import base64
import datetime as dt
import json
import logging
import os
import shutil
import subprocess
import time
from mimetypes import guess_extension

import requests
from retry import retry

from pollinator.constants import available_models
from pollinator.ipfs_to_json import ipfs_subfolder_to_json


class BackgroundCommand:
    def __init__(self, cmd):
        self.cmd = cmd

    def __enter__(self):
        self.proc = subprocess.Popen(
            f"exec {self.cmd}",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return self.proc

    def __exit__(self, type, value, traceback):
        time.sleep(15)
        logging.info(f"Killing background command: {self.cmd}")
        self.proc.kill()
        logs, errors = self.proc.communicate()
        logging.info(f"   Logs: {logs}")
        logging.error(f"   errors: {errors}")
        logging.info("killed")


loaded_model = None


class RunningCogModel:
    def __init__(self, image, output_path):
        self.image = image
        gpus = "--gpus all"  # TODO check if GPU is available
        # Start cog container
        self.cog_cmd = (
            f'bash -c "docker run --rm --name cogmodel --network host '
            f"--mount type=bind,source={output_path},target=/outputs "
            f'{gpus} {image} &> {output_path}/log" &'
        )
        logging.info(f"Initializing cog command: {self.cog_cmd}")

    def __enter__(self):
        global loaded_model
        if loaded_model == self.image:
            try:
                assert (
                    requests.get(
                        "http://localhost:5000/",
                    ).status_code
                    == 200
                )
                logging.info(f"Model already loaded: {self.image}")
                return
            except:  # noqa
                logging.info(f"Loaded model unhealthy, restarting: {self.image}")
        kill_cog_model()
        logging.info(f"Starting {self.image}: {self.cog_cmd}")
        os.system(self.cog_cmd)
        loaded_model = self.image

    def __exit__(self, type, value, traceback):
        # we leave the model running in case the next request needs the same model
        pass


def kill_cog_model():
    try:
        os.system("docker kill cogmodel")
        time.sleep(3)  # we have to wait until the container name is available again :/
        logging.info(f"Killed previous model ({loaded_model})")
    except Exception as e:  # noqa
        logging.error(f"Error killing cogmodel: {type(e)}{e}")


def process_message(message):
    """Message example:
     {
        'end_time': None,
        'image': some-image-with-hash,
        'input': 'url to ipfs',
        'logs': None, # to be filled with a url to the log file
        'output': None, # to be filled with a url to the output folder ipfs
        'request_submit_time': timestamp,
        'start_time': # to be filled with now
    }
    """
    # start process: pollinate --send --ipns --nodeid nodeid --path /content/ipfs
    logging.info(f"processing message: {message}")
    message["start_time"] = dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    ipfs_root = os.path.abspath("/tmp/ipfs/")
    output_path = os.path.join(ipfs_root, "output")
    input_path = os.path.join(ipfs_root, "input")
    image = message["image"]
    if image not in available_models():
        raise ValueError(f"Model not found: {image}")

    clean_folder(input_path)
    prepare_output_folder(output_path)
    inputs = fetch_inputs(message["input"])

    # Write inputs to /input
    for key, value in inputs.items():
        write_folder(input_path, key, json.dumps(value))

    # Start IPFS syncing
    with BackgroundCommand(
        f"pollinate-cli.js --send --ipns --nodeid {message['input']} --debounce 70"
        f" --path {ipfs_root} > /tmp/cid"
    ):
        with BackgroundCommand(f"python pollinator/outputs_to_db.py {message['input']}"):
            # Update output in pollen db whenever a new file is generated
            os.system(f"touch {output_path}/dummy")
            with RunningCogModel(image, output_path):
                response = send_to_cog_container(inputs, output_path)
                if response.status_code == 500:
                    kill_cog_model()

    # read cid from the last line of /tmp/cid
    with open("/tmp/cid", "r") as f:
        cid = f.readlines()[-1].strip()

    logging.info("Got CID: " + cid + ". Triggering pinning and social post")

    # run pinning and social post
    os.system(f"node /usr/local/bin/pinning-cli.js {cid}")
    os.system(f"node /usr/local/bin/social-post-cli.js {cid}")
    logging.info("done pinning and social post")

    message["end_time"] = dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    return message


def prepare_output_folder(output_path):
    logging.info(f"Mounting output folder: {output_path}")
    os.makedirs(output_path, exist_ok=True)
    clean_folder(output_path)
    write_folder(output_path, "done", "false")
    write_folder(output_path, "time_start", str(int(time.time())))


def fetch_inputs(ipfs_cid):
    try:
        inputs = ipfs_subfolder_to_json(ipfs_cid, "input")
    except KeyError:
        raise ValueError(f"IPFS hash {ipfs_cid} could ot be resolved")
    logging.info(f"Fetched inputs from IPFS {ipfs_cid}: {inputs}")
    return inputs


@retry(tries=120, delay=2)
def send_to_cog_container(inputs, output_path):
    # Send message to cog container
    payload = {"input": inputs}
    response = requests.post("http://localhost:5000/predictions", json=payload)

    logging.info(f"response: {response}")

    write_folder(output_path, "time_start", str(int(time.time())))

    if response.status_code != 200:
        logging.error(response.text)
        write_folder(output_path, "log", response.text, "a")
        write_folder(output_path, "success", "false")
        kill_cog_model()
        raise Exception(
            f"Error while sending message to cog container: {response.text}"
        )
    else:
        write_http_response_files(response, output_path)
        write_folder(output_path, "done", "true")
        write_folder(output_path, "success", "true")
        logging.info(f"Set done to true in {output_path}")

    return response


# Since ipfs reads its data from the filesystem we write keys and values to files using this function
# TODO: needs to handle URL values
def write_folder(path, key, value, mode="w"):
    os.makedirs(path, exist_ok=True)
    with open(f"{path}/{key}", mode) as f:
        f.write(value)


def clean_folder(folder):
    os.makedirs(folder, exist_ok=True)
    for filename in os.listdir(folder):
        file_path = os.path.join(folder, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print("Failed to delete %s. Reason: %s" % (file_path, e))


def write_http_response_files(response, output_path):
    try:
        for i, encoded_file in enumerate(response.json()["output"]):
            try:
                encoded_file = encoded_file["file"]
            except TypeError:
                pass  # already a string
            meta, encoded = encoded_file.split(";base64,")
            extension = guess_extension(meta.split(":")[1])
            with open(f"{output_path}/out_{i}{extension}", "wb") as f:
                f.write(base64.b64decode(encoded))
    except Exception as e:  # noqa
        logging.info(f"http response not written to file: {type(e)} {e}")


if __name__ == "__main__":
    message = {
        "pollen_id": "0f4d29cf132e48b89b86d4d922916be7",
        "notebook": "voodoohop/dalle-playground",
        "ipfs": "QmYdTVSzh6MNDBKMG9Z1vqfzomTYWczV3iP15YBupKSsM1",
    }
    process_message(message)

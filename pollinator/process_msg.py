import base64
import logging
import os
import shutil
import subprocess
import time
from mimetypes import guess_extension

import requests
from retry import retry

from pollinator.constants import lookup_model
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
        time.sleep(30)
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
            f'bash -c "docker run --rm --detach --name cogmodel --network host '
            f"--mount type=bind,source={output_path},target=/outputs "
            f'{gpus} {image} &> {output_path}/log"'
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
    except:  # noqa
        pass


def process_message(message):
    # start process: pollinate --send --ipns --nodeid nodeid --path /content/ipfs
    logging.info(f"processing message: {message}")
    ipfs_root = os.path.abspath("/tmp/ipfs/")
    output_path = os.path.join(ipfs_root, "output")
    input_path = os.path.join(ipfs_root, "input")
    image = lookup_model(message["notebook"], None)
    if image is None:
        raise ValueError(f"Model not found: {message['notebook']}")

    prepare_output_folder(output_path)
    inputs = fetch_inputs(message["ipfs"])

    # Write inputs to /input
    # The reasoning behind having /output and /input was that we could always reproduce the run from the artifact that is produced
    # And also for the UI to display some information about the model used to create the output
    # It may have been more consistent to use pollinate --receive instead of fetching the ipfs content via HTTP
    # But since we're going to switch this out soon it doesn't matter.

    for key, value in inputs.items():
        write_folder(input_path, key, value)

    # Start IPFS syncing
    with BackgroundCommand(
        f"pollinate --send --ipns --nodeid {message['pollen_id']}"
        f" --path {ipfs_root}"
    ):
        with RunningCogModel(image, output_path):
            response = send_to_cog_container(inputs, output_path)
            if response.status_code == 500:
                kill_cog_model()


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


@retry(tries=90, delay=2)
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
        raise Exception(
            f"Error while sending message to cog container: {response.text}"
        )
    else:
        write_http_response_files(response, output_path)
        write_folder(output_path, "done", "true")
        write_folder(output_path, "success", "true")

    return response


# Since ipfs reads its data from the filesystem we write keys and values to files using this function
def write_folder(path, key, value, mode="w"):
    os.makedirs(path, exist_ok=True)
    with open(f"{path}/{key}", mode) as f:
        f.write(value)


def clean_folder(folder):
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
        "ipfs": "QmfW4HUN35dqCqBzmtbv96MyRjXHiyhckpULE9SxKUSBvu",
    }
    process_message(message)

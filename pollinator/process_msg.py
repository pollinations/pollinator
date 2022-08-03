import base64
import datetime as dt
import json
import logging
import os
import shutil
import subprocess
import time
import traceback
from mimetypes import guess_extension

import psutil
import requests
from retry import retry

from pollinator import constants
from pollinator.constants import available_models, supabase, test_image
from pollinator.ipfs_to_json import ipfs_subfolder_to_json

ipfs_root = os.path.abspath("/tmp/ipfs/")
output_path = os.path.join(ipfs_root, "output")
input_path = os.path.join(ipfs_root, "input")


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
        logging.info(f"Killing background command: {self.cmd}")
        tree_kill(self.proc.pid)
        try:
            logs, errors = self.proc.communicate(timeout=2)
            logs, errors = logs.decode("utf-8"), errors.decode("utf-8")
            logging.info(f"   Logs: {logs}")
            logging.error(f"   errors: {errors}")
        except subprocess.TimeoutExpired:
            pass


loaded_model = None


@retry(tries=450, delay=2)
def cogmodel_can_start_healthy():
    """Wait for the cogmodel to load and return a healthy status code
    If no docker command is running anymore, throw an exception"""
    # check that cogmodel is a running as a container
    if "cogmodel" not in os.popen("docker ps").read():
        logging.error("No running cogmodel found in docker ps. Exiting")
        return False
    # check that it is healthy. This step might fail and and be retried
    response = requests.get("http://localhost:5000/")
    logging.info("Cog model is not healthy")
    print(os.popen("cat /tmp/ipfs/output/logs").read())
    return response.status_code == 200


@retry(tries=60, delay=1)
def wait_for_docker_container():
    logging.error(f"Trying to find cog container: {os.popen('docker ps').read()}")
    assert "cogmodel" in os.popen("docker ps").read()


class UnhealthyModel(Exception):
    pass


class RunningCogModel:
    def __init__(self, image, output_path):
        self.image = image
        gpus = "--gpus all" if image != test_image else ""
        # Start cog container
        self.cog_cmd = (
            f'bash -c "docker run --rm --name cogmodel -p 5000:5000 '
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
        wait_for_docker_container()
        if not cogmodel_can_start_healthy():
            raise UnhealthyModel()

        loaded_model = self.image

    def __exit__(self, type, value, traceback):
        pass


def kill_cog_model():
    try:
        os.system("docker kill cogmodel")
        time.sleep(3)  # we have to wait until the container name is available again :/
        logging.info(f"Killed previous model ({loaded_model})")
    except Exception as e:  # noqa
        logging.error(f"Error killing cogmodel: {type(e)}{e}")


def process_message(message):
    logging.info(f"processing message: {message}")
    updated_message = {}
    updated_message["start_time"] = dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    response = None
    try:
        response, success = start_container_and_perform_request_and_send_outputs(
            message
        )
        updated_message["success"] = success
    except Exception as e:
        logging.error(e)
        updated_message["success"] = False
        updated_message["error"] = str(e)

    try:
        data = (
            supabase.table(constants.db_name)
            .select("*")
            .eq("input", message["input"])
            .execute()
            .data
        )
        assert len(data) == 1
        cid = data[0]["output"]

        data = (
            supabase.table(constants.db_name)
            .update(updated_message)
            .eq("input", message["input"])
            .execute()
        )
        print("Pollen set to done in db: ", data)
        logging.info(f"Got CID: {cid}. Triggering pinning and social post")
        # run pinning and social post
        os.system(f"node /usr/local/bin/pinning-cli.js {cid}")
        os.system(f"node /usr/local/bin/social-post-cli.js {cid}")
        logging.info("done pinning and social post")
        updated_message["final_output"] = cid
        updated_message["end_time"] = dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        updated_message["logs"] = f"https://ipfs.pollinations.ai/ipfs/{cid}/output/log"

    except Exception as e:  # noqa
        traceback.print_exc()

    return response


def start_container_and_perform_request_and_send_outputs(message):
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
        f"pollinate-cli.js --send --debounce 70 --path {ipfs_root} "
        f"| python pollinator/outputs_to_db.py {message['input']} {constants.db_name}"
    ):
        with RunningCogModel(image, output_path):
            response = send_to_cog_container(inputs, output_path)
            if response.status_code == 500:
                kill_cog_model()
                success = False
            else:
                success = True
    # Now send final results once
    os.system(
        f"pollinate-cli.js --send --path {ipfs_root} --once "
        f"| python pollinator/outputs_to_db.py {message['input']} {constants.db_name}",
    )
    return message, success


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


def send_to_cog_container(inputs, output_path):
    # Send message to cog container
    payload = {"input": inputs}
    response = requests.post("http://localhost:5000/predictions", json=payload)

    logging.info(f"response: {response}")

    write_folder(output_path, "time_start", str(int(time.time())))

    if response.status_code != 200:
        logging.error(response.text)
        write_folder(output_path, "cog_response", response.text, "a")
        kill_cog_model()
        raise Exception(
            f"Error while sending message to cog container: {response.text}"
        )
    else:
        write_http_response_files(response, output_path)
        write_folder(output_path, "done", "true")
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
        traceback.print_exc()


def tree_kill(pid):
    print(f"Killing process {pid} and their complete family")
    parent = psutil.Process(pid)
    for child in parent.children(recursive=True):
        print(f"Killing child: {child} {child.pid}")
        child.kill()
    parent.kill()


# if __name__ == "__main__":
#     message = {
#         "input": "QmNgrCgddkXpRhiZVYHuuuM5KCu4DJDPP9F1K9kW99etfY",
#         "image": "majesty"
#     }
#     process_message(message)

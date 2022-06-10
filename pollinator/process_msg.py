import logging
import os
import shutil
import subprocess
import time

import requests
from retry import retry

from pollinator.constants import images
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
        time.sleep(5)
        logging.info(f"Killing background command: {self.cmd}")
        self.proc.kill()
        logs, errors = self.proc.communicate()
        logging.info(f"   Logs: {logs}")
        logging.error(f"   errors: {errors}")
        logging.info("killed")


class RunningCogModel:
    def __init__(self, image, output_path):
        self.image = image
        gpus = "--gpus all"  # TODO check if GPU is available
        # Start cog container
        self.cog_cmd = (
            f"docker run --rm --detach --name cogmodel --network host "
            f"--mount type=bind,source={output_path},target=/outputs "
            f"{gpus} {image}"
        )
        logging.info(f"Initializing cog command: {self.cog_cmd}")

    def __enter__(self):
        logging.info("Starting cog model")
        os.system(self.cog_cmd)

    def __exit__(self, type, value, traceback):
        logging.info(f"Killing {self.image}")
        os.system("docker kill cogmodel")


def process_message(message):
    # start process: pollinate --send --ipns --nodeid nodeid --path /content/ipfs
    logging.info(f"processing message: {message}")
    ipfs_root = os.path.abspath("/tmp/ipfs/")
    output_path = os.path.join(ipfs_root, "output")
    image = images.get(message["notebook"], None)
    if image is None:
        raise ValueError(f"Model not found: {message['notebook']}")

    prepare_output_folder(output_path)
    inputs = fetch_inputs(message["ipfs"])

    # Start IPFS syncing
    with BackgroundCommand(
        f"pollinate --send --ipns --nodeid {message['pollen_id']}"
        f" --path {ipfs_root}"
    ):
        with RunningCogModel(image, output_path):
            send_to_cog_container(inputs, output_path)


def prepare_output_folder(output_path):
    logging.info(f"Mounting output folder: {output_path}")
    shutil.rmtree(output_path, ignore_errors=True)
    os.makedirs(output_path, exist_ok=True)
    with open(f"{output_path}/done", "w") as f:
        f.write("false")
    with open(f"{output_path}/time_start", "w") as f:
        f.write(str(int(time.time())))


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

    logging.info(f"response: {response} {response.text}")

    with open(f"{output_path}/time_start", "w") as f:
        f.write(str(int(time.time())))

    if response.status_code != 200:
        logging.error(response.text)
        with open(f"{output_path}/error.txt", "w") as f:
            f.write(response.text)
        with open(f"{output_path}/success", "w") as f:
            f.write("false")
        raise Exception(
            f"Error while sending message to cog container: {response.text}"
        )
    else:
        with open(f"{output_path}/done", "w") as f:
            f.write("true")
        with open(f"{output_path}/success", "w") as f:
            f.write("true")

    return response

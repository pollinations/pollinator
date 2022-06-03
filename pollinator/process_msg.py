import logging
import os
import shutil
import subprocess
import time
from uuid import uuid4

import requests
from retry import retry

from pollinator.constants import images


class BackgroundCommand:
    def __init__(self, cmd):
        self.cmd = cmd

    def __enter__(self):
        self.proc = subprocess.Popen(
            self.cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return self.proc

    def __exit__(self, type, value, traceback):
        time.sleep(5)
        logging.info(f"Killing background command: {self.cmd} which generated these logs:")
        logging.info(self.proc.stdout.read().decode("utf-8"))
        self.proc.kill()
        self.proc.wait()
        self.proc.stdout.close()
        self.proc.stderr.close()


class RunningCogModel:
    def __init__(self, message, output_path):
        self.message = message
        self.output_path = output_path
        self.container_id_file = str(uuid4().hex)

    def __enter__(self):
        image = images[self.message["notebook"]]
        gpus = "--gpus all"  # TODO check if GPU is available
        # Start cog container
        cog_cmd = (
            f"docker run --rm --detach --cidfile {self.container_id_file} --network host "
            f"--mount type=bind,source={self.output_path},target=/outputs "
            f"{gpus} {image}"
        )
        logging.info(cog_cmd)
        os.system(cog_cmd)

    def __exit__(self, type, value, traceback):
        if os.path.exists(self.container_id_file):
            container_id = open(self.container_id_file).read()
            logging.info(f"Killing cog container: {container_id}")
            os.system(f"docker kill {container_id}")
            os.remove(self.container_id_file)
        else:
            logging.info("No container id file found")


def process_message(message):
    # start process: pollinate --send --ipns --nodeid nodeid --path /content/ipfs
    logging.info(f"processing message: {message}")
    output_path = os.path.abspath("/tmp/outputs")
    container_id_file = "./container_id"

    prepare_output_folder(output_path, container_id_file)

    # # Start IPFS syncinv=g
    with BackgroundCommand(
        f"pollinate --send --ipns --nodeid {message['pollen_id']}"
        f" --path {output_path}"
    ):
        with RunningCogModel(message, output_path):
            send_to_cog_container(message, output_path)


def prepare_output_folder(output_path, container_id_file):
    logging.info(f"Mounting output folder: {output_path}")
    shutil.rmtree(output_path, ignore_errors=True)
    os.makedirs(output_path, exist_ok=True)
    if os.path.exists(container_id_file):
        os.remove(container_id_file)

@retry(tries=90, delay=2)
def send_to_cog_container(message, output_path):
    # Send message to cog container
    payload = {"input": message["inputs"]}
    response = requests.post("http://localhost:5000/predictions", json=payload)

    logging.info(f"response: {response} {response.text}")

    if response.status_code != 200:
        logging.error(response.text)
        with open(f"{output_path}/error.txt", "w") as f:
            f.write(response.text)
        raise Exception(
            f"Error while sending message to cog container: {response.text}"
        )

    return response

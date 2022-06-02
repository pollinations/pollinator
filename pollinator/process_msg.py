import logging
import os
import shutil
import time
import subprocess

import requests
from retry import retry

from pollinator.constants import images


def process_message(message):
    # start process: pollinate --send --ipns --nodeid nodeid --path /content/ipfs
    logging.info(f"processing message: {message}")
    output_path = os.path.abspath("/tmp/outputs")
    container_id_file = "./container_id"

    prepare_output_folder(output_path, container_id_file)

    # # Start IPFS syncinv=g
    ipfs_pid = subprocess.Popen(
        f"pollinate --send --ipns --nodeid {message['pollen_id']}"
        f" --path {output_path} ",
        shell=True).pid

    # process message
    start_cog_container(message, output_path, container_id_file)
    time.sleep(10)
    try:
        send_to_cog_container(message, output_path)
    except Exception as e:
        kill_cog_container(container_id_file)
        time.sleep(5)
        subprocess.Popen(["kill", str(ipfs_pid)])
        raise e
    kill_cog_container(container_id_file)
    # # kill pollinate
    time.sleep(5)
    subprocess.Popen(["kill", str(ipfs_pid)])


def prepare_output_folder(output_path, container_id_file):
    logging.info(f"Mounting output folder: {output_path}")
    shutil.rmtree(output_path, ignore_errors=True)
    os.makedirs(output_path, exist_ok=True)
    if os.path.exists(container_id_file):
        os.remove(container_id_file)


def start_cog_container(message, output_path, container_id_file):
    # docker run --rm -ti --publish 6421:5000 --mount type=bind,source=/tmp,target=/src/output  r8.im/pixray/text2image@sha256:f6ca4f09e1cad8c4adca2c86fd1f4c9121f5f2e6c2f00408ab19c4077192fd23 /bin/bash
    image = images[message["notebook"]]
    gpus = "--gpus all"  # TODO check if GPU is available
    # Start cog container
    cog_cmd = (
        f"docker run --rm --detach --cidfile {container_id_file} --network host "
        f"--mount type=bind,source={output_path},target=/outputs "
        f"{gpus} {image}"
    )
    logging.info(cog_cmd)
    os.system(cog_cmd)


@retry(tries=30, delay=1)
def send_to_cog_container(message, output_path):
    # Send message to cog container
    payload = {"input": message["inputs"], "output_file_prefix": str(output_path)}
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


def kill_cog_container(container_id_file):
    if os.path.exists(container_id_file):
        container_id = open(container_id_file).read()
        logging.info(f"Killing cog container: {container_id}")
        os.system(f"docker kill {container_id}")
        os.remove(container_id_file)
    else:
        logging.info("No container id file found")

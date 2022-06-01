import os
import subprocess
import time
import tempfile
import json
import shutil
import requests
import logging
from retry import retry

from pollinator.constants import images

def debug(f):
    def debugged(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logging.error(type(e), e)
            breakpoint()
            f(*args, **kwargs)
    return debugged


@retry(tries=10, delay=1)
def send_to_cog_container(message, output_path):
    # Send message to cog container
    payload = {
        "inputs": message['inputs']
    }  
    response = requests.post("http://localhost:6421/predictions", json=payload)

    logging.info(f"response: {response} {response.text}")

    if response.status_code != 200:
        logging.error(response.text)
        with open(f"{output_path}/error.txt", "w") as f:
            f.write(response.text)
        raise Exception(f"Error while sending message to cog container: {response.text}")

    return response


def kill_cog_container(container_id_file):
    if os.path.exists(container_id_file):
        container_id = open(container_id_file).read()
        logging.info(f"Killing cog container: {container_id}")
        os.system(f"docker kill {container_id}")
        os.remove(container_id_file)
    else:
        logging.info("No container id file found")


def start_cog_container(message, output_path, container_id_file):
    image = images[message['notebook']]
    gpus = "" if True else "--gpus all" # TODO check if GPU is available
    # Start cog container
    cog_cmd = (
        f'docker run --rm --detach --cidfile {container_id_file} --publish 6421:5000 '
        f'--mount type=bind,source={output_path},target=/src/output '
        f'{gpus} {image}'
    )
    logging.info(cog_cmd)
    os.system(cog_cmd)


def prepare_output_folder(output_path, container_id_file):
    logging.info(f"Mounting output folder: {output_path}")
    shutil.rmtree(output_path, ignore_errors=True)
    os.makedirs(output_path, exist_ok=True)
    if os.path.exists(container_id_file):
        os.remove(container_id_file)


# @debug
def process_message(message):
    # start process: pollinate --send --ipns --nodeid nodeid --path /content/ipfs
    logging.info(f"processing message: {message}")
    output_path = os.path.abspath("/tmp/outputs")
    container_id_file = "./container_id"

    prepare_output_folder(output_path, container_id_file)
    
    # # Start IPFS syncinv=g
    # ipfs_pid = subprocess.Popen(
    #     f"pollinate --send --ipns --nodeid {message['pollen_id']}"
    #     f" --path {output_path} ",
    #     shell=True).pid

    # process message
    start_cog_container(message, output_path, container_id_file)
    time.sleep(10)
    send_to_cog_container(message, output_path)
    kill_cog_container(container_id_file)
    
    # # kill pollinate
    # time.sleep(5)
    # subprocess.Popen(["kill", str(ipfs_pid)])

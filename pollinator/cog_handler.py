import base64
import logging
import os
import time
import traceback
from mimetypes import guess_extension

import requests
from retry import retry

from pollinator.constants import test_image
from pollinator.ipfs_to_json import write_folder


@retry(tries=450, delay=2)
def cogmodel_can_start_healthy():
    """Wait for the cogmodel to load and return a healthy status code
    If no docker command is running anymore, throw an exception"""
    logging.info("Checking if cogmodel is healthy...")

    # check that cogmodel is a running as a containere
    if "cogmodel" not in os.popen("docker ps").read():
        logging.error("No running cogmodel found in docker ps. Exiting")
        return False
    # check that it is healthy. This step might fail and and be retried
    response = requests.get("http://localhost:5000/")

    print(os.popen("cat /tmp/ipfs/output/logs").read())
    return response.status_code == 200


@retry(tries=60, delay=1)
def wait_for_docker_container(cog_cmd):
    logging.info(cog_cmd)
    os.system(cog_cmd)
    logging.error(f"Trying to find cog container: {os.popen('docker ps').read()}")
    assert "cogmodel" in os.popen("docker ps").read()
    # with open("/tmp/ipfs/output/log", "r") as f:
    #     docker_logs = f.read()
    #     if "is already in use by container" in docker_logs:
    #         logging.error(f"container name cogmodel is already in use: {docker_logs}")
    #         kill_cog_model()
    #         raise Exception(docker_logs)


@retry(tries=60, delay=1)
def wait_until_cogmodel_is_free():
    logging.info("docker kill cogmodel")
    os.system("docker kill cogmodel")
    assert "cogmodel" not in os.popen("docker ps").read()
    logging.info("cogmodel killed and is container name is free.")
    time.sleep(3)


def kill_cog_model():
    try:
        wait_until_cogmodel_is_free()
        logging.info(f"Killed previous model ({loaded_model})")
    except Exception as e:  # noqa
        logging.error(f"Error killing cogmodel: {type(e)}{e}")


loaded_model = None


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
        wait_for_docker_container(self.cog_cmd)
        if not cogmodel_can_start_healthy():
            raise UnhealthyModel()

        loaded_model = self.image

    def __exit__(self, type, value, traceback):
        pass


def send_to_cog_container(inputs, output_path):
    logging.info("Send to cog model")
    # Send message to cog container
    payload = {"input": inputs}
    response = requests.post("http://localhost:5000/predictions", json=payload)

    logging.info(f"response: {response}")

    write_folder(output_path, "time_start", str(int(time.time())))

    if response.status_code != 200:
        logging.error(response.text)
        write_folder(output_path, "cog_response", response.text, "a")
        try:
            print("Unhealthy cog model with these logs:")
            print(os.popen("docker logs cogmodel").read())
        except:  # noqa
            pass
        kill_cog_model()
        raise Exception(
            f"Error while sending message to cog container: {response.text}"
        )
    else:
        write_http_response_files(response, output_path)
        write_folder(output_path, "done", "true")
        logging.info(f"Set done to true in {output_path}")

    return response


def write_http_response_files(response, output_path):
    try:
        output = response.json()["output"]
        if not isinstance(output, list):
            output = [output]
        for i, encoded_file in enumerate(output):
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

import base64
import datetime as dt
import json
import logging
import time
import traceback
from mimetypes import guess_extension

import docker
import requests

from pollinator import constants
from pollinator.ipfs_to_json import write_folder

docker_client = docker.from_env()


class UnhealthyCogContainer(Exception):
    pass


loaded_model = None
MAX_NUM_POLLEN_UNTIL_RESTART = 100


class RunningCogModel:
    def __init__(self, image, output_path):
        self.image_name = image
        self.image = docker_client.images.get(image)
        self.output_path = output_path
        self.container = None
        self.pollen_start_time = None
        self.pollen_since_container_start = 0

    def __enter__(self):
        global loaded_model
        # Check if the container is already running
        self.pollen_start_time = dt.datetime.now()
        try:
            running_image = docker_client.containers.get("cogmodel").image
        except docker.errors.NotFound:
            running_image = None
        if (
            self.image == running_image
            and self.pollen_since_container_start < MAX_NUM_POLLEN_UNTIL_RESTART
        ):
            self.pollen_since_container_start += 1
            logging.info(f"Model already loaded: {self.image}")
            return self
        # Kill the running container if it is not the same model
        self.kill_cog_model(logs=False)
        self.pollen_since_container_start = 0
        # Start the container
        if constants.has_gpu:
            gpus = [
                docker.types.DeviceRequest(
                    count=1,
                    capabilities=[["gpu"]],
                )
            ]
        else:
            gpus = []
        container = docker_client.containers.run(
            self.image,
            detach=True,
            name="cogmodel",
            ports={"5000/tcp": 5000},
            volumes={self.output_path: {"bind": "/outputs", "mode": "rw"}},
            remove=True,
            device_requests=gpus,
        )
        logging.info(f"Starting {self.image}: {container}")
        # Wait for the container to start
        self.wait_until_cogmodel_is_healthy()
        loaded_model = self.image_name
        return self

    def __exit__(self, type, value, traceback):
        # write container logs to output folder
        self.write_logs()

    def write_logs(self):
        try:
            logs = (
                docker_client.containers.get("cogmodel")
                .logs(stdout=True, stderr=True, since=self.pollen_start_time)
                .decode("utf-8")
            )
            write_folder(self.output_path, "container.log", logs)
        except (docker.errors.NotFound, docker.errors.APIError):
            pass

    def shutdown(self):
        self.write_logs()
        self.kill_cog_model()

    def kill_cog_model(self, logs=True):
        # get cogmodel logs and write them to output folder and kill container
        for _ in range(5):
            try:
                container = docker_client.containers.get("cogmodel")
                if logs:
                    logs = container.logs(
                        stdout=True, stderr=True, since=self.pollen_start_time
                    ).decode("utf-8")
                    write_folder(f"{constants.output_path}", "log", logs)
                container.kill()
                logging.info(f"Killed {self.image}")
                time.sleep(1)
            except docker.errors.NotFound:
                return
            except docker.errors.APIError:
                time.sleep(1)

    def wait_until_cogmodel_is_healthy(self, timeout=40 * 60):
        # Wait for the container to start
        logging.info(f"Waiting for {self.image} to start")
        for i in range(timeout):
            try:
                assert (
                    requests.get(
                        "http://localhost:5000/",
                    ).status_code
                    == 200
                )
                logging.info(f"Model healthy: {self.image}")
                return
            except:  # noqa
                time.sleep(1)
        raise UnhealthyCogContainer(f"Model unhealthy: {self.image}")


def send_to_cog_container(inputs, output_path):
    logging.info("Send to cog model")
    # Send message to cog container
    payload = {"input": inputs}
    response = requests.post("http://localhost:5000/predictions", json=payload)
    logging.info(f"response: {response}")
    write_folder(output_path, "time_start", str(int(time.time())))
    write_folder(output_path, "done", "true")
    if response.status_code != 200:
        write_folder(output_path, "cog_response", json.dumps(response.text))
        write_folder(output_path, "success", "false")
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

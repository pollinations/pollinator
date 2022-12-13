import base64
import datetime as dt
import json
import logging
import time
from mimetypes import guess_extension

import docker
import requests

from pollinator import constants

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
            container_object = docker_client.containers.get("cogmodel")
            running_image = container_object.image
            logging.info(
                f"got running image from docker_client: {running_image} with status {container_object.status}"
            )

            # check if image is created but not started. start in that case
            if container_object.status == "created":
                logging.info(f"container is created but not running. starting")
                container_object.start()

        except docker.errors.NotFound:
            running_image = None
        logging.info(f"Running image: {running_image}")

        if (
            self.image == running_image
            and self.pollen_since_container_start < MAX_NUM_POLLEN_UNTIL_RESTART
            and running_image is not None
        ):
            self.pollen_since_container_start += 1
            logging.info(f"Model already loaded: {self.image}")
            loaded_model = self.image_name
            return self
        # Kill the running container if it is not the same model
        self.kill_cog_model()
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
            auto_remove=True,
            device_requests=gpus,
            stderr=True,
            tty=True,
            environment={
                "SUPABASE_URL": constants.url,
                "SUPABASE_API_KEY": constants.supabase_api_key,
                "SUPABASE_ID": constants.supabase_id,
                "OPENAI_API_KEY": constants.openai_api_key,
                "WEB3STORAGE_TOKEN": constants.web3storage_token,
            },
        )
        logging.info(f"Starting {self.image}: {container}")
        # Wait for the container to start
        self.wait_until_cogmodel_is_healthy()
        loaded_model = self.image_name
        return self

    def __exit__(self, type, value, traceback):
        pass

    def shutdown(self):
        self.kill_cog_model()

    def kill_cog_model(self):
        # get cogmodel logs and write them to output folder and kill container
        for i in range(5):
            try:
                logging.info(
                    f"trying to kill and remove cogmodel container. attempt {i}"
                )
                container = docker_client.containers.get("cogmodel")
                container.kill()
                logging.info(f"Killed {self.image}")
                time.sleep(1)
                container.remove()
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

    def get_logs(self):
        container = docker_client.containers.get("cogmodel")
        logs = container.logs(since=self.pollen_start_time, timestamps=True).decode(
            "utf-8"
        )
        return logs


def send_to_cog_container(inputs, output_path):
    logging.info("Send to cog model", inputs)
    inputs = flatten_image_inputs(inputs)
    # Send message to cog container
    payload = {"input": inputs}
    response = requests.post("http://localhost:5000/predictions", json=payload)
    return response


# transform dict of the form
# {"image": {"input1.png": "https://store.pollinations.ai/ipfs/Qm..."} }
# to
# {"image": "https://store.pollinations.ai/ipfs/Qm..."}
def flatten_image_inputs(content):
    for key, value in content.items():
        # if value is object, it is a dict of the form {"input1.png": "https://store.pollinations.ai/ipfs/Qm..."}
        if isinstance(value, dict):
            content[key] = list(value.values())[1]
    return content

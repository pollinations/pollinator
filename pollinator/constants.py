import logging
import os
import socket
import time
from functools import lru_cache

import requests
from dotenv import load_dotenv
from supabase import Client, create_client

from pollinator import utils

try:
    ip = requests.get("http://ip.42.pl/raw").text
except:  # noqa
    ip = "?"
try:
    hostname, _, _ = socket.gethostbyaddr(ip)
except:  # noqa
    hostname = ip


load_dotenv()
url: str = os.environ.get("SUPABASE_URL")
supabase_api_key: str = os.environ.get("SUPABASE_API_KEY")
supabase: Client = create_client(url, supabase_api_key)
supabase_id: str = os.environ["SUPABASE_ID"]
db_name = ""  # will be set by main.py or a test
test_image = "no-gpu-test-image"
i_am_busy = False
has_gpu = utils.system("nvidia-smi") == 0
gpu_flag = "--gpus all" if has_gpu else ""
pollinator_image = os.environ.get("POLLINATOR_IMAGE")


pollinator_group = os.environ.get("POLLINATOR_GROUP", "T4")


model_index = (
    "https://raw.githubusercontent.com/pollinations/model-index/main/metadata.json"
)


def image_exists(image_name):
    return image_name.split("@")[0] in utils.popen(f"docker images {image_name}").read()


def get_ttl_hash(seconds=300):
    """Return the same value withing `seconds` time period"""
    return round(time.time() / seconds)


@lru_cache()
def available_models_(ttl_hash=None):
    del ttl_hash  # to emphasize we don't use it and to shut pylint up
    metadata = requests.get(model_index).json()
    supported = []
    for image, meta in metadata.items():
        try:
            if pollinator_group in meta["meta"]["pollinator_group"]:
                if image_exists(image):
                    supported += [image]
        except KeyError:
            pass
    return supported + [test_image]


def available_models():
    return available_models_(get_ttl_hash())


logging.info(f"Pollinator group: {pollinator_group}")
logging.info(f"Pollinator image: {pollinator_image}")
logging.info(f"Available models: {available_models()}")
logging.info(f"DB: {db_name}")
logging.info(f"IP: {ip}")
logging.info(f"hostname: {hostname}")
logging.info(f"GPU: {has_gpu}")

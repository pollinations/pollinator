#!/usr/bin/env python
# coding: utf-8
import logging
import os
import shutil
import signal
import subprocess
import sys
import time

import psutil
import requests
import timeout_decorator

from pollinator import constants, utils
from pollinator.s3_wrapper import s3store


@timeout_decorator.timeout(20)
def cid_to_json(cid: str):
    """Get a CID of a dir in IPFS and return a dict. Runs "node /usr/local/bin/getcid-cli.js [cid]
    with {filename: filecontent} structure, where
        - files with file extension are skipped
        - filecontents containing a filename are resolved to absolute URIs
    """
    logging.info(f"Fetching IPFS dir {cid}")
    if cid.startswith("s3:"):
        return s3store.get(cid)
    else:
        response = requests.get(f"{constants.storage_service_endpoint}/{cid}")
        content = response.json()
        return content


# we don't actually need to download referenced files
# because cog does it and is happy with URLs
# def download_referenced_files(data, target):
#     # If it's a dict, recursively call this function
#     # if a value is a URL, download it
#     if isinstance(data, dict):
#         for key, value in data.items():
#             download_referenced_files(value, f"{target}/{key}")
#     # If it's a list, recursively call this function
#     elif isinstance(data, list):
#         for i, value in enumerate(data):
#             download_referenced_files(value, f"{target}/{key}/{i}")
#     # If it's a URL, download it
#     elif isinstance(data, str) and data.startswith("http"):
#         os.makedirs(os.path.dirname(target), exist_ok=True)
#         logging.info(f"Downloading {data} to {target}")
#         urllib.request.urlretrieve(data, f"{target}")


def fetch_inputs(cid: str):
    try:
        data = cid_to_json(cid)
        inputs = data["input"]
    except KeyError:
        raise ValueError(f"CID {cid} could ot be resolved")
    logging.info(f"Fetched inputs from IPFS {cid}: {inputs}")
    # download_referenced_files(inputs, constants.input_path)
    return inputs


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


def tree_kill(pid):
    print(f"Killing process {pid} and their complete family")
    parent = psutil.Process(pid)
    for child in parent.children(recursive=True):
        print(f"Killing child: {child} {child.pid}")
        # send SIGINT to the process
        child.send_signal(signal.SIGINT)
    parent.send_signal(signal.SIGINT)


store_url = "https://store.pollinations.ai"


def store(data: dict):
    return s3store.put(data)
    # data = remove_none(data)
    # response = requests.post(f"{store_url}/", json=data)
    # response.raise_for_status()
    # cid = response.text
    # return cid


def remove_none(data):
    if isinstance(data, dict):
        return {k: remove_none(v) for k, v in data.items() if v is not None}
    elif isinstance(data, list):
        return [remove_none(v) for v in data if v is not None]
    else:
        return data


def lookup(cid: str):
    response = requests.get(f"{store_url}/ipfs/{cid}")
    response.raise_for_status()
    data = adjust_format(response.json())
    return data


def adjust_format(data):
    if isinstance(data, list):
        return [adjust_format(x) for x in data]
    elif isinstance(data, dict):
        if "0" in data:
            return [adjust_format(data[k]) for k in sorted(data.keys()) if k.isdigit()]
        else:
            return {k: adjust_format(v) for k, v in data.items() if k != ".cid"}
    else:
        return data


if __name__ == "__main__":
    fetch_inputs(sys.argv[1])

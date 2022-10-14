#!/usr/bin/env python
# coding: utf-8
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import requests
from urllib import parse
import urllib.request

import psutil
import timeout_decorator

from pollinator import utils, constants



@timeout_decorator.timeout(20)
def cid_to_json(cid: str):
    """Get a CID of a dir in IPFS and return a dict. Runs "node /usr/local/bin/getcid-cli.js [cid]
    with {filename: filecontent} structure, where
        - files with file extension are skipped
        - filecontents containing a filename are resolved to absolute URIs
    """
    logging.info(f"Fetching IPFS dir {cid}")
    content = requests.get(f"{constants.storage_service_endpoint}/?cid={cid}").json()
    return content


def write_folder(path, key, value, mode="w"):
    os.makedirs(path, exist_ok=True)
    with open(f"{path}/{key}", mode) as f:
        f.write(value)


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
        inputs = cid_to_json(cid)["input"]
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


def prepare_output_folder(output_path):
    logging.info(f"Mounting output folder: {output_path}")
    os.makedirs(output_path, exist_ok=True)
    clean_folder(output_path)
    write_folder(output_path, "done", "false")
    write_folder(output_path, "time_start", str(int(time.time())))


class BackgroundCommand:
    def __init__(self, cmd, on_exit=None, wait_before_exit=3):
        self.cmd = cmd
        self.on_exit = on_exit
        self.wait_before_exit = wait_before_exit

    def __enter__(self):
        self.proc = subprocess.Popen(["/bin/bash", "-c", self.cmd])
        return self.proc

    def __exit__(self, type, value, traceback):
        logging.info(f"Killing background command: {self.cmd}")
        time.sleep(self.wait_before_exit)
        tree_kill(self.proc.pid)
        if self.on_exit is not None:
            try:
                utils.system(self.on_exit)
            except timeout_decorator.timeout_decorator.TimeoutError:
                logging.error(f"Timeout while running on_exit command: {self.on_exit}")


def tree_kill(pid):
    print(f"Killing process {pid} and their complete family")
    parent = psutil.Process(pid)
    for child in parent.children(recursive=True):
        print(f"Killing child: {child} {child.pid}")
        child.kill()
    parent.kill()

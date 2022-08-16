#!/usr/bin/env python
# coding: utf-8
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from typing import Any, Dict

import psutil
import timeout_decorator


@timeout_decorator.timeout(20)
def ipfs_dir_to_json(cid: str):
    """Get a CID of a dir in IPFS and return a dict. Runs "node /usr/local/bin/getcid-cli.js [cid]
    with {filename: filecontent} structure, where
        - files with file extension are skipped
        - filecontents containing a filename are resolved to absolute URIs
    """
    logging.info(f"Fetching IPFS dir {cid}")

    # use subprocess to run getcid-cli.js

    proc = subprocess.Popen(
        ["node", "/usr/local/bin/getcid-cli.js", cid],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        logging.error(f"Error while fetching IPFS dir {cid}: {stderr}")
        sys.exit(1)

    # parse stdout to json
    json_str = stdout.decode("utf-8")
    print(json_str)
    json_dict = json.loads(json_str)

    return json_dict


def ipfs_subfolder_to_json(cid: str, subdir: str) -> Dict[str, Any]:
    """Get the contents of a subdir of a cid as json"""
    json_dict = ipfs_dir_to_json(cid)
    return json_dict[subdir]


def fetch_inputs(ipfs_cid):
    try:
        inputs = ipfs_subfolder_to_json(ipfs_cid, "input")
    except KeyError:
        raise ValueError(f"IPFS hash {ipfs_cid} could ot be resolved")
    logging.info(f"Fetched inputs from IPFS {ipfs_cid}: {inputs}")
    return inputs


# Since ipfs reads its data from the filesystem we write keys and values to files using this function
# TODO: needs to handle URL values
def write_folder(path, key, value, mode="w"):
    os.makedirs(path, exist_ok=True)
    with open(f"{path}/{key}", mode) as f:
        f.write(value)


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
    def __init__(self, cmd):
        self.cmd = cmd
        
    def __init__(self, cmd, on_exit=None):
        self.cmd = cmd
        self.on_exit = on_exit

    def __enter__(self):
        self.proc = subprocess.Popen(
            f"exec {self.cmd}",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return self.proc

    def __exit__(self, type, value, traceback):
        logging.info(f"Killing background command: {self.cmd}")
        tree_kill(self.proc.pid)
        try:
            logs, errors = self.proc.communicate(timeout=2)
            logs, errors = logs.decode("utf-8"), errors.decode("utf-8")
            logging.info(f"   Logs: {logs}")
            logging.error(f"   errors: {errors}")
        except subprocess.TimeoutExpired:
            pass
        if self.on_exit is not None:
            os.system(self.on_exit)


def tree_kill(pid):
    print(f"Killing process {pid} and their complete family")
    parent = psutil.Process(pid)
    for child in parent.children(recursive=True):
        print(f"Killing child: {child} {child.pid}")
        child.kill()
    parent.kill()


# if an argument is passed, it is a cid


def main():
    if len(sys.argv) > 1:
        cid = sys.argv[1]
        print(ipfs_dir_to_json(cid)["input"])
    else:
        print("Usage: ipfs_to_json.py <cid>")


if __name__ == "__main__":
    main()

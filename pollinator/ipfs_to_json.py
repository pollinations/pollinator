#!/usr/bin/env python
# coding: utf-8
import json
import logging
import subprocess
import sys
from typing import Any, Dict


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


# if an argument is passed, it is a cid


def main():
    if len(sys.argv) > 1:
        cid = sys.argv[1]
        print(ipfs_dir_to_json(cid)["input"])
    else:
        print("Usage: ipfs_to_json.py <cid>")


if __name__ == "__main__":
    main()

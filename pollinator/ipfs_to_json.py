#!/usr/bin/env python
# coding: utf-8
import requests
import logging
from typing import List, Dict, Any, Optional

ipfs_endpoint = "https://ipfs.pollinations.ai/api/v0"
# ipfs_endpoint = "https://api.nft.storage"
ipfs_files_endpoint = "https://nftstorage.link/ipfs"


def first_true(iterable: List, pred):
    return next(filter(pred, iterable), None)


def named_list_to_dict(object_list: List[Dict[str, str]]) -> Dict[str, str]:
    """Turn [{"name": "some-name", ...}, ...] into {"some-name": ..., ...}"""
    return {i['Name']: i for i in object_list}


def ipfs_dir_to_json(cid: str):
    """Get a CID of a dir in IPFS and return a dict
    with {filename: filecontent} structure, where
        - files with file extension are skipped
        - filecontents containing a filename are resolved to absolute URIs
    """
    object_list = requests.get(f"{ipfs_endpoint}/ls?arg={cid}")\
                          .json()
    object_list = object_list['Objects'][0]['Links']

    metadata = named_list_to_dict(object_list)
    contents = {}
    files = {} # Name: URI
    for name, value in metadata.items():
        uri = f"{ipfs_files_endpoint}/{cid}/{name}"
        # skip files but track which files are available
        if "." in name:
            files[name] = uri
            continue
        # Get filecontent
        content = None
        if value['Size'] < 250:
            resp = requests.get(uri)
            try:
                content = resp.json()
            except Exception as e:
                try:
                    content = resp.content.decode('utf-8')
                except:
                    pass
        if content is None:        
            logging.warning(f"Large file: {name} in {ipfs_files_endpoint}/{value['Hash']} - skipped in json conversion")
        contents[name] = content
    
    contents = {key: files.get(value, value) for key, value in contents.items()}
    
    return contents


def ipfs_subfolder_to_json(cid: str, subdir: str) -> Dict[str, Any]:
    """Get the contents of a subdir of a cid as json"""
    response = requests.get(f"{ipfs_endpoint}/ls?arg={cid}")
    data = first_true(response.json()['Objects'], pred=lambda i: i['Hash']==cid)["Links"]
    links = {i['Name']: i['Hash'] for i in data}
    inputs = ipfs_dir_to_json(links[subdir])
    return inputs
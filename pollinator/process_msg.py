import datetime as dt
import json
import logging
import traceback

from pollinator import constants, utils
from pollinator.cog_handler import RunningCogModel, send_to_cog_container
from pollinator.constants import (
    available_models,
    input_path,
    ipfs_root,
    output_path,
    supabase,
)
from pollinator.storage import clean_folder, fetch_inputs, store


def process_message(message):
    logging.info(f"processing message: {message}")
    updated_message = {}
    updated_message["start_time"] = dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    response = None
    try:
        (
            response_cid,
            success,
            logs_cid,
        ) = start_container_and_perform_request_and_send_outputs(message)
        updated_message["success"] = success
        updated_message["output"] = response_cid
        updated_message["logs"] = logs_cid
    except Exception as e:
        logging.error(f"process_message: caught {e}")
        updated_message["success"] = False
        updated_message["error"] = str(e)

    try:
        updated_message["end_time"] = dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        data = (
            supabase.table(constants.db_name)
            .update(updated_message)
            .eq("input", message["input"])
            .execute()
            .data
        )

        assert len(data) == 1
        cid = data[0]["output"]
        # todo get cid from data
        # run pinning and social post
        utils.system(f"node /usr/local/bin/pinning-cli.js {cid}")
        utils.system(f"node /usr/local/bin/social-post-cli.js {cid}")

    except Exception as e:  # noqa
        traceback.print_exc()
    print("process_message: done")
    return response


def start_container_and_perform_request_and_send_outputs(message):
    """Message example:
     {
        'end_time': None,
        'image': some-image-with-hash,
        'input': 'url to ipfs',
        'logs': None, # to be filled with a url to the log file
        'output': None, # to be filled with a url to the output folder ipfs
        'request_submit_time': timestamp,
        'start_time': # to be filled with now
    }
    """
    # start process: pollinate --send --ipns --nodeid nodeid --path /content/ipfs
    image = message["image"]
    if image not in available_models():
        raise ValueError(f"Model not found: {image}")
    inputs = fetch_inputs(message["input"])
    clean_folder(output_path)

    # Start IPFS syncing
    with RunningCogModel(image, output_path) as cogmodel:
        response = send_to_cog_container(inputs, output_path)
        get_logs_cmd = (
            f"docker logs cogmodel --since {cogmodel.pollen_start_time.isoformat()}"
        )
        logs = cogmodel.get_logs()
        response_cid = None
        if response.status_code == 500:
            cogmodel.shutdown()
            success = False
        elif response.status_code == 200:
            response = response.json()
            success = response["status"] == "succeeded"
            response_cid = store(response.get("output"))
        elif 400 <= response.status_code < 500:
            success = False
    logs_cid = store({"logs": logs})
    return response_cid, success, logs_cid

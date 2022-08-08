import datetime as dt
import json
import logging
import os
import traceback

from pollinator import constants
from pollinator.cog_handler import (
    RunningCogModel,
    kill_cog_model,
    send_to_cog_container,
)
from pollinator.constants import available_models, supabase
from pollinator.ipfs_to_json import (
    BackgroundCommand,
    clean_folder,
    fetch_inputs,
    prepare_output_folder,
    write_folder,
)

ipfs_root = os.path.abspath("/tmp/ipfs/")
output_path = os.path.join(ipfs_root, "output")
input_path = os.path.join(ipfs_root, "input")


def process_message(message):
    logging.info(f"processing message: {message}")
    updated_message = {}
    updated_message["start_time"] = dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    response = None
    try:
        response, success = start_container_and_perform_request_and_send_outputs(
            message
        )
        updated_message["success"] = success
    except Exception as e:
        logging.error(e)
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
        print("Pollen set to done in db: ", data)
        logging.info(f"Got CID: {cid}. Triggering pinning and social post")
        # run pinning and social post
        os.system(f"node /usr/local/bin/pinning-cli.js {cid}")
        os.system(f"node /usr/local/bin/social-post-cli.js {cid}")
        logging.info("done pinning and social post")

    except Exception as e:  # noqa
        traceback.print_exc()

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

    clean_folder(input_path)
    prepare_output_folder(output_path)
    inputs = fetch_inputs(message["input"])
    # Write inputs to /input
    for key, value in inputs.items():
        write_folder(input_path, key, json.dumps(value))

    # Start IPFS syncing
    with BackgroundCommand(
        f"pollinate-cli.js --send --debounce 70 --path {ipfs_root} "
        f"| python pollinator/outputs_to_db.py {message['input']} {constants.db_name}",
        on_exit=f"pollinate-cli.js --send --path {ipfs_root} --once "
        f"| python pollinator/outputs_to_db.py {message['input']} {constants.db_name}",
    ):
        with RunningCogModel(image, output_path):
            response = send_to_cog_container(inputs, output_path)
            if response.status_code == 500:
                kill_cog_model()
                success = False
            else:
                success = True
    return message, success

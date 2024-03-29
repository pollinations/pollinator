import datetime as dt
import json
import logging
import traceback

from pollinator import constants, utils
from pollinator.cog_handler import RunningCogModel, send_to_cog_container
from pollinator.constants import (available_models, input_path, ipfs_root,
                                  output_path, supabase)
from pollinator.storage import (BackgroundCommand, clean_folder, fetch_inputs,
                                prepare_output_folder, write_folder)


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
        f"pollinate-cli.js --send --path {ipfs_root} --nodeid {message['input']}  --ipns --debounce 4000"
    ):
        with RunningCogModel(image, output_path) as cogmodel:
            with BackgroundCommand(
                f"docker logs cogmodel -f --since {cogmodel.pollen_start_time.isoformat()} > {output_path}/log",
                wait_before_exit=3,
            ):
                response = send_to_cog_container(inputs, output_path)
                if response.status_code == 500:
                    cogmodel.shutdown()
                    success = False
                else:
                    success = True
        write_folder(output_path, "success", json.dumps(success))
        # sleep for 5 seconds to make sure the log file is written
        utils.system("sleep 5")
    # utils.system(
    #     f"/usr/local/bin/pollinate-cli.js --send --path {ipfs_root} --once --nodeid {message['input']} --ipns"
    # )
    return message, success

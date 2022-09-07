import logging
import sys
import time

import click
import docker

from pollinator import cog_handler, constants
from pollinator.constants import supabase
from pollinator.process_msg import process_message

logging.basicConfig(format="%(asctime)s %(levelname)s:%(message)s", level=logging.INFO)

print(constants.hostname)

docker_client = docker.from_env()


@click.command()
@click.option("--db_name", default=constants.db_name, help="Name of the db to use.")
def main(db_name):
    constants.db_name = db_name
    """First finish all existing tasks, then go into infinite loop"""
    check_if_chrashed()
    finish_all_tasks()
    poll_forever()


def check_if_chrashed():
    """If the worker crashed, the input cid is still in the file system.
    In that case, we need to unlock the message in the db."""
    # check if done=False and input_cid is in file system
    try:
        status_path = constants.input_path / "done"
        with open(status_path, "r") as f:
            done = f.read()
        if done == "true":
            return
    except FileNotFoundError:
        return
    # We crashed, unlock the message and increase the attempt counter
    try:
        with open(constants.input_cid_path, "r") as f:
            input_cid = f.read()
        with open(constants.attempt_path, "r") as f:
            attempt = int(f.read())
        if attempt > constants.max_attempts:
            logging.error(f"Too many attempts, giving up on {input_cid}")
            supabase.table(constants.db_name).update({"success": False}).eq(
                "input", input_cid
            ).execute()
            return
        supabase.table(constants.db_name).update(
            {
                "processing_started": False,
                "pollinator_group": None,
                "worker": None,
                "attempt": attempt + 1,
            }
        ).eq("input", input_cid).execute()
    except FileNotFoundError:
        pass


def poll_forever():
    while True:
        try:
            finish_all_tasks()
            time.sleep(1)
        except Exception as e:
            logging.error(e)
            time.sleep(5)


def finish_all_tasks():
    while (message := get_task_from_db()) is not None:
        # After this iteraton, the task will be processed either by this worker or by another worker
        maybe_process(message)


def get_task_from_db():
    """Scan the db for tasks that are not in progress. If there are none, return None
    If there are many, return one with the maximal priority.
    If there are still many, return one with the currently loaded model.
    If there are still many, return one with the oldest request_submit_time."""
    candidates = (
        supabase.table("pollen")
        .select("*")
        .eq("processing_started", False)
        .in_("image", constants.available_models())
        .order("priority", desc=True)
        .order("request_submit_time", desc=False)
        .execute()
    ).data
    if len(candidates) == 0:
        return None
    priority = candidates[0]["priority"]
    candidates = [c for c in candidates if c["priority"] == priority]
    ready_candidates = [c for c in candidates if c["image"] == cog_handler.loaded_model]
    if len(ready_candidates) > 0:
        return ready_candidates[0]
    else:
        return candidates[0]


def check_pollinator_updates():
    """Check if the image of the currently running container has the same
    hash as the latest pollinator. If not, kill the running container"""
    try:
        running_pollinator_image = docker_client.containers.get("pollinator").image
    except docker.errors.NotFound:
        logging.info(
            "No pollinator container running. This must be the dev environment."
        )
        return
    latest_pollinator_image = docker_client.images.get(constants.pollinator_image)
    if running_pollinator_image != latest_pollinator_image:
        print("Pollinator image has changed, restarting container", flush=True)
        try:
            docker_client.containers.get("pollinator").kill()
        except docker.errors.NotFound:
            sys.exit(0)
    else:
        logging.info("Pollinator is up to date")


def maybe_process(message):
    check_pollinator_updates()
    if message["image"] not in constants.available_models():
        logging.info(f"Ignoring message for {message['image']}")
        return None
    if (
        message["image"] != cog_handler.loaded_model
        and cog_handler.loaded_model is not None
    ):
        logging.info(
            "Message is not for this model, waiting a bit to give other workers a chance"
        )
        time.sleep(1)
    elif (
        message["image"] != cog_handler.loaded_model
        and cog_handler.loaded_model is None
    ):
        logging.info("No model loaded, wait 0.5s to give other workers a chance")
        time.sleep(0.5)
    try:
        lock_message(message)
        return process_message(message)
    except LockError:
        return None


class LockError(Exception):
    pass


def lock_message(message):
    """Lock the message in the db and throw an error if it is already locked"""
    data = (
        supabase.table(constants.db_name)
        .update(
            {
                "processing_started": True,
                "pollinator_group": constants.pollinator_group,
                "worker": constants.hostname,
            }
        )
        .eq("input", message["input"])
        .eq("processing_started", False)
        .execute()
    )
    if len(data.data) == 0:
        raise LockError(f"Message {message['input']} is already locked")
    # write input cid to disk in case the worker crashes
    with open(constants.input_cid_path, "w") as f:
        f.write(message["input"])
    with open(constants.attempt_path, "w") as f:
        f.write(str(message["attempt"]))


if __name__ == "__main__":
    main()

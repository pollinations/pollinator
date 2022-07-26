import logging
import time
import traceback

import click
from realtime.connection import Socket

from pollinator import constants, process_msg
from pollinator.constants import supabase, supabase_api_key, supabase_id
from pollinator.process_msg import process_message

logging.basicConfig(format="%(asctime)s %(levelname)s:%(message)s", level=logging.INFO)


@click.command()
@click.option("--db_name", default=constants.db_name, help="Name of the db to use.")
def main(db_name):
    constants.db_name = db_name
    """First finish all existing tasks, then go into infinite loop"""
    finish_all_tasks()
    subscribe_while_idle()


def finish_all_tasks():
    while (message := get_task_from_db()) is not None:
        # After this iteraton, the task will be processed either by this worker or by another worker
        maybe_process(message)


def get_task_from_db():
    """Scan the db for tasks that are not in progress. If there are none, return None
    If there are many, return the olderst one for the currently process_msg.loaded_model.
    If there are none for the process_msg.loaded_model, return the oldest."""
    data = (
        supabase.table(constants.db_name)
        .select("*")
        .eq("processing_started", False)
        .eq("image", process_msg.loaded_model)
        .order("request_submit_time")
        .execute()
    )
    if len(data.data) > 0:
        return data.data[0]
    # No tasks found, include tasks for other images
    data = (
        supabase.table(constants.db_name)
        .select("*")
        .eq("processing_started", False)
        .order("request_submit_time")
        .execute()
    )
    if len(data.data) > 0:
        return data.data[0]
    # There is no task
    return None


def maybe_process(message):
    if (
        message["image"] != process_msg.loaded_model
        and process_msg.loaded_model is not None
    ):
        logging.info(
            "Message is not for this model, waiting a bit to give other workers a chance"
        )
        time.sleep(1)
    elif (
        message["image"] != process_msg.loaded_model
        and process_msg.loaded_model is None
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
        .update({"processing_started": True})
        .eq("input", message["input"])
        .eq("processing_started", False)
        .execute()
    )
    if len(data.data) == 0:
        raise LockError(f"Message {message['input']} is already locked")


def subscribe_while_idle():
    """Subscribe to db inserts in supabase and wait for one to arrive.
    As soon as one arrives, unsubscribe and return the message."""
    url = f"wss://{supabase_id}.supabase.co/realtime/v1/websocket?apikey={supabase_api_key}&vsn=1.0.0"
    s = Socket(url)

    while True:
        try:
            s.connect()

            channel = s.set_channel(f"realtime:public:{constants.db_name}")

            def unsubscribe_and_process(payload):
                if constants.i_am_busy:
                    print("Ignoring task, am busy")
                    return
                constants.i_am_busy = True
                maybe_process(payload["record"])
                finish_all_tasks()
                constants.i_am_busy = False
                print("Ready to accept a task")

            channel.join().on("INSERT", unsubscribe_and_process)
            s.listen()
        except Exception as e:
            logging.info(f"Socket stopped listening, restarting: {e}")
            traceback.print_exc()


if __name__ == "__main__":
    main()

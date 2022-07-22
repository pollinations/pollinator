import logging
import time

import click
from realtime.connection import Socket

from pollinator import constants
from pollinator.constants import supabase, supabase_api_key, supabase_id
from pollinator.process_msg import loaded_model, process_message

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
    If there are many, return the olderst one for the currently loaded_model.
    If there are none for the loaded_model, return the oldest."""
    data = (
        supabase.table(constants.db_name)
        .select("*")
        .eq("processing_started", False)
        .eq("image", loaded_model)
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
    if message["image"] != loaded_model:
        logging.info(
            "Message is not for this model, waiting a bit to give other workers a chance"
        )
        time.sleep(1)
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
                channel.off("INSERT")
                maybe_process(payload["record"])
                finish_all_tasks()
                channel.on("INSERT", unsubscribe_and_process)

            channel.join().on("INSERT", unsubscribe_and_process)
            s.listen()
        except Exception as e:
            logging.info(f"Socket stopped listening, restarting: {e}")


if __name__ == "__main__":
    main()

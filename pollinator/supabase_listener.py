import logging
import os

import dotenv
from realtime.connection import Socket
from supabase import Client, create_client

from pollinator.process_msg import process_message

dotenv.load_dotenv()
logging.basicConfig(format="%(asctime)s %(levelname)s:%(message)s", level=logging.INFO)


SUPABASE_ID: str = os.environ["SUPABASE_ID"]
API_KEY: str = os.environ["SUPABASE_API_KEY"]
SUPABASE_URL: str = os.environ["SUPABASE_URL"]


supabase: Client = create_client(SUPABASE_URL, API_KEY)


def callback1(payload):
    """Payload example:
    {
        'columns': [
            {'name': 'input', 'type': 'varchar'},
            {'name': 'output', 'type': 'varchar'},
            {'name': 'image', 'type': 'varchar'},
            {'name': 'start_time', 'type': 'timestamp'},
            {'name': 'end_time', 'type': 'timestamp'},
            {'name': 'logs', 'type': 'varchar'},
            {'name': 'request_submit_time', 'type': 'timestamp'}],
        'commit_timestamp': '2022-07-15T18:19:24Z',
        'errors': None,
        'record': {
            'end_time': None,
            'image': None,
            'input': 'iyg',
            'logs': None,
            'output': None,
            'request_submit_time': None,
            'start_time': None},
        'schema': 'public',
        'table': 'pollen',
        'type': 'INSERT'
    }
    """
    # Check if the image exists
    if payload["record"]["image"] is not None:
        # Process the message
        updated_payload = process_message(payload["record"])

    # Update the database entry
    data = (
        supabase.table("pollens")
        .update(updated_payload)
        .eq("input", payload["record"]["input"])
        .execute()
    )
    print(data)


def clb2(payload):
    import time

    print(payload["record"])
    time.sleep(10)


if __name__ == "__main__":
    URL = f"wss://{SUPABASE_ID}.supabase.co/realtime/v1/websocket?apikey={API_KEY}&vsn=1.0.0"
    s = Socket(URL)
    s.connect()

    channel_1 = s.set_channel("realtime:*")
    channel_1.join().on("INSERT", clb2)
    s.listen()

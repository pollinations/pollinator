"""
Usage:
python pollinator/outputs_to_db.py {message['input']}

Watches /tmp/cid and writes its content into the output field as a json list
"""
from supabase import create_client, Client
import time
import click
import os
from dotenv import load_dotenv


load_dotenv()
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_API_KEY")
supabase: Client = create_client(url, key)


@click.command()
@click.argument("pollen_input_id", type=str)
def main(pollen_input_id: str):
    written_cids = 0
    while True:
        with open("/tmp/cid") as f:
            cids = [i.strip() for i in f.readlines()]
        if len(cids) > written_cids:
            data = supabase.table("pollen").update({"output": cids}).eq("input", pollen_input_id).execute()
            written_cids = len(cids)
            print("Updated: ", data)
        time.sleep(0.1)


if __name__ == "__main__":
    main()
"""
Usage:
python pollinator/outputs_to_db.py {message['input']}

Watches /tmp/cid and writes its content into the output field as a json list
"""
import time

import click

from pollinator import constants
from pollinator.constants import supabase


@click.command()
@click.argument("pollen_input_id", type=str)
def main(pollen_input_id: str):
    written_cids = 0
    while True:
        with open("/tmp/cid") as f:
            cids = [i.strip() for i in f.readlines()]
        if len(cids) > written_cids:
            data = (
                supabase.table(constants.db_name)
                .update({"output": cids})
                .eq("input", pollen_input_id)
                .execute()
            )
            written_cids = len(cids)
            print("Updated: ", data)
        time.sleep(0.1)


if __name__ == "__main__":
    main()

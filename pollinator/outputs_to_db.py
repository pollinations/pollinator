"""
Usage:
python pollinator/outputs_to_db.py {message['input']}

Watches /tmp/cid and writes its content into the output field as a json list
"""
import time
import traceback

import click

from pollinator import constants
from pollinator.constants import supabase


@click.command()
@click.argument("pollen_input_id", type=str)
def main(pollen_input_id: str):
    written_cids = 0
    while True:
        try:
            with open("/tmp/cid") as f:
                cids = [i.strip() for i in f.readlines()]
            if len(cids) > written_cids:
                data = []
                while len(data) == 0:
                    data = (
                        supabase.table(constants.db_name)
                        .update({"output": cids[-1]})
                        .eq("input", pollen_input_id)
                        .execute()
                    ).data
                written_cids = len(cids)
                print("Updated: ", data)
            time.sleep(0.1)
        except Exception: # noqa
            # Sometimes we read broken cids that cannot be written to db
            # I assume this happens when we read the cid file in the wrong moment
            # That's why we just try again
            traceback.print_exc()


if __name__ == "__main__":
    main()

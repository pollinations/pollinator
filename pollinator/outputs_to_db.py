"""
Usage:
python pollinator/outputs_to_db.py {message['input']}

Watches /tmp/cid and writes its content into the output field as a json list
"""
import traceback

import click
from postgrest.exceptions import APIError

from pollinator import constants
from pollinator.constants import supabase


@click.command()
@click.argument("pollen_input_id", type=str)
def main(pollen_input_id: str):
    while True:
        try:
            cid = input()
            data = []
            while len(data) == 0:
                data = (
                    supabase.table(constants.db_name)
                    .update({"output": cid})
                    .eq("input", pollen_input_id)
                    .execute()
                ).data
        except APIError:  # noqa
            # Sometimes we read broken cids that cannot be written to db
            # I assume this happens when we read the cid file in the wrong moment
            # That's why we just try again
            traceback.print_exc()


if __name__ == "__main__":
    main()

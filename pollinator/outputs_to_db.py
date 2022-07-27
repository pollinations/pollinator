"""
Usage:
python pollinator/outputs_to_db.py {message['input']}
"""
import sys
import traceback

import click
from postgrest.exceptions import APIError

from pollinator import constants
from pollinator.constants import supabase


@click.command()
@click.argument("pollen_input_id", type=str)
@click.argument("db_name", type=str)
def main(pollen_input_id: str, db_name: str):
    for cid in sys.stdin:
        cid = cid.strip()
        try:
            while len(supabase.table(db_name)
                .update({"output": cid})
                .eq("input", pollen_input_id)
                .execute().data) != 1:
                print(f"Failed to update: {pollen_input_id} (with output={cid}), trying again...")
        except APIError:  # noqa
            # Sometimes we read broken cids that cannot be written to db
            # I assume this happens when we read the cid file in the wrong moment
            # That's why we just try again
            traceback.print_exc()


if __name__ == "__main__":
    main()

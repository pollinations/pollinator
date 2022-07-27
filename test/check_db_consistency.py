from pollinator.constants import supabase
from pollinator import constants
from pollinator.ipfs_to_json import ipfs_subfolder_to_json


def check_input_output_consistency():
    """
    Check that input and output are consistent
    """
    data = (
        supabase.table(constants.db_name)
        .select("input", "output", "request_submit_time")
        .eq("success", True)
        .execute()
    )
    data = sorted(data.data, key=lambda x: x["request_submit_time"], reverse=True)
    for row in data:
        original = ipfs_subfolder_to_json(row["input"], "input")
        referenced = ipfs_subfolder_to_json(row["output"], "input")
        assert referenced == original


if __name__ == "__main__":
    check_input_output_consistency()
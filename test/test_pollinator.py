import os
import tempfile
import time
from uuid import uuid4

from pollinator import constants
from pollinator.constants import supabase
from pollinator.process_msg import BackgroundCommand


class DebugCommand:
    def __init__(self, cmd):
        self.cmd = cmd

    def __enter__(self):
        print("Please start: \n", self.cmd)
        input()

    def __exit__(self, type, value, traceback):
        print("Please stop: \n", self.cmd)
        input()


def upload_prompt_to_ipfs(prompt):
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, "input"))
        path = f"{tmpdir}/input/Prompt"
        with BackgroundCommand(
            f"pollinate-cli.js --send --ipns --debounce 70 --path {tmpdir} > /tmp/cid"
        ):
            with open(path, "w") as f:
                f.write(prompt)
        with open("/tmp/cid") as f:
            cid = f.read().strip().split("\n")[-1].strip()

        return cid


def send_valid_dummy_request():
    prompt = uuid4().hex
    cid = upload_prompt_to_ipfs(prompt)
    image = "no-gpu-test-image"
    payload = {"input": cid, "image": image}
    print("Insert:", payload)
    data = supabase.table(constants.db_name).insert(payload).execute()
    assert len(data.data) > 0, f"Failed to insert {cid} into db"


def send_invalid_dummy_request():
    cid = f"something-that-is-not-a-cid-{uuid4().hex}"
    data = (
        supabase.table(constants.db_name)
        .insert({"input": cid, "image": constants.test_image})
        .execute()
    )
    assert len(data.data) > 0, f"Failed to insert {cid} into db"


def clear_db():
    supabase.table(constants.db_name).delete().neq(
        "input", "i just want to delete all rows"
    ).execute()


def test_many_open_requests_in_db():
    constants.db_name = "pollen_test_db"
    clear_db()
    for _ in range(2):
        send_valid_dummy_request()
    with BackgroundCommand("python pollinator/main.py --db_name pollen_test_db"):
        time.sleep(60)
    assert_success_is_not(None)
    assert_success_is_not(False)


def test_no_open_request_subscribe_and_wait():
    constants.db_name = "pollen_test_db"
    clear_db()
    with BackgroundCommand("python pollinator/main.py --db_name pollen_test_db"):
        for _ in range(2):
            send_valid_dummy_request()
        time.sleep(30)
        for _ in range(2):
            send_valid_dummy_request()
        time.sleep(90)
    assert_success_is_not(None)
    assert_success_is_not(False)


def test_invalid_request_in_db():
    constants.db_name = "pollen_test_db"
    clear_db()
    with BackgroundCommand("python pollinator/main.py --db_name pollen_test_db"):
        for _ in range(2):
            send_invalid_dummy_request()
        time.sleep(30)
        for _ in range(2):
            send_invalid_dummy_request()
        time.sleep(60)
    assert_success_is_not(None)
    assert_success_is_not(True)


def assert_success_is_not(success=None):
    """Assert that all requests"""
    data = supabase.table(constants.db_name).select("*").execute()
    data = [i for i in data.data if i["success"] == success]
    assert len(data) == 0, f"Found {len(data)} with success={success}: {data}"

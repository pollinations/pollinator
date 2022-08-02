from pollinator import constants
from pollinator.constants import supabase

constants.db_name = "pollen_test_db"


def clear_db():
    supabase.table("pollen_test_db").delete().neq(
        "input", "i just want to delete all rows"
    ).execute()


class DebugCommand:
    def __init__(self, cmd):
        self.cmd = cmd

    def __enter__(self):
        print("Please start: \n", self.cmd)
        input()

    def __exit__(self, type, value, traceback):
        print("Please stop: \n", self.cmd)
        input()


def copy_failed_pollens(original_db, target_db):
    failed = supabase.table(original_db).select("*").eq("success", False).execute().data
    for pollen in failed:
        supabase.table(target_db).insert(
            {"input": pollen["input"], "image": pollen["image"]}
        ).execute()
    return failed


def test_failed_pollens_work():
    clear_db()
    with DebugCommand("python pollinator/main.py --db_name pollen_test_db"):
        failed = copy_failed_pollens("pollen", "pollen_test_db")
        print(failed)


if __name__ == "__main__":
    test_failed_pollens_work()

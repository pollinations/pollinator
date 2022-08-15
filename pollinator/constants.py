import os

import requests
from dotenv import load_dotenv
from supabase import Client, create_client


load_dotenv()
url: str = os.environ.get("SUPABASE_URL")
supabase_api_key: str = os.environ.get("SUPABASE_API_KEY")
supabase: Client = create_client(url, supabase_api_key)
supabase_id: str = os.environ["SUPABASE_ID"]
db_name = ""  # will be set by main.py or a test
test_image = "no-gpu-test-image"
i_am_busy = False


model_index = (
    "https://raw.githubusercontent.com/pollinations/model-index/main/images.json"
)


def image_exists(image_name):
    return image_name.split("@")[0] in os.popen(f"docker images {image_name}").read()


def available_models():
    supported = list(requests.get(model_index).json().values()) + [
        "no-gpu-test-image",
        "avatarclip",
    ] 
    available = [i for i in supported if image_exists(i)]
    return available


if __name__ == "__main__":
    print(available_models())

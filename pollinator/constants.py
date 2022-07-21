import os

import requests
from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()
url: str = os.environ.get("SUPABASE_URL")
supabase_api_key: str = os.environ.get("SUPABASE_API_KEY")
supabase: Client = create_client(url, supabase_api_key)
supabase_id: str = os.environ["SUPABASE_ID"]


model_index = (
    "https://raw.githubusercontent.com/pollinations/model-index/main/images.json"
)


def available_models():
    return requests.get(model_index).json().values()  # TODO .keys()

import requests

model_index = (
    "https://raw.githubusercontent.com/pollinations/model-index/main/images.json"
)


def lookup_model(key, default=None):
    return requests.get(model_index).json().get(key, default)

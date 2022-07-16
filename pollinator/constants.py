import requests

model_index = (
    "https://raw.githubusercontent.com/pollinations/model-index/main/images.json"
)


def available_models():
    return ["majesty"]
    return requests.get(model_index).json().values() # TODO .keys()

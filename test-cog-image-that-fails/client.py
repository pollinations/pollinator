import requests

payload = {
    "input": {"Prompt": "Hello, how are you?"},
}
response = requests.post("http://localhost:5000/predictions", json=payload)
breakpoint()

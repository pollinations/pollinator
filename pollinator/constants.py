import requests


class JsonFileDict(dict):
    """Acts like a dict, but loads the data from a file on first access or whenever a key is missing."""

    def __init__(self, file_url):
        self.file_url = file_url
        response = requests.get(self.file_url)
        super().__init__(response.json())

    def __getitem__(self, key):
        if key not in self:
            response = requests.get(self.file_url)
            self.update(response.json())
        if key in self:
            return self.get(key)
        return super().__getitem__(key)


images = JsonFileDict(
    "https://raw.githubusercontent.com/pollinations/model-index/main/images.json"
)

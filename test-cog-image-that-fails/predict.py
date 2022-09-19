# Prediction interface for Cog ⚙️
# https://github.com/replicate/cog/blob/main/docs/python.md

import time

from cog import BasePredictor, Input
from tqdm import tqdm


class Predictor(BasePredictor):
    def setup(self):
        """Load the model into memory to make running multiple predictions efficient"""
        # self.model = torch.load("./weights.pth")

    def predict(self, Prompt: str = Input(description="Grayscale input image")) -> str:
        """Run a single prediction on the model"""
        " use stdout for tqdm progress bar"
        for i in tqdm(range(30)):
            print(i)
            time.sleep(1)
        raise Exception("Hopefully this exception shows up in the logs.")
        return Prompt

# Prediction interface for Cog ⚙️
# https://github.com/replicate/cog/blob/main/docs/python.md

from cog import BasePredictor, Input


class Predictor(BasePredictor):
    def setup(self):
        """Load the model into memory to make running multiple predictions efficient"""
        # self.model = torch.load("./weights.pth")

    def predict(self, Prompt: str = Input(description="Grayscale input image")) -> str:
        """Run a single prediction on the model"""
        # processed_input = preprocess(input)
        # output = self.model(processed_input, scale)
        # return postprocess(output)
        return Prompt

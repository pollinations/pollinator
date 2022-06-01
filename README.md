# pollinator
- Read tasks from an SQS queue 
    [code taken from here](https://perandrestromhaug.com/posts/writing-an-sqs-consumer-in-python/)
- execute tasks
- stream outputs to topic specified in queue item

# Run locally
Install package:
```sh
# Install dependencies
pip install -e ".[test]"

# Install pre-commit hooks
brew install pre-commit
pre-commit install -t pre-commit
```

Setup localstack (see [../README.md](../README.md))
And start the worker
```
python pollinator/sqs_consumer.py --aws_endpoint http://localhost:4566 --aws_profile localstack
```
Or build an run the image:
```
docker build -t pollinator .
docker run -p 8000:5000 --env-file .env pollinator
```
# Requests




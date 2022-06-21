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
export QUEUE_NAME="pollens-queue-dev"
python pollinator/sqs_consumer.py --aws_endpoint http://localhost:4566 --aws_profile localstack
```
Or build an run the image:
```
docker build -t pollinator .
docker run -p 8000:5000 --env-file .env pollinator
```

# Debugging notes
- the easiest way to debug is to create a pollens input ipfs, then uncomment the last section in `pollinator/process_msg.py` and execute it. This can be used to debug all non sqs related logic. This should ideally be done on the GPU dev machine, because running the models requires a GPU.
- the ec2-instances are initialized with [this script](https://github.com/pollinations/infrastructure/blob/main/user_data.sh). If you update it and deploy the infrastructure stack, it will not effect running ec2-instances. Therefore, I usually login to the running instance and execute the changed command manually. **Note that `$QUEUE_NAME` should be replaced with `pollens-queue-prod` or `pollens-queue-dev` before copy & pasting user_data.sh into the command line of ec2.**
- Deployment works like this:
    - pollinator ci builds and pushes pollinator image to ECR
    - [`user_data.sh`](https://github.com/pollinations/infrastructure/blob/main/user_data.sh) has setup two cron jobs that pull for pollinator images and images referenced in the [model-index](https://github.com/pollinations/model-index) every 5 minutes. If pollinator was updated, it kills the running container and starts the new image.






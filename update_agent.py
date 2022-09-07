"""
This script is executed from the host machine and not the container.
It is responsible for keeping the instance in a healthy and updated state.
This involves:
- fetching the latest images referenced in model-index
- fetching the latest version of pollinator
- killing the container and restart the updated container as soon as an update is available and
    the running pollinator is not busy anymore
- run migrations: one-time bash scripts that change something about the host machine

Host environment assumptions:
- there is a ~/.env file with all secrets and environment variables
"""
import json
import logging
import os
from urllib.request import urlopen

import dotenv

dotenv.load_dotenv()


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


home_dir = os.environ["HOME"]
gpu_flag = "--gpus all" if os.system("nvidia-smi  > /dev/null 2>&1") == 0 else ""
dev_or_main = os.environ.get("POLLINATOR_ENV")
pollen_db = os.environ.get("POLLEN_DB")
pollinator_group = os.environ.get("POLLINATOR_GROUP")
pollinator_image = os.environ.get("POLLINATOR_IMAGE")

logging.info(f"Pollinator group: {pollinator_group}")
logging.info(f"Pollinator image: {pollinator_image}")


def log(msg):
    logging.info(msg)


def system(cmd):
    log("-" * 80)
    log(cmd)
    result = os.popen(cmd).read()
    log(result)
    log("-" * 80)
    return result


def sudo(cmd):
    return system(f"sudo {cmd}")


def load_web_json(url):
    response = urlopen(url)
    return json.loads(response.read())


def pull(image):
    pull_cmd = """
    aws ecr get-login-password \
        --region us-east-1 \
    | docker login \
        --username AWS \
        --password-stdin 614871946825.dkr.ecr.us-east-1.amazonaws.com
    docker pull {}
    """.format(
        image
    )
    response = system(pull_cmd)
    is_updated = "Status: Downloaded newer image for" in response
    return is_updated


def fetch_images():
    log("Fetching images")
    images = load_web_json(
        "https://raw.githubusercontent.com/pollinations/model-index/main/images.json"
    )
    metadata = load_web_json(
        "https://raw.githubusercontent.com/pollinations/model-index/main/metadata.json"
    )

    for _, image in images.items():
        try:
            assert (
                pollinator_group
                in metadata[image.split("@")[0]]["meta"]["pollinator_group"]
            )
        except (AssertionError, KeyError):
            log(f"# Ignore {image}")
            continue
        pull(image)
        if "@" in image:
            system(f"docker tag {image} {image.split('@')[0]}")


def fetch_pollinator():
    log("Fetching pollinator")
    needs_restart = pull(pollinator_image)
    return needs_restart


def start_pollinator_if_not_running():
    pollinator_cmd = f"""docker run {gpu_flag} --rm \\
        --network host \\
        --name pollinator \\
        --env-file {home_dir}/.env \\
        -v /var/run/docker.sock:/var/run/docker.sock \\
        -v "$HOME/.aws/:/root/.aws/" \\
        --mount type=bind,source=/tmp/ipfs,target=/tmp/ipfs \\
        {pollinator_image} > /tmp/pollinator.log 2>&1 &"""
    system(pollinator_cmd)


def main():
    fetch_pollinator()
    start_pollinator_if_not_running()
    fetch_images()
    system("docker system prune -f")


if __name__ == "__main__":
    main()

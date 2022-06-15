from constants import images

for _, image in images.items():
    print(f"docker pull {image}")

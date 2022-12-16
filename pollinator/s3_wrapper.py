import base64
import hashlib
import json

import boto3


def lookup(data, keys):
    keys = [] if keys is None else keys.split("/")
    for key in keys:
        if isinstance(data, list):
            key = int(key)
        data = data[key]
    return data


def is_base64(data):
    if not isinstance(data, str):
        return False
    if data.startswith("base64:"):
        return True
    if data.startswith("data:"):
        try:
            return data.split(";")[1].startswith("base64")
        except IndexError:
            return False
    return False


def split_base64(data):
    """Example: data="'data:video/mp4;base64,AAAAIGZ0eXBpc29tAAAC..." """
    if data.startswith("data:"):
        extension = data.split(";")[0].split(":")[1].split("/")[1]
        content = data.split(",")[1]
    elif data.startswith("base64:"):
        extension = None
        content = data.split("base64,")[1]
    else:
        extension = None
        content = data
    return extension, content


class S3Wrapper:
    def __init__(self, bucket_name):
        self.s3 = boto3.client("s3")
        self.bucket_name = bucket_name

    def _get_object_key(self, data, extension=None):
        if isinstance(data, bytes):
            data_hash = hashlib.sha256(data).hexdigest()
        else:
            data_str = json.dumps(data, sort_keys=True)
            data_hash = hashlib.sha256(data_str.encode("utf-8")).hexdigest()
        if extension:
            data_hash += f".{extension}"
        return data_hash

    def _replace_base64(self, data):
        if isinstance(data, dict):
            for key, value in data.items():
                data[key] = self._replace_base64(value)
        elif isinstance(data, list):
            for i, value in enumerate(data):
                data[i] = self._replace_base64(value)
        elif is_base64(data):
            extension, content = split_base64(data)
            decoded_data = base64.b64decode(content)
            object_key = self._get_object_key(decoded_data, extension=extension)
            self.s3.put_object(
                Bucket=self.bucket_name, Key=object_key, Body=decoded_data
            )
            return f"s3:{object_key}"
        return data

    def put(self, data):
        """Put data in S3 and return the hash as object key"""
        # Recursively check for base64 encoded data. Every base64 encoded
        # data should be stored in S3 and the key should be replaced with
        # s3:<key>
        data = self._replace_base64(data)
        object_key = self._get_object_key(data)
        try:
            self.s3.head_object(Bucket=self.bucket_name, Key=object_key)
            return f"s3:{object_key}"
        except self.s3.exceptions.ClientError:
            pass
        self.s3.put_object(
            Bucket=self.bucket_name, Key=object_key, Body=json.dumps(data)
        )
        return f"s3:{object_key}"

    def _replace_s3(self, data):
        if isinstance(data, dict):
            for key, value in data.items():
                data[key] = self._replace_s3(value)
            return data
        elif isinstance(data, list):
            for i, value in enumerate(data):
                data[i] = self._replace_s3(value)
            return data
        elif isinstance(data, str) and data.startswith("s3:"):
            object_key = data[3:]
            expires_in = 3600  # 1 hour
            # Generate the presigned URL
            url = self.s3.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": self.bucket_name, "Key": object_key},
                ExpiresIn=expires_in,
            )
            return url
        else:
            return data

    def get(self, object_key, key=None):
        """Get data from S3. If key is provided, return the value at the key"""
        if object_key.startswith("s3:"):
            object_key = object_key[3:]
        response = self.s3.get_object(Bucket=self.bucket_name, Key=object_key)
        data = json.loads(response["Body"].read())
        data = self._replace_s3(data)
        return lookup(data, key)


s3store = S3Wrapper("pollinations-user-data")

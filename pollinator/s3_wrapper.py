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


class S3Wrapper:
    def __init__(self, bucket_name):
        self.s3 = boto3.client("s3")
        self.bucket_name = bucket_name

    def _get_object_key(self, data):
        data_str = json.dumps(data, sort_keys=True)
        data_hash = hashlib.sha256(data_str.encode("utf-8")).hexdigest()
        return data_hash

    def put(self, data):
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

    def get(self, object_key, key=None):
        if object_key.startswith("s3:"):
            object_key = object_key[3:]
        response = self.s3.get_object(Bucket=self.bucket_name, Key=object_key)
        data = json.loads(response["Body"].read())
        return lookup(data, key)


s3store = S3Wrapper("pollinations-user-data")
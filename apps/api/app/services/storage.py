"""Document storage abstraction.

Local-folder backend for dev (no dependencies); S3/MinIO backend for production.
The interface returns a storage key that is stored on the Document row.
"""

from __future__ import annotations

import os
import uuid

from ..core.config import get_settings

settings = get_settings()


class LocalStorage:
    backend = "local"

    def __init__(self, root: str) -> None:
        self._root = os.path.abspath(root)
        os.makedirs(self._root, exist_ok=True)

    def save(self, filename: str, data: bytes) -> str:
        key = f"{uuid.uuid4().hex}_{os.path.basename(filename)}"
        with open(os.path.join(self._root, key), "wb") as fh:
            fh.write(data)
        return key

    def read(self, key: str) -> bytes:
        with open(os.path.join(self._root, key), "rb") as fh:
            return fh.read()

    def delete(self, key: str) -> None:
        path = os.path.join(self._root, key)
        if os.path.exists(path):
            os.remove(path)


class S3Storage:
    backend = "s3"

    def __init__(self) -> None:
        import boto3  # lazy import

        self._bucket = settings.local_storage_dir  # overridden below
        s = settings
        self._client = boto3.client(
            "s3",
            endpoint_url=os.getenv("S3_ENDPOINT_URL"),
            aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
            aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
            region_name=os.getenv("S3_REGION", "us-east-1"),
        )
        self._bucket = os.getenv("S3_BUCKET", "vat-documents")

    def save(self, filename: str, data: bytes) -> str:
        key = f"{uuid.uuid4().hex}_{os.path.basename(filename)}"
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)
        return key

    def read(self, key: str) -> bytes:
        obj = self._client.get_object(Bucket=self._bucket, Key=key)
        return obj["Body"].read()

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)


def get_storage():
    if settings.storage_backend == "s3":
        return S3Storage()
    return LocalStorage(settings.local_storage_dir)

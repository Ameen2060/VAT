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


class VercelBlobStorage:
    """Persistent object storage on Vercel Blob (serverless has no writable disk).

    Uses the documented Blob REST API over stdlib urllib — no extra dependency and no
    SDK. The returned public URL (with an unguessable random suffix) is stored as the
    key; files are only ever streamed back to users through authenticated API routes,
    so the URL itself is never exposed in the UI.
    """

    backend = "blob"
    _API = "https://blob.vercel-storage.com"
    _API_VERSION = "7"

    def __init__(self) -> None:
        self._token = os.getenv("BLOB_READ_WRITE_TOKEN", "")
        if not self._token:
            raise RuntimeError("BLOB_READ_WRITE_TOKEN is not set (Vercel Blob store not connected).")

    @staticmethod
    def _safe(name: str) -> str:
        base = os.path.basename(name) or "file"
        return "".join(c if (c.isalnum() or c in "._-") else "_" for c in base)[:120]

    def save(self, filename: str, data: bytes) -> str:
        import json
        import urllib.request

        pathname = f"{uuid.uuid4().hex}_{self._safe(filename)}"
        req = urllib.request.Request(
            f"{self._API}/{pathname}",
            data=data,
            method="PUT",
            headers={
                "authorization": f"Bearer {self._token}",
                "x-api-version": self._API_VERSION,
                "x-add-random-suffix": "1",
                "content-type": "application/octet-stream",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        url = payload.get("url")
        if not url:
            raise RuntimeError("Vercel Blob upload returned no URL.")
        return url

    def read(self, key: str) -> bytes:
        import urllib.request

        # Tolerate keys written by the DB backend before Blob was connected.
        if key.startswith("db:"):
            return DbStorage().read(key)
        # Keys are full blob URLs; fetch directly.
        with urllib.request.urlopen(key, timeout=30) as resp:
            return resp.read()

    def delete(self, key: str) -> None:
        import json
        import urllib.request

        body = json.dumps({"urls": [key]}).encode("utf-8")
        req = urllib.request.Request(
            f"{self._API}/delete",
            data=body,
            method="POST",
            headers={
                "authorization": f"Bearer {self._token}",
                "x-api-version": self._API_VERSION,
                "content-type": "application/json",
            },
        )
        try:
            urllib.request.urlopen(req, timeout=30).read()
        except Exception:  # noqa: BLE001 — a failed delete must not break the request
            pass


class DbStorage:
    """Persist blobs in the database (StoredBlob table). Zero extra infrastructure:
    works anywhere the app's database works, including serverless hosts with no disk.
    Suitable for documents/reports of typical size; for very large files or high
    volume, attach Vercel Blob / S3 instead."""

    backend = "db"

    def save(self, filename: str, data: bytes) -> str:
        from ..models import StoredBlob
        from ..core.database import SessionLocal

        key = f"db:{uuid.uuid4().hex}"
        with SessionLocal() as db:
            db.add(StoredBlob(key=key, filename=os.path.basename(filename or "file"), content=data))
            db.commit()
        return key

    def read(self, key: str) -> bytes:
        # Tolerate keys written by the Blob backend (public URLs) if the store changed.
        if key.startswith(("http://", "https://")):
            import urllib.request

            with urllib.request.urlopen(key, timeout=30) as resp:
                return resp.read()

        from ..models import StoredBlob
        from ..core.database import SessionLocal

        with SessionLocal() as db:
            row = db.get(StoredBlob, key)
            if row is None:
                raise FileNotFoundError(key)
            return row.content

    def delete(self, key: str) -> None:
        from ..models import StoredBlob
        from ..core.database import SessionLocal

        with SessionLocal() as db:
            row = db.get(StoredBlob, key)
            if row is not None:
                db.delete(row)
                db.commit()


def get_storage():
    """Choose a storage backend. Order of preference:
    - Vercel Blob when a token is configured (best for large files / scale);
    - the database (StoredBlob) as a persistent fallback that needs no extra store —
      so attaching just Postgres is enough for uploads to work and persist;
    - S3 when explicitly selected;
    - the local disk for local development.
    """
    backend = settings.storage_backend
    if backend == "blob":
        if os.getenv("BLOB_READ_WRITE_TOKEN"):
            return VercelBlobStorage()
        # Blob selected but not connected yet — fall back to durable DB storage
        # instead of failing, so uploads persist as long as the database is attached.
        return DbStorage()
    if backend == "db":
        return DbStorage()
    if backend == "s3":
        return S3Storage()
    return LocalStorage(settings.local_storage_dir)

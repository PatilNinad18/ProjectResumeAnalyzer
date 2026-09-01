"""
Storage backends for raw JD text and generated artifacts (JSON/Markdown).

Two backends implement the same small interface (put_text/get_text/
presigned_get_url/checksum/build_key):

  - LocalStorage: writes to a local folder on disk. Zero setup, no AWS
    account, no credentials -- this is the default so the project runs
    immediately after `pip install` + an LLM API key.
  - S3Storage: private S3 storage for production. Objects are stored
    privately (no public ACLs); downloads are served either by proxying
    through the API (with auth) or via short-lived pre-signed URLs.

Pick the backend via STORAGE_BACKEND=local|s3 in your .env (see config.py).
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional

from app.config import get_settings

settings = get_settings()

_ARTIFACT_EXT = {"raw": "txt", "markdown": "md", "json": "json"}


def build_key(project_id: str, jd_id: str, version: int, artifact: str) -> str:
    # artifact in {"raw", "markdown", "json"}
    ext = _ARTIFACT_EXT[artifact]
    return f"projects/{project_id}/jds/{jd_id}/v{version}/{artifact}.{ext}"


def checksum(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class LocalStorage:
    """
    Filesystem-backed storage for local development and testing. Stores
    each object as a plain file under `local_storage_path`, mirroring the
    same "key" layout used by S3Storage so the two are drop-in compatible.
    """

    def __init__(self, base_path: Optional[str] = None):
        self.base_path = Path(base_path or settings.local_storage_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        # Keys are always relative, forward-slash paths (e.g.
        # "projects/x/jds/y/v1/raw.txt") -- safe to join directly.
        path = self.base_path / key
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def put_text(self, key: str, content: str, content_type: str = "text/plain") -> str:
        path = self._resolve(key)
        path.write_text(content, encoding="utf-8")
        return key

    def get_text(self, key: str) -> str:
        path = self._resolve(key)
        if not path.exists():
            raise FileNotFoundError(f"No such object: {key}")
        return path.read_text(encoding="utf-8")

    def presigned_get_url(self, key: str, expires_in: int = 300) -> str:
        # No real "URL" for local files; return a file:// reference so
        # callers that just display/log it still get something sensible.
        return self._resolve(key).resolve().as_uri()

    @staticmethod
    def checksum(content: str) -> str:
        return checksum(content)

    @staticmethod
    def build_key(project_id: str, jd_id: str, version: int, artifact: str) -> str:
        return build_key(project_id, jd_id, version, artifact)


class S3Storage:
    def __init__(self, bucket: Optional[str] = None):
        self.bucket = bucket or settings.s3_bucket
        self._client = None  # lazy boto3 client

    def _get_client(self):
        if self._client is None:
            import boto3  # local import so boto3 is optional for pure unit tests

            self._client = boto3.client("s3", region_name=settings.aws_region)
        return self._client

    def put_text(self, key: str, content: str, content_type: str = "text/plain") -> str:
        client = self._get_client()
        client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content.encode("utf-8"),
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )
        return key

    def get_text(self, key: str) -> str:
        client = self._get_client()
        obj = client.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"].read().decode("utf-8")

    def presigned_get_url(self, key: str, expires_in: int = 300) -> str:
        client = self._get_client()
        return client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires_in
        )

    @staticmethod
    def checksum(content: str) -> str:
        return checksum(content)

    @staticmethod
    def build_key(project_id: str, jd_id: str, version: int, artifact: str) -> str:
        return build_key(project_id, jd_id, version, artifact)


def get_storage():
    """Factory: returns the configured storage backend (default: local)."""
    backend = os.environ.get("STORAGE_BACKEND", settings.storage_backend)
    if backend == "s3":
        return S3Storage()
    return LocalStorage()

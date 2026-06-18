"""
Pluggable media storage for user uploads (asset images, grading scans).

Today uploads are written to local disk and served by FastAPI ``StaticFiles``
(`app/main.py`). That's fine for a single box but fatal for the multi-node pool
fleet (one node's disk isn't another's). This module abstracts the write/read/
delete/serve of upload objects so the same handlers work against local disk
(OSS / self-host / dev) or an S3-compatible bucket (S3 / Cloudflare R2) for the
hosted pool — selected by ``STORAGE_BACKEND`` (``local`` default, or ``s3``).

Design that keeps the cutover non-invasive:
  - Objects are addressed by a backend-independent **key** like ``assets/42.jpg``
    or ``grading/7.jpg`` (the existing ``{integer_id}.{ext}`` naming → no
    user-controlled paths, no traversal).
  - The DB keeps storing the **relative** ``/uploads/<key>`` path regardless of
    backend (so models, API responses and the frontend are untouched). Only the
    serving layer differs: local → ``StaticFiles`` from disk; remote → a route
    that redirects ``/uploads/<key>`` to ``storage.url(key)`` (CDN / public bucket
    URL, or a presigned URL).

Env (s3 mode): ``S3_BUCKET`` (required), ``S3_ENDPOINT_URL`` (set for R2),
``S3_REGION``, ``S3_KEY_PREFIX``, ``S3_PUBLIC_BASE_URL`` (CDN/public base; if
unset, presigned GET URLs are used). AWS creds come from boto3's default chain.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

# URL path prefix the app serves media under (matches the historical /uploads mount).
PUBLIC_PREFIX = "/uploads"

# boto3's "not found" / API error type, when botocore is installed; falls back to
# Exception so this module imports (and the S3 unit tests run) without botocore.
try:  # pragma: no cover - import shim
    from botocore.exceptions import ClientError as _S3Error
except Exception:  # pragma: no cover
    _S3Error = Exception


class Storage(ABC):
    """Backend-independent object store for uploads."""

    # True when serving requires redirecting to an external URL (remote bucket).
    remote: bool = False

    @abstractmethod
    def save(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None: ...

    @abstractmethod
    def read(self, key: str) -> Optional[bytes]: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def url(self, key: str) -> str:
        """Absolute URL that serves ``key`` (used by the redirect route in remote mode)."""

    def public_path(self, key: str) -> str:
        """The ``/uploads``-relative path stored in the DB (backend-independent)."""
        return f"{PUBLIC_PREFIX}/{key.lstrip('/')}"

    @staticmethod
    def key_from_public_path(path: str) -> str:
        """Inverse of ``public_path`` — strip a leading ``/uploads/`` to get the key."""
        p = path.lstrip("/")
        prefix = PUBLIC_PREFIX.lstrip("/") + "/"  # "uploads/"
        return p[len(prefix):] if p.startswith(prefix) else p


class LocalStorage(Storage):
    """Disk-backed store rooted at ``base_dir`` (served by StaticFiles)."""

    remote = False

    def __init__(self, base_dir: str | os.PathLike):
        self.base = Path(base_dir)

    def _path(self, key: str) -> Path:
        return self.base / key.lstrip("/")

    def save(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def read(self, key: str) -> Optional[bytes]:
        p = self._path(key)
        return p.read_bytes() if p.exists() else None

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def url(self, key: str) -> str:
        return self.public_path(key)


class S3Storage(Storage):
    """S3 / R2-backed store. boto3 is imported lazily so the core stays importable."""

    remote = True

    def __init__(
        self,
        bucket: str,
        *,
        key_prefix: str = "",
        endpoint_url: Optional[str] = None,
        region: Optional[str] = None,
        public_base_url: Optional[str] = None,
        signed_ttl: int = 3600,
    ):
        import boto3  # lazy — only when s3 mode is actually selected

        self.bucket = bucket
        self.key_prefix = key_prefix.strip("/")
        self.public_base_url = (public_base_url or "").rstrip("/")
        self.signed_ttl = signed_ttl
        self._client = boto3.client(
            "s3", endpoint_url=endpoint_url or None, region_name=region or None
        )

    def _full(self, key: str) -> str:
        k = key.lstrip("/")
        return f"{self.key_prefix}/{k}" if self.key_prefix else k

    def save(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self._client.put_object(
            Bucket=self.bucket, Key=self._full(key), Body=data, ContentType=content_type
        )

    def read(self, key: str) -> Optional[bytes]:
        try:
            obj = self._client.get_object(Bucket=self.bucket, Key=self._full(key))
            return obj["Body"].read()
        except _S3Error:
            return None

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=self._full(key))

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=self._full(key))
            return True
        except _S3Error:
            return False

    def url(self, key: str) -> str:
        full = self._full(key)
        if self.public_base_url:
            return f"{self.public_base_url}/{full}"
        return self._client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": full}, ExpiresIn=self.signed_ttl
        )


def build_storage() -> Storage:
    """Construct the storage backend from the environment (no caching)."""
    backend = os.getenv("STORAGE_BACKEND", "local").strip().lower()
    if backend in ("s3", "r2"):
        bucket = os.getenv("S3_BUCKET", "").strip()
        if not bucket:
            raise RuntimeError("STORAGE_BACKEND=s3 requires S3_BUCKET")
        return S3Storage(
            bucket,
            key_prefix=os.getenv("S3_KEY_PREFIX", ""),
            endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
            region=os.getenv("S3_REGION") or None,
            public_base_url=os.getenv("S3_PUBLIC_BASE_URL") or None,
        )
    base = os.getenv("UPLOADS_PATH") or "/app/uploads"
    return LocalStorage(base)


_storage: Optional[Storage] = None


def get_storage() -> Storage:
    """Process-wide storage singleton (built once from env on first use)."""
    global _storage
    if _storage is None:
        _storage = build_storage()
    return _storage

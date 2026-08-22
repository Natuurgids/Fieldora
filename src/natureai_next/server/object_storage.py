"""Replaceable object storage for governed server payloads."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ObjectStore(Protocol):
    def put(self, key: str, source: Path, mime_type: str, sha256: str) -> None: ...

    def read_range(self, key: str, start: int, end: int) -> bytes: ...

    def delete(self, key: str) -> None: ...


class FileObjectStore:
    """Contained filesystem adapter used by standalone and one-node installs."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("object key escapes storage root") from exc
        return candidate

    def put(self, key: str, source: Path, mime_type: str, sha256: str) -> None:
        destination = self.path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as reader, destination.open("xb") as writer:
            for block in iter(lambda: reader.read(1024 * 1024), b""):
                writer.write(block)

    def read_range(self, key: str, start: int, end: int) -> bytes:
        with self.path(key).open("rb") as stream:
            stream.seek(start)
            return stream.read(end - start + 1)

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)


class S3CompatibleClient(Protocol):
    """Minimal client surface supported by boto3 and compatible SDK facades."""

    def put_object(self, **kwargs: object) -> object: ...

    def get_object(self, **kwargs: object) -> dict[str, object]: ...

    def delete_object(self, **kwargs: object) -> object: ...

    def head_bucket(self, **kwargs: object) -> object: ...


class S3ObjectStore:
    """S3-compatible adapter without exposing object URLs to application code."""

    def __init__(
        self, client: S3CompatibleClient, bucket: str, prefix: str = "fieldora/media"
    ) -> None:
        if not bucket.strip():
            raise ValueError("S3 bucket is required")
        self._client = client
        self._bucket = bucket.strip()
        self._prefix = prefix.strip("/")

    def _key(self, key: str) -> str:
        normalized = key.replace("\\", "/").strip("/")
        if not normalized or any(part in ("", ".", "..") for part in normalized.split("/")):
            raise ValueError("invalid object key")
        return f"{self._prefix}/{normalized}" if self._prefix else normalized

    def put(self, key: str, source: Path, mime_type: str, sha256: str) -> None:
        with source.open("rb") as body:
            self._client.put_object(
                Bucket=self._bucket,
                Key=self._key(key),
                Body=body,
                ContentType=mime_type,
                Metadata={"sha256": sha256},
            )

    def read_range(self, key: str, start: int, end: int) -> bytes:
        response = self._client.get_object(
            Bucket=self._bucket, Key=self._key(key), Range=f"bytes={start}-{end}"
        )
        body = response.get("Body")
        if body is None or not hasattr(body, "read"):
            raise OSError("S3 response has no readable body")
        try:
            payload = body.read()
        finally:
            close = getattr(body, "close", None)
            if close is not None:
                close()
        if not isinstance(payload, bytes) or len(payload) != end - start + 1:
            raise OSError("S3 range response length mismatch")
        return payload

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=self._key(key))

    def ready(self) -> bool:
        self._client.head_bucket(Bucket=self._bucket)
        return True

"""Restart-safe ranged media download coordination."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Protocol

from natureai_next.domain.synchronization import MediaTransfer
from natureai_next.ports.synchronization import DesktopSynchronizationRepository


class RangeMediaTransport(Protocol):
    def read_range(
        self, *, media_id: str, offset: int, length: int, etag: str
    ) -> tuple[bytes, str]: ...


class ResumableMediaDownloadService:
    def __init__(
        self, repository: DesktopSynchronizationRepository, transport: RangeMediaTransport
    ) -> None:
        self._repository = repository
        self._transport = transport

    def run_chunk(self, transfer_id: str, *, chunk_size: int = 1024 * 1024) -> MediaTransfer:
        transfer = self._repository.media_transfer(transfer_id)
        if transfer is None:
            raise KeyError(transfer_id)
        if transfer.state == "complete":
            return transfer
        target = Path(transfer.destination_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        current_size = target.stat().st_size if target.exists() else 0
        if current_size > transfer.offset:
            with target.open("r+b") as stream:
                stream.truncate(transfer.offset)
        elif current_size < transfer.offset:
            raise ValueError("media checkpoint is ahead of local bytes")
        data, response_etag = self._transport.read_range(
            media_id=transfer.media_id, offset=transfer.offset,
            length=min(chunk_size, transfer.expected_size - transfer.offset),
            etag=transfer.etag,
        )
        if response_etag != transfer.etag:
            raise ValueError("media changed during transfer")
        if not data and transfer.offset < transfer.expected_size:
            raise ValueError("media range response ended early")
        with target.open("ab") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        offset = transfer.offset + len(data)
        if offset > transfer.expected_size:
            raise ValueError("media range exceeded expected size")
        state = "transferring"
        if offset == transfer.expected_size:
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            if digest != transfer.expected_sha256:
                raise ValueError("completed media checksum mismatch")
            state = "complete"
        updated = MediaTransfer(
            transfer.transfer_id, transfer.enrollment_id, transfer.media_id,
            transfer.destination_path, transfer.expected_size, transfer.expected_sha256,
            transfer.etag, offset, state,
        )
        self._repository.put_media_transfer(updated)
        return updated


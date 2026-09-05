"""Bounded original-byte range servicing for the linked-storage agent."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from natureai_next.server.linked_storage import _contained
from natureai_next.server.storage_service_agent import (
    LinkedStorageAgent,
    MutualTLSStorageExchangeClient,
    StorageAgentConfig,
)

_MAX_RANGE_BYTES = 4 * 1024 * 1024


class MutualTLSStorageRangeExchangeClient(MutualTLSStorageExchangeClient):
    """Extend the fixed-path mTLS client with bounded original-range operations."""

    _ALLOWED_PATHS = MutualTLSStorageExchangeClient._ALLOWED_PATHS | frozenset(
        {
            "/internal/v1/storage/ranges/claim",
            "/internal/v1/storage/ranges/upload",
        }
    )

    def claim_ranges(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post("/internal/v1/storage/ranges/claim", payload)

    def upload_range(
        self,
        payload: bytes,
        *,
        service_id: str,
        organization_id: str,
        storage_id: str,
        worker_id: str,
        media_id: str,
        request_id: str,
        start_byte: int,
        end_byte: int,
        sha256: str,
    ) -> dict[str, Any]:
        start = int(start_byte)
        end = int(end_byte)
        if start < 0 or end < start or end - start + 1 > _MAX_RANGE_BYTES:
            raise ValueError("linked range upload is invalid")
        if len(payload) != end - start + 1:
            raise ValueError("linked range upload length mismatch")
        return self._request(
            "PUT",
            "/internal/v1/storage/ranges/upload",
            payload,
            {
                "Content-Type": "application/octet-stream",
                "Accept": "application/json",
                "Fieldora-Service-Id": self._header_value(service_id),
                "Fieldora-Organization-Id": self._header_value(organization_id),
                "Fieldora-Storage-Id": self._header_value(storage_id),
                "Fieldora-Worker-Id": self._header_value(worker_id),
                "Fieldora-Media-Id": self._header_value(media_id),
                "Fieldora-Range-Request-Id": self._header_value(request_id),
                "Fieldora-Range-Start": str(start),
                "Fieldora-Range-End": str(end),
                "Fieldora-Range-Sha256": self._header_value(sha256.casefold()),
            },
        )


class LinkedStorageRangeAgent(LinkedStorageAgent):
    """Storage agent with outbound servicing for browser-authorized range requests."""

    def __init__(
        self,
        config: StorageAgentConfig,
        exchange: MutualTLSStorageRangeExchangeClient | Any | None = None,
    ) -> None:
        if exchange is None:
            exchange = MutualTLSStorageRangeExchangeClient(
                config.endpoint,
                config.certificate,
                config.private_key,
                config.ca_certificate,
            )
        super().__init__(config, exchange)

    def process_range_leases(
        self,
        *,
        worker_id: str,
        limit: int = 8,
        lease_seconds: int = 120,
    ) -> int:
        exchange = self.exchange
        claim = getattr(exchange, "claim_ranges", None)
        upload = getattr(exchange, "upload_range", None)
        if claim is None or upload is None:
            raise RuntimeError("storage exchange does not support original-range transfers")
        response = claim(
            {
                "service_id": self.config.service_id,
                "organization_id": self.config.organization_id,
                "storage_id": self.config.storage_id,
                "worker_id": worker_id,
                "limit": max(1, min(int(limit), 32)),
                "lease_seconds": max(30, min(int(lease_seconds), 300)),
            }
        )
        leases = response.get("items", [])
        if not isinstance(leases, list):
            raise RuntimeError("range claim response is invalid")
        processed = 0
        root = self.config.root_path.resolve(strict=True)
        for lease in leases:
            if not isinstance(lease, dict):
                continue
            request_id = str(lease.get("request_id", "")).strip()
            media_id = str(lease.get("media_id", "")).strip()
            object_id = str(lease.get("object_id", "")).strip()
            try:
                start = int(lease["start_byte"])
                end = int(lease["end_byte"])
                total_size = int(lease["total_size"])
            except (KeyError, TypeError, ValueError):
                continue
            if (
                not request_id
                or not media_id
                or not object_id
                or start < 0
                or end < start
                or end - start + 1 > _MAX_RANGE_BYTES
            ):
                continue
            local = self.repository.media(object_id)
            if local is None:
                continue
            original = _contained(root, local.relative_path)
            stat = original.stat()
            if int(stat.st_size) != total_size or end >= int(stat.st_size):
                continue
            payload = _read_range(original, start, end)
            digest = hashlib.sha256(payload).hexdigest()
            upload(
                payload,
                service_id=self.config.service_id,
                organization_id=self.config.organization_id,
                storage_id=self.config.storage_id,
                worker_id=worker_id,
                media_id=media_id,
                request_id=request_id,
                start_byte=start,
                end_byte=end,
                sha256=digest,
            )
            processed += 1
        return processed


def _read_range(path: Path, start_byte: int, end_byte: int) -> bytes:
    length = end_byte - start_byte + 1
    if length < 1 or length > _MAX_RANGE_BYTES:
        raise ValueError("linked original range length is invalid")
    with path.open("rb") as stream:
        stream.seek(start_byte)
        payload = stream.read(length)
    if len(payload) != length:
        raise OSError("linked original changed during range read")
    return payload

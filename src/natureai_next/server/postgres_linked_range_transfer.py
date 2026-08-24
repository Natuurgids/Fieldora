"""Short-lived, lease-bound byte-range transfer for linked original media.

Original files remain on the organisation-controlled storage node. Browser/API callers
request a bounded range; an outbound-only storage worker claims the request and uploads
exactly that slice over mTLS. Range payloads are temporary and expire automatically.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from natureai_next.server.storage_exchange import StorageObjectState

_MAX_RANGE_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class LinkedRangeLease:
    request_id: str
    media_id: str
    storage_id: str
    object_id: str
    organization_id: str
    start_byte: int
    end_byte: int
    total_size: int
    mime_type: str
    worker_id: str


@dataclass(frozen=True, slots=True)
class LinkedRangeResult:
    request_id: str
    media_id: str
    organization_id: str
    requested_by: str
    start_byte: int
    end_byte: int
    total_size: int
    mime_type: str
    state: str
    sha256: str
    payload: bytes
    expires_at_epoch: int


class PostgresLinkedRangeTransfers:
    """Shared temporary range queue for outbound-only linked-storage services."""

    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    ("fieldora_linked_range_transfer_schema_v1",),
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS linked_range_requests_pg(
                        request_id TEXT PRIMARY KEY,
                        media_id TEXT NOT NULL
                            REFERENCES linked_storage_media_pg(media_id) ON DELETE CASCADE,
                        storage_id TEXT NOT NULL,
                        organization_id TEXT NOT NULL,
                        requested_by TEXT NOT NULL,
                        start_byte BIGINT NOT NULL CHECK(start_byte >= 0),
                        end_byte BIGINT NOT NULL CHECK(end_byte >= start_byte),
                        total_size BIGINT NOT NULL CHECK(total_size > 0),
                        mime_type TEXT NOT NULL,
                        state TEXT NOT NULL,
                        requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        expires_at TIMESTAMPTZ NOT NULL,
                        claimed_by TEXT NOT NULL DEFAULT '',
                        lease_until TIMESTAMPTZ,
                        sha256 TEXT NOT NULL DEFAULT '',
                        payload BYTEA
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_linked_range_claim_pg "
                    "ON linked_range_requests_pg(storage_id,state,requested_at,request_id)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_linked_range_requester_pg "
                    "ON linked_range_requests_pg(organization_id,requested_by,request_id)"
                )

    def request_range(
        self,
        *,
        media_id: str,
        organization_id: str,
        requested_by: str,
        start_byte: int,
        end_byte: int,
        ttl_seconds: int = 300,
    ) -> str:
        media_id = media_id.strip()
        organization_id = organization_id.strip()
        requested_by = requested_by.strip()
        start = int(start_byte)
        end = int(end_byte)
        ttl = max(30, min(int(ttl_seconds), 900))
        if not all((media_id, organization_id, requested_by)):
            raise ValueError("linked range request identity is required")
        if start < 0 or end < start or end - start + 1 > _MAX_RANGE_BYTES:
            raise ValueError("linked range request is invalid")

        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._delete_expired(cursor)
                cursor.execute(
                    "SELECT m.storage_id,m.size_bytes,m.mime_type,m.object_state "
                    "FROM linked_storage_media_pg m "
                    "JOIN linked_storage_sources_pg s ON s.storage_id=m.storage_id "
                    "WHERE m.media_id=%s AND m.organization_id=%s AND s.enabled=TRUE",
                    (media_id, organization_id),
                )
                media = cursor.fetchone()
                if media is None:
                    raise KeyError(media_id)
                total_size = int(media[1])
                if str(media[3]) != StorageObjectState.AVAILABLE.value:
                    raise ValueError("linked original is not available")
                if end >= total_size:
                    raise ValueError("linked range exceeds original size")

                cursor.execute(
                    "SELECT request_id FROM linked_range_requests_pg "
                    "WHERE media_id=%s AND organization_id=%s AND requested_by=%s "
                    "AND start_byte=%s AND end_byte=%s AND expires_at>NOW() "
                    "ORDER BY requested_at DESC LIMIT 1",
                    (media_id, organization_id, requested_by, start, end),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    return str(existing[0])

                request_id = str(uuid4())
                cursor.execute(
                    "INSERT INTO linked_range_requests_pg("
                    "request_id,media_id,storage_id,organization_id,requested_by,"
                    "start_byte,end_byte,total_size,mime_type,state,expires_at"
                    ") VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',"
                    "NOW()+(%s*INTERVAL '1 second'))",
                    (
                        request_id,
                        media_id,
                        str(media[0]),
                        organization_id,
                        requested_by,
                        start,
                        end,
                        total_size,
                        str(media[2]),
                        ttl,
                    ),
                )
        return request_id

    def claim(
        self,
        *,
        storage_id: str,
        service_id: str,
        worker_id: str,
        limit: int = 8,
        lease_seconds: int = 120,
    ) -> tuple[LinkedRangeLease, ...]:
        storage_id = storage_id.strip()
        service_id = service_id.strip()
        worker_id = worker_id.strip()
        if not all((storage_id, service_id, worker_id)):
            raise ValueError("linked range claim identity is required")
        bounded_limit = max(1, min(int(limit), 32))
        bounded_lease = max(30, min(int(lease_seconds), 300))
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_source_service(cursor, storage_id, service_id)
                self._delete_expired(cursor)
                cursor.execute(
                    "SELECT r.request_id,r.media_id,r.storage_id,m.object_id,"
                    "r.organization_id,r.start_byte,r.end_byte,r.total_size,r.mime_type "
                    "FROM linked_range_requests_pg r "
                    "JOIN linked_storage_media_pg m ON m.media_id=r.media_id "
                    "WHERE r.storage_id=%s AND r.expires_at>NOW() "
                    "AND (r.state='pending' OR (r.state='claimed' AND r.lease_until<=NOW())) "
                    "ORDER BY r.requested_at,r.request_id "
                    "FOR UPDATE OF r SKIP LOCKED LIMIT %s",
                    (storage_id, bounded_limit),
                )
                rows = cursor.fetchall()
                leases: list[LinkedRangeLease] = []
                for row in rows:
                    request_id = str(row[0])
                    cursor.execute(
                        "UPDATE linked_range_requests_pg SET state='claimed',claimed_by=%s,"
                        "lease_until=NOW()+(%s*INTERVAL '1 second') WHERE request_id=%s",
                        (worker_id, bounded_lease, request_id),
                    )
                    leases.append(
                        LinkedRangeLease(
                            request_id=request_id,
                            media_id=str(row[1]),
                            storage_id=str(row[2]),
                            object_id=str(row[3]),
                            organization_id=str(row[4]),
                            start_byte=int(row[5]),
                            end_byte=int(row[6]),
                            total_size=int(row[7]),
                            mime_type=str(row[8]),
                            worker_id=worker_id,
                        )
                    )
        return tuple(leases)

    def put_leased_range(
        self,
        *,
        request_id: str,
        media_id: str,
        storage_id: str,
        organization_id: str,
        service_id: str,
        worker_id: str,
        start_byte: int,
        end_byte: int,
        sha256: str,
        payload: bytes,
    ) -> LinkedRangeResult:
        request_id = request_id.strip()
        media_id = media_id.strip()
        storage_id = storage_id.strip()
        organization_id = organization_id.strip()
        service_id = service_id.strip()
        worker_id = worker_id.strip()
        start = int(start_byte)
        end = int(end_byte)
        digest = sha256.strip().casefold()
        if not all((request_id, media_id, storage_id, organization_id, service_id, worker_id)):
            raise ValueError("linked range upload identity is required")
        if start < 0 or end < start or end - start + 1 > _MAX_RANGE_BYTES:
            raise ValueError("linked range upload is invalid")
        if len(payload) != end - start + 1:
            raise ValueError("linked range payload length mismatch")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("linked range sha256 is invalid")
        if hashlib.sha256(payload).hexdigest() != digest:
            raise ValueError("linked range sha256 mismatch")

        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_source_service(cursor, storage_id, service_id)
                cursor.execute(
                    "SELECT media_id,organization_id,start_byte,end_byte,total_size,mime_type,"
                    "requested_by,claimed_by,EXTRACT(EPOCH FROM expires_at)::BIGINT "
                    "FROM linked_range_requests_pg "
                    "WHERE request_id=%s AND storage_id=%s AND expires_at>NOW() "
                    "AND state='claimed' AND lease_until>NOW() FOR UPDATE",
                    (request_id, storage_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise PermissionError("linked range lease is not active")
                if (
                    str(row[0]) != media_id
                    or str(row[1]) != organization_id
                    or int(row[2]) != start
                    or int(row[3]) != end
                    or str(row[7]) != worker_id
                ):
                    raise PermissionError("linked range lease identity mismatch")
                cursor.execute(
                    "UPDATE linked_range_requests_pg SET state='ready',sha256=%s,payload=%s,"
                    "lease_until=NULL WHERE request_id=%s",
                    (digest, payload, request_id),
                )
                result = LinkedRangeResult(
                    request_id=request_id,
                    media_id=media_id,
                    organization_id=organization_id,
                    requested_by=str(row[6]),
                    start_byte=start,
                    end_byte=end,
                    total_size=int(row[4]),
                    mime_type=str(row[5]),
                    state="ready",
                    sha256=digest,
                    payload=bytes(payload),
                    expires_at_epoch=int(row[8]),
                )
        return result

    def result(
        self, request_id: str, organization_id: str, requested_by: str
    ) -> LinkedRangeResult | None:
        request_id = request_id.strip()
        organization_id = organization_id.strip()
        requested_by = requested_by.strip()
        if not all((request_id, organization_id, requested_by)):
            return None
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._delete_expired(cursor)
                cursor.execute(
                    "SELECT request_id,media_id,organization_id,requested_by,start_byte,end_byte,"
                    "total_size,mime_type,state,sha256,payload,"
                    "EXTRACT(EPOCH FROM expires_at)::BIGINT "
                    "FROM linked_range_requests_pg WHERE request_id=%s "
                    "AND organization_id=%s AND requested_by=%s AND expires_at>NOW()",
                    (request_id, organization_id, requested_by),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return LinkedRangeResult(
            request_id=str(row[0]),
            media_id=str(row[1]),
            organization_id=str(row[2]),
            requested_by=str(row[3]),
            start_byte=int(row[4]),
            end_byte=int(row[5]),
            total_size=int(row[6]),
            mime_type=str(row[7]),
            state=str(row[8]),
            sha256=str(row[9]),
            payload=b"" if row[10] is None else bytes(row[10]),
            expires_at_epoch=int(row[11]),
        )

    @staticmethod
    def _delete_expired(cursor: Any) -> None:
        cursor.execute("DELETE FROM linked_range_requests_pg WHERE expires_at<=NOW()")

    @staticmethod
    def _require_source_service(cursor: Any, storage_id: str, service_id: str) -> None:
        cursor.execute(
            "SELECT service_id FROM linked_storage_sources_pg "
            "WHERE storage_id=%s AND enabled=TRUE FOR SHARE",
            (storage_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise KeyError(storage_id)
        if str(row[0]) != service_id:
            raise PermissionError("storage source is owned by a different service")


def range_etag(result: LinkedRangeResult) -> str:
    """Stable strong ETag for one transferred range."""
    if result.state != "ready" or not result.sha256:
        return ""
    return result.sha256


def range_retry_after_seconds(result: LinkedRangeResult | None) -> int:
    """Small polling hint bounded by the remaining request lifetime."""
    if result is None:
        return 1
    remaining = max(1, result.expires_at_epoch - int(time.time()))
    return min(2, remaining)

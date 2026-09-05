"""PostgreSQL leasing for storage-service thumbnail workers.

Claims are bound to the storage source's enrolled service identity and use row locks with
SKIP LOCKED so multiple Fieldora/storage-service workers can consume one shared queue
without duplicate work. Transport authentication remains the responsibility of the
service boundary that calls this repository.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from natureai_next.server.storage_exchange import PreviewState


@dataclass(frozen=True, slots=True)
class LinkedPreviewLease:
    media_id: str
    storage_id: str
    object_id: str
    organization_id: str
    priority: int
    reason: str
    requested_by: str
    worker_id: str


class PostgresLinkedPreviewLeases:
    """Shared lease/ack queue used by externally mounted storage-service workers."""

    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect

    def claim(
        self,
        *,
        storage_id: str,
        service_id: str,
        worker_id: str,
        limit: int = 50,
        lease_seconds: int = 120,
    ) -> tuple[LinkedPreviewLease, ...]:
        storage_id = storage_id.strip()
        service_id = service_id.strip()
        worker_id = worker_id.strip()
        if not storage_id or not service_id or not worker_id:
            raise ValueError("preview claim identity is required")
        bounded_limit = max(1, min(int(limit), 200))
        bounded_lease = max(30, min(int(lease_seconds), 900))

        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_source_service(cursor, storage_id, service_id)
                cursor.execute(
                    "SELECT q.media_id,q.storage_id,m.object_id,q.organization_id,"
                    "q.priority,q.reason,q.requested_by "
                    "FROM linked_preview_queue_pg q "
                    "JOIN linked_storage_media_pg m ON m.media_id=q.media_id "
                    "WHERE q.storage_id=%s "
                    "AND (q.lease_until IS NULL OR q.lease_until<=NOW()) "
                    "ORDER BY q.priority DESC,q.requested_at,q.media_id "
                    "FOR UPDATE OF q SKIP LOCKED LIMIT %s",
                    (storage_id, bounded_limit),
                )
                rows = cursor.fetchall()
                leases: list[LinkedPreviewLease] = []
                for row in rows:
                    media_id = str(row[0])
                    cursor.execute(
                        "UPDATE linked_preview_queue_pg SET claimed_by=%s,"
                        "lease_until=NOW()+(%s*INTERVAL '1 second') WHERE media_id=%s",
                        (worker_id, bounded_lease, media_id),
                    )
                    cursor.execute(
                        "UPDATE linked_storage_media_pg SET thumbnail_state=%s "
                        "WHERE media_id=%s",
                        (PreviewState.PROCESSING.value, media_id),
                    )
                    leases.append(
                        LinkedPreviewLease(
                            media_id=media_id,
                            storage_id=str(row[1]),
                            object_id=str(row[2]),
                            organization_id=str(row[3]),
                            priority=int(row[4]),
                            reason=str(row[5]),
                            requested_by=str(row[6]),
                            worker_id=worker_id,
                        )
                    )
        return tuple(leases)

    def complete(
        self,
        *,
        media_id: str,
        storage_id: str,
        service_id: str,
        worker_id: str,
        state: PreviewState,
        thumbnail_etag: str = "",
    ) -> bool:
        if state not in {PreviewState.READY, PreviewState.UNSUPPORTED, PreviewState.FAILED}:
            raise ValueError("preview completion state is not terminal")
        media_id = media_id.strip()
        storage_id = storage_id.strip()
        service_id = service_id.strip()
        worker_id = worker_id.strip()
        if not media_id or not storage_id or not service_id or not worker_id:
            raise ValueError("preview completion identity is required")
        if len(thumbnail_etag) > 512:
            raise ValueError("thumbnail etag is too long")

        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_source_service(cursor, storage_id, service_id)
                cursor.execute(
                    "SELECT claimed_by FROM linked_preview_queue_pg "
                    "WHERE media_id=%s AND storage_id=%s "
                    "AND lease_until>NOW() FOR UPDATE",
                    (media_id, storage_id),
                )
                row = cursor.fetchone()
                if row is None or str(row[0]) != worker_id:
                    return False
                cursor.execute(
                    "UPDATE linked_storage_media_pg SET thumbnail_state=%s,thumbnail_etag=%s "
                    "WHERE media_id=%s AND storage_id=%s",
                    (state.value, thumbnail_etag, media_id, storage_id),
                )
                if cursor.rowcount != 1:
                    return False
                cursor.execute(
                    "DELETE FROM linked_preview_queue_pg WHERE media_id=%s",
                    (media_id,),
                )
        return True

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

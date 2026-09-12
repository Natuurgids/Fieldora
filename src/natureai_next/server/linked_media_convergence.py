"""Converge verified linked evidence into canonical governed Library media.

Linked storage paths and provider identities remain inside the storage boundary. The
canonical Library receives only verified content metadata plus an opaque internal
source reference; original bytes remain in place.
"""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath

from natureai_next.server.linked_storage import (
    LinkedMediaRecord,
    LinkedStorageRepository,
    LinkedStorageSource,
    sha256_linked_file,
)
from natureai_next.server.media import GovernedMediaStore, MediaRecord
from natureai_next.server.media_links import new_association


class LinkedMediaConvergenceService:
    """Attach a verified linked instance to canonical governed media.

    Discovery alone never creates governed evidence. Convergence happens only after
    the current linked bytes are re-validated against the catalogue stat and hashed
    read-only. Project context is represented as an association, never as ownership.
    """

    def __init__(
        self,
        linked_repository: LinkedStorageRepository,
        governed_media: GovernedMediaStore,
    ) -> None:
        self._linked = linked_repository
        self._governed = governed_media

    def converge(self, linked_media_id: str, *, linked_by: str) -> MediaRecord:
        record = self._linked.media(linked_media_id)
        if record is None or record.missing:
            raise ValueError("linked media is unavailable")
        source = self._linked.source(record.storage_id)
        if source is None or not source.enabled or not source.read_only:
            raise ValueError("linked storage source is unavailable")
        if source.organization_id != record.organization_id:
            raise ValueError("linked media organization does not match source")
        actor = linked_by.strip()
        if record.project_id and not actor:
            raise ValueError("project association actor is required")

        before = _contained_stat(source, record)
        if before != (record.size_bytes, record.modified_ns):
            raise ValueError("linked media changed since catalogue scan; rescan required")
        digest = sha256_linked_file(source, record.relative_path)
        after = _contained_stat(source, record)
        if after != before:
            raise ValueError("linked media changed during verification; rescan required")
        if record.sha256 and record.sha256 != digest:
            raise ValueError("linked media content changed after prior verification")

        canonical = self._governed.attach_referenced(
            organization_id=record.organization_id,
            project_id=record.project_id,
            mime_type=record.mime_type,
            size_bytes=record.size_bytes,
            sha256=digest,
            source_ref=_opaque_source_ref(record),
            availability="available",
        )
        if record.project_id:
            self._governed.associations.link(
                new_association(
                    media_id=canonical.media_id,
                    organization_id=record.organization_id,
                    association_type="project",
                    target_id=record.project_id,
                    purpose="linked-reference",
                    linked_by=actor,
                )
            )
        if not record.sha256:
            self._linked.set_sha256(record.media_id, digest)
        return canonical


def _contained_stat(
    source: LinkedStorageSource, record: LinkedMediaRecord
) -> tuple[int, int]:
    root = Path(source.root_path).resolve(strict=True)
    relative = PurePosixPath(record.relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("linked path escapes storage source")
    candidate = (root / Path(*relative.parts)).resolve(strict=True)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("linked path escapes storage source") from exc
    stat = candidate.stat()
    return int(stat.st_size), int(stat.st_mtime_ns)


def _opaque_source_ref(record: LinkedMediaRecord) -> str:
    identity = f"{record.organization_id}\0{record.media_id}".encode()
    return "linked:" + hashlib.sha256(identity).hexdigest()

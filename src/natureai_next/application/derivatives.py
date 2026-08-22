"""Application service for durable, idempotent media derivative requests."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from natureai_next.application.jobs import JobService, SubmitJob
from natureai_next.domain.jobs import JobState, ResourceClass

@dataclass(frozen=True, slots=True)
class DerivativeRequest:
    asset_id: int
    file_instance_id: int
    source: Path
    source_sha256: str
    kind: str = "thumbnail"
    max_size: int = 384
    quality: int = 85
    renderer_identity: str = "pillow-v1"
    output_format: str = "JPEG"

class DurableDerivativeScheduler:
    def __init__(self, jobs: JobService) -> None:
        self.jobs = jobs

    def schedule(self, request: DerivativeRequest):
        identity = hashlib.sha256(
            f"{request.file_instance_id}\0{request.source_sha256}\0{request.kind}\0{request.max_size}\0{request.quality}\0{request.renderer_identity}\0{request.output_format}".encode()
        ).hexdigest()
        job = self.jobs.submit(SubmitJob(
            job_type="media.generate_derivative",
            resource_class=ResourceClass.IO,
            priority=20 if request.kind == "thumbnail" else 10,
            idempotency_key=f"derivative:{identity}",
            payload={
                "asset_id": request.asset_id,
                "file_instance_id": request.file_instance_id,
                "source": str(request.source),
                "source_sha256": request.source_sha256,
                "kind": request.kind,
                "max_width": request.max_size,
                "max_height": request.max_size,
                "quality": request.quality,
                "renderer_identity": request.renderer_identity,
                "output_format": request.output_format,
            },
        ))
        # A derivative is a rebuildable cache artifact. If the file or catalog
        # record was removed after an earlier successful job, the stable
        # idempotency key returns that completed job. Requeue that exact record
        # instead of creating unbounded repair jobs.
        if job.state is JobState.SUCCEEDED and self.jobs.restart_completed(job.public_id):
            refreshed = next(
                (item for item in self.jobs.recent(100) if item.public_id == job.public_id),
                None,
            )
            return refreshed or job
        return job


def schedule_missing_photo_thumbnails(factory, scheduler: DurableDerivativeScheduler, *, limit: int = 10000) -> int:
    """Reconcile photo assets that have no current valid thumbnail job/artifact."""
    connection = factory.connect(read_only=True)
    try:
        rows = connection.execute(
            """SELECT a.id asset_id,f.id file_instance_id,f.normalized_path,f.sha256
            FROM assets a
            JOIN file_instances f ON f.id=a.primary_file_instance_id
            JOIN image_properties ip ON ip.asset_id=a.id
            WHERE a.lifecycle_state='active' AND f.availability_state='available'
              AND f.thumbnail_state='imported'
              AND NOT EXISTS(
                SELECT 1 FROM derivative_cache_entries d
                WHERE d.asset_id=a.id AND d.derivative_kind='thumbnail' AND d.state='valid'
              )
            ORDER BY a.id LIMIT ?""",
            (int(limit),),
        ).fetchall()
    finally:
        connection.close()
    scheduled = 0
    for row in rows:
        source = Path(str(row["normalized_path"]))
        if not source.is_file():
            continue
        job = scheduler.schedule(DerivativeRequest(
            asset_id=int(row["asset_id"]),
            file_instance_id=int(row["file_instance_id"]),
            source=source,
            source_sha256=str(row["sha256"] or ""),
        ))
        if job.state in {JobState.FAILED, JobState.INTERRUPTED, JobState.PAUSED}:
            scheduler.jobs.resume(job.public_id)
        scheduled += 1
    return scheduled

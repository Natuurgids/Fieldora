"""SQLite adapter for Application job commands and recent-history queries."""

from __future__ import annotations

from natureai_next.domain.jobs import JobRecord
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.repositories import SqliteJobRepository
from natureai_next.infrastructure.database.unit_of_work import SqliteUnitOfWork


class SqliteJobCommandStore:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def submit(self, record: JobRecord) -> JobRecord:
        with SqliteUnitOfWork(self._factory) as uow:
            if record.idempotency_key:
                row = uow.connection.execute(
                    "SELECT public_id FROM jobs WHERE idempotency_key=?", (record.idempotency_key,)
                ).fetchone()
                if row is not None:
                    existing = uow.jobs.get(row[0])
                    uow.commit()
                    if existing is None:
                        raise RuntimeError("idempotent job disappeared")
                    return existing
            created = uow.jobs.add(record)
            uow.commit()
            return created

    def request_cancel(self, public_id: str, now_us: int) -> bool:
        return self._change(lambda jobs: jobs.request_cancel(public_id, now_us))

    def request_pause(self, public_id: str, now_us: int) -> bool:
        return self._change(lambda jobs: jobs.request_pause(public_id, now_us))

    def resume(self, public_id: str, now_us: int) -> bool:
        return self._change(lambda jobs: jobs.resume(public_id, now_us))

    def restart_completed(self, public_id: str, now_us: int) -> bool:
        """Requeue a completed disposable-cache job without creating duplicates."""
        with SqliteUnitOfWork(self._factory) as uow:
            cursor = uow.connection.execute(
                """UPDATE jobs
                   SET state='queued', cancellation_requested=0, pause_requested=0,
                       retry_at_us=NULL, started_at_us=NULL, completed_at_us=NULL,
                       lease_owner=NULL, lease_expires_at_us=NULL,
                       progress_current=0, progress_total=NULL, progress_unit=NULL,
                       progress_message='Derivative cache rebuild queued',
                       error_code=NULL, diagnostic_reference=NULL, result_json=NULL,
                       modified_at_us=?
                   WHERE public_id=? AND state='succeeded'
                     AND job_type='media.generate_derivative'""",
                (now_us, public_id),
            )
            uow.commit()
            return cursor.rowcount == 1

    def list_recent(self, limit: int = 100) -> tuple[JobRecord, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            return SqliteJobRepository(connection).list_recent(limit)
        finally:
            connection.close()

    def _change(self, operation) -> bool:
        with SqliteUnitOfWork(self._factory) as uow:
            changed = operation(uow.jobs)
            uow.commit()
            return changed

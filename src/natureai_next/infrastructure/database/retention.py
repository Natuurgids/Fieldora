"""SQLite workflow-history retention adapter."""

from __future__ import annotations

from natureai_next.domain.workflows import RetentionPolicy
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory

_DAY_US = 86_400_000_000


class SqliteRetentionHistoryStore:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def eligible_ids(
        self, *, now_us: int, policy: RetentionPolicy
    ) -> tuple[tuple[int, ...], tuple[int, ...]]:
        connection = self._factory.connect()
        try:
            thresholds = {
                "succeeded": now_us - policy.succeeded_job_days * _DAY_US,
                "failed": now_us - policy.failed_job_days * _DAY_US,
                "cancelled": now_us - policy.cancelled_job_days * _DAY_US,
            }
            rows = connection.execute(
                """SELECT id,job_type,state,completed_at_us,
                          ROW_NUMBER() OVER (PARTITION BY job_type ORDER BY completed_at_us DESC,id DESC) AS recency
                   FROM jobs
                   WHERE state IN ('succeeded','failed','cancelled') AND completed_at_us IS NOT NULL"""
            ).fetchall()
            job_ids = tuple(
                int(row["id"])
                for row in rows
                if row["recency"] > policy.keep_latest_jobs_per_type
                and int(row["completed_at_us"]) < thresholds[str(row["state"])]
            )
            event_threshold = now_us - policy.dispatched_event_days * _DAY_US
            event_rows = connection.execute(
                "SELECT id FROM event_outbox WHERE dispatch_state='dispatched' AND created_at_us<?",
                (event_threshold,),
            ).fetchall()
            return job_ids, tuple(int(row["id"]) for row in event_rows)
        finally:
            connection.close()

    def delete(self, *, job_ids: tuple[int, ...], event_ids: tuple[int, ...]) -> None:
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            if job_ids:
                placeholders = ",".join("?" for _ in job_ids)
                connection.execute(f"DELETE FROM jobs WHERE id IN ({placeholders})", job_ids)
            if event_ids:
                placeholders = ",".join("?" for _ in event_ids)
                connection.execute(
                    f"DELETE FROM event_outbox WHERE id IN ({placeholders})", event_ids
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

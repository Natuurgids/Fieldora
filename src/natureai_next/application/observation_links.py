"""Durable observation-to-subject links used by enrichment projection."""

from __future__ import annotations

import time
from pathlib import Path

from natureai_next.domain.enrichment import SubjectRef, SubjectType
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory


class ObservationLinkService:
    def __init__(self, database_path: Path) -> None:
        self._factory = SqliteConnectionFactory(database_path)

    def link(self, observation_public_id: str, subject: SubjectRef) -> None:
        if subject.subject_type is SubjectType.OBSERVATION:
            raise ValueError("an observation cannot be linked to itself as evidence")
        now = time.time_ns() // 1000
        connection = self._factory.connect()
        try:
            connection.execute(
                """INSERT INTO observation_subject_links(
                       observation_public_id,subject_type,subject_public_id,created_at_us
                   ) VALUES(?,?,?,?)
                   ON CONFLICT(observation_public_id,subject_type,subject_public_id) DO NOTHING""",
                (observation_public_id, subject.subject_type.value, subject.public_id, now),
            )
        finally:
            connection.close()

    def unlink(self, observation_public_id: str, subject: SubjectRef) -> None:
        connection = self._factory.connect()
        try:
            connection.execute(
                "DELETE FROM observation_subject_links WHERE observation_public_id=? AND subject_type=? AND subject_public_id=?",
                (observation_public_id, subject.subject_type.value, subject.public_id),
            )
        finally:
            connection.close()

    def linked_subjects(self, observation_public_id: str) -> tuple[SubjectRef, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                """SELECT subject_type,subject_public_id
                   FROM observation_subject_links
                   WHERE observation_public_id=?
                   ORDER BY subject_type,subject_public_id""",
                (observation_public_id,),
            ).fetchall()
            return tuple(SubjectRef(SubjectType(str(row[0])), str(row[1])) for row in rows)
        finally:
            connection.close()

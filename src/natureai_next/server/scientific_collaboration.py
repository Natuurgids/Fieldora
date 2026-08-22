"""Project-independent scientific intake and expert determination records.

Library evidence is authoritative independently of projects.  A submission records how
material entered the institution; a review case records a request for interpretation;
determinations are immutable expert assertions that may later be accepted or superseded.
Projects are optional references rather than ownership containers.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class SubmissionRecord:
    submission_id: str
    organization_id: str
    submitted_by: str
    source_type: str
    source_reference: str
    project_id: str
    collection_id: str
    license_id: str
    consent_code: str
    purpose: str
    state: str
    created_at_epoch: int
    updated_at_epoch: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ReviewCase:
    review_case_id: str
    organization_id: str
    subject_type: str
    subject_id: str
    project_id: str
    domain: str
    specialty: str
    geography: str
    state: str
    requested_by: str
    accepted_determination_id: str
    created_at_epoch: int
    updated_at_epoch: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Determination:
    determination_id: str
    review_case_id: str
    expert_id: str
    assertion: str
    confidence: float
    evidence_json: dict[str, object]
    created_at_epoch: int
    supersedes_id: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class CollaborationRepository(Protocol):
    def create_submission(self, **kwargs: Any) -> SubmissionRecord: ...
    def submission(self, submission_id: str) -> SubmissionRecord | None: ...
    def submissions(self, organization_id: str, limit: int = 100) -> tuple[SubmissionRecord, ...]: ...
    def create_review_case(self, **kwargs: Any) -> ReviewCase: ...
    def review_case(self, review_case_id: str) -> ReviewCase | None: ...
    def review_cases(self, organization_id: str, limit: int = 100) -> tuple[ReviewCase, ...]: ...
    def add_determination(self, **kwargs: Any) -> Determination: ...
    def determinations(self, review_case_id: str) -> tuple[Determination, ...]: ...
    def accept_determination(self, review_case_id: str, determination_id: str) -> ReviewCase: ...


_SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS scientific_submissions(
    submission_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    submitted_by TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_reference TEXT NOT NULL,
    project_id TEXT NOT NULL DEFAULT '',
    collection_id TEXT NOT NULL DEFAULT '',
    license_id TEXT NOT NULL DEFAULT '',
    consent_code TEXT NOT NULL DEFAULT '',
    purpose TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at_epoch INTEGER NOT NULL,
    updated_at_epoch INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_scientific_submissions_scope
    ON scientific_submissions(organization_id,state,created_at_epoch,submission_id);
CREATE TABLE IF NOT EXISTS scientific_review_cases(
    review_case_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    project_id TEXT NOT NULL DEFAULT '',
    domain TEXT NOT NULL,
    specialty TEXT NOT NULL DEFAULT '',
    geography TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    accepted_determination_id TEXT NOT NULL DEFAULT '',
    created_at_epoch INTEGER NOT NULL,
    updated_at_epoch INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_scientific_review_cases_route
    ON scientific_review_cases(organization_id,state,domain,specialty,geography);
CREATE TABLE IF NOT EXISTS scientific_determinations(
    determination_id TEXT PRIMARY KEY,
    review_case_id TEXT NOT NULL REFERENCES scientific_review_cases(review_case_id),
    expert_id TEXT NOT NULL,
    assertion TEXT NOT NULL,
    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
    evidence_json TEXT NOT NULL,
    created_at_epoch INTEGER NOT NULL,
    supersedes_id TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_scientific_determinations_case
    ON scientific_determinations(review_case_id,created_at_epoch,determination_id);
CREATE TABLE IF NOT EXISTS scientific_review_events(
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    review_case_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    occurred_at_epoch INTEGER NOT NULL
);
"""


class SqliteCollaborationRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA_SQLITE)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, isolation_level=None, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def create_submission(self, **kwargs: Any) -> SubmissionRecord:
        record = _submission_from_kwargs(kwargs)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO scientific_submissions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                tuple(asdict(record).values()),
            )
        return record

    def submission(self, submission_id: str) -> SubmissionRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM scientific_submissions WHERE submission_id=?",
                (submission_id,),
            ).fetchone()
        return None if row is None else SubmissionRecord(*row)

    def submissions(
        self, organization_id: str, limit: int = 100
    ) -> tuple[SubmissionRecord, ...]:
        limit = max(1, min(int(limit), 500))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM scientific_submissions WHERE organization_id=? "
                "ORDER BY created_at_epoch DESC,submission_id DESC LIMIT ?",
                (organization_id, limit),
            ).fetchall()
        return tuple(SubmissionRecord(*row) for row in rows)

    def create_review_case(self, **kwargs: Any) -> ReviewCase:
        record = _review_case_from_kwargs(kwargs)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO scientific_review_cases VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                tuple(asdict(record).values()),
            )
            self._event(
                connection,
                record.review_case_id,
                "review_requested",
                record.requested_by,
                {"domain": record.domain, "specialty": record.specialty},
                record.created_at_epoch,
            )
        return record

    def review_case(self, review_case_id: str) -> ReviewCase | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM scientific_review_cases WHERE review_case_id=?",
                (review_case_id,),
            ).fetchone()
        return None if row is None else ReviewCase(*row)

    def review_cases(
        self, organization_id: str, limit: int = 100
    ) -> tuple[ReviewCase, ...]:
        limit = max(1, min(int(limit), 500))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM scientific_review_cases WHERE organization_id=? "
                "ORDER BY updated_at_epoch DESC,review_case_id DESC LIMIT ?",
                (organization_id, limit),
            ).fetchall()
        return tuple(ReviewCase(*row) for row in rows)

    def add_determination(self, **kwargs: Any) -> Determination:
        determination = _determination_from_kwargs(kwargs)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            case = connection.execute(
                "SELECT organization_id,state FROM scientific_review_cases "
                "WHERE review_case_id=?",
                (determination.review_case_id,),
            ).fetchone()
            if case is None:
                raise KeyError(determination.review_case_id)
            if str(case["state"]) == "closed":
                raise ValueError("review case is closed")
            connection.execute(
                "INSERT INTO scientific_determinations VALUES(?,?,?,?,?,?,?)",
                (
                    determination.determination_id,
                    determination.review_case_id,
                    determination.expert_id,
                    determination.assertion,
                    determination.confidence,
                    json.dumps(
                        determination.evidence_json,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    determination.created_at_epoch,
                    determination.supersedes_id,
                ),
            )
            connection.execute(
                "UPDATE scientific_review_cases SET state='under_review',updated_at_epoch=? "
                "WHERE review_case_id=?",
                (determination.created_at_epoch, determination.review_case_id),
            )
            self._event(
                connection,
                determination.review_case_id,
                "determination_added",
                determination.expert_id,
                {"determination_id": determination.determination_id},
                determination.created_at_epoch,
            )
            connection.commit()
        return determination

    def determinations(self, review_case_id: str) -> tuple[Determination, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM scientific_determinations WHERE review_case_id=? "
                "ORDER BY created_at_epoch,determination_id",
                (review_case_id,),
            ).fetchall()
        return tuple(_determination_from_row(row) for row in rows)

    def accept_determination(
        self, review_case_id: str, determination_id: str
    ) -> ReviewCase:
        now = int(time.time())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT expert_id FROM scientific_determinations "
                "WHERE review_case_id=? AND determination_id=?",
                (review_case_id, determination_id),
            ).fetchone()
            if row is None:
                raise KeyError(determination_id)
            connection.execute(
                "UPDATE scientific_review_cases SET accepted_determination_id=?,"
                "state='accepted',updated_at_epoch=? WHERE review_case_id=?",
                (determination_id, now, review_case_id),
            )
            self._event(
                connection,
                review_case_id,
                "determination_accepted",
                str(row["expert_id"]),
                {"determination_id": determination_id},
                now,
            )
            connection.commit()
        result = self.review_case(review_case_id)
        if result is None:
            raise KeyError(review_case_id)
        return result

    @staticmethod
    def _event(
        connection: sqlite3.Connection,
        review_case_id: str,
        event_type: str,
        actor_id: str,
        detail: dict[str, object],
        now: int,
    ) -> None:
        connection.execute(
            "INSERT INTO scientific_review_events("
            "review_case_id,event_type,actor_id,detail_json,occurred_at_epoch"
            ") VALUES(?,?,?,?,?)",
            (
                review_case_id,
                event_type,
                actor_id,
                json.dumps(detail, sort_keys=True, separators=(",", ":")),
                now,
            ),
        )


class PostgresCollaborationRepository:
    """Shared collaboration repository intended for multi-node deployments."""

    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scientific_submissions(
                        submission_id TEXT PRIMARY KEY,
                        organization_id TEXT NOT NULL,
                        submitted_by TEXT NOT NULL,
                        source_type TEXT NOT NULL,
                        source_reference TEXT NOT NULL,
                        project_id TEXT NOT NULL DEFAULT '',
                        collection_id TEXT NOT NULL DEFAULT '',
                        license_id TEXT NOT NULL DEFAULT '',
                        consent_code TEXT NOT NULL DEFAULT '',
                        purpose TEXT NOT NULL,
                        state TEXT NOT NULL,
                        created_at_epoch BIGINT NOT NULL,
                        updated_at_epoch BIGINT NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scientific_review_cases(
                        review_case_id TEXT PRIMARY KEY,
                        organization_id TEXT NOT NULL,
                        subject_type TEXT NOT NULL,
                        subject_id TEXT NOT NULL,
                        project_id TEXT NOT NULL DEFAULT '',
                        domain TEXT NOT NULL,
                        specialty TEXT NOT NULL DEFAULT '',
                        geography TEXT NOT NULL DEFAULT '',
                        state TEXT NOT NULL,
                        requested_by TEXT NOT NULL,
                        accepted_determination_id TEXT NOT NULL DEFAULT '',
                        created_at_epoch BIGINT NOT NULL,
                        updated_at_epoch BIGINT NOT NULL
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_scientific_review_cases_route_pg "
                    "ON scientific_review_cases(organization_id,state,domain,specialty,geography)"
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scientific_determinations(
                        determination_id TEXT PRIMARY KEY,
                        review_case_id TEXT NOT NULL,
                        expert_id TEXT NOT NULL,
                        assertion TEXT NOT NULL,
                        confidence DOUBLE PRECISION NOT NULL CHECK(
                            confidence >= 0 AND confidence <= 1
                        ),
                        evidence_json JSONB NOT NULL,
                        created_at_epoch BIGINT NOT NULL,
                        supersedes_id TEXT NOT NULL DEFAULT ''
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_scientific_determinations_case_pg "
                    "ON scientific_determinations(review_case_id,created_at_epoch,determination_id)"
                )

    def create_submission(self, **kwargs: Any) -> SubmissionRecord:
        record = _submission_from_kwargs(kwargs)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO scientific_submissions VALUES(" + ",".join(["%s"] * 13) + ")",
                    tuple(asdict(record).values()),
                )
        return record

    def submission(self, submission_id: str) -> SubmissionRecord | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM scientific_submissions WHERE submission_id=%s",
                    (submission_id,),
                )
                row = cursor.fetchone()
        return None if row is None else SubmissionRecord(*row)

    def submissions(
        self, organization_id: str, limit: int = 100
    ) -> tuple[SubmissionRecord, ...]:
        limit = max(1, min(int(limit), 500))
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM scientific_submissions WHERE organization_id=%s "
                    "ORDER BY created_at_epoch DESC,submission_id DESC LIMIT %s",
                    (organization_id, limit),
                )
                rows = cursor.fetchall()
        return tuple(SubmissionRecord(*row) for row in rows)

    def create_review_case(self, **kwargs: Any) -> ReviewCase:
        record = _review_case_from_kwargs(kwargs)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO scientific_review_cases VALUES(" + ",".join(["%s"] * 13) + ")",
                    tuple(asdict(record).values()),
                )
        return record

    def review_case(self, review_case_id: str) -> ReviewCase | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM scientific_review_cases WHERE review_case_id=%s",
                    (review_case_id,),
                )
                row = cursor.fetchone()
        return None if row is None else ReviewCase(*row)

    def review_cases(
        self, organization_id: str, limit: int = 100
    ) -> tuple[ReviewCase, ...]:
        limit = max(1, min(int(limit), 500))
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM scientific_review_cases WHERE organization_id=%s "
                    "ORDER BY updated_at_epoch DESC,review_case_id DESC LIMIT %s",
                    (organization_id, limit),
                )
                rows = cursor.fetchall()
        return tuple(ReviewCase(*row) for row in rows)

    def add_determination(self, **kwargs: Any) -> Determination:
        determination = _determination_from_kwargs(kwargs)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT state FROM scientific_review_cases WHERE review_case_id=%s "
                    "FOR UPDATE",
                    (determination.review_case_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise KeyError(determination.review_case_id)
                if str(row[0]) == "closed":
                    raise ValueError("review case is closed")
                cursor.execute(
                    "INSERT INTO scientific_determinations VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        determination.determination_id,
                        determination.review_case_id,
                        determination.expert_id,
                        determination.assertion,
                        determination.confidence,
                        json.dumps(determination.evidence_json),
                        determination.created_at_epoch,
                        determination.supersedes_id,
                    ),
                )
                cursor.execute(
                    "UPDATE scientific_review_cases SET state='under_review',"
                    "updated_at_epoch=%s WHERE review_case_id=%s",
                    (determination.created_at_epoch, determination.review_case_id),
                )
        return determination

    def determinations(self, review_case_id: str) -> tuple[Determination, ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT determination_id,review_case_id,expert_id,assertion,confidence,"
                    "evidence_json,created_at_epoch,supersedes_id FROM scientific_determinations "
                    "WHERE review_case_id=%s ORDER BY created_at_epoch,determination_id",
                    (review_case_id,),
                )
                rows = cursor.fetchall()
        return tuple(_determination_from_row(row) for row in rows)

    def accept_determination(
        self, review_case_id: str, determination_id: str
    ) -> ReviewCase:
        now = int(time.time())
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM scientific_determinations "
                    "WHERE review_case_id=%s AND determination_id=%s",
                    (review_case_id, determination_id),
                )
                if cursor.fetchone() is None:
                    raise KeyError(determination_id)
                cursor.execute(
                    "UPDATE scientific_review_cases SET accepted_determination_id=%s,"
                    "state='accepted',updated_at_epoch=%s WHERE review_case_id=%s",
                    (determination_id, now, review_case_id),
                )
                if cursor.rowcount != 1:
                    raise KeyError(review_case_id)
        result = self.review_case(review_case_id)
        assert result is not None
        return result


def _submission_from_kwargs(values: dict[str, Any]) -> SubmissionRecord:
    now = int(values.get("now_epoch") or time.time())
    organization_id = str(values.get("organization_id", "")).strip()
    submitted_by = str(values.get("submitted_by", "")).strip()
    source_type = str(values.get("source_type", "")).strip()
    purpose = str(values.get("purpose", "research")).strip()
    if not all((organization_id, submitted_by, source_type, purpose)):
        raise ValueError("submission organization, contributor, source, and purpose are required")
    return SubmissionRecord(
        str(values.get("submission_id") or uuid4()),
        organization_id,
        submitted_by,
        source_type,
        str(values.get("source_reference", "")).strip()[:500],
        str(values.get("project_id", "")).strip(),
        str(values.get("collection_id", "")).strip(),
        str(values.get("license_id", "")).strip(),
        str(values.get("consent_code", "")).strip(),
        purpose,
        "received",
        now,
        now,
    )


def _review_case_from_kwargs(values: dict[str, Any]) -> ReviewCase:
    now = int(values.get("now_epoch") or time.time())
    required = {
        name: str(values.get(name, "")).strip()
        for name in ("organization_id", "subject_type", "subject_id", "domain", "requested_by")
    }
    if not all(required.values()):
        raise ValueError("review organization, subject, domain, and requester are required")
    return ReviewCase(
        str(values.get("review_case_id") or uuid4()),
        required["organization_id"],
        required["subject_type"],
        required["subject_id"],
        str(values.get("project_id", "")).strip(),
        required["domain"],
        str(values.get("specialty", "")).strip(),
        str(values.get("geography", "")).strip(),
        "requested",
        required["requested_by"],
        "",
        now,
        now,
    )


def _determination_from_kwargs(values: dict[str, Any]) -> Determination:
    review_case_id = str(values.get("review_case_id", "")).strip()
    expert_id = str(values.get("expert_id", "")).strip()
    assertion = str(values.get("assertion", "")).strip()
    confidence = float(values.get("confidence", 0.0))
    evidence = values.get("evidence_json", {})
    if not review_case_id or not expert_id or not assertion:
        raise ValueError("determination case, expert, and assertion are required")
    if not 0 <= confidence <= 1 or not isinstance(evidence, dict):
        raise ValueError("invalid determination confidence or evidence")
    return Determination(
        str(values.get("determination_id") or uuid4()),
        review_case_id,
        expert_id,
        assertion,
        confidence,
        dict(evidence),
        int(values.get("now_epoch") or time.time()),
        str(values.get("supersedes_id", "")).strip(),
    )


def _determination_from_row(row: Any) -> Determination:
    values = list(row)
    evidence = values[5]
    if isinstance(evidence, str):
        evidence = json.loads(evidence)
    values[5] = dict(evidence)
    return Determination(*values)

"""Transactional append helper for Fieldora's tamper-evident access audit chain."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any


def append_governance_audit(
    connection: Any,
    *,
    subject_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    reason: str,
    request: dict[str, object] | None = None,
    allowed: bool = True,
    occurred_at_utc: str | None = None,
) -> int:
    """Append and hash one audit event using the caller's existing transaction.

    The caller owns commit/rollback. This lets evidence-contract mutations and their
    audit evidence succeed or fail atomically on both SQLite and the PostgreSQL parity
    adapter.
    """
    occurred = occurred_at_utc or datetime.now(UTC).isoformat()
    policy_ids: list[str] = []
    request_value = request or {}
    cursor = connection.execute(
        "INSERT INTO access_audit_events("
        "occurred_at_utc,subject_id,action,resource_type,resource_id,allowed,"
        "reason,policy_ids_json,request_json) VALUES(?,?,?,?,?,?,?,?,?)",
        (
            occurred,
            subject_id,
            action,
            resource_type,
            resource_id,
            int(allowed),
            reason,
            json.dumps(policy_ids),
            json.dumps(request_value, sort_keys=True),
        ),
    )
    sequence = int(cursor.lastrowid)
    previous_row = connection.execute(
        "SELECT event_hash FROM access_audit_chain ORDER BY sequence DESC LIMIT 1"
    ).fetchone()
    previous_hash = "0" * 64 if previous_row is None else str(previous_row[0])
    canonical = json.dumps(
        {
            "sequence": sequence,
            "occurred_at_utc": occurred,
            "subject_id": subject_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "allowed": bool(allowed),
            "reason": reason,
            "policy_ids": policy_ids,
            "request": request_value,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    event_hash = hashlib.sha256((previous_hash + canonical).encode()).hexdigest()
    connection.execute(
        "INSERT INTO access_audit_chain VALUES(?,?,?)",
        (sequence, previous_hash, event_hash),
    )
    return sequence

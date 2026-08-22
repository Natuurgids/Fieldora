"""Outbox and audit entities."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    public_id: str
    event_type: str
    schema_version: int
    aggregate_public_id: str | None
    payload_json: str
    created_at_us: int
    dispatch_state: str = "pending"
    attempt_count: int = 0
    id: int | None = None


@dataclass(frozen=True, slots=True)
class AuditEntry:
    public_id: str
    actor: str
    action_type: str
    target_public_id: str
    before_json: str | None
    after_json: str | None
    created_at_us: int
    correlation_id: str
    id: int | None = None

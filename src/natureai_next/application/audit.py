"""Application-level audit recording service."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from natureai_next.domain.events import AuditEntry, OutboxEvent
from natureai_next.ports.clock import Clock
from natureai_next.ports.identity import UuidGenerator
from natureai_next.ports.persistence import UnitOfWork


@dataclass(slots=True)
class AuditService:
    clock: Clock
    ids: UuidGenerator

    def record(
        self,
        uow: UnitOfWork,
        *,
        actor: str,
        action_type: str,
        target_public_id: str,
        correlation_id: str,
        before: Mapping[str, object] | None = None,
        after: Mapping[str, object] | None = None,
    ) -> AuditEntry:
        now = int(self.clock.now_utc().timestamp() * 1_000_000)
        entry = AuditEntry(
            public_id=str(self.ids.new_uuid()),
            actor=actor,
            action_type=action_type,
            target_public_id=target_public_id,
            before_json=None
            if before is None
            else json.dumps(before, sort_keys=True, separators=(",", ":")),
            after_json=None
            if after is None
            else json.dumps(after, sort_keys=True, separators=(",", ":")),
            created_at_us=now,
            correlation_id=correlation_id,
        )
        stored = uow.audit.add(entry)
        uow.outbox.add(
            OutboxEvent(
                public_id=str(self.ids.new_uuid()),
                event_type="audit.recorded",
                schema_version=1,
                aggregate_public_id=target_public_id,
                payload_json=json.dumps(
                    {"audit_public_id": stored.public_id, "action_type": action_type},
                    sort_keys=True,
                ),
                created_at_us=now,
            )
        )
        return stored

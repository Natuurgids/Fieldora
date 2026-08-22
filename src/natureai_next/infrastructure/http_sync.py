"""Strict JSON/HTTP binding for the Phase E synchronization transport."""

from __future__ import annotations

from typing import Protocol
from urllib.parse import quote

from natureai_next.domain.sync_protocol import (
    SYNC_PROTOCOL_VERSION,
    PullPage,
    PushDisposition,
    PushResult,
)
from natureai_next.domain.synchronization import SyncChange


class JsonHttpClient(Protocol):
    def request_json(
        self, method: str, path: str, *, token: str, body: dict | None = None
    ) -> dict: ...


def _change(data: dict) -> SyncChange:
    required = {
        "change_id", "enrollment_id", "idempotency_key", "aggregate_type",
        "aggregate_id", "base_revision", "payload", "tombstone",
    }
    if (
        not required <= data.keys()
        or not isinstance(data["payload"], dict)
        or type(data["base_revision"]) is not int
        or type(data["tombstone"]) is not bool
    ):
        raise ValueError("invalid synchronization change")
    return SyncChange(
        str(data["change_id"]), str(data["enrollment_id"]),
        str(data["idempotency_key"]), str(data["aggregate_type"]),
        str(data["aggregate_id"]), int(data["base_revision"]),
        data["payload"], bool(data["tombstone"]),
    )


def _wire(change: SyncChange) -> dict:
    return {
        "change_id": change.change_id, "enrollment_id": change.enrollment_id,
        "idempotency_key": change.idempotency_key,
        "aggregate_type": change.aggregate_type, "aggregate_id": change.aggregate_id,
        "base_revision": change.base_revision, "payload": change.payload,
        "tombstone": change.tombstone,
    }


class HttpSynchronizationTransport:
    def __init__(self, client: JsonHttpClient, token_provider) -> None:
        self._client = client
        self._token_provider = token_provider

    def _token(self) -> str:
        token = str(self._token_provider())
        if not token:
            raise PermissionError("machine authentication token is required")
        return token

    def push(self, *, enrollment_id: str, changes: tuple[SyncChange, ...]):
        response = self._client.request_json(
            "POST", f"/api/v1/sync/enrollments/{quote(enrollment_id, safe='')}/push",
            token=self._token(),
            body={"protocol_version": SYNC_PROTOCOL_VERSION,
                  "changes": [_wire(change) for change in changes]},
        )
        if response.get("protocol_version") != SYNC_PROTOCOL_VERSION:
            raise ValueError("unsupported synchronization protocol version")
        results = response.get("results")
        if not isinstance(results, list):
            raise ValueError("invalid push response")
        return tuple(
            PushResult(
                str(item["change_id"]), PushDisposition(str(item["disposition"])),
                int(item.get("remote_revision", 0)), item.get("remote_payload"),
                str(item.get("retry_at_utc", "")), str(item.get("reason", "")),
            )
            for item in results
        )

    def pull(self, *, enrollment_id: str, cursor: str, limit: int) -> PullPage:
        if not 1 <= limit <= 500:
            raise ValueError("pull limit must be between 1 and 500")
        response = self._client.request_json(
            "POST", f"/api/v1/sync/enrollments/{quote(enrollment_id, safe='')}/pull",
            token=self._token(),
            body={"protocol_version": SYNC_PROTOCOL_VERSION, "cursor": cursor, "limit": limit},
        )
        changes = response.get("changes")
        if not isinstance(changes, list):
            raise ValueError("invalid pull response")
        return PullPage(
            str(response.get("enrollment_id", "")), tuple(_change(item) for item in changes),
            str(response.get("next_cursor", "")), bool(response.get("has_more", False)),
            int(response.get("protocol_version", 0)),
        )

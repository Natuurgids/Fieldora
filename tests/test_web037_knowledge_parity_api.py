from __future__ import annotations

import json
from dataclasses import dataclass

from natureai_next.server.api import ApiResponse
from natureai_next.server.knowledge_parity_api import KnowledgeParityApiMixin


@dataclass
class _Identity:
    identity_id: str = "researcher-1"
    organization_id: str = "org-1"


class _Science:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, tuple[dict, int]]] = {}

    def records(self, collection: str):
        return tuple(
            dict(item) for item, _revision in self.items.get(collection, {}).values()
        )

    def put(self, collection: str, record: dict, expected_revision: int | None):
        bucket = self.items.setdefault(collection, {})
        record_id = str(record["id"])
        current = bucket.get(record_id)
        current_revision = 0 if current is None else current[1]
        if expected_revision is not None and expected_revision != current_revision:
            raise ValueError("revision_conflict")
        revision = current_revision + 1
        bucket[record_id] = (dict(record), revision)
        return revision


class _Decision:
    allowed = True


class _Decisions:
    def decide(self, _request):
        return _Decision()


class _Base:
    def __init__(self) -> None:
        self._science = _Science()
        self._decisions = _Decisions()
        self.generic_calls: list[tuple[str, str]] = []

    def _identity(self, _headers):
        return "token", _Identity()

    def dispatch(self, method, target, _headers, _body):
        self.generic_calls.append((method, target))
        return ApiResponse.json(404, {"error": "not_found"})


class _Api(KnowledgeParityApiMixin, _Base):
    pass


def _payload(response: ApiResponse) -> dict:
    return json.loads(response.body)


def _proposal(**overrides) -> dict:
    payload = {
        "project_id": "project-1",
        "provider_key": "fieldora-ai",
        "subject": {"subject_type": "observation", "public_id": "obs-1"},
        "candidate": {
            "shape": "taxonomy_candidate",
            "value": {"scientific_name": "Bombus terrestris"},
            "confidence": 0.93,
            "target": {},
            "external_id": "taxon:123",
        },
        "source_snapshot": {
            "producer_name": "Local classifier",
            "producer_version": "v7",
            "source_name": "Fieldora offline model",
            "source_version": "2026.08",
            "checksum": "sha256:abc",
            "attribution": "Fieldora",
            "licence": "internal",
            "created_at_us": 123456,
        },
    }
    payload.update(overrides)
    return payload


def _create(api: _Api, **overrides) -> dict:
    response = api.dispatch(
        "POST",
        "/api/v1/knowledge",
        {},
        json.dumps(_proposal(**overrides)).encode(),
    )
    assert response.status == 201
    return _payload(response)


def test_browser_cannot_post_accepted_knowledge_or_forge_governance_fields() -> None:
    api = _Api()
    response = api.dispatch(
        "POST",
        "/api/v1/knowledge",
        {},
        json.dumps(
            _proposal(
                id="caller-owned-id",
                review_state="accepted",
                revision=99,
                acceptance_action_public_id="forged-action",
                submitted_by_identity_id="forged-producer",
            )
        ).encode(),
    )

    assert response.status == 400
    assert _payload(response)["error"] == "invalid_knowledge_proposal"
    assert "server_knowledge_proposals" not in api._science.items
    assert all(path != "/api/v1/knowledge" for _method, path in api.generic_calls)


def test_proposal_has_server_identity_pending_state_and_preserved_source_snapshot() -> None:
    api = _Api()
    source_snapshot = _proposal()["source_snapshot"]
    payload = _create(api)
    item = payload["item"]

    assert item["id"]
    assert item["id"] != "obs-1"
    assert item["review_state"] == "pending"
    assert item["revision"] == 1
    assert item["review_actions"] == []
    assert item["canonical"] is None
    assert item["source_snapshot"] == source_snapshot
    assert item["provider_key"] == "fieldora-ai"
    assert item["submitted_by_identity_id"] == "researcher-1"
    assert payload["revision"] == 1

    listed = api.dispatch("GET", "/api/v1/knowledge", {}, b"")
    assert listed.status == 200
    assert _payload(listed)["items"][0]["source_snapshot"] == source_snapshot
    assert all(path != "/api/v1/knowledge" for _method, path in api.generic_calls)


def test_accept_is_explicit_revisioned_and_preserves_proposal_action_and_canonical() -> None:
    api = _Api()
    created = _create(api)
    proposal = created["item"]
    proposal_id = proposal["id"]

    missing_revision = api.dispatch(
        "POST",
        f"/api/v1/knowledge/{proposal_id}/review",
        {},
        b'{"action":"accept"}',
    )
    assert missing_revision.status == 428

    accepted = api.dispatch(
        "POST",
        f"/api/v1/knowledge/{proposal_id}/review",
        {"if-match": "1"},
        b'{"action":"accept"}',
    )
    assert accepted.status == 200
    payload = _payload(accepted)
    item = payload["item"]
    action = payload["action"]
    canonical = payload["canonical"]

    assert item["id"] == proposal_id
    assert item["review_state"] == "accepted"
    assert item["source_snapshot"] == proposal["source_snapshot"]
    assert item["candidate"] == proposal["candidate"]
    assert item["review_actions"] == [action]
    assert action["action"] == "accept"
    assert action["proposal_id"] == proposal_id
    assert canonical["lifecycle_state"] == "accepted"
    assert canonical["source_suggestion_public_id"] == proposal_id
    assert canonical["acceptance_action_public_id"] == action["id"]
    assert canonical["source_snapshot"] == proposal["source_snapshot"]
    assert canonical["provider_key"] == proposal["provider_key"]
    assert payload["revision"] == 2

    assert proposal_id in api._science.items["server_knowledge_proposals"]
    assert action["id"] in api._science.items["server_knowledge_review_actions"]
    assert canonical["id"] in api._science.items["server_knowledge_canonical"]

    stale = api.dispatch(
        "POST",
        f"/api/v1/knowledge/{proposal_id}/review",
        {"if-match": "1"},
        b'{"action":"reject"}',
    )
    assert stale.status == 409
    assert _payload(stale)["error"] == "revision_conflict"


def test_defer_reject_and_invalid_or_terminal_transitions_are_governed() -> None:
    api = _Api()
    first = _create(api)["item"]

    deferred = api.dispatch(
        "POST",
        f'/api/v1/knowledge/{first["id"]}/review',
        {"if-match": "1"},
        b'{"action":"defer"}',
    )
    assert deferred.status == 200
    assert _payload(deferred)["item"]["review_state"] == "deferred"

    accepted = api.dispatch(
        "POST",
        f'/api/v1/knowledge/{first["id"]}/review',
        {"if-match": "2"},
        b'{"action":"accept"}',
    )
    assert accepted.status == 200

    terminal = api.dispatch(
        "POST",
        f'/api/v1/knowledge/{first["id"]}/review',
        {"if-match": "3"},
        b'{"action":"reject"}',
    )
    assert terminal.status == 409
    assert _payload(terminal)["error"] == "knowledge_review_already_resolved"

    second = _create(api)["item"]
    rejected = api.dispatch(
        "POST",
        f'/api/v1/knowledge/{second["id"]}/review',
        {"if-match": "1"},
        b'{"action":"reject"}',
    )
    assert rejected.status == 200
    assert _payload(rejected)["item"]["review_state"] == "rejected"

    third = _create(api)["item"]
    invalid = api.dispatch(
        "POST",
        f'/api/v1/knowledge/{third["id"]}/review',
        {"if-match": "1"},
        b'{"action":"supersede"}',
    )
    assert invalid.status == 400
    assert _payload(invalid)["error"] == "invalid_review_action"


def test_generic_item_mutation_is_blocked_instead_of_falling_back() -> None:
    api = _Api()
    proposal = _create(api)["item"]
    api.generic_calls.clear()

    response = api.dispatch(
        "PUT",
        f'/api/v1/knowledge/{proposal["id"]}',
        {"if-match": "1"},
        b'{"review_state":"accepted"}',
    )

    assert response.status == 405
    assert _payload(response)["error"] == "knowledge_review_action_required"
    assert all("/api/v1/knowledge" not in path for _method, path in api.generic_calls)

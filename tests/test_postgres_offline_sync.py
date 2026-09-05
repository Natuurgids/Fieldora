from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from natureai_next.domain.synchronization import (
    AssertionState,
    PrimaryResolution,
    SyncAssertion,
    SyncBundle,
)
from natureai_next.server.postgres_offline_sync import PostgresOfflineSyncStore


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _assertion(
    *,
    bundle_id: str,
    logical_id: str,
    value: str,
    organization_id: str,
    project_id: str,
) -> SyncAssertion:
    return SyncAssertion(
        assertion_id=str(uuid4()),
        logical_record_id=logical_id,
        record_type="observation",
        organization_id=organization_id,
        project_id=project_id,
        author_identity_id="field-worker",
        device_id="offline-tablet",
        created_at_utc=_now(),
        payload={"taxon": value, "confidence": 0.8},
        state=AssertionState.CURRENT,
        source_bundle_id=bundle_id,
        contract_id="contract-a",
        evidence_ids=("media-a",),
    )


def _store():
    dsn = os.environ.get("FIELDORA_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("FIELDORA_TEST_POSTGRES_DSN is not configured")
    psycopg = pytest.importorskip("psycopg")
    return PostgresOfflineSyncStore(lambda: psycopg.connect(dsn))


@pytest.mark.integration
def test_postgres_sync_preserves_disagreement_and_bundle_replay_is_idempotent() -> None:
    store = _store()
    suffix = uuid4().hex
    organization_id = f"org-{suffix}"
    project_id = f"project-{suffix}"
    logical_id = f"observation-{suffix}"

    bundle_a_id = str(uuid4())
    assertion_a = _assertion(
        bundle_id=bundle_a_id,
        logical_id=logical_id,
        value="Panthera onca",
        organization_id=organization_id,
        project_id=project_id,
    )
    bundle_a = SyncBundle(
        bundle_a_id,
        organization_id,
        "offline-tablet",
        "field-worker",
        _now(),
        (assertion_a,),
    )
    first = store.apply_bundle(bundle_a)
    assert first.inserted_assertion_ids == (assertion_a.assertion_id,)
    replay = store.apply_bundle(bundle_a)
    assert replay.inserted_assertion_ids == ()
    assert replay.duplicate_assertion_ids == (assertion_a.assertion_id,)

    bundle_b_id = str(uuid4())
    assertion_b = _assertion(
        bundle_id=bundle_b_id,
        logical_id=logical_id,
        value="Puma concolor",
        organization_id=organization_id,
        project_id=project_id,
    )
    second = store.apply_bundle(
        SyncBundle(
            bundle_b_id,
            organization_id,
            "offline-phone",
            "second-worker",
            _now(),
            (replace(assertion_b, device_id="offline-phone", author_identity_id="second-worker"),),
        )
    )
    assert second.conflict_record_ids == (logical_id,)

    preserved = store.assertions(organization_id, "observation", logical_id)
    assert len(preserved) == 2
    assert {item.payload["taxon"] for item in preserved} == {
        "Panthera onca",
        "Puma concolor",
    }
    assert any(item.state is AssertionState.DISPUTED for item in preserved)
    assert store.presentation_assertion(organization_id, "observation", logical_id) is None


@pytest.mark.integration
def test_postgres_primary_resolution_is_append_only_and_does_not_delete_alternatives() -> None:
    store = _store()
    suffix = uuid4().hex
    organization_id = f"org-{suffix}"
    project_id = f"project-{suffix}"
    logical_id = f"observation-{suffix}"

    ids: list[str] = []
    for device, value in (("tablet-a", "Species A"), ("tablet-b", "Species B")):
        bundle_id = str(uuid4())
        assertion = _assertion(
            bundle_id=bundle_id,
            logical_id=logical_id,
            value=value,
            organization_id=organization_id,
            project_id=project_id,
        )
        assertion = replace(assertion, device_id=device)
        store.apply_bundle(
            SyncBundle(
                bundle_id,
                organization_id,
                device,
                "field-worker",
                _now(),
                (assertion,),
            )
        )
        ids.append(assertion.assertion_id)

    first = PrimaryResolution(
        str(uuid4()),
        logical_id,
        "observation",
        organization_id,
        project_id,
        ids[0],
        "reviewer-a",
        _now(),
        "initial committee determination",
        "organization",
    )
    store.resolve_primary(first)
    assert store.presentation_assertion(
        organization_id, "observation", logical_id
    ).assertion_id == ids[0]

    second = PrimaryResolution(
        str(uuid4()),
        logical_id,
        "observation",
        organization_id,
        project_id,
        ids[1],
        "reviewer-b",
        _now(),
        "later evidence changed the displayed interpretation",
        "organization",
        first.resolution_id,
    )
    store.resolve_primary(second)
    assert store.current_resolution(
        organization_id, "observation", logical_id
    ).resolution_id == second.resolution_id
    assert store.presentation_assertion(
        organization_id, "observation", logical_id
    ).assertion_id == ids[1]
    assert len(store.assertions(organization_id, "observation", logical_id)) == 2

    with pytest.raises(ValueError, match="history conflict"):
        store.resolve_primary(
            replace(second, resolution_id=str(uuid4()), previous_resolution_id="")
        )


@pytest.mark.integration
def test_postgres_sync_rejects_cross_organization_assertion() -> None:
    store = _store()
    suffix = uuid4().hex
    bundle_id = str(uuid4())
    assertion = _assertion(
        bundle_id=bundle_id,
        logical_id=f"observation-{suffix}",
        value="Species A",
        organization_id=f"other-{suffix}",
        project_id=f"project-{suffix}",
    )
    result = store.apply_bundle(
        SyncBundle(
            bundle_id,
            f"org-{suffix}",
            "offline-tablet",
            "field-worker",
            _now(),
            (assertion,),
        )
    )
    assert result.inserted_assertion_ids == ()
    assert result.rejected_assertion_ids == (assertion.assertion_id,)

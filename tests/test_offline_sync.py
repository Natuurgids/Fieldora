from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from natureai_next.domain.synchronization import (
    AssertionState,
    PrimaryResolution,
    SyncAssertion,
    SyncBundle,
)
from natureai_next.server.offline_sync import OfflineSyncStore


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _assertion(
    *,
    bundle_id: str,
    logical_id: str,
    value: str,
    organization_id: str = "org-1",
    project_id: str = "project-1",
) -> SyncAssertion:
    return SyncAssertion(
        assertion_id=str(uuid4()),
        logical_record_id=logical_id,
        record_type="observation",
        organization_id=organization_id,
        project_id=project_id,
        author_identity_id="field-worker",
        device_id="tablet-1",
        created_at_utc=_now(),
        payload={"taxon": value},
        state=AssertionState.CURRENT,
        source_bundle_id=bundle_id,
        contract_id="contract-1",
        evidence_ids=("media-1",),
    )


def test_sqlite_sync_bundle_replay_is_idempotent(tmp_path: Path) -> None:
    store = OfflineSyncStore(tmp_path / "sync.sqlite3")
    bundle_id = str(uuid4())
    assertion = _assertion(bundle_id=bundle_id, logical_id="obs-1", value="Species A")
    bundle = SyncBundle(
        bundle_id,
        "org-1",
        "tablet-1",
        "field-worker",
        _now(),
        (assertion,),
    )

    first = store.apply_bundle(bundle)
    replay = store.apply_bundle(bundle)

    assert first.inserted_assertion_ids == (assertion.assertion_id,)
    assert replay.inserted_assertion_ids == ()
    assert replay.duplicate_assertion_ids == (assertion.assertion_id,)
    assert len(store.assertions("org-1", "observation", "obs-1")) == 1


def test_sqlite_sync_preserves_competing_scientific_assertions(tmp_path: Path) -> None:
    store = OfflineSyncStore(tmp_path / "sync.sqlite3")
    first_bundle = str(uuid4())
    second_bundle = str(uuid4())
    first = _assertion(
        bundle_id=first_bundle, logical_id="obs-1", value="Panthera onca"
    )
    second = replace(
        _assertion(
            bundle_id=second_bundle, logical_id="obs-1", value="Puma concolor"
        ),
        author_identity_id="field-worker-2",
        device_id="phone-2",
    )

    store.apply_bundle(
        SyncBundle(
            first_bundle,
            "org-1",
            "tablet-1",
            "field-worker",
            _now(),
            (first,),
        )
    )
    result = store.apply_bundle(
        SyncBundle(
            second_bundle,
            "org-1",
            "phone-2",
            "field-worker-2",
            _now(),
            (second,),
        )
    )

    assert result.conflict_record_ids == ("obs-1",)
    preserved = store.assertions("org-1", "observation", "obs-1")
    assert len(preserved) == 2
    assert {item.payload["taxon"] for item in preserved} == {
        "Panthera onca",
        "Puma concolor",
    }
    assert any(item.state is AssertionState.DISPUTED for item in preserved)
    assert store.presentation_assertion("org-1", "observation", "obs-1") is None


def test_sqlite_primary_resolution_changes_display_not_history(tmp_path: Path) -> None:
    store = OfflineSyncStore(tmp_path / "sync.sqlite3")
    assertion_ids: list[str] = []
    for device, value in (("tablet-1", "Species A"), ("tablet-2", "Species B")):
        bundle_id = str(uuid4())
        assertion = replace(
            _assertion(bundle_id=bundle_id, logical_id="obs-1", value=value),
            device_id=device,
        )
        store.apply_bundle(
            SyncBundle(
                bundle_id,
                "org-1",
                device,
                "field-worker",
                _now(),
                (assertion,),
            )
        )
        assertion_ids.append(assertion.assertion_id)

    first = PrimaryResolution(
        str(uuid4()),
        "obs-1",
        "observation",
        "org-1",
        "project-1",
        assertion_ids[0],
        "reviewer-1",
        _now(),
        "initial determination",
        "organization",
    )
    store.resolve_primary(first)
    assert store.presentation_assertion(
        "org-1", "observation", "obs-1"
    ).assertion_id == assertion_ids[0]

    second = PrimaryResolution(
        str(uuid4()),
        "obs-1",
        "observation",
        "org-1",
        "project-1",
        assertion_ids[1],
        "reviewer-2",
        _now(),
        "later evidence changed the primary presentation",
        "organization",
        first.resolution_id,
    )
    store.resolve_primary(second)

    assert store.presentation_assertion(
        "org-1", "observation", "obs-1"
    ).assertion_id == assertion_ids[1]
    assert len(store.assertions("org-1", "observation", "obs-1")) == 2

    with pytest.raises(ValueError, match="history conflict"):
        store.resolve_primary(
            replace(second, resolution_id=str(uuid4()), previous_resolution_id="")
        )


def test_sqlite_sync_rejects_cross_organization_assertion(tmp_path: Path) -> None:
    store = OfflineSyncStore(tmp_path / "sync.sqlite3")
    bundle_id = str(uuid4())
    assertion = _assertion(
        bundle_id=bundle_id,
        logical_id="obs-1",
        value="Species A",
        organization_id="other-org",
    )
    result = store.apply_bundle(
        SyncBundle(
            bundle_id,
            "org-1",
            "tablet-1",
            "field-worker",
            _now(),
            (assertion,),
        )
    )

    assert result.inserted_assertion_ids == ()
    assert result.rejected_assertion_ids == (assertion.assertion_id,)
    assert store.assertions("org-1", "observation", "obs-1") == ()

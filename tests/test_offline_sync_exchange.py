from __future__ import annotations

from pathlib import Path

import pytest

from natureai_next.domain.synchronization import (
    AssertionState,
    PrimaryResolution,
    SyncAssertion,
    SyncBundle,
)
from natureai_next.server.offline_sync import OfflineSyncStore


def _assertion(
    assertion_id: str,
    *,
    species: str,
    device_id: str,
    bundle_id: str,
) -> SyncAssertion:
    return SyncAssertion(
        assertion_id=assertion_id,
        logical_record_id="observation-1",
        record_type="observation",
        organization_id="org-1",
        project_id="project-1",
        author_identity_id=f"user-{device_id}",
        device_id=device_id,
        created_at_utc="2026-08-23T12:00:00+00:00",
        payload={"species": species, "count": 1},
        source_bundle_id=bundle_id,
        evidence_ids=("image-1",),
    )


def _bundle(bundle_id: str, assertion: SyncAssertion) -> SyncBundle:
    return SyncBundle(
        bundle_id=bundle_id,
        organization_id="org-1",
        source_device_id=assertion.device_id,
        source_identity_id=assertion.author_identity_id,
        created_at_utc="2026-08-23T13:00:00+00:00",
        assertions=(assertion,),
    )


def test_conflicting_offline_assertions_are_retained(tmp_path: Path) -> None:
    store = OfflineSyncStore(tmp_path / "sync.sqlite3")
    left = _assertion(
        "assertion-a",
        species="Panthera onca",
        device_id="device-a",
        bundle_id="bundle-a",
    )
    right = _assertion(
        "assertion-b",
        species="Puma concolor",
        device_id="device-b",
        bundle_id="bundle-b",
    )

    first = store.apply_bundle(_bundle("bundle-a", left))
    second = store.apply_bundle(_bundle("bundle-b", right))

    assert first.inserted_assertion_ids == ("assertion-a",)
    assert second.inserted_assertion_ids == ("assertion-b",)
    assert second.conflict_record_ids == ("observation-1",)

    assertions = store.assertions("org-1", "observation", "observation-1")
    assert {item.assertion_id for item in assertions} == {"assertion-a", "assertion-b"}
    assert {item.payload["species"] for item in assertions} == {
        "Panthera onca",
        "Puma concolor",
    }
    assert assertions[0].state is AssertionState.CURRENT
    assert assertions[1].state is AssertionState.DISPUTED
    assert store.presentation_assertion("org-1", "observation", "observation-1") is None


def test_resolution_selects_primary_without_deleting_alternative(tmp_path: Path) -> None:
    store = OfflineSyncStore(tmp_path / "sync.sqlite3")
    for bundle_id, assertion in (
        (
            "bundle-a",
            _assertion(
                "assertion-a",
                species="Panthera onca",
                device_id="device-a",
                bundle_id="bundle-a",
            ),
        ),
        (
            "bundle-b",
            _assertion(
                "assertion-b",
                species="Puma concolor",
                device_id="device-b",
                bundle_id="bundle-b",
            ),
        ),
    ):
        store.apply_bundle(_bundle(bundle_id, assertion))

    resolution = PrimaryResolution(
        resolution_id="resolution-1",
        logical_record_id="observation-1",
        record_type="observation",
        organization_id="org-1",
        project_id="project-1",
        primary_assertion_id="assertion-a",
        decided_by_identity_id="reviewer-1",
        decided_at_utc="2026-08-24T08:00:00+00:00",
        rationale="Expert review selected the jaguar determination.",
    )
    store.resolve_primary(resolution)

    primary = store.presentation_assertion("org-1", "observation", "observation-1")
    assert primary is not None
    assert primary.assertion_id == "assertion-a"
    assert len(store.assertions("org-1", "observation", "observation-1")) == 2


def test_resolution_changes_are_append_only_history(tmp_path: Path) -> None:
    store = OfflineSyncStore(tmp_path / "sync.sqlite3")
    for bundle_id, assertion in (
        (
            "bundle-a",
            _assertion(
                "assertion-a",
                species="Panthera onca",
                device_id="device-a",
                bundle_id="bundle-a",
            ),
        ),
        (
            "bundle-b",
            _assertion(
                "assertion-b",
                species="Puma concolor",
                device_id="device-b",
                bundle_id="bundle-b",
            ),
        ),
    ):
        store.apply_bundle(_bundle(bundle_id, assertion))

    first = PrimaryResolution(
        "resolution-1",
        "observation-1",
        "observation",
        "org-1",
        "project-1",
        "assertion-a",
        "reviewer-1",
        "2026-08-24T08:00:00+00:00",
        "Initial expert review.",
    )
    store.resolve_primary(first)

    second = PrimaryResolution(
        "resolution-2",
        "observation-1",
        "observation",
        "org-1",
        "project-1",
        "assertion-b",
        "reviewer-2",
        "2026-09-01T08:00:00+00:00",
        "Genetic evidence changed the presented determination.",
        previous_resolution_id="resolution-1",
    )
    store.resolve_primary(second)

    primary = store.presentation_assertion("org-1", "observation", "observation-1")
    assert primary is not None
    assert primary.assertion_id == "assertion-b"
    assert store.current_resolution("org-1", "observation", "observation-1") == second
    assert len(store.assertions("org-1", "observation", "observation-1")) == 2


def test_resolution_requires_current_history_head(tmp_path: Path) -> None:
    store = OfflineSyncStore(tmp_path / "sync.sqlite3")
    assertion = _assertion(
        "assertion-a",
        species="Panthera onca",
        device_id="device-a",
        bundle_id="bundle-a",
    )
    store.apply_bundle(_bundle("bundle-a", assertion))
    store.resolve_primary(
        PrimaryResolution(
            "resolution-1",
            "observation-1",
            "observation",
            "org-1",
            "project-1",
            "assertion-a",
            "reviewer-1",
            "2026-08-24T08:00:00+00:00",
            "Initial decision.",
        )
    )

    with pytest.raises(ValueError, match="resolution history conflict"):
        store.resolve_primary(
            PrimaryResolution(
                "resolution-2",
                "observation-1",
                "observation",
                "org-1",
                "project-1",
                "assertion-a",
                "reviewer-2",
                "2026-08-25T08:00:00+00:00",
                "Stale writer.",
                previous_resolution_id="",
            )
        )


def test_bundle_replay_is_idempotent(tmp_path: Path) -> None:
    store = OfflineSyncStore(tmp_path / "sync.sqlite3")
    assertion = _assertion(
        "assertion-a",
        species="Panthera onca",
        device_id="device-a",
        bundle_id="bundle-a",
    )
    bundle = _bundle("bundle-a", assertion)

    first = store.apply_bundle(bundle)
    replay = store.apply_bundle(bundle)

    assert first.inserted_assertion_ids == ("assertion-a",)
    assert replay.inserted_assertion_ids == ()
    assert replay.duplicate_assertion_ids == ("assertion-a",)
    assert len(store.assertions("org-1", "observation", "observation-1")) == 1


def test_cross_organization_assertion_is_rejected(tmp_path: Path) -> None:
    store = OfflineSyncStore(tmp_path / "sync.sqlite3")
    invalid = SyncAssertion(
        assertion_id="assertion-x",
        logical_record_id="observation-x",
        record_type="observation",
        organization_id="other-org",
        project_id="project-x",
        author_identity_id="user-x",
        device_id="device-x",
        created_at_utc="2026-08-23T12:00:00+00:00",
        payload={"species": "Unknown"},
        source_bundle_id="bundle-x",
    )
    result = store.apply_bundle(
        SyncBundle(
            bundle_id="bundle-x",
            organization_id="org-1",
            source_device_id="device-x",
            source_identity_id="user-x",
            created_at_utc="2026-08-23T13:00:00+00:00",
            assertions=(invalid,),
        )
    )

    assert result.rejected_assertion_ids == ("assertion-x",)
    assert store.assertions("org-1", "observation", "observation-x") == ()

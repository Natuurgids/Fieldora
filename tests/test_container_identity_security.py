from __future__ import annotations

import pytest

from scripts.verify_container_identity import certification_proof_digest, verify_container_identity


COMMIT = "1" * 40
DIGEST = "sha256:" + "a" * 64


def evidence() -> dict[str, str]:
    value = {
        "git_commit": COMMIT,
        "build_input_commit": COMMIT,
        "built_image_digest": DIGEST,
        "deployed_image_digest": DIGEST,
        "running_image_digest": DIGEST,
    }
    value["certification_proof_digest"] = certification_proof_digest(value)
    return value


def test_accepts_one_identity_from_git_through_running_container() -> None:
    verify_container_identity(evidence())


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("build_input_commit", "2" * 40),
        ("deployed_image_digest", "sha256:" + "b" * 64),
        ("running_image_digest", "sha256:" + "c" * 64),
    ],
)
def test_rejects_identity_chain_mismatch(field: str, replacement: str) -> None:
    value = evidence()
    value[field] = replacement
    value["certification_proof_digest"] = certification_proof_digest(value)
    with pytest.raises(ValueError):
        verify_container_identity(value)


def test_rejects_mutated_chain_with_stale_certification_proof() -> None:
    value = evidence()
    value["running_image_digest"] = "sha256:" + "d" * 64
    with pytest.raises(ValueError):
        verify_container_identity(value)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("git_commit", "main"),
        ("built_image_digest", "fieldora:latest"),
        ("certification_proof_digest", "sha256:not-a-digest"),
    ],
)
def test_rejects_mutable_or_malformed_identity(field: str, replacement: str) -> None:
    value = evidence()
    value[field] = replacement
    with pytest.raises(ValueError):
        verify_container_identity(value)


def test_rejects_missing_evidence() -> None:
    value = evidence()
    del value["running_image_digest"]
    with pytest.raises(ValueError):
        verify_container_identity(value)

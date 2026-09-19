"""Fail-closed verification for immutable container deployment identity evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Mapping

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_REQUIRED = (
    "git_commit",
    "build_input_commit",
    "built_image_digest",
    "deployed_image_digest",
    "running_image_digest",
    "certification_proof_digest",
)


def _text(evidence: Mapping[str, object], key: str) -> str:
    value = evidence.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"container identity evidence requires {key}")
    return value


def canonical_identity_payload(evidence: Mapping[str, object]) -> bytes:
    """Return the exact deployment chain covered by the certification proof."""
    payload = {
        "build_input_commit": _text(evidence, "build_input_commit"),
        "built_image_digest": _text(evidence, "built_image_digest"),
        "deployed_image_digest": _text(evidence, "deployed_image_digest"),
        "git_commit": _text(evidence, "git_commit"),
        "running_image_digest": _text(evidence, "running_image_digest"),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def certification_proof_digest(evidence: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(canonical_identity_payload(evidence)).hexdigest()


def verify_container_identity(evidence: Mapping[str, object]) -> None:
    """Require one immutable identity from source input through running container."""
    for key in _REQUIRED:
        _text(evidence, key)

    git_commit = _text(evidence, "git_commit")
    build_input_commit = _text(evidence, "build_input_commit")
    if not _GIT_SHA.fullmatch(git_commit) or not _GIT_SHA.fullmatch(build_input_commit):
        raise ValueError("git and build input commits must be lowercase 40-character Git SHAs")
    if git_commit != build_input_commit:
        raise ValueError("container build input does not match the certified Git commit")

    digests = tuple(
        _text(evidence, key)
        for key in ("built_image_digest", "deployed_image_digest", "running_image_digest")
    )
    if any(not _SHA256.fullmatch(value) for value in digests):
        raise ValueError("container image identities must be immutable sha256 digests")
    if len(set(digests)) != 1:
        raise ValueError("built, deployed, and running container digests do not match")

    proof = _text(evidence, "certification_proof_digest")
    if not _SHA256.fullmatch(proof):
        raise ValueError("certification proof must be a sha256 digest")
    expected = certification_proof_digest(evidence)
    if proof != expected:
        raise ValueError("container certification proof does not bind the identity chain")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args(argv)
    payload = json.loads(args.evidence.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("container identity evidence must be a JSON object")
    verify_container_identity(payload)
    print("container identity chain verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

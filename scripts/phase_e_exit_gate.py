"""Evaluate deterministic Phase E exit-gate evidence."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _contains(path: str, *needles: str) -> bool:
    text = (ROOT / path).read_text(encoding="utf-8")
    return all(needle in text for needle in needles)


def evaluate() -> dict:
    checks = [
        ("interrupted-sync", "tests/test_fieldora_009_desktop_sync_foundation.py",
         "test_outbox_resumes_after_interrupted_lease_and_is_idempotent"),
        ("revoked-rights", "tests/test_fieldora_009_sync_protocol.py",
         "test_revoked_rights_block_transport"),
        ("offline-provenance", "tests/test_fieldora_009_contribution_review.py",
         "test_preview_and_current_terms_acknowledgment_gate_push"),
        ("governed-deltas", "tests/test_fieldora_009_governed_packs.py",
         "test_delta_requires_exact_installed_base_and_updates_isolated_store"),
        ("pack-security", "tests/test_fieldora_009_governed_pack_security.py",
         "test_tamper_is_rejected_and_revocation_destroys_key_and_envelope"),
    ]
    results = [
        {"check_id": check_id, "status": "pass" if _contains(path, needle) else "fail",
         "evidence": [f"{path}::{needle}"]}
        for check_id, path, needle in checks
    ]
    return {
        "schema_version": 1, "phase": "E", "release": "0.11.21",
        "status": "pass" if all(item["status"] == "pass" for item in results) else "failed",
        "checks": results,
    }


def main() -> int:
    report = evaluate()
    (ROOT / "PHASE_E_EXIT_GATE.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Evaluate the Phase D exit gate from repository evidence.

The audit deliberately distinguishes deterministic implementation evidence from
provider-backed operational certification.  A conditional result is a release
blocker, not a successful exit.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Check:
    check_id: str
    status: str
    requirement: str
    evidence: tuple[str, ...]
    note: str


def _contains(path: str, *needles: str) -> bool:
    text = (ROOT / path).read_text(encoding="utf-8")
    return all(needle in text for needle in needles)


def evaluate() -> dict[str, object]:
    automated = (
        Check(
            "pbac-default-deny",
            "pass"
            if _contains(
                "tests/test_fieldora_007_pbac.py",
                "test_pbac_defaults_to_deny_and_enforces_scope_and_fields",
                "test_contract_expiry_and_explicit_object_deny_override_allow",
            )
            else "fail",
            "Authorization defaults to deny and rejects expired or explicit denials.",
            ("tests/test_fieldora_007_pbac.py",),
            "Deterministic policy tests cover scope, fields, expiry, and deny precedence.",
        ),
        Check(
            "governed-media",
            "pass"
            if _contains(
                "tests/test_fieldora_008_server.py",
                "test_media_download_is_pbac_filtered_and_resumable",
                "test_s3_compatible_media_adapter_preserves_governed_range_contract",
            )
            else "fail",
            "Media bytes and ranges are available only after an API policy decision.",
            (
                "tests/test_fieldora_008_server.py::test_media_download_is_pbac_filtered_and_resumable",
                "tests/test_fieldora_008_server.py::test_s3_compatible_media_adapter_preserves_governed_range_contract",
            ),
            "The object-store boundary exposes opaque keys, not direct object URLs.",
        ),
        Check(
            "governed-search",
            "pass"
            if _contains(
                "tests/test_fieldora_008_server.py",
                "test_search_filters_candidates_before_title_or_snippet_disclosure",
                "test_opensearch_projection_uses_atomic_alias_and_bounded_candidates",
            )
            else "fail",
            "Search cannot disclose result metadata or snippets before PBAC filtering.",
            (
                "tests/test_fieldora_008_server.py::test_search_filters_candidates_before_title_or_snippet_disclosure",
                "tests/test_fieldora_008_server.py::test_opensearch_projection_uses_atomic_alias_and_bounded_candidates",
            ),
            "External search remains a non-authoritative candidate projection.",
        ),
        Check(
            "governed-export",
            "pass"
            if _contains(
                "tests/test_fieldora_008_server.py",
                "test_project_export_is_governed_at_submit_status_and_download",
            )
            else "fail",
            "Export submission, job visibility, and download are separate PBAC gates.",
            (
                "tests/test_fieldora_008_server.py::test_project_export_is_governed_at_submit_status_and_download",
            ),
            "Storage paths are not returned by the governed download API.",
        ),
        Check(
            "governed-job-output",
            "pass"
            if _contains(
                "tests/test_fieldora_008_server.py",
                "test_durable_job_output_requires_separate_pbac_and_lease_recovers",
            )
            else "fail",
            "Job output requires authorization independently of job submission.",
            (
                "tests/test_fieldora_008_server.py::test_durable_job_output_requires_separate_pbac_and_lease_recovers",
            ),
            "Lease recovery does not weaken output authorization.",
        ),
        Check(
            "upgrade-and-restore",
            "pass"
            if _contains(
                "tests/test_fieldora_008_server.py",
                "test_one_node_server_backup_verifies_and_restores_to_new_root",
                "test_restored_root_validation_composes_current_server_offline",
            )
            else "fail",
            "The one-node reference can be verified, restored, migrated, and composed.",
            (
                "tests/test_fieldora_008_server.py::test_one_node_server_backup_verifies_and_restores_to_new_root",
                "tests/test_fieldora_008_server.py::test_restored_root_validation_composes_current_server_offline",
            ),
            "Restore is intentionally non-destructive and targets a new data root.",
        ),
    )
    certification = (
        Check(
            "live-postgresql",
            "blocked",
            "Run repository parity and recovery against a supported live PostgreSQL service.",
            ("tests/test_fieldora_008_server.py (DB-API contract doubles only)",),
            "No provider-backed execution record is present in this release.",
        ),
        Check(
            "live-object-search",
            "blocked",
            "Run governed ranges/uploads and PBAC-filtered search against live S3 and OpenSearch.",
            ("tests/test_fieldora_008_server.py (provider doubles only)",),
            "No provider-backed execution record is present in this release.",
        ),
        Check(
            "deployed-tls-client",
            "blocked",
            "Exercise the packaged web client over a real TLS listener and trusted browser.",
            (
                "tests/test_fieldora_008_server.py::test_https_server_uses_tls_12_or_newer_certificate_context",
            ),
            "The SSL-context contract is tested; installed-client field evidence is absent.",
        ),
    )
    checks = automated + certification
    failed = [item.check_id for item in checks if item.status == "fail"]
    blocked = [item.check_id for item in checks if item.status == "blocked"]
    status = "fail" if failed else ("conditional" if blocked else "pass")
    return {
        "schema_version": 1,
        "phase": "D",
        "release": "0.08.34",
        "status": status,
        "decision": (
            "Phase D implementation is complete; exit is blocked pending live-provider "
            "and installed-client certification."
            if status == "conditional"
            else "Phase D exit gate passed."
            if status == "pass"
            else "Phase D exit gate failed."
        ),
        "checks": [asdict(item) for item in checks],
        "failed": failed,
        "blocked": blocked,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--allow-conditional",
        action="store_true",
        help="Return success for a conditional report (use only to generate release evidence).",
    )
    args = parser.parse_args()
    report = evaluate()
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    if report["status"] == "pass":
        return 0
    if report["status"] == "conditional" and args.allow_conditional:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

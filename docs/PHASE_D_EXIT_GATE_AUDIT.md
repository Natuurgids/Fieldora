# Phase D Exit-Gate Audit

**Release:** Fieldora 0.08.34  
**Decision:** Conditional — implementation complete, operational certification blocked

Phase D's implementation gate is supported by automated evidence. The API applies
PBAC before disclosing governed media, search metadata or snippets, export state or
payloads, and durable job output. Default-deny, expired-contract, cross-scope, restore,
and revision-conflict behavior are also covered.

The formal phase exit is **not yet passed**. This repository contains deterministic
adapter tests, but no recorded acceptance run against live PostgreSQL,
S3-compatible storage, OpenSearch, or an installed browser client using a real TLS
endpoint. Treating mocks as production certification would overstate readiness.

## Evidence matrix

| Gate | Result | Automated evidence |
|---|---|---|
| Default deny and contract expiry | Pass | `tests/test_fieldora_007_pbac.py` |
| Governed media and byte ranges | Pass | `test_media_download_is_pbac_filtered_and_resumable` |
| PBAC-filtered search | Pass | `test_search_filters_candidates_before_title_or_snippet_disclosure` |
| Export submit/status/download separation | Pass | `test_project_export_is_governed_at_submit_status_and_download` |
| Independent job-output authorization | Pass | `test_durable_job_output_requires_separate_pbac_and_lease_recovers` |
| Verified one-node restore and upgrade | Pass | one-node recovery and restored-root tests |
| Live PostgreSQL certification | Blocked | No provider-backed execution record |
| Live S3 and OpenSearch certification | Blocked | No provider-backed execution record |
| Packaged client over deployed TLS | Blocked | No installed-client execution record |

## Closure procedure

1. Provision disposable supported PostgreSQL, S3-compatible, and OpenSearch services.
2. Run the same cross-tenant and expired-contract scenarios through the packaged API
   and web client, including ranges, search, export, and job output.
3. Perform backup, restore-to-new-root, migration, and readiness certification using
   the provider-backed configuration.
4. Attach sanitized command output, versions, configuration profile, and checksums to
   this audit.
5. Change blocked checks only when their recorded evidence is reviewable, then run
   `python scripts/phase_d_exit_gate.py`. A genuine pass returns zero; conditional or
   failed results return non-zero.

The machine-readable `PHASE_D_EXIT_GATE.json` is generated from the checker and is the
release's authoritative gate snapshot.

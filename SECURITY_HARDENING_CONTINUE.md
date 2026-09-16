# Fieldora Security Hardening — Continuation Instructions

**Branch:** `security/native-update-trust-hardening`  
**Authoritative base audited:** `54abf55aa0c5124e1c1e7c46db14814c64a4e37c`  
**Tracking PR:** #15 — Harden native update trust and PBAC boundaries  
**Detailed requirements:** `docs/security/native-update-trust-hardening.md`

## Purpose and mandatory continuation procedure

This file is the durable entry point for continuing the Fieldora security remediation. When the user asks to continue, do not require the previous audit chat.

1. Confirm `Natuurgids/Fieldora`, branch `security/native-update-trust-hardening`.
2. Read this file completely, then read `docs/security/native-update-trust-hardening.md` completely.
3. Read PR #15 status, changed files, review comments/threads, checks/workflows, and current head SHA.
4. Compare the branch with current `main` before changes; never silently overwrite newer mainline security work.
5. Inspect current implementation/tests; repository state is authoritative.
6. Work findings in dependency order. For each finding: inspect exact code, implement the smallest coherent fail-closed fix, add/update tests and certification, inspect available checks, update this ledger, and commit with a security-boundary-specific message.
7. Keep PR #15 draft until every mandatory acceptance gate is demonstrated. Never weaken a failing gate to make tests pass.
8. Before completion, re-audit end-to-end and distinguish demonstrated, implied, and unresolved properties.

## Security model — never conflate these

Analyze separately: **integrity** (bytes/digests), **authenticity/provenance** (trusted publisher cryptographically authorized the release), **authorization** (the acting subject is permitted), and **deployment binding** (audited/built artifact is immutably bound to deployed/running artifact).

SHA-256 is not publisher authenticity. A Git commit SHA is not OCI/runtime identity. PBAC is not release provenance. Serialized `signature_verified=true` / `provenance_verified=true` is not cryptographic verification. Do not claim RCE/arbitrary substitution unless every required attacker-controlled trust boundary is demonstrated. Preserve fail-closed behavior.

## Remediation requirements and order

### F-01 — Native release authenticity/provenance — HIGH

Use a canonical signed native release index with detached Ed25519 verification against an administrator-controlled trust anchor that is not supplied by the user-selected update source. Signed content must bind format/version, product, channel, version, minimum supported version, package basename, SHA-256, byte size, release identity/digest, and Security Install evidence digest. Reject unsigned/malformed/untrusted/path-traversal/hash-size/evidence mismatches. `OfflineUpdateService.check()` authenticates before consuming security-sensitive metadata. Security Install derives authenticity from verification output, never media booleans.

Primary code: `application/updates.py`, `application/update_trust.py`, `application/security_install.py`, `domain/security_install.py`, release tooling.

### F-02 — Native updater PBAC provisioning — HIGH

Clean bootstrap provisions enabled service identity `fieldora-native-updater` with only effective permission action `install`, resource type `security_install_release`, purpose `security_install`. Provisioning is idempotent; no wildcard updater grant. Tests cover clean install, unrelated subject denial, and missing/disabled updater denial.

### F-03 — Local PBAC administration authorization — HIGH

Access-control mutations carry authenticated actor context and are authorized at the application/service boundary before writes. Cover organization, identity, group membership, role assignment, contract, and policy mutation with narrowly scoped administration permissions. Qt is read-only/fail-closed without an authorized actor. Tests include prevention of self-provisioning an unauthorized Security Install grant.

Primary code: `application/access_control.py`, `ui/qt/access_control.py`, desktop actor/session composition, server administration patterns.

### F-04 — Config-root / authorization-context binding — MEDIUM

Carry the resolved application/config root explicitly desktop -> stage -> handoff -> updater. Updater PBAC DB, history, and update state resolve from that explicit root and cannot be redirected by inherited `APERTURE_DATA_ROOT` / `NATUREAI_DATA_ROOT`. Test non-default roots and conflicting environment roots.

Primary code: `bootstrap/paths.py`, `application/native_handoff.py`, `bootstrap/native_updater.py`, desktop composition.

### F-05 — Authenticated anti-rollback — MEDIUM

Version and minimum-supported-version remain monotonic checks but are authenticated signed fields. Tests prove modifying either invalidates authenticity.

### F-06 — Immutable deployment/runtime binding — MEDIUM

Establish `Git commit -> build inputs -> OCI digest -> deployed digest -> running digest -> certification proof`. Never use mutable image tag alone as runtime identity. Certification compares intended built/deployed immutable identity with running workload identity; functional health checks are not cryptographic binding. Re-inspect current deployment code before changes because it may evolve independently.

### F-07 — Security certification coverage — DEFENSE IN DEPTH

CI/certification must demonstrate: valid signed update accepted; unsigned/untrusted/tampered metadata rejected; package hash/size and Security Install evidence mismatches rejected; valid artifact without PBAC denied; exact updater identity/policy provisioned; unrelated subject denied; local PBAC mutation without authorized actor denied; explicit config root preserved; inherited environment cannot redirect PBAC DB; immutable runtime digest recorded/checked.

## Integration rules

This branch owns the concrete remediation. PR #10 / `deployment/docker-layout-stage` is stale/superseded and must not be resurrected. PR #13 / `feat/platform-bootstrap-contract` may contain compatible platform/supply-chain contract work, but re-evaluate it against current `main` before reuse. If main advances, integrate carefully and re-run all security gates.

## Progress ledger

Status values: `NOT STARTED`, `IN PROGRESS`, `IMPLEMENTED — TESTS PENDING`, `CERTIFIED`, `BLOCKED`.

| Finding | Status | Completion evidence |
| --- | --- | --- |
| F-01 Native release authenticity/provenance | IN PROGRESS | Ed25519 signed-index verification, strict signed-field validation, administrator trust-anchor loading, package hash/size and Security Install evidence binding, detached-updater re-verification, cryptographically derived Security Install release context, and signed-index tooling are implemented. `ApplicationPaths` defines the administrator trust anchor at the explicit application root. Serialized provenance booleans are non-authoritative. Positive/negative tests exist and are included in the focused hardening workflow. Remaining: desktop trust-anchor composition and successful focused CI evidence. |
| F-02 Native updater PBAC provisioning | IMPLEMENTED — TESTS PENDING | Migration 7 provisions enabled `fieldora-native-updater`, removes inherited/legacy updater authority, and leaves one direct allow policy limited to `install` / `security_install_release` / `security_install`. Tests cover clean install, idempotency, exact policy, unrelated-subject denial, missing/disabled updater denial, out-of-scope requests, and legacy/inherited grant cleanup. Tests are included in the focused hardening workflow; a successful run is still required. |
| F-03 Local PBAC administration authorization | NOT STARTED | Application-layer actor authorization and fail-closed Qt mutation controls required. |
| F-04 Config-root binding | IN PROGRESS | Handoff carries explicit config/trust roots; updater requires explicit roots, resolves PBAC/history from config root, rejects request/root mismatch, and re-verifies signed staged index. `ApplicationPaths` binds `updates_dir` and `update_trust_anchor_file` to the same explicit application root, with a conflicting-environment test. Updater tests prove inherited `APERTURE_DATA_ROOT` / `NATUREAI_DATA_ROOT` cannot redirect authenticated-update PBAC. These tests are included in the focused workflow. Remaining: desktop composition must pass the resolved root/trust anchor and root update settings/staging/history consistently. |
| F-05 Authenticated anti-rollback | IMPLEMENTED — TESTS PENDING | Version/minimum version are consumed only after signature verification; tamper-negative tests exist and are included in the focused workflow. Successful focused CI evidence is required. |
| F-06 Immutable deployment/runtime binding | NOT STARTED | Implementation required. |
| F-07 Security certification coverage | IN PROGRESS | `.github/workflows/security-hardening-certification.yml` now provides a dedicated PR/manual gate for native authenticity, Security Install provenance/PBAC, updater provisioning, handoff roots, conflicting inherited environment roots, and application update-path tests. No run was visible immediately after workflow creation, so it is not yet certification evidence. Desktop composition, local PBAC administration, and immutable runtime-digest gates remain. |

## Current continuation note — 2026-09-16

PR #15 remains open and draft. At head `54a6208d12a2dcfdb0a32f2f90a275abc77353a0`, the branch was 30 commits ahead of and 0 behind `main`, whose head remains audited commit `54abf55aa0c5124e1c1e7c46db14814c64a4e37c`. Four broad PR workflows passed at `54a6208d`, but they do not exercise the dedicated hardening test set. Commit `54d452b05dab834df8876e664487a6f575b86770` adds the focused native security hardening certification workflow. No workflow run was visible immediately after that commit, so do not mark any focused gate certified until a completed successful run is observed.

Highest-priority unresolved integration remains F-01/F-04 desktop composition. `MainWindow` still constructs `OfflineUpdateService()` without the required trust-anchor argument, stores update settings/staging/history under the library/session root, and launches the updater without explicit config/trust roots. `run_desktop()` and its bootstrap call also do not carry those values. Continue by wiring `container.paths.local_root`, `container.paths.updates_dir`, and `container.paths.update_trust_anchor_file` through bootstrap -> `run_desktop` -> `MainWindow`, moving update state to the application `updates_dir`, and passing the same roots into `augment_request` / `HelperLaunch`. Large-file GitHub edits require complete-file replacement: do not overwrite `ui/qt/application.py` or `bootstrap/cli.py` from partial fetches.

## Completion definition

Do not mark complete or ready for merge until: F-01 through F-07 are `CERTIFIED` (or an approved non-applicable decision is documented); positive and fail-closed negative tests pass; no authenticity decision trusts serialized verification booleans; native install requires both authenticated provenance and independent PBAC; local PBAC mutation requires an authorized actor; desktop/updater share one explicit application root; container certification checks immutable runtime identity; unrelated security gates remain passing; PR #15 is re-reviewed after final end-to-end audit; and this ledger reflects actual repository state.

## Instruction to the next chat

**Start here. Do not ask the user to reproduce the prior audit.** Read this file, the detailed hardening document, PR #15, current branch diff, and current `main`; then continue the first non-certified phase and maintain this ledger.

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

### F-02 — Native updater PBAC provisioning — HIGH
Clean bootstrap provisions enabled service identity `fieldora-native-updater` with only effective permission action `install`, resource type `security_install_release`, purpose `security_install`. Provisioning is idempotent; no wildcard updater grant.

### F-03 — Local PBAC administration authorization — HIGH
Access-control mutations carry authenticated actor context and are authorized at the application/service boundary before writes. Cover organization, identity, group membership, role assignment, contract, and policy mutation with narrowly scoped administration permissions. Qt is read-only/fail-closed without an authorized actor. Tests include prevention of self-provisioning an unauthorized Security Install grant.

### F-04 — Config-root / authorization-context binding — MEDIUM
Carry the resolved application/config root explicitly desktop -> stage -> handoff -> updater. Updater PBAC DB, history, and update state resolve from that explicit root and cannot be redirected by inherited `APERTURE_DATA_ROOT` / `NATUREAI_DATA_ROOT`.

### F-05 — Authenticated anti-rollback — MEDIUM
Version and minimum-supported-version remain monotonic checks but are authenticated signed fields. Tests prove modifying either invalidates authenticity.

### F-06 — Immutable deployment/runtime binding — MEDIUM
Establish `Git commit -> build inputs -> OCI digest -> deployed digest -> running digest -> certification proof`. Never use mutable image tag alone as runtime identity.

### F-07 — Security certification coverage — DEFENSE IN DEPTH
CI/certification must demonstrate all positive and fail-closed boundaries above, including local PBAC mutation without an authorized actor, explicit config-root preservation, and immutable runtime digest verification.

## Integration rules

This branch owns the concrete remediation. PR #10 / `deployment/docker-layout-stage` is stale/superseded and must not be resurrected. PR #13 / `feat/platform-bootstrap-contract` may contain compatible platform/supply-chain contract work, but re-evaluate it against current `main` before reuse.

## Progress ledger

Status values: `NOT STARTED`, `IN PROGRESS`, `IMPLEMENTED — TESTS PENDING`, `CERTIFIED`, `BLOCKED`.

| Finding | Status | Completion evidence |
| --- | --- | --- |
| F-01 Native release authenticity/provenance | IN PROGRESS | Ed25519 signed-index verification, strict signed-field validation, administrator trust-anchor loading, package hash/size and Security Install evidence binding, detached-updater re-verification, cryptographically derived Security Install release context, and signed-index tooling are implemented. Focused hardening CI passed at `b1260dc9048ddd1154e39e561c94a5e4c7ac945f`. Remaining: desktop trust-anchor composition. |
| F-02 Native updater PBAC provisioning | CERTIFIED | Migration 7 provisions the exact updater identity and removes inherited/legacy updater authority. Dedicated hardening workflow run 35072409315 passed 49 focused tests at `b1260dc9048ddd1154e39e561c94a5e4c7ac945f`. |
| F-03 Local PBAC administration authorization | IN PROGRESS | `AccessAdministrationService` requires authenticated `actor_id` plus PBAC `administer` / `access_control_administration` authorization before organization, identity, group-membership, role-assignment, contract, or policy writes. Contract proposal/approval identities are bound to the actor. Focused hardening workflow run 35073093431 succeeded at `87fd75a03a76d56f807576e7b5ecee9c109b6e08`, including the no-actor, unauthorized-actor, authorized mutation, and Security Install self-provisioning tests. Remaining: wire authenticated desktop actor context and make Qt explicitly read-only without authorized administration. |
| F-04 Config-root binding | IN PROGRESS | Handoff/updater use explicit config/trust roots and focused CI proves inherited root variables cannot redirect updater PBAC. Remaining: desktop composition must pass root/trust anchor and root update settings/staging/history consistently. |
| F-05 Authenticated anti-rollback | CERTIFIED | Dedicated hardening workflow run 35072409315 exercised signed version/minimum-version tamper negatives successfully. |
| F-06 Immutable deployment/runtime binding | NOT STARTED | Implementation required. |
| F-07 Security certification coverage | IN PROGRESS | Dedicated hardening workflow run 35073093431 succeeded with the F-03 actor tests included. At that same head the WEB-030 Project-owner gate failed because its test fixture still performed setup through unauthenticated `AccessAdministrationService`; commit `971758d6ebe1f48ad2db6496ce08ade520d92967` changes that fixture to bootstrap a narrowly authorized test administrator instead of weakening the production gate. Re-certification of WEB-030 at the repaired head is pending. Desktop composition, Qt actor/read-only composition, and immutable runtime-digest gates remain. |

## Current continuation note — 2026-09-16

PR #15 remains open and draft with no review comments, review threads, or submitted reviews. `main` remains audited commit `54abf55aa0c5124e1c1e7c46db14814c64a4e37c`. Dedicated native-security workflow run 35073093431 completed successfully at head `87fd75a03a76d56f807576e7b5ecee9c109b6e08`, demonstrating the new F-03 application-layer actor checks. The Qt, browser multi-import, facility-actions, administration-actions, and WEB-060 workflows also succeeded at that head. WEB-030 failed only because its legacy test setup instantiated `AccessAdministrationService` without actor context; the failure was the intended new fail-closed exception, not a bypass. Commit `971758d6ebe1f48ad2db6496ce08ade520d92967` repairs the fixture by provisioning a narrowly scoped test administrator before exercising the existing Project-owner contract. No workflow run was visible immediately after that repair, so the unrelated regression is not yet re-certified.

Highest-priority unresolved integration remains desktop composition across F-01/F-03/F-04. `MainWindow` still constructs `OfflineUpdateService()` without the required trust-anchor argument, keeps update state under the library root, launches the updater without explicit config/trust roots, and constructs access administration without authenticated actor context while rediscovering application paths from environment. Continue by wiring the already-resolved `container.paths` and authenticated desktop identity through bootstrap -> `run_desktop` -> `MainWindow`, and make Access & Contracts read-only when that actor lacks administration authority. Large-file GitHub edits require complete-file replacement: do not overwrite `ui/qt/application.py` or `bootstrap/cli.py` from partial fetches.

## Completion definition

Do not mark complete or ready for merge until F-01 through F-07 are certified (or an approved non-applicable decision is documented), native install requires both authenticated provenance and PBAC, local PBAC mutation requires authorized actor context, desktop/updater share one explicit application root, immutable runtime identity is certified, unrelated gates pass, and this ledger reflects repository state.

## Instruction to the next chat

**Start here. Do not ask the user to reproduce the prior audit.** Read this file, the detailed hardening document, PR #15, current branch diff, and current `main`; then continue the first non-certified phase and maintain this ledger.

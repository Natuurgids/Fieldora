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
| F-02 Native updater PBAC provisioning | CERTIFIED | Historical Migration 7 is preserved byte-for-byte because the migration runner enforces immutable SQL checksums. Migration 8 now removes inherited/legacy updater roles, groups, policies and identity attributes while preserving the exact `fieldora-native-updater` Security Install permission. Upgrade regression coverage pins the historical Migration 7 checksum, applies the old state, introduces excess authority, upgrades through Migration 8, and verifies isolation. Dedicated hardening workflow run 35089520417 succeeded at `e2c1bcf9fbbc0e2885834d16d9e46cf313bc741d`. |
| F-03 Local PBAC administration authorization | IN PROGRESS | `AccessAdministrationService` requires authenticated `actor_id` plus PBAC `administer` / `access_control_administration` authorization before organization, identity, group-membership, role-assignment, contract, or policy writes. Contract proposal/approval identities are bound to the actor. Focused hardening workflow run 35073093431 succeeded at `87fd75a03a76d56f807576e7b5ecee9c109b6e08`. WEB-030 production owner-grant propagation is now certified: run 35098533519 succeeded at `b582daaf149a6dff338d9f064ba19cfbd4126b02`, using actor-bound `AccessAdministrationService(..., actor_id=identity_id)` plus the fixed `grant_project_owner_workspace()` seam. Remaining: desktop authenticated actor composition and Qt read-only/fail-closed behavior. |
| F-04 Config-root binding | IN PROGRESS | Handoff/updater use explicit config/trust roots and focused CI proves inherited root variables cannot redirect updater PBAC. Remaining: desktop composition must pass root/trust anchor and root update settings/staging/history consistently. |
| F-05 Authenticated anti-rollback | CERTIFIED | Dedicated hardening workflow run 35072409315 exercised signed version/minimum-version tamper negatives successfully. |
| F-06 Immutable deployment/runtime binding | NOT STARTED | Implementation required. |
| F-07 Security certification coverage | IN PROGRESS | Native hardening and WEB-030 are green at `b582daaf` (runs 35098532643 and 35098533519). The same head exposed a separate media-identity gate failure because its lightweight `_AccessRepository` test double no longer implemented the authenticated owner-grant repository contract; production WEB-030 remained green. Commit `f40e9628daa6cdb7d6a4749e895b8512fb855cdb` updates only that test double with identity/policy/audit repository behavior rather than weakening authorization. At the last check, WEB-030 run 35103348388 and native hardening run 35103348462 were green on `f40e9628`; media-identity run 35103348287 was still in progress. Desktop composition, Qt actor/read-only composition, and immutable runtime-digest gates remain. |

## Current continuation note — 2026-09-16

PR #15 remains open and draft with no comments, review threads, or submitted reviews. `main` remains `54abf55aa0c5124e1c1e7c46db14814c64a4e37c`; the branch remained 0 commits behind main when rechecked before the first change in this continuation.

The mandatory handoff point `b582daaf149a6dff338d9f064ba19cfbd4126b02` is now inspected and WEB-030 is certified. Workflow run 35098533519 completed successfully, including the creator immediate Project authority step. Native hardening run 35098532643 also succeeded. The production browser path is actor-bound and calls the narrow `grant_project_owner_workspace()` operation; the previous ledger statement that it still used unauthenticated general `create_policy()` was stale and is corrected here.

One unrelated gate at `b582daaf` failed: media-identity run 35098533649. Its only failure was `tests/test_browser_functionality_api.py::test_project_creator_receives_project_scoped_workspace_permission`, where the test-only `_AccessRepository` lacked `identity()` after the owner seam was correctly hardened. Commit `f40e9628daa6cdb7d6a4749e895b8512fb855cdb` repaired the test double by supplying the authenticated identity, the pre-existing project-create authorization needed by the narrow seam, and the repository methods used by `PolicyDecisionService`. It did not bypass or relax the service-layer authorization. On the first follow-up check, WEB-030 run 35103348388 and native hardening run 35103348462 were green; media-identity run 35103348287 and several unrelated workflows were still running. Re-check all of those runs before relying on the new head as fully green.

The updater migration history is upgrade-safe. `MigrationRunner` rejects checksum changes for already-applied migrations, so Migration 7 is preserved at its historical checksum and Migration 8 carries cleanup/isolation. Do not edit either migration in place; future changes require a new migration number.

Highest-priority unresolved integration is desktop composition across F-01/F-03/F-04. Inspection confirms `MainWindow` still constructs `OfflineUpdateService()` without its administrator trust-anchor argument, derives update settings/staging/history from `session_path.parent`, launches handoff without explicit config/trust roots, and calls `resolve_application_paths()` inside the Qt composition for subsystem databases. It also constructs `AccessAdministrationService` without actor context. `run_desktop` does have an actual authenticated local-login identity (`login.profile["username"]`); use that authenticated session identity rather than inventing an OS/library identity. Continue by wiring the already-resolved `container.paths` and authenticated desktop identity through bootstrap -> `run_desktop` -> `MainWindow`, and make Access & Contracts read-only when that actor lacks administration authority. Large-file GitHub edits require complete-file replacement: do not overwrite `ui/qt/application.py` or `bootstrap/cli.py` from partial fetches.

## Completion definition

Do not mark complete or ready for merge until F-01 through F-07 are certified (or an approved non-applicable decision is documented), native install requires both authenticated provenance and PBAC, local PBAC mutation requires authorized actor context, desktop/updater share one explicit application root, immutable runtime identity is certified, unrelated gates pass, and this ledger reflects repository state.

## Instruction to the next chat

**Start here. Do not ask the user to reproduce the prior audit.** Read this file, the detailed hardening document, PR #15, current branch diff, and current `main`; then continue the first non-certified phase and maintain this ledger.

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

### F-03 — Local PBAC admin authorization — HIGH
Access-control mutations carry authenticated actor context and are authorized at the application/service boundary before writes. Cover organization, identity, group membership, role assignment, contract, and policy mutation with narrowly scoped administration permissions. Qt is read-only/fail-closed without an authorized actor.

### F-04 — Config-root / authorization-context binding — MEDIUM
Carry the resolved application/config root explicitly desktop -> stage -> handoff -> updater. Updater PBAC DB, history, and update state resolve from that explicit root. Do not independently rediscover the root from inherited environment variables after handoff.

### F-05 — Authenticated anti-rollback — MEDIUM
Version and `minimum_supported_version` remain monotonic checks, but both must be inside the authenticated native-release manifest. Add tests proving that modifying either field invalidates the signature.

### F-06 — Deployment identity
Container release/runtime evidence should bind:

`Git commit -> build input -> OCI digest -> deployed digest -> running container digest -> certification proof`.

Functional health checks remain necessary but are not a substitute for immutable artifact identity.

## Certification gates

The implementation is complete only when CI demonstrates all of the following:

- valid signed native update is accepted;
- unsigned index is rejected;
- signature made by an untrusted key is rejected;
- tampered version, minimum version, package hash, package size, release digest, or Security Install evidence is rejected;
- valid package with invalid/missing PBAC authorization is rejected;
- clean install provisions the exact updater identity and least-privilege allow policy;
- unrelated subjects cannot install a Security Install release;
- local PBAC mutation without authorized actor context is rejected;
- explicit non-default config root is preserved across detached updater handoff;
- updater cannot select a different PBAC database through inherited root environment variables;
- container certification records and verifies the immutable running image digest.

## Branch integration

This branch owns the security implementation. It should not be folded into stale deployment-layout staging work.

`feat/platform-bootstrap-contract` has useful overlap at the platform/supply-chain contract layer and should be rebased onto current `main`; its platform manifest work can remain separate. Native update authenticity, updater PBAC provisioning, and local PBAC authorization must be implemented here (or cherry-picked from here) so the trust-boundary changes remain independently reviewable.

## Progress ledger

Status values: `NOT STARTED`, `IN PROGRESS`, `IMPLEMENTED — TESTS PENDING`, `CERTIFIED`, `BLOCKED`.

| Finding | Status | Completion evidence |
| --- | --- | --- |
| F-01 Native release authenticity/provenance | CERTIFIED | Ed25519 signed-index verification, strict signed-field validation, administrator trust-anchor loading, package hash/size and Security Install evidence binding, detached-updater re-verification, cryptographically derived Security Install release context, and signed-index tooling are implemented. Desktop composition constructs `OfflineUpdateService` with `application_paths.update_trust_anchor_file`. At cleaned head `cc752abb93fe081d448e592a672459158fa2e06d`, native hardening run 35145227266 and Qt run 35145227421 succeeded. |
| F-02 Native updater PBAC provisioning | CERTIFIED | Historical Migration 7 remains checksum-stable and Migration 8 removes inherited/legacy updater authority while preserving exact `fieldora-native-updater` Security Install permission. Upgrade regression coverage is certified; cleaned-head native hardening run 35145227266 also succeeded. |
| F-03 Local PBAC administration authorization | CERTIFIED | `AccessAdministrationService` requires authenticated `actor_id` plus PBAC administration authorization before writes. Desktop login captures a non-empty authenticated actor and passes it explicitly through `run_desktop` to `MainWindow` and `AccessAdministrationService`; Qt remains fail-closed/read-only without authorization. Cleaned-head native hardening run 35145227266 and GUI-enabled Qt run 35145227421 succeeded. |
| F-04 Config-root binding | CERTIFIED | Bootstrap passes resolved `container.paths` into desktop composition. Update settings, staging, history, trust anchor and security-sensitive subsystem paths derive from explicit `ApplicationPaths`; updater handoff carries the explicit local config root and trust anchor. Focused tests prove inherited root variables cannot redirect updater PBAC. Cleaned-head native hardening run 35145227266 and Qt run 35145227421 succeeded. |
| F-05 Authenticated anti-rollback | CERTIFIED | Signed version/minimum-version tamper negatives are covered and cleaned-head native hardening run 35145227266 succeeded. |
| F-06 Immutable deployment/runtime binding | CERTIFIED | `scripts/verify_container_identity.py` fail-closes unless Git commit equals build input and built/deployed/running identities are the same immutable `sha256:` digest, with certification proof binding the chain. Cleaned-head container identity run 35145227136 passed exact PR-head checkout verification, focused verifier tests, OCI build/publish/deploy/inspection, evidence verification and artifact upload. This demonstrates the CI deployment identity chain; external deployments require an equivalent gate. |
| F-07 Security certification coverage | CERTIFIED | At cleaned implementation head `cc752abb93fe081d448e592a672459158fa2e06d`, all 17 observed PR workflow runs completed successfully. Native hardening run 35145227266 passed its security-boundary job with 62 passed and 2 GUI-only tests skipped because PySide6 is absent from that job; separate GUI-enabled Qt run 35145227421 passed. Native container identity run 35145227136 passed. PR comments, submitted reviews and review threads were empty at the final re-check. |

## Current continuation note — 2026-09-17

PR #15 is open, mergeable, and draft at cleaned implementation head `cc752abb93fe081d448e592a672459158fa2e06d`. `main` remains `54abf55aa0c5124e1c1e7c46db14814c64a4e37c`; the branch is 69 commits ahead and 0 behind main. The PR has no conversation comments, submitted reviews, or review threads.

The desktop composition gap is closed. `run_desktop` receives the resolved application paths from bootstrap, captures the authenticated local-login actor, and passes both explicitly into `MainWindow`. Update trust, settings, staging and history use the resolved application update root; PBAC administration receives explicit actor context; detached updater handoff receives the explicit config root and trust anchor. No security-sensitive desktop update/PBAC root needs to be rediscovered from inherited environment variables.

All 17 observed PR workflows for `cc752abb93fe081d448e592a672459158fa2e06d` completed successfully, including native hardening, Qt certification and immutable container identity. Native hardening run 35145227266 reported 62 passed and 2 skipped; the skipped cases require PySide6, while the separate GUI-enabled Qt certification run 35145227421 completed successfully. Native container identity run 35145227136 completed successfully with exact-head verification and immutable OCI identity certification.

F-01 through F-07 are certified against the repository and CI evidence above. Before merge, re-check that the PR head has not moved, `main` has not advanced, required checks remain successful, and no new review/comment findings exist. If any condition changes, certification is stale until revalidated.

## Completion definition

Do not mark complete or ready for merge until F-01 through F-07 are certified (or an approved non-applicable decision is documented), native install requires both authenticated provenance and PBAC, local PBAC mutation requires authorized actor context, desktop/updater share one explicit application root, immutable runtime identity is certified, unrelated gates pass, and this ledger reflects repository state.

## Instruction to the next chat

**Start here. Do not ask the user to reproduce the prior audit.** Read this file, the detailed hardening document, PR #15, current branch diff, and current `main`; then revalidate certification against the current head before further mutation or merge.
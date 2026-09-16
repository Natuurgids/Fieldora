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
| F-01 Native release authenticity/provenance | IN PROGRESS | Ed25519 signed-index verification, strict signed-field validation, administrator trust-anchor loading, package hash/size and Security Install evidence binding, detached-updater re-verification, cryptographically derived Security Install release context, and signed-index tooling are implemented. Focused hardening CI passed at `b1260dc9048ddd1154e39e561c94a5e4c7ac945f`. Remaining: desktop trust-anchor composition. |
| F-02 Native updater PBAC provisioning | CERTIFIED | Historical Migration 7 is preserved byte-for-byte because the migration runner enforces immutable SQL checksums. Migration 8 removes inherited/legacy updater roles, groups, policies and identity attributes while preserving the exact `fieldora-native-updater` Security Install permission. Upgrade regression coverage pins the historical Migration 7 checksum, applies the old state, introduces excess authority, upgrades through Migration 8, and verifies isolation. Dedicated hardening workflow run 35089520417 succeeded at `e2c1bcf9fbbc0e2885834d16d9e46cf313bc741d`. |
| F-03 Local PBAC administration authorization | IN PROGRESS | `AccessAdministrationService` requires authenticated `actor_id` plus PBAC `administer` / `access_control_administration` authorization before organization, identity, group-membership, role-assignment, contract, or policy writes. Contract proposal/approval identities are bound to the actor. WEB-030 production owner-grant propagation is certified at run 35098533519. Qt fail-closed capability controls and focused tests are certified at `5e74849b463482e9e2b95fba570261ba8852ed0b`: Qt run 35128650055 and native hardening run 35128650081 succeeded. Remaining: desktop authenticated actor composition. |
| F-04 Config-root binding | IN PROGRESS | Handoff/updater use explicit config/trust roots and focused CI proves inherited root variables cannot redirect updater PBAC. Remaining: desktop composition must pass root/trust anchor and root update settings/staging/history consistently. |
| F-05 Authenticated anti-rollback | CERTIFIED | Dedicated hardening workflow run 35072409315 exercised signed version/minimum-version tamper negatives successfully. |
| F-06 Immutable deployment/runtime binding | CERTIFIED | `scripts/verify_container_identity.py` fail-closes unless Git commit equals build input and built/deployed/running identities are the same immutable `sha256:` digest, with a certification proof binding the chain. Workflow run 35142967386 succeeded at `b76a1f4222ea424e90aca04a0def8fbfd9c61551`: it checked out the exact PR head, passed focused verifier tests, built an image from that checkout, pushed it to an ephemeral registry to obtain an OCI manifest digest, deployed by digest, verified the running container/image identity, verified the evidence chain, and uploaded `container-identity-evidence` artifact 10465777576 (artifact digest `sha256:fe40b7b9bc721c9a85144b5b0b200c07093b29c0d20eac557acce29856e3017d`). |
| F-07 Security certification coverage | IN PROGRESS | At `b76a1f4222ea424e90aca04a0def8fbfd9c61551`, all 17 observed PR workflow runs completed successfully, including native hardening, Qt, Docker runtime, and immutable container identity certification. Desktop composition remains the unresolved mandatory gate. |

## Current continuation note — 2026-09-16

PR #15 remains open, mergeable, and draft with no comments or review threads. `main` remains `54abf55aa0c5124e1c1e7c46db14814c64a4e37c`. At the latest mandatory re-check, branch head `b76a1f4222ea424e90aca04a0def8fbfd9c61551` was 60 commits ahead and 0 behind main. All 17 workflow runs observed for that head completed successfully.

F-06 is now certified by real measured CI evidence rather than source-SHA inference. The dedicated workflow uses an ephemeral local OCI registry, captures the pushed manifest digest, deploys that exact digest, inspects the running container's image identity, verifies one immutable digest across built/deployed/running stages, and archives the certification evidence. This certification demonstrates the required identity chain for the CI container deployment scenario; it does not imply that arbitrary external production deployments are automatically bound unless they execute an equivalent gate.

The updater migration history is upgrade-safe. `MigrationRunner` rejects checksum changes for already-applied migrations, so Migration 7 is preserved at its historical checksum and Migration 8 carries cleanup/isolation. Do not edit either migration in place; future changes require a new migration number.

Highest-priority unresolved integration remains desktop composition across F-01/F-03/F-04. Current branch inspection confirms `MainWindow` still constructs `OfflineUpdateService()` without its required administrator trust-anchor argument, derives update settings/staging/history from `session_path.parent`, launches handoff without explicit config/trust roots, and repeatedly calls `resolve_application_paths()` inside Qt composition. It also constructs `AccessAdministrationService` without actor context. `run_desktop` establishes the actual authenticated local-login identity from `login.profile["username"]`. Continue by wiring the already-resolved `container.paths` and authenticated desktop identity through bootstrap -> `run_desktop` -> `MainWindow`, then add focused regression tests.

**Tooling boundary:** the connected GitHub contents writer only supports complete-file replacement, while connector reads of `src/natureai_next/ui/qt/application.py` and `src/natureai_next/bootstrap/cli.py` are truncated before a complete replacement body can be safely reconstructed. Do not overwrite either large file from partial reads. Use a patch-capable/local checkout (or another tool that can preserve untouched file bytes) for this composition edit. This is a tooling limitation, not a security-design blocker; do not weaken the explicit-root or actor-context requirements to work around it.

## Completion definition

Do not mark complete or ready for merge until F-01 through F-07 are certified (or an approved non-applicable decision is documented), native install requires both authenticated provenance and PBAC, local PBAC mutation requires authorized actor context, desktop/updater share one explicit application root, immutable runtime identity is certified, unrelated gates pass, and this ledger reflects repository state.

## Instruction to the next chat

**Start here. Do not ask the user to reproduce the prior audit.** Read this file, the detailed hardening document, PR #15, current branch diff, and current `main`; then continue the first non-certified phase and maintain this ledger.
# Fieldora Security Hardening — Continuation Instructions

**Branch:** `security/native-update-trust-hardening`  
**Authoritative base audited:** `54abf55aa0c5124e1c1e7c46db14814c64a4e37c`  
**Tracking PR:** #15 — Harden native update trust and PBAC boundaries  
**Detailed requirements:** `docs/security/native-update-trust-hardening.md`

## Purpose

This file is the single entry point for any future ChatGPT/Codex session continuing the Fieldora security remediation.

When the user says **“continue fixing the security hardening”**, **“continue the security branch”**, or equivalent, first read this file from this branch and then continue from its current repository state. Do not require the previous audit chat as context.

## Mandatory continuation procedure

1. Confirm the active target is `Natuurgids/Fieldora`, branch `security/native-update-trust-hardening`.
2. Read this file completely.
3. Read `docs/security/native-update-trust-hardening.md` completely.
4. Read PR #15 status, changed files, review comments, checks, and current head SHA.
5. Compare this branch with current `main` before making changes. Do not silently overwrite newer mainline security work.
6. Inspect the implementation and tests already present on this branch. Treat repository state as authoritative; do not assume a checklist item is complete because this document says it was planned.
7. Work through the remediation checklist below in dependency order. For each item:
   - inspect exact current code;
   - implement the smallest coherent fix;
   - add/update tests and certification;
   - run or inspect available checks;
   - update this file's progress section in the same branch;
   - commit the change to this branch with a security-boundary-specific commit message.
8. Keep the PR in draft until every mandatory acceptance gate is demonstrated.
9. Never weaken or bypass a failing security gate merely to make tests pass.
10. Before declaring completion, re-audit the resulting branch end-to-end and explicitly distinguish demonstrated, implied, and unresolved properties.

## Security model — never conflate these

Always analyze and report these as separate properties:

1. **Integrity** — bytes/digests match expected bytes.
2. **Authenticity / provenance** — a trusted publisher cryptographically authorized the release metadata/artifact.
3. **Authorization** — the acting subject is permitted to perform the operation.
4. **Deployment binding** — the audited/built artifact is immutably bound to what is deployed/running.

Rules:

- SHA-256 integrity is not publisher authenticity.
- A Git commit SHA is not an OCI/runtime identity.
- PBAC authorization is not release provenance.
- A serialized `signature_verified=true` or `provenance_verified=true` assertion is not cryptographic verification.
- Do not claim RCE/arbitrary package substitution unless every required attacker-controlled trust boundary is demonstrated.
- Preserve fail-closed behavior.

## Remediation order

### Phase 1 — F-01 Native release authenticity/provenance — HIGH

Implement cryptographic authentication of native update metadata before security-sensitive metadata is trusted.

Required behavior:

- Use a canonical signed release manifest/index.
- Verify a detached Ed25519 signature against an administrator-controlled trust anchor.
- The trust anchor must not be supplied by the same user-selected update source.
- Signed content must bind at least:
  - format + format version;
  - product;
  - channel;
  - version;
  - minimum supported version;
  - package basename;
  - package SHA-256;
  - package byte size;
  - release identity/digest;
  - digest of Security Install evidence.
- Reject unsigned manifests, malformed signatures, unknown/untrusted key IDs, path traversal, digest/size mismatch, and evidence not bound by the signed payload.
- `OfflineUpdateService.check()` must authenticate the index before consuming version, rollback, package, release, or Security Install trust assertions.
- Security Install must derive authenticity/provenance state from verification output rather than trusting booleans from update media.

Primary areas to inspect:

- `src/natureai_next/application/updates.py`
- `src/natureai_next/application/security_install.py`
- `src/natureai_next/domain/security_install.py`
- appropriate ports/infrastructure modules for trust-anchor/signature verification
- release/build tooling that produces `update-index.json`

### Phase 2 — F-02 Native updater PBAC provisioning — HIGH

Provision the exact updater identity and least-privilege authorization during clean bootstrap/install.

Required identity:

- identity ID: `fieldora-native-updater`
- kind: service
- enabled: true

Required effective permission only:

- action: `install`
- resource type: `security_install_release`
- purpose: `security_install`

Requirements:

- idempotent provisioning;
- no wildcard updater action/resource grant;
- clean-install test proves the identity/policy exists;
- test proves an unrelated subject remains denied;
- test proves missing/disabled updater identity remains denied.

Inspect platform bootstrap and every first-class clean-install target so the deployment that exposes native updating also provisions its required PBAC state.

### Phase 3 — F-03 Local PBAC administration authorization — HIGH

Close the local privilege-administration boundary.

Required behavior:

- Access-control mutations must carry authenticated acting-subject context.
- The application/service layer must call an authorization decision before mutation; Qt button visibility alone is insufficient.
- Cover organization, identity, group membership, role assignment, contract, and policy mutation.
- Define narrowly scoped administration actions/resource types/purpose rather than granting arbitrary wildcard authority where avoidable.
- Local Qt Access & Contracts workspace must be read-only/fail-closed when actor context is absent or unauthorized.
- Add positive and negative tests, including prevention of self-provisioning an unauthorized Security Install grant.

Primary areas:

- `src/natureai_next/application/access_control.py`
- `src/natureai_next/ui/qt/access_control.py`
- desktop composition/session/authentication context
- server administration authorization patterns for architectural consistency

### Phase 4 — F-04 Config-root / authorization-context binding — MEDIUM

Bind detached updater authorization state to the same explicit application root used by the desktop session.

Required behavior:

- resolved config/application root is explicitly carried in the handoff/request;
- detached updater resolves PBAC DB, update history, and relevant update state from that explicit root;
- it must not independently choose a different authorization root from inherited `APERTURE_DATA_ROOT` / `NATUREAI_DATA_ROOT` after handoff;
- explicit non-default `--config-root` must survive desktop -> stage -> handoff -> updater;
- add tests for conflicting environment roots and prove they cannot redirect updater authorization state.

Primary areas:

- `src/natureai_next/bootstrap/paths.py`
- `src/natureai_next/application/native_handoff.py`
- `src/natureai_next/bootstrap/native_updater.py`
- desktop bootstrap/composition

### Phase 5 — F-05 Authenticated anti-rollback — MEDIUM

Keep monotonic version/minimum-supported-version checks, but authenticate the metadata they rely on.

Tests must prove modification of `version` or `minimum_supported_version` invalidates authenticity and cannot be used as trusted rollback metadata.

### Phase 6 — F-06 Immutable deployment/runtime binding — MEDIUM

For container deployment/certification, establish evidence chain:

`Git commit -> build inputs -> OCI digest -> deployed digest -> running digest -> certification proof`

Requirements:

- do not use mutable image tag alone as runtime identity;
- record/verify image digest or equivalent immutable image identity;
- certification must compare intended built/deployed identity with running workload identity;
- keep functional health checks, but do not treat them as cryptographic binding.

Inspect Docker/Kubernetes/OpenShift build/install/certification paths from current main/branch state before changing them because deployment work may evolve independently.

### Phase 7 — F-07 Security certification coverage — DEFENSE IN DEPTH

Add explicit CI/certification for the native-update and local-PBAC security boundaries.

Minimum gates:

- valid signed native update accepted;
- unsigned index rejected;
- untrusted signer rejected;
- tampered signed field rejected;
- package hash/size mismatch rejected;
- Security Install evidence digest mismatch rejected;
- valid artifact without PBAC authorization rejected;
- clean install provisions exact updater identity + least-privilege policy;
- unrelated subject denied;
- local PBAC mutation without authorized actor denied;
- explicit config root preserved through detached updater;
- conflicting inherited environment cannot redirect PBAC DB;
- immutable container runtime digest recorded and checked.

## Integration / branch rules

- This branch owns the concrete security remediation.
- Do not move the fixes into stale deployment-layout work.
- PR #10 / `deployment/docker-layout-stage` was closed as stale/superseded. Do not resurrect it as the security implementation base.
- `feat/platform-bootstrap-contract` / PR #13 contains potentially useful platform/supply-chain contract work but was diverged from main when this branch was created. Re-evaluate its current state before reuse; cherry-pick/reimplement only compatible pieces after comparison with current main.
- Historical branches with zero commits ahead of main should not be used as implementation bases.
- If current main has advanced, rebase/merge carefully and re-run the security acceptance gates; never assume the audited base still describes current code.

## Progress ledger

Future sessions MUST update this section when implementation state changes.

Status values: `NOT STARTED`, `IN PROGRESS`, `IMPLEMENTED — TESTS PENDING`, `CERTIFIED`, `BLOCKED`.

| Finding | Status | Completion evidence |
| --- | --- | --- |
| F-01 Native release authenticity/provenance | IN PROGRESS | Ed25519 signed index verification and administrator trust-anchor loading implemented; authenticated package hash/size and Security Install evidence binding tests added. Still required: wire trust-anchor path at desktop/update composition, remove trust in serialized provenance booleans inside Security Install acceptance, and add release/build tooling that emits the signed index. |
| F-02 Native updater PBAC provisioning | NOT STARTED | Contract documented; implementation required |
| F-03 Local PBAC administration authorization | NOT STARTED | Contract documented; implementation required |
| F-04 Config-root binding | NOT STARTED | Contract documented; implementation required |
| F-05 Authenticated anti-rollback | IMPLEMENTED — TESTS PENDING | Version and minimum-supported-version are consumed only after Ed25519 verification; tamper-negative tests added but CI/check result not yet observed. |
| F-06 Immutable deployment/runtime binding | NOT STARTED | Contract documented; implementation required |
| F-07 Security certification coverage | IN PROGRESS | Native authenticity negative/positive pytest coverage added; dedicated workflow and remaining PBAC/config-root/runtime gates required. |

## Current continuation note — 2026-09-15

Branch work added `application/update_trust.py`, changed `OfflineUpdateService` to require an explicit administrator-controlled trust-anchor file, and added `tests/test_native_update_authenticity.py`. The PR remains draft. No passing CI result has yet been observed for these commits, so none of these properties is certified. Continue F-01 before moving to F-02: first inspect/update all `OfflineUpdateService` composition call sites for the new required trust-anchor argument, then change Security Install so authenticity/provenance is derived from cryptographic verification output rather than `signature_verified` / `provenance_verified` media booleans, then add signed-index release tooling and run/inspect the focused tests and static checks.

## Completion definition

Do not mark this branch complete or PR #15 ready for merge until all of the following are true:

1. F-01 through F-07 are `CERTIFIED` or a specifically documented non-applicable decision is approved in the PR.
2. Tests cover both successful operation and fail-closed negative paths.
3. No authenticity decision depends on untrusted serialized verification booleans.
4. No native install can occur without both authenticated release provenance and independent PBAC authorization.
5. Local PBAC mutation cannot occur without an authorized actor.
6. Desktop and updater authorization state are explicitly rooted to the same application root.
7. Container certification uses immutable runtime artifact identity.
8. Existing unrelated security gates remain passing.
9. PR #15 is re-reviewed after the final end-to-end security audit.
10. This progress ledger reflects the actual final repository state.

## Instruction to the next chat

**Start here. Do not ask the user to reproduce the prior audit.** Read this file, the detailed hardening document, PR #15, current branch diff, and current `main`; then continue implementing the first non-certified phase. Maintain this file as the durable handoff record for every subsequent session.
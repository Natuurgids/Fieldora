# Fieldora certification remediation logbook

Branch: `feature/versioned-facility-floorplans`

This logbook records the certification/remediation slices performed directly on the existing product branch. Each entry captures the verified repository evidence, smallest architecture-consistent change, regression coverage, validation status, and blockers.

## 2026-08-25 — Slice 1: governed Audit projection/navigation

Starting head: `2b2b3515a3ef3af66c3d521c5ec4863c57738220`

### Verified current-state gap

- `/api/v1/audit` already exists in `src/natureai_next/server/api.py` and authorizes with the existing PBAC tuple `view_audit / security_audit / administration`.
- The zero-trust browser capability projection did not expose an Audit destination.
- Audit was embedded in the Governance/Administration page, so `loadAdministration()` eagerly called `loadAudit()` even when the identity merely had another Administration capability.
- The grouped Administration navigation contained eight destinations and omitted Audit.

### Remediation

- `BrowserFunctionalityFieldoraApi` now projects `pages.audit` from the exact PBAC request used by `/api/v1/audit`; an Audit-only grant also makes the parent Administration workspace reachable.
- The Administration web alignment extracts Audit into its own managed workspace, adds it to the governed Administration sub-navigation, and loads Audit only when that workspace is opened.
- Governance no longer implicitly calls the Audit endpoint.
- No new permission vocabulary, browser-local authorization, persistence layer, or audit subsystem was introduced.

### Regression coverage

- `tests/test_audit_capability_projection.py` covers allow, default-deny, and explicit-deny behavior for the existing Audit PBAC tuple.
- `tests/test_administration_workspace_web.py` covers authorized Audit navigation, no eager Audit fetch from Governance, Audit loading on navigation, unauthorized Audit hiding, and direct-navigation fail-closed behavior.

### Commits

- `b6eeac0c088e3353c7897f371ee79349d945b4f7` — Project audit capability through PBAC
- `4c79761310a091990a973fc295339c8d2be76f21` — Expose Audit as governed Administration workspace
- `06a736bcacb3818668fc69644901708b9d1aad59` — Cover governed Audit administration navigation
- `0ddcae4a23ac2d5b3a109651ceb22e01d91e0759` — Cover Audit PBAC capability projection

### Validation

GitHub certification workflows were triggered for head `0ddcae4a23ac2d5b3a109651ceb22e01d91e0759`, including server-web, zero-trust-web, platform-server, Qt and real-host runtime-harness certification. At log creation they were queued; conclusions will be recorded in a later slice.

## Next slices

1. AI Administration / MCP contract coherence.
2. Whiteboard and Notebook persistence/execution coherence.
3. Runtime/jobs/worker cancellation/failure/status/authorization coherence.
4. Broad certification workflow review and final diff/governance review.

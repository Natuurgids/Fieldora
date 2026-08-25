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
- Audit workspace sub-navigation preserves live navigation handlers rather than relying on cloned DOM event state.
- No new permission vocabulary, browser-local authorization, persistence layer, or audit subsystem was introduced.

### Regression coverage

- `tests/test_audit_capability_projection.py` covers allow, default-deny, and explicit-deny behavior for the existing Audit PBAC tuple.
- `tests/test_administration_workspace_web.py` covers authorized Audit navigation, no eager Audit fetch from Governance, Audit loading on navigation, unauthorized Audit hiding, direct-navigation fail-closed behavior, and functional Audit sub-navigation.

### Commits

- `b6eeac0c088e3353c7897f371ee79349d945b4f7` — Project audit capability through PBAC
- `4c79761310a091990a973fc295339c8d2be76f21` — Expose Audit as governed Administration workspace
- `06a736bcacb3818668fc69644901708b9d1aad59` — Cover governed Audit administration navigation
- `0ddcae4a23ac2d5b3a109651ceb22e01d91e0759` — Cover Audit PBAC capability projection
- `8094a49af8137186ad0c91f9310656f1045712ae` — Preserve Audit workspace navigation handlers

### Validation

GitHub certification workflows were triggered for the Audit commits, including server-web, zero-trust-web, platform-server, Qt and real-host runtime-harness certification. Their conclusions are not treated as passing until checked at the current certification head.

## 2026-08-25 — Slice 2: granular AI Administration mutation projection

Starting head: `8094a49af8137186ad0c91f9310656f1045712ae`

### Verified current-state gap

- The managed server exposes Providers, Models, and MCP Servers as separately PBAC-governed science resources (`ai_provider`, `ai_model`, and `mcp_server`). Their generic POST paths authorize with `edit` on the corresponding resource type.
- AI Administration page visibility correctly follows read authority across those resource types.
- The generic “Register AI component” form remained visible whenever the page was visible, even for read-only identities. The existing `aiadmin.manage` action only represented `edit / ai_model / administration`, so it could not safely authorize provider or MCP mutation controls.
- The richer application-level `AIPlatformService` already implements offline-first provider/MCP network governance and is separately covered by `tests/test_ai_platform_offline_first.py`; the managed server record routes are not silently rewritten to that service in this slice.

### Remediation

- Added granular browser action projections for `aiadmin.models.manage`, `aiadmin.providers.manage`, and `aiadmin.mcp.manage`, each using the exact `edit` + resource-type + `administration` tuple used by the corresponding managed API record route.
- Preserved `aiadmin.manage` as the existing model-edit alias used by offline-model registration controls.
- The managed browser now hides/disables unauthorized AI component types, selects an authorized type when one exists, hides the generic registration card when none are editable, and keeps the save action absent when the selected type is not authorized.
- Backend PBAC remains authoritative; no client-side permission is treated as a security boundary.

### Regression coverage

- `tests/test_aiadmin_capability_projection.py` proves read authority does not imply mutation authority and that model/provider/MCP edit capabilities are projected independently.
- `tests/test_aiadmin_zero_trust_web.py` certifies in Chromium, Firefox, and WebKit that a model-only editor sees the model mutation path while provider and MCP mutation choices are absent/disabled.

### Commits

- `448644d65b2913c7051daef99c0c965d94103fd6` — Project granular AI administration actions
- `51628acb6aa9afd192668c0c5c334f16c7e26ac6` — Cover granular AI administration capabilities
- `c1e3f4bd8a65e47862386055b00d577ba856c288` — Cover AI administration zero trust controls

### Architectural follow-up

The managed server currently persists its AI provider/model/MCP administration records through the generic governed science-record boundary, while `AIPlatformService` owns richer local/remote network-approval and MCP invocation behavior. This is recorded as a coherence question for later architecture review rather than being merged implicitly during a zero-trust UI remediation.

## Next slices

1. Whiteboard and Notebook persistence/execution coherence.
2. Runtime/jobs/worker cancellation/failure/status/authorization coherence.
3. AI Platform managed-server versus `AIPlatformService` architecture decision, if current product contracts require convergence.
4. Broad certification workflow review and final diff/governance review.

# Fieldora desktop ↔ web functional parity program

Status: ACTIVE — runtime validation on Windows 11 + Docker Desktop exposed substantial functional divergence between the mature Qt desktop workflows and the managed web client.

This file is the restart point for future implementation sessions. A new session should read this file first, inspect the referenced code/tests, update item statuses as work lands, and keep each change small enough to certify independently.

## Goal

The web client may use different presentation technology and may scale to more users/nodes, but it must not invent different scientific, evidence, project, provenance, deduplication, access-control, or workflow semantics from the desktop application.

The authoritative order is:

1. domain invariants;
2. application services / repository contracts;
3. governed API behavior;
4. desktop and web presentation adapters.

Where desktop currently reaches a production application service and web duplicates the logic in JavaScript or a browser-only endpoint, prefer moving the web onto the same application-service contract rather than copying desktop UI code.

## Runtime findings that started this program

The clean Docker installation itself passed, including the Rocky Linux 9 Fieldora image, PostgreSQL mutual TLS, service enrollment, certificate renewal, browser trust, and bootstrap authentication. The problems below were observed after entering the actual web application.

- Re-importing the same photo can create additional evidence rather than applying content identity / duplicate policy correctly.
- A repeated source should normally resolve to the existing evidence identity. Depending on provenance/context it may add a file-instance or observation/link; an exact duplicate with no new information should be a no-op.
- Multi-file import currently reports a browser `fetch` failure and does not complete the import.
- Bulk intake must support mixed evidence types (photos/RAW, documents, video, sound, and extensible specialist evidence such as X-ray scans) while hashing and validating each item.
- The Projects `Create` action is not functionally usable in the tested web application.
- Multiple other web buttons/views do not perform the corresponding desktop action.
- Navigation/display parity alone is therefore not an adequate certification target.

## Confirmed code-architecture mismatch

Desktop import (`src/natureai_next/ui/qt/importing.py`) delegates planning/execution to the production import application service. It exposes storage policy, duplicate policy, recursion, heterogeneous source kinds, cancellation/progress, and per-item import results.

The shared domain import model (`src/natureai_next/domain/importing.py`) already defines:

- `DuplicatePolicy.SKIP`
- `DuplicatePolicy.ADD_FILE_INSTANCE`
- `ImportDecision.IMPORT_NEW_ASSET`
- `ImportDecision.ATTACH_TO_EXISTING_ASSET`
- `ImportDecision.SKIP_EXACT_DUPLICATE`
- `ImportDecision.REJECT_SOURCE`
- photo, RAW photo, sound, video, document, sidecar, and unknown source kinds
- SHA-256 fingerprints and deterministic import plans

The current browser compatibility layer (`src/natureai_next/server/browser_functionality_web.py`) instead hashes files in browser JavaScript and directly drives `/api/v1/uploads` or staged-submission endpoints. This is a separate behavioral implementation and is a likely source of parity defects. Folder import and ordinary multi-file import also currently use different browser paths.

Project creation is similarly split: browser JavaScript builds its own record and POSTs to `/api/v1/projects`, while `BrowserFunctionalityFieldoraApi` provides a browser-specific creation path. This must be compared against the desktop project-management application service and normalized so both clients execute the same business contract.

## Status legend

- `TODO` — not yet analyzed or implemented.
- `ANALYSIS` — desktop/web contract comparison in progress.
- `READY` — desired contract and tests are defined; implementation can start.
- `BUILDING` — code change in progress.
- `BLOCKED` — external decision/dependency required.
- `DONE` — implementation and focused certification are green.
- `RUNTIME` — automated tests are green and a real browser/runtime check is still required.

Every `DONE` item must name its focused tests/CI evidence in the Notes column or directly below the item.

---

# Work breakdown

## Phase A — parity foundations and contract inventory

| ID | Status | Work item | Acceptance contract |
|---|---|---|---|
| WEB-001 | READY | Build desktop/web capability inventory | Enumerate every desktop top-level workspace, principal action, and corresponding web route/button/API. Missing and browser-only behavior are explicitly marked. |
| WEB-002 | READY | Define shared-service parity rule | New web mutations must call the same application/domain service as desktop or document why a different adapter is required. No business rule may live only in browser JS. |
| WEB-003 | TODO | Add parity test manifest | Machine-readable/pytest parameter list maps capability ID → desktop service → API route → web control → expected authorization action. |
| WEB-004 | TODO | Add browser action telemetry for tests | Test-only capture identifies which API mutation a button invoked and its result, without exposing policy internals to production UI. |
| WEB-005 | TODO | Classify existing browser patches | Review `*_web.py` monkey/append patches and mark each as presentation-only, compatibility adapter, or business-logic duplication requiring removal/refactor. |

## Phase B — evidence identity, hashing, and duplicate semantics

| ID | Status | Work item | Acceptance contract |
|---|---|---|---|
| WEB-006 | READY | Trace authoritative desktop duplicate flow | Document exact repository/application calls from fingerprint → existing asset lookup → skip/attach/new decision. |
| WEB-007 | READY | Define canonical evidence identity | SHA-256 + required structural metadata identify byte identity; content identity is not inferred from filename/path alone. |
| WEB-008 | READY | Exact duplicate no-op | Importing the same bytes again with no new provenance/context creates no new evidence and no meaningless duplicate observation. |
| WEB-009 | READY | Duplicate path/file-instance semantics | Same bytes from a materially different source path/storage instance attach provenance/file-instance to existing evidence when policy allows. |
| WEB-010 | TODO | Observation-on-repeat semantics | Define when a repeated encounter is a scientific observation versus merely a duplicate file transfer. Observation creation requires new observation context, not just a repeated upload. |
| WEB-011 | TODO | Project-link-on-existing-evidence semantics | Importing already-known evidence into another authorized project creates a governed relationship/link, not a second evidence identity. |
| WEB-012 | TODO | Dedup race safety | Two concurrent uploads of identical bytes converge on one evidence identity using DB uniqueness/transaction logic; loser returns existing identity deterministically. |
| WEB-013 | TODO | Dedup audit contract | Audit records distinguish new evidence, existing-evidence link, attached file instance, skipped exact duplicate, and rejected source without logging sensitive host paths. |
| WEB-014 | TODO | Web duplicate UX | Browser reports `new / linked / attached / skipped / failed` counts and per-item reasons consistent with desktop summary. |

## Phase C — single and bulk heterogeneous intake

| ID | Status | Work item | Acceptance contract |
|---|---|---|---|
| WEB-015 | READY | Reproduce current multi-file `fetch` failure | Add focused Chromium/Firefox/WebKit test reproducing the runtime failure before fixing it. Capture exact failed request/response. |
| WEB-016 | READY | Unify single/multi/folder intake contract | One server-side intake application contract handles one file, many files, and directory manifests; UI source selection is the only difference. |
| WEB-017 | READY | Server-authoritative import planning | Browser may calculate a client checksum for transport verification, but server/application service performs authoritative classification, fingerprint verification, duplicate planning, and persistence. |
| WEB-018 | READY | Mixed evidence batch | One batch accepts photo/RAW, document, video, audio and supported sidecars together. |
| WEB-019 | TODO | Extensible specialist evidence type | Add explicit extension/MIME registration path for types such as X-ray/DICOM or other scientific scans without treating every unknown file as generic evidence. |
| WEB-020 | TODO | Bulk manifest schema | Submission manifest carries relative path, size, MIME hint, client hash, optional project/context, and stable client item ID; server returns stable per-item results. |
| WEB-021 | TODO | Chunked upload resumability | Large-file chunk upload validates ranges, idempotently retries a chunk, and can resume without creating duplicate evidence. |
| WEB-022 | TODO | Batch partial-failure semantics | One bad file does not silently roll back good independent files unless submission policy explicitly requests atomic intake; final summary is deterministic. |
| WEB-023 | TODO | Import cancellation | Cancel stops remaining work cleanly, preserves already committed valid items according to declared transaction policy, and leaves no orphan staging rows/blobs. |
| WEB-024 | TODO | Import progress/activity parity | Web exposes queued/scanning/hashing/uploading/processing/completed states compatible with job/activity engine semantics rather than a single fragile fetch spinner. |
| WEB-025 | TODO | Intake housekeeping | Expired/incomplete staged uploads are garbage-collected; referenced blobs and completed evidence are never deleted by staging cleanup. |

## Phase D — Projects & Portfolio parity

| ID | Status | Work item | Acceptance contract |
|---|---|---|---|
| WEB-026 | READY | Reproduce unusable Create Project button | Browser test clicks the actual Projects create control and proves the observed failure before implementation changes. |
| WEB-027 | READY | Trace desktop project creation contract | Compare Qt project-management create dialog/service, required fields/defaults, ownership, revision behavior, audit and post-create selection. |
| WEB-028 | READY | Replace browser-only project semantics | Web project creation uses the same application service/command contract as desktop; API adapter handles transport/auth only. |
| WEB-029 | TODO | Project validation parity | Name/status/dates/owner/description and any required organizational fields validate identically in desktop/API/web. |
| WEB-030 | TODO | Project owner immediate access | Creator receives only the intended governed project authority and can immediately open/edit the project; PBAC remains authoritative. |
| WEB-031 | TODO | Project edit/archive lifecycle | Web implements desktop-equivalent edit/status/archive actions with optimistic revision conflict handling. |
| WEB-032 | DONE | Project hierarchy and child creation | Phase/task/sprint/allocation creation and hierarchy views invoke real governed mutations, not view-only placeholders. |

WEB-032 evidence: exact implementation head `f98f8c0040507bed23c6ad3f21534ac9ea542baf`; workflow **WEB-032 managed Project hierarchy certification** run `33276063660`; Ruff and `tests/test_web032_project_hierarchy.py` passed, covering PBAC-denied direct mutation plus contextual phase/task/subtask/sprint/allocation browser actions.

## Phase E — Library, observations, provenance, and relationships

| ID | Status | Work item | Acceptance contract |
|---|---|---|---|
| WEB-033 | TODO | Library evidence detail parity | Web detail exposes the same governed identity/provenance/metadata relationships as desktop, subject to PBAC and opacity rules. |
| WEB-034 | TODO | File instances vs evidence records | UI clearly distinguishes one evidence identity from its managed/referenced/hybrid file instances. |
| WEB-035 | TODO | Observation creation parity | Create/edit observation uses the desktop application contract and can link existing evidence without cloning it. |
| WEB-036 | TODO | Evidence ↔ observation many-to-many | Multiple observations may reference one evidence item and one observation may reference multiple evidence items where domain allows. |
| WEB-037 | TODO | Project-independent Library rule | Evidence may exist in General Library without project; project assignment is a relationship/context, never ownership-by-upload shortcut. |
| WEB-038 | TODO | Collections/datasets parity | Collection/dataset create/edit/link/remove actions match desktop semantics and retain evidence provenance. |
| WEB-039 | TODO | Original/derivative semantics | Preview/thumbnail/transcode/analysis derivatives never replace or silently mutate the governed original. |

## Phase F — action/button parity across workspaces

| ID | Status | Work item | Acceptance contract |
|---|---|---|---|
| WEB-040 | TODO | Inventory every visible web button | For each visible control: action exists, authorization capability exists, mutation/read succeeds, success state renders, failure is intelligible. Remove dead controls. |
| WEB-041 | TODO | Observations workspace actions | Filters, create, open, edit, link evidence, review/status actions execute real contracts. |
| WEB-042 | TODO | Research workspace actions | Specimen/sample/protocol/survey/lab/research-domain actions are compared to desktop and wired through governed APIs. |
| WEB-043 | TODO | Knowledge & AI actions | Review queue, accepted determination, enrichment and AI-task actions preserve provenance/history and match desktop acceptance rules. |
| WEB-044 | TODO | Facilities/Operations actions | Assets, locations, floorplans, relocation, picklists and movement confirmation retain the desktop physical-reality invariants. |
| WEB-045 | TODO | Administration actions | Governance/audit/contracts/reference/connectors/operator/platform controls are real, authorized, and have correct parent/subnav state. |
| WEB-046 | TODO | Help/guides/navigation actions | All navigation controls lead to implemented content/action and preserve zero-trust visibility rules. |

## Phase G — web scale, housekeeping, robustness

| ID | Status | Work item | Acceptance contract |
|---|---|---|---|
| WEB-047 | TODO | Pagination and bounded queries | Library/projects/observations/audit lists do not fetch unbounded datasets; stable cursor/page semantics and counts are authorization-safe. |
| WEB-048 | TODO | Search/filter server parity | Large collections use server-side governed filtering/search rather than downloading everything then filtering in JS. |
| WEB-049 | TODO | Idempotency for browser mutations | Retried POST/PUT operations cannot create duplicate projects/evidence/links due to network retry or double click. |
| WEB-050 | TODO | Optimistic concurrency UX | Revision conflicts surface actionable reload/compare behavior rather than generic fetch errors or silent overwrite. |
| WEB-051 | TODO | Structured web error model | API errors have stable code + safe message + correlation ID; browser does not collapse transport, auth, validation and conflict errors into `fetch error`. |
| WEB-052 | TODO | Browser upload memory bounds | Large files are not fully duplicated in JS memory merely to hash/upload; use bounded streaming/chunk strategy where browser capabilities permit. |
| WEB-053 | TODO | Database constraints/index review | Verify identity/link uniqueness, project lookup, observation/evidence relations, staging cleanup and common web query indexes under PostgreSQL. |
| WEB-054 | TODO | Multi-user concurrency tests | Concurrent users editing projects, linking evidence, importing duplicates and reviewing records preserve revisions/PBAC/domain invariants. |

## Phase H — certification and release gate

| ID | Status | Work item | Acceptance contract |
|---|---|---|---|
| WEB-055 | TODO | Desktop ↔ API contract tests | Application-service fixtures prove desktop adapter and API adapter produce equivalent domain/repository outcomes for key mutations. |
| WEB-056 | TODO | Cross-browser workflow certification | Chromium, Firefox and WebKit exercise complete create/import/link/edit/review workflows, not only visibility/navigation. |
| WEB-057 | TODO | Duplicate/bulk runtime scenario | Real Docker browser test imports same photo twice, same bytes from second path, mixed batch, large file and partial failure; resulting DB/evidence graph is verified. |
| WEB-058 | TODO | Project runtime scenario | Real Docker browser creates, edits and reopens a project, adds child work, links pre-existing evidence, and verifies creator authority. |
| WEB-059 | TODO | Zero-trust regression gate | Every new control is absent when unauthorized; direct API remains independently denied; denied navigation never triggers protected fetches. |
| WEB-060 | TODO | Web functional-parity release gate | Do not call web version functionally complete until all mandatory parity IDs are DONE and Windows Docker runtime verification is green. |

---

# Implementation order

Work in small slices. Do not attempt an entire workspace in one commit.

### Slice 1 — evidence identity baseline

Target: `WEB-006` through `WEB-014`.

1. Trace current `ImportService` and repository uniqueness behavior.
2. Write tests for exact duplicate, second file instance, existing-evidence project link and concurrent duplicate race.
3. Expose a server/API import-plan endpoint or command adapter that invokes the same application service.
4. Change web single-file import to use it.
5. Certify before touching bulk UI.

### Slice 2 — repair multi/bulk intake

Target: `WEB-015` through `WEB-025`.

Start with a failing cross-browser reproduction of the reported `fetch` error. Then converge single/multiple/folder paths on one intake manifest and server-side planner. Add mixed-media fixtures. Keep upload transport separate from evidence commit semantics.

### Slice 3 — projects

Target: `WEB-026` through `WEB-032`.

Reproduce the broken create button, map the desktop service, replace the browser-specific record construction with the shared project command/application service, then add edit/lifecycle/hierarchy one action at a time.

### Slice 4 — evidence/observation relationships

Target: `WEB-033` through `WEB-039`.

Make the web Library show the actual evidence graph rather than a flat upload list. Implement observation linking without evidence cloning.

### Slice 5 — visible control audit

Target: `WEB-040` through `WEB-046`.

Walk every visible button in each workspace. A visible action without an implemented/authorized contract is a defect. Prefer hiding genuinely unavailable capabilities to presenting dead placeholders.

### Slice 6 — scale and robustness

Target: `WEB-047` through `WEB-054`.

After semantics are correct, add pagination, bounded search, idempotency, concurrency, structured errors, upload memory bounds and PostgreSQL indexes.

### Slice 7 — release certification

Target: `WEB-055` through `WEB-060`.

Run contract parity, three browser engines, zero-trust regression, then the real Windows Docker scenarios. Keep the PR draft until the mandatory gate is complete.

---

# Required test scenarios

These scenarios should become durable automated tests and later a short real-host checklist.

1. Import photo A → exactly one evidence identity.
2. Import identical bytes A again from the same source/context → no new evidence; deterministic skip/no-op.
3. Import identical bytes A from a different file path under `ADD_FILE_INSTANCE` → same evidence, new file-instance/provenance only.
4. Link existing evidence A to a second project → same evidence, new governed project relationship only.
5. Create a second observation that uses evidence A → same evidence, new observation relationship.
6. Simultaneously import A from two sessions → one evidence identity after race.
7. Bulk import photo + RAW + PDF + DOCX + WAV + MP4 → each classified/hashed and returned in one batch summary.
8. Include one unsupported/corrupt item in a batch → clear per-item failure; valid items follow declared partial/atomic policy.
9. Retry a failed chunk → no duplicate bytes/evidence.
10. Cancel a large batch → no orphan committed evidence for unfinished items and staging cleanup remains possible.
11. Create project in browser → it appears after reload and creator can immediately open/edit it.
12. Double-click/retry project create → idempotent result, not two projects.
13. Unauthorized user → create/import/link controls absent and direct API forbidden.
14. Revision conflict → safe conflict response and explicit browser recovery, no silent overwrite.
15. Library list with large fixture → bounded/paginated server query and stable filtering.

---

# Files to inspect first in future sessions

Desktop / domain:

- `src/natureai_next/ui/qt/importing.py`
- `src/natureai_next/ui/qt/library.py`
- `src/natureai_next/ui/qt/media_library.py`
- `src/natureai_next/ui/qt/observations.py`
- `src/natureai_next/ui/qt/project_management.py`
- `src/natureai_next/ui/qt/navigation_contracts.py`
- `src/natureai_next/domain/importing.py`
- import/project/observation application services and repositories reached by those Qt adapters

Web / API:

- `src/natureai_next/server/browser_functionality_web.py`
- `src/natureai_next/server/browser_functionality_api.py`
- `src/natureai_next/server/directory_intake_web.py`
- `src/natureai_next/server/media.py`
- `src/natureai_next/server/media_links.py`
- `src/natureai_next/server/desktop_alignment_web.py`
- `src/natureai_next/server/navigation_web_compatibility.py`
- `src/natureai_next/server/web_capabilities.py`
- relevant `*_api.py` resource adapters

Tests:

- `tests/test_server_web.py` and related server-web parity tests
- `tests/test_administration_workspace_web.py`
- zero-trust browser tests
- import service/repository tests
- project-management tests
- observation/evidence relationship tests

## Rule for updating this tracker

For every implementation commit:

1. change only the affected IDs from `TODO/READY` → `BUILDING/DONE/RUNTIME`;
2. add the exact test names or certification workflow proving the item;
3. if behavior changes from desktop, record the domain reason explicitly rather than calling it a web simplification;
4. never mark a visual/navigation-only test as proof of functional parity;
5. keep unresolved runtime observations in this file even when CI is green.

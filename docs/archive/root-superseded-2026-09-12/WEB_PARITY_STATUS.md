# Fieldora web parity live status

Last updated: 2026-08-26

Read this file together with:

- `WEB_DESKTOP_PARITY_PLAN.md` — full 60-item work breakdown and acceptance contracts.
- `WEB_PARITY_IMPORT_CONTRACT.md` — detailed import/evidence identity source trace and target architecture.
- `WEB_PARITY_PROJECT_CONTRACT.md` — authoritative desktop/server/web Project creation trace and target contract.

This file is deliberately short. It is the current-session handoff/status board and should be updated whenever a slice changes state.

## Current branch state

Branch: `feature/versioned-facility-floorplans`

The Windows 11 + Docker Desktop clean installation has been runtime-validated by the user and the Rocky Linux 9 application image was built successfully. Runtime use then exposed desktop/web functional divergence; this program addresses that divergence.

## In progress

| Work | State | Current evidence / next action |
|---|---|---|
| WEB-006 authoritative duplicate-flow trace | DONE (analysis) | Source trace is recorded in `WEB_PARITY_IMPORT_CONTRACT.md`. Desktop uses production `ImportService.plan()/execute()`; browser currently implements a separate upload loop. |
| WEB-007 canonical evidence identity | DONE (organization canonical) | Same organization + same verified SHA-256/size converges to one media identity across project contexts in reference/SQLite and PostgreSQL paths. `Fieldora media identity and project association certification` run #34 is green. |
| WEB-008 exact duplicate no-op | DONE (same context) | Repeated verified upload/register in the same organization/project returns the canonical existing media record, creates no second media row, and removes redundant temporary/object bytes. `Fieldora media identity certification` run #4 is green on reference/SQLite and PostgreSQL. |
| WEB-012 dedup race safety | DONE | PostgreSQL completion/schema bootstrap and SQLite/reference canonical claims are serialized and certified. Eight simultaneous SQLite upload completions and eight simultaneous direct registrations converge to one media ID and one object file. Run #32 reproduced the race with five identities; runs #33 and #34 are green after `BEGIN IMMEDIATE` canonical-claim serialization. |
| WEB-015 reproduce multi-file browser fetch failure | DONE | Root cause was browser patch precedence: `web_compatibility.py` replaced the correct multi-file `uploadSelectedFiles()` click handler with a single-file `generalUpload()` handler. Commit `72ce70a3ceb9f0c4531e758745a2cd6ed0e861ed` removes that override. `Fieldora browser multi import certification` run #13 is green over the real threaded HTTP adapter with three files, zero `requestfailed` events, six 201 upload responses, three media rows and Project links for every file. |
| WEB-011 project link on existing evidence | DONE | Upload completion records project associations against the organization-canonical media identity. Project A/B both list and download the same canonical object, an unlinked Project C receives no listing and a 404 download, PostgreSQL persists two distinct project association rows, and concurrent API/worker schema bootstrap is certified. Run #30 plus Platform run #522 are green. |
| WEB-026 unusable Create Project button | DONE | Root cause was managed-web patch composition: the Project editor created by `browser_functionality_web.py` was inserted inside the legacy portfolio split, then the later project cockpit removed that split while the Add Project button retained a closure to the detached editor. Commit `0a4b6eb6db2d7306c78ec9bf61e27268a6f3fe1a` keeps the editor connected outside the disposable split. `Fieldora project parity certification` run #46 (`32936244117`) is green and certifies real Chromium Research → Projects & Portfolio → Add Project → Create Project against authoritative PostgreSQL PM persistence, canonical server ID, visible cockpit refresh, default statuses, creator admin membership, activity, PBAC create decision, and no Science snapshot fallback. |
| WEB-027 desktop Project creation trace | DONE (analysis) | `WEB_PARITY_PROJECT_CONTRACT.md` records that authoritative creation validates dates, creates the canonical ID, five workflow statuses, admin PM membership, activity and optional template state. |
| WEB-028 shared web Project creation contract | DONE (managed creation subset) | Managed PostgreSQL creation is organization-scoped, server-ID authoritative, creates desktop-equivalent default statuses/admin PM membership/activity, and remains PBAC-gated. `Fieldora project parity certification` run #46 is green, including the real managed-browser click/runtime path. Templates and later edit/archive/child work remain separate WEB-029–032 slices. |
| WEB-029 Project validation parity | DONE | Ordinary managed browser creation now binds ownership to the authenticated creator, does not send a browser-selected initial lifecycle status, and transports name/description/start date/due date/budget/currency to the authoritative Project service. Real Chromium/PostgreSQL coverage proves valid fields persist and an impossible due-before-start schedule returns 400, keeps the editor open and persists nothing. `Fieldora project parity certification` run #53 (`32937090033`) is green. |
| WEB-030 Project owner immediate access | DONE | The real browser fixture now uses repository-backed `PolicyDecisionService` rather than a permissive stub. Creator `edit project` is default-denied before creation, immediately allowed for the canonical Project after the scoped object grant, while unrelated `delete project` remains denied. PostgreSQL PM membership is still `admin` and visible Project refresh remains green. `Fieldora project parity certification` run #55 (`32937427005`) is green. |
| WEB-031 Project edit/archive lifecycle | DONE | Production managed-server composition inherits `ProjectLifecycleFieldoraApi`, which adds per-Project fail-closed edit capability plus revision-safe edit and non-destructive archive UI/API behavior. Dedicated Chromium/PostgreSQL lifecycle coverage certifies canonical `expected_revision`, authoritative reload on stale-revision `409`, PBAC-hidden mutation actions and `project.archived` persistence. Project parity run #68 (`32943126097`) is green on the cleaned branch head after removing a duplicate false-red harness. |
| WEB-032 Project hierarchy/lifecycle parity | DONE | Project parity run #74 (`32949639582`, job `98117924355`) is green at certified implementation head `24a95c9491bd20f7156b5977e3b1b8156cff4a7d`. It certifies real governed Project → phase → sprint → task → allocation persistence and authoritative hierarchy behavior; the fixture adds only the required `view allocation` authority for the Capacity surface. |
| WEB-033 Library evidence-detail parity | DONE | Media identity certification run #91 (`32950877375`, job `98121747191`) is green at certified implementation head `973ba3d3c6a291b551e999ca3528e2a2cccbbfbe`. Real Chromium certifies asset-level `view asset` plus per-association PBAC filtering: authorized Project/Collection provenance is visible, unauthorized Dossier provenance is absent, and internal object paths/original upload filename are not disclosed. |

## Evidence-identity slice commits

- `2831150daf9b708a1d84ecb01be177bbb12a82dc` — PostgreSQL same-context canonical content completion.
- `d810b803e74a0511798ed9f67a21e066f4875b3f` — governed media store returns canonical record and removes redundant bytes.
- `70a94bc50ea18b5ebed8f9ebac62cebced31ee14` — filesystem/reference identity tests.
- `9193475a819d2dfd22d968e98e4815a375232d03` — PostgreSQL identity test.
- `9512eb699728109df188402a66d5792f06bd3694` — dedicated media identity certification workflow.
- `9789297c9645f2103d8d14fd95c7a299d020cce0` — repair PostgreSQL advisory key after run #1 exposed illegal NUL separators.
- `1593dc5cbb6d1c299c05e61c8d38d51b3ce5151d` — add the deterministic eight-way SQLite upload-completion race test; run #32 reproduced five canonical identities.
- `1a336f6164d8b360c82ec79a6e4be6339c731b56` — serialize SQLite canonical claims with `BEGIN IMMEDIATE` and remove losing object bytes.
- `36207dd376607e019aa81d1b4443bda658a5b6a4` — extend SQLite race certification to direct `register()` calls.

## WEB-015 browser multi-file slice commits

- `9e60ecf0f51f39b3847cc89c70a015dbc0092457` — add real threaded-HTTP Chromium multi-file import trace with `requestfailed` and upload-response capture.
- `38a9a952dddec655e4a41cb10125332cce1af87c` — add the dedicated `Fieldora browser multi import certification` workflow.
- `72ce70a3ceb9f0c4531e758745a2cd6ed0e861ed` — remove the later single-file compatibility override so the browser-functionality multi-file handler remains authoritative.
- `e5a81aefb3681fe9da6b40f8cbddb9ccd0cf9f2d` — verify every imported file retains its Project association in the real-HTTP browser trace.

## WEB-011 project-association slice commits

- `78d5f56f2f402321ed39c64c68a0a91f561e1e83` — canonicalize governed media across Project contexts.
- `6fb6713b6853927025c7c4f92f18c60748eef258` — query governed media associations by target Project.
- `614516411100f02558f812e71f77986ec8287189` — canonicalize PostgreSQL media across Project contexts.
- `0889371a1090e08f3d25bea42624110463abbbc3` — expose PostgreSQL media associations beside canonical metadata.
- `197fb951de4ac4870ed41f48bf282fc5adda199a` — attach governed associations to the media store.
- `475701d3c1349745634e492de46c2c94c938f54e` — wire Project associations into browser media upload/list/download access.
- `3b7178520be5e67f7b589c6a21d7cd4e3c0b5351` — certify browser canonical-media Project association behavior.
- `bea1390a8c642b512a1859ff212ec98cfbd690ae` — certify PostgreSQL canonical-media Project association persistence.
- `4548021f164bc5438c662f1537a2580420c094d4` — extend the named media certification workflow to WEB-011.
- `715b0dc6daa14a3081a4a0ede37002f603dada3e` — initialize the managed Project fixture required by the broader browser test file.
- `b7491c899a95d6a2bbe3f7a1c929aa9765d102be` — serialize standalone PostgreSQL association schema bootstrap with the governed-media advisory lock.
- `c74542c19b889547e3779b8b8458ea2dadfb46c3` — create association schema inside the metadata repository's already-serialized bootstrap transaction.
- `a3b52164df9ba0d113f0f9b72eb1f521d4d0643f` — strengthen the clean-schema concurrency regression to recreate association, media and upload tables under eight simultaneous initializers.

## Project creation slice commits

- `7758cfa3015331c30d89cc29a06ee43b178a0212` — Project creation parity contract/source trace.
- `70b2837066d065e1e84597d55667437e7c61faf5` — initial managed PostgreSQL PM creation adapter.
- `21eb14d78ef95a45e46b6dc0bb8b0d2b17ab54d7` — managed browser API Project Management hook.
- `eeacf3a8` — organization-scope managed PM persistence.
- `d4ba18f9` — organization-scope managed browser Project API.
- `4666f594` — compose PostgreSQL PM service into managed `serve` runtime.
- `39a1a737` — managed browser API canonical-ID/PBAC tests.
- `dff0f36cbf99de17703b4f6bb38e11bc789cf6f3` — dedicated Project parity certification workflow.
- `8935007d` — add real managed-browser Chromium Project creation certification against PostgreSQL PM persistence.
- `a6c7745a` — install Chromium and run the browser Project test in the Project parity workflow.
- `1939649a` — use the production SQLite access repository in the browser fixture so zero-trust capability projection and inherited runtime dependencies are representative.
- `0a4b6eb6db2d7306c78ec9bf61e27268a6f3fe1a` — keep the Project editor connected when the later project cockpit removes the legacy portfolio split.
- `a15cb6a71842f2771db469000118b5e85b7b90f1` — certify visible canonical Project refresh through the final cockpit tree after creation.
- `afdaeae61c5eeace61406deab7166a9bfa42dc58` — add the red WEB-029 owner/status validation regression; Project parity run #49 reproduced unauthorized payload ownership winning.
- `df20cf39330fe86d9da59f27aa233a757cd1595b` — make authenticated creator ownership authoritative at the ordinary managed browser create boundary.
- `5d487fc7343853b76fe57e558303c0b593790c0e` — add the red real-browser shared-field parity regression.
- `d26f65a54348f6f2c0e72ed4d3814d3216abdbec` — replace browser-only initial status/owner submission with shared start/due/budget/currency transport fields.
- `3dd9dab67681936621e076b43f35950b8e964050` — certify due-before-start rejection through the real browser/API/PostgreSQL path.
- `1825af11aead99c86517d5b4588a935d6eb8956d` — certify immediate creator authority with the real default-deny PBAC decision service.
- `66d99cc87a7c084c1b509e5d82ba35732c85f0b7` — add WEB-031 Project lifecycle revision regressions.
- `6fcf8580e40406419e7619bd827d19f71a0e8a1d` — implement managed PostgreSQL Project lifecycle revisions and archive.
- `516a3ae373806645db254c4e0268f685e2081ad1` — add governed Project edit/archive API with revision conflicts.
- `a07a27a9a9062b2f512050cc8a982ff0e0e210ed` — add revision-safe managed-web Project lifecycle UI.
- `b2003fe896b55538ed6c08a3967b8e0c2602c6da` — synchronize lifecycle browser mutations with completed authoritative refresh.
- `8b335f0ba1b899456dda25e5adb8be1f18189e19` — remove the duplicate non-production lifecycle harness after confirming production composition already inherits `ProjectLifecycleFieldoraApi`.

## certification history

### Fieldora browser multi import certification — run #13

Result: SUCCESS (run `32906526462`, job `97991753859`).

- Ruff passed for the browser multi-import test, browser compatibility patch and threaded HTTP adapter.
- Chromium exercised the shipped browser JavaScript against a real `ThreadingHTTPServer` and actual `BrowserFunctionalityFieldoraApi`/`GovernedMediaStore`.
- Three selected evidence files completed with no browser `requestfailed` events and six successful upload responses (POST + PUT for each file).
- Exactly three governed media records remained, covering image, text document and audio evidence.
- Every resulting media record retained the selected Project association.
- This closes WEB-015 and proves the earlier failure was the later single-file compatibility-handler override, not the 4 MiB chunk size or the HTTP adapter body path.

### Fieldora Platform server certification — run #522

Result: SUCCESS (run `32899917999`, job `97971078482`).

- PostgreSQL 16 service initialized successfully.
- Ruff passed.
- Bandit full audit, high-severity repository gate and governed platform gate passed.
- Semgrep OWASP Top 10 full audit and governed platform gate passed.
- Platform server tests passed, including the clean-database media schema concurrency regression.

### Fieldora project parity certification — run #1

Result: SUCCESS (run `32882236322`, job `97914262275`).

- PostgreSQL 16 service initialized successfully.
- Ruff managed Project parity check passed.
- PostgreSQL Project creation contract tests passed: canonical project, exact desktop default statuses, admin PM membership, `project.created` activity, date validation and organization isolation.
- Managed API tests passed: browser-provided IDs do not become authoritative, authenticated organization is used, and PBAC denial persists nothing.

### Fieldora project parity certification — run #46

Result: SUCCESS (run `32936244117`, job `98077885921`).

- PostgreSQL 16 service initialized successfully.
- Chromium and Ruff setup passed.
- The final managed browser UI navigated Research → Projects & Portfolio and exposed the PBAC-authorized Add Project action.
- Add Project opened a connected editor in the final project-cockpit composition.
- Create Project issued the real `POST /api/v1/projects`; the server returned 201 with its own canonical Project ID rather than accepting the browser UUID.
- The editor closed and the canonical Project became visible in the final project cockpit tree after the client refreshed authoritative Project state.
- PostgreSQL contained exactly the canonical Project with the submitted name/description, creator `admin` PM membership, the five desktop-equivalent default statuses and one `project.created` activity event.
- The fixture makes Science writes fatal, proving the browser runtime did not fall back to the old Science snapshot persistence path.
- The recorded access decisions include the PBAC-gated Project `create` decision and the browser emitted no failed network requests.
- This closes WEB-026.

### Fieldora project parity certification — run #53

Result: SUCCESS (run `32937090033`, job `98080309042`).

- PostgreSQL 16, Chromium installation and Ruff all passed.
- Ordinary managed browser creation no longer accepts payload owner delegation; authenticated creator ownership is authoritative and the service-created lifecycle remains `active`.
- The final browser editor transports name, description, start date, due date, budget and currency without duplicating Project business validation in JavaScript.
- A valid real Chromium creation persists all shared scalar fields to the canonical PostgreSQL Project, refreshes the visible cockpit, and omits browser `owner_id`/`status` authority from the request.
- A real Chromium submission with due date before start date reaches the same authoritative Project service, returns HTTP 400, leaves the editor visible and persists no Project.
- This closes WEB-029.

### Fieldora project parity certification — run #55

Result: SUCCESS (run `32937427005`, job `98081315202`).

- The browser fixture uses the real repository-backed `PolicyDecisionService` with default-deny semantics.
- Before Project creation, the authenticated creator has no `edit` right for a not-yet-created Project.
- The managed create flow writes its scoped object-grant policy and PostgreSQL PM `admin` membership for the canonical Project.
- Immediately after creation, the same PBAC service allows `edit project` for that canonical Project.
- An unrelated `delete project` request remains default-denied, proving the creator grant does not broaden into unrestricted Project authority.
- The real Chromium create/refresh and WEB-029 validation paths remain green under the authoritative PBAC engine.
- This closes WEB-030.

### Fieldora project parity certification — run #68

Result: SUCCESS (run `32943126097`, job `98098101467`).

- PostgreSQL 16, Chromium installation and Ruff managed Project parity checks all passed.
- The dedicated lifecycle browser path runs through production `ProjectLifecycleFieldoraApi` composition, not the lower-level creation-only API fixture.
- Authorized Project edit submits the current canonical revision to the managed PATCH endpoint and persists the authoritative PostgreSQL update/activity event.
- A stale edit receives HTTP 409; the browser reloads the latest authoritative Project/revision instead of overwriting the concurrent winner.
- Per-Project lifecycle mutation visibility is derived from the fail-closed PBAC capability endpoint rather than client role assumptions.
- Archive is a revisioned non-destructive status transition and persists `project.archived` rather than deleting Project state.
- A duplicate lifecycle test that instantiated the lower-level `BrowserFunctionalityFieldoraApi` was removed after it correctly failed to see the production-only lifecycle patch; run #68 proves the cleaned production certification lane remains green.
- This closes WEB-031.

### Fieldora project parity certification — run #74

Result: SUCCESS (run `32949639582`, job `98117924355`) at certified implementation head `24a95c9491bd20f7156b5977e3b1b8156cff4a7d`.

- PostgreSQL 16, Chromium installation, Ruff and the managed Project parity tests passed.
- The governed browser path persists the authoritative Project → phase → sprint → task → allocation hierarchy and reloads canonical server state.
- Capacity visibility is exercised with the minimum fixture PBAC authority required by that surface: `view allocation`.
- This closes WEB-032 without weakening production PBAC behavior.

### Fieldora media identity certification — run #91

Result: SUCCESS (run `32950877375`, job `98121747191`) at certified implementation head `973ba3d3c6a291b551e999ca3528e2a2cccbbfbe`.

- PostgreSQL 16, Chromium installation, Ruff and governed media identity/project-association tests passed.
- The requested evidence asset independently passes `view asset` PBAC in its Project context before detail is returned.
- Each association independently passes its own `view` PBAC check: authorized Project and Collection provenance is visible while unauthorized Dossier provenance is absent.
- The real detail UI does not disclose `relative_path`, filesystem/object-store paths, organization IDs or the original upload filename, and does not manufacture unstored metadata.
- Existing `/api/v1/media/{id}` byte/download behavior remains unchanged.
- This closes WEB-033.

## Guardrails

1. Do not modify the job-engine lease implementation to solve web parity defects.
2. Do not duplicate domain/application business rules in browser JavaScript.
3. Do not equate a repeated byte transfer with a new scientific observation.
4. Do not represent a new project relationship by copying evidence bytes or inventing a second evidence identity.
5. Preserve PBAC/zero-trust authorization at every new API/application adapter.
6. Every completed slice needs focused tests and a named certification result.

## Resume instructions for a new session

1. Read this file.
2. Read `WEB_DESKTOP_PARITY_PLAN.md`.
3. For import work, read `WEB_PARITY_IMPORT_CONTRACT.md`.
4. For Project work, read `WEB_PARITY_PROJECT_CONTRACT.md`.
5. Inspect the current branch head and latest workflow runs before editing.
6. Finish any `BUILDING`/`PARTIAL` item before starting unrelated parity work unless a failed test shows the design is wrong.
7. Update this status file when the slice changes state.
# Fieldora modular web architecture tasks

Status: ACTIVE — working task/dependency ledger for PR #3.

This ledger complements `WEB_DESKTOP_PARITY_PLAN.md`. Functional parity is not sufficient for completion: migrated web capabilities must be independently mountable, removable, and replaceable behind explicit contracts. Work should follow this dependency order and update the evidence/status here as slices land.

## Completion rule

A capability is modular only when its dependencies are explicit and mediated through contracts/services/events rather than another module's private DOM, mutable globals, private functions, or implementation-specific load order. Required dependencies must be declared; optional integrations must degrade safely when absent; runtime data relationships must travel through public events/contracts.

Status legend: `[ ]` missing, `[~]` partial/evidence or migration in progress, `[x]` certified.

## Foundation tasks

| ID | Status | Task | Depends on | Completion contract |
|---|---|---|---|---|
| A01 | [~] | Module contract | — | Module identity, route, capability, owned actions, provided/required contracts and lifecycle are explicit. |
| A02 | [~] | Module/capability registry | A01 | Shell discovers modules from a validated registry; duplicate ownership and unresolved requirements fail validation. |
| A03 | [~] | Shared application contracts | A01 | Auth, project context, navigation, inspector and notifications are consumed through public contracts. |
| A04 | [~] | Event/message boundary | A03 | Cross-module runtime changes use declared actions/events; producer and consumer ownership are known. |
| A05 | [~] | Service/API adapters | A03 | Presentation modules receive service/API adapters through stable interfaces; transport details are not feature globals. |
| A06 | [~] | State ownership | A03,A04 | Every shared state field has one owner; consumers use snapshots/read contracts/events and cannot mutate owner state directly. |
| A07 | [~] | DOM ownership | A01 | Each module owns a bounded render root and does not reach into another module's private DOM. |
| A08 | [~] | Shell decomposition | A01-A07 | Shell performs composition, capability gating, route/history and lifecycle only; feature business behavior is outside the shell. |

## Projects slice — Project list and project context

| ID | Status | Task | Depends on | Completion contract |
|---|---|---|---|---|
| P01 | [~] | Projects capability object | A01-A08 | Projects can mount/unmount behind shell contract without owning unrelated workspaces. |
| P02 | [~] | Project list provider/object | P01,A05,A06 | Accessible projects have one owner/provider; consumers do not read ambient `projects`. |
| P03 | [~] | Project context object | P02,A04,A06 | Selected project is validated against accessible list before publication; inaccessible/stale IDs do not mutate context. |
| P04 | [~] | Project scope/filter object | P02 | `My work` and `All accessible` are explicit scope semantics; zero `My work` matches remains zero. |
| P05 | [~] | Project hierarchy/tree object | P03,A05 | Hierarchy consumes project-context and work-data contracts; it does not own project selection. |
| P06 | [~] | Project inspector object | P03,P05 | Inspector consumes selected-record contract and can be replaced without changing hierarchy/context. |
| P07 | [~] | Project work-data adapters | P03,A05 | Phases/tasks/sprints/allocations/evidence are accessed behind declared service contracts. |
| P08 | [~] | Remove mutable global Projects coupling | P02-P07 | `projects`, `selectedProject`, direct feature globals and equivalent ambient state are no longer module integration APIs. |
| P09 | [~] | Retire legacy Projects wiring | P01-P08 | Final `/app.js` contains one owner per migrated responsibility and no competing legacy listeners. |
| P10 | [ ] | Module removal test | P01-P09 | Remove/disable Projects module and prove shell plus unrelated modules still boot/function. |
| P11 | [~] | Module replacement test | P01-P09 | Substitute a minimal Projects provider implementing the same public contracts without shell/consumer changes. |
| P12 | [~] | Dependency contract tests | A01-P11 | Duplicate ownership, missing providers and undeclared concrete coupling are rejected where mechanically testable. |
| P13 | [ ] | Browser behavior certification | P02-P07 | Chromium/Firefox/WebKit cover list, context switch, strict empty `My work`, stale/inaccessible selection, error and recovery. |
| P14 | [~] | API/security certification | P02,P07 | Accessible-list filtering, cross-org exclusion and scoped authorization are proven independently of UI hiding. |
| P15 | [~] | Persistence/domain proof | P07 | Visible project result traces through governed API/application contract to authoritative persisted/domain state. |
| P16 | [ ] | Eight-link certification chain | P01-P15 | capability → visible entry point → input validation → owned wiring → API/application call → persisted/domain outcome → visible result → audit/test evidence. |
| P17 | [~] | Dependency graph maintained | A01-P16 | Required, optional and provided contracts are represented in registry/manifest and this ledger stays current. |
| P18 | [ ] | Certify Project list/context | P01-P17 | Iteration 6 item may move from `[~]` only when behavior and removal/replacement boundaries are proven at one exact head. |

## Current dependency findings at audit head `6b792b615408711fabc3eec5dcff2a1d30abce49`

- The registry and browser runtime now distinguish concrete module dependencies from public provided/required contracts. `projects.core` provides `projects.list.read`, `projects.context.select` and `projects.toolbar.extend`; Portfolio requires list/context contracts rather than the concrete Projects module ID.
- `projects.list.read` has one Projects-owned provider with immutable snapshots, refresh deduplication and loaded-state reporting. Projects/Core and Portfolio consume that contract instead of reading ambient `projects`/`window.projects`.
- `web_capabilities.py` routes modular initial project loading through `projects.list.read`; it copies the returned snapshot into the legacy `projects` array only as a compatibility mirror. The direct `/api/v1/projects` bootstrap remains only as the non-modular fallback.
- Home's managed zero-trust renderer now resolves `projects.list.read` and renders its visible Project metric/cards from a copied contract snapshot. Its `projectItems()` helper retains the ambient `projects` array only as a non-modular compatibility fallback; focused tests reject ambient `projects` as the managed Home render source.
- Project Creation and Project Lifecycle now require `projects.list.read` for refresh and no longer copy refreshed snapshots into ambient `projects` or call `projectOptions()` themselves. The web compatibility boundary alone bridges `fieldora:project-list-changed` into the legacy `projects` mirror and selector refresh while those consumers remain.
- `projects.context.select` has a Projects-owned provider around the existing public Projects module API. Portfolio, Capacity and Research consume that contract for project-context interactions instead of reading the Projects implementation directly.
- `projects.toolbar.extend` is a Projects-owned cockpit extension contract. Capacity and Research register their cross-module entry points through it instead of querying the Projects cockpit DOM or following `projects.core` mount/unmount lifecycle.
- Capacity and Research now declare no concrete dependency on `projects.core`; both require `projects.context.select` and `projects.toolbar.extend`. Focused registry tests prove each consumer can validate against a replacement Projects provider implementing those contracts. This is meaningful P11/P12 evidence, but full runtime Projects replacement/removal is not yet certified.
- Portfolio no longer calls the transitional global `window.loadPortfolio`: it refreshes `projects.list.read`, owns phases/tasks/sprints loading through governed API calls, stores that work-data snapshot in its own render root, and renders its views module-locally. Focused Portfolio tests also reject `window.projects`, `window.openProject` and `window.loadPortfolio`; the exact-head modular-shell and wider workflow set are green for this slice. Portfolio still reads the ambient `window.me`, so its broader shared-service cleanup is not complete.
- P09 final-shell retirement now removes the base Projects-page `showPage("projects") → loadPortfolio()` call plus legacy Portfolio refresh, scope and view-button handlers once the relevant module owners are present. Focused composition tests prove those exact legacy snippets are absent from finalized `/app.js` while their owners remain.
- The surviving legacy work editor is not yet removable: its visible task fields still include explicit phase/parent, sprint, manual-estimate and realized inputs that the newer Project work-actions editor does not fully replace. Its successful-save refresh has nevertheless been decoupled from concrete `loadPortfolio()` ownership: Project Core finalization rewrites that one success path to emit `fieldora:project-work-changed`, which Project Core already consumes to reload owned work data. Focused finalizer evidence is green at this audit head.
- Navigation and desktop-cockpit compatibility patches still contain `loadPortfolio` references in their source, but those Portfolio/Projects-owned compatibility ranges are stripped by the finalizer when the corresponding owner markers are present. Their source presence is therefore not sufficient evidence that the finalized shell still consumes the base global; exact final-shell tracing remains required before deleting `loadPortfolio()` wholesale.
- Research no longer consumes the ambient Project list as an active managed integration surface: when the Research owner marker is present, finalization removes the base `cards("project-list",projects,...)` renderer and its `#project-list` click handler. The surviving Home click handler still reaches the globally rebound `openProject`, whose managed adapter selects through `projects.context.select` before invoking the legacy detail renderer for presentation.
- The Research adapter, Research record bridge, export path and record-editor prefill do not read or write `selectedProject`. Finalization now also removes the legacy `selectedProject=id` assignment from the compatibility `openProject(id)` renderer while preserving that renderer's visible `#project-detail` presentation. Focused modular-shell tests prove this retirement is bounded.
- Remaining ambient coupling keeps P08 open: `loadBase()` still seeds the legacy `projects` mirror for compatibility; Projects/Core still writes the transitional `selectedProject` and `#work-project` mirrors; and the compatibility `projectOptions()` wrapper/`fieldora:project-list-changed` bridge remains live for surviving legacy selectors. Exact final-shell tracing is still required before deleting either mirror wholesale.
- Research's bounded Projects integration intentionally requires only `projects.context.select` and `projects.toolbar.extend`; it does not require `projects.list.read`. The legacy Research list surface is now retired under the owner marker rather than being migrated into a new Research list dependency.
- Exact finalized-shell tracing is still required before deleting any remaining global wholesale: each occurrence must be classified as stripped/dead, transitional mirror write, or surviving consumer, then migrated behind a required contract, optional contract, or runtime data/event boundary as appropriate.
- Qt Project Management obtains accessible projects through `WorkspaceContext.accessible_projects(...)`; its `select_project()` refreshes the accessible list and returns `False` when the requested project is absent. This supports the web stale/inaccessible-selection guard as parity behavior.
- WEB-056 still lacks runtime Projects list/context certification for strict `My work`, context switching, stale/inaccessible IDs and Projects error/recovery. P13 remains open.

## Dependency direction

```text
Shell/Registry
  ├─ capability + lifecycle contracts
  ├─ auth/navigation/notification contracts
  └─ Projects capability
       ├─ ProjectListProvider        provides projects.list.read
       ├─ ProjectContext             provides projects.context.select
       ├─ ProjectToolbarExtensions   provides projects.toolbar.extend
       ├─ ProjectScope
       ├─ ProjectHierarchy
       ├─ ProjectInspector
       └─ ProjectWorkData adapters

Portfolio
  └─ requires projects.list.read + projects.context.select

Capacity / Research
  └─ require projects.context.select + projects.toolbar.extend
     (no concrete `projects.core` dependency)
```

## Working order

Work A01 → A08 before treating feature extraction as certified. For the current Projects requirement, proceed P01 → P08 first, then P09 → P17 certification. Keep changes small: introduce/validate one contract boundary, migrate one consumer, prove removal/replacement behavior, then continue. Do not bundle unrelated parity repairs into an architecture slice.

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
| A05 | [ ] | Service/API adapters | A03 | Presentation modules receive service/API adapters through stable interfaces; transport details are not feature globals. |
| A06 | [ ] | State ownership | A03,A04 | Every shared state field has one owner; consumers use snapshots/read contracts/events and cannot mutate owner state directly. |
| A07 | [~] | DOM ownership | A01 | Each module owns a bounded render root and does not reach into another module's private DOM. |
| A08 | [~] | Shell decomposition | A01-A07 | Shell performs composition, capability gating, route/history and lifecycle only; feature business behavior is outside the shell. |

## Projects slice — Project list and project context

| ID | Status | Task | Depends on | Completion contract |
|---|---|---|---|---|
| P01 | [~] | Projects capability object | A01-A08 | Projects can mount/unmount behind shell contract without owning unrelated workspaces. |
| P02 | [ ] | Project list provider/object | P01,A05,A06 | Accessible projects have one owner/provider; consumers do not read ambient `projects`. |
| P03 | [~] | Project context object | P02,A04,A06 | Selected project is validated against accessible list before publication; inaccessible/stale IDs do not mutate context. |
| P04 | [~] | Project scope/filter object | P02 | `My work` and `All accessible` are explicit scope semantics; zero `My work` matches remains zero. |
| P05 | [~] | Project hierarchy/tree object | P03,A05 | Hierarchy consumes project-context and work-data contracts; it does not own project selection. |
| P06 | [~] | Project inspector object | P03,P05 | Inspector consumes selected-record contract and can be replaced without changing hierarchy/context. |
| P07 | [~] | Project work-data adapters | P03,A05 | Phases/tasks/sprints/allocations/evidence are accessed behind declared service contracts. |
| P08 | [ ] | Remove mutable global Projects coupling | P02-P07 | `projects`, `selectedProject`, direct feature globals and equivalent ambient state are no longer module integration APIs. |
| P09 | [~] | Retire legacy Projects wiring | P01-P08 | Final `/app.js` contains one owner per migrated responsibility and no competing legacy listeners. |
| P10 | [ ] | Module removal test | P01-P09 | Remove/disable Projects module and prove shell plus unrelated modules still boot/function. |
| P11 | [ ] | Module replacement test | P01-P09 | Substitute a minimal Projects provider implementing the same public contracts without shell/consumer changes. |
| P12 | [~] | Dependency contract tests | A01-P11 | Duplicate ownership, missing providers and undeclared concrete coupling are rejected where mechanically testable. |
| P13 | [ ] | Browser behavior certification | P02-P07 | Chromium/Firefox/WebKit cover list, context switch, strict empty `My work`, stale/inaccessible selection, error and recovery. |
| P14 | [~] | API/security certification | P02,P07 | Accessible-list filtering, cross-org exclusion and scoped authorization are proven independently of UI hiding. |
| P15 | [~] | Persistence/domain proof | P07 | Visible project result traces through governed API/application contract to authoritative persisted/domain state. |
| P16 | [ ] | Eight-link certification chain | P01-P15 | capability → visible entry point → input validation → owned wiring → API/application call → persisted/domain outcome → visible result → audit/test evidence. |
| P17 | [~] | Dependency graph maintained | A01-P16 | Required, optional and provided contracts are represented in registry/manifest and this ledger stays current. |
| P18 | [ ] | Certify Project list/context | P01-P17 | Iteration 6 item may move from `[~]` only when behavior and removal/replacement boundaries are proven at one exact head. |

## Current dependency findings at audit head `6379822f4ef579228fb2f5079bbcb179fe709034`

- `WebModuleSpec` declares `dependencies`, but current foundation entries couple Portfolio, Capacity and Research to the concrete module ID `projects.core`. The next foundation slice must introduce provider/consumer contracts so consumers depend on a project-context/list interface, not that implementation.
- Projects/Core already has `mount()`/`unmount()` and emits `fieldora:project-context-changed`, which is useful A01/A04 evidence, but it reads ambient `projects`, `me`, `selectedProject`, `api()` and shared DOM IDs directly.
- `web_capabilities.py` currently owns initial `/api/v1/projects` loading and writes the shared `projects` array, while Projects/Core renders/validates against it. This splits project-list ownership and leaves P02/P08 open.
- Portfolio currently reads `window.projects`/`window.me` and calls `window.loadPortfolio`/`window.openProject`; these are transitional concrete/global dependencies and must be replaced by declared contracts.
- Qt Project Management obtains accessible projects through `WorkspaceContext.accessible_projects(...)`; its `select_project()` refreshes the accessible list and returns `False` when the requested project is absent. This supports the web stale/inaccessible-selection guard as parity behavior.
- The current WEB-056 cross-browser workflow does not certify Projects list/context semantics and does not exercise strict `My work`, context switching, stale/inaccessible IDs or Projects error/recovery. P13 remains open.

## Dependency direction

```text
Shell/Registry
  ├─ capability + lifecycle contracts
  ├─ auth/navigation/notification contracts
  └─ Projects capability
       ├─ ProjectListProvider
       ├─ ProjectContext
       ├─ ProjectScope
       ├─ ProjectHierarchy
       ├─ ProjectInspector
       └─ ProjectWorkData adapters

Portfolio / Capacity / Research
  └─ require ProjectContext/ProjectList contracts
     (never require `projects.core` implementation or its private DOM/state)
```

## Working order

Work A01 → A08 before treating feature extraction as certified. For the current Projects requirement, proceed P01 → P08 first, then P09 → P17 certification. Keep changes small: introduce/validate one contract boundary, migrate one consumer, prove removal/replacement behavior, then continue. Do not bundle unrelated parity repairs into an architecture slice.

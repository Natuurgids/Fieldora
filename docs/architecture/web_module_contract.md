# Web module contract

Every web functional module must document and test this contract before parity work is considered complete.

## Identity

- **Module:** stable functional name.
- **User intent:** the job the user is trying to complete.
- **Desktop reference:** Qt workflow(s), commands, dialogs or views that define expected behavior.
- **Owner:** the web module that owns the DOM and action wiring for this function.

## Inputs

List every input explicitly:

- user-entered fields;
- selected entity IDs;
- current organization/project/context;
- capability/authorization booleans;
- API data required to render;
- environment/runtime state;
- browser capabilities where relevant;
- optional vs required values;
- validation and normalization rules.

Inputs must not be obtained through undocumented global variables or unrelated modules' private DOM state.

## Outputs

List every observable output explicitly:

- rendered state;
- API requests;
- created/updated/deleted domain records;
- emitted module events;
- navigation/selection changes;
- asynchronous job IDs/progress;
- downloads or generated artifacts;
- status/error messages;
- audit/provenance effects.

## Integration points

For every integration point record:

- provider module/service;
- public selector, event, function, endpoint or application port used;
- data shape;
- lifecycle expectation;
- whether the dependency is required or optional;
- failure behavior when unavailable.

A module must not reach into another module's internal DOM to drive behavior unless that selector is intentionally declared as a public integration point.

## Environment dependencies

Record dependencies such as:

- authenticated session;
- PBAC/capability requirement;
- organization/project context;
- server feature flag;
- configured storage service;
- worker/job runner availability;
- online/offline state;
- filesystem/browser file APIs;
- model/runtime availability;
- TLS or deployment profile assumptions.

The UI must fail closed or present an explicit unavailable state when a required dependency is absent.

## Lifecycle

Every module must define:

- mount/init entry point;
- idempotency behavior;
- DOM elements it owns;
- listeners it installs;
- listeners/resources it removes on teardown, if teardown is supported;
- refresh/reload behavior;
- how dynamically inserted controls receive action wiring.

Repeated initialization must not duplicate controls, event listeners or API calls.

## Authorization

Document separately:

1. **Disclosure rule** — whether the user may see the workspace/control.
2. **Action rule** — authority required to execute it.
3. **Server enforcement** — the API/application layer that independently authorizes the request.

Hidden or disabled UI is never the authorization boundary.

## Error and asynchronous behavior

Define:

- validation errors;
- authorization failures;
- not-found/conflict states;
- network/runtime failures;
- retry behavior;
- cancellation behavior;
- long-running job progress;
- stale-data handling;
- success feedback.

## Tests required

At minimum:

1. **Contract test** — inputs, outputs and declared dependencies are represented in the module.
2. **API/application test** — requests reach the intended backend behavior and preserve domain/security rules.
3. **Browser action test** — user action produces the expected request/result.
4. **Visible-control wiring audit** — every visible button/control has an owned direct, delegated or listener action contract.
5. **Parity test** — desktop behavior and web behavior agree for the audited function, including failure states that matter.
6. **Cross-browser test** where browser behavior is relevant.

## Completion record

Each audited module ends with:

- **Parity:** full / partial / intentionally different / missing.
- **Implementation decision:** keep / refactor / rebuild.
- **Known gaps:** explicit list.
- **Dependencies certified:** explicit list.
- **Tests:** exact test files/workflows.
- **Exact commit SHA:** SHA on which the evidence was produced.

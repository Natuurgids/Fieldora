# Identity, Contracts, and PBAC Architecture

## Status

Fieldora 0.08.13 provides the local domain, persistence, administration, decision, and
audit foundation plus server-enforced sessions, service/device credentials, pinned
OIDC verification, and project contract grants. The local desktop owner can manage
the foundation in **Settings → Access & Contracts**; trusted server operators can use
the local administration command boundary.

Fieldora 0.08.16 also exposes authenticated contract administration through `/api/v1`.
It does not infer authority from a UI role or OIDC claim: every create, list, inspect,
and status operation requires `administer_contracts` PBAC for the target organization
and project. Lists are cursor-bounded and filtered per contract; denied and unknown
contract object routes both return 404. Remote suspension and termination take effect
at the next policy decision.

Fieldora 0.08.17 exposes those operations in a separate Contracts section of the
limited web client. Client navigation is presentation, not authorization. Contract
values are rendered as text, bearer tokens remain session-only, and every mutation
still crosses the server PBAC boundary.

## Approval quorums

Fieldora 0.08.19 can create a contract with `approval_required` and a bounded
`required_approvals` quorum from one to ten. It remains `proposed`, creates no
policies, and grants no access while distinct authorized organizational identities
record approvals. Approval requires the separate `approve_contracts` action. The
requester cannot approve their contract, disabled identities cannot approve, and an
identity cannot approve twice. Every approver and timestamp are retained. Final
activation and all derived policies are written in one transaction; lifecycle changes
cannot bypass approvals that remain outstanding.

## Delegated approval queue

Fieldora 0.08.20 exposes proposed contracts through a separate cursor-bounded
approval queue. Every candidate must pass `approve_contracts` PBAC for its
organization and project before any contract data is returned. The queue does not
require or imply `administer_contracts`; it excludes the requester, identities that
already approved the proposal, and contracts whose quorum is complete. The approval
operation repeats the authoritative PBAC decision and all quorum checks.

## Expiry reminders

Fieldora 0.08.21 provides a read-only, cursor-bounded expiry queue for active
contracts ending within a caller-selected one-to-365-day window. Every candidate
must pass `administer_contracts` PBAC before disclosure. Expired, inactive,
malformed-date, out-of-window, and unauthorized contracts are omitted. Any subsequent
suspension, termination, or replacement remains a separate authorized operation.

## PBAC model

Policy-based access control is the overarching model. A request contains:

- subject identity;
- action;
- resource type and optional object identity;
- organization and project;
- declared purpose;
- requested fields;
- environmental or data attributes;
- evaluation time.

Policies may be sourced from:

- a direct subject rule;
- an assigned role;
- a versioned contract;
- an object-specific grant or restriction.

RBAC, ABAC, contracts, and object grants are therefore policy inputs, not alternative
authorization systems.

## Decision order

1. Unknown or disabled identities are denied.
2. Cross-organization access is denied unless the identity carries the explicit local
   platform-administrator attribute.
3. Direct and nested group memberships are resolved; candidate role assignments for
   the subject and its groups are limited to the request organization and project.
4. Policies are matched by subject/role, action, resource, object, organization,
   project, purpose, fields, conditions, validity period, and enabled state.
5. Contract policies additionally require an active contract at evaluation time.
6. Any matching explicit deny overrides matching allows.
7. At least one allow is required; otherwise default deny applies.
8. Every decision is appended to the decision audit.

## Project contract grants

The server administration command can create one contract and its project-scoped
policies from an explicit right list. Rights are not interpreted as a wildcard:
`view`, `search`, `upload`, `export`, `view_job`, and `download_export` each map to
specific resource types and purposes. The subject must belong to the contract
organization, project scope is mandatory, and timezone-aware dates are normalized to
UTC. Suspending or terminating the contract invalidates every derived allow at the
next PBAC decision without deleting historical policy or decision records.

The application enforcement contract exposes both `decide()` and fail-closed
`require()`. Later APIs, search, exports, background jobs, and data-pack builders must
call `require()` before disclosure or mutation.

## Database boundary

Organizations, identities, nested group memberships, role assignments, contracts,
policies, and audit events belong to the independent authoritative
`subsystems/access-control.sqlite3` database. It is registered for
migrations, integrity checks, Maintenance inventory, verified backup, and restore
payloads. It never joins directly to Library or Science tables; policies use stable
organization, project, subject, and resource public IDs.

## Audit properties

The repository exposes append and bounded reads for audit events; it provides no
update or delete operation. Each event records the request, decision, reason, and
matched policy identities. Events are canonically encoded and linked with SHA-256;
verification detects changed, removed, reordered, or disconnected rows. Existing
events are sealed once when the chain migration first runs. External anchoring,
retention/legal hold, and independent audit storage remain production work.

## Deliberate limits

- Desktop and local command administration rely on control of the host. The remote
  contract API is enforced, but a dedicated administration client and delegated
  approval workflow are not yet provided.
- A hidden button is not an enforcement point.
- Local policies do not claim to protect files from the machine owner.
- Contract records are operational policy inputs, not electronic signatures.
- Contract records and local commands are not a substitute for electronic signatures,
  delegated remote administration, MFA, TLS, or production tenant operations.

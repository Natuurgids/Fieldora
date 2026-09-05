# Fieldora Access Contracts and Information Barriers

Fieldora Library evidence is preserved independently of projects, but access is governed by explicit contracts. A contract may apply to an individual Library asset or to an entire Collection/Dataset.

## Intake defaults

- Administrator or installation-wide generic service: unrestricted/all-access by default. In this context `all-access` means that no additional data-contract wall is imposed beyond normal authentication/PBAC; it does **not** mean public or anonymous access.
- Organization service: restricted automatically to its organization.
- Contracted phone, Aperture client, field device, or similar client: inherits the supplied contract.
- Project member: must choose one project from their actual memberships; project contract terms govern that intake.
- Ordinary uncontracted user outside a project: organization-scoped by default.

The sender/source remains the sender/source. Sharing evidence with another organization or project never rewrites the evidence provenance, owning/source organization, source project, or import history.

## Contract subjects

Contracts and contract replacements may target:

- one individual Library asset; or
- one complete Collection/Dataset.

Changing a collection contract does not require copying or re-importing the collection. The governed evidence remains the same; only its effective access contract changes.

An administrator may therefore import material as unrestricted and later issue a replacement contract limiting one asset or a whole collection to a specific organization, project, organization/project pair, or other permitted contract target.

## Contract precedence

Access rules are cumulative and restrictive rules prevail.

An evidence owner may have an upstream evidence-owner contract for an asset or Collection/Dataset. That contract is the maximum sharing envelope for the governed evidence. A source project owner may approve sharing from the project only inside that envelope.

For example, if the evidence-owner contract permits only Organization A, a project owner cannot share the evidence with Organization B even after performing the required two project-owner attestations. The upstream evidence-owner restriction prevails.

Conversely, if the evidence-owner contract permits Organization B, the project owner may approve a narrower grant to a specific project inside Organization B, subject to the normal project approval/signature requirements.

The effective rule is therefore:

`PBAC authority AND evidence-owner contract AND project/data contract AND collection barriers`

Every applicable layer must permit the operation. No downstream contract can widen past an upstream restriction.

## Widening and narrowing

Narrowing/replacing an unrestricted administrator contract is an explicit administrative operation. For example:

`all-access -> Organization A only`

Widening access is a contract amendment. Standard user/supervisor choices include another project, the entire organization, another organization, or a specific project in another organization. Administrative/bulk workflows may specify multiple organization/project targets in one governed contract.

Cross-project or cross-organization access never copies the asset and never transfers provenance or ownership. It creates an additional governed recipient access path to the same source-owned Library evidence.

A recipient must still have normal authority in the recipient organization/project named by the contract. The source-side contract grants eligibility to receive access; it does not impersonate the recipient as the uploader or source.

## Project-owner approval

A project member may request broader sharing, but the request grants no access by itself. Project-governed data may be shared more widely only after approval by the recorded owner of the source project and only when the evidence-owner contract does not block the requested target.

When the project owner permits wider sharing, Fieldora requires two distinct owner attestations/signatures for that contract amendment before it becomes effective. Both attestations must be made by the recorded source-project owner. This rule also applies when the project owner initiated the sharing request.

If an evidence-owner contract blocks the requested sharing scope, project-owner approval cannot override it and the amendment remains ineffective.

## Audit and transaction integrity

Contract governance is not merely logged after the fact. Mutations that affect the authoritative information barrier are transactionally coupled to Fieldora's tamper-evident access audit chain wherever they share the authoritative access database.

Contract creation, replacement, sharing requests, owner attestations, activation, supersession, evidence-owner ceiling assignment, source-project owner assignment, contract-required intake state, and Collection/Dataset barrier membership changes are sealed in the audit chain before the governing transaction commits.

If the audit event or its chain hash cannot be persisted, the governance mutation is rolled back. Fieldora must not accept an authoritative access-contract change that it cannot durably account for.

This audit coupling applies to the SQLite reference access store and the PostgreSQL parity store through the same repository contract. PostgreSQL serializes audit-chain appends under its access-audit advisory transaction lock.

# Fieldora Access Contracts and Information Barriers

Fieldora Library evidence is preserved independently of projects, but access is governed by explicit contracts. A contract may apply to an individual Library asset or to an entire Collection/Dataset.

## Intake defaults

- Administrator or installation-wide generic service: unrestricted/all-access by default.
- Organization service: restricted automatically to its organization.
- Contracted phone, Aperture client, field device, or similar client: inherits the supplied contract.
- Project member: must choose one project from their actual memberships; project contract terms govern that intake.
- Ordinary uncontracted user outside a project: organization-scoped by default.

## Contract subjects

Contracts and contract replacements may target:

- one individual Library asset; or
- one complete Collection/Dataset.

Changing a collection contract does not require copying or re-importing the collection. The governed evidence remains the same; only its effective access contract changes.

An administrator may therefore import material as unrestricted and later issue a replacement contract limiting one asset or a whole collection to a specific organization, project, organization/project pair, or other permitted contract target.

## Widening and narrowing

Narrowing/replacing an unrestricted administrator contract is an explicit administrative operation. For example:

`all-access -> Organization A only`

Widening access is a contract amendment. Standard user/supervisor choices include another project, the entire organization, another organization, or a specific project in another organization. Administrative/bulk workflows may specify multiple organization/project targets in one governed contract.

Cross-project or cross-organization access never copies the asset. It creates an additional governed access path to the same Library evidence.

## Project-owner approval

A project member may request broader sharing, but the request grants no access by itself. Project-governed data may be shared more widely only after approval by the project owner.

When the project owner permits wider sharing, Fieldora requires two distinct owner attestations/signatures for that contract amendment before it becomes effective. This rule also applies when the project owner initiated the sharing request.

All contract creations, replacements, amendments, approvals, signatures, activation, supersession, and revocations are auditable governance events.

# Portable Project Packages

## Status

Fieldora 0.06 implements the first offline project exchange format. It is intended for
deliberate transfer between trusted standalone installations. It is not yet a
contract-authorized or cryptographically signed server data pack.

## Format

A `*.fieldora-project.zip` archive contains exactly:

- `manifest.json`;
- `records.json`.

The manifest declares `fieldora.portable-project` format version 1, producer version,
project identity, record count, reference count, redaction decisions, and the SHA-256
of `records.json`. ZIP members use deterministic names, timestamps, permissions, and
JSON ordering. Import rejects extra members, members larger than 100 MB, unsafe
compression ratios, unsupported versions, and checksum mismatches.

## Project scope

The package can contain:

- one project;
- stages and project activities;
- required resources and budget;
- project dossiers;
- whiteboards attached to those dossiers;
- whiteboard elements and dossier-to-board links;
- optionally, stable references to Library assets.

Original photos, sounds, videos, and documents are always excluded in 0.06. A user must
explicitly choose whether stable Library references are retained. The redaction section
records that choice.

## Import

Import always presents a preview before mutation. Collision policies are:

- stop without changes;
- keep existing records;
- replace existing records.

The repository applies the resulting snapshot atomically. Any validation, collision,
revision, or persistence error restores the in-memory snapshot and leaves no partial
database commit.

Removing an imported project removes its project-scoped dossiers and planning records.
Whiteboards are removed only when no remaining dossier links to them. Library assets
are never deleted.

## Next security step

Fieldora 0.08.11 can generate this same redacted format as a durable server job.
Submission, job-result visibility, and package download use separate PBAC actions; the
contained result has SHA-256 and expiry metadata and no filesystem path is disclosed.

Cryptographic signing, institutional trust roots, encryption, contract-derived grants,
revocation, automated expiry deletion, and media renditions remain governed data-pack
work in later phases. They must not be implied by this checksum-only exchange format.

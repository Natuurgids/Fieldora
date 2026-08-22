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
Fieldora 0.08.12 adds separately authorized revocation and physical cleanup of revoked
or expired server payloads while retaining lifecycle metadata.

Fieldora 0.08.14 can add a detached Ed25519 attestation over the SHA-256 of the entire
archive. Detaching the signature preserves the strict two-member ZIP format and keeps
older importers compatible. The attestation is downloaded separately under the same
`download_export` PBAC gate and verified against an explicitly selected trusted-key
file. Unsigned packages remain valid portable packages but do not prove an issuer.

Fieldora 0.08.15 optionally wraps the complete ZIP in a recipient-encrypted envelope.
The recipient public JSON key uses X25519; each export uses an ephemeral X25519 key,
HKDF-SHA256, and streaming AES-256-GCM. The private recipient key never enters the
server job. When signing is configured, the detached Ed25519 attestation covers the
ciphertext so authenticity can be verified before decryption. Decryption publishes
the ZIP only after GCM authentication succeeds and never overwrites an existing file.

Institutional trust exchange, multi-recipient envelopes, key rotation/revocation,
managed recovery, electronic contract execution, and media renditions remain governed
data-pack work in later phases.

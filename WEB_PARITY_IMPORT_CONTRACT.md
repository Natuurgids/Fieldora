# Fieldora web parity — import and evidence identity contract

Status: implementation contract for `WEB-006` through `WEB-025` in `WEB_DESKTOP_PARITY_PLAN.md`.

This document records the detailed source trace so a future session can resume the web import rebuild without relying on chat history.

## 1. Authoritative desktop import path

The desktop is not implementing import rules in Qt widgets. `src/natureai_next/bootstrap/cli.py` composes the production `ImportService` from `src/natureai_next/application/import_service.py` with:

- `SqliteUnitOfWork`
- `DirectorySourceScanner`
- `StreamingFileFingerprinter`
- `ShardedManagedFileStore`
- image/RAW decoders and metadata readers
- XMP sidecar resolution/storage
- the durable derivative scheduler

`src/natureai_next/ui/qt/importing.py` is therefore a presentation adapter: it asks the service to `plan()` and then `execute()` the resulting deterministic plan.

This is the behavior the web path must converge on at the application/domain boundary. Browser JavaScript must not become a second import engine.

## 2. Existing desktop duplicate contract

The shared domain model in `src/natureai_next/domain/importing.py` defines the relevant decisions:

- `IMPORT_NEW_ASSET`
- `ATTACH_TO_EXISTING_ASSET`
- `SKIP_EXACT_DUPLICATE`
- `REJECT_SOURCE`

and the duplicate policies:

- `SKIP`
- `ADD_FILE_INSTANCE`

The desktop `ImportService.plan()` performs these steps for each selected source:

1. classify the source kind;
2. reject obviously unsupported formats;
3. detect an unchanged previously known source where possible;
4. calculate the authoritative fingerprint;
5. probe/validate supported media where needed;
6. find existing file instances by SHA-256;
7. compare normalized source path and storage policy;
8. choose new asset, attach, or exact-duplicate skip;
9. persist the deterministic import plan before execution.

For an existing hash:

- same physical path + same storage policy => `SKIP_EXACT_DUPLICATE`;
- same bytes but a materially different path or storage policy => `ATTACH_TO_EXISTING_ASSET`;
- no existing hash => `IMPORT_NEW_ASSET`.

For duplicate hashes inside the same new plan, the first item creates the asset; following items are skipped under `SKIP` or attached under `ADD_FILE_INSTANCE`.

Execution re-fingerprints the source before committing it, protecting the plan from a file that changed after planning.

## 3. Confirmed server/web divergence

The current browser path in `src/natureai_next/server/browser_functionality_web.py` implements its own transport/import loop:

- JavaScript reads the complete browser `File` into an `ArrayBuffer`;
- JavaScript computes SHA-256;
- ordinary selected files use `/api/v1/uploads` one file at a time;
- folder selection uses the staged-submission API instead;
- the browser directly coordinates chunks and completion.

The underlying `GovernedMediaStore` in `src/natureai_next/server/media.py` verifies the declared SHA-256 correctly, but after successful verification it always creates a fresh UUID and a fresh governed-media record. There is no content-identity lookup before the new `media_id` is allocated.

The PostgreSQL metadata adapter in `src/natureai_next/server/postgres_media.py` likewise has no content-identity uniqueness rule or lookup. Its `governed_media` table has a primary key on `media_id` and a unique `relative_path`, but SHA-256 is only a checked text column.

That explains the runtime observation: re-uploading identical bytes can create another evidence record.

## 4. Evidence identity rules to implement

### 4.1 Byte identity

Within an organization, byte identity is based on verified SHA-256 plus size. The server must calculate or verify the hash authoritatively before a persistence decision is final.

Filename, browser path, MIME hint, project selection and upload UUID are not evidence identity.

### 4.2 Exact retry / repeated transfer

If the same verified bytes are submitted again with no new provenance or governed relationship, the operation is idempotent:

- no new evidence identity;
- no duplicate object bytes;
- no synthetic observation;
- return the existing evidence identity and a result state such as `skipped` / `existing`.

### 4.3 New file instance / provenance

If the bytes are the same but the new submission represents a materially different source instance that Fieldora is expected to preserve, attach source-instance/provenance information to the existing evidence identity. Do not create another evidence identity.

The remote/web equivalent must not persist client host filesystem paths as trusted server paths. Browser relative paths may be retained only as submission provenance where policy allows.

### 4.4 New project/context

If existing evidence is intentionally introduced into another authorized project or collection, create a governed association to the existing evidence identity. `src/natureai_next/server/media_links.py` already states this model explicitly: the media object belongs to the organization Library and associations describe participation in projects, collections, dossiers, submissions and review cases without copying bytes or changing media identity.

Therefore the long-term server model must stop treating `project_id` on a media row as evidence identity.

### 4.5 Observation semantics

A second file transfer is not automatically a second scientific observation.

Create another observation only when the submission carries new observation/encounter context (for example time/place/specimen/event data). That observation may point to the same evidence bytes.

## 5. Database safety requirement

Application-level lookup alone is insufficient under multi-user web concurrency.

A canonical evidence identity constraint must be enforced transactionally. The preferred server shape is an organization-scoped canonical evidence row with a uniqueness constraint equivalent to:

`UNIQUE (organization_id, sha256, size_bytes)`

If later requirements prove that byte-identical evidence must remain distinct for a narrowly defined governance reason, that must be represented as a separate identity/context concept, not by silently weakening the content-addressed uniqueness rule.

The create path must handle the concurrent-insert loser by reading and returning the canonical row, not by surfacing an internal database error.

SQLite/reference-server behavior and PostgreSQL behavior must be certified with the same contract tests.

## 6. Web intake target architecture

Single-file, multi-file and folder intake must use one server-side application contract.

Browser responsibilities:

- select files/directories;
- provide stable client item IDs and relative-path hints;
- stream chunks;
- optionally calculate a client checksum for early transport feedback;
- render server progress and per-item results.

Server/application responsibilities:

- authoritative content verification;
- source classification;
- duplicate planning;
- validation/probing;
- evidence identity decision;
- governed associations;
- audit;
- persistence;
- staging cleanup;
- deterministic summary.

The ordinary-file `/uploads` path and folder staged-submission path must not retain different evidence semantics.

## 7. Mixed evidence batches

A batch is a collection of evidence candidates, not a photo-only operation.

The existing domain classifier already includes photo, RAW photo, sound, video, document and sidecar kinds. The web batch contract must preserve heterogeneous batches and leave room for registered specialist evidence types such as DICOM/X-ray scans.

Unknown data must not automatically become trusted generic evidence. Specialist types need explicit classification/validation registration.

## 8. Immediate implementation sequence

### Slice I1 — characterize and prevent exact duplicate evidence

1. Add server tests proving two completed uploads of the same verified bytes in the same organization/context do not create two evidence identities.
2. Add equivalent PostgreSQL repository coverage.
3. Introduce canonical content lookup/uniqueness at the metadata boundary.
4. Make upload completion return the canonical existing record on an idempotent repeat.
5. Ensure abandoned temporary upload bytes are removed.

This is the narrow first fix; it must not invent project-link semantics inside `GovernedMediaStore`.

### Slice I2 — canonical associations

1. Route project/collection context through `MediaAssociationRepository` (or a promoted application-level equivalent).
2. Existing bytes + new authorized project => association, not duplicate media.
3. Existing bytes + already existing association => no-op.
4. Audit new evidence vs association vs no-op distinctly.

### Slice I3 — one remote intake service

Create an application-level remote intake command/service that expresses the same domain decisions as desktop `ImportService` but accepts staged/streamed server-side objects rather than trusted local `Path` instances.

Both `/uploads` and staged folder/bulk routes become transport adapters for that service.

### Slice I4 — reproduce and fix multi-file fetch failure

Add a browser test that uses the real multi-select control and records the exact failing request before changing behavior. Then move the control onto the unified intake service.

### Slice I5 — heterogeneous bulk + progress

Certify mixed photo/document/audio/video batches, partial failures, cancellation, resumability and Activity/Job progress.

## 9. Do not do

- Do not solve deduplication only in JavaScript.
- Do not trust filename or relative path as content identity.
- Do not create an observation merely because a byte-identical file was submitted again.
- Do not create a second media/evidence row solely to represent another project.
- Do not add sleeps/browser-specific delays to hide a transport race.
- Do not remove PBAC checks to make bulk import easier.
- Do not collapse server concurrency correctness into desktop single-process assumptions.

## 10. Completion evidence for WEB-006 / WEB-007

The authoritative desktop path and current web/server divergence are now traced in source. `WEB-006` (trace authoritative duplicate flow) and the analysis portion of `WEB-007` (canonical byte identity) are complete at the design level.

Implementation is not `DONE` until the transactional server uniqueness/idempotency tests are green on both SQLite/reference metadata and PostgreSQL metadata.

# Fieldora staged ingestion

Fieldora separates untrusted delivery from scientific catalog publication.
The legacy `/api/v1/uploads` endpoint remains a direct governed-media endpoint;
large or multi-user submissions use `/api/v1/staged-submissions`.

## State model

Submission states:

`uploading → scanning → validated | validated_with_rejections → processing → ready_to_publish`

Files move independently through:

`uploading → uploaded → validated | rejected → processing → processed`

Quarantine objects are not returned by `/api/v1/media`. A staged record keeps
the submitting identity, organization, project, access-contract ID, purpose,
relative source path, verified checksum, validation evidence, and eventual
published media identity.

## API workflow

1. `POST /api/v1/staged-submissions`
2. `POST /api/v1/staged-submissions/{submission_id}/files` for each manifest item.
3. `PUT /api/v1/staged-files/{staged_file_id}` with contiguous `Content-Range`
   chunks of at most 8 MiB.
4. `POST /api/v1/staged-submissions/{submission_id}/seal`.
5. Validation workers verify size, SHA-256, signature-based media type, archive
   safety, and malware status.
6. Accepted files fan out into bounded `staged.process` jobs. The default batch
   contains 250 files and the hard maximum is 1,000.
7. `GET /api/v1/staged-submissions/{submission_id}` returns per-file evidence
   and progress without disclosing quarantine object paths.

Example:

```json
{
  "project_id": "field-survey-2026",
  "contract_id": "contract-123",
  "purpose": "research",
  "publication_policy": "review",
  "expected_files": 500
}
```

## Security and operation

- Validation is fail-closed. If ClamAV is unavailable or times out, the file is
  rejected and remains outside the media catalog.
- Relative paths reject absolute paths and `..`.
- Declared checksums and sizes are verified after upload.
- File signatures are checked independently of extensions.
- ZIP member counts, expanded size, and member paths are bounded.
- Contract and purpose values are copied into every processing job.
- Only PBAC-authorized project users in the originating organization can
  inspect or continue a submission.

Configure workers with:

```text
fieldora-server --clamav-executable clamscan \
  --staged-import-batch-size 250 ... run-job-worker --continuous
```

API and worker processes must mount the same non-executable quarantine volume
and have the selected scanner installed. PostgreSQL job claims provide
multi-worker fencing. Direct multipart S3 quarantine upload and PostgreSQL
staging metadata remain production-scale adapter milestones; the 0.11.5
reference implementation keeps quarantine bytes behind Fieldora's
authenticated chunk endpoint.

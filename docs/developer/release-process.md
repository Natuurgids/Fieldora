# Release Process

1. Select the approved prior release archive as the immutable baseline.
2. Update `pyproject.toml`, `natureai_next.__version__`, changelog, release notes, and guide version references.
3. Run compile, lint, format, type, architecture, unit, integration, migration, and packaging checks.
4. Confirm no unapproved Version 2 work entered the branch.
5. Regenerate `RELEASE_MANIFEST.json` from the final files.
6. Build a root-layout ZIP and test its integrity.
7. Record the ZIP SHA-256 and retain the previous release for rollback.

A release is not complete unless installation, quick-start, troubleshooting, backup/recovery, developer, and release documentation are packaged and match the implementation.

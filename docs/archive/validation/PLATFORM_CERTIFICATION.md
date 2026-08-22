# Version 2 Platform Certification

Platform certification is a read-only release-hardening operation exposed by the existing Maintenance Center.

It evaluates six sections:

- Core Library
- AI Enrichment
- Taxonomy Reference
- Offline Maps
- Knowledge Engine
- Maintenance Center

Certification does not activate optional subsystem databases that have never been installed, and it never repairs or mutates authoritative data. Results are classified as PASS, WARNING, or FAIL. Warnings from absent optional packages are expected and do not block core-library use.

Full-environment validation remains a release-owner activity. Reports from real installations should include the certification section, displayed findings, operating system, Aperture build, and the user action that triggered the issue.

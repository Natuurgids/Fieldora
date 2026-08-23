# Fieldora Bandit Security Audit

Fieldora runs Bandit as part of Platform server certification. The scanner is a security signal, not a substitute for threat modelling, PBAC/contract tests, dependency review, or runtime penetration testing.

## CI policy

The Platform certification performs three Bandit passes:

1. **Full repository audit** — scans `src/natureai_next` at medium-or-higher severity and medium-or-higher confidence. The JSON report is retained as a CI artifact so existing findings remain visible and can be burned down deliberately.
2. **High-severity repository gate** — any high-severity Bandit finding anywhere in `src/natureai_next` fails certification.
3. **Governed Platform gate** — the security-sensitive server/bootstrap modules introduced or materially changed by the governed Platform work are scanned at medium-or-higher severity and medium-or-higher confidence. Findings in this surface fail certification.

A finding is not globally suppressed merely to make CI green. A narrow `# nosec Bxxx` is acceptable only after the exact data flow is reviewed and the justification is local and durable. Prefer removing the hazardous primitive or proving a bounded allow-list in code.

## Initial full-repository baseline

The first full scan on 2026-08-23 covered approximately 94,145 lines of Python and reported:

- high severity: **0**;
- medium severity: **114**;
- low severity: **138**.

The medium findings were dominated by four categories:

- `B608` dynamic SQL construction. Many are parameterized queries whose dynamic fragments are generated from fixed internal allow-lists/placeholders, but each occurrence must be reviewed rather than globally ignored.
- `B310` `urllib` URL opening. Fixed or prevalidated HTTPS endpoints are often safe, while user/configurable endpoints require explicit scheme/host/redirect validation.
- `B314` standard-library XML parsing of imported data. These are actionable and are being migrated to `defusedxml` in bounded importers.
- `B615` Hugging Face downloads without immutable revision pinning. Model/dataset downloads used by Fieldora must be pinned to reviewed revisions or otherwise verified by an immutable digest/provenance contract.

The first audit therefore found no immediate high-severity Bandit defect, but it established a concrete medium-risk cleanup backlog instead of treating a zero-high result as complete security certification.

## Security invariants relevant to Bandit triage

- External URLs must not gain `file:`, custom-scheme, downgrade, or unreviewed redirect behavior.
- Imported XML is untrusted input even when the file came from a scientific archive or sidecar.
- Dynamic SQL identifiers must originate from fixed internal mappings/allow-lists; data values remain parameterized.
- Model and dataset acquisition is a software/data supply-chain boundary and must preserve revision/digest provenance.
- New governed evidence fails closed when its required access contract is absent or inactive.
- Source evidence ownership/provenance is never rewritten when a recipient organization/project is granted access.
- Evidence-owner restrictions are upstream of project-owner sharing authority and cannot be overridden by downstream approval.

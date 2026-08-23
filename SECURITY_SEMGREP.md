# Fieldora Semgrep OWASP Security Audit

Fieldora runs Semgrep alongside Bandit. The two scanners are complementary: Bandit focuses on Python security patterns, while Semgrep applies broader semantic rules, including the Semgrep Registry OWASP Top 10 ruleset.

## CI policy

The Platform server certification performs two Semgrep OWASP passes over `src/natureai_next`:

1. **Full OWASP audit** — runs the Semgrep Registry `p/owasp-top-ten` ruleset and writes the complete JSON result to `semgrep-owasp-audit.json`, retained as a CI artifact.
2. **Blocking OWASP gate** — runs the same ruleset with `--severity ERROR --error`. Any ERROR-severity OWASP finding, scanner failure, or ruleset-loading failure fails Platform certification.

Semgrep metrics are disabled in CI. The Registry ruleset is retrieved at scan time, so findings may evolve as Semgrep improves the OWASP rules. A newly introduced finding must be reviewed rather than globally suppressed simply to restore a green build.

## Relationship to Bandit

A clean Bandit run is not considered equivalent to a clean Semgrep OWASP run. Platform certification requires both blocking gates to pass. Findings from either scanner are triaged against the same Fieldora invariants: authenticated/PBAC-governed access, fail-closed evidence contracts, explicit information barriers, source provenance preservation, safe parsing, bounded external network behavior, least-authority service identities, and transactional governance auditability.

## Suppression policy

Do not add repository-wide exclusions for a rule merely because it reports existing code. Prefer fixing the data flow. If a finding is demonstrably a false positive, any suppression must be narrow, local, documented, and independently reviewable.

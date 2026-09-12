# Fieldora Semgrep OWASP Security Audit

Fieldora runs Semgrep alongside Bandit. The two scanners are complementary: Bandit focuses on Python security patterns, while Semgrep applies broader semantic rules, including the Semgrep Registry OWASP Top 10 ruleset.

## CI policy

Platform server certification performs two Semgrep OWASP passes:

1. **Full OWASP audit** — runs the Semgrep Registry `p/owasp-top-ten` ruleset over `src/natureai_next` and writes the complete JSON result to `semgrep-owasp-audit.json`, retained as a CI artifact. Existing findings remain visible and are not erased simply to make the build green.
2. **Governed Platform blocking gate** — runs the same OWASP rules at ERROR severity over the security-sensitive Platform/bootstrap/server surface changed by the governed Platform work. An ERROR-severity finding, scanner failure, or ruleset-loading failure in this surface fails Platform certification.

Semgrep metrics are disabled in CI. The Registry ruleset is retrieved at scan time, so findings may evolve as Semgrep improves the OWASP rules. A newly introduced finding must be reviewed rather than globally suppressed simply to restore a green build.

## Initial OWASP baseline

The first full OWASP scan on 2026-08-23 scanned 1,322 tracked targets with the `p/owasp-top-ten` registry configuration and reported two ERROR-severity findings, both in pre-existing process-launch surfaces outside the governed Platform gate:

- `synthesis_core/optional_model_worker.py`: the BatDetect2 adapter passes an externally supplied local source path as an argument to a fixed `sys.executable -m batdetect2 process ...` argument vector.
- `ui/qt/application.py`: the Maintenance Center launcher passes library/ready-file arguments to a trusted executable selected from the running Python environment or installed Fieldora executables.

Both calls use argument vectors rather than a shell command. They remain in the full audit backlog because Semgrep cannot prove the surrounding executable/path trust boundary. They are not globally suppressed or removed from the full report. Their source validation and process-launch contracts should continue to be hardened and independently tested.

The initial scan also exposed timeouts while scanning large vendored/minified Excalidraw JavaScript assets. Those assets remain visible to the full audit; timeout warnings are not treated as evidence of a clean scan.

## Relationship to Bandit

A clean Bandit run is not considered equivalent to a clean Semgrep OWASP run. Platform certification requires the Bandit governed-platform gate and the Semgrep governed-platform gate to pass, while both tools retain repository-wide audit output. Findings are triaged against the same Fieldora invariants: authenticated/PBAC-governed access, fail-closed evidence contracts, explicit information barriers, source provenance preservation, safe parsing, bounded external network behavior, least-authority service identities, and transactional governance auditability.

## Suppression policy

Do not add repository-wide exclusions for a rule merely because it reports existing code. Prefer fixing the data flow. If a finding is demonstrably a false positive, any suppression must be narrow, local, documented, and independently reviewable. Keeping a reviewed legacy finding in the full audit while preventing it from blocking unrelated governed-Platform certification is acceptable only when the blocking surface remains explicit and the finding stays visible as security debt.

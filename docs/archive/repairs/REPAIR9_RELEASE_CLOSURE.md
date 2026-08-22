# Repair 9 release closure

Repair 9 closes audit findings R8-001 through R8-009.

- One installer transaction; no second registration pass.
- Exactly one caller-selected library; no repository-local fallback.
- Pristine archive and exhaustive release manifest.
- Synchronous QThread cleanup on main-window construction failure.
- Strict read-only manifest parsing; normalization is explicit.
- Manifest format and database filename enforced.
- SQLite validation uses `mode=ro` with canonical-path assertion.
- Behavioral regression tests cover installer orchestration and library contracts.
- Unique PEP 440 release identity.

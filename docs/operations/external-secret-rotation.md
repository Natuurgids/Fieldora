# External-secret rotation

Fieldora stores only provider references and rotation state. Secret values remain in
Vault, KMS, or the platform's external-secret provider and must never be passed on a
Fieldora command line.

Production operators use the PostgreSQL backend so every API and worker replica
observes one active version. First create the new provider secret, then stage its
reference:

```text
fieldora-secret-rotation --backend postgresql \
  --postgres-dsn-file /run/secrets/fieldora-governance-dsn \
  stage --purpose oidc-signing --version-id 2026-07 \
  --provider-reference vault://fieldora/oidc/2026-07 \
  --created-at-epoch 1785283200
```

Inspect the current version and record its exact ID. Activation is an optimistic,
serialized operation; `--expected-active-version` must match the current active
version when replacing one:

```text
fieldora-secret-rotation --backend postgresql \
  --postgres-dsn-file /run/secrets/fieldora-governance-dsn \
  activate --purpose oidc-signing --version-id 2026-07 \
  --expected-active-version 2026-04 --activated-at-epoch 1785286800
```

Use `status --purpose PURPOSE` to retrieve the active record and full staged,
active, and retired history. An `active_version_conflict` means another operator
completed a rotation first; inspect status and validate the provider state before
retrying.

Provider rollout, workload reload, overlap windows, and functional verification
remain platform responsibilities. Record the ingress certificate rotation exercise
with `fieldora-record-phase-f-evidence` only after clients have verified uninterrupted
TLS service in the target environment.

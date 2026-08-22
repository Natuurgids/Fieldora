# Phase F production deployment

Fieldora 0.10 introduces a fail-closed production topology contract. The reference
document is `deployment/reference-production.json`; validate a customized copy with:

```console
python scripts/assess_production_deployment.py deployment/reference-production.json \
  --report PHASE_F_DEPLOYMENT_ASSESSMENT.json
```

A configuration-ready result means the declared topology includes redundant APIs and
fenced workers, PostgreSQL failover and PITR, replicated S3-compatible storage,
distributed OpenSearch, TLS ingress, external secret rotation, and safe rolling
upgrades. It does not certify that a provider actually delivered those properties.

Production certification remains `conditional` until signed evidence exists for every
node, service, recovery, upgrade, certificate-rotation, and zone-failure exercise in
the assessment. Exercise identifiers are stable and must not be removed or marked
complete based only on configuration inspection.

Secrets must be referenced from an external provider. They must never be committed to
the deployment document, container image, environment template, test fixture, or
assessment report.

Record provider-generated logs or reports with
`fieldora-record-phase-f-evidence`. The command copies the artifact into the evidence
set and records its digest; later gate evaluation rejects missing or modified
artifacts. All nine passing exercises must refer to the same environment identifier.

The Kubernetes reference base is under `deployment/kubernetes/base`. Before applying
it, an environment overlay must replace the example hostname, pin the Fieldora image
by digest, provision the `fieldora-runtime` secret through the declared external
provider, and bind private PostgreSQL, S3-compatible, and OpenSearch endpoints.
Container builds must pass a verified digest in `PYTHON_BASE_IMAGE`.
`--allow-insecure-http` is intentional only inside the namespace because TLS
terminates at the ingress; the NetworkPolicy limits that listener to ingress traffic.

Both API and worker deployments use PostgreSQL for authoritative metadata and
S3-compatible storage for media and governed export payloads. Local `emptyDir`
volumes contain staging/runtime files only and must never be treated as authoritative
or backed up as the platform data source.

Create a certification session plan before scheduling disruptive exercises:

```console
fieldora-phase-f-certification plan --environment ENVIRONMENT_ID \
  --destination phase-f-certification-plan.json
```

The plan defines required observations and artifact guidance but contains no result
fields. After recording provider evidence, assess the session with:

```console
fieldora-phase-f-certification status --environment ENVIRONMENT_ID \
  --evidence-root deployment/evidence --report phase-f-certification-status.json
```

The status command exits nonzero until every exercise has passing, digest-verified
evidence from that exact environment. Evidence from another environment is reported
as foreign and prevents certification.

# Fieldora Kubernetes baseline

This directory is the minimal infrastructure-as-code baseline for running the Fieldora platform on Kubernetes. It intentionally defines only the application-layer resources that Fieldora owns and keeps cloud-provider infrastructure outside this repository.

## What the base owns

`deployment/kubernetes/base` defines:

- the `fieldora` namespace with Kubernetes restricted Pod Security enforcement;
- API and worker Deployments plus the API Service;
- a dedicated ServiceAccount with automatic token mounting disabled;
- readiness, liveness, and startup probes;
- non-root, read-only container security contexts with Linux capabilities dropped;
- PodDisruptionBudgets for the API and workers;
- a default-deny NetworkPolicy with the explicit application egress ports required by the reference runtime;
- an NGINX-compatible TLS Ingress using a placeholder host.

The manifests reference runtime secrets but do not contain secret material.

## External prerequisites

A deployment environment must provide these independently of the base:

- a Kubernetes cluster and a CNI implementation that enforces NetworkPolicy;
- an ingress controller compatible with the annotations in `base/ingress.yaml`;
- the `fieldora-runtime` Secret containing the PostgreSQL DSN file expected at `/run/secrets/postgresql-dsn`;
- the `fieldora-ingress-tls` TLS Secret;
- reachable PostgreSQL, S3-compatible object storage, and OpenSearch services matching the runtime configuration;
- the Fieldora platform image referenced by the deployment or an environment-specific image override.

Do not commit credentials, private keys, production hostnames, provider-specific account identifiers, or generated Secret manifests to this base.

## Environment customization

Treat `base` as the cloud-neutral application contract. Production environments should use a separate Kustomize overlay or an equivalent deployment layer to replace the placeholder ingress host, image reference, storage endpoints, replica counts, and environment-specific resource sizing.

Render the base with:

```sh
kubectl kustomize deployment/kubernetes/base
```

Rendering does not prove that external dependencies exist; deployment automation must supply and validate those dependencies separately.

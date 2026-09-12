# Kubernetes deployment

Fieldora includes a minimal cloud-neutral Kubernetes baseline under `deployment/kubernetes/`.

## Purpose

The baseline is infrastructure-as-code for running the Fieldora platform in an orchestrated environment. It is deliberately not tied to a specific cloud provider.

## Baseline properties

The certified baseline includes:

- Kustomize composition;
- a dedicated `fieldora` namespace with restricted pod-security labels;
- hardened Fieldora workloads;
- non-root execution and dropped Linux capabilities;
- disabled automatic service-account token mounting;
- readiness, liveness, and startup probes;
- default-deny network policy with explicitly required application traffic;
- TLS ingress using an environment-specific host placeholder;
- references to externally supplied runtime secrets rather than committed Secret data.

## External dependencies

The baseline assumes production-grade external services for concerns such as PostgreSQL, S3-compatible object storage, and OpenSearch where configured. Those services are deployment dependencies, not domain authorities.

## Render the baseline

From the repository root:

```sh
kubectl kustomize deployment/kubernetes/base
```

Review the rendered resources before applying them. Configure environment-specific image references, ingress host/TLS, external service endpoints, and secret provisioning through your deployment process.

## Secrets

Do not commit credentials or private key material to the Kubernetes manifests. Supply runtime secrets through the environment's secret-management mechanism and keep the repository manifest as a reference to that external secret boundary.

## Relationship to Docker

Kubernetes and Docker Compose are different deployment adapters for the same Fieldora server platform. They must not introduce different domain or authorization semantics.

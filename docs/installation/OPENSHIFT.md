# OpenShift deployment

Fieldora includes a first-class OpenShift deployment adapter under `deployment/openshift/`. It reuses the cloud-neutral Kubernetes application baseline and adds only the OpenShift-specific exposure layer.

## Purpose

OpenShift is a distinct deployment target, not a synonym for generic Kubernetes. Fieldora keeps the same server/domain/application semantics while adapting ingress and platform-policy expectations to OpenShift.

## Baseline properties

The certified OpenShift baseline:

- reuses `deployment/kubernetes/base` for the Fieldora namespace, Deployments, Service, ServiceAccount, PodDisruptionBudgets, and NetworkPolicy;
- removes the generic NGINX-oriented Kubernetes Ingress from the composed output;
- exposes `fieldora-api` with an OpenShift `Route`;
- redirects insecure Route traffic to HTTPS;
- preserves the shared non-root, read-only-root-filesystem, no-added-capabilities security context;
- does not define a privileged or custom `SecurityContextConstraints` object;
- does not commit Secret objects or credential material.

## External dependencies

The OpenShift environment must provide production-grade external PostgreSQL, S3-compatible object storage, and OpenSearch services where configured. It must also provide the `fieldora-runtime` Secret referenced by the shared application baseline and an approved Fieldora image.

The OpenShift router, DNS, certificate policy, image registry integration, and cluster security policy remain environment-owned concerns.

## Render the baseline

From the repository root:

```sh
oc kustomize deployment/openshift/base
```

Review the rendered resources before applying them. Replace the placeholder Route host and configure environment-specific image, dependency endpoints, Secret provisioning, and router certificate policy through your deployment process.

## Security policy

The manifests intentionally avoid fixed user IDs, privileged containers, host networking, host paths, and repository-owned privileged SCC definitions. Use the cluster's approved restricted workload policy. Do not weaken the shared Kubernetes workload security merely to fit a broader SCC.

## Relationship to Kubernetes and Docker

Kubernetes, OpenShift, and Docker are deployment adapters for the same Fieldora server platform. OpenShift should reuse the Kubernetes application contract where possible while keeping OpenShift-specific routing and certification explicit.

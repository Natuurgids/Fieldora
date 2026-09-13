# Fieldora OpenShift baseline

This directory provides the Fieldora OpenShift deployment adapter. It deliberately reuses the certified Kubernetes application baseline instead of duplicating Fieldora workload definitions.

## What the OpenShift base owns

`deployment/openshift/base`:

- imports `deployment/kubernetes/base` for the Fieldora namespace, Deployments, Service, ServiceAccount, PodDisruptionBudgets, and NetworkPolicy;
- removes the generic NGINX-oriented Kubernetes Ingress;
- exposes the existing `fieldora-api` Service through an OpenShift `Route`;
- requires HTTPS at the router and redirects insecure requests;
- keeps the Kubernetes hardened container security contexts unchanged;
- does not define or request a privileged SecurityContextConstraints object;
- does not contain Secret objects or secret material.

The Route host is intentionally a placeholder. Configure the environment-specific host and certificate policy through your OpenShift deployment process.

## OpenShift security boundary

Fieldora should run under the cluster's normal restricted workload policy. The manifests intentionally avoid fixed user IDs, privileged containers, added Linux capabilities, host networking, host paths, and custom privileged SCC definitions. Cluster administrators remain responsible for mapping the workload to the organization-approved OpenShift security policy.

Do not relax the Kubernetes base security context merely to make the workload fit an overly permissive SCC.

## External prerequisites

The OpenShift environment must provide:

- an OpenShift cluster with the `route.openshift.io/v1` API;
- the `fieldora-runtime` Secret referenced by the shared Kubernetes base;
- production PostgreSQL, S3-compatible object storage, and OpenSearch dependencies;
- the Fieldora platform image or an approved image override;
- router/DNS configuration for the environment-specific Route host;
- a NetworkPolicy-capable cluster network implementation.

## Render

From the repository root:

```sh
oc kustomize deployment/openshift/base
```

Review the rendered resources before applying them. Rendering confirms composition only; it does not prove the external services, image registry, DNS, router certificates, or runtime Secret exist.

## Relationship to Kubernetes

OpenShift is a first-class deployment target, but it remains an adapter over the same Fieldora server semantics. The shared Kubernetes base is the application contract; this OpenShift layer carries only platform-specific exposure and policy assumptions.

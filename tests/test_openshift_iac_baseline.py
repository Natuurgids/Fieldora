from __future__ import annotations

from pathlib import Path

OPENSHIFT = Path("deployment/openshift")
BASE = OPENSHIFT / "base"
KUBERNETES_BASE = Path("deployment/kubernetes/base")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_openshift_overlay_reuses_kubernetes_application_base() -> None:
    kustomization = _text(BASE / "kustomization.yaml")

    assert "namespace: fieldora" in kustomization
    assert "- ../../kubernetes/base" in kustomization
    assert "- route.yaml" in kustomization
    assert "- path: delete-ingress.yaml" in kustomization
    assert (KUBERNETES_BASE / "platform.yaml").is_file()
    assert (KUBERNETES_BASE / "network-policy.yaml").is_file()


def test_openshift_overlay_replaces_generic_ingress_with_route() -> None:
    delete_ingress = _text(BASE / "delete-ingress.yaml")
    route = _text(BASE / "route.yaml")

    assert "$patch: delete" in delete_ingress
    assert "apiVersion: networking.k8s.io/v1" in delete_ingress
    assert "kind: Ingress" in delete_ingress
    assert "name: fieldora" in delete_ingress

    assert "apiVersion: route.openshift.io/v1" in route
    assert "kind: Route" in route
    assert "name: fieldora-api" in route
    assert "targetPort: http" in route
    assert "termination: edge" in route
    assert "insecureEdgeTerminationPolicy: Redirect" in route
    assert "fieldora.apps.example.invalid" in route


def test_openshift_keeps_shared_restricted_workload_security() -> None:
    platform = _text(KUBERNETES_BASE / "platform.yaml")

    assert platform.count("allowPrivilegeEscalation: false") >= 2
    assert platform.count("readOnlyRootFilesystem: true") >= 2
    assert platform.count("runAsNonRoot: true") >= 2
    assert platform.count('drop: ["ALL"]') >= 2
    assert "automountServiceAccountToken: false" in platform
    assert "runAsUser:" not in platform
    assert "privileged: true" not in platform
    assert "hostNetwork: true" not in platform
    assert "hostPath:" not in platform


def test_openshift_adapter_does_not_request_privileged_cluster_policy() -> None:
    combined = "\n".join(
        _text(path)
        for path in sorted(OPENSHIFT.rglob("*"))
        if path.is_file()
    )

    for forbidden in (
        "kind: SecurityContextConstraints",
        "allowPrivilegedContainer: true",
        "hostNetwork: true",
        "hostPID: true",
        "hostIPC: true",
        "hostPath:",
        "kind: Secret",
        "stringData:",
    ):
        assert forbidden not in combined


def test_openshift_documentation_keeps_external_secret_and_route_boundaries() -> None:
    readme = _text(OPENSHIFT / "README.md")

    for required in (
        "fieldora-runtime",
        "route.openshift.io/v1",
        "restricted workload policy",
        "oc kustomize deployment/openshift/base",
        "PostgreSQL",
        "S3-compatible object storage",
        "OpenSearch",
    ):
        assert required in readme
    assert "Do not relax the Kubernetes base security context" in readme

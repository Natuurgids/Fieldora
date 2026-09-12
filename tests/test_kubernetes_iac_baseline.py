from __future__ import annotations

from pathlib import Path

BASE = Path("deployment/kubernetes/base")


def _text(name: str) -> str:
    return (BASE / name).read_text(encoding="utf-8")


def test_kustomize_base_declares_only_versioned_fieldora_resources() -> None:
    kustomization = _text("kustomization.yaml")

    assert "namespace: fieldora" in kustomization
    for resource in (
        "namespace.yaml",
        "platform.yaml",
        "ingress.yaml",
        "network-policy.yaml",
    ):
        assert f"- {resource}" in kustomization
        assert (BASE / resource).is_file()


def test_namespace_enforces_restricted_pod_security() -> None:
    namespace = _text("namespace.yaml")

    assert "name: fieldora" in namespace
    assert "pod-security.kubernetes.io/enforce: restricted" in namespace
    assert "pod-security.kubernetes.io/audit: restricted" in namespace
    assert "pod-security.kubernetes.io/warn: restricted" in namespace


def test_platform_workloads_keep_hardened_runtime_boundaries() -> None:
    platform = _text("platform.yaml")

    assert platform.count("kind: Deployment") == 2
    assert "name: fieldora-api" in platform
    assert "name: fieldora-worker" in platform
    assert "kind: ServiceAccount" in platform
    assert "automountServiceAccountToken: false" in platform
    assert "secretName: fieldora-runtime" in platform
    assert "kind: Secret" not in platform
    assert "\nstringData:" not in platform
    assert "\ndata:" not in platform
    assert platform.count("allowPrivilegeEscalation: false") >= 2
    assert platform.count("readOnlyRootFilesystem: true") >= 2
    assert platform.count("runAsNonRoot: true") >= 2
    assert platform.count('drop: ["ALL"]') >= 2
    assert "readinessProbe:" in platform
    assert "livenessProbe:" in platform
    assert "startupProbe:" in platform
    assert "image: fieldora/platform:latest" not in platform


def test_network_policy_starts_default_deny_and_limits_platform_ports() -> None:
    policy = _text("network-policy.yaml")

    assert "name: default-deny" in policy
    assert "podSelector: {}" in policy
    assert "policyTypes: [Ingress, Egress]" in policy
    assert "name: fieldora-platform" in policy
    for port in ("8765", "443", "5432", "9200"):
        assert f"port: {port}" in policy


def test_ingress_requires_tls_and_keeps_environment_host_as_placeholder() -> None:
    ingress = _text("ingress.yaml")

    assert 'nginx.ingress.kubernetes.io/ssl-redirect: "true"' in ingress
    assert "tls:" in ingress
    assert "secretName: fieldora-ingress-tls" in ingress
    assert "fieldora.example.invalid" in ingress


def test_kubernetes_baseline_documents_external_dependencies_and_secret_boundary() -> None:
    readme = Path("deployment/kubernetes/README.md").read_text(encoding="utf-8")

    for prerequisite in (
        "fieldora-runtime",
        "fieldora-ingress-tls",
        "PostgreSQL",
        "S3-compatible object storage",
        "OpenSearch",
        "NetworkPolicy",
    ):
        assert prerequisite in readme
    assert "Do not commit credentials" in readme
    assert "kubectl kustomize deployment/kubernetes/base" in readme

from __future__ import annotations

from natureai_next.server.linked_storage_operator_web import (
    _LINKED_STORAGE_OPERATOR_WEB_PATCH,
)


def test_linked_storage_setup_enrolls_governed_service_without_storage_secrets() -> None:
    patch = _LINKED_STORAGE_OPERATOR_WEB_PATCH.decode("utf-8")

    assert 'id="operator-linked-service-enroll"' in patch
    assert 'api("/api/v1/operator/services"' in patch
    assert 'service_type:"linked-storage"' in patch
    assert 'certificate_serial:serial' in patch
    assert 'certificate_not_after_epoch:expiryEpoch' in patch
    assert "crypto.randomUUID" not in patch

    enrollment = patch.split('api("/api/v1/operator/services"', 1)[1].split(");", 1)[0]
    for forbidden in (
        "root_path",
        "root_alias",
        "private_key",
        "ca_certificate",
        "source_secret",
        "credential",
    ):
        assert forbidden not in enrollment


def test_linked_storage_setup_requires_explicit_activation_and_node_registration() -> None:
    patch = _LINKED_STORAGE_OPERATOR_WEB_PATCH.decode("utf-8")

    assert 'id="operator-linked-service-activate"' in patch
    assert '/api/v1/operator/services/${encodeURIComponent(serviceId)}/activate' in patch
    assert "It is not active until explicitly activated." in patch
    assert "The storage node registers the read-only archive after mTLS activation." in patch
    assert "Root paths, root aliases, private keys, CA material and source credentials" in patch
    assert "/internal/v1/storage/sources" not in patch


def test_linked_storage_empty_state_points_to_real_setup_flow() -> None:
    patch = _LINKED_STORAGE_OPERATOR_WEB_PATCH.decode("utf-8")

    assert "No linked archives registered for this organization. Enroll and activate" in patch
    assert 'operatorOrganizationId=String(overview.organization_id||"")' in patch
    assert "Storage-node handoff" in patch
    assert "Service ID" in patch
    assert "Organization ID" in patch

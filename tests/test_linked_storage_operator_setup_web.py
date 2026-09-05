from __future__ import annotations

from natureai_next.server.linked_storage_operator_web import (
    _LINKED_STORAGE_OPERATOR_WEB_PATCH,
)
from natureai_next.server.linked_storage_setup_web import (
    _LINKED_STORAGE_SETUP_WEB_PATCH,
)


def test_linked_storage_setup_prepares_server_identity_before_certificate_enrollment() -> None:
    patch = _LINKED_STORAGE_OPERATOR_WEB_PATCH.decode("utf-8")

    assert 'id="operator-linked-service-prepare"' in patch
    assert 'id="operator-linked-service-id" readonly' in patch
    assert 'api("/api/v1/operator/linked-storage-services/prepare-id"' in patch
    assert 'api("/api/v1/operator/linked-storage-services"' in patch
    assert 'service_id:serviceId' in patch
    assert 'certificate_serial:serial' in patch
    assert 'certificate_not_after_epoch:expiryEpoch' in patch
    assert "crypto.randomUUID" not in patch
    assert "New-Fieldora-Storage-ServiceTrust.ps1" in patch

    enrollment = patch.split('api("/api/v1/operator/linked-storage-services"', 1)[1].split(");", 1)[0]
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
    assert "Storage service active. Configure the storage node with the handoff values below" in patch
    assert "the node registers its read-only archive over mTLS." in patch
    assert "Root paths, root aliases, private keys, CA material and source credentials" in patch
    assert "/internal/v1/storage/sources" not in patch


def test_linked_storage_setup_never_asks_browser_for_key_or_mount_material() -> None:
    patch = _LINKED_STORAGE_OPERATOR_WEB_PATCH.decode("utf-8")

    assert "Do not paste private keys or CA material into the browser." in patch
    assert 'id="operator-linked-service-certificate-serial"' in patch
    assert 'id="operator-linked-service-certificate-expiry"' in patch
    assert 'id="operator-linked-service-trust-command"' in patch
    assert 'id="operator-linked-service-private-key"' not in patch
    assert 'id="operator-linked-service-root-path"' not in patch
    assert 'id="operator-linked-service-credential"' not in patch


def test_linked_storage_empty_state_points_to_real_setup_flow() -> None:
    patch = _LINKED_STORAGE_OPERATOR_WEB_PATCH.decode("utf-8")
    handoff = _LINKED_STORAGE_SETUP_WEB_PATCH.decode("utf-8")

    assert "No linked archives registered for this organization. Prepare, enroll and activate" in patch
    assert 'operatorOrganizationId=String(overview.organization_id||"")' in patch
    assert "Storage-node handoff" in patch
    assert "Service ID" in patch
    assert "Organization ID" in patch

    assert 'id="linked-storage-operator-setup"' in handoff
    assert 'document.querySelector(\'.nav[data-page="operator"]\')' in handoff
    assert 'showPage("operator")' in handoff
    assert 'byId("operator-linked-service-name")?.focus()' in handoff
    assert "operatorNav" in handoff

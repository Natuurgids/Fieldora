from pathlib import Path
from shutil import copy2
from types import SimpleNamespace

from natureai_next.bootstrap.certificate_renewer_cli import _renew_cycle
from natureai_next.server.operator_control import ServiceState
from natureai_next.server.service_trust import ServiceTrustAuthority


class RecordingRepository:
    def __init__(self, service_id: str) -> None:
        self.service_id = service_id
        self.heartbeats: list[dict[str, object]] = []

    def service(self, service_id: str):
        if service_id != self.service_id:
            return None
        return SimpleNamespace(state=ServiceState.ACTIVE.value)

    def heartbeat(self, service_id: str, **kwargs: object):
        assert service_id == self.service_id
        self.heartbeats.append(dict(kwargs))
        return SimpleNamespace(state=ServiceState.ACTIVE.value)


def test_online_issuer_can_issue_without_root_private_key(tmp_path: Path) -> None:
    root = tmp_path / "offline-root"
    online = tmp_path / "online-issuer"
    authority = ServiceTrustAuthority(root)
    authority.initialize("Fieldora Test Root")
    online.mkdir()
    for name in (
        "ca-certificate.pem",
        "issuer-certificate.pem",
        "issuer-private.pem",
    ):
        copy2(root / name, online / name)

    assert not (online / "ca-private.pem").exists()

    certificate = tmp_path / "service.crt"
    private_key = tmp_path / "service.key"
    record = ServiceTrustAuthority(online).issue(
        service_id="worker-1",
        organization_id="test-org",
        common_name="fieldora",
        certificate_path=certificate,
        private_key_path=private_key,
        dns_names=("worker-1",),
        lifetime_hours=24,
    )

    assert record.service_id == "worker-1"
    assert certificate.read_bytes().count(b"BEGIN CERTIFICATE") == 2
    inspected = ServiceTrustAuthority(online).inspect(certificate)
    assert inspected.service_id == "worker-1"
    assert inspected.organization_id == "test-org"


def test_renewal_keeps_identity_and_updates_operator_certificate(tmp_path: Path) -> None:
    offline = tmp_path / "offline-root"
    online = tmp_path / "online-issuer"
    root_authority = ServiceTrustAuthority(offline)
    root_authority.initialize("Fieldora Test Root")
    online.mkdir()
    for name in (
        "ca-certificate.pem",
        "issuer-certificate.pem",
        "issuer-private.pem",
    ):
        copy2(offline / name, online / name)

    certificate = tmp_path / "worker.crt"
    private_key = tmp_path / "worker.key"
    issuer = ServiceTrustAuthority(online)
    first = issuer.issue(
        service_id="worker-1",
        organization_id="test-org",
        common_name="fieldora",
        certificate_path=certificate,
        private_key_path=private_key,
        lifetime_hours=1,
    )
    repository = RecordingRepository("worker-1")

    _renew_cycle(
        issuer,
        repository,  # type: ignore[arg-type]
        "unused",
        [
            {
                "service_id": "worker-1",
                "organization_id": "test-org",
                "common_name": "fieldora",
                "certificate": str(certificate),
                "private_key": str(private_key),
                "dns_names": [],
                "ip_addresses": [],
            }
        ],
        renew_before_hours=2,
        lifetime_hours=24,
    )

    second = issuer.inspect(certificate)
    assert second.service_id == first.service_id
    assert second.serial_number != first.serial_number
    assert repository.heartbeats[-1]["certificate_serial"] == second.serial_number

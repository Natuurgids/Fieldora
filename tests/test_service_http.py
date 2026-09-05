from __future__ import annotations

from pathlib import Path

from natureai_next.server import service_http


class _FakeContext:
    def __init__(self, _protocol) -> None:
        self.minimum_version = None
        self.verify_mode = None
        self.ca_files: list[str] = []
        self.chains: list[tuple[str, str]] = []

    def load_verify_locations(self, *, cafile: str) -> None:
        self.ca_files.append(cafile)

    def load_cert_chain(self, certificate: str, private_key: str) -> None:
        self.chains.append((certificate, private_key))


def test_mtls_context_reloads_replaced_server_identity(
    tmp_path: Path, monkeypatch
) -> None:
    certificate = tmp_path / "service.crt"
    private_key = tmp_path / "service.key"
    client_ca = tmp_path / "ca.pem"
    certificate.write_text("certificate-v1", encoding="utf-8")
    private_key.write_text("key-v1", encoding="utf-8")
    client_ca.write_text("ca", encoding="utf-8")

    created: list[_FakeContext] = []

    def fake_context(protocol):
        context = _FakeContext(protocol)
        created.append(context)
        return context

    monkeypatch.setattr(service_http.ssl, "SSLContext", fake_context)
    tls = service_http.ReloadingMutualTLSContext(certificate, private_key, client_ca)

    assert len(created) == 1
    assert len(created[0].chains) == 1
    assert tls.reload_if_changed() is False
    assert len(created[0].chains) == 1

    certificate.write_text("certificate-v2", encoding="utf-8")
    private_key.write_text("key-v2", encoding="utf-8")
    assert tls.reload_if_changed() is True
    assert len(created[0].chains) == 2
    assert created[0].ca_files == [str(client_ca.resolve())]

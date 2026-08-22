from pathlib import Path

from natureai_next.server.http import ReloadingCertificateChain


class RecordingContext:
    def __init__(self) -> None:
        self.loaded: list[tuple[str, str]] = []

    def load_cert_chain(self, certificate: str, private_key: str) -> None:
        self.loaded.append((certificate, private_key))


def test_certificate_chain_reloads_only_when_material_changes(tmp_path: Path) -> None:
    certificate = tmp_path / "service.crt"
    private_key = tmp_path / "service.key"
    certificate.write_text("certificate-one", encoding="ascii")
    private_key.write_text("key-one", encoding="ascii")
    context = RecordingContext()

    chain = ReloadingCertificateChain(context, certificate, private_key)  # type: ignore[arg-type]

    assert len(context.loaded) == 1
    assert chain.reload_if_changed() is False
    assert len(context.loaded) == 1

    certificate.write_text("certificate-two", encoding="ascii")

    assert chain.reload_if_changed() is True
    assert len(context.loaded) == 2
    assert chain.reload_if_changed() is False


def test_certificate_chain_detects_private_key_rotation(tmp_path: Path) -> None:
    certificate = tmp_path / "service.crt"
    private_key = tmp_path / "service.key"
    certificate.write_text("certificate-one", encoding="ascii")
    private_key.write_text("key-one", encoding="ascii")
    context = RecordingContext()
    chain = ReloadingCertificateChain(context, certificate, private_key)  # type: ignore[arg-type]

    private_key.write_text("key-two", encoding="ascii")

    assert chain.reload_if_changed() is True
    assert len(context.loaded) == 2

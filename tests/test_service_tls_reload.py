import inspect
from pathlib import Path

from natureai_next.bootstrap.server_cli import build_parser
from natureai_next.server.api import ApiResponse
from natureai_next.server.http import ReloadingCertificateChain, handler_for, serve


class RecordingContext:
    def __init__(self) -> None:
        self.loaded: list[tuple[str, str]] = []

    def load_cert_chain(self, certificate: str, private_key: str) -> None:
        self.loaded.append((certificate, private_key))


class DispatchOnlyApplication:
    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        return ApiResponse.json(
            200,
            {"method": method, "target": target, "body_size": len(body)},
        )


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


def test_http_handler_uses_the_fieldora_dispatch_contract() -> None:
    application = DispatchOnlyApplication()
    handler = handler_for(application)  # type: ignore[arg-type]

    assert handler is not None
    assert not hasattr(application, "handle")
    assert application.dispatch("GET", "/api/v1/health/live", {}, b"").status == 200


def test_clean_installer_init_user_cli_and_http_serve_contract() -> None:
    args = build_parser().parse_args(
        [
            "--data-root",
            "/var/lib/fieldora",
            "--access-backend",
            "postgresql",
            "--postgres-access-dsn-file",
            "/run/secrets/fieldora-access-dsn",
            "init-user",
            "--organization",
            "local",
            "--name",
            "Administrator",
            "--username",
            "admin",
            "--password",
            "test-password-value",
        ]
    )

    assert args.command == "init-user"
    assert args.access_backend == "postgresql"
    assert args.postgres_access_dsn_file == Path(
        "/run/secrets/fieldora-access-dsn"
    )
    assert args.organization == "local"
    assert args.username == "admin"

    parameters = inspect.signature(serve).parameters
    for name in (
        "certificate",
        "private_key",
        "on_shutdown",
        "shutdown_grace_seconds",
    ):
        assert name in parameters

import json
import zipfile
from pathlib import Path

from natureai_next.application.governed_packs import GovernedPackBuilder, GovernedPackInstaller
from natureai_next.application.synchronization import DesktopSynchronizationService
from natureai_next.domain.synchronization import EnrollmentState, PlatformAccount, ProjectEnrollment
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.governed_packs import SqliteGovernedPackRegistry
from natureai_next.infrastructure.database.migrations import CORE_MIGRATIONS, MigrationRunner
from natureai_next.infrastructure.database.synchronization import SqliteDesktopSynchronizationRepository


def _registry(tmp_path: Path):
    factory = SqliteConnectionFactory(tmp_path / "library.sqlite3")
    with factory.connect() as connection:
        MigrationRunner(CORE_MIGRATIONS, "0.09.5").apply(connection)
    sync = SqliteDesktopSynchronizationRepository(factory)
    service = DesktopSynchronizationService(sync)
    service.save_account(
        PlatformAccount("a", "https://fieldora.example", "Account", "org", "user", "now")
    )
    service.enroll_project(
        ProjectEnrollment(
            "e", "a", "p", "c", EnrollmentState.ACTIVE, ("view",),
            "2027-01-01T00:00:00+00:00", 1, "now",
        )
    )
    return SqliteGovernedPackRegistry(factory)


def test_builder_filters_records_and_fields_before_packaging(tmp_path: Path) -> None:
    package = tmp_path / "pack.zip"
    summary = GovernedPackBuilder().build(
        package, pack_id="pack-1", enrollment_id="e", project_id="p",
        version=1, records=(
            {"id": "allowed", "title": "Visible", "secret": "remove"},
            {"id": "denied", "title": "Hidden", "secret": "remove"},
        ),
        disclose=lambda row: (
            {"id": row["id"], "title": row["title"]} if row["id"] == "allowed" else None
        ),
    )
    assert summary.record_count == 1
    with zipfile.ZipFile(package) as archive:
        payload = json.loads(archive.read("payload.json"))
    assert payload["records"] == [{"id": "allowed", "title": "Visible"}]
    assert b"secret" not in package.read_bytes()


def test_delta_requires_exact_installed_base_and_updates_isolated_store(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    builder = GovernedPackBuilder()
    installer = GovernedPackInstaller(tmp_path / "governed-cache", registry)
    full = tmp_path / "full.zip"
    builder.build(
        full, pack_id="pack-1", enrollment_id="e", project_id="p",
        version=1, records=({"id": "one"},), disclose=lambda row: row,
    )
    installer.install(full)
    bad = tmp_path / "bad-delta.zip"
    builder.build(
        bad, pack_id="pack-3", enrollment_id="e", project_id="p",
        version=3, base_version=2, records=({"id": "three"},), disclose=lambda row: row,
    )
    try:
        installer.install(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("delta with the wrong base was installed")
    delta = tmp_path / "delta.zip"
    builder.build(
        delta, pack_id="pack-2", enrollment_id="e", project_id="p",
        version=2, base_version=1, records=({"id": "two"},),
        tombstones=({"id": "one"},), disclose=lambda row: row,
    )
    installer.install(delta)
    assert registry.pack_version("e") == 2
    payload = json.loads((tmp_path / "governed-cache/e/payload.json").read_text())
    assert payload == {"records": [{"id": "two"}], "tombstones": [{"id": "one"}]}

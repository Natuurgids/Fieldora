"""SQLite/filesystem Library lifecycle backend."""

from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from natureai_next import __version__
from natureai_next.domain.library import IntegrityReport, LibraryLayout, LibraryManifest
from natureai_next.infrastructure.database.backup import create_database_backup
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.integrity import check_integrity
from natureai_next.infrastructure.database.migrations import (
    CORE_MIGRATIONS,
    MigrationError,
    MigrationRunner,
)
from natureai_next.infrastructure.database.settings import SqliteSettings
from natureai_next.infrastructure.filesystem.library_lock import LibraryLock
from natureai_next.infrastructure.filesystem.library_manifest import read_manifest, write_manifest


@lru_cache(maxsize=1)
def _required_schema_contract() -> dict[str, frozenset[str]]:
    """Build the canonical clean-start schema and return required columns by table.

    Startup must validate the schema actually consumed by repositories, not only
    trust the migration ledger.  A migration row can survive an interrupted or
    externally replaced database while one or more application tables are absent.
    """
    connection = sqlite3.connect(":memory:")
    try:
        MigrationRunner(CORE_MIGRATIONS, __version__).apply(connection)
        names = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        return {
            name: frozenset(
                str(row[1]) for row in connection.execute(f"PRAGMA table_info({name!r})")
            )
            for name in names
        }
    finally:
        connection.close()


def _schema_defects(connection: sqlite3.Connection) -> dict[str, tuple[str, ...]]:
    present = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
        )
    }
    defects: dict[str, tuple[str, ...]] = {}
    for table, required_columns in _required_schema_contract().items():
        if table not in present:
            defects[table] = ("<missing table>",)
            continue
        columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table!r})")}
        missing_columns = tuple(sorted(required_columns - columns))
        if missing_columns:
            defects[table] = missing_columns
    return defects


def _assert_repository_schema(connection: sqlite3.Connection) -> None:
    """Exercise every required table on the same connection repositories use."""
    defects = _schema_defects(connection)
    if defects:
        detail = "; ".join(
            f"{table}: {', '.join(columns)}" for table, columns in sorted(defects.items())
        )
        raise MigrationError(f"Fieldora library schema is incomplete: {detail}")
    # Force SQLite to compile representative core queries before the UI exists.
    connection.execute("SELECT 1 FROM observations LIMIT 0")
    connection.execute("SELECT 1 FROM assets LIMIT 0")
    connection.execute("SELECT 1 FROM collections LIMIT 0")
    connection.execute("SELECT 1 FROM library_info LIMIT 0")


def _has_user_data(connection) -> bool:
    present = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    for table in ("assets", "observations", "collections", "user_taxa"):
        if (
            table in present
            and connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() is not None
        ):
            return True
    return False


@dataclass(slots=True)
class SqliteOpenLibrary:
    layout: LibraryLayout
    manifest: LibraryManifest
    connection_factory: SqliteConnectionFactory
    lock: LibraryLock
    _closed: bool = False

    def integrity(self, *, full: bool = False) -> IntegrityReport:
        return check_integrity(self.connection_factory, full=full)

    def backup_database(self, destination: Path) -> Path:
        return create_database_backup(self.connection_factory, destination)

    def ensure_runtime_schema(self) -> None:
        """Validate only. Normal startup is never allowed to repair or replace files."""
        if self._closed:
            raise RuntimeError("library is closed")
        connection = self.connection_factory.connect(read_only=True)
        try:
            _assert_repository_schema(connection)
            row = connection.execute("SELECT public_id FROM library_info WHERE id=1").fetchone()
            if row is None or str(row[0]) != self.manifest.library_public_id:
                raise MigrationError("library manifest and database identity differ")
        finally:
            connection.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self.layout.database.is_file():
                connection = self.connection_factory.connect()
                try:
                    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                finally:
                    connection.close()
        except Exception:
            pass
        finally:
            self.lock.release()

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class SqliteLibraryLifecycleBackend:
    def __init__(self, clock, ids, settings=None) -> None:
        self.clock = clock
        self.ids = ids
        self.settings = settings or SqliteSettings()

    def _initialize_directory(self, root: Path, *, display_name: str, default_locale: str) -> None:
        layout = LibraryLayout.at(root)
        layout.create_directories()
        public_id = str(self.ids.new_uuid())
        created = int(self.clock.now_utc().timestamp() * 1_000_000)
        manifest = LibraryManifest(1, public_id, display_name, created)
        factory = SqliteConnectionFactory(layout.database, self.settings)
        connection = factory.connect()
        try:
            MigrationRunner(CORE_MIGRATIONS, __version__).apply(connection)
            _assert_repository_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO library_info(id,public_id,created_at_us,current_schema_version,minimum_app_version,display_name,default_locale) VALUES(1,?,?,?,?,?,?)",
                (
                    public_id,
                    created,
                    len(CORE_MIGRATIONS),
                    __version__,
                    display_name,
                    default_locale,
                ),
            )
            connection.execute("COMMIT")
            quick = connection.execute("PRAGMA quick_check").fetchone()
            if quick is None or str(quick[0]).lower() != "ok":
                raise sqlite3.DatabaseError("new library failed SQLite quick_check")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        # Publish the manifest last. A directory with a manifest is therefore complete.
        write_manifest(layout.manifest, manifest)

    def create(
        self, root: Path, *, display_name: str, default_locale: str = "en"
    ) -> SqliteOpenLibrary:
        root = root.expanduser().resolve()
        if root.exists():
            if not root.is_dir():
                raise NotADirectoryError(f"library path is not a directory: {root}")
            if any(root.iterdir()):
                raise FileExistsError(f"library directory is not empty: {root}")
        parent = root.parent
        parent.mkdir(parents=True, exist_ok=True)
        staging = parent / f".{root.name}.aperture-staging-{self.ids.new_uuid()}"
        if staging.exists():
            raise FileExistsError(f"staging directory already exists: {staging}")
        try:
            self._initialize_directory(
                staging, display_name=display_name, default_locale=default_locale
            )
            # Reopen from disk before publication; do not trust the creation connection.
            staged_layout = LibraryLayout.at(staging)
            staged_manifest = read_manifest(staged_layout.manifest)
            check = SqliteConnectionFactory(staged_layout.database, self.settings).connect(
                read_only=True
            )
            try:
                _assert_repository_schema(check)
                identity = check.execute("SELECT public_id FROM library_info WHERE id=1").fetchone()
                if identity is None or str(identity[0]) != staged_manifest.library_public_id:
                    raise MigrationError("staged library identity validation failed")
            finally:
                check.close()
            if root.exists():
                root.rmdir()  # only succeeds while still empty
            staging.replace(root)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return self.open(root)

    def upgrade(self, root: Path) -> SqliteOpenLibrary:
        """Back up and explicitly upgrade a compatible older library, then open it."""
        layout = LibraryLayout.at(root)
        if not layout.root.is_dir() or not layout.manifest.is_file() or not layout.database.is_file():
            raise MigrationError("The selected directory is not a complete Fieldora library.")
        factory = SqliteConnectionFactory(layout.database, self.settings)
        lock = LibraryLock(layout.lock_file)
        lock.acquire()
        try:
            with factory.connect(read_only=True) as connection:
                applied = {
                    int(row[0]): str(row[1])
                    for row in connection.execute(
                        "SELECT migration_number, checksum FROM schema_migrations ORDER BY migration_number"
                    )
                }
            expected = {migration.number: migration.checksum for migration in CORE_MIGRATIONS}
            prefix_length = len(applied)
            valid_prefix = (
                tuple(applied) == tuple(range(1, prefix_length + 1))
                and applied == {number: expected[number] for number in range(1, prefix_length + 1)}
                and prefix_length <= len(expected)
            )
            if not valid_prefix:
                raise MigrationError("The selected library migration history is not compatible.")
            if applied != expected:
                backup = layout.backups / (
                    f"pre-schema-{prefix_length}-to-{len(expected)}-{self.ids.new_uuid()}.sqlite3"
                )
                create_database_backup(factory, backup)
                with factory.connect() as connection:
                    MigrationRunner(CORE_MIGRATIONS, __version__).apply(connection)
                    connection.execute(
                        "UPDATE library_info SET current_schema_version=?,minimum_app_version=? WHERE id=1",
                        (len(CORE_MIGRATIONS), __version__),
                    )
                    connection.commit()
        finally:
            lock.release()
        return self.open(root)

    def open(self, root: Path) -> SqliteOpenLibrary:
        layout = LibraryLayout.at(root)
        if not layout.root.is_dir():
            raise FileNotFoundError(f"library directory does not exist: {layout.root}")
        if not layout.manifest.is_file() or not layout.database.is_file():
            raise MigrationError(
                "The selected directory is not a complete Aperture V4 library. "
                "Normal startup never repairs or replaces library files."
            )
        manifest = read_manifest(layout.manifest)
        lock = LibraryLock(layout.lock_file)
        lock.acquire()
        try:
            factory = SqliteConnectionFactory(layout.database, self.settings)
            connection = factory.connect(read_only=True)
            try:
                applied = {
                    int(row[0]): str(row[1])
                    for row in connection.execute(
                        "SELECT migration_number, checksum FROM schema_migrations ORDER BY migration_number"
                    )
                }
                expected = {migration.number: migration.checksum for migration in CORE_MIGRATIONS}
                prefix_length = len(applied)
                valid_prefix = (
                    tuple(applied) == tuple(range(1, prefix_length + 1))
                    and applied
                    == {
                        number: expected[number]
                        for number in range(1, prefix_length + 1)
                    }
                    and prefix_length <= len(expected)
                )
                if applied != expected and not valid_prefix:
                    raise MigrationError(
                        "The selected library migration history is not compatible with this Fieldora release. "
                        "No library data was changed."
                    )
            finally:
                connection.close()

            if applied != expected:
                raise MigrationError(
                    "The selected library requires an explicit schema upgrade in the "
                    "Fieldora Maintenance Center. No library data was changed."
                )

            connection = factory.connect(read_only=True)
            try:
                _assert_repository_schema(connection)
                row = connection.execute("SELECT public_id FROM library_info WHERE id=1").fetchone()
                if row is None or str(row[0]) != manifest.library_public_id:
                    raise MigrationError(
                        "library manifest and database identity differ; no data was changed"
                    )
                quick = connection.execute("PRAGMA quick_check").fetchone()
                if quick is None or str(quick[0]).lower() != "ok":
                    raise sqlite3.DatabaseError(
                        f"SQLite quick_check failed: {quick[0] if quick else 'no result'}"
                    )
            finally:
                connection.close()
            return SqliteOpenLibrary(layout, manifest, factory, lock)
        except Exception:
            lock.release()
            raise

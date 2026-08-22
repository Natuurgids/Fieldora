"""SQLite governed-pack registry; payload bytes remain in the isolated pack store."""

from natureai_next.infrastructure.database.connection import SqliteConnectionFactory


class SqliteGovernedPackRegistry:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def pack_version(self, enrollment_id: str) -> int:
        with self._factory.connect() as connection:
            row = connection.execute(
                "SELECT version FROM sync_governed_packs WHERE enrollment_id=?",
                (enrollment_id,),
            ).fetchone()
        return 0 if row is None else int(row["version"])

    def put_pack(
        self, pack_id: str, enrollment_id: str, project_id: str, version: int,
        payload_path: str, package_sha256: str,
    ) -> None:
        with self._factory.connect() as connection:
            connection.execute(
                "INSERT INTO sync_governed_packs("
                "enrollment_id,pack_id,project_id,version,payload_path,package_sha256"
                ") VALUES(?,?,?,?,?,?) ON CONFLICT(enrollment_id) DO UPDATE SET "
                "pack_id=excluded.pack_id,project_id=excluded.project_id,"
                "version=excluded.version,payload_path=excluded.payload_path,"
                "package_sha256=excluded.package_sha256,state='active' "
                "WHERE excluded.version>sync_governed_packs.version",
                (enrollment_id, pack_id, project_id, version, payload_path, package_sha256),
            )

    def put_pack_security(
        self, pack_id: str, enrollment_id: str, envelope_path: str, key_ref: str,
        expires_at_utc: str, signing_key_id: str,
    ) -> None:
        with self._factory.connect() as connection:
            connection.execute(
                "INSERT INTO sync_governed_pack_security VALUES(?,?,?,?,?,?,'active') "
                "ON CONFLICT(pack_id) DO UPDATE SET envelope_path=excluded.envelope_path,"
                "key_ref=excluded.key_ref,expires_at_utc=excluded.expires_at_utc,"
                "signing_key_id=excluded.signing_key_id,state='active'",
                (pack_id, enrollment_id, envelope_path, key_ref,
                 expires_at_utc, signing_key_id),
            )

    def pack_security(self, pack_id: str):
        with self._factory.connect() as connection:
            row = connection.execute(
                "SELECT * FROM sync_governed_pack_security WHERE pack_id=?", (pack_id,)
            ).fetchone()
        return None if row is None else dict(row)

    def set_pack_security_state(self, pack_id: str, state: str) -> None:
        if state not in {"active", "expired", "revoked"}:
            raise ValueError("invalid governed pack security state")
        with self._factory.connect() as connection:
            connection.execute(
                "UPDATE sync_governed_pack_security SET state=? WHERE pack_id=?",
                (state, pack_id),
            )


"""Database integrity maintenance primitives."""

from __future__ import annotations

from natureai_next.domain.library import IntegrityReport
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory


def check_integrity(factory: SqliteConnectionFactory, *, full: bool = False) -> IntegrityReport:
    c = factory.connect(read_only=True)
    try:
        pragma = "integrity_check" if full else "quick_check"
        checks = tuple(str(r[0]) for r in c.execute(f"PRAGMA {pragma}"))
        fk = tuple(tuple(r) for r in c.execute("PRAGMA foreign_key_check"))
        return IntegrityReport(checks, fk)
    finally:
        c.close()

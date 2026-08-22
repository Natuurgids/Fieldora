"""Read-only access and working-set filters for isolated taxonomy sources."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TaxonomyWorkingSet:
    name: str
    kingdom: str | None = None
    taxon_class: str | None = None
    taxon_order: str | None = None
    family: str | None = None
    rank: str | None = None


class TaxonomySourceLibrary:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (
            (
                root
                or Path(os.getenv("LOCALAPPDATA", Path.home()))
                / "NatureAI"
                / "NatureAI Next"
                / "taxonomy-sources"
            )
            .expanduser()
            .resolve()
        )
        self.db = self.root / "gbif.active.sqlite3"
        self.sets_file = self.root / "working-sets.json"

    def distinct(self, field: str, filters: dict[str, str | None] | None = None) -> tuple[str, ...]:
        allowed = {"kingdom", "taxon_class", "taxon_order", "family", "rank"}
        if field not in allowed:
            raise ValueError(f"Unsupported taxonomy filter: {field}")
        if not self.db.exists():
            return ()
        clauses = [f"{field} IS NOT NULL", f"trim({field}) <> ''"]
        params = []
        for key, value in (filters or {}).items():
            if key not in allowed or not value:
                continue
            clauses.append(f"{key} = ?")
            params.append(value)
        uri = f"file:{self.db.as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as con:
            rows = con.execute(
                f"SELECT DISTINCT {field} FROM taxa WHERE "
                + " AND ".join(clauses)
                + f" ORDER BY {field} COLLATE NOCASE",
                params,
            ).fetchall()
        return tuple(str(r[0]) for r in rows)

    def count(self, working_set: TaxonomyWorkingSet) -> int:
        if not self.db.exists():
            return 0
        clauses = []
        params = []
        for key in ("kingdom", "taxon_class", "taxon_order", "family", "rank"):
            value = getattr(working_set, key)
            if value:
                clauses.append(f"{key}=?")
                params.append(value)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        uri = f"file:{self.db.as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as con:
            return int(con.execute("SELECT count(*) FROM taxa" + where, params).fetchone()[0])

    def load_sets(self) -> tuple[TaxonomyWorkingSet, ...]:
        if not self.sets_file.exists():
            return ()
        try:
            payload = json.loads(self.sets_file.read_text(encoding="utf-8"))
        except Exception:
            return ()
        return tuple(TaxonomyWorkingSet(**item) for item in payload.get("sets", []))

    def save_set(self, working_set: TaxonomyWorkingSet) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        sets = {item.name: item for item in self.load_sets()}
        sets[working_set.name] = working_set
        temp = self.sets_file.with_suffix(".tmp")
        temp.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "sets": [
                        asdict(v) for v in sorted(sets.values(), key=lambda x: x.name.casefold())
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        os.replace(temp, self.sets_file)

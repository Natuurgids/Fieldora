"""SQLite ecological-context store."""

from __future__ import annotations

import json
import re
import unicodedata
from difflib import get_close_matches

from natureai_next.domain.ecology import EcologicalContext


def _normalise_name(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).replace("×", " x ")
    text = re.sub(r"[(),]", " ", text.lower())
    tokens = [t.strip(".") for t in text.split() if t]
    if len(tokens) <= 2:
        return " ".join(tokens)
    # Preserve genus + epithet (+ hybrid marker/name), discard common authorship suffixes.
    kept = tokens[:2]
    if len(tokens) > 2 and tokens[1] == "x":
        kept = tokens[:3]
    elif len(tokens) > 3 and tokens[2] in {"subsp", "ssp", "var", "f"}:
        kept = tokens[:4]
    return " ".join(kept)


class SqliteEcologicalContextStore:
    def __init__(self, factory) -> None:
        self._factory = factory

    def for_taxon(self, public_id):
        c = self._factory.connect(read_only=True)
        try:
            r = c.execute(
                "SELECT t.public_id,t.scientific_name,e.* FROM taxa t JOIN ecological_context e ON e.taxon_id=t.id WHERE t.public_id=?",
                (public_id,),
            ).fetchone()
            if r is None:
                return None
            return EcologicalContext(
                str(r["public_id"]),
                str(r["scientific_name"]),
                r["conservation_status"],
                tuple(json.loads(r["seasonal_months"] or "[]")),
                r["migration_status"],
                tuple(json.loads(r["habitats"] or "[]")),
                str(r["source_name"]),
                r["source_version"],
                r["source_url"],
            )
        finally:
            c.close()

    def _taxon_names(self):
        c = self._factory.connect(read_only=True)
        try:
            return [
                dict(
                    public_id=str(r["public_id"]),
                    scientific_name=str(r["scientific_name"]),
                    authorship=r["authorship"],
                )
                for r in c.execute(
                    "SELECT public_id,scientific_name,authorship FROM taxa WHERE status='accepted'"
                )
            ]
        finally:
            c.close()

    def match_taxon_name(self, value):
        target = value.strip().casefold()
        rows = self._taxon_names()
        for row in rows:
            if row["scientific_name"].casefold() == target:
                return {**row, "match_kind": "exact", "suggestion": None}
        norm = _normalise_name(value)
        candidates = []
        for row in rows:
            forms = {_normalise_name(row["scientific_name"])}
            if row.get("authorship"):
                forms.add(_normalise_name(f"{row['scientific_name']} {row['authorship']}"))
            if norm and norm in forms:
                candidates.append(row)
        if len(candidates) == 1:
            return {
                **candidates[0],
                "match_kind": "normalized",
                "suggestion": candidates[0]["scientific_name"],
            }
        return None

    def suggest_taxon_name(self, value):
        rows = self._taxon_names()
        normalized = {_normalise_name(r["scientific_name"]): r["scientific_name"] for r in rows}
        m = get_close_matches(_normalise_name(value), list(normalized), n=1, cutoff=0.72)
        return normalized[m[0]] if m else None

    def upsert_many(self, records, *, now_us):
        c = self._factory.connect()
        count = 0
        try:
            c.execute("BEGIN IMMEDIATE")
            for item in records:
                taxon = c.execute(
                    "SELECT id FROM taxa WHERE public_id=?", (item["taxon_public_id"],)
                ).fetchone()
                if taxon is None:
                    continue
                c.execute(
                    """INSERT INTO ecological_context(taxon_id,conservation_status,seasonal_months,migration_status,habitats,source_name,source_version,source_url,updated_at_us)
                VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(taxon_id) DO UPDATE SET conservation_status=excluded.conservation_status,seasonal_months=excluded.seasonal_months,migration_status=excluded.migration_status,habitats=excluded.habitats,source_name=excluded.source_name,source_version=excluded.source_version,source_url=excluded.source_url,updated_at_us=excluded.updated_at_us""",
                    (
                        int(taxon[0]),
                        item["conservation_status"],
                        json.dumps(item["seasonal_months"]),
                        item["migration_status"],
                        json.dumps(item["habitats"]),
                        item["source_name"],
                        item["source_version"],
                        item["source_url"],
                        now_us,
                    ),
                )
                count += 1
            c.execute("COMMIT")
            return count
        except Exception:
            c.execute("ROLLBACK")
            raise
        finally:
            c.close()

    def count(self):
        c = self._factory.connect(read_only=True)
        try:
            return int(c.execute("SELECT COUNT(*) FROM ecological_context").fetchone()[0])
        finally:
            c.close()

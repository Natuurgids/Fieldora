"""Application service for local ecological context."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from natureai_next.domain.ecology import EcologicalContext


@dataclass(frozen=True)
class EcologicalImportRow:
    row_number: int
    scientific_name: str
    matched_public_id: str | None
    matched_scientific_name: str | None
    match_kind: str
    suggestion: str | None
    record: dict


@dataclass(frozen=True)
class EcologicalImportPreview:
    rows: tuple[EcologicalImportRow, ...]

    @property
    def matched_count(self):
        return sum(1 for row in self.rows if row.matched_public_id)

    @property
    def unmatched_count(self):
        return len(self.rows) - self.matched_count


class EcologicalContextService:
    def __init__(self, store: object, *, now_us) -> None:
        self._store = store
        self._now_us = now_us

    def for_taxon(self, taxon_public_id: str | None) -> EcologicalContext | None:
        return self._store.for_taxon(taxon_public_id) if taxon_public_id else None

    def _read_csv(self, path: Path):
        if not path.is_file():
            raise FileNotFoundError(path)
        records = []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if (
                not reader.fieldnames
                or "scientific_name" not in reader.fieldnames
                or "source_name" not in reader.fieldnames
            ):
                raise ValueError("CSV must contain scientific_name and source_name columns")
            for row_number, row in enumerate(reader, start=2):
                name = (row.get("scientific_name") or "").strip()
                source = (row.get("source_name") or "").strip()
                if not name or not source:
                    raise ValueError(
                        f"row {row_number}: scientific_name and source_name are required"
                    )
                months = tuple(
                    sorted(
                        {
                            int(x)
                            for x in (row.get("seasonal_months") or "").replace(";", ",").split(",")
                            if x.strip()
                        }
                    )
                )
                if any(m < 1 or m > 12 for m in months):
                    raise ValueError(f"row {row_number}: invalid seasonal month for {name}")
                records.append(
                    dict(
                        row_number=row_number,
                        scientific_name=name,
                        conservation_status=(row.get("conservation_status") or "").strip() or None,
                        seasonal_months=months,
                        migration_status=(row.get("migration_status") or "").strip() or None,
                        habitats=tuple(
                            x.strip() for x in (row.get("habitats") or "").split(";") if x.strip()
                        ),
                        source_name=source,
                        source_version=(row.get("source_version") or "").strip() or None,
                        source_url=(row.get("source_url") or "").strip() or None,
                    )
                )
        return records

    def preview_csv(self, path: Path):
        rows = []
        for record in self._read_csv(path):
            match = self._store.match_taxon_name(record["scientific_name"])
            rows.append(
                EcologicalImportRow(
                    record["row_number"],
                    record["scientific_name"],
                    match["public_id"] if match else None,
                    match["scientific_name"] if match else None,
                    match["match_kind"] if match else "unmatched",
                    match.get("suggestion")
                    if match
                    else self._store.suggest_taxon_name(record["scientific_name"]),
                    record,
                )
            )
        return EcologicalImportPreview(tuple(rows))

    def import_preview(self, preview):
        records = []
        for row in preview.rows:
            if row.matched_public_id:
                item = dict(row.record)
                item["taxon_public_id"] = row.matched_public_id
                records.append(item)
        return self._store.upsert_many(records, now_us=self._now_us())

    def import_csv(self, path: Path):
        return self.import_preview(self.preview_csv(path))

    def write_unmatched_report(self, preview, path: Path):
        unmatched = [row for row in preview.rows if not row.matched_public_id]
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            w = csv.writer(handle)
            w.writerow(("row", "scientific_name", "suggested_accepted_name", "reason"))
            for row in unmatched:
                w.writerow(
                    (
                        row.row_number,
                        row.scientific_name,
                        row.suggestion or "",
                        "No installed taxonomy match",
                    )
                )
        return len(unmatched)

    def count(self):
        return self._store.count()

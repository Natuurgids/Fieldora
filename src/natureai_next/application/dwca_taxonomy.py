"""Streaming import of a GBIF Darwin Core Archive into an isolated source database."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import time
import zipfile
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TextIO
from xml.etree import ElementTree


@dataclass(frozen=True, slots=True)
class DwcaTaxonomyImportResult:
    source_public_id: str
    package_path: Path  # retained API name; now points to the isolated source database
    taxa_count: int
    names_count: int
    embedding_counts: tuple[int, int] | None = None


def _local(term: str) -> str:
    return term.rsplit("/", 1)[-1].rsplit("#", 1)[-1].strip()


def _decode_separator(value: str | None, default: str) -> str:
    return default if value is None else bytes(value, "utf-8").decode("unicode_escape")


class DwcaTaxonomyImportService:
    """Build and atomically publish one read-only database per taxonomy source.

    The active GBIF database is never opened for writing during an update. Rows are
    streamed into a ``.next`` database in bounded transactions, validated, and then
    published with an atomic file replacement. The operational Aperture Library and
    the shared AI databases are not touched.
    """

    SCHEMA_VERSION = 1
    BATCH_SIZE = 5000

    def __init__(self, resources: object | None = None) -> None:
        # Kept for source compatibility with the existing UI/bootstrap.
        self._resources = resources

    def run(
        self,
        archive_path: Path,
        *,
        workspace: Path | None = None,
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> DwcaTaxonomyImportResult:
        source = archive_path.expanduser().resolve()
        if not source.exists() or not (source.is_file() or source.is_dir()):
            raise FileNotFoundError(source)
        report = progress or (lambda _c, _t, _m: None)
        is_cancelled = cancelled or (lambda: False)
        root = (
            (
                workspace
                or Path(os.getenv("LOCALAPPDATA", Path.home()))
                / "NatureAI"
                / "NatureAI Next"
                / "taxonomy-sources"
            )
            .expanduser()
            .resolve()
        )
        root.mkdir(parents=True, exist_ok=True)

        checksum = self._source_checksum(source)
        source_id = f"gbif-dwca-{checksum[:16]}"
        final_db = root / "gbif.active.sqlite3"
        next_db = root / f"gbif.{checksum[:16]}.next.sqlite3"
        checkpoint = next_db.with_suffix(".checkpoint.json")
        resume_rows = 0
        resume_taxa = 0
        resume_names = 0
        if checkpoint.exists() and next_db.exists():
            try:
                saved = json.loads(checkpoint.read_text(encoding="utf-8"))
                if saved.get("checksum") == checksum:
                    resume_rows = int(saved.get("rows_scanned", 0))
                    resume_taxa = int(saved.get("taxa", 0))
                    resume_names = int(saved.get("names", 0))
                else:
                    next_db.unlink(missing_ok=True)
                    checkpoint.unlink(missing_ok=True)
            except Exception:
                next_db.unlink(missing_ok=True)
                checkpoint.unlink(missing_ok=True)
        else:
            next_db.unlink(missing_ok=True)
            checkpoint.unlink(missing_ok=True)

        report(1, 100, "Reading Darwin Core metadata…")
        descriptor, stream_factory = self._open_core(source)
        connection = sqlite3.connect(next_db)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA temp_store=FILE")
        connection.execute("PRAGMA cache_size=-32768")
        connection.execute("PRAGMA mmap_size=0")
        if resume_rows == 0:
            self._create_schema(connection)
        connection.execute(
            "INSERT OR REPLACE INTO source_metadata(key,value) VALUES(?,?)",
            ("import_state", "building"),
        )
        connection.commit()

        taxa_count, names_count, scanned, skipped = resume_taxa, resume_names, 0, 0
        batch_taxa: list[tuple[object, ...]] = []
        batch_names: list[tuple[object, ...]] = []
        started = time.monotonic()
        try:
            with stream_factory() as text:
                reader = csv.reader(
                    text,
                    delimiter=descriptor["delimiter"],
                    quotechar=descriptor["quote"] or None,
                )
                for _ in range(descriptor["ignore"]):
                    next(reader, None)
                for row_number, row in enumerate(reader, 1):
                    scanned += 1
                    if scanned <= resume_rows:
                        continue
                    if is_cancelled():
                        raise InterruptedError(
                            "GBIF taxonomy import cancelled at a safe batch boundary"
                        )
                    values = {
                        name: row[index].strip()
                        for index, name in descriptor["field_map"].items()
                        if index < len(row)
                    }
                    raw_id = (
                        values.get("taxonKey")
                        or values.get("acceptedTaxonKey")
                        or values.get("taxonID")
                        or (
                            row[descriptor["id_index"]].strip()
                            if descriptor["id_index"] is not None
                            and descriptor["id_index"] < len(row)
                            else ""
                        )
                        or f"dwca-{row_number}"
                    )
                    scientific = (
                        values.get("acceptedScientificName")
                        or values.get("scientificName")
                        or values.get("canonicalName")
                        or ""
                    ).strip()
                    if not scientific:
                        skipped += 1
                        continue
                    rank = (values.get("taxonRank") or "species").casefold()
                    status_text = (
                        values.get("taxonomicStatus") or values.get("taxonStatus") or "accepted"
                    ).casefold()
                    status = (
                        "accepted"
                        if status_text in {"accepted", "doubtful", "valid"}
                        else "unresolved"
                    )
                    batch_taxa.append(
                        (
                            raw_id,
                            scientific,
                            values.get("scientificNameAuthorship") or None,
                            rank,
                            status,
                            values.get("parentNameUsageID") or values.get("parentKey") or None,
                            values.get("acceptedNameUsageID")
                            or values.get("acceptedTaxonKey")
                            or None,
                            values.get("kingdom") or None,
                            values.get("phylum") or values.get("class") or None,
                            values.get("class") or None,
                            values.get("order") or None,
                            values.get("family") or None,
                        )
                    )
                    batch_names.append(
                        (
                            raw_id,
                            scientific,
                            "scientific",
                            "scientific",
                            1,
                            "GBIF Darwin Core Archive",
                        )
                    )
                    vernacular = (values.get("vernacularName") or "").strip()
                    if vernacular:
                        batch_names.append(
                            (
                                raw_id,
                                vernacular,
                                "vernacular",
                                values.get("language") or None,
                                1,
                                "GBIF Darwin Core Archive",
                            )
                        )
                    if len(batch_taxa) >= self.BATCH_SIZE:
                        inserted_taxa, inserted_names = self._flush(
                            connection, batch_taxa, batch_names
                        )
                        taxa_count += inserted_taxa
                        names_count += inserted_names
                        batch_taxa.clear()
                        batch_names.clear()
                        checkpoint.write_text(
                            json.dumps(
                                {
                                    "checksum": checksum,
                                    "rows_scanned": scanned,
                                    "taxa": taxa_count,
                                    "names": names_count,
                                }
                            ),
                            encoding="utf-8",
                        )
                        speed = int(scanned / max(0.1, time.monotonic() - started))
                        report(
                            min(94, 5 + scanned // 100000),
                            100,
                            f"GBIF: {scanned:,} rows scanned • {taxa_count:,} taxa staged • {speed:,} rows/s",
                        )
            inserted_taxa, inserted_names = self._flush(connection, batch_taxa, batch_names)
            taxa_count += inserted_taxa
            names_count += inserted_names
            report(95, 100, "Validating isolated GBIF taxonomy database…")
            integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
            if integrity != "ok":
                raise ValueError(f"GBIF taxonomy database integrity check failed: {integrity}")
            actual = int(connection.execute("SELECT count(*) FROM taxa").fetchone()[0])
            if actual <= 0:
                raise ValueError("The Darwin Core Archive contains no usable taxonomy records.")
            connection.execute(
                "INSERT OR REPLACE INTO source_metadata(key,value) VALUES('source_id',?)",
                (source_id,),
            )
            connection.execute(
                "INSERT OR REPLACE INTO source_metadata(key,value) VALUES('source_checksum',?)",
                (checksum,),
            )
            connection.execute(
                "INSERT OR REPLACE INTO source_metadata(key,value) VALUES('rows_scanned',?)",
                (str(scanned),),
            )
            connection.execute(
                "INSERT OR REPLACE INTO source_metadata(key,value) VALUES('rows_skipped',?)",
                (str(skipped),),
            )
            connection.execute(
                "INSERT OR REPLACE INTO source_metadata(key,value) VALUES('import_state','ready')"
            )
            connection.commit()
            # Publication moves only the main SQLite file.  Drain WAL completely
            # first so every committed EOF batch is present in that file.
            checkpoint_result = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if checkpoint_result and int(checkpoint_result[0]) != 0:
                raise RuntimeError(
                    f"GBIF taxonomy WAL checkpoint remained busy: {checkpoint_result}"
                )
            durable_actual = int(connection.execute("SELECT count(*) FROM taxa").fetchone()[0])
            if durable_actual != actual:
                raise RuntimeError(
                    "GBIF taxonomy row count changed while finalising the staging database"
                )
            checkpoint.write_text(
                json.dumps(
                    {
                        "checksum": checksum,
                        "rows_scanned": scanned,
                        "taxa": taxa_count,
                        "names": names_count,
                        "state": "validated",
                    }
                ),
                encoding="utf-8",
            )
        except Exception:
            connection.close()
            raise
        connection.close()

        report(98, 100, "Publishing the new GBIF source atomically…")
        previous = root / "gbif.previous.sqlite3"
        previous.unlink(missing_ok=True)
        if final_db.exists():
            os.replace(final_db, previous)
        os.replace(next_db, final_db)
        checkpoint.unlink(missing_ok=True)
        registry = root / "sources.json"
        registry.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "active": {
                        "gbif": {
                            "source_id": source_id,
                            "database": final_db.name,
                            "checksum": checksum,
                        }
                    },
                    "previous": previous.name if previous.exists() else None,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        report(100, 100, f"GBIF source published: {taxa_count:,} taxa and {names_count:,} names")
        return DwcaTaxonomyImportResult(source_id, final_db, taxa_count, names_count)

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.executescript("""
        CREATE TABLE source_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE taxa(
          source_taxon_id TEXT PRIMARY KEY,
          scientific_name TEXT NOT NULL,
          authorship TEXT,
          rank TEXT NOT NULL,
          status TEXT NOT NULL,
          parent_source_taxon_id TEXT,
          accepted_source_taxon_id TEXT,
          kingdom TEXT,
          major_group TEXT,
          taxon_class TEXT,
          taxon_order TEXT,
          family TEXT
        );
        CREATE TABLE taxon_names(
          source_taxon_id TEXT NOT NULL,
          name TEXT NOT NULL,
          name_type TEXT NOT NULL,
          language_tag TEXT,
          preferred INTEGER NOT NULL,
          source TEXT NOT NULL,
          UNIQUE(source_taxon_id,name,name_type,language_tag)
        );
        CREATE INDEX taxon_name_lookup ON taxon_names(name COLLATE NOCASE);
        CREATE INDEX taxon_scientific_lookup ON taxa(scientific_name COLLATE NOCASE);
        """)

    @staticmethod
    def _flush(
        connection: sqlite3.Connection,
        taxa: list[tuple[object, ...]],
        names: list[tuple[object, ...]],
    ) -> tuple[int, int]:
        if not taxa:
            return 0, 0
        connection.execute("BEGIN IMMEDIATE")
        try:
            before_taxa = connection.total_changes
            connection.executemany(
                "INSERT OR REPLACE INTO taxa VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", taxa
            )
            taxon_changes = connection.total_changes - before_taxa
            before_names = connection.total_changes
            connection.executemany("INSERT OR IGNORE INTO taxon_names VALUES(?,?,?,?,?,?)", names)
            name_changes = connection.total_changes - before_names
            connection.execute("COMMIT")
            return taxon_changes, name_changes
        except Exception:
            connection.execute("ROLLBACK")
            raise

    @classmethod
    def _read_archive(cls, path: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        """Compatibility helper for focused tests; production import is streaming."""
        descriptor, factory = cls._open_core(path)
        records_by_id: dict[str, dict[str, object]] = {}
        names_by_key: dict[tuple[str, str, str], dict[str, object]] = {}
        with factory() as text:
            reader = csv.reader(
                text, delimiter=descriptor["delimiter"], quotechar=descriptor["quote"] or None
            )
            for _ in range(descriptor["ignore"]):
                next(reader, None)
            for number, row in enumerate(reader, 1):
                values = {
                    name: row[index].strip()
                    for index, name in descriptor["field_map"].items()
                    if index < len(row)
                }
                scientific = (
                    values.get("scientificName") or values.get("acceptedScientificName") or ""
                )
                if not scientific:
                    continue
                sid = values.get("taxonKey") or values.get("taxonID") or f"dwca-{number}"
                records_by_id.setdefault(
                    sid,
                    {
                        "source_taxon_id": sid,
                        "scientific_name": scientific,
                        "kingdom": values.get("kingdom") or None,
                        "rank": (values.get("taxonRank") or "species").casefold(),
                        "status": "accepted",
                    },
                )
                names_by_key.setdefault(
                    (sid, scientific, "scientific"),
                    {"source_taxon_id": sid, "name": scientific, "name_type": "scientific"},
                )
        return list(records_by_id.values()), list(names_by_key.values())

    @staticmethod
    def _source_checksum(path: Path) -> str:
        digest = hashlib.sha256()
        if path.is_file():
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            return digest.hexdigest()
        for item in sorted(
            (p for p in path.rglob("*") if p.is_file()),
            key=lambda p: p.relative_to(path).as_posix().casefold(),
        ):
            relative = item.relative_to(path).as_posix().encode()
            digest.update(relative)
            with item.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _open_core(path: Path) -> tuple[dict[str, object], Callable[[], contextmanager[TextIO]]]:
        if path.is_dir():
            metas = list(path.rglob("meta.xml"))
            if len(metas) != 1:
                raise ValueError(
                    "Select one extracted Darwin Core Archive folder containing exactly one meta.xml."
                )
            meta_path = metas[0].resolve()
            root = meta_path.parent
            meta_bytes = meta_path.read_bytes()

            def member_factory(location: str, encoding: str):
                target = (root / Path(*PurePosixPath(location.replace("\\", "/")).parts)).resolve()
                target.relative_to(root)

                @contextmanager
                def opened():
                    with target.open(
                        "r", encoding=encoding, errors="replace", newline=""
                    ) as stream:
                        yield stream

                return opened
        else:
            archive = zipfile.ZipFile(path)
            names = {
                PurePosixPath(i.filename.replace("\\", "/")).as_posix().casefold(): i.filename
                for i in archive.infolist()
            }
            metas = [
                actual
                for folded, actual in names.items()
                if PurePosixPath(folded).name == "meta.xml"
            ]
            if len(metas) != 1:
                archive.close()
                raise ValueError("The ZIP must contain exactly one Darwin Core meta.xml.")
            meta_name = metas[0]
            parent = PurePosixPath(meta_name).parent
            meta_bytes = archive.read(meta_name)

            def member_factory(location: str, encoding: str):
                actual = names.get(
                    (parent / PurePosixPath(location.replace("\\", "/"))).as_posix().casefold()
                )
                if actual is None:
                    raise ValueError(f"Darwin Core core data file is missing: {location}")

                @contextmanager
                def opened():
                    raw = archive.open(actual, "r")
                    text = io.TextIOWrapper(raw, encoding=encoding, errors="replace", newline="")
                    try:
                        yield text
                    finally:
                        text.close()
                        archive.close()

                return opened

        try:
            meta = ElementTree.fromstring(meta_bytes)
        except ElementTree.ParseError as exc:
            raise ValueError("Darwin Core meta.xml is invalid.") from exc
        core = next((n for n in meta.iter() if n.tag.rsplit("}", 1)[-1] == "core"), None)
        if core is None:
            raise ValueError("Darwin Core meta.xml does not declare a core table.")
        location_node = next(
            (n for n in core.iter() if n.tag.rsplit("}", 1)[-1] == "location"), None
        )
        location = (location_node.text or "").strip() if location_node is not None else ""
        if not location:
            raise ValueError("Darwin Core meta.xml does not name the core data file.")
        field_map: dict[int, str] = {}
        id_index = None
        next_index = 0
        for node in core:
            tag = node.tag.rsplit("}", 1)[-1]
            if tag not in {"id", "field"}:
                continue
            raw = node.attrib.get("index")
            try:
                index = int(raw) if raw not in (None, "") else next_index
            except ValueError as exc:
                raise ValueError(
                    f"Darwin Core meta.xml has an invalid column index: {raw!r}"
                ) from exc
            next_index = max(next_index, index + 1)
            if tag == "id":
                id_index = index
            else:
                term = _local(node.attrib.get("term", ""))
                if term:
                    field_map[index] = term
        encoding = core.attrib.get("encoding", "UTF-8")
        return {
            "field_map": field_map,
            "id_index": id_index,
            "delimiter": _decode_separator(core.attrib.get("fieldsTerminatedBy"), "\t"),
            "quote": _decode_separator(core.attrib.get("fieldsEnclosedBy"), '"'),
            "ignore": int(core.attrib.get("ignoreHeaderLines", "0")),
        }, member_factory(location, encoding)


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _python_interpreter() -> Path:
    """Return a real Python interpreter, never a console-script launcher."""
    candidates = [
        getattr(sys, "_base_executable", None),
        Path(sys.prefix) / ("python.exe" if os.name == "nt" else "bin/python"),
        Path(sys.prefix) / ("pythonw.exe" if os.name == "nt" else "bin/python3"),
    ]
    for candidate in candidates:
        if (
            candidate
            and Path(candidate).is_file()
            and Path(candidate).name.casefold().startswith("python")
        ):
            return Path(candidate)
    executable = Path(sys.executable)
    if executable.name.casefold().startswith("python"):
        return executable
    raise RuntimeError(
        "A real Python interpreter could not be located for the detached taxonomy worker"
    )


def _detached_job_paths(source: Path, workspace: Path | None) -> tuple[Path, Path, str]:
    root = (
        (
            workspace
            or Path(os.getenv("LOCALAPPDATA", Path.home()))
            / "NatureAI"
            / "NatureAI Next"
            / "taxonomy-sources"
        )
        .expanduser()
        .resolve()
    )
    jobs = root / "jobs"
    jobs.mkdir(parents=True, exist_ok=True)
    stat = source.stat()
    identity = hashlib.sha256(
        f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode()
    ).hexdigest()[:20]
    return jobs / f"gbif-{identity}.json", jobs / f"gbif-{identity}.cancel", identity


def detached_taxonomy_job_state(
    source: Path, *, workspace: Path | None = None
) -> dict[str, object]:
    """Read the durable detached job status without launching or attaching a worker."""
    status_path, _cancel_path, _identity = _detached_job_paths(
        source.expanduser().resolve(), workspace
    )
    try:
        value = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def run_dwca_taxonomy_import_isolated(
    source: Path, *, workspace: Path | None = None, progress=None, cancelled=None
) -> DwcaTaxonomyImportResult:
    """Launch or reattach to a detached builder that survives Aperture restarts."""
    source = source.expanduser().resolve()
    report = progress or (lambda _c, _t, _m: None)
    is_cancelled = cancelled or (lambda: False)
    status_path, cancel_path, identity = _detached_job_paths(source, workspace)
    root = (
        (
            workspace
            or Path(os.getenv("LOCALAPPDATA", Path.home()))
            / "NatureAI"
            / "NatureAI Next"
            / "taxonomy-sources"
        )
        .expanduser()
        .resolve()
    )

    def launch() -> None:
        cancel_path.unlink(missing_ok=True)
        cmd = [
            str(_python_interpreter()),
            "-m",
            "natureai_next.application.dwca_taxonomy_worker",
            str(source),
            str(root),
            str(status_path),
            str(cancel_path),
        ]
        kwargs = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if os.name == "nt":
            kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            )
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(cmd, **kwargs)

    state = {}
    if status_path.exists():
        try:
            state = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception:
            state = {}
    if state.get("state") not in {"running", "ready"}:
        launch()
    while True:
        if is_cancelled():
            # The Activity Centre cancellation token is also raised during normal
            # application shutdown.  Never forward that lifecycle signal to the
            # detached builder: it owns its process and staging database and must
            # survive Aperture closing.  A future explicit taxonomy Cancel action
            # may create cancel_path directly.
            raise InterruptedError(
                "Detached GBIF taxonomy build continues independently; reopen Aperture to reattach"
            )
        try:
            state = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception:
            time.sleep(0.25)
            continue
        report(
            int(state.get("current", 0)),
            int(state.get("total", 100)),
            str(state.get("message", "Preparing taxonomy source…")),
        )
        if state.get("state") == "ready":
            return DwcaTaxonomyImportResult(
                str(state["source_public_id"]),
                Path(str(state["package_path"])),
                int(state["taxa_count"]),
                int(state["names_count"]),
            )
        if state.get("state") == "failed":
            raise RuntimeError(str(state.get("error", "Detached taxonomy builder failed")))
        if state.get("state") == "cancelled":
            raise InterruptedError("GBIF taxonomy source build cancelled")
        time.sleep(0.35)

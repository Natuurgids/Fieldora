"""Run the provisional 100,000-asset persistence benchmark."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.migrations import CORE_MIGRATIONS, MigrationRunner


def run(directory: Path, count: int = 100_000) -> dict[str, object]:
    path = directory / "persistence-benchmark.sqlite3"
    path.unlink(missing_ok=True)
    f = SqliteConnectionFactory(path)
    c = f.connect()
    MigrationRunner(CORE_MIGRATIONS, "benchmark").apply(c)
    c.execute(
        "INSERT INTO library_info VALUES(1,'benchmark',1,1,'0.1','Benchmark','en','[]','clean')"
    )
    started = time.perf_counter()
    c.execute("BEGIN IMMEDIATE")
    c.executemany(
        "INSERT INTO assets(public_id,media_type,lifecycle_state,created_at_us,modified_at_us,revision) VALUES(?,?,?,?,?,?)",
        ((f"asset-{n:08d}", "image", "active", n, n, 1) for n in range(count)),
    )
    c.execute("COMMIT")
    insert_seconds = time.perf_counter() - started
    started = time.perf_counter()
    rows = c.execute(
        "SELECT id,public_id FROM assets WHERE lifecycle_state='active' AND id>? ORDER BY id LIMIT 200",
        (max(0, count - 1000),),
    ).fetchall()
    query_ms = (time.perf_counter() - started) * 1000
    size = path.stat().st_size
    c.close()
    return {
        "asset_count": count,
        "insert_seconds": round(insert_seconds, 4),
        "assets_per_second": round(count / insert_seconds, 1),
        "keyset_query_ms": round(query_ms, 4),
        "page_rows": len(rows),
        "database_bytes": size,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--count", type=int, default=100_000)
    args = parser.parse_args()
    directory = args.directory or Path(tempfile.mkdtemp(prefix="natureai-benchmark-"))
    directory.mkdir(parents=True, exist_ok=True)
    print(json.dumps(run(directory, args.count), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

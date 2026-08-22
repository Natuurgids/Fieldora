"""Restart-safe, per-item storage operations for copy and move batches."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

OperationKind = Literal["copy", "move"]

@dataclass(frozen=True, slots=True)
class StorageOperationResult:
    public_id: str
    state: str
    source: Path
    destination: Path
    error: str | None = None

class StorageTransactionJournal:
    """Durable operation journal; every item commits independently."""
    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.database_path)
        c.row_factory = sqlite3.Row
        return c

    def _ensure_schema(self) -> None:
        with self._connect() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS storage_operation_journal(
                id INTEGER PRIMARY KEY, public_id TEXT NOT NULL UNIQUE,
                idempotency_key TEXT NOT NULL UNIQUE, kind TEXT NOT NULL,
                source_path TEXT NOT NULL, destination_path TEXT NOT NULL,
                expected_sha256 TEXT, state TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0, error TEXT,
                created_at_us INTEGER NOT NULL, modified_at_us INTEGER NOT NULL)""")
            c.commit()

    def queue(self, kind: OperationKind, source: Path, destination: Path, expected_sha256: str | None = None) -> str:
        source = source.expanduser().resolve(strict=False)
        destination = destination.expanduser().resolve(strict=False)
        key = hashlib.sha256(f"{kind}\0{source}\0{destination}".encode()).hexdigest()
        now = time.time_ns() // 1000
        with self._connect() as c:
            row = c.execute("SELECT public_id FROM storage_operation_journal WHERE idempotency_key=?", (key,)).fetchone()
            if row: return str(row[0])
            public_id = str(uuid.uuid4())
            c.execute("INSERT INTO storage_operation_journal(public_id,idempotency_key,kind,source_path,destination_path,expected_sha256,state,created_at_us,modified_at_us) VALUES(?,?,?,?,?,?,'pending',?,?)",
                      (public_id,key,kind,str(source),str(destination),expected_sha256,now,now))
            c.commit(); return public_id

    def list_recent(self, limit: int = 100):
        with self._connect() as c:
            return tuple(dict(row) for row in c.execute("SELECT * FROM storage_operation_journal ORDER BY modified_at_us DESC LIMIT ?", (limit,)).fetchall())

    def cancel(self, public_id: str) -> bool:
        now=time.time_ns()//1000
        with self._connect() as c:
            changed=c.execute("UPDATE storage_operation_journal SET state='cancelled',modified_at_us=? WHERE public_id=? AND state IN ('pending','failed')",(now,public_id)).rowcount
            c.commit(); return bool(changed)

    def retry(self, public_id: str) -> bool:
        now=time.time_ns()//1000
        with self._connect() as c:
            changed=c.execute("UPDATE storage_operation_journal SET state='pending',error=NULL,modified_at_us=? WHERE public_id=? AND state='failed'",(now,public_id)).rowcount
            c.commit(); return bool(changed)

    def run_pending(self, *, cancel: callable | None = None) -> tuple[StorageOperationResult, ...]:
        with self._connect() as c:
            rows = c.execute("SELECT * FROM storage_operation_journal WHERE state IN ('pending','running') ORDER BY id").fetchall()
        results=[]
        for row in rows:
            if cancel:
                try: cancel()
                except Exception: break
            results.append(self._run_one(row))
        return tuple(results)

    def _run_one(self, row: sqlite3.Row) -> StorageOperationResult:
        src, dst = Path(row['source_path']), Path(row['destination_path'])
        now=time.time_ns()//1000
        with self._connect() as c:
            c.execute("UPDATE storage_operation_journal SET state='running',attempt_count=attempt_count+1,error=NULL,modified_at_us=? WHERE id=?",(now,row['id'])); c.commit()
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            part=dst.with_name(dst.name+'.aperture-part')
            if not dst.is_file():
                shutil.copy2(src, part)
                digest=_sha256(part)
                expected=row['expected_sha256'] or _sha256(src)
                if digest != expected: raise OSError('destination verification failed')
                os.replace(part, dst)
            expected=row['expected_sha256'] or _sha256(dst)
            if _sha256(dst) != expected: raise OSError('destination verification failed')
            if row['kind']=='move' and src.exists(): src.unlink()
            state,error='completed',None
        except Exception as exc:
            state,error='failed',f"{type(exc).__name__}: {exc}"
            try: part.unlink(missing_ok=True)
            except OSError: pass
        now=time.time_ns()//1000
        with self._connect() as c:
            c.execute("UPDATE storage_operation_journal SET state=?,error=?,modified_at_us=? WHERE id=?",(state,error,now,row['id'])); c.commit()
        return StorageOperationResult(str(row['public_id']),state,src,dst,error)

def _sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

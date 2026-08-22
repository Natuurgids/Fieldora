from __future__ import annotations

import sqlite3
from pathlib import Path

from natureai_next.infrastructure.database.migrations import CORE_MIGRATIONS
from natureai_next.infrastructure.database.migrations.core import MigrationRunner
from natureai_next.application.storage import AssetStorageService


def _db(path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    MigrationRunner(CORE_MIGRATIONS, 'test').apply(c)
    return c

def test_migration_enforces_one_initial_observation(tmp_path: Path) -> None:
    c = _db(tmp_path / 'catalog.db')
    cols = {r[1] for r in c.execute('PRAGMA table_info(asset_storage_locations)')}
    assert {'provenance_role','discovered_at_us'} <= cols
    indexes = {r[1] for r in c.execute('PRAGMA index_list(asset_storage_locations)')}
    assert 'ux_asset_one_initial_observation' in indexes

def test_resolver_opens_available_follow_up(tmp_path: Path) -> None:
    db = tmp_path / 'catalog.db'; c = _db(db)
    now=1
    aid=c.execute("INSERT INTO assets(public_id,media_type,lifecycle_state,created_at_us,modified_at_us) VALUES('a','image','active',?,?)",(now,now)).lastrowid
    pid=c.execute("INSERT INTO storage_providers(public_id,kind,display_name,configuration_json,created_at_us,modified_at_us) VALUES('p','local_filesystem','Local','{}',?,?)",(now,now)).lastrowid
    missing=tmp_path/'camera'/'x.jpg'; available=tmp_path/'ssd'/'x.jpg'; available.parent.mkdir(); available.write_bytes(b'x')
    for public,path,prov in [('s1',missing,'initial'),('s2',available,'follow_up')]:
        norm=str(path); key=norm.casefold()
        c.execute("INSERT INTO asset_storage_locations(public_id,asset_id,provider_id,role,normalized_path,path_key,health,is_primary,created_at_us,modified_at_us,provenance_role,discovered_at_us) VALUES(?,?,?,'source',?,?,'available',0,?,?,?,?)",(public,aid,pid,norm,key,now,now,prov,now))
    c.commit(); c.close()
    assert AssetStorageService(db).resolve_original(aid) == available

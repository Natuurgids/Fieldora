"""Search, saved query, collection hierarchy, and geography migration."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
ALTER TABLE collections ADD COLUMN parent_collection_id INTEGER REFERENCES collections(id) ON DELETE SET NULL;
ALTER TABLE collections ADD COLUMN position_key TEXT NOT NULL DEFAULT '';
CREATE INDEX ix_collections_parent_position ON collections(parent_collection_id,position_key,name);
CREATE TABLE saved_searches(id INTEGER PRIMARY KEY, public_id TEXT NOT NULL UNIQUE, name TEXT NOT NULL COLLATE NOCASE UNIQUE, query_json TEXT NOT NULL CHECK(json_valid(query_json)), query_schema_version INTEGER NOT NULL, created_at_us INTEGER NOT NULL, modified_at_us INTEGER NOT NULL);
CREATE VIRTUAL TABLE asset_search_fts USING fts5(asset_public_id UNINDEXED, title, caption, user_notes, tags, tokenize='unicode61 remove_diacritics 2');
CREATE TRIGGER asset_search_fts_assets_ai AFTER INSERT ON assets BEGIN INSERT INTO asset_search_fts(rowid,asset_public_id,title,caption,user_notes,tags) VALUES(new.id,new.public_id,COALESCE(new.title,''),COALESCE(new.caption,''),COALESCE(new.user_notes,''),''); END;
CREATE TRIGGER asset_search_fts_assets_ad AFTER DELETE ON assets BEGIN DELETE FROM asset_search_fts WHERE rowid=old.id; END;
CREATE TRIGGER asset_search_fts_assets_au AFTER UPDATE OF title,caption,user_notes ON assets BEGIN UPDATE asset_search_fts SET title=COALESCE(new.title,''),caption=COALESCE(new.caption,''),user_notes=COALESCE(new.user_notes,'') WHERE rowid=new.id; END;
CREATE TRIGGER asset_search_fts_tags_ai AFTER INSERT ON asset_tags BEGIN UPDATE asset_search_fts SET tags=COALESCE((SELECT group_concat(t.display_name,' ') FROM asset_tags x JOIN tags t ON t.id=x.tag_id WHERE x.asset_id=new.asset_id),'') WHERE rowid=new.asset_id; END;
CREATE TRIGGER asset_search_fts_tags_ad AFTER DELETE ON asset_tags BEGIN UPDATE asset_search_fts SET tags=COALESCE((SELECT group_concat(t.display_name,' ') FROM asset_tags x JOIN tags t ON t.id=x.tag_id WHERE x.asset_id=old.asset_id),'') WHERE rowid=old.asset_id; END;
CREATE UNIQUE INDEX ux_asset_locations_role ON asset_locations(asset_id,role) WHERE role IN ('capture','subject','user_defined');
INSERT INTO asset_search_fts(rowid,asset_public_id,title,caption,user_notes,tags)
SELECT a.id,a.public_id,COALESCE(a.title,''),COALESCE(a.caption,''),COALESCE(a.user_notes,''),COALESCE((SELECT group_concat(t.display_name,' ') FROM asset_tags x JOIN tags t ON t.id=x.tag_id WHERE x.asset_id=a.id),'') FROM assets a;
"""
MIGRATION = Migration(4, "search_collections_geography", SQL)

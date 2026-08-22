"""Observation identity, multi-asset evidence, and personal-history indexes."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
CREATE TABLE observation_assets(
 observation_id INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
 asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
 role TEXT NOT NULL DEFAULT 'evidence' CHECK(role IN ('primary','evidence')),
 linked_at_us INTEGER NOT NULL,
 PRIMARY KEY(observation_id,asset_id)
);
INSERT INTO observation_assets(observation_id,asset_id,role,linked_at_us)
SELECT id,asset_id,'primary',created_at_us FROM observations;
CREATE UNIQUE INDEX ux_observation_assets_primary
 ON observation_assets(observation_id) WHERE role='primary';
CREATE INDEX ix_observation_assets_asset ON observation_assets(asset_id,observation_id);
CREATE INDEX ix_observations_confirmed_taxon
 ON observations(taxon_id,created_at_us,id) WHERE confirmation_state='confirmed' AND taxon_id IS NOT NULL;
"""

MIGRATION = Migration(14, "observation_intelligence", SQL)

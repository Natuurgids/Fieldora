"""Fieldora 5.2 observation assertions, referrals, relationships and contribution state."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
CREATE TABLE observation_assertions(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 observation_id INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
 parent_assertion_id INTEGER REFERENCES observation_assertions(id),
 assertion_kind TEXT NOT NULL CHECK(assertion_kind IN ('observer','ai','specialist','authority','reference')),
 proposed_name TEXT NOT NULL,
 taxon_public_id TEXT,
 author TEXT NOT NULL,
 authority_level INTEGER NOT NULL DEFAULT 0 CHECK(authority_level BETWEEN 0 AND 9),
 confidence REAL CHECK(confidence IS NULL OR confidence BETWEEN 0 AND 1),
 status TEXT NOT NULL CHECK(status IN ('proposed','accepted','rejected','disputed','superseded')),
 rationale TEXT NOT NULL DEFAULT '',
 evidence_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(evidence_json)),
 created_at_us INTEGER NOT NULL,
 decided_at_us INTEGER,
 decided_by TEXT
);
CREATE INDEX ix_observation_assertions_history
 ON observation_assertions(observation_id,created_at_us,id);
CREATE TABLE observation_review_referrals(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 observation_id INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
 assertion_id INTEGER REFERENCES observation_assertions(id),
 referred_by TEXT NOT NULL,
 referred_to TEXT NOT NULL,
 authority_level INTEGER NOT NULL CHECK(authority_level BETWEEN 1 AND 9),
 status TEXT NOT NULL CHECK(status IN ('open','accepted','declined','completed','escalated','cancelled')),
 question TEXT NOT NULL DEFAULT '',
 response TEXT NOT NULL DEFAULT '',
 parent_referral_id INTEGER REFERENCES observation_review_referrals(id),
 created_at_us INTEGER NOT NULL,
 updated_at_us INTEGER NOT NULL
);
CREATE INDEX ix_observation_referrals_queue
 ON observation_review_referrals(referred_to,status,authority_level,created_at_us);
CREATE TABLE observation_context_links(
 observation_id INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
 context_type TEXT NOT NULL CHECK(context_type IN ('project','dossier','collection')),
 context_public_id TEXT NOT NULL,
 linked_by TEXT NOT NULL,
 linked_at_us INTEGER NOT NULL,
 PRIMARY KEY(observation_id,context_type,context_public_id)
);
CREATE INDEX ix_observation_context_target
 ON observation_context_links(context_type,context_public_id,observation_id);
CREATE TABLE external_contributions(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 observation_id INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
 connector_id TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('draft','validated','queued','submitted','synchronised','failed','withdrawn')),
 remote_id TEXT,
 remote_url TEXT,
 request_fingerprint TEXT NOT NULL,
 response_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(response_json)),
 last_error TEXT NOT NULL DEFAULT '',
 created_at_us INTEGER NOT NULL,
 updated_at_us INTEGER NOT NULL,
 UNIQUE(observation_id,connector_id,request_fingerprint)
);
CREATE INDEX ix_external_contribution_state
 ON external_contributions(connector_id,state,updated_at_us);
"""

MIGRATION = Migration(39, "fieldora_5_2_unified_observation_workflow", SQL)

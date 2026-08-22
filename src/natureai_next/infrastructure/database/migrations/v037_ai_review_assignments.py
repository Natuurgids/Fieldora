"""Assignable, auditable legacy photo-review queues."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
CREATE TABLE ai_review_assignments(
    suggestion_id INTEGER PRIMARY KEY REFERENCES ai_suggestions(id) ON DELETE CASCADE,
    assigned_to TEXT NOT NULL,
    assigned_by TEXT NOT NULL,
    assigned_at_us INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX ix_ai_review_assignments_user
    ON ai_review_assignments(assigned_to,assigned_at_us DESC);
CREATE TABLE ai_review_assignment_events(
    id INTEGER PRIMARY KEY,
    suggestion_id INTEGER NOT NULL REFERENCES ai_suggestions(id) ON DELETE CASCADE,
    assigned_to TEXT,
    assigned_by TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN('assigned','reassigned','unassigned','completed')),
    note TEXT NOT NULL DEFAULT '',
    created_at_us INTEGER NOT NULL
);
CREATE INDEX ix_ai_review_assignment_events_suggestion
    ON ai_review_assignment_events(suggestion_id,created_at_us DESC);
"""

MIGRATION = Migration(37, "assignable AI review queues", SQL)

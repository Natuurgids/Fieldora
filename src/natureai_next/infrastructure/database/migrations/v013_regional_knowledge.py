"""Per-library regional profile and occurrence evidence metadata."""

from natureai_next.infrastructure.database.migrations.core import Migration

MIGRATION = Migration(
    13,
    "regional_knowledge",
    r"""
CREATE TABLE regional_profiles(
 id INTEGER PRIMARY KEY CHECK(id=1),
 primary_continent_code TEXT,
 include_global_fallback INTEGER NOT NULL DEFAULT 1 CHECK(include_global_fallback IN(0,1)),
 preferred_languages_json TEXT NOT NULL DEFAULT '["en","scientific"]',
 modified_at_us INTEGER NOT NULL
);
CREATE TABLE regional_profile_countries(
 country_code TEXT PRIMARY KEY,
 continent_code TEXT NOT NULL,
 country_name TEXT NOT NULL,
 priority INTEGER NOT NULL CHECK(priority>=0),
 verified_by TEXT,
 modified_at_us INTEGER NOT NULL
);
CREATE INDEX ix_regional_profile_countries_continent
 ON regional_profile_countries(continent_code,priority,country_code);
""",
)

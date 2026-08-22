"""Map-ready longitudinal observation foundation."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
CREATE TABLE monitoring_projects(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL,
 description TEXT,
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('planned','active','paused','completed','archived')),
 starts_at_us INTEGER,
 ends_at_us INTEGER,
 created_at_us INTEGER NOT NULL,
 modified_at_us INTEGER NOT NULL,
 CHECK(ends_at_us IS NULL OR starts_at_us IS NULL OR ends_at_us>=starts_at_us)
);
CREATE INDEX ix_monitoring_projects_status_name ON monitoring_projects(status,name COLLATE NOCASE,id);

CREATE TABLE spatial_regions(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL,
 region_type TEXT NOT NULL DEFAULT 'area' CHECK(region_type IN ('area','site_boundary','survey_area','saved_selection','administrative','ecological')),
 geometry_type TEXT NOT NULL CHECK(geometry_type IN ('bbox','polygon','multipolygon')),
 geometry_json TEXT NOT NULL CHECK(json_valid(geometry_json)),
 min_latitude REAL NOT NULL CHECK(min_latitude BETWEEN -90 AND 90),
 min_longitude REAL NOT NULL CHECK(min_longitude BETWEEN -180 AND 180),
 max_latitude REAL NOT NULL CHECK(max_latitude BETWEEN -90 AND 90),
 max_longitude REAL NOT NULL CHECK(max_longitude BETWEEN -180 AND 180),
 geometry_source TEXT NOT NULL DEFAULT 'user' CHECK(geometry_source IN ('user','import','plugin','map','external')),
 created_at_us INTEGER NOT NULL,
 modified_at_us INTEGER NOT NULL,
 CHECK(min_latitude<=max_latitude),
 CHECK(min_longitude<=max_longitude)
);
CREATE INDEX ix_spatial_regions_bounds ON spatial_regions(min_latitude,max_latitude,min_longitude,max_longitude);

CREATE TABLE monitoring_sites(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL,
 description TEXT,
 location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
 boundary_region_id INTEGER REFERENCES spatial_regions(id) ON DELETE SET NULL,
 habitat TEXT,
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','inactive','retired')),
 created_at_us INTEGER NOT NULL,
 modified_at_us INTEGER NOT NULL
);
CREATE INDEX ix_monitoring_sites_location ON monitoring_sites(location_id,id) WHERE location_id IS NOT NULL;
CREATE INDEX ix_monitoring_sites_boundary ON monitoring_sites(boundary_region_id,id) WHERE boundary_region_id IS NOT NULL;

CREATE TABLE observation_series(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 title TEXT NOT NULL,
 description TEXT,
 series_type TEXT NOT NULL DEFAULT 'monitoring' CHECK(series_type IN ('monitoring','same_organism','same_population','same_site','phenology','comparison','other')),
 project_id INTEGER REFERENCES monitoring_projects(id) ON DELETE SET NULL,
 site_id INTEGER REFERENCES monitoring_sites(id) ON DELETE SET NULL,
 created_at_us INTEGER NOT NULL,
 modified_at_us INTEGER NOT NULL
);
CREATE INDEX ix_observation_series_project ON observation_series(project_id,id) WHERE project_id IS NOT NULL;
CREATE INDEX ix_observation_series_site ON observation_series(site_id,id) WHERE site_id IS NOT NULL;

CREATE TABLE project_sites(
 project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
 site_id INTEGER NOT NULL REFERENCES monitoring_sites(id) ON DELETE CASCADE,
 linked_at_us INTEGER NOT NULL,
 PRIMARY KEY(project_id,site_id)
);
CREATE INDEX ix_project_sites_site ON project_sites(site_id,project_id);

CREATE TABLE observation_project_links(
 observation_id INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
 project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
 linked_at_us INTEGER NOT NULL,
 PRIMARY KEY(observation_id,project_id)
);
CREATE INDEX ix_observation_project_project ON observation_project_links(project_id,observation_id);

CREATE TABLE observation_site_links(
 observation_id INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
 site_id INTEGER NOT NULL REFERENCES monitoring_sites(id) ON DELETE CASCADE,
 linked_at_us INTEGER NOT NULL,
 PRIMARY KEY(observation_id,site_id)
);
CREATE INDEX ix_observation_site_site ON observation_site_links(site_id,observation_id);

CREATE TABLE observation_series_members(
 series_id INTEGER NOT NULL REFERENCES observation_series(id) ON DELETE CASCADE,
 observation_id INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
 sequence_number INTEGER,
 linked_at_us INTEGER NOT NULL,
 PRIMARY KEY(series_id,observation_id),
 UNIQUE(series_id,sequence_number)
);
CREATE INDEX ix_observation_series_observation ON observation_series_members(observation_id,series_id);

CREATE TABLE observation_relationships(
 source_observation_id INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
 target_observation_id INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
 relationship_type TEXT NOT NULL CHECK(relationship_type IN ('revisits','same_organism','same_population','same_habitat','same_nest','same_colony','follow_up','verification','comparison','related')),
 notes TEXT,
 created_at_us INTEGER NOT NULL,
 PRIMARY KEY(source_observation_id,target_observation_id,relationship_type),
 CHECK(source_observation_id<>target_observation_id)
);
CREATE INDEX ix_observation_relationships_target ON observation_relationships(target_observation_id,relationship_type,source_observation_id);

CREATE TABLE map_bookmarks(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL,
 center_latitude REAL NOT NULL CHECK(center_latitude BETWEEN -90 AND 90),
 center_longitude REAL NOT NULL CHECK(center_longitude BETWEEN -180 AND 180),
 zoom_level REAL NOT NULL CHECK(zoom_level>=0),
 region_id INTEGER REFERENCES spatial_regions(id) ON DELETE SET NULL,
 filter_json TEXT CHECK(filter_json IS NULL OR json_valid(filter_json)),
 created_at_us INTEGER NOT NULL,
 modified_at_us INTEGER NOT NULL
);
CREATE INDEX ix_map_bookmarks_name ON map_bookmarks(name COLLATE NOCASE,id);
"""

MIGRATION = Migration(18, "spatial_longitudinal", SQL)

"""Fieldora Project work-management domain and SQLite application service.

The project module deliberately owns a fresh schema.  It does not import the
former lightweight Science ``projects`` snapshot.
"""

from __future__ import annotations

import json
import csv
import math
import io
import os
import sqlite3
import time
import zipfile
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from html import escape
from pathlib import Path
from uuid import uuid4

SCHEMA_VERSION = 6

ROLE_PERMISSIONS = {
    "admin": frozenset({"view", "create", "edit", "delete", "manage", "report", "portal"}),
    "manager": frozenset({"view", "create", "edit", "manage", "report", "portal"}),
    "contributor": frozenset({"view", "create", "edit"}),
    "guest": frozenset({"view"}),
}

PRIORITIES = ("critical", "high", "normal", "low")
RECURRENCES = ("none", "daily", "weekly", "monthly")
QUALITY_RULES = {
    "missing_coordinates": "Missing coordinates",
    "missing_date": "Missing date",
    "impossible_coordinates": "Impossible coordinates",
    "outside_expected_range": "Observation outside expected range",
    "duplicate_observation": "Possible duplicate observation",
    "conflicting_identification": "Conflicting identifications",
    "low_quality_evidence": "Low-quality evidence",
    "missing_licence_consent": "Missing licence or consent",
    "taxonomy_mismatch": "Taxonomy mismatch",
    "anomalous_measurement": "Anomalous measurement",
    "incomplete_sampling_protocol": "Incomplete sampling protocol",
}


def _safe_export_name(value: str) -> str:
    safe = "".join(character if character.isalnum() or character in "-_." else "-" for character in value)
    return safe.strip(".-") or "media-file"


def _research_map_html(project_name: str, collection: dict) -> str:
    rings = [feature["geometry"]["coordinates"][0] for feature in collection["features"]]
    points = [point for ring in rings for point in ring]
    if points:
        west, east = min(p[0] for p in points), max(p[0] for p in points)
        south, north = min(p[1] for p in points), max(p[1] for p in points)
    else:
        west, east, south, north = -180.0, 180.0, -90.0, 90.0
    dx, dy = max(east - west, 0.01), max(north - south, 0.01)
    west, east = west - dx * .08, east + dx * .08
    south, north = south - dy * .08, north + dy * .08
    def xy(point):
        return ((point[0] - west) / (east - west) * 760 + 20, (north - point[1]) / (north - south) * 460 + 20)
    polygons = "".join(
        f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x,y in map(xy, ring))}"/>'
        for ring in rings
    )
    return f"""<!doctype html><meta charset='utf-8'><title>{escape(project_name)} research map</title>
<style>body{{font:15px system-ui;margin:2rem;background:#f5f7f5;color:#172019}}svg{{max-width:100%;height:auto;background:#eaf0e9;border:1px solid #819184}}polygon{{fill:#2f8f5b55;stroke:#17663c;stroke-width:3}}.grid{{stroke:#cad4cc;stroke-width:1}}code{{word-break:break-all}}</style>
<h1>{escape(project_name)} — research area</h1><p>Portable WGS84 project map. The authoritative geometry is <code>research-areas.geojson</code>.</p>
<svg viewBox='0 0 800 500' role='img' aria-label='Project research polygons'><path class='grid' d='M20 250H780M400 20V480'/>{polygons}</svg>
<p>Bounds: {west:.6f}, {south:.6f} — {east:.6f}, {north:.6f}</p>"""


def _project_index_html(project, tasks, notes, areas, media, snapshots=(), *, embed_audio_video: bool) -> str:
    media_rows = []
    for row in media:
        title = escape(str(row.get("title") or row.get("original_filename") or row.get("asset_public_id")))
        media_type = str(row.get("media_type") or "other")
        path = row.get("package_path")
        preview = ""
        if path and media_type == "photo":
            preview = f"<img loading='lazy' src='{escape(str(path))}' alt='{title}'>"
        elif path and media_type == "sound" and embed_audio_video:
            preview = f"<audio controls preload='metadata' src='{escape(str(path))}'></audio>"
        elif path and media_type == "video" and embed_audio_video:
            preview = f"<video controls preload='metadata' src='{escape(str(path))}'></video>"
        elif path:
            preview = f"<a href='{escape(str(path))}'>Open packaged file</a>"
        media_rows.append(f"<article><h3>{title}</h3><p>{escape(media_type.title())} · {escape(str(row.get('asset_public_id')))}</p>{preview}<p>{escape(str(row.get('note') or ''))}</p></article>")
    note_html = "".join(f"<article><h3>{escape(str(row['title']))}</h3><p>{escape(str(row['body'])).replace(chr(10), '<br>')}</p></article>" for row in notes)
    task_rows = "".join(f"<tr><td>{escape(row.title)}</td><td>{escape(row.status_name)}</td><td>{escape(row.owner_id)}</td><td>{escape(row.due_date)}</td></tr>" for row in tasks)
    snapshot_html = "".join(
        f"<article><h3>{escape(str(row.get('name') or 'Map snapshot'))}</h3><img loading='lazy' src='{escape(str(row['package_path']))}' alt='StreetMaps project snapshot'></article>"
        for row in snapshots if row.get("package_path")
    )
    return f"""<!doctype html><meta charset='utf-8'><title>{escape(project.name)} — Fieldora research package</title>
<style>body{{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#18221b}}nav a{{margin-right:1rem}}section{{margin:2rem 0}}article{{border:1px solid #ccd5ce;border-radius:9px;padding:1rem;margin:.8rem 0}}img,video{{max-width:680px;max-height:480px}}audio{{width:min(680px,100%)}}table{{border-collapse:collapse;width:100%}}th,td{{text-align:left;border-bottom:1px solid #ddd;padding:.5rem}}</style>
<h1>{escape(project.name)}</h1><p>Structured offline Fieldora project research package.</p><nav><a href='maps/research-map.html'>Research map</a><a href='maps/research-areas.geojson'>GeoJSON</a><a href='data/media-index.csv'>Media index</a></nav>
<section><h2>Project</h2><p>Status: {escape(project.status)} · Owner: {escape(project.owner_id)} · {escape(project.start_date)}—{escape(project.due_date)}</p></section>
<section><h2>Research areas ({len(areas)})</h2><p><a href='maps/research-map.html'>View attached project map</a></p></section>
<section><h2>StreetMaps snapshots ({len(snapshots)})</h2>{snapshot_html or '<p>No map snapshots selected.</p>'}</section>
<section><h2>Notes ({len(notes)})</h2>{note_html or '<p>No notes selected.</p>'}</section>
<section><h2>Tasks ({len(tasks)})</h2><table><tr><th>Task</th><th>Status</th><th>Owner</th><th>Due</th></tr>{task_rows}</table></section>
<section><h2>Related media and documents ({len(media)})</h2>{''.join(media_rows) or '<p>No media selected.</p>'}</section>"""


def _now_us() -> int:
    return time.time_ns() // 1_000


def _id() -> str:
    return str(uuid4())


def _validate_date(value: str, label: str) -> None:
    if value:
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{label} must use YYYY-MM-DD") from exc


@dataclass(frozen=True, slots=True)
class ProjectSummary:
    project_id: str
    name: str
    status: str
    owner_id: str
    start_date: str
    due_date: str
    budget: float
    currency: str


@dataclass(frozen=True, slots=True)
class TaskSummary:
    task_id: str
    project_id: str
    parent_task_id: str | None
    title: str
    status_id: str
    status_name: str
    status_category: str
    owner_id: str
    priority: str
    start_date: str
    due_date: str
    estimate_hours: float
    actual_hours: float
    progress: int
    blocked: bool
    milestone: bool
    phase_id: str | None = None
    phase_name: str = ""
    sprint_id: str | None = None
    sprint_name: str = ""
    manual_estimate_hours: float = 0.0
    calculated_estimate_hours: float = 0.0
    effective_estimate_hours: float = 0.0
    realized_hours: float = 0.0


@dataclass(frozen=True, slots=True)
class ProjectExportOptions:
    include_project: bool = True
    include_tasks: bool = True
    include_notes: bool = True
    include_research_areas: bool = True
    include_map_snapshots: bool = True
    include_media_index: bool = True
    include_original_media: bool = False
    include_task_attachments: bool = True
    embed_audio_video: bool = False
    include_activity: bool = True
    include_surveys: bool = True
    include_measurements_samples: bool = True
    include_quality_audit: bool = True


class ProjectManagementService:
    """Transactional work-management service shared by desktop and server UI."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def public_holidays(self, start_date: str, end_date: str) -> tuple[dict, ...]:
        """Return public holidays in the inclusive ISO-date range.

        The calendar UI calls this method during initial project restoration, so it
        must be available on every service instance, including a clean database.
        """
        start = str(start_date or "").strip()
        end = str(end_date or "").strip()
        if not start or not end:
            return ()
        if end < start:
            start, end = end, start
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT holiday_date,name FROM pm_holidays "
                "WHERE holiday_date BETWEEN ? AND ? ORDER BY holiday_date,name",
                (start, end),
            ).fetchall()
        return tuple({"date": row["holiday_date"], "name": row["name"]} for row in rows)

    def add_public_holiday(self, holiday_date: str, name: str) -> None:
        """Create or rename a public holiday used by calendar/capacity views."""
        day = str(holiday_date or "").strip()
        label = str(name or "").strip()
        if not day or not label:
            raise ValueError("holiday date and name are required")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO pm_holidays(holiday_date,name) VALUES(?,?) "
                "ON CONFLICT(holiday_date) DO UPDATE SET name=excluded.name",
                (day, label),
            )

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS pm_schema(
                    id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER NOT NULL
                );
                INSERT OR IGNORE INTO pm_schema(id,version) VALUES(1,1);
                CREATE TABLE IF NOT EXISTS pm_projects(
                    project_id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',owner_id TEXT NOT NULL DEFAULT '',
                    start_date TEXT NOT NULL DEFAULT '',due_date TEXT NOT NULL DEFAULT '',
                    budget REAL NOT NULL DEFAULT 0,currency TEXT NOT NULL DEFAULT 'EUR',
                    template_id TEXT,client_name TEXT NOT NULL DEFAULT '',
                    created_at_us INTEGER NOT NULL,updated_at_us INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pm_statuses(
                    status_id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES pm_projects(project_id)
                        ON DELETE CASCADE,name TEXT NOT NULL,category TEXT NOT NULL,
                    color TEXT NOT NULL,display_order INTEGER NOT NULL,wip_limit INTEGER,
                    UNIQUE(project_id,name)
                );
                CREATE TABLE IF NOT EXISTS pm_phases(
                    phase_id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES pm_projects(project_id)
                        ON DELETE CASCADE,name TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',
                    planned_budget REAL NOT NULL DEFAULT 0,realized_budget REAL NOT NULL DEFAULT 0,
                    display_order INTEGER NOT NULL DEFAULT 0,created_by TEXT NOT NULL,
                    created_at_us INTEGER NOT NULL,updated_at_us INTEGER NOT NULL,
                    UNIQUE(project_id,name)
                );
                CREATE TABLE IF NOT EXISTS pm_sprints(
                    sprint_id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES pm_projects(project_id)
                        ON DELETE CASCADE,name TEXT NOT NULL,start_date TEXT NOT NULL DEFAULT '',
                    end_date TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'planned',
                    goal TEXT NOT NULL DEFAULT '',created_by TEXT NOT NULL,created_at_us INTEGER NOT NULL,
                    updated_at_us INTEGER NOT NULL,UNIQUE(project_id,name)
                );
                CREATE TABLE IF NOT EXISTS pm_tasks(
                    task_id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES pm_projects(project_id)
                        ON DELETE CASCADE,parent_task_id TEXT REFERENCES pm_tasks(task_id) ON DELETE CASCADE,
                    title TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',
                    status_id TEXT NOT NULL REFERENCES pm_statuses(status_id),
                    owner_id TEXT NOT NULL DEFAULT '',priority TEXT NOT NULL DEFAULT 'normal',
                    start_date TEXT NOT NULL DEFAULT '',due_date TEXT NOT NULL DEFAULT '',
                    estimate_hours REAL NOT NULL DEFAULT 0,budget REAL NOT NULL DEFAULT 0,
                    progress INTEGER NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 100),
                    recurrence TEXT NOT NULL DEFAULT 'none',recurrence_end TEXT NOT NULL DEFAULT '',
                    milestone INTEGER NOT NULL DEFAULT 0 CHECK(milestone IN(0,1)),
                    sprint TEXT NOT NULL DEFAULT '',position INTEGER NOT NULL DEFAULT 0,
                    phase_id TEXT REFERENCES pm_phases(phase_id) ON DELETE SET NULL,
                    sprint_id TEXT REFERENCES pm_sprints(sprint_id) ON DELETE SET NULL,
                    realized_hours REAL NOT NULL DEFAULT 0,
                    created_by TEXT NOT NULL,created_at_us INTEGER NOT NULL,updated_at_us INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS pm_tasks_project_status
                    ON pm_tasks(project_id,status_id,position,due_date);
                CREATE INDEX IF NOT EXISTS pm_tasks_owner ON pm_tasks(owner_id,due_date);
                CREATE TABLE IF NOT EXISTS pm_task_dependencies(
                    task_id TEXT NOT NULL REFERENCES pm_tasks(task_id) ON DELETE CASCADE,
                    depends_on_task_id TEXT NOT NULL REFERENCES pm_tasks(task_id) ON DELETE CASCADE,
                    dependency_type TEXT NOT NULL DEFAULT 'finish_to_start',
                    PRIMARY KEY(task_id,depends_on_task_id),CHECK(task_id<>depends_on_task_id)
                );
                CREATE TABLE IF NOT EXISTS pm_checklist_items(
                    item_id TEXT PRIMARY KEY,task_id TEXT NOT NULL REFERENCES pm_tasks(task_id)
                        ON DELETE CASCADE,title TEXT NOT NULL,completed INTEGER NOT NULL DEFAULT 0,
                    owner_id TEXT NOT NULL DEFAULT '',display_order INTEGER NOT NULL DEFAULT 0,
                    created_at_us INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pm_comments(
                    comment_id TEXT PRIMARY KEY,task_id TEXT NOT NULL REFERENCES pm_tasks(task_id)
                        ON DELETE CASCADE,parent_comment_id TEXT REFERENCES pm_comments(comment_id)
                        ON DELETE CASCADE,author_id TEXT NOT NULL,body TEXT NOT NULL,
                    mentions_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(mentions_json)),
                    created_at_us INTEGER NOT NULL,edited_at_us INTEGER
                );
                CREATE TABLE IF NOT EXISTS pm_attachments(
                    attachment_id TEXT PRIMARY KEY,task_id TEXT NOT NULL REFERENCES pm_tasks(task_id)
                        ON DELETE CASCADE,name TEXT NOT NULL,kind TEXT NOT NULL,
                    location TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,
                    previous_attachment_id TEXT REFERENCES pm_attachments(attachment_id),
                    uploaded_by TEXT NOT NULL,created_at_us INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pm_time_entries(
                    entry_id TEXT PRIMARY KEY,task_id TEXT NOT NULL REFERENCES pm_tasks(task_id)
                        ON DELETE CASCADE,user_id TEXT NOT NULL,started_at_us INTEGER,
                    ended_at_us INTEGER,minutes INTEGER NOT NULL DEFAULT 0,note TEXT NOT NULL DEFAULT '',
                    created_at_us INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS pm_time_user ON pm_time_entries(user_id,created_at_us);
                CREATE TABLE IF NOT EXISTS hr_schedule_templates(
                    template_id TEXT PRIMARY KEY,name TEXT NOT NULL UNIQUE,description TEXT NOT NULL DEFAULT '',
                    cycle_weeks INTEGER NOT NULL DEFAULT 1 CHECK(cycle_weeks IN(1,2)),
                    weekly_hours_odd REAL NOT NULL DEFAULT 40,weekly_hours_even REAL NOT NULL DEFAULT 40,
                    active INTEGER NOT NULL DEFAULT 1,created_by TEXT NOT NULL,created_at_us INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS hr_schedule_periods(
                    period_id TEXT PRIMARY KEY,template_id TEXT NOT NULL REFERENCES hr_schedule_templates(template_id) ON DELETE CASCADE,
                    week_parity INTEGER NOT NULL DEFAULT 0 CHECK(week_parity IN(0,1,2)),weekday INTEGER NOT NULL CHECK(weekday BETWEEN 1 AND 7),
                    start_time TEXT NOT NULL,end_time TEXT NOT NULL,UNIQUE(template_id,week_parity,weekday,start_time,end_time)
                );
                CREATE TABLE IF NOT EXISTS hr_user_schedules(
                    assignment_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,template_id TEXT NOT NULL REFERENCES hr_schedule_templates(template_id),
                    effective_from TEXT NOT NULL,effective_until TEXT NOT NULL DEFAULT '',reference_week TEXT NOT NULL,
                    created_by TEXT NOT NULL,created_at_us INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS hr_user_schedules_user ON hr_user_schedules(user_id,effective_from,effective_until);
                CREATE TABLE IF NOT EXISTS hr_absences(
                    absence_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,start_at TEXT NOT NULL,end_at TEXT NOT NULL,
                    absence_type TEXT NOT NULL,privacy_level TEXT NOT NULL DEFAULT 'private',status TEXT NOT NULL DEFAULT 'approved',
                    note TEXT NOT NULL DEFAULT '',created_by TEXT NOT NULL,created_at_us INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS hr_absences_user_time ON hr_absences(user_id,start_at,end_at);
                CREATE TABLE IF NOT EXISTS hr_organisational_obligations(
                    obligation_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,start_at TEXT NOT NULL,end_at TEXT NOT NULL,
                    obligation_type TEXT NOT NULL,title TEXT NOT NULL,note TEXT NOT NULL DEFAULT '',
                    created_by TEXT NOT NULL,created_at_us INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS hr_obligations_user_time ON hr_organisational_obligations(user_id,start_at,end_at);
                CREATE TABLE IF NOT EXISTS hr_project_allocations(
                    allocation_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,project_id TEXT NOT NULL REFERENCES pm_projects(project_id) ON DELETE CASCADE,
                    start_date TEXT NOT NULL,end_date TEXT NOT NULL DEFAULT '',hours_per_week REAL NOT NULL DEFAULT 0,
                    allocation_percent REAL NOT NULL DEFAULT 0,role TEXT NOT NULL DEFAULT '',phase_id TEXT REFERENCES pm_phases(phase_id) ON DELETE SET NULL,
                    status TEXT NOT NULL DEFAULT 'active',created_by TEXT NOT NULL,created_at_us INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS hr_allocations_user_project ON hr_project_allocations(user_id,project_id,start_date,end_date);
                CREATE TABLE IF NOT EXISTS pm_holidays(
                    holiday_date TEXT PRIMARY KEY,name TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pm_capacity(
                    project_id TEXT NOT NULL REFERENCES pm_projects(project_id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL,weekly_hours REAL NOT NULL DEFAULT 40,
                    hourly_cost REAL NOT NULL DEFAULT 0,PRIMARY KEY(project_id,user_id)
                );
                CREATE TABLE IF NOT EXISTS pm_project_members(
                    project_id TEXT NOT NULL REFERENCES pm_projects(project_id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL,role TEXT NOT NULL,PRIMARY KEY(project_id,user_id)
                );
                CREATE TABLE IF NOT EXISTS pm_custom_fields(
                    field_id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES pm_projects(project_id)
                        ON DELETE CASCADE,name TEXT NOT NULL,field_type TEXT NOT NULL,
                    options_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(options_json)),
                    required INTEGER NOT NULL DEFAULT 0,display_order INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS pm_custom_values(
                    task_id TEXT NOT NULL REFERENCES pm_tasks(task_id) ON DELETE CASCADE,
                    field_id TEXT NOT NULL REFERENCES pm_custom_fields(field_id) ON DELETE CASCADE,
                    value_json TEXT NOT NULL CHECK(json_valid(value_json)),
                    PRIMARY KEY(task_id,field_id)
                );
                CREATE TABLE IF NOT EXISTS pm_templates(
                    template_id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',
                    definition_json TEXT NOT NULL CHECK(json_valid(definition_json)),
                    created_by TEXT NOT NULL,created_at_us INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pm_portals(
                    portal_id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES pm_projects(project_id)
                        ON DELETE CASCADE,name TEXT NOT NULL,token_hash TEXT NOT NULL UNIQUE,
                    show_tasks INTEGER NOT NULL DEFAULT 1,show_milestones INTEGER NOT NULL DEFAULT 1,
                    show_budget INTEGER NOT NULL DEFAULT 0,enabled INTEGER NOT NULL DEFAULT 1,
                    expires_at_us INTEGER
                );
                CREATE TABLE IF NOT EXISTS pm_notifications(
                    notification_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,project_id TEXT,
                    task_id TEXT,channel TEXT NOT NULL,event_type TEXT NOT NULL,
                    message TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'pending',
                    deliver_at_us INTEGER NOT NULL,created_at_us INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS pm_notifications_due
                    ON pm_notifications(state,deliver_at_us,user_id);
                CREATE TABLE IF NOT EXISTS pm_activity(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT NOT NULL,
                    task_id TEXT,actor_id TEXT NOT NULL,event_type TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(details_json)),
                    created_at_us INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS pm_activity_project
                    ON pm_activity(project_id,created_at_us DESC,event_id DESC);
                CREATE TABLE IF NOT EXISTS pm_research_areas(
                    area_id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES pm_projects(project_id)
                        ON DELETE CASCADE,name TEXT NOT NULL,geojson TEXT NOT NULL CHECK(json_valid(geojson)),
                    created_by TEXT NOT NULL,created_at_us INTEGER NOT NULL,updated_at_us INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS pm_research_areas_project
                    ON pm_research_areas(project_id,updated_at_us DESC);
                CREATE TABLE IF NOT EXISTS pm_project_media(
                    project_id TEXT NOT NULL REFERENCES pm_projects(project_id) ON DELETE CASCADE,
                    asset_public_id TEXT NOT NULL,media_type TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',included_default INTEGER NOT NULL DEFAULT 1,
                    added_by TEXT NOT NULL,added_at_us INTEGER NOT NULL,
                    PRIMARY KEY(project_id,asset_public_id)
                );
                CREATE TABLE IF NOT EXISTS pm_project_notes(
                    note_id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES pm_projects(project_id)
                        ON DELETE CASCADE,title TEXT NOT NULL,body TEXT NOT NULL,
                    author_id TEXT NOT NULL,created_at_us INTEGER NOT NULL,updated_at_us INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pm_task_notes(
                    note_id TEXT PRIMARY KEY,task_id TEXT NOT NULL REFERENCES pm_tasks(task_id)
                        ON DELETE CASCADE,body TEXT NOT NULL,author_id TEXT NOT NULL,
                    created_at_us INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS pm_task_notes_task
                    ON pm_task_notes(task_id,created_at_us,note_id);
                CREATE TABLE IF NOT EXISTS pm_project_map_snapshots(
                    snapshot_id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES pm_projects(project_id)
                        ON DELETE CASCADE,name TEXT NOT NULL,image_path TEXT NOT NULL,
                    viewport_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(viewport_json)),
                    created_by TEXT NOT NULL,created_at_us INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS pm_project_map_snapshots_project
                    ON pm_project_map_snapshots(project_id,created_at_us DESC);
                CREATE TABLE IF NOT EXISTS pm_survey_protocols(
                    protocol_id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES pm_projects(project_id)
                        ON DELETE CASCADE,name TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,
                    method TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',target_group TEXT NOT NULL DEFAULT '',
                    default_duration_minutes REAL NOT NULL DEFAULT 0,default_distance_m REAL NOT NULL DEFAULT 0,
                    equipment_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(equipment_json)),
                    required_fields_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(required_fields_json)),
                    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN(0,1)),created_by TEXT NOT NULL,
                    created_at_us INTEGER NOT NULL,updated_at_us INTEGER NOT NULL,
                    UNIQUE(project_id,name,version)
                );
                CREATE INDEX IF NOT EXISTS pm_survey_protocols_project
                    ON pm_survey_protocols(project_id,active DESC,name,version DESC);
                CREATE TABLE IF NOT EXISTS pm_survey_events(
                    survey_event_id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES pm_projects(project_id)
                        ON DELETE CASCADE,protocol_id TEXT REFERENCES pm_survey_protocols(protocol_id),
                    name TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'planned',start_text TEXT NOT NULL DEFAULT '',
                    end_text TEXT NOT NULL DEFAULT '',latitude REAL,longitude REAL,location_name TEXT NOT NULL DEFAULT '',
                    sampling_unit_type TEXT NOT NULL DEFAULT 'station',sampling_unit_name TEXT NOT NULL DEFAULT '',
                    route_geojson TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(route_geojson)),
                    effort_duration_minutes REAL NOT NULL DEFAULT 0,effort_distance_m REAL NOT NULL DEFAULT 0,
                    effort_area_m2 REAL NOT NULL DEFAULT 0,observer_team_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(observer_team_json)),
                    weather_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(weather_json)),habitat TEXT NOT NULL DEFAULT '',
                    equipment_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(equipment_json)),notes TEXT NOT NULL DEFAULT '',
                    created_by TEXT NOT NULL,created_at_us INTEGER NOT NULL,updated_at_us INTEGER NOT NULL,
                    CHECK(latitude IS NULL OR latitude BETWEEN -90 AND 90),
                    CHECK(longitude IS NULL OR longitude BETWEEN -180 AND 180)
                );
                CREATE INDEX IF NOT EXISTS pm_survey_events_project
                    ON pm_survey_events(project_id,start_text,status);
                CREATE TABLE IF NOT EXISTS pm_survey_detections(
                    detection_id TEXT PRIMARY KEY,survey_event_id TEXT NOT NULL REFERENCES pm_survey_events(survey_event_id)
                        ON DELETE CASCADE,taxon_name TEXT NOT NULL,detection_state TEXT NOT NULL,
                    count_value REAL,unit TEXT NOT NULL DEFAULT 'individuals',evidence_public_id TEXT,
                    notes TEXT NOT NULL DEFAULT '',recorded_by TEXT NOT NULL,created_at_us INTEGER NOT NULL,
                    CHECK(detection_state IN('detected','not_detected'))
                );
                CREATE INDEX IF NOT EXISTS pm_survey_detections_event
                    ON pm_survey_detections(survey_event_id,detection_state,taxon_name);
                CREATE TABLE IF NOT EXISTS pm_measurement_definitions(
                    definition_id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES pm_projects(project_id) ON DELETE CASCADE,
                    name TEXT NOT NULL,category TEXT NOT NULL,unit TEXT NOT NULL,value_type TEXT NOT NULL DEFAULT 'number',
                    minimum REAL,maximum REAL,active INTEGER NOT NULL DEFAULT 1,created_by TEXT NOT NULL,created_at_us INTEGER NOT NULL,
                    UNIQUE(project_id,name,unit));
                CREATE TABLE IF NOT EXISTS pm_samples(
                    sample_id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES pm_projects(project_id) ON DELETE CASCADE,
                    sample_code TEXT NOT NULL,specimen_code TEXT NOT NULL DEFAULT '',sample_type TEXT NOT NULL,
                    collected_at TEXT NOT NULL DEFAULT '',latitude REAL,longitude REAL,collector TEXT NOT NULL DEFAULT '',
                    container TEXT NOT NULL DEFAULT '',preservation TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'collected',
                    notes TEXT NOT NULL DEFAULT '',created_by TEXT NOT NULL,created_at_us INTEGER NOT NULL,updated_at_us INTEGER NOT NULL,
                    UNIQUE(project_id,sample_code));
                CREATE TABLE IF NOT EXISTS pm_measurements(
                    measurement_id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES pm_projects(project_id) ON DELETE CASCADE,
                    sample_id TEXT REFERENCES pm_samples(sample_id) ON DELETE CASCADE,definition_id TEXT REFERENCES pm_measurement_definitions(definition_id),
                    subject_type TEXT NOT NULL DEFAULT 'sample',subject_id TEXT NOT NULL DEFAULT '',name TEXT NOT NULL,category TEXT NOT NULL,
                    value_text TEXT NOT NULL,unit TEXT NOT NULL,measured_at TEXT NOT NULL DEFAULT '',instrument TEXT NOT NULL DEFAULT '',
                    calibration_reference TEXT NOT NULL DEFAULT '',uncertainty REAL,source TEXT NOT NULL DEFAULT 'manual',
                    recorded_by TEXT NOT NULL,created_at_us INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS pm_sample_custody(
                    custody_id TEXT PRIMARY KEY,sample_id TEXT NOT NULL REFERENCES pm_samples(sample_id) ON DELETE CASCADE,
                    action TEXT NOT NULL,from_party TEXT NOT NULL DEFAULT '',to_party TEXT NOT NULL DEFAULT '',occurred_at TEXT NOT NULL,
                    location TEXT NOT NULL DEFAULT '',condition TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',recorded_by TEXT NOT NULL,created_at_us INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS pm_laboratory_records(
                    laboratory_id TEXT PRIMARY KEY,sample_id TEXT NOT NULL REFERENCES pm_samples(sample_id) ON DELETE CASCADE,
                    record_type TEXT NOT NULL,external_reference TEXT NOT NULL DEFAULT '',laboratory TEXT NOT NULL DEFAULT '',
                    requested_test TEXT NOT NULL DEFAULT '',result TEXT NOT NULL DEFAULT '',unit TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'requested',recorded_at TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',
                    recorded_by TEXT NOT NULL,created_at_us INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS pm_quality_findings(
                    finding_id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES pm_projects(project_id) ON DELETE CASCADE,
                    rule_code TEXT NOT NULL,severity TEXT NOT NULL,entity_type TEXT NOT NULL,entity_id TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL,explanation TEXT NOT NULL,evidence_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(evidence_json)),
                    state TEXT NOT NULL DEFAULT 'open',dismissed_reason TEXT NOT NULL DEFAULT '',dismissed_by TEXT NOT NULL DEFAULT '',
                    created_at_us INTEGER NOT NULL,updated_at_us INTEGER NOT NULL,
                    UNIQUE(project_id,rule_code,entity_type,entity_id));
                CREATE INDEX IF NOT EXISTS pm_quality_findings_project ON pm_quality_findings(project_id,state,severity);
                CREATE TABLE IF NOT EXISTS pm_reference_values(
                    value_id TEXT PRIMARY KEY,domain TEXT NOT NULL,code TEXT NOT NULL,display_name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',display_order INTEGER NOT NULL DEFAULT 0,active INTEGER NOT NULL DEFAULT 1,
                    system_value INTEGER NOT NULL DEFAULT 0,created_by TEXT NOT NULL DEFAULT '',created_at_us INTEGER NOT NULL,updated_at_us INTEGER NOT NULL,
                    UNIQUE(domain,code));
                CREATE TABLE IF NOT EXISTS pm_specimens(
                    specimen_id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES pm_projects(project_id) ON DELETE CASCADE,
                    specimen_code TEXT NOT NULL,taxon_name TEXT NOT NULL DEFAULT '',sex_code TEXT NOT NULL DEFAULT 'unknown',
                    life_stage_code TEXT NOT NULL DEFAULT 'unknown',status_code TEXT NOT NULL DEFAULT 'active',identity_confidence TEXT NOT NULL DEFAULT 'confirmed',
                    notes TEXT NOT NULL DEFAULT '',created_by TEXT NOT NULL,created_at_us INTEGER NOT NULL,updated_at_us INTEGER NOT NULL,
                    UNIQUE(project_id,specimen_code));
                CREATE TABLE IF NOT EXISTS pm_specimen_identifiers(
                    identifier_id TEXT PRIMARY KEY,specimen_id TEXT NOT NULL REFERENCES pm_specimens(specimen_id) ON DELETE CASCADE,
                    identifier_type TEXT NOT NULL,identifier_value TEXT NOT NULL,authority TEXT NOT NULL DEFAULT '',status_code TEXT NOT NULL DEFAULT 'active',
                    applied_at TEXT NOT NULL DEFAULT '',retired_at TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',recorded_by TEXT NOT NULL,created_at_us INTEGER NOT NULL,
                    UNIQUE(identifier_type,identifier_value));
                CREATE TABLE IF NOT EXISTS pm_specimen_enrichments(
                    enrichment_id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES pm_projects(project_id) ON DELETE CASCADE,
                    specimen_id TEXT NOT NULL REFERENCES pm_specimens(specimen_id) ON DELETE CASCADE,survey_event_id TEXT REFERENCES pm_survey_events(survey_event_id),
                    enrichment_type TEXT NOT NULL,definition_id TEXT REFERENCES pm_measurement_definitions(definition_id),
                    occurred_at TEXT NOT NULL,status_code TEXT NOT NULL DEFAULT 'recorded',value_text TEXT NOT NULL DEFAULT '',unit TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(payload_json)),source TEXT NOT NULL DEFAULT 'manual',confidence TEXT NOT NULL DEFAULT 'confirmed',
                    supersedes_enrichment_id TEXT REFERENCES pm_specimen_enrichments(enrichment_id),recorded_by TEXT NOT NULL,created_at_us INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS pm_specimen_enrichments_subject ON pm_specimen_enrichments(specimen_id,occurred_at DESC);
                CREATE TABLE IF NOT EXISTS pm_laboratory_media(
                    media_id TEXT PRIMARY KEY,laboratory_id TEXT NOT NULL REFERENCES pm_laboratory_records(laboratory_id) ON DELETE CASCADE,
                    media_type TEXT NOT NULL,modality TEXT NOT NULL,file_path TEXT NOT NULL,file_name TEXT NOT NULL,checksum_sha256 TEXT NOT NULL,
                    captured_at TEXT NOT NULL DEFAULT '',description TEXT NOT NULL DEFAULT '',status_code TEXT NOT NULL DEFAULT 'active',
                    uploaded_by TEXT NOT NULL,created_at_us INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS pm_specimen_encounters(
                    encounter_id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES pm_projects(project_id) ON DELETE CASCADE,
                    specimen_id TEXT NOT NULL REFERENCES pm_specimens(specimen_id) ON DELETE CASCADE,
                    survey_event_id TEXT REFERENCES pm_survey_events(survey_event_id),encounter_type TEXT NOT NULL,
                    status_code TEXT NOT NULL DEFAULT 'recorded',occurred_at TEXT NOT NULL,location_name TEXT NOT NULL DEFAULT '',
                    latitude REAL,longitude REAL,capture_method TEXT NOT NULL DEFAULT '',release_status TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',recorded_by TEXT NOT NULL,created_at_us INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS pm_specimen_encounters_subject ON pm_specimen_encounters(specimen_id,occurred_at DESC);
                CREATE TABLE IF NOT EXISTS pm_dossier_context_links(
                    link_id TEXT PRIMARY KEY,dossier_id TEXT NOT NULL,project_id TEXT NOT NULL REFERENCES pm_projects(project_id) ON DELETE CASCADE,
                    context_type TEXT NOT NULL,context_id TEXT NOT NULL,relationship TEXT NOT NULL DEFAULT 'related',
                    linked_by TEXT NOT NULL,created_at_us INTEGER NOT NULL,UNIQUE(dossier_id,context_type,context_id));
                """
            )
            now = _now_us()
            defaults = {
                "specimen_status": (("active","Active"),("released","Released"),("deceased","Deceased"),("lost","Lost"),("archived","Archived")),
                "sample_type": (("blood","Blood"),("serum","Serum"),("plasma","Plasma"),("tissue","Tissue"),("skin_biopsy","Skin biopsy"),("feather","Feather"),("hair","Hair"),("swab","Swab"),("saliva","Saliva"),("urine","Urine"),("faeces","Faeces"),("dna","DNA"),("rna","RNA"),("bone","Bone"),("tooth","Tooth"),("egg","Egg"),("shell","Shell"),("blubber","Blubber"),("parasite","Parasite"),("water","Water"),("sediment","Sediment"),("edna","Environmental DNA"),("other","Other")),
                "sample_status": (("collected","Collected"),("in_transit","In transit"),("received","Received"),("processing","Processing"),("consumed","Consumed"),("returned","Returned"),("disposed","Disposed")),
                "survey_event_status": (("planned","Planned"),("active","Active"),("completed","Completed"),("cancelled","Cancelled")),
                "laboratory_status": (("requested","Requested"),("received","Received"),("in_progress","In progress"),("completed","Completed"),("rejected","Rejected"),("cancelled","Cancelled")),
                "custody_status": (("transferred","Transferred"),("received","Received"),("stored","Stored"),("released","Released")),
                "custody_action": (("collected","Collected"),("transferred","Transferred"),("received","Received"),("stored","Stored"),("released","Released"),("returned","Returned"),("disposed","Disposed")),
                "laboratory_record_type": (("diagnostic","Diagnostic examination"),("pathology","Pathology"),("histology","Histology"),("genetics","Genetics"),("toxicology","Toxicology"),("microbiology","Microbiology"),("imaging","Imaging"),("other","Other")),
                "party": (("field_team","Field team"),("laboratory","Laboratory"),("repository","Repository"),("external_partner","External partner")),
                "identifier_type": (("ring","Ring / band"),("tag","Tag"),("rfid","RFID / PIT"),("microchip","Microchip"),("photo_id","Photo ID"),("genetic_id","Genetic ID"),("field_code","Field code")),
                "media_type": (("image","Image"),("video","Video"),("audio","Audio"),("document","Document"),("dataset","Dataset"),("model_3d","3D model")),
                "modality": (("photograph","Photograph"),("x_ray","X-ray"),("ct","CT"),("mri","MRI"),("ultrasound","Ultrasound"),("microscopy","Microscopy"),("histology","Histology"),("bioacoustics","Bioacoustics"),("report","Report")),
                "enrichment_status": (("recorded","Recorded"),("reviewed","Reviewed"),("approved","Approved"),("rejected","Rejected"),("superseded","Superseded")),
                "encounter_type": (("capture","Capture"),("recapture","Recapture"),("resighting","Resighting"),("telemetry","Telemetry detection"),("camera","Camera detection"),("acoustic","Acoustic detection"),("recovery","Recovery"),("laboratory","Laboratory-only")),
                "encounter_status": (("recorded","Recorded"),("reviewed","Reviewed"),("confirmed","Confirmed"),("cancelled","Cancelled")),
                "protocol_method": (("point_count","Point count"),("transect","Transect"),("capture_station","Capture station"),("camera_trap","Camera trap"),("acoustic_monitoring","Acoustic monitoring"),("laboratory","Laboratory"),("other","Other")),
            }
            for domain, values in defaults.items():
                for order, (code, name) in enumerate(values):
                    connection.execute("INSERT OR IGNORE INTO pm_reference_values(value_id,domain,code,display_name,display_order,active,system_value,created_by,created_at_us,updated_at_us) VALUES(?,?,?,?,?,1,1,'system',?,?)", (_id(),domain,code,name,order,now,now))
            version = connection.execute("SELECT version FROM pm_schema WHERE id=1").fetchone()[0]
            if int(version) == 1:
                connection.execute("UPDATE pm_schema SET version=2 WHERE id=1")
                version = 2
            if int(version) == 2:
                connection.execute("UPDATE pm_schema SET version=3 WHERE id=1")
                version = 3
            if int(version) == 3:
                connection.execute("UPDATE pm_schema SET version=4 WHERE id=1")
                version = 4
            if int(version) == 4:
                connection.execute("UPDATE pm_schema SET version=5 WHERE id=1")
                version = 5
            if int(version) == 5:
                connection.execute("UPDATE pm_schema SET version=6 WHERE id=1")
                version = 6
            if int(version) != SCHEMA_VERSION:
                raise RuntimeError(
                    "The Project module schema is not compatible with this release. "
                    "Create a new Project database; legacy project migration is intentionally unsupported."
                )

    def save_research_area(
        self, project_id: str, name: str, coordinates: list[list[float]], *, actor_id: str
    ) -> str:
        self.require(project_id, actor_id, "edit")
        if len(coordinates) < 3:
            raise ValueError("research area requires at least three map points")
        ring = [[float(point[0]), float(point[1])] for point in coordinates]
        if any(not -180 <= p[0] <= 180 or not -90 <= p[1] <= 90 for p in ring):
            raise ValueError("research area coordinates are outside WGS84 bounds")
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        area_id = _id()
        now = _now_us()
        feature = {
            "type": "Feature",
            "id": area_id,
            "properties": {"name": name.strip() or "Research area", "project_id": project_id},
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        }
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO pm_research_areas VALUES(?,?,?,?,?,?,?)",
                (area_id, project_id, name.strip() or "Research area", json.dumps(feature), actor_id, now, now),
            )
            self._event(connection, project_id, actor_id, "research_area.created", details={"area_id": area_id})
        return area_id

    def import_research_area(self, project_id: str, source: Path, *, actor_id: str) -> str:
        payload = json.loads(source.read_text(encoding="utf-8"))
        feature = payload["features"][0] if payload.get("type") == "FeatureCollection" else payload
        if feature.get("type") != "Feature" or feature.get("geometry", {}).get("type") != "Polygon":
            raise ValueError("research-area GeoJSON must contain a Polygon feature")
        coordinates = feature["geometry"]["coordinates"][0]
        name = str(feature.get("properties", {}).get("name") or source.stem)
        return self.save_research_area(project_id, name, coordinates, actor_id=actor_id)

    def research_areas(self, project_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT area_id,name,geojson,created_by,created_at_us,updated_at_us FROM pm_research_areas WHERE project_id=? ORDER BY updated_at_us DESC",
                (project_id,),
            ).fetchall()
        return tuple({**dict(row), "feature": json.loads(str(row["geojson"]))} for row in rows)

    def delete_research_area(self, area_id: str, *, actor_id: str) -> None:
        with self._connect() as connection:
            row = connection.execute("SELECT project_id FROM pm_research_areas WHERE area_id=?", (area_id,)).fetchone()
            if row is None:
                raise KeyError(area_id)
            self.require(str(row[0]), actor_id, "edit")
            connection.execute("DELETE FROM pm_research_areas WHERE area_id=?", (area_id,))
            self._event(connection, str(row[0]), actor_id, "research_area.deleted", details={"area_id": area_id})

    def create_survey_protocol(
        self, project_id: str, *, name: str, method: str, actor_id: str,
        description: str = "", target_group: str = "", duration_minutes: float = 0,
        distance_m: float = 0, equipment: tuple[str, ...] = (),
        required_fields: tuple[str, ...] = (), version: int = 1,
    ) -> str:
        self.require(project_id, actor_id, "edit")
        if not name.strip() or not method.strip():
            raise ValueError("protocol name and method are required")
        if version < 1 or duration_minutes < 0 or distance_m < 0:
            raise ValueError("protocol version and effort defaults must be non-negative")
        protocol_id, now = _id(), _now_us()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO pm_survey_protocols VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (protocol_id, project_id, name.strip(), int(version), method.strip(), description.strip(),
                 target_group.strip(), float(duration_minutes), float(distance_m),
                 json.dumps([value for value in equipment if value.strip()]),
                 json.dumps([value for value in required_fields if value.strip()]), 1, actor_id, now, now),
            )
            self._event(connection, project_id, actor_id, "survey_protocol.created", details={"protocol_id": protocol_id, "version": version})
        return protocol_id

    def survey_protocols(self, project_id: str, *, active_only: bool = False) -> tuple[dict, ...]:
        where = " AND active=1" if active_only else ""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pm_survey_protocols WHERE project_id=?" + where + " ORDER BY active DESC,name,version DESC",
                (project_id,),
            ).fetchall()
        return tuple({**dict(row), "equipment": json.loads(row["equipment_json"]), "required_fields": json.loads(row["required_fields_json"])} for row in rows)

    def set_survey_protocol_active(self, protocol_id: str, active: bool, *, actor_id: str) -> None:
        now = _now_us()
        with self._connect() as connection:
            row = connection.execute("SELECT project_id FROM pm_survey_protocols WHERE protocol_id=?", (protocol_id,)).fetchone()
            if row is None:
                raise KeyError(protocol_id)
            self.require(str(row[0]), actor_id, "edit")
            connection.execute("UPDATE pm_survey_protocols SET active=?,updated_at_us=? WHERE protocol_id=?", (int(active), now, protocol_id))
            self._event(connection, str(row[0]), actor_id, "survey_protocol.activated" if active else "survey_protocol.deactivated", details={"protocol_id": protocol_id})

    def create_survey_event(
        self, project_id: str, *, name: str, actor_id: str, protocol_id: str | None = None,
        status: str = "planned", start_text: str = "", end_text: str = "",
        latitude: float | None = None, longitude: float | None = None, location_name: str = "",
        sampling_unit_type: str = "station", sampling_unit_name: str = "",
        duration_minutes: float = 0, distance_m: float = 0, area_m2: float = 0,
        observers: tuple[str, ...] = (), weather: dict | None = None, habitat: str = "",
        equipment: tuple[str, ...] = (), notes: str = "", route_geojson: dict | None = None,
    ) -> str:
        self.require(project_id, actor_id, "edit")
        if not name.strip() or status not in {"planned", "active", "completed", "cancelled"}:
            raise ValueError("event name and a valid status are required")
        if latitude is not None and not -90 <= latitude <= 90:
            raise ValueError("latitude must be between -90 and 90")
        if longitude is not None and not -180 <= longitude <= 180:
            raise ValueError("longitude must be between -180 and 180")
        if min(duration_minutes, distance_m, area_m2) < 0:
            raise ValueError("survey effort cannot be negative")
        event_id, now = _id(), _now_us()
        with self._connect() as connection:
            if protocol_id:
                protocol = connection.execute(
                    "SELECT project_id FROM pm_survey_protocols WHERE protocol_id=?", (protocol_id,)
                ).fetchone()
                if protocol is None:
                    raise ValueError("survey protocol does not exist")
                if str(protocol[0]) != project_id:
                    raise ValueError("survey protocol belongs to another project")
            connection.execute(
                """INSERT INTO pm_survey_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (event_id, project_id, protocol_id, name.strip(), status, start_text.strip(), end_text.strip(),
                 latitude, longitude, location_name.strip(), sampling_unit_type.strip() or "station",
                 sampling_unit_name.strip(), json.dumps(route_geojson or {}), float(duration_minutes),
                 float(distance_m), float(area_m2), json.dumps([x for x in observers if x.strip()]),
                 json.dumps(weather or {}), habitat.strip(), json.dumps([x for x in equipment if x.strip()]),
                 notes.strip(), actor_id, now, now),
            )
            self._event(connection, project_id, actor_id, "survey_event.created", details={"survey_event_id": event_id, "protocol_id": protocol_id})
        return event_id

    def survey_events(self, project_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT e.*,p.name AS protocol_name,p.version AS protocol_version,
                          (SELECT COUNT(*) FROM pm_survey_detections d WHERE d.survey_event_id=e.survey_event_id AND d.detection_state='detected') AS detected_count,
                          (SELECT COUNT(*) FROM pm_survey_detections d WHERE d.survey_event_id=e.survey_event_id AND d.detection_state='not_detected') AS non_detection_count
                   FROM pm_survey_events e LEFT JOIN pm_survey_protocols p ON p.protocol_id=e.protocol_id
                   WHERE e.project_id=? ORDER BY CASE WHEN e.start_text='' THEN 1 ELSE 0 END,e.start_text DESC,e.created_at_us DESC""",
                (project_id,),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def add_survey_detection(
        self, survey_event_id: str, *, taxon_name: str, detected: bool, actor_id: str,
        count: float | None = None, unit: str = "individuals", evidence_public_id: str | None = None,
        notes: str = "",
    ) -> str:
        if not taxon_name.strip() or count is not None and count < 0:
            raise ValueError("taxon name is required and count cannot be negative")
        detection_id, now = _id(), _now_us()
        with self._connect() as connection:
            row = connection.execute("SELECT project_id FROM pm_survey_events WHERE survey_event_id=?", (survey_event_id,)).fetchone()
            if row is None:
                raise KeyError(survey_event_id)
            project_id = str(row[0]); self.require(project_id, actor_id, "edit")
            connection.execute(
                "INSERT INTO pm_survey_detections VALUES(?,?,?,?,?,?,?,?,?,?)",
                (detection_id, survey_event_id, taxon_name.strip(), "detected" if detected else "not_detected",
                 count, unit.strip() or "individuals", evidence_public_id, notes.strip(), actor_id, now),
            )
            self._event(connection, project_id, actor_id, "survey_detection.created", details={"survey_event_id": survey_event_id, "detection_id": detection_id, "detected": detected})
        return detection_id

    def survey_detections(self, survey_event_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM pm_survey_detections WHERE survey_event_id=? ORDER BY detection_state,taxon_name", (survey_event_id,)).fetchall()
        return tuple(dict(row) for row in rows)

    def create_measurement_definition(self, project_id: str, *, name: str, category: str, unit: str,
                                      actor_id: str, minimum: float | None = None, maximum: float | None = None) -> str:
        self.require(project_id, actor_id, "edit")
        if not name.strip() or not unit.strip() or minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("measurement name/unit and a valid range are required")
        identity, now = _id(), _now_us()
        with self._connect() as connection:
            connection.execute("INSERT INTO pm_measurement_definitions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (identity, project_id, name.strip(), category.strip() or "general", unit.strip(), "number", minimum, maximum, 1, actor_id, now))
            self._event(connection, project_id, actor_id, "measurement_definition.created", details={"definition_id": identity})
        return identity

    def measurement_definitions(self, project_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            return tuple(dict(row) for row in connection.execute("SELECT * FROM pm_measurement_definitions WHERE project_id=? ORDER BY category,name", (project_id,)))

    def create_sample(self, project_id: str, *, sample_code: str, sample_type: str, actor_id: str,
                      specimen_code: str = "", collected_at: str = "", latitude: float | None = None,
                      longitude: float | None = None, collector: str = "", container: str = "",
                      preservation: str = "", notes: str = "") -> str:
        self.require(project_id, actor_id, "edit")
        if not sample_code.strip() or not sample_type.strip(): raise ValueError("sample identifier and type are required")
        if latitude is not None and not -90 <= latitude <= 90 or longitude is not None and not -180 <= longitude <= 180:
            raise ValueError("sample coordinates are outside WGS84 bounds")
        identity, now = _id(), _now_us()
        with self._connect() as connection:
            connection.execute("INSERT INTO pm_samples VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (identity, project_id, sample_code.strip(), specimen_code.strip(), sample_type.strip(), collected_at.strip(), latitude, longitude,
                 collector.strip(), container.strip(), preservation.strip(), "collected", notes.strip(), actor_id, now, now))
            self._event(connection, project_id, actor_id, "sample.created", details={"sample_id": identity, "sample_code": sample_code})
        return identity

    def samples(self, project_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            return tuple(dict(row) for row in connection.execute("SELECT * FROM pm_samples WHERE project_id=? ORDER BY created_at_us DESC", (project_id,)))

    def record_measurement(self, project_id: str, *, name: str, value: str, unit: str, actor_id: str,
                           sample_id: str | None = None, definition_id: str | None = None, category: str = "general",
                           measured_at: str = "", instrument: str = "", calibration_reference: str = "",
                           uncertainty: float | None = None, source: str = "manual") -> str:
        self.require(project_id, actor_id, "edit")
        if not name.strip() or not str(value).strip() or not unit.strip(): raise ValueError("measurement name, value and unit are required")
        identity, now = _id(), _now_us()
        with self._connect() as connection:
            if sample_id:
                sample = connection.execute("SELECT project_id FROM pm_samples WHERE sample_id=?", (sample_id,)).fetchone()
                if sample is None: raise KeyError(sample_id)
                if str(sample[0]) != project_id: raise ValueError("sample belongs to another project")
            definition = None
            if definition_id:
                definition = connection.execute("SELECT project_id,value_type FROM pm_measurement_definitions WHERE definition_id=?", (definition_id,)).fetchone()
                if definition is None: raise KeyError(definition_id)
                if str(definition[0]) != project_id: raise ValueError("measurement definition belongs to another project")
                if str(definition[1]) == "number":
                    try: number = float(str(value).strip())
                    except ValueError as exc: raise ValueError("measurement value must be numeric") from exc
                    if not math.isfinite(number): raise ValueError("measurement value must be finite")
            connection.execute("INSERT INTO pm_measurements VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (identity, project_id, sample_id, definition_id, "sample" if sample_id else "project", sample_id or project_id,
                 name.strip(), category.strip() or "general", str(value).strip(), unit.strip(), measured_at.strip(), instrument.strip(),
                 calibration_reference.strip(), uncertainty, source.strip() or "manual", actor_id, now))
            self._event(connection, project_id, actor_id, "measurement.recorded", details={"measurement_id": identity})
        return identity

    def measurements(self, project_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            return tuple(dict(row) for row in connection.execute("SELECT m.*,s.sample_code FROM pm_measurements m LEFT JOIN pm_samples s ON s.sample_id=m.sample_id WHERE m.project_id=? ORDER BY m.created_at_us DESC", (project_id,)))

    def sample_workflow_records(self, project_id: str) -> dict[str, list[dict]]:
        with self._connect() as connection:
            custody = [dict(row) for row in connection.execute("SELECT c.* FROM pm_sample_custody c JOIN pm_samples s ON s.sample_id=c.sample_id WHERE s.project_id=? ORDER BY c.created_at_us", (project_id,))]
            laboratory = [dict(row) for row in connection.execute("SELECT l.* FROM pm_laboratory_records l JOIN pm_samples s ON s.sample_id=l.sample_id WHERE s.project_id=? ORDER BY l.created_at_us", (project_id,))]
        return {"chain_of_custody": custody, "laboratory_records": laboratory}

    def add_custody_event(self, sample_id: str, *, action: str, occurred_at: str, actor_id: str,
                          from_party: str = "", to_party: str = "", location: str = "", condition: str = "", notes: str = "") -> str:
        if not action.strip() or not occurred_at.strip(): raise ValueError("custody action and timestamp are required")
        with self._connect() as connection:
            row = connection.execute("SELECT project_id FROM pm_samples WHERE sample_id=?", (sample_id,)).fetchone()
            if row is None: raise KeyError(sample_id)
            project_id = str(row[0]); self.require(project_id, actor_id, "edit"); identity, now = _id(), _now_us()
            connection.execute("INSERT INTO pm_sample_custody VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (identity, sample_id, action.strip(), from_party.strip(), to_party.strip(), occurred_at.strip(), location.strip(), condition.strip(), notes.strip(), actor_id, now))
            self._event(connection, project_id, actor_id, "sample.custody", details={"sample_id": sample_id, "custody_id": identity})
        return identity

    def add_laboratory_record(self, sample_id: str, *, record_type: str, actor_id: str, laboratory: str = "",
                              requested_test: str = "", result: str = "", unit: str = "", status: str = "requested",
                              external_reference: str = "", recorded_at: str = "", notes: str = "") -> str:
        if not record_type.strip() or not status.strip(): raise ValueError("laboratory record type and status are required")
        recorded_at = recorded_at.strip() or datetime.now(UTC).isoformat(timespec="minutes")
        with self._connect() as connection:
            row = connection.execute("SELECT project_id FROM pm_samples WHERE sample_id=?", (sample_id,)).fetchone()
            if row is None: raise KeyError(sample_id)
            project_id = str(row[0]); self.require(project_id, actor_id, "edit"); identity, now = _id(), _now_us()
            connection.execute("INSERT INTO pm_laboratory_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (identity, sample_id, record_type.strip(), external_reference.strip(), laboratory.strip(), requested_test.strip(), result.strip(), unit.strip(), status.strip(), recorded_at.strip(), notes.strip(), actor_id, now))
            self._event(connection, project_id, actor_id, "laboratory.recorded", details={"sample_id": sample_id, "laboratory_id": identity})
        return identity

    def reference_values(self, domain: str, *, active_only: bool = True) -> tuple[dict, ...]:
        where = " AND active=1" if active_only else ""
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM pm_reference_values WHERE domain=?" + where + " ORDER BY display_order,display_name", (domain,)).fetchall()
        return tuple(dict(row) for row in rows)

    def is_global_admin(self, actor_id: str) -> bool:
        if actor_id == "local-user" or os.environ.get("FIELDORA_PROFILE_ROLE") == "administrator": return True
        with self._connect() as connection:
            return connection.execute("SELECT 1 FROM pm_project_members WHERE user_id=? AND role='admin' LIMIT 1", (actor_id,)).fetchone() is not None

    def save_reference_value(self, domain: str, code: str, display_name: str, *, actor_id: str, active: bool = True) -> str:
        if not self.is_global_admin(actor_id): raise PermissionError("administrator permission is required to manage reference values")
        if not domain.strip() or not code.strip() or not display_name.strip(): raise ValueError("domain, code and display name are required")
        identity, now = _id(), _now_us()
        with self._connect() as connection:
            existing = connection.execute("SELECT value_id FROM pm_reference_values WHERE domain=? AND code=?", (domain.strip(),code.strip())).fetchone()
            if existing:
                identity = str(existing[0]); connection.execute("UPDATE pm_reference_values SET display_name=?,active=?,updated_at_us=? WHERE value_id=?", (display_name.strip(),int(active),now,identity))
            else:
                connection.execute("INSERT INTO pm_reference_values(value_id,domain,code,display_name,active,created_by,created_at_us,updated_at_us) VALUES(?,?,?,?,?,?,?,?)", (identity,domain.strip(),code.strip(),display_name.strip(),int(active),actor_id,now,now))
        return identity

    def create_specimen(self, project_id: str, *, specimen_code: str, actor_id: str, taxon_name: str = "", sex_code: str = "unknown", life_stage_code: str = "unknown", status_code: str = "active", notes: str = "") -> str:
        self.require(project_id, actor_id, "edit")
        if not specimen_code.strip(): raise ValueError("specimen identifier is required")
        identity, now = _id(), _now_us()
        with self._connect() as connection:
            connection.execute("INSERT INTO pm_specimens VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (identity,project_id,specimen_code.strip(),taxon_name.strip(),sex_code,life_stage_code,status_code,"confirmed",notes.strip(),actor_id,now,now))
            self._event(connection, project_id, actor_id, "specimen.created", details={"specimen_id":identity,"specimen_code":specimen_code})
        return identity

    def specimens(self, project_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows=connection.execute("SELECT * FROM pm_specimens WHERE project_id=? ORDER BY specimen_code",(project_id,)).fetchall()
        return tuple(dict(r) for r in rows)

    def add_specimen_identifier(self, specimen_id: str, *, identifier_type: str, identifier_value: str, actor_id: str, authority: str = "", applied_at: str = "", status_code: str = "active", notes: str = "") -> str:
        if not identifier_type or not identifier_value.strip(): raise ValueError("identifier type and value are required")
        with self._connect() as connection:
            row=connection.execute("SELECT project_id FROM pm_specimens WHERE specimen_id=?",(specimen_id,)).fetchone()
            if row is None: raise KeyError(specimen_id)
            project_id=str(row[0]); self.require(project_id,actor_id,"edit"); identity,now=_id(),_now_us()
            connection.execute("INSERT INTO pm_specimen_identifiers VALUES(?,?,?,?,?,?,?,?,?,?,?)",(identity,specimen_id,identifier_type,identifier_value.strip(),authority.strip(),status_code,applied_at.strip(),"",notes.strip(),actor_id,now))
            self._event(connection,project_id,actor_id,"specimen.identifier_added",details={"specimen_id":specimen_id,"identifier_id":identity})
        return identity

    def specimen_identifiers(self, project_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows=connection.execute("SELECT i.*,s.specimen_code FROM pm_specimen_identifiers i JOIN pm_specimens s ON s.specimen_id=i.specimen_id WHERE s.project_id=? ORDER BY i.created_at_us DESC",(project_id,)).fetchall()
        return tuple(dict(r) for r in rows)

    def record_specimen_enrichment(self, project_id: str, specimen_id: str, *, enrichment_type: str, occurred_at: str, actor_id: str, value_text: str = "", unit: str = "", definition_id: str | None = None, survey_event_id: str | None = None, status_code: str = "recorded", source: str = "manual", confidence: str = "confirmed", payload: dict | None = None, supersedes_enrichment_id: str | None = None) -> str:
        self.require(project_id,actor_id,"edit")
        if not enrichment_type.strip() or not occurred_at.strip(): raise ValueError("enrichment type and occurred date/time are required")
        identity,now=_id(),_now_us()
        with self._connect() as connection:
            row=connection.execute("SELECT project_id FROM pm_specimens WHERE specimen_id=?",(specimen_id,)).fetchone()
            if row is None or str(row[0])!=project_id: raise ValueError("specimen belongs to another project")
            if definition_id:
                d=connection.execute("SELECT project_id FROM pm_measurement_definitions WHERE definition_id=?",(definition_id,)).fetchone()
                if d is None or str(d[0])!=project_id: raise ValueError("definition belongs to another project")
            connection.execute("INSERT INTO pm_specimen_enrichments VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(identity,project_id,specimen_id,survey_event_id,enrichment_type.strip(),definition_id,occurred_at.strip(),status_code,value_text.strip(),unit.strip(),json.dumps(payload or {},sort_keys=True),source,confidence,supersedes_enrichment_id,actor_id,now))
            self._event(connection,project_id,actor_id,"enrichment.recorded",details={"enrichment_id":identity,"specimen_id":specimen_id,"type":enrichment_type})
        return identity

    def specimen_enrichments(self, project_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows=connection.execute("SELECT e.*,s.specimen_code,d.name AS definition_name FROM pm_specimen_enrichments e JOIN pm_specimens s ON s.specimen_id=e.specimen_id LEFT JOIN pm_measurement_definitions d ON d.definition_id=e.definition_id WHERE e.project_id=? ORDER BY e.occurred_at DESC,e.created_at_us DESC",(project_id,)).fetchall()
        return tuple({**dict(r),"payload":json.loads(r["payload_json"])} for r in rows)

    def create_specimen_encounter(self, project_id: str, specimen_id: str, *, encounter_type: str, occurred_at: str, actor_id: str, survey_event_id: str | None = None, status_code: str = "recorded", location_name: str = "", latitude: float | None = None, longitude: float | None = None, capture_method: str = "", release_status: str = "", notes: str = "") -> str:
        self.require(project_id, actor_id, "edit")
        if not encounter_type.strip() or not occurred_at.strip(): raise ValueError("encounter type and occurred date/time are required")
        identity, now = _id(), _now_us()
        with self._connect() as connection:
            specimen = connection.execute("SELECT project_id FROM pm_specimens WHERE specimen_id=?", (specimen_id,)).fetchone()
            if specimen is None or str(specimen[0]) != project_id: raise ValueError("specimen belongs to another project")
            if survey_event_id:
                event = connection.execute("SELECT project_id FROM pm_survey_events WHERE survey_event_id=?", (survey_event_id,)).fetchone()
                if event is None or str(event[0]) != project_id: raise ValueError("survey event belongs to another project")
            connection.execute("INSERT INTO pm_specimen_encounters VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (identity,project_id,specimen_id,survey_event_id,encounter_type.strip(),status_code,occurred_at.strip(),location_name.strip(),latitude,longitude,capture_method.strip(),release_status.strip(),notes.strip(),actor_id,now))
            self._event(connection,project_id,actor_id,"specimen.encounter_recorded",details={"encounter_id":identity,"specimen_id":specimen_id,"type":encounter_type})
        return identity

    def specimen_encounters(self, project_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows=connection.execute("SELECT e.*,s.specimen_code,v.name AS survey_event_name FROM pm_specimen_encounters e JOIN pm_specimens s ON s.specimen_id=e.specimen_id LEFT JOIN pm_survey_events v ON v.survey_event_id=e.survey_event_id WHERE e.project_id=? ORDER BY e.occurred_at DESC,e.created_at_us DESC",(project_id,)).fetchall()
        return tuple(dict(r) for r in rows)

    def specimen_timeline(self, specimen_id: str, *, actor_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            row=connection.execute("SELECT project_id FROM pm_specimens WHERE specimen_id=?",(specimen_id,)).fetchone()
            if row is None: raise KeyError(specimen_id)
            project_id=str(row[0]); self.require(project_id,actor_id,"view")
            items=[]
            for r in connection.execute("SELECT enrichment_id AS id,occurred_at AS happened,'enrichment' AS kind,enrichment_type AS title,value_text AS detail,recorded_by AS actor FROM pm_specimen_enrichments WHERE specimen_id=?",(specimen_id,)): items.append(dict(r))
            for r in connection.execute("SELECT encounter_id AS id,occurred_at AS happened,'encounter' AS kind,encounter_type AS title,location_name AS detail,recorded_by AS actor FROM pm_specimen_encounters WHERE specimen_id=?",(specimen_id,)): items.append(dict(r))
            for r in connection.execute("SELECT identifier_id AS id,COALESCE(NULLIF(applied_at,''),datetime(created_at_us/1000000,'unixepoch')) AS happened,'identifier' AS kind,identifier_type AS title,identifier_value AS detail,recorded_by AS actor FROM pm_specimen_identifiers WHERE specimen_id=?",(specimen_id,)): items.append(dict(r))
            for r in connection.execute("SELECT sample_id AS id,COALESCE(NULLIF(collected_at,''),datetime(created_at_us/1000000,'unixepoch')) AS happened,'sample' AS kind,sample_type AS title,sample_code AS detail,created_by AS actor FROM pm_samples WHERE specimen_code=(SELECT specimen_code FROM pm_specimens WHERE specimen_id=?) AND project_id=?",(specimen_id,project_id)): items.append(dict(r))
        return tuple(sorted(items,key=lambda x:(str(x.get('happened') or ''),str(x.get('id'))),reverse=True))

    def merge_specimens(self, canonical_specimen_id: str, duplicate_specimen_id: str, *, actor_id: str, reason: str) -> None:
        if canonical_specimen_id == duplicate_specimen_id: raise ValueError("select two different specimens")
        if not reason.strip(): raise ValueError("merge reason is required")
        with self._connect() as connection:
            rows=connection.execute("SELECT specimen_id,project_id,specimen_code FROM pm_specimens WHERE specimen_id IN (?,?)",(canonical_specimen_id,duplicate_specimen_id)).fetchall()
            if len(rows)!=2 or len({str(r['project_id']) for r in rows})!=1: raise ValueError("specimens must exist in the same project")
            project_id=str(rows[0]['project_id']); self.require(project_id,actor_id,"manage")
            duplicate_code=next(str(r['specimen_code']) for r in rows if str(r['specimen_id'])==duplicate_specimen_id)
            canonical_code=next(str(r['specimen_code']) for r in rows if str(r['specimen_id'])==canonical_specimen_id)
            connection.execute("UPDATE pm_specimen_identifiers SET specimen_id=? WHERE specimen_id=?",(canonical_specimen_id,duplicate_specimen_id))
            connection.execute("UPDATE pm_specimen_enrichments SET specimen_id=? WHERE specimen_id=?",(canonical_specimen_id,duplicate_specimen_id))
            connection.execute("UPDATE pm_specimen_encounters SET specimen_id=? WHERE specimen_id=?",(canonical_specimen_id,duplicate_specimen_id))
            connection.execute("UPDATE pm_samples SET specimen_code=? WHERE project_id=? AND specimen_code=?",(canonical_code,project_id,duplicate_code))
            connection.execute("DELETE FROM pm_specimens WHERE specimen_id=?",(duplicate_specimen_id,))
            self._event(connection,project_id,actor_id,"specimen.merged",details={"canonical_specimen_id":canonical_specimen_id,"duplicate_specimen_id":duplicate_specimen_id,"reason":reason.strip()})

    def link_dossier_context(self, dossier_id: str, project_id: str, context_type: str, context_id: str, *, actor_id: str, relationship: str = "related") -> str:
        self.require(project_id,actor_id,"edit")
        if context_type not in {"specimen","identifier","encounter","survey_event","protocol","definition","enrichment","sample","laboratory","laboratory_media"}: raise ValueError("unsupported dossier context type")
        identity,now=_id(),_now_us()
        with self._connect() as connection:
            existing=connection.execute("SELECT link_id FROM pm_dossier_context_links WHERE dossier_id=? AND context_type=? AND context_id=?",(dossier_id,context_type,context_id)).fetchone()
            if existing:return str(existing[0])
            connection.execute("INSERT INTO pm_dossier_context_links VALUES(?,?,?,?,?,?,?,?)",(identity,dossier_id,project_id,context_type,context_id,relationship,actor_id,now))
            self._event(connection,project_id,actor_id,"dossier.context_linked",details={"dossier_id":dossier_id,"context_type":context_type,"context_id":context_id})
        return identity

    def dossier_context(self, dossier_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows=connection.execute("SELECT * FROM pm_dossier_context_links WHERE dossier_id=? ORDER BY created_at_us DESC",(dossier_id,)).fetchall()
        return tuple(dict(r) for r in rows)

    def update_sample_status(self, sample_id: str, status_code: str, *, actor_id: str) -> None:
        with self._connect() as connection:
            row=connection.execute("SELECT project_id,status FROM pm_samples WHERE sample_id=?",(sample_id,)).fetchone()
            if row is None: raise KeyError(sample_id)
            project_id=str(row[0]); self.require(project_id,actor_id,"edit"); connection.execute("UPDATE pm_samples SET status=?,updated_at_us=? WHERE sample_id=?",(status_code,_now_us(),sample_id)); self._event(connection,project_id,actor_id,"sample.status_changed",details={"sample_id":sample_id,"old":row[1],"new":status_code})

    def update_survey_event_status(self, survey_event_id: str, status_code: str, *, actor_id: str) -> None:
        with self._connect() as connection:
            row=connection.execute("SELECT project_id,status FROM pm_survey_events WHERE survey_event_id=?",(survey_event_id,)).fetchone()
            if row is None: raise KeyError(survey_event_id)
            project_id=str(row[0]); self.require(project_id,actor_id,"edit"); connection.execute("UPDATE pm_survey_events SET status=?,updated_at_us=? WHERE survey_event_id=?",(status_code,_now_us(),survey_event_id)); self._event(connection,project_id,actor_id,"survey_event.status_changed",details={"survey_event_id":survey_event_id,"old":row[1],"new":status_code})

    def update_laboratory_status(self, laboratory_id: str, status_code: str, *, actor_id: str) -> None:
        with self._connect() as connection:
            row=connection.execute("SELECT s.project_id,l.status FROM pm_laboratory_records l JOIN pm_samples s ON s.sample_id=l.sample_id WHERE l.laboratory_id=?",(laboratory_id,)).fetchone()
            if row is None: raise KeyError(laboratory_id)
            project_id=str(row[0]); self.require(project_id,actor_id,"edit"); connection.execute("UPDATE pm_laboratory_records SET status=? WHERE laboratory_id=?",(status_code,laboratory_id)); self._event(connection,project_id,actor_id,"laboratory.status_changed",details={"laboratory_id":laboratory_id,"old":row[1],"new":status_code})

    def add_laboratory_media(self, laboratory_id: str, file_path: Path, *, media_type: str, modality: str, actor_id: str, captured_at: str = "", description: str = "") -> str:
        import hashlib
        source=Path(file_path)
        if not source.is_file(): raise ValueError("media file does not exist")
        with self._connect() as connection:
            row=connection.execute("SELECT s.project_id FROM pm_laboratory_records l JOIN pm_samples s ON s.sample_id=l.sample_id WHERE l.laboratory_id=?",(laboratory_id,)).fetchone()
            if row is None: raise KeyError(laboratory_id)
            project_id=str(row[0]); self.require(project_id,actor_id,"edit"); identity,now=_id(),_now_us(); digest=hashlib.sha256(source.read_bytes()).hexdigest()
            connection.execute("INSERT INTO pm_laboratory_media VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(identity,laboratory_id,media_type,modality,str(source),source.name,digest,captured_at.strip(),description.strip(),"active",actor_id,now))
            self._event(connection,project_id,actor_id,"laboratory.media_added",details={"laboratory_id":laboratory_id,"media_id":identity,"checksum":digest})
        return identity

    def laboratory_media(self, project_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows=connection.execute("SELECT m.*,l.record_type,s.sample_code FROM pm_laboratory_media m JOIN pm_laboratory_records l ON l.laboratory_id=m.laboratory_id JOIN pm_samples s ON s.sample_id=l.sample_id WHERE s.project_id=? ORDER BY m.created_at_us DESC",(project_id,)).fetchall()
        return tuple(dict(r) for r in rows)

    def import_instrument_csv(self, project_id: str, source: Path, *, actor_id: str) -> int:
        """Validate and import one instrument file atomically."""
        self.require(project_id, actor_id, "edit")
        with Path(source).open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            required = {"name", "value", "unit"}
            missing = required.difference(reader.fieldnames or ())
            if missing:
                raise ValueError("missing required CSV column(s): " + ", ".join(sorted(missing)))
            parsed = []
            for line_number, row in enumerate(reader, 2):
                name, value, unit = (str(row.get(key, "")).strip() for key in ("name", "value", "unit"))
                if not name or not value or not unit:
                    raise ValueError(f"row {line_number}: name, value and unit are required")
                uncertainty = None
                if str(row.get("uncertainty", "")).strip():
                    try: uncertainty = float(str(row["uncertainty"]).strip())
                    except ValueError as exc: raise ValueError(f"row {line_number}: uncertainty must be numeric") from exc
                    if not math.isfinite(uncertainty) or uncertainty < 0:
                        raise ValueError(f"row {line_number}: uncertainty must be a finite non-negative number")
                parsed.append((name, value, unit, str(row.get("category", "instrument")).strip() or "instrument",
                               str(row.get("measured_at", "")).strip(), str(row.get("instrument", "")).strip(),
                               str(row.get("calibration_reference", "")).strip(), uncertainty))
        now = _now_us()
        with self._connect() as connection:
            for name, value, unit, category, measured_at, instrument, calibration, uncertainty in parsed:
                identity = _id()
                connection.execute("INSERT INTO pm_measurements VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (identity, project_id, None, None, "project", project_id, name, category, value, unit,
                     measured_at, instrument, calibration, uncertainty, "csv-instrument", actor_id, now))
            self._event(connection, project_id, actor_id, "measurement.csv_imported", details={"rows": len(parsed), "source": Path(source).name})
        return len(parsed)

    def run_quality_checks(self, project_id: str, *, actor_id: str) -> int:
        self.require(project_id, actor_id, "view"); now = _now_us(); findings = []
        for sample in self.samples(project_id):
            if not sample["collected_at"]: findings.append(("missing_date", "sample", sample["sample_id"], {"sample_code": sample["sample_code"]}))
            if sample["latitude"] is None or sample["longitude"] is None: findings.append(("missing_coordinates", "sample", sample["sample_id"], {"sample_code": sample["sample_code"]}))
        definitions = {row["definition_id"]: row for row in self.measurement_definitions(project_id)}
        for value in self.measurements(project_id):
            definition = definitions.get(value["definition_id"])
            if definition:
                try: number = float(value["value_text"])
                except ValueError: number = None
                if number is not None and (definition["minimum"] is not None and number < definition["minimum"] or definition["maximum"] is not None and number > definition["maximum"]):
                    findings.append(("anomalous_measurement", "measurement", value["measurement_id"], {"value": number, "unit": value["unit"], "minimum": definition["minimum"], "maximum": definition["maximum"]}))
        for event in self.survey_events(project_id):
            if not event["protocol_id"] or not event["start_text"] or not event["location_name"] or event["effort_duration_minutes"] <= 0:
                findings.append(("incomplete_sampling_protocol", "survey_event", event["survey_event_id"], {"event": event["name"]}))
        with self._connect() as connection:
            active_keys = {(code, entity_type, entity_id) for code, entity_type, entity_id, _ in findings}
            for code, entity_type, entity_id, evidence in findings:
                explanation = f'{QUALITY_RULES[code]}. Review the recorded {entity_type} fields and supporting evidence.'
                connection.execute("INSERT INTO pm_quality_findings VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(project_id,rule_code,entity_type,entity_id) DO UPDATE SET evidence_json=excluded.evidence_json,explanation=excluded.explanation,state=CASE WHEN pm_quality_findings.state='dismissed' THEN 'dismissed' ELSE 'open' END,updated_at_us=excluded.updated_at_us",
                    (_id(), project_id, code, "warning", entity_type, entity_id, QUALITY_RULES[code], explanation, json.dumps(evidence), "open", "", "", now, now))
            open_rows = connection.execute("SELECT finding_id,rule_code,entity_type,entity_id FROM pm_quality_findings WHERE project_id=? AND state='open'", (project_id,)).fetchall()
            for row in open_rows:
                if (str(row[1]), str(row[2]), str(row[3])) not in active_keys:
                    connection.execute("UPDATE pm_quality_findings SET state='resolved',updated_at_us=? WHERE finding_id=?", (now, str(row[0])))
            self._event(connection, project_id, actor_id, "quality.checked", details={"findings": len(findings), "active_keys": len(active_keys)})
        return len(findings)

    def quality_findings(self, project_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            return tuple({**dict(row), "evidence": json.loads(row["evidence_json"])} for row in connection.execute("SELECT * FROM pm_quality_findings WHERE project_id=? ORDER BY state,severity,updated_at_us DESC", (project_id,)))

    def dismiss_quality_finding(self, finding_id: str, *, reason: str, actor_id: str) -> None:
        if not reason.strip(): raise ValueError("a dismissal reason is required")
        with self._connect() as connection:
            row = connection.execute("SELECT project_id FROM pm_quality_findings WHERE finding_id=?", (finding_id,)).fetchone()
            if row is None: raise KeyError(finding_id)
            project_id = str(row[0]); self.require(project_id, actor_id, "edit"); now = _now_us()
            connection.execute("UPDATE pm_quality_findings SET state='dismissed',dismissed_reason=?,dismissed_by=?,updated_at_us=? WHERE finding_id=?", (reason.strip(), actor_id, now, finding_id))
            self._event(connection, project_id, actor_id, "quality.dismissed", details={"finding_id": finding_id, "reason": reason.strip()})

    def add_map_snapshot(
        self, project_id: str, name: str, image_path: Path, *, actor_id: str,
        viewport: dict[str, float] | None = None,
    ) -> str:
        self.require(project_id, actor_id, "edit")
        source = Path(image_path)
        if not source.is_file():
            raise ValueError("map snapshot image does not exist")
        snapshot_id, now = _id(), _now_us()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO pm_project_map_snapshots VALUES(?,?,?,?,?,?,?)",
                (snapshot_id, project_id, name.strip() or "Map snapshot", str(source),
                 json.dumps(viewport or {}), actor_id, now),
            )
            self._event(connection, project_id, actor_id, "map_snapshot.created", details={"snapshot_id": snapshot_id})
        return snapshot_id

    def map_snapshots(self, project_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pm_project_map_snapshots WHERE project_id=? ORDER BY created_at_us DESC",
                (project_id,),
            ).fetchall()
        return tuple({**dict(row), "viewport": json.loads(str(row["viewport_json"]))} for row in rows)

    def attach_project_media(
        self, project_id: str, assets: tuple[tuple[str, str], ...], *, actor_id: str
    ) -> int:
        self.require(project_id, actor_id, "edit")
        now = _now_us()
        with self._connect() as connection:
            for asset_id, media_type in assets:
                connection.execute(
                    "INSERT OR IGNORE INTO pm_project_media VALUES(?,?,?,'',1,?,?)",
                    (project_id, asset_id, media_type, actor_id, now),
                )
            self._event(connection, project_id, actor_id, "project.media_attached", details={"count": len(assets)})
        return len(assets)

    def project_media(self, project_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pm_project_media WHERE project_id=? ORDER BY media_type,asset_public_id",
                (project_id,),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def add_project_note(self, project_id: str, title: str, body: str, *, actor_id: str) -> str:
        self.require(project_id, actor_id, "edit")
        note_id, now = _id(), _now_us()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO pm_project_notes VALUES(?,?,?,?,?,?,?)",
                (note_id, project_id, title.strip() or "Project note", body, actor_id, now, now),
            )
        return note_id

    def project_notes(self, project_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pm_project_notes WHERE project_id=? ORDER BY updated_at_us DESC",
                (project_id,),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def _event(
        self,
        connection: sqlite3.Connection,
        project_id: str,
        actor: str,
        event_type: str,
        *,
        task_id: str | None = None,
        details: dict | None = None,
    ) -> None:
        now = _now_us()
        connection.execute(
            "INSERT INTO pm_activity(project_id,task_id,actor_id,event_type,details_json,created_at_us)"
            " VALUES(?,?,?,?,?,?)",
            (project_id, task_id, actor, event_type, json.dumps(details or {}), now),
        )

    def _notify(
        self,
        connection: sqlite3.Connection,
        user_id: str,
        project_id: str,
        task_id: str | None,
        event_type: str,
        message: str,
        *,
        deliver_at_us: int | None = None,
    ) -> None:
        if not user_id:
            return
        now = _now_us()
        connection.execute(
            "INSERT INTO pm_notifications VALUES(?,?,?,?,'in_app',?,?,?,?,?)",
            (_id(), user_id, project_id, task_id, event_type, message, "pending",
             deliver_at_us or now, now),
        )

    def projects(self) -> tuple[ProjectSummary, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT project_id,name,status,owner_id,start_date,due_date,budget,currency "
                "FROM pm_projects ORDER BY updated_at_us DESC"
            ).fetchall()
        return tuple(ProjectSummary(*tuple(row)) for row in rows)

    def create_project(
        self,
        name: str,
        *,
        owner_id: str,
        actor_id: str,
        start_date: str = "",
        due_date: str = "",
        description: str = "",
        budget: float = 0,
        currency: str = "EUR",
        template_id: str | None = None,
    ) -> str:
        if not name.strip():
            raise ValueError("project name is required")
        _validate_date(start_date, "project start date")
        _validate_date(due_date, "project due date")
        if start_date and due_date and due_date < start_date:
            raise ValueError("project due date cannot be before its start date")
        project_id = _id()
        now = _now_us()
        statuses = (
            ("To Do", "todo", "#6b7280"),
            ("In Progress", "active", "#2563eb"),
            ("QA", "review", "#7c3aed"),
            ("Blocked", "blocked", "#dc2626"),
            ("Done", "done", "#16a34a"),
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO pm_projects VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (project_id, name.strip(), description.strip(), "active", owner_id.strip(),
                 start_date, due_date, float(budget), currency.strip() or "EUR", template_id,
                 "", now, now),
            )
            for order, (status_name, category, color) in enumerate(statuses):
                connection.execute(
                    "INSERT INTO pm_statuses VALUES(?,?,?,?,?,?,NULL)",
                    (_id(), project_id, status_name, category, color, order),
                )
            connection.execute(
                "INSERT INTO pm_project_members VALUES(?,?,?)",
                (project_id, owner_id or actor_id, "admin"),
            )
            self._event(connection, project_id, actor_id, "project.created", details={"name": name})
        if template_id:
            self.apply_template(project_id, template_id, actor_id=actor_id)
        return project_id

    def delete_project(self, project_id: str, *, actor_id: str) -> None:
        self.require(project_id, actor_id, "delete")
        with self._connect() as connection:
            connection.execute("DELETE FROM pm_projects WHERE project_id=?", (project_id,))

    def statuses(self, project_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pm_statuses WHERE project_id=? ORDER BY display_order,status_id",
                (project_id,),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def add_status(
        self,
        project_id: str,
        name: str,
        category: str,
        color: str,
        *,
        actor_id: str,
        wip_limit: int | None = None,
    ) -> str:
        self.require(project_id, actor_id, "manage")
        status_id = _id()
        with self._connect() as connection:
            order = connection.execute(
                "SELECT COALESCE(MAX(display_order),-1)+1 FROM pm_statuses WHERE project_id=?",
                (project_id,),
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO pm_statuses VALUES(?,?,?,?,?,?,?)",
                (status_id, project_id, name.strip(), category.strip(), color, order, wip_limit),
            )
            self._event(connection, project_id, actor_id, "status.created", details={"name": name})
        return status_id

    def phases(self, project_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pm_phases WHERE project_id=? ORDER BY display_order,name",
                (project_id,),
            ).fetchall()
        rollups = {row["phase_id"]: row for row in self.phase_rollups(project_id)}
        return tuple({**dict(row), **rollups.get(str(row["phase_id"]), {})} for row in rows)

    def create_phase(self, project_id: str, name: str, *, actor_id: str,
                     description: str = "", planned_budget: float = 0,
                     realized_budget: float = 0) -> str:
        self.require(project_id, actor_id, "edit")
        if not name.strip():
            raise ValueError("phase name is required")
        with self._connect() as connection:
            phase_id = _id(); now = _now_us()
            order = int(connection.execute(
                "SELECT COALESCE(MAX(display_order),-1)+1 FROM pm_phases WHERE project_id=?",
                (project_id,),
            ).fetchone()[0])
            connection.execute(
                "INSERT INTO pm_phases VALUES(?,?,?,?,?,?,?,?,?,?)",
                (phase_id, project_id, name.strip(), description.strip(), float(planned_budget),
                 float(realized_budget), order, actor_id, now, now),
            )
            self._event(connection, project_id, actor_id, "phase.created", details={"phase_id": phase_id, "name": name})
        return phase_id

    def update_phase(self, phase_id: str, *, actor_id: str, **changes: object) -> None:
        allowed = {"name", "description", "planned_budget", "realized_budget", "display_order"}
        values = {key: value for key, value in changes.items() if key in allowed}
        if not values:
            return
        with self._connect() as connection:
            row = connection.execute("SELECT project_id FROM pm_phases WHERE phase_id=?", (phase_id,)).fetchone()
            if row is None:
                raise KeyError(phase_id)
            project_id = str(row[0]); self.require(project_id, actor_id, "edit", connection=connection)
            assignments = ",".join(f"{key}=?" for key in values)
            connection.execute(f"UPDATE pm_phases SET {assignments},updated_at_us=? WHERE phase_id=?", (*values.values(), _now_us(), phase_id))
            self._event(connection, project_id, actor_id, "phase.updated", details={"phase_id": phase_id, **values})

    def assign_task_phase(self, task_id: str, phase_id: str | None, *, actor_id: str) -> None:
        with self._connect() as connection:
            row = connection.execute("SELECT project_id FROM pm_tasks WHERE task_id=?", (task_id,)).fetchone()
            if row is None:
                raise KeyError(task_id)
            project_id = str(row[0]); self.require(project_id, actor_id, "edit", connection=connection)
            if phase_id is not None:
                phase = connection.execute("SELECT project_id FROM pm_phases WHERE phase_id=?", (phase_id,)).fetchone()
                if phase is None or str(phase[0]) != project_id:
                    raise ValueError("phase does not belong to this project")
            queue = [task_id]; ids: list[str] = []
            while queue:
                current = queue.pop(0); ids.append(current)
                queue.extend(str(r[0]) for r in connection.execute("SELECT task_id FROM pm_tasks WHERE parent_task_id=?", (current,)))
            connection.executemany("UPDATE pm_tasks SET phase_id=?,updated_at_us=? WHERE task_id=?", ((phase_id, _now_us(), value) for value in ids))
            self._event(connection, project_id, actor_id, "task.phase_changed", task_id=task_id, details={"phase_id": phase_id})

    def sprints(self, project_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM pm_sprints WHERE project_id=? ORDER BY start_date,name", (project_id,)).fetchall()
        return tuple(dict(row) for row in rows)

    def create_sprint(self, project_id: str, name: str, *, actor_id: str, start_date: str = "",
                      end_date: str = "", status: str = "planned", goal: str = "") -> str:
        self.require(project_id, actor_id, "edit")
        _validate_date(start_date, "sprint start date"); _validate_date(end_date, "sprint end date")
        if start_date and end_date and end_date < start_date:
            raise ValueError("sprint end date cannot be before its start date")
        with self._connect() as connection:
            sprint_id = _id(); now = _now_us()
            connection.execute("INSERT INTO pm_sprints VALUES(?,?,?,?,?,?,?,?,?,?)",
                               (sprint_id, project_id, name.strip(), start_date, end_date, status, goal.strip(), actor_id, now, now))
            self._event(connection, project_id, actor_id, "sprint.created", details={"sprint_id": sprint_id, "name": name})
        return sprint_id

    def phase_rollups(self, project_id: str) -> tuple[dict, ...]:
        tasks = self.tasks(project_id)
        result: list[dict] = []
        for phase in self._raw_phases(project_id):
            direct = [task for task in tasks if task.phase_id == phase["phase_id"] and task.parent_task_id is None]
            calculated = sum(task.effective_estimate_hours for task in direct)
            realized = sum(task.realized_hours for task in direct)
            result.append({"phase_id": str(phase["phase_id"]), "calculated_estimate_hours": calculated,
                           "effective_estimate_hours": calculated, "calculated_realized_hours": realized,
                           "budget_variance": float(phase["planned_budget"]) - float(phase["realized_budget"])})
        return tuple(result)

    def _raw_phases(self, project_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM pm_phases WHERE project_id=? ORDER BY display_order,name", (project_id,)).fetchall()
        return tuple(dict(row) for row in rows)

    def tasks(self, project_id: str) -> tuple[TaskSummary, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT t.task_id,t.project_id,t.parent_task_id,t.title,t.status_id,s.name,
                       s.category,t.owner_id,t.priority,t.start_date,t.due_date,t.estimate_hours,
                       COALESCE((SELECT SUM(minutes)/60.0 FROM pm_time_entries e
                                 WHERE e.task_id=t.task_id),0),t.progress,
                       EXISTS(SELECT 1 FROM pm_task_dependencies d
                              JOIN pm_tasks p ON p.task_id=d.depends_on_task_id
                              JOIN pm_statuses ps ON ps.status_id=p.status_id
                              WHERE d.task_id=t.task_id AND ps.category!='done'),
                       t.milestone,t.phase_id,COALESCE(ph.name,''),t.sprint_id,
                       COALESCE(sp.name,t.sprint,''),t.realized_hours
                FROM pm_tasks t JOIN pm_statuses s ON s.status_id=t.status_id
                LEFT JOIN pm_phases ph ON ph.phase_id=t.phase_id
                LEFT JOIN pm_sprints sp ON sp.sprint_id=t.sprint_id
                WHERE t.project_id=?
                ORDER BY COALESCE(ph.display_order,999999),s.display_order,t.position,t.due_date,t.task_id
                """,
                (project_id,),
            ).fetchall()
        raw = [
            TaskSummary(
                task_id=str(r[0]), project_id=str(r[1]),
                parent_task_id=None if r[2] is None else str(r[2]), title=str(r[3]),
                status_id=str(r[4]), status_name=str(r[5]), status_category=str(r[6]),
                owner_id=str(r[7]), priority=str(r[8]), start_date=str(r[9]), due_date=str(r[10]),
                estimate_hours=float(r[11]), actual_hours=float(r[12]), progress=int(r[13]),
                blocked=bool(r[14]), milestone=bool(r[15]),
                phase_id=None if r[16] is None else str(r[16]), phase_name=str(r[17]),
                sprint_id=None if r[18] is None else str(r[18]), sprint_name=str(r[19]),
                manual_estimate_hours=float(r[11]), realized_hours=float(r[20]),
            )
            for r in rows
        ]
        by_parent: dict[str, list[TaskSummary]] = {}
        for task in raw:
            if task.parent_task_id:
                by_parent.setdefault(task.parent_task_id, []).append(task)
        cache: dict[str, tuple[float, float]] = {}
        visiting: set[str] = set()

        def rollup(task: TaskSummary) -> tuple[float, float]:
            if task.task_id in cache:
                return cache[task.task_id]
            if task.task_id in visiting:
                return task.manual_estimate_hours, task.realized_hours
            visiting.add(task.task_id)
            children = by_parent.get(task.task_id, ())
            if children:
                calculated = sum(rollup(child)[0] for child in children)
                realized = sum(rollup(child)[1] for child in children)
                effective = calculated
            else:
                calculated = 0.0
                effective = task.manual_estimate_hours
                realized = task.realized_hours or task.actual_hours
            visiting.discard(task.task_id)
            cache[task.task_id] = (effective, realized)
            return cache[task.task_id]

        enriched: list[TaskSummary] = []
        for task in raw:
            effective, realized = rollup(task)
            calculated = sum(rollup(child)[0] for child in by_parent.get(task.task_id, ()))
            enriched.append(replace(
                task, estimate_hours=effective, calculated_estimate_hours=calculated,
                effective_estimate_hours=effective, realized_hours=realized,
            ))
        return self._hierarchical_tasks(enriched)

    @staticmethod
    def _hierarchical_tasks(tasks: list[TaskSummary]) -> tuple[TaskSummary, ...]:
        """Return tasks parent-first, with every subtask directly after its parent.

        The database query defines the stable sibling order. Orphaned tasks are
        retained as top-level entries so data is never hidden. Cycles are also
        handled defensively by appending any unvisited tasks once.
        """
        by_id = {task.task_id: task for task in tasks}
        children: dict[str, list[TaskSummary]] = {}
        roots: list[TaskSummary] = []
        for task in tasks:
            parent_id = task.parent_task_id
            if parent_id and parent_id in by_id and parent_id != task.task_id:
                children.setdefault(parent_id, []).append(task)
            else:
                roots.append(task)

        ordered: list[TaskSummary] = []
        visited: set[str] = set()

        def append_branch(task: TaskSummary) -> None:
            if task.task_id in visited:
                return
            visited.add(task.task_id)
            ordered.append(task)
            for child in children.get(task.task_id, ()):
                append_branch(child)

        for root in roots:
            append_branch(root)
        for task in tasks:
            append_branch(task)
        return tuple(ordered)

    def create_task(
        self,
        project_id: str,
        title: str,
        *,
        actor_id: str,
        owner_id: str = "",
        status_id: str | None = None,
        parent_task_id: str | None = None,
        priority: str = "normal",
        start_date: str = "",
        due_date: str = "",
        estimate_hours: float = 0,
        budget: float = 0,
        recurrence: str = "none",
        recurrence_end: str = "",
        milestone: bool = False,
        sprint: str = "",
        phase_id: str | None = None,
        sprint_id: str | None = None,
        realized_hours: float = 0,
        description: str = "",
    ) -> str:
        self.require(project_id, actor_id, "create")
        if not title.strip():
            raise ValueError("task title is required")
        if priority not in PRIORITIES or recurrence not in RECURRENCES:
            raise ValueError("invalid priority or recurrence")
        _validate_date(start_date, "task start date")
        _validate_date(due_date, "task due date")
        _validate_date(recurrence_end, "recurrence end date")
        if due_date and start_date and due_date < start_date:
            raise ValueError("due date cannot be before start date")
        with self._connect() as connection:
            if parent_task_id is not None:
                parent = connection.execute(
                    "SELECT project_id,phase_id FROM pm_tasks WHERE task_id=?",
                    (parent_task_id,),
                ).fetchone()
                if parent is None:
                    raise KeyError(parent_task_id)
                if str(parent[0]) != project_id:
                    raise ValueError("parent task does not belong to this project")
                if phase_id is None and parent[1] is not None:
                    phase_id = str(parent[1])
            if phase_id is not None:
                row = connection.execute("SELECT project_id FROM pm_phases WHERE phase_id=?", (phase_id,)).fetchone()
                if row is None or str(row[0]) != project_id:
                    raise ValueError("phase does not belong to this project")
            if sprint_id is not None:
                row = connection.execute("SELECT project_id FROM pm_sprints WHERE sprint_id=?", (sprint_id,)).fetchone()
                if row is None or str(row[0]) != project_id:
                    raise ValueError("sprint does not belong to this project")
            if status_id is None:
                row = connection.execute(
                    "SELECT status_id FROM pm_statuses WHERE project_id=? "
                    "ORDER BY display_order LIMIT 1",
                    (project_id,),
                ).fetchone()
                if row is None:
                    raise ValueError("project has no workflow status")
                status_id = str(row[0])
            task_id = _id()
            now = _now_us()
            position = connection.execute(
                "SELECT COALESCE(MAX(position),-1)+1 FROM pm_tasks "
                "WHERE project_id=? AND status_id=?",
                (project_id, status_id),
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO pm_tasks(
                    task_id,project_id,parent_task_id,title,description,status_id,owner_id,
                    priority,start_date,due_date,estimate_hours,budget,progress,recurrence,
                    recurrence_end,milestone,sprint,position,phase_id,sprint_id,realized_hours,
                    created_by,created_at_us,updated_at_us
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (task_id, project_id, parent_task_id, title.strip(), description.strip(),
                 status_id, (owner_id.strip() or actor_id), priority, start_date, due_date,
                 float(estimate_hours), float(budget), 0, recurrence, recurrence_end,
                 int(milestone), sprint.strip(), int(position), phase_id, sprint_id,
                 float(realized_hours), actor_id, now, now),
            )
            self._event(connection, project_id, actor_id, "task.created", task_id=task_id,
                        details={"title": title, "owner": (owner_id.strip() or actor_id), "due": due_date})
            self._notify(connection, (owner_id.strip() or actor_id), project_id, task_id, "task.assigned",
                         f"You were assigned: {title}")
            if due_date:
                try:
                    due = datetime.combine(date.fromisoformat(due_date), datetime.min.time(), UTC)
                    self._notify(
                        connection, owner_id, project_id, task_id, "task.due_soon",
                        f"Task due soon: {title}",
                        deliver_at_us=int((due - timedelta(days=1)).timestamp() * 1_000_000),
                    )
                except ValueError:
                    pass
        return task_id

    def update_task(self, task_id: str, *, actor_id: str, **changes: object) -> None:
        allowed = {
            "title", "description", "status_id", "owner_id", "priority", "start_date",
            "due_date", "estimate_hours", "budget", "progress", "recurrence",
            "recurrence_end", "milestone", "sprint", "position", "phase_id",
            "sprint_id", "realized_hours",
        }
        values = {key: value for key, value in changes.items() if key in allowed}
        if not values:
            return
        with self._connect() as connection:
            row = connection.execute(
                "SELECT project_id,owner_id,status_id FROM pm_tasks WHERE task_id=?",
                (task_id,),
            ).fetchone()
            if row is None:
                raise KeyError(task_id)
            project_id = str(row[0])
            if str(row[1] or "") != actor_id:
                self.require(project_id, actor_id, "edit", connection=connection)
            if "status_id" in values:
                target = connection.execute(
                    "SELECT category,wip_limit FROM pm_statuses WHERE status_id=? AND project_id=?",
                    (values["status_id"], project_id),
                ).fetchone()
                if target is None:
                    raise ValueError("status does not belong to project")
                if str(target[0]) == "active":
                    blockers = connection.execute(
                        """SELECT COUNT(*) FROM pm_task_dependencies d
                           JOIN pm_tasks p ON p.task_id=d.depends_on_task_id
                           JOIN pm_statuses s ON s.status_id=p.status_id
                           WHERE d.task_id=? AND s.category!='done'""",
                        (task_id,),
                    ).fetchone()[0]
                    if blockers:
                        raise ValueError("task cannot start until all dependencies are done")
                if target[1] is not None:
                    current = connection.execute(
                        "SELECT COUNT(*) FROM pm_tasks WHERE status_id=? AND task_id<>?",
                        (values["status_id"], task_id),
                    ).fetchone()[0]
                    if int(current) >= int(target[1]):
                        raise ValueError("workflow status WIP limit has been reached")
            assignments = ",".join(f"{key}=?" for key in values)
            connection.execute(
                f"UPDATE pm_tasks SET {assignments},updated_at_us=? WHERE task_id=?",
                (*values.values(), _now_us(), task_id),
            )
            self._event(connection, project_id, actor_id, "task.updated", task_id=task_id,
                        details=values)
            new_owner = str(values.get("owner_id") or "")
            if new_owner and new_owner != str(row["owner_id"]):
                self._notify(connection, new_owner, project_id, task_id, "task.assigned",
                             "A task was assigned to you")

    def delete_task(self, task_id: str, *, actor_id: str) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT project_id,title FROM pm_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if row is None:
                return
            self.require(str(row[0]), actor_id, "delete", connection=connection)
            self._event(connection, str(row[0]), actor_id, "task.deleted",
                        task_id=task_id, details={"title": str(row[1])})
            connection.execute("DELETE FROM pm_tasks WHERE task_id=?", (task_id,))

    def add_dependency(
        self, task_id: str, depends_on_task_id: str, *, actor_id: str
    ) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT project_id FROM pm_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            other = connection.execute(
                "SELECT project_id FROM pm_tasks WHERE task_id=?", (depends_on_task_id,)
            ).fetchone()
            if row is None or other is None or row[0] != other[0]:
                raise ValueError("dependencies must reference tasks in the same project")
            project_id = str(row[0])
            self.require(project_id, actor_id, "edit", connection=connection)
            if self._would_cycle(connection, task_id, depends_on_task_id):
                raise ValueError("dependency would create a cycle")
            connection.execute(
                "INSERT OR IGNORE INTO pm_task_dependencies VALUES(?,?,'finish_to_start')",
                (task_id, depends_on_task_id),
            )
            self._event(connection, project_id, actor_id, "dependency.created",
                        task_id=task_id, details={"depends_on": depends_on_task_id})

    @staticmethod
    def _would_cycle(
        connection: sqlite3.Connection, task_id: str, depends_on: str
    ) -> bool:
        row = connection.execute(
            """WITH RECURSIVE chain(task_id) AS(
                   SELECT depends_on_task_id FROM pm_task_dependencies WHERE task_id=?
                   UNION
                   SELECT d.depends_on_task_id FROM pm_task_dependencies d
                   JOIN chain c ON d.task_id=c.task_id
               ) SELECT 1 FROM chain WHERE task_id=? LIMIT 1""",
            (depends_on, task_id),
        ).fetchone()
        return row is not None or task_id == depends_on

    def add_checklist_item(
        self, task_id: str, title: str, *, actor_id: str, owner_id: str = ""
    ) -> str:
        item_id = _id()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT project_id FROM pm_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if row is None:
                raise KeyError(task_id)
            self.require(str(row[0]), actor_id, "edit", connection=connection)
            order = connection.execute(
                "SELECT COALESCE(MAX(display_order),-1)+1 FROM pm_checklist_items WHERE task_id=?",
                (task_id,),
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO pm_checklist_items VALUES(?,?,?,?,?,?,?)",
                (item_id, task_id, title.strip(), 0, owner_id.strip(), order, _now_us()),
            )
            self._event(connection, str(row[0]), actor_id, "checklist.created",
                        task_id=task_id, details={"title": title})
        return item_id

    def checklist(self, task_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pm_checklist_items WHERE task_id=? ORDER BY display_order",
                (task_id,),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def set_checklist_completed(
        self, item_id: str, completed: bool, *, actor_id: str
    ) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT c.task_id,t.project_id FROM pm_checklist_items c "
                "JOIN pm_tasks t ON t.task_id=c.task_id WHERE c.item_id=?",
                (item_id,),
            ).fetchone()
            if row is None:
                raise KeyError(item_id)
            self.require(str(row[1]), actor_id, "edit", connection=connection)
            connection.execute(
                "UPDATE pm_checklist_items SET completed=? WHERE item_id=?",
                (int(completed), item_id),
            )
            self._event(connection, str(row[1]), actor_id, "checklist.updated",
                        task_id=str(row[0]), details={"completed": bool(completed)})

    def add_comment(
        self,
        task_id: str,
        body: str,
        *,
        author_id: str,
        parent_comment_id: str | None = None,
    ) -> str:
        mentions = sorted(
            {word[1:].rstrip(".,:;!?") for word in body.split() if word.startswith("@") and len(word) > 1}
        )
        comment_id = _id()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT project_id FROM pm_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if row is None:
                raise KeyError(task_id)
            project_id = str(row[0])
            self.require(project_id, author_id, "edit", connection=connection)
            connection.execute(
                "INSERT INTO pm_comments VALUES(?,?,?,?,?,?,?,NULL)",
                (comment_id, task_id, parent_comment_id, author_id, body.strip(),
                 json.dumps(mentions), _now_us()),
            )
            self._event(connection, project_id, author_id, "comment.created",
                        task_id=task_id, details={"comment_id": comment_id, "mentions": mentions})
            for user_id in mentions:
                self._notify(connection, user_id, project_id, task_id, "comment.mentioned",
                             f"{author_id} mentioned you in a task comment")
        return comment_id

    def comments(self, task_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pm_comments WHERE task_id=? ORDER BY created_at_us,comment_id",
                (task_id,),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def add_attachment(
        self,
        task_id: str,
        name: str,
        location: str,
        *,
        actor_id: str,
        kind: str = "file",
        previous_attachment_id: str | None = None,
    ) -> str:
        attachment_id = _id()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT project_id FROM pm_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if row is None:
                raise KeyError(task_id)
            project_id = str(row[0])
            self.require(project_id, actor_id, "edit", connection=connection)
            version = 1
            if previous_attachment_id:
                previous = connection.execute(
                    "SELECT version FROM pm_attachments WHERE attachment_id=? AND task_id=?",
                    (previous_attachment_id, task_id),
                ).fetchone()
                if previous is None:
                    raise ValueError("previous attachment version is not attached to task")
                version = int(previous[0]) + 1
            connection.execute(
                "INSERT INTO pm_attachments VALUES(?,?,?,?,?,?,?,?,?)",
                (attachment_id, task_id, name.strip(), kind, location.strip(), version,
                 previous_attachment_id, actor_id, _now_us()),
            )
            self._event(connection, project_id, actor_id, "attachment.created",
                        task_id=task_id, details={"name": name, "version": version})
        return attachment_id

    def attachments(self, task_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pm_attachments WHERE task_id=? ORDER BY name,version DESC",
                (task_id,),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def log_time(
        self, task_id: str, user_id: str, minutes: int, *, note: str = ""
    ) -> str:
        if minutes <= 0:
            raise ValueError("time must be greater than zero")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT project_id FROM pm_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if row is None:
                raise KeyError(task_id)
            project_id = str(row[0])
            self.require(project_id, user_id, "edit", connection=connection)
            entry_id = _id()
            connection.execute(
                "INSERT INTO pm_time_entries VALUES(?,?,?,NULL,NULL,?,?,?)",
                (entry_id, task_id, user_id, int(minutes), note.strip(), _now_us()),
            )
            self._event(connection, project_id, user_id, "time.logged", task_id=task_id,
                        details={"minutes": minutes})
        return entry_id

    def time_entries(self, task_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pm_time_entries WHERE task_id=? ORDER BY created_at_us DESC",
                (task_id,),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def dependencies(self, task_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT p.task_id,p.title,s.name AS status,d.dependency_type
                   FROM pm_task_dependencies d
                   JOIN pm_tasks p ON p.task_id=d.depends_on_task_id
                   JOIN pm_statuses s ON s.status_id=p.status_id
                   WHERE d.task_id=? ORDER BY p.title""",
                (task_id,),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def task_activity(self, task_id: str, *, limit: int = 200) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pm_activity WHERE task_id=? ORDER BY created_at_us DESC LIMIT ?",
                (task_id, int(limit)),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    @staticmethod
    def _parse_iso_datetime(value: str) -> datetime:
        text = str(value).strip().replace(" ", "T")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    def ensure_default_schedule_templates(self, *, actor_id: str = "system") -> None:
        now = _now_us()
        defaults = (("40-hours", "40 hours", 1, 40, 40), ("36-hours", "36 hours", 1, 36, 36),
                    ("32-hours", "32 hours", 1, 32, 32), ("40-32-alternating", "Odd week 40 / even week 32", 2, 40, 32),
                    ("32-40-alternating", "Odd week 32 / even week 40", 2, 32, 40))
        with self._connect() as connection:
            for tid,name,cycle,odd,even in defaults:
                connection.execute("INSERT OR IGNORE INTO hr_schedule_templates VALUES(?,?,?,?,?,?,?,?,?)",
                                   (tid,name,"Default work-schedule template",cycle,odd,even,1,actor_id,now))
                # Five-day schedule. Alternating 32-hour week uses 6.4 hours/day.
                for parity,hours in ((1,odd),(2,even)) if cycle == 2 else ((0,odd),):
                    daily=float(hours)/5.0
                    for weekday in range(1,6):
                        end_hour=8.0+daily
                        hh=int(end_hour); mm=int(round((end_hour-hh)*60))
                        connection.execute("INSERT OR IGNORE INTO hr_schedule_periods VALUES(?,?,?,?,?,?)",
                                           (_id(),tid,parity,weekday,"08:00",f"{hh:02d}:{mm:02d}"))

    def schedule_templates(self) -> tuple[dict, ...]:
        self.ensure_default_schedule_templates()
        with self._connect() as connection:
            rows=connection.execute("SELECT * FROM hr_schedule_templates WHERE active=1 ORDER BY name").fetchall()
        return tuple(dict(r) for r in rows)

    def assign_work_schedule(self,user_id: str,template_id: str,effective_from: str,*,effective_until: str="",reference_week: str="",actor_id: str) -> str:
        _validate_date(effective_from,"schedule effective date")
        if effective_until: _validate_date(effective_until,"schedule end date")
        reference_week=reference_week or effective_from
        _validate_date(reference_week,"reference week")
        assignment_id=_id()
        with self._connect() as connection:
            connection.execute("INSERT INTO hr_user_schedules VALUES(?,?,?,?,?,?,?,?)",
                               (assignment_id,user_id,template_id,effective_from,effective_until,reference_week,actor_id,_now_us()))
        return assignment_id

    def add_absence(self,user_id: str,start_at: str,end_at: str,absence_type: str,*,privacy_level: str="private",status: str="approved",note: str="",actor_id: str) -> str:
        start=self._parse_iso_datetime(start_at); end=self._parse_iso_datetime(end_at)
        if end <= start: raise ValueError("absence end must be after start")
        aid=_id()
        with self._connect() as connection:
            connection.execute("INSERT INTO hr_absences VALUES(?,?,?,?,?,?,?,?,?,?)",
                               (aid,user_id,start.isoformat(),end.isoformat(),absence_type,privacy_level,status,note.strip(),actor_id,_now_us()))
        return aid

    def add_organisational_obligation(self,user_id: str,start_at: str,end_at: str,obligation_type: str,title: str,*,note: str="",actor_id: str) -> str:
        start=self._parse_iso_datetime(start_at); end=self._parse_iso_datetime(end_at)
        if end <= start: raise ValueError("obligation end must be after start")
        oid=_id()
        with self._connect() as connection:
            connection.execute("INSERT INTO hr_organisational_obligations VALUES(?,?,?,?,?,?,?,?,?)",
                               (oid,user_id,start.isoformat(),end.isoformat(),obligation_type,title.strip(),note.strip(),actor_id,_now_us()))
        return oid

    def set_project_allocation(self,user_id: str,project_id: str,start_date: str,*,end_date: str="",hours_per_week: float=0,allocation_percent: float=0,role: str="",phase_id: str|None=None,actor_id: str) -> str:
        self.require(project_id,actor_id,"manage")
        _validate_date(start_date,"allocation start date")
        if end_date: _validate_date(end_date,"allocation end date")
        if hours_per_week < 0 or allocation_percent < 0: raise ValueError("allocation cannot be negative")
        allocation_id=_id()
        with self._connect() as connection:
            connection.execute("INSERT INTO hr_project_allocations VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                               (allocation_id,user_id,project_id,start_date,end_date,float(hours_per_week),float(allocation_percent),role,phase_id,"active",actor_id,_now_us()))
            self._event(connection,project_id,actor_id,"allocation.updated",details={"user":user_id,"hours_per_week":hours_per_week,"percent":allocation_percent})
        return allocation_id

    def _schedule_for(self,connection,user_id: str,on_date: date):
        return connection.execute("SELECT us.*,t.cycle_weeks,t.weekly_hours_odd,t.weekly_hours_even FROM hr_user_schedules us JOIN hr_schedule_templates t ON t.template_id=us.template_id WHERE us.user_id=? AND us.effective_from<=? AND (us.effective_until='' OR us.effective_until>=?) ORDER BY us.effective_from DESC LIMIT 1",(user_id,on_date.isoformat(),on_date.isoformat())).fetchone()

    def capacity_summary(self,user_id: str,start_at: str,end_at: str,*,project_id: str|None=None) -> dict:
        start=self._parse_iso_datetime(start_at); end=self._parse_iso_datetime(end_at)
        if end <= start: raise ValueError("capacity range end must be after start")
        self.ensure_default_schedule_templates()
        scheduled=0.0
        with self._connect() as connection:
            day=start.date()
            while day <= end.date():
                sched=self._schedule_for(connection,user_id,day)
                if sched:
                    parity=0
                    if int(sched["cycle_weeks"])==2:
                        ref=date.fromisoformat(str(sched["reference_week"])); parity=1 if ((day-ref).days//7)%2==0 else 2
                    periods=connection.execute("SELECT start_time,end_time FROM hr_schedule_periods WHERE template_id=? AND weekday=? AND week_parity IN(0,?)",(sched["template_id"],day.isoweekday(),parity)).fetchall()
                    for period in periods:
                        ps=datetime.fromisoformat(f"{day.isoformat()}T{period['start_time']}").replace(tzinfo=start.tzinfo)
                        pe=datetime.fromisoformat(f"{day.isoformat()}T{period['end_time']}").replace(tzinfo=start.tzinfo)
                        overlap=max(0.0,(min(pe,end)-max(ps,start)).total_seconds()/3600)
                        scheduled+=overlap
                day += timedelta(days=1)
            def overlap_hours(table):
                rows=connection.execute(f"SELECT start_at,end_at FROM {table} WHERE user_id=? AND end_at>? AND start_at<?",(user_id,start.isoformat(),end.isoformat())).fetchall()
                intervals=[]
                for r in rows:
                    a=max(start,self._parse_iso_datetime(r['start_at'])); b=min(end,self._parse_iso_datetime(r['end_at']))
                    if b>a: intervals.append((a,b))
                intervals.sort(); merged=[]
                for a,b in intervals:
                    if merged and a<=merged[-1][1]: merged[-1]=(merged[-1][0],max(merged[-1][1],b))
                    else: merged.append((a,b))
                return sum((b-a).total_seconds()/3600 for a,b in merged)
            unavailable=overlap_hours("hr_absences")
            organisational=overlap_hours("hr_organisational_obligations")
            params=[user_id,start.date().isoformat(),end.date().isoformat()]
            sql="SELECT project_id,hours_per_week,allocation_percent FROM hr_project_allocations WHERE user_id=? AND status='active' AND start_date<=? AND (end_date='' OR end_date>=?)"
            allocations=connection.execute(sql,(user_id,end.date().isoformat(),start.date().isoformat())).fetchall()
        net=max(0.0,scheduled-unavailable-organisational)
        weeks=max((end-start).total_seconds()/604800,1/7)
        allocation_hours=sum((float(r['hours_per_week']) if float(r['hours_per_week']) else net*float(r['allocation_percent'])/100.0) * weeks for r in allocations if project_id is None or r['project_id']==project_id)
        return {"scheduled_hours":round(scheduled,2),"absence_hours":round(unavailable,2),"organisational_hours":round(organisational,2),"net_capacity_hours":round(net,2),"allocated_hours":round(allocation_hours,2),"remaining_hours":round(net-allocation_hours,2)}

    def workload(self, project_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows=connection.execute("SELECT m.user_id,m.role,COUNT(t.task_id) task_count,COALESCE(SUM(CASE WHEN s.category!='done' THEN t.estimate_hours ELSE 0 END),0) open_estimate_hours,COALESCE((SELECT SUM(e.minutes)/60.0 FROM pm_time_entries e JOIN pm_tasks te ON te.task_id=e.task_id WHERE te.project_id=m.project_id AND e.user_id=m.user_id),0) actual_hours FROM pm_project_members m LEFT JOIN pm_tasks t ON t.project_id=m.project_id AND t.owner_id=m.user_id LEFT JOIN pm_statuses s ON s.status_id=t.status_id WHERE m.project_id=? GROUP BY m.user_id,m.role ORDER BY open_estimate_hours DESC,m.user_id",(project_id,)).fetchall()
        today=datetime.now(UTC); end=today+timedelta(days=7)
        result=[]
        for row in rows:
            item=dict(row); cap=self.capacity_summary(item['user_id'],today.isoformat(),end.isoformat(),project_id=project_id)
            item.update(cap); result.append(item)
        return tuple(result)

    def portfolio_snapshot(self, user_id: str) -> dict[str, object]:
        """Return a permission-filtered portfolio across all accessible projects.

        Platform administrators inherit all projects through ``accessible_projects``.
        Other users only receive projects they own or where their effective role grants
        view access.  The returned rows are intentionally presentation-neutral so the
        desktop, server, and future mobile clients can use the same calculations.
        """
        projects = tuple(self.accessible_projects(user_id, permission="view"))
        project_rows: list[dict] = []
        task_rows: list[dict] = []
        phase_rows: list[dict] = []
        workload_by_user: dict[str, dict] = {}
        total_budget = 0.0
        total_realized_budget = 0.0
        total_effective = 0.0
        total_realized = 0.0
        for project in projects:
            project_id = str(project["project_id"])
            tasks = self.tasks(project_id)
            phases = self.phases(project_id)
            workload = self.workload(project_id)
            planned = float(project.get("budget") or 0)
            realized_budget = sum(float(row.get("realized_budget") or 0) for row in phases)
            effective = sum(t.effective_estimate_hours for t in tasks if t.parent_task_id is None)
            realized = sum(t.realized_hours for t in tasks if t.parent_task_id is None)
            total_budget += planned
            total_realized_budget += realized_budget
            total_effective += effective
            total_realized += realized
            project_rows.append({
                **dict(project),
                "task_count": len(tasks),
                "phase_count": len(phases),
                "effective_estimate_hours": round(effective, 2),
                "realized_hours": round(realized, 2),
                "realized_budget": round(realized_budget, 2),
                "budget_variance": round(planned - realized_budget, 2),
            })
            for phase in phases:
                phase_rows.append({**dict(phase), "project_name": str(project.get("name") or "")})
            for task in tasks:
                task_rows.append({
                    "project_id": project_id,
                    "project_name": str(project.get("name") or ""),
                    "task_id": task.task_id,
                    "parent_task_id": task.parent_task_id,
                    "title": task.title,
                    "phase_id": task.phase_id,
                    "phase_name": task.phase_name,
                    "sprint_name": task.sprint_name,
                    "owner_id": task.owner_id,
                    "status_id": task.status_id,
                    "status_name": task.status_name,
                    "status_category": task.status_category,
                    "priority": task.priority,
                    "start_date": task.start_date,
                    "due_date": task.due_date,
                    "effective_estimate_hours": task.effective_estimate_hours,
                    "realized_hours": task.realized_hours,
                    "progress": task.progress,
                    "blocked": task.blocked,
                    "milestone": task.milestone,
                })
            for row in workload:
                uid = str(row["user_id"])
                target = workload_by_user.setdefault(uid, {
                    "user_id": uid, "projects": set(), "roles": set(),
                    "scheduled_hours": 0.0, "absence_hours": 0.0,
                    "organisational_hours": 0.0, "allocated_hours": 0.0,
                    "remaining_hours": 0.0, "task_count": 0,
                    "open_estimate_hours": 0.0, "actual_hours": 0.0,
                })
                target["projects"].add(str(project.get("name") or project_id))
                target["roles"].add(str(row.get("role") or "member"))
                for key in ("scheduled_hours", "absence_hours", "organisational_hours", "allocated_hours", "remaining_hours", "open_estimate_hours", "actual_hours"):
                    target[key] += float(row.get(key) or 0)
                target["task_count"] += int(row.get("task_count") or 0)
        workload_rows = []
        for row in workload_by_user.values():
            workload_rows.append({
                **row,
                "projects": ", ".join(sorted(row["projects"])),
                "roles": ", ".join(sorted(row["roles"])),
                "scheduled_hours": round(row["scheduled_hours"], 2),
                "absence_hours": round(row["absence_hours"], 2),
                "organisational_hours": round(row["organisational_hours"], 2),
                "allocated_hours": round(row["allocated_hours"], 2),
                "remaining_hours": round(row["remaining_hours"], 2),
                "open_estimate_hours": round(row["open_estimate_hours"], 2),
                "actual_hours": round(row["actual_hours"], 2),
            })
        workload_rows.sort(key=lambda row: (-float(row["open_estimate_hours"]), str(row["user_id"])))
        return {
            "projects": tuple(project_rows),
            "phases": tuple(phase_rows),
            "tasks": tuple(task_rows),
            "workload": tuple(workload_rows),
            "summary": {
                "project_count": len(project_rows),
                "phase_count": len(phase_rows),
                "task_count": len(task_rows),
                "planned_budget": round(total_budget, 2),
                "realized_budget": round(total_realized_budget, 2),
                "budget_variance": round(total_budget - total_realized_budget, 2),
                "effective_estimate_hours": round(total_effective, 2),
                "realized_hours": round(total_realized, 2),
            },
        }

    def add_leave(self, user_id: str, start_date: str, end_date: str, kind: str, note: str = "") -> str:
        """Compatibility API; project UI no longer exposes leave entry. HR owns the record."""
        _validate_date(start_date, "leave start date")
        _validate_date(end_date, "leave end date")
        if end_date < start_date:
            raise ValueError("leave end date cannot be before start date")
        return self.add_absence(user_id, f"{start_date}T00:00:00+00:00", f"{end_date}T23:59:59+00:00", kind, note=note, actor_id=user_id)

    def set_capacity(self, project_id: str, user_id: str, weekly_hours: float, hourly_cost: float, *, actor_id: str) -> None:
        """Compatibility API for reports; schedules are authoritative for availability."""
        self.require(project_id, actor_id, "manage")
        with self._connect() as connection:
            connection.execute("INSERT INTO pm_capacity VALUES(?,?,?,?) ON CONFLICT(project_id,user_id) DO UPDATE SET weekly_hours=excluded.weekly_hours,hourly_cost=excluded.hourly_cost", (project_id,user_id,float(weekly_hours),float(hourly_cost)))
            self._event(connection,project_id,actor_id,"capacity.updated",details={"user":user_id,"weekly_hours":weekly_hours})

    def project_members(self, project_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT user_id,role FROM pm_project_members WHERE project_id=? ORDER BY user_id",
                (project_id,),
            ).fetchall()
            owner = connection.execute(
                "SELECT owner_id FROM pm_projects WHERE project_id=?", (project_id,)
            ).fetchone()
        result = [dict(row) for row in rows]
        if owner and not any(str(row["user_id"]) == str(owner[0]) for row in result):
            result.insert(0, {"user_id": str(owner[0]), "role": "owner"})
        return tuple(result)

    def task_details(self, task_id: str) -> dict:
        """Return the complete editable task record for the detail workspace."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM pm_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
        if row is None:
            raise KeyError(task_id)
        return dict(row)

    def can_edit_task(self, task_id: str, user_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT project_id,owner_id FROM pm_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
        if row is None:
            return False
        return str(row[1] or "") == user_id or self.can(str(row[0]), user_id, "edit")

    def add_task_note(self, task_id: str, body: str, *, author_id: str) -> str:
        if not body.strip():
            raise ValueError("note is required")
        note_id = _id()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT project_id,owner_id FROM pm_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if row is None:
                raise KeyError(task_id)
            if str(row[1] or "") != author_id:
                self.require(str(row[0]), author_id, "edit", connection=connection)
            now = _now_us()
            connection.execute(
                "INSERT INTO pm_task_notes(note_id,task_id,body,author_id,created_at_us) VALUES(?,?,?,?,?)",
                (note_id, task_id, body.strip(), author_id, now),
            )
            self._event(connection, str(row[0]), author_id, "task.note_added",
                        task_id=task_id, details={"note_id": note_id})
        return note_id

    def task_notes(self, task_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pm_task_notes WHERE task_id=? ORDER BY created_at_us,note_id",
                (task_id,),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def set_member_role(
        self, project_id: str, user_id: str, role: str, *, actor_id: str
    ) -> None:
        if role not in ROLE_PERMISSIONS:
            raise ValueError("unknown project role")
        self.require(project_id, actor_id, "manage")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO pm_project_members VALUES(?,?,?) "
                "ON CONFLICT(project_id,user_id) DO UPDATE SET role=excluded.role",
                (project_id, user_id, role),
            )
            self._event(connection, project_id, actor_id, "member.role_changed",
                        details={"user": user_id, "role": role})

    def _effective_project_role(self, member_role: str | None, user_id: str) -> str:
        """Resolve the project role, including the authenticated platform administrator."""
        if user_id == "local-user" or os.environ.get("FIELDORA_PROFILE_ROLE") == "administrator":
            return "admin"
        return "" if member_role is None else str(member_role)

    def authorization_snapshot(self, project_id: str, user_id: str) -> dict[str, object]:
        """Return the effective RBAC/ABAC/PBAC inputs used for this project decision."""
        with self._connect() as connection:
            project = connection.execute(
                "SELECT status,owner_id FROM pm_projects WHERE project_id=?", (project_id,)
            ).fetchone()
            if project is None:
                raise KeyError(project_id)
            member = connection.execute(
                "SELECT role FROM pm_project_members WHERE project_id=? AND user_id=?",
                (project_id, user_id),
            ).fetchone()
        role = self._effective_project_role(None if member is None else str(member[0]), user_id)
        return {
            "user_id": user_id,
            "role": role,
            "permissions": tuple(sorted(ROLE_PERMISSIONS.get(role, frozenset()))),
            "project_status": str(project[0]),
            "owner_id": str(project[1]),
            "rbac": bool(role),
            "abac_editable": str(project[0]) not in {"archived", "cancelled"} or role == "admin",
            "pbac_default": "deny",
        }

    def can(self, project_id: str, user_id: str, permission: str) -> bool:
        try:
            self.require(project_id, user_id, permission)
            return True
        except (PermissionError, KeyError):
            return False

    def accessible_projects(self, user_id: str, permission: str = "view") -> tuple[dict, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT p.project_id,p.name,p.status,p.owner_id,m.role,p.due_date,p.budget,p.currency,p.start_date "
                "FROM pm_projects p LEFT JOIN pm_project_members m "
                "ON m.project_id=p.project_id AND m.user_id=? ORDER BY p.updated_at_us DESC",
                (user_id,),
            ).fetchall()
        visible = []
        for row in rows:
            role = self._effective_project_role(None if row[4] is None else str(row[4]), user_id)
            if permission in ROLE_PERMISSIONS.get(role, frozenset()):
                visible.append(dict(row))
        return tuple(visible)

    def require(
        self,
        project_id: str,
        user_id: str,
        permission: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        owns = connection is None
        db = connection or self._connect()
        try:
            row = db.execute(
                "SELECT role FROM pm_project_members WHERE project_id=? AND user_id=?",
                (project_id, user_id),
            ).fetchone()
            role = self._effective_project_role(None if row is None else str(row[0]), user_id)
            project = db.execute("SELECT status FROM pm_projects WHERE project_id=?", (project_id,)).fetchone()
            if project is None:
                raise KeyError(project_id)
            if permission not in ROLE_PERMISSIONS.get(role, frozenset()):
                raise PermissionError(f"{user_id} does not have {permission} permission")
            # ABAC project-state rule. PBAC remains default-deny and combines this
            # attribute decision with the project role above.
            if permission in {"create", "edit", "delete", "manage"} and str(project[0]) in {"archived", "cancelled"} and role != "admin":
                raise PermissionError(f"{permission} is denied while the project is {project[0]}")
        finally:
            if owns:
                db.close()

    def add_custom_field(
        self,
        project_id: str,
        name: str,
        field_type: str,
        *,
        actor_id: str,
        options: tuple[str, ...] = (),
        required: bool = False,
    ) -> str:
        self.require(project_id, actor_id, "manage")
        field_id = _id()
        with self._connect() as connection:
            order = connection.execute(
                "SELECT COALESCE(MAX(display_order),-1)+1 FROM pm_custom_fields WHERE project_id=?",
                (project_id,),
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO pm_custom_fields VALUES(?,?,?,?,?,?,?)",
                (field_id, project_id, name.strip(), field_type, json.dumps(options),
                 int(required), int(order)),
            )
            self._event(connection, project_id, actor_id, "custom_field.created",
                        details={"name": name, "type": field_type})
        return field_id

    def custom_fields(self, project_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pm_custom_fields WHERE project_id=? ORDER BY name,field_id",
                (project_id,),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def set_custom_field_value(
        self, task_id: str, field_id: str, value: object, *, actor_id: str
    ) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT t.project_id,f.project_id FROM pm_tasks t CROSS JOIN pm_custom_fields f "
                "WHERE t.task_id=? AND f.field_id=?",
                (task_id, field_id),
            ).fetchone()
            if row is None or row[0] != row[1]:
                raise ValueError("custom field does not belong to the task project")
            self.require(str(row[0]), actor_id, "edit", connection=connection)
            connection.execute(
                "INSERT INTO pm_custom_values VALUES(?,?,?) "
                "ON CONFLICT(task_id,field_id) DO UPDATE SET value_json=excluded.value_json",
                (task_id, field_id, json.dumps(value)),
            )
            self._event(
                connection, str(row[0]), actor_id, "custom_field.updated",
                task_id=task_id, details={"field_id": field_id},
            )

    def custom_field_values(self, task_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT f.field_id,f.name,f.field_type,f.options_json,
                          COALESCE(v.value_json,'null') value_json
                   FROM pm_tasks t JOIN pm_custom_fields f ON f.project_id=t.project_id
                   LEFT JOIN pm_custom_values v
                     ON v.task_id=t.task_id AND v.field_id=f.field_id
                   WHERE t.task_id=? ORDER BY f.name,f.field_id""",
                (task_id,),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def save_template(
        self, project_id: str, name: str, *, actor_id: str
    ) -> str:
        self.require(project_id, actor_id, "manage")
        definition = {
            "statuses": [
                {key: row[key] for key in ("name", "category", "color", "display_order", "wip_limit")}
                for row in self.statuses(project_id)
            ],
            "tasks": [
                {
                    "title": task.title, "priority": task.priority,
                    "estimate_hours": task.estimate_hours, "milestone": task.milestone,
                    "status_name": task.status_name,
                }
                for task in self.tasks(project_id)
                if task.parent_task_id is None
            ],
        }
        template_id = _id()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO pm_templates VALUES(?,?,?,?,?,?)",
                (template_id, name.strip(), "", json.dumps(definition), actor_id, _now_us()),
            )
        return template_id

    def templates(self) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT template_id,name,description,created_by,created_at_us "
                "FROM pm_templates ORDER BY name"
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def apply_template(self, project_id: str, template_id: str, *, actor_id: str) -> None:
        self.require(project_id, actor_id, "manage")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT definition_json FROM pm_templates WHERE template_id=?", (template_id,)
            ).fetchone()
        if row is None:
            raise KeyError(template_id)
        definition = json.loads(str(row[0]))
        status_by_name = {row["name"]: row["status_id"] for row in self.statuses(project_id)}
        for task in definition.get("tasks", []):
            self.create_task(
                project_id, str(task["title"]), actor_id=actor_id,
                status_id=status_by_name.get(str(task.get("status_name", ""))),
                priority=str(task.get("priority", "normal")),
                estimate_hours=float(task.get("estimate_hours", 0)),
                milestone=bool(task.get("milestone", False)),
            )

    def activity(self, project_id: str, *, limit: int = 500) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pm_activity WHERE project_id=? "
                "ORDER BY created_at_us DESC,event_id DESC LIMIT ?",
                (project_id, max(1, min(limit, 5000))),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def notifications(self, user_id: str) -> tuple[dict, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT *, event_type AS kind FROM pm_notifications "
                "WHERE user_id=? AND state='pending' "
                "AND deliver_at_us<=? ORDER BY deliver_at_us",
                (user_id, _now_us()),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def dashboard(self, project_id: str) -> dict[str, object]:
        tasks = self.tasks(project_id)
        today = date.today().isoformat()
        total = len(tasks)
        done = sum(item.status_category == "done" for item in tasks)
        overdue = sum(
            bool(item.due_date and item.due_date < today and item.status_category != "done")
            for item in tasks
        )
        blocked = sum(item.blocked or item.status_category == "blocked" for item in tasks)
        estimate = sum(item.estimate_hours for item in tasks)
        actual = sum(item.actual_hours for item in tasks)
        by_status: dict[str, int] = {}
        for item in tasks:
            by_status[item.status_name] = by_status.get(item.status_name, 0) + 1
        return {
            "total": total, "done": done, "overdue": overdue, "blocked": blocked,
            "completion_percent": 0 if not total else round(done * 100 / total, 1),
            "estimated_hours": estimate, "actual_hours": actual,
            "by_status": by_status,
        }

    def agile_metrics(self, project_id: str) -> dict[str, object]:
        tasks = self.tasks(project_id)
        by_sprint: dict[str, dict[str, float]] = {}
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT t.sprint,s.category,COUNT(*) count,SUM(t.estimate_hours) hours
                   FROM pm_tasks t JOIN pm_statuses s ON s.status_id=t.status_id
                   WHERE t.project_id=? GROUP BY t.sprint,s.category""",
                (project_id,),
            ).fetchall()
        for row in rows:
            sprint = str(row[0] or "Unscheduled")
            values = by_sprint.setdefault(sprint, {"planned": 0, "done": 0})
            values["planned"] += float(row[3] or row[2] or 0)
            if str(row[1]) == "done":
                values["done"] += float(row[3] or row[2] or 0)
        return {
            "sprints": by_sprint,
            "cumulative_flow": self.dashboard(project_id)["by_status"],
            "open_tasks": sum(item.status_category != "done" for item in tasks),
        }

    def materialize_recurring_tasks(self, project_id: str, *, actor_id: str) -> int:
        created = 0
        today = date.today()
        for task in self.tasks(project_id):
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT recurrence,recurrence_end,due_date,title,owner_id,priority,"
                    "estimate_hours,budget,status_id FROM pm_tasks WHERE task_id=?",
                    (task.task_id,),
                ).fetchone()
            if row is None or str(row[0]) == "none" or not str(row[2]):
                continue
            due = date.fromisoformat(str(row[2]))
            delta = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}.get(str(row[0]))
            next_due = (
                due + delta
                if delta is not None
                else date(due.year + (due.month == 12), 1 if due.month == 12 else due.month + 1,
                          min(due.day, 28))
            )
            if next_due > today:
                continue
            if row[1] and next_due.isoformat() > str(row[1]):
                continue
            self.create_task(
                project_id, str(row[3]), actor_id=actor_id, owner_id=str(row[4]),
                priority=str(row[5]), due_date=next_due.isoformat(),
                estimate_hours=float(row[6]), budget=float(row[7]), status_id=str(row[8]),
                recurrence="none",
            )
            self.update_task(
                task.task_id, actor_id=actor_id, due_date=next_due.isoformat()
            )
            created += 1
        return created

    def export_research_package(
        self,
        project_id: str,
        destination: Path,
        *,
        options: ProjectExportOptions,
        library_database: Path | None = None,
    ) -> Path:
        """Write a self-contained, selective ZIP with JSON, GeoJSON, CSV and HTML."""
        project = next((row for row in self.projects() if row.project_id == project_id), None)
        if project is None:
            raise KeyError(project_id)
        tasks = self.tasks(project_id) if options.include_tasks else ()
        notes = self.project_notes(project_id) if options.include_notes else ()
        areas = self.research_areas(project_id) if options.include_research_areas else ()
        snapshots = self.map_snapshots(project_id) if options.include_map_snapshots else ()
        media_links = self.project_media(project_id) if options.include_media_index else ()
        activity = self.activity(project_id, limit=5000) if options.include_activity else ()
        survey_protocols = self.survey_protocols(project_id) if options.include_surveys else ()
        survey_events = self.survey_events(project_id) if options.include_surveys else ()
        survey_results = {
            str(row["survey_event_id"]): self.survey_detections(str(row["survey_event_id"]))
            for row in survey_events
        }
        measurement_data = {"definitions": list(self.measurement_definitions(project_id)), "samples": list(self.samples(project_id)), "measurements": list(self.measurements(project_id)), **self.sample_workflow_records(project_id)} if options.include_measurements_samples else {}
        quality_data = list(self.quality_findings(project_id)) if options.include_quality_audit else []
        structured_records = self._structured_project_records(project_id) if options.include_tasks else {}
        media = self._resolve_project_media(media_links, library_database)
        manifest = {
            "format": "fieldora-project-research-package",
            "format_version": 1,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "project": {"id": project.project_id, "name": project.name},
            "selection": options.__dict__ if hasattr(options, "__dict__") else {
                field: getattr(options, field) for field in options.__dataclass_fields__
            },
            "counts": {
                "tasks": len(tasks), "notes": len(notes), "research_areas": len(areas),
                "media": len(media), "map_snapshots": len(snapshots), "activity": len(activity),
                "survey_protocols": len(survey_protocols), "survey_events": len(survey_events),
                "survey_results": sum(len(rows) for rows in survey_results.values()),
            },
        }
        destination.parent.mkdir(parents=True, exist_ok=True)
        used_names: set[str] = set()
        exported_media: list[dict] = []
        exported_snapshots: list[dict] = []
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as package:
            package.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            if options.include_project:
                package.writestr("data/project.json", json.dumps(project.__dict__ if hasattr(project, "__dict__") else {f: getattr(project, f) for f in project.__dataclass_fields__}, indent=2, ensure_ascii=False))
            if options.include_tasks:
                package.writestr("data/tasks.json", json.dumps([{f: getattr(row, f) for f in row.__dataclass_fields__} for row in tasks], indent=2, ensure_ascii=False))
                package.writestr("data/project-records.json", json.dumps(structured_records, indent=2, ensure_ascii=False))
            if options.include_notes:
                package.writestr("data/notes.json", json.dumps(notes, indent=2, ensure_ascii=False))
            if options.include_activity:
                package.writestr("data/activity.json", json.dumps(activity, indent=2, ensure_ascii=False))
            if options.include_surveys:
                package.writestr(
                    "data/surveys.json",
                    json.dumps(
                        {
                            "protocols": list(survey_protocols),
                            "events": list(survey_events),
                            "results": {key: list(value) for key, value in survey_results.items()},
                        },
                        indent=2,
                        ensure_ascii=False,
                    ),
                )
                output = io.StringIO()
                writer = csv.DictWriter(
                    output,
                    fieldnames=("event", "protocol", "status", "start", "location", "sampling_unit", "duration_minutes", "distance_m", "area_m2", "taxon", "detection_state", "count", "unit"),
                )
                writer.writeheader()
                for event in survey_events:
                    results = survey_results[str(event["survey_event_id"])] or ({},)
                    for result in results:
                        writer.writerow({
                            "event": event["name"], "protocol": event["protocol_name"] or "",
                            "status": event["status"], "start": event["start_text"],
                            "location": event["location_name"],
                            "sampling_unit": f'{event["sampling_unit_type"]}: {event["sampling_unit_name"]}',
                            "duration_minutes": event["effort_duration_minutes"],
                            "distance_m": event["effort_distance_m"], "area_m2": event["effort_area_m2"],
                            "taxon": result.get("taxon_name", ""), "detection_state": result.get("detection_state", ""),
                            "count": result.get("count_value", ""), "unit": result.get("unit", ""),
                        })
                package.writestr("data/surveys.csv", output.getvalue())
            if options.include_measurements_samples:
                package.writestr("data/measurements-samples.json", json.dumps(measurement_data, indent=2, ensure_ascii=False))
            if options.include_quality_audit:
                package.writestr("data/quality-findings.json", json.dumps(quality_data, indent=2, ensure_ascii=False))
            if options.include_research_areas:
                collection = {"type": "FeatureCollection", "features": [row["feature"] for row in areas]}
                package.writestr("maps/research-areas.geojson", json.dumps(collection, indent=2, ensure_ascii=False))
                package.writestr("maps/research-map.html", _research_map_html(project.name, collection))
            if options.include_map_snapshots:
                for row in snapshots:
                    source = Path(str(row["image_path"]))
                    exported = {key: value for key, value in row.items() if key not in {"image_path", "viewport_json"}}
                    exported["package_path"] = None
                    if source.is_file():
                        candidate = f"maps/snapshots/{_safe_export_name(str(row['snapshot_id']) + source.suffix.lower())}"
                        package.write(source, candidate)
                        exported["package_path"] = candidate
                    exported_snapshots.append(exported)
                package.writestr("maps/snapshots.json", json.dumps(exported_snapshots, indent=2, ensure_ascii=False))
            for row in media:
                exported = dict(row)
                source = Path(str(row.get("source_path") or ""))
                exported["package_path"] = None
                if options.include_original_media and source.is_file():
                    safe = _safe_export_name(source.name or str(row["asset_public_id"]))
                    candidate = f"media/{row.get('media_type') or 'other'}/{safe}"
                    stem, suffix, counter = Path(candidate).stem, Path(candidate).suffix, 2
                    while candidate.casefold() in used_names:
                        candidate = f"media/{row.get('media_type') or 'other'}/{stem}-{counter}{suffix}"
                        counter += 1
                    used_names.add(candidate.casefold())
                    package.write(source, candidate)
                    exported["package_path"] = candidate
                exported_media.append(exported)
            if options.include_task_attachments:
                for attachment in structured_records.get("attachments", []):
                    source = Path(str(attachment.get("location") or ""))
                    if not source.is_file():
                        continue
                    safe = _safe_export_name(source.name or str(attachment.get("name") or "attachment"))
                    candidate = f"attachments/{safe}"
                    counter = 2
                    while candidate.casefold() in used_names:
                        candidate = f"attachments/{Path(safe).stem}-{counter}{Path(safe).suffix}"
                        counter += 1
                    used_names.add(candidate.casefold())
                    package.write(source, candidate)
            if options.include_media_index:
                package.writestr("data/media-index.json", json.dumps(exported_media, indent=2, ensure_ascii=False))
                output = io.StringIO()
                writer = csv.DictWriter(output, fieldnames=("asset_public_id", "media_type", "title", "original_filename", "note", "package_path"), extrasaction="ignore")
                writer.writeheader()
                writer.writerows(exported_media)
                package.writestr("data/media-index.csv", output.getvalue())
            package.writestr(
                "index.html",
                _project_index_html(
                    project, tasks, notes, areas, exported_media, exported_snapshots,
                    embed_audio_video=options.embed_audio_video and options.include_original_media,
                ),
            )
        return destination

    def _structured_project_records(self, project_id: str) -> dict[str, list[dict]]:
        direct = {
            "statuses": ("pm_statuses", "project_id"),
            "tasks": ("pm_tasks", "project_id"),
            "capacity": ("pm_capacity", "project_id"),
            "members": ("pm_project_members", "project_id"),
            "custom_fields": ("pm_custom_fields", "project_id"),
            "activity": ("pm_activity", "project_id"),
        }
        related = {
            "dependencies": "SELECT d.* FROM pm_task_dependencies d JOIN pm_tasks t ON t.task_id=d.task_id WHERE t.project_id=?",
            "checklists": "SELECT c.* FROM pm_checklist_items c JOIN pm_tasks t ON t.task_id=c.task_id WHERE t.project_id=?",
            "comments": "SELECT c.* FROM pm_comments c JOIN pm_tasks t ON t.task_id=c.task_id WHERE t.project_id=?",
            "attachments": "SELECT a.* FROM pm_attachments a JOIN pm_tasks t ON t.task_id=a.task_id WHERE t.project_id=?",
            "time_entries": "SELECT e.* FROM pm_time_entries e JOIN pm_tasks t ON t.task_id=e.task_id WHERE t.project_id=?",
            "custom_values": "SELECT v.* FROM pm_custom_values v JOIN pm_tasks t ON t.task_id=v.task_id WHERE t.project_id=?",
        }
        result: dict[str, list[dict]] = {}
        with self._connect() as connection:
            for name, (table, column) in direct.items():
                result[name] = [dict(row) for row in connection.execute(f"SELECT * FROM {table} WHERE {column}=?", (project_id,))]
            for name, sql in related.items():
                result[name] = [dict(row) for row in connection.execute(sql, (project_id,))]
        return result

    def _resolve_project_media(self, links: tuple[dict, ...], library_database: Path | None) -> tuple[dict, ...]:
        if not links:
            return ()
        details = {str(row["asset_public_id"]): dict(row) for row in links}
        if library_database is None or not Path(library_database).is_file():
            return tuple(details.values())
        ids = tuple(details)
        with sqlite3.connect(library_database) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                f"""SELECT la.asset_public_id,la.asset_type media_type,la.original_filename,
                           la.title,la.description,la.mime_type,f.normalized_path source_path
                    FROM library_assets la LEFT JOIN file_instances f ON f.public_id=la.primary_file_public_id
                    WHERE la.asset_public_id IN ({','.join('?' for _ in ids)})""",
                ids,
            ).fetchall()
        for row in rows:
            asset_id = str(row["asset_public_id"])
            details[asset_id].update(dict(row))
        return tuple(details[asset_id] for asset_id in ids)

    def export_csv(self, project_id: str, destination: Path) -> Path:
        import csv

        rows = self.tasks(project_id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(TaskSummary.__dataclass_fields__)
            for row in rows:
                writer.writerow(tuple(getattr(row, field) for field in TaskSummary.__dataclass_fields__))
        return destination

    def export_xlsx(self, project_id: str, destination: Path) -> Path:
        """Write a dependency-free Office Open XML task workbook."""
        fields = tuple(TaskSummary.__dataclass_fields__)
        rows = [fields, *(tuple(getattr(task, field) for field in fields) for task in self.tasks(project_id))]

        def cell(column: int, row: int, value: object) -> str:
            name = ""
            number = column + 1
            while number:
                number, remainder = divmod(number - 1, 26)
                name = chr(65 + remainder) + name
            coordinate = f"{name}{row}"
            if isinstance(value, bool):
                return f'<c r="{coordinate}" t="b"><v>{int(value)}</v></c>'
            if isinstance(value, (int, float)):
                return f'<c r="{coordinate}"><v>{value}</v></c>'
            return (
                f'<c r="{coordinate}" t="inlineStr"><is><t>'
                f"{escape(str(value))}</t></is></c>"
            )

        sheet_rows = "".join(
            f'<row r="{row_number}">'
            + "".join(cell(column, row_number, value) for column, value in enumerate(row))
            + "</row>"
            for row_number, row in enumerate(rows, start=1)
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as workbook:
            workbook.writestr(
                "[Content_Types].xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                "</Types>",
            )
            workbook.writestr(
                "_rels/.rels",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                "</Relationships>",
            )
            workbook.writestr(
                "xl/workbook.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="Tasks" sheetId="1" r:id="rId1"/></sheets></workbook>',
            )
            workbook.writestr(
                "xl/_rels/workbook.xml.rels",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                "</Relationships>",
            )
            workbook.writestr(
                "xl/worksheets/sheet1.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f"<sheetData>{sheet_rows}</sheetData></worksheet>",
            )
        return destination

    def report_html(self, project_id: str) -> str:
        project = next((item for item in self.projects() if item.project_id == project_id), None)
        if project is None:
            raise KeyError(project_id)
        health = self.dashboard(project_id)
        task_rows = "".join(
            "<tr>"
            f"<td>{escape(task.title)}</td><td>{escape(task.owner_id)}</td>"
            f"<td>{escape(task.status_name)}</td><td>{escape(task.priority)}</td>"
            f"<td>{escape(task.due_date)}</td><td>{task.estimate_hours:g}</td>"
            f"<td>{task.actual_hours:g}</td><td>{task.progress}%</td>"
            "</tr>"
            for task in self.tasks(project_id)
        )
        return (
            "<html><body>"
            f"<h1>{escape(project.name)}</h1><p>Status: {escape(project.status)} · "
            f"Period: {escape(project.start_date)} to {escape(project.due_date)}</p>"
            f"<p>{health['completion_percent']}% complete · {health['overdue']} overdue · "
            f"{health['blocked']} blocked · {health['actual_hours']} actual hours</p>"
            "<table border='1' cellspacing='0' cellpadding='4'><thead><tr>"
            "<th>Task</th><th>Owner</th><th>Status</th><th>Priority</th><th>Due</th>"
            "<th>Estimated hours</th><th>Actual hours</th><th>Progress</th>"
            f"</tr></thead><tbody>{task_rows}</tbody></table></body></html>"
        )

    def client_portal_snapshot(self, project_id: str) -> dict[str, object]:
        project = next((item for item in self.projects() if item.project_id == project_id), None)
        if project is None:
            raise KeyError(project_id)
        tasks = self.tasks(project_id)
        return {
            "project": {
                "name": project.name, "status": project.status,
                "start_date": project.start_date, "due_date": project.due_date,
            },
            "health": self.dashboard(project_id),
            "milestones": [
                {"title": item.title, "due_date": item.due_date,
                 "status": item.status_name, "progress": item.progress}
                for item in tasks if item.milestone
            ],
        }

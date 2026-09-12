"""Managed PostgreSQL Capacity persistence for the Project Management service.

This adapter extends the governed managed Project service with the same schedule,
absence, organisational-obligation and aggregate workload semantics used by the
SQLite/desktop Project Management service. Browser/API authorization remains outside
this persistence adapter; private HR records are never returned by ``workload``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from natureai_next.server.postgres_project_management import (
    PostgresProjectManagementService,
    _id,
    _now_us,
    _validate_date,
)


class PostgresCapacityProjectManagementService(PostgresProjectManagementService):
    """Add managed Capacity persistence without changing Project domain ownership."""

    def __init__(self, connect) -> None:
        super().__init__(connect)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    ("fieldora_project_capacity_schema_v1",),
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS hr_schedule_templates(
                        template_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT NOT NULL DEFAULT '',
                        cycle_weeks INTEGER NOT NULL DEFAULT 1 CHECK(cycle_weeks IN(1,2)),
                        weekly_hours_odd DOUBLE PRECISION NOT NULL DEFAULT 40,
                        weekly_hours_even DOUBLE PRECISION NOT NULL DEFAULT 40,
                        active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_by TEXT NOT NULL,
                        created_at_us BIGINT NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS hr_schedule_periods(
                        period_id TEXT PRIMARY KEY,
                        template_id TEXT NOT NULL REFERENCES hr_schedule_templates(template_id)
                            ON DELETE CASCADE,
                        week_parity INTEGER NOT NULL DEFAULT 0 CHECK(week_parity IN(0,1,2)),
                        weekday INTEGER NOT NULL CHECK(weekday BETWEEN 1 AND 7),
                        start_time TEXT NOT NULL,
                        end_time TEXT NOT NULL,
                        UNIQUE(template_id,week_parity,weekday,start_time,end_time)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS hr_user_schedules(
                        assignment_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        template_id TEXT NOT NULL REFERENCES hr_schedule_templates(template_id),
                        effective_from TEXT NOT NULL,
                        effective_until TEXT NOT NULL DEFAULT '',
                        reference_week TEXT NOT NULL,
                        created_by TEXT NOT NULL,
                        created_at_us BIGINT NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS hr_absences(
                        absence_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        start_at TEXT NOT NULL,
                        end_at TEXT NOT NULL,
                        absence_type TEXT NOT NULL,
                        privacy_level TEXT NOT NULL DEFAULT 'private',
                        status TEXT NOT NULL DEFAULT 'approved',
                        note TEXT NOT NULL DEFAULT '',
                        created_by TEXT NOT NULL,
                        created_at_us BIGINT NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS hr_organisational_obligations(
                        obligation_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        start_at TEXT NOT NULL,
                        end_at TEXT NOT NULL,
                        obligation_type TEXT NOT NULL,
                        title TEXT NOT NULL,
                        note TEXT NOT NULL DEFAULT '',
                        created_by TEXT NOT NULL,
                        created_at_us BIGINT NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS hr_capacity_activity(
                        activity_id BIGSERIAL PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        actor_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        record_id TEXT NOT NULL,
                        created_at_us BIGINT NOT NULL
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_hr_capacity_activity_user_pg "
                    "ON hr_capacity_activity(user_id,created_at_us)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_hr_user_schedules_user_pg "
                    "ON hr_user_schedules(user_id,effective_from,effective_until)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_hr_absences_user_time_pg "
                    "ON hr_absences(user_id,start_at,end_at)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_hr_obligations_user_time_pg "
                    "ON hr_organisational_obligations(user_id,start_at,end_at)"
                )
        self.ensure_default_schedule_templates()

    @staticmethod
    def _capacity_event(
        cursor, user_id: str, actor_id: str, event_type: str, record_id: str
    ) -> None:
        cursor.execute(
            """
            INSERT INTO hr_capacity_activity(user_id,actor_id,event_type,record_id,created_at_us)
            VALUES(%s,%s,%s,%s,%s)
            """,
            (user_id, actor_id, event_type, record_id, _now_us()),
        )

    @staticmethod
    def _parse_iso_datetime(value: str) -> datetime:
        text = str(value).strip().replace(" ", "T")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    def ensure_default_schedule_templates(self, *, actor_id: str = "system") -> None:
        now = _now_us()
        defaults = (
            ("40-hours", "40 hours", 1, 40.0, 40.0),
            ("36-hours", "36 hours", 1, 36.0, 36.0),
            ("32-hours", "32 hours", 1, 32.0, 32.0),
            ("40-32-alternating", "Odd week 40 / even week 32", 2, 40.0, 32.0),
            ("32-40-alternating", "Odd week 32 / even week 40", 2, 32.0, 40.0),
        )
        with self._connect() as connection:
            with connection.cursor() as cursor:
                for template_id, name, cycle, odd, even in defaults:
                    cursor.execute(
                        """
                        INSERT INTO hr_schedule_templates(
                            template_id,name,description,cycle_weeks,weekly_hours_odd,
                            weekly_hours_even,active,created_by,created_at_us
                        ) VALUES(%s,%s,%s,%s,%s,%s,TRUE,%s,%s)
                        ON CONFLICT(template_id) DO NOTHING
                        """,
                        (
                            template_id,
                            name,
                            "Default work-schedule template",
                            cycle,
                            odd,
                            even,
                            actor_id,
                            now,
                        ),
                    )
                    periods = ((1, odd), (2, even)) if cycle == 2 else ((0, odd),)
                    for parity, hours in periods:
                        daily = float(hours) / 5.0
                        end_minutes = int(round((8.0 + daily) * 60))
                        end_time = f"{end_minutes // 60:02d}:{end_minutes % 60:02d}"
                        for weekday in range(1, 6):
                            cursor.execute(
                                """
                                INSERT INTO hr_schedule_periods(
                                    period_id,template_id,week_parity,weekday,start_time,end_time
                                ) VALUES(%s,%s,%s,%s,'08:00',%s)
                                ON CONFLICT(template_id,week_parity,weekday,start_time,end_time)
                                DO NOTHING
                                """,
                                (_id(), template_id, parity, weekday, end_time),
                            )

    def schedule_templates(self) -> tuple[dict[str, Any], ...]:
        self.ensure_default_schedule_templates()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT template_id,name,description,cycle_weeks,weekly_hours_odd,
                           weekly_hours_even,active,created_by,created_at_us
                    FROM hr_schedule_templates WHERE active=TRUE ORDER BY name
                    """
                )
                rows = cursor.fetchall()
        keys = (
            "template_id",
            "name",
            "description",
            "cycle_weeks",
            "weekly_hours_odd",
            "weekly_hours_even",
            "active",
            "created_by",
            "created_at_us",
        )
        return tuple(dict(zip(keys, row, strict=True)) for row in rows)

    def project_members(self, project_id: str) -> tuple[dict[str, str], ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT user_id,role FROM pm_project_members "
                    "WHERE project_id=%s ORDER BY user_id",
                    (project_id,),
                )
                rows = cursor.fetchall()
        return tuple({"user_id": str(row[0]), "role": str(row[1])} for row in rows)

    def assign_work_schedule(
        self,
        user_id: str,
        template_id: str,
        effective_from: str,
        *,
        effective_until: str = "",
        reference_week: str = "",
        actor_id: str,
    ) -> str:
        if not user_id.strip():
            raise ValueError("schedule user is required")
        _validate_date(effective_from, "schedule effective date")
        if effective_until:
            _validate_date(effective_until, "schedule end date")
            if effective_until < effective_from:
                raise ValueError("schedule end date cannot be before its effective date")
        reference_week = reference_week or effective_from
        _validate_date(reference_week, "reference week")
        assignment_id = _id()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM hr_schedule_templates WHERE template_id=%s AND active=TRUE",
                    (template_id,),
                )
                if cursor.fetchone() is None:
                    raise ValueError("unknown schedule template")
                cursor.execute(
                    """
                    INSERT INTO hr_user_schedules(
                        assignment_id,user_id,template_id,effective_from,effective_until,
                        reference_week,created_by,created_at_us
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        assignment_id,
                        user_id.strip(),
                        template_id,
                        effective_from,
                        effective_until,
                        reference_week,
                        actor_id,
                        _now_us(),
                    ),
                )
                self._capacity_event(
                    cursor, user_id.strip(), actor_id, "schedule.assigned", assignment_id
                )
        return assignment_id

    def add_absence(
        self,
        user_id: str,
        start_at: str,
        end_at: str,
        absence_type: str,
        *,
        privacy_level: str = "private",
        status: str = "approved",
        note: str = "",
        actor_id: str,
    ) -> str:
        start = self._parse_iso_datetime(start_at)
        end = self._parse_iso_datetime(end_at)
        if end <= start:
            raise ValueError("absence end must be after start")
        absence_id = _id()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO hr_absences(
                        absence_id,user_id,start_at,end_at,absence_type,privacy_level,status,
                        note,created_by,created_at_us
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        absence_id,
                        user_id.strip(),
                        start.isoformat(),
                        end.isoformat(),
                        absence_type,
                        privacy_level,
                        status,
                        note.strip(),
                        actor_id,
                        _now_us(),
                    ),
                )
                self._capacity_event(
                    cursor, user_id.strip(), actor_id, "absence.registered", absence_id
                )
        return absence_id

    def add_organisational_obligation(
        self,
        user_id: str,
        start_at: str,
        end_at: str,
        obligation_type: str,
        title: str,
        *,
        note: str = "",
        actor_id: str,
    ) -> str:
        start = self._parse_iso_datetime(start_at)
        end = self._parse_iso_datetime(end_at)
        if end <= start:
            raise ValueError("obligation end must be after start")
        obligation_id = _id()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO hr_organisational_obligations(
                        obligation_id,user_id,start_at,end_at,obligation_type,title,note,
                        created_by,created_at_us
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        obligation_id,
                        user_id.strip(),
                        start.isoformat(),
                        end.isoformat(),
                        obligation_type,
                        title.strip(),
                        note.strip(),
                        actor_id,
                        _now_us(),
                    ),
                )
                self._capacity_event(
                    cursor,
                    user_id.strip(),
                    actor_id,
                    "obligation.created",
                    obligation_id,
                )
        return obligation_id

    def _schedule_for(self, cursor, user_id: str, on_date: date):
        cursor.execute(
            """
            SELECT us.template_id,us.reference_week,t.cycle_weeks
            FROM hr_user_schedules us
            JOIN hr_schedule_templates t ON t.template_id=us.template_id
            WHERE us.user_id=%s AND us.effective_from<=%s
              AND (us.effective_until='' OR us.effective_until>=%s)
              AND t.active=TRUE
            ORDER BY us.effective_from DESC,us.created_at_us DESC
            LIMIT 1
            """,
            (user_id, on_date.isoformat(), on_date.isoformat()),
        )
        return cursor.fetchone()

    @staticmethod
    def _merged_overlap_hours(rows, start: datetime, end: datetime) -> float:
        intervals: list[tuple[datetime, datetime]] = []
        for row in rows:
            left = max(start, PostgresCapacityProjectManagementService._parse_iso_datetime(row[0]))
            right = min(end, PostgresCapacityProjectManagementService._parse_iso_datetime(row[1]))
            if right > left:
                intervals.append((left, right))
        intervals.sort()
        merged: list[tuple[datetime, datetime]] = []
        for left, right in intervals:
            if merged and left <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], right))
            else:
                merged.append((left, right))
        return sum((right - left).total_seconds() / 3600 for left, right in merged)

    def capacity_summary(
        self,
        user_id: str,
        start_at: str,
        end_at: str,
        *,
        project_id: str | None = None,
    ) -> dict[str, float]:
        start = self._parse_iso_datetime(start_at)
        end = self._parse_iso_datetime(end_at)
        if end <= start:
            raise ValueError("capacity range end must be after start")
        self.ensure_default_schedule_templates()
        scheduled = 0.0
        with self._connect() as connection:
            with connection.cursor() as cursor:
                day = start.date()
                while day <= end.date():
                    schedule = self._schedule_for(cursor, user_id, day)
                    if schedule:
                        template_id, reference_week, cycle_weeks = schedule
                        parity = 0
                        if int(cycle_weeks) == 2:
                            reference = date.fromisoformat(str(reference_week))
                            parity = 1 if ((day - reference).days // 7) % 2 == 0 else 2
                        cursor.execute(
                            """
                            SELECT start_time,end_time FROM hr_schedule_periods
                            WHERE template_id=%s AND weekday=%s AND week_parity IN(0,%s)
                            """,
                            (template_id, day.isoweekday(), parity),
                        )
                        for period in cursor.fetchall():
                            period_start = datetime.fromisoformat(
                                f"{day.isoformat()}T{period[0]}"
                            ).replace(tzinfo=start.tzinfo)
                            period_end = datetime.fromisoformat(
                                f"{day.isoformat()}T{period[1]}"
                            ).replace(tzinfo=start.tzinfo)
                            scheduled += max(
                                0.0,
                                (
                                    min(period_end, end) - max(period_start, start)
                                ).total_seconds()
                                / 3600,
                            )
                    day += timedelta(days=1)

                cursor.execute(
                    "SELECT start_at,end_at FROM hr_absences "
                    "WHERE user_id=%s AND end_at>%s AND start_at<%s",
                    (user_id, start.isoformat(), end.isoformat()),
                )
                unavailable = self._merged_overlap_hours(cursor.fetchall(), start, end)
                cursor.execute(
                    "SELECT start_at,end_at FROM hr_organisational_obligations "
                    "WHERE user_id=%s AND end_at>%s AND start_at<%s",
                    (user_id, start.isoformat(), end.isoformat()),
                )
                organisational = self._merged_overlap_hours(cursor.fetchall(), start, end)
                cursor.execute(
                    """
                    SELECT project_id,hours_per_week,allocation_percent
                    FROM hr_project_allocations
                    WHERE user_id=%s AND status='active' AND start_date<=%s
                      AND (end_date='' OR end_date>=%s)
                    """,
                    (user_id, end.date().isoformat(), start.date().isoformat()),
                )
                allocations = cursor.fetchall()

        net = max(0.0, scheduled - unavailable - organisational)
        weeks = max((end - start).total_seconds() / 604800, 1 / 7)
        allocation_hours = sum(
            (float(row[1]) if float(row[1]) else net * float(row[2]) / 100.0) * weeks
            for row in allocations
            if project_id is None or str(row[0]) == project_id
        )
        return {
            "scheduled_hours": round(scheduled, 2),
            "absence_hours": round(unavailable, 2),
            "organisational_hours": round(organisational, 2),
            "net_capacity_hours": round(net, 2),
            "allocated_hours": round(allocation_hours, 2),
            "remaining_hours": round(net - allocation_hours, 2),
        }

    def workload(self, project_id: str) -> tuple[dict[str, Any], ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT m.user_id,m.role,COUNT(t.task_id),
                           COALESCE(
                               SUM(CASE WHEN s.category!='done' THEN t.estimate_hours ELSE 0 END),
                               0
                           ),
                           COALESCE(SUM(t.realized_hours),0)
                    FROM pm_project_members m
                    LEFT JOIN pm_tasks t
                      ON t.project_id=m.project_id AND t.owner_id=m.user_id
                    LEFT JOIN pm_statuses s ON s.status_id=t.status_id
                    WHERE m.project_id=%s
                    GROUP BY m.user_id,m.role
                    ORDER BY 4 DESC,m.user_id
                    """,
                    (project_id,),
                )
                rows = cursor.fetchall()
        today = datetime.now(UTC)
        end = today + timedelta(days=7)
        result = []
        for row in rows:
            summary = self.capacity_summary(
                str(row[0]), today.isoformat(), end.isoformat(), project_id=project_id
            )
            result.append(
                {
                    "user_id": str(row[0]),
                    "role": str(row[1]),
                    "task_count": int(row[2]),
                    "open_estimate_hours": round(float(row[3]), 2),
                    "actual_hours": round(float(row[4]), 2),
                    **summary,
                }
            )
        return tuple(result)

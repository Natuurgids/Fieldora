"""Durable tenant quotas, rate limits, and usage accounting."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class QuotaDecision:
    allowed: bool
    metric: str
    used: int
    limit: int | None
    remaining: int | None
    resets_at_epoch: int


class TenantGovernance(Protocol):
    def consume(
        self,
        organization_id: str,
        metric: str,
        amount: int = 1,
        *,
        now_epoch: int | None = None,
    ) -> QuotaDecision: ...


def costed_usage_report(
    usage: tuple[dict[str, int | str], ...],
    unit_costs: dict[str, str],
) -> dict[str, object]:
    items = []
    total = Decimal("0")
    for row in usage:
        metric = str(row["metric"])
        amount = int(row["amount"])
        try:
            unit_cost = Decimal(unit_costs.get(metric, "0"))
        except InvalidOperation as exc:
            raise ValueError(f"invalid unit cost for {metric}") from exc
        if not unit_cost.is_finite() or unit_cost < 0:
            raise ValueError(f"invalid unit cost for {metric}")
        cost = unit_cost * amount
        total += cost
        items.append(
            {
                **row,
                "unit_cost": format(unit_cost, "f"),
                "cost": format(cost, "f"),
            }
        )
    return {"items": items, "total_cost": format(total, "f")}


class SqliteTenantGovernance:
    """Transactional standalone reference for the production governance contract."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._ensure()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _ensure(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tenant_quotas(
                    organization_id TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    limit_value INTEGER NOT NULL CHECK(limit_value >= 0),
                    period_seconds INTEGER NOT NULL CHECK(period_seconds > 0),
                    revision INTEGER NOT NULL CHECK(revision > 0),
                    PRIMARY KEY(organization_id, metric)
                );
                CREATE TABLE IF NOT EXISTS tenant_usage(
                    organization_id TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    period_start_epoch INTEGER NOT NULL,
                    period_seconds INTEGER NOT NULL CHECK(period_seconds > 0),
                    amount INTEGER NOT NULL CHECK(amount >= 0),
                    PRIMARY KEY(organization_id, metric, period_start_epoch)
                );
                CREATE TABLE IF NOT EXISTS tenant_usage_ledger(
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    organization_id TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    amount INTEGER NOT NULL CHECK(amount >= 0),
                    occurred_at_epoch INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tenant_usage_ledger_scope
                    ON tenant_usage_ledger(organization_id, occurred_at_epoch);
                """
            )

    def set_quota(
        self,
        organization_id: str,
        metric: str,
        limit: int,
        period_seconds: int,
        *,
        expected_revision: int | None = None,
    ) -> int:
        if not organization_id.strip() or not metric.strip():
            raise ValueError("organization and metric are required")
        if limit < 0 or period_seconds <= 0:
            raise ValueError("quota values are invalid")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT revision FROM tenant_quotas WHERE organization_id=? AND metric=?",
                (organization_id, metric),
            ).fetchone()
            current = 0 if row is None else int(row["revision"])
            if expected_revision is not None and current != expected_revision:
                connection.rollback()
                raise ValueError("revision_conflict")
            revision = current + 1
            connection.execute(
                """
                INSERT INTO tenant_quotas(
                    organization_id,metric,limit_value,period_seconds,revision
                ) VALUES(?,?,?,?,?)
                ON CONFLICT(organization_id,metric) DO UPDATE SET
                    limit_value=excluded.limit_value,
                    period_seconds=excluded.period_seconds,
                    revision=excluded.revision
                """,
                (organization_id, metric, limit, period_seconds, revision),
            )
            connection.commit()
        return revision

    def consume(
        self,
        organization_id: str,
        metric: str,
        amount: int = 1,
        *,
        now_epoch: int | None = None,
    ) -> QuotaDecision:
        if amount < 0:
            raise ValueError("usage amount cannot be negative")
        now = int(time.time()) if now_epoch is None else now_epoch
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            quota = connection.execute(
                """
                SELECT limit_value,period_seconds FROM tenant_quotas
                WHERE organization_id=? AND metric=?
                """,
                (organization_id, metric),
            ).fetchone()
            if quota is None:
                connection.execute(
                    """
                    INSERT INTO tenant_usage_ledger(
                        organization_id,metric,amount,occurred_at_epoch
                    ) VALUES(?,?,?,?)
                    """,
                    (organization_id, metric, amount, now),
                )
                connection.commit()
                return QuotaDecision(True, metric, amount, None, None, now)
            limit = int(quota["limit_value"])
            period = int(quota["period_seconds"])
            start = now - (now % period)
            row = connection.execute(
                """
                SELECT amount FROM tenant_usage
                WHERE organization_id=? AND metric=? AND period_start_epoch=?
                """,
                (organization_id, metric, start),
            ).fetchone()
            used = 0 if row is None else int(row["amount"])
            proposed = used + amount
            if proposed > limit:
                connection.rollback()
                return QuotaDecision(
                    False, metric, used, limit, max(0, limit - used), start + period
                )
            connection.execute(
                """
                INSERT INTO tenant_usage(
                    organization_id,metric,period_start_epoch,period_seconds,amount
                ) VALUES(?,?,?,?,?)
                ON CONFLICT(organization_id,metric,period_start_epoch)
                DO UPDATE SET amount=excluded.amount
                """,
                (organization_id, metric, start, period, proposed),
            )
            connection.execute(
                """
                INSERT INTO tenant_usage_ledger(
                    organization_id,metric,amount,occurred_at_epoch
                ) VALUES(?,?,?,?)
                """,
                (organization_id, metric, amount, now),
            )
            connection.commit()
            return QuotaDecision(
                True, metric, proposed, limit, max(0, limit - proposed), start + period
            )

    def usage_report(
        self, organization_id: str, start_epoch: int, end_epoch: int
    ) -> tuple[dict[str, int | str], ...]:
        if end_epoch <= start_epoch:
            raise ValueError("usage report range is invalid")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT metric,SUM(amount) AS total FROM tenant_usage_ledger
                WHERE organization_id=? AND occurred_at_epoch>=? AND occurred_at_epoch<?
                GROUP BY metric ORDER BY metric
                """,
                (organization_id, start_epoch, end_epoch),
            ).fetchall()
        return tuple(
            {"organization_id": organization_id, "metric": str(row["metric"]), "amount": int(row["total"])}
            for row in rows
        )


class PostgresTenantGovernance:
    """Shared quota and usage repository for redundant API nodes."""

    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tenant_quotas(
                        organization_id TEXT NOT NULL,
                        metric TEXT NOT NULL,
                        limit_value BIGINT NOT NULL CHECK(limit_value >= 0),
                        period_seconds BIGINT NOT NULL CHECK(period_seconds > 0),
                        revision BIGINT NOT NULL CHECK(revision > 0),
                        PRIMARY KEY(organization_id,metric)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tenant_usage(
                        organization_id TEXT NOT NULL,
                        metric TEXT NOT NULL,
                        period_start_epoch BIGINT NOT NULL,
                        period_seconds BIGINT NOT NULL CHECK(period_seconds > 0),
                        amount BIGINT NOT NULL CHECK(amount >= 0),
                        PRIMARY KEY(organization_id,metric,period_start_epoch)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tenant_usage_ledger(
                        sequence BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                        organization_id TEXT NOT NULL,
                        metric TEXT NOT NULL,
                        amount BIGINT NOT NULL CHECK(amount >= 0),
                        occurred_at_epoch BIGINT NOT NULL
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_tenant_usage_ledger_scope_pg "
                    "ON tenant_usage_ledger(organization_id,occurred_at_epoch)"
                )

    def set_quota(
        self,
        organization_id: str,
        metric: str,
        limit: int,
        period_seconds: int,
        *,
        expected_revision: int | None = None,
    ) -> int:
        if not organization_id.strip() or not metric.strip():
            raise ValueError("organization and metric are required")
        if limit < 0 or period_seconds <= 0:
            raise ValueError("quota values are invalid")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT revision FROM tenant_quotas
                    WHERE organization_id=%s AND metric=%s FOR UPDATE
                    """,
                    (organization_id, metric),
                )
                row = cursor.fetchone()
                current = 0 if row is None else int(row[0])
                if expected_revision is not None and current != expected_revision:
                    raise ValueError("revision_conflict")
                revision = current + 1
                cursor.execute(
                    """
                    INSERT INTO tenant_quotas(
                        organization_id,metric,limit_value,period_seconds,revision
                    ) VALUES(%s,%s,%s,%s,%s)
                    ON CONFLICT(organization_id,metric) DO UPDATE SET
                        limit_value=excluded.limit_value,
                        period_seconds=excluded.period_seconds,
                        revision=excluded.revision
                    """,
                    (organization_id, metric, limit, period_seconds, revision),
                )
        return revision

    def consume(
        self,
        organization_id: str,
        metric: str,
        amount: int = 1,
        *,
        now_epoch: int | None = None,
    ) -> QuotaDecision:
        if amount < 0:
            raise ValueError("usage amount cannot be negative")
        now = int(time.time()) if now_epoch is None else now_epoch
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT limit_value,period_seconds FROM tenant_quotas
                    WHERE organization_id=%s AND metric=%s
                    """,
                    (organization_id, metric),
                )
                quota = cursor.fetchone()
                if quota is None:
                    cursor.execute(
                        """
                        INSERT INTO tenant_usage_ledger(
                            organization_id,metric,amount,occurred_at_epoch
                        ) VALUES(%s,%s,%s,%s)
                        """,
                        (organization_id, metric, amount, now),
                    )
                    return QuotaDecision(True, metric, amount, None, None, now)
                limit, period = int(quota[0]), int(quota[1])
                start = now - (now % period)
                cursor.execute(
                    """
                    INSERT INTO tenant_usage(
                        organization_id,metric,period_start_epoch,period_seconds,amount
                    ) VALUES(%s,%s,%s,%s,0)
                    ON CONFLICT(organization_id,metric,period_start_epoch) DO NOTHING
                    """,
                    (organization_id, metric, start, period),
                )
                cursor.execute(
                    """
                    SELECT amount FROM tenant_usage
                    WHERE organization_id=%s AND metric=%s AND period_start_epoch=%s
                    FOR UPDATE
                    """,
                    (organization_id, metric, start),
                )
                used = int(cursor.fetchone()[0])
                proposed = used + amount
                if proposed > limit:
                    return QuotaDecision(
                        False, metric, used, limit, max(0, limit - used), start + period
                    )
                cursor.execute(
                    """
                    UPDATE tenant_usage SET amount=%s
                    WHERE organization_id=%s AND metric=%s AND period_start_epoch=%s
                    """,
                    (proposed, organization_id, metric, start),
                )
                cursor.execute(
                    """
                    INSERT INTO tenant_usage_ledger(
                        organization_id,metric,amount,occurred_at_epoch
                    ) VALUES(%s,%s,%s,%s)
                    """,
                    (organization_id, metric, amount, now),
                )
        return QuotaDecision(
            True, metric, proposed, limit, max(0, limit - proposed), start + period
        )

    def usage_report(
        self, organization_id: str, start_epoch: int, end_epoch: int
    ) -> tuple[dict[str, int | str], ...]:
        if end_epoch <= start_epoch:
            raise ValueError("usage report range is invalid")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT metric,SUM(amount) FROM tenant_usage_ledger
                    WHERE organization_id=%s AND occurred_at_epoch>=%s
                      AND occurred_at_epoch<%s
                    GROUP BY metric ORDER BY metric
                    """,
                    (organization_id, start_epoch, end_epoch),
                )
                rows = cursor.fetchall()
        return tuple(
            {
                "organization_id": organization_id,
                "metric": str(row[0]),
                "amount": int(row[1]),
            }
            for row in rows
        )

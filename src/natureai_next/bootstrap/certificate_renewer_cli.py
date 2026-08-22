"""Long-lived certificate renewal controller for enrolled Fieldora services."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from natureai_next.server.operator_control import PostgresOperatorRepository, ServiceState
from natureai_next.server.service_trust import ServiceTrustAuthority


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fieldora-certificate-renewer")
    parser.add_argument("--authority-root", type=Path, required=True)
    parser.add_argument("--postgres-dsn-file", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--interval-seconds", type=float, default=3600.0)
    parser.add_argument("--renew-before-hours", type=float, default=48.0)
    parser.add_argument("--lifetime-hours", type=int, default=168)
    parser.add_argument("--once", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 60 <= args.interval_seconds <= 86_400:
        raise SystemExit("renewal interval must be between 60 seconds and 24 hours")
    if not 1 <= args.renew_before_hours <= args.lifetime_hours:
        raise SystemExit("renew-before window must be within the certificate lifetime")
    configuration = json.loads(args.config.read_text(encoding="utf-8"))
    services = configuration.get("services")
    if not isinstance(services, list) or not services:
        raise SystemExit("renewal configuration requires a non-empty services list")
    repository, dsn = _repository(args.postgres_dsn_file)
    authority = ServiceTrustAuthority(args.authority_root)

    while True:
        _renew_cycle(
            authority,
            repository,
            dsn,
            services,
            renew_before_hours=args.renew_before_hours,
            lifetime_hours=args.lifetime_hours,
        )
        if args.once:
            return 0
        time.sleep(args.interval_seconds)


def _renew_cycle(
    authority: ServiceTrustAuthority,
    repository: PostgresOperatorRepository,
    postgres_dsn: str,
    services: list[object],
    *,
    renew_before_hours: float,
    lifetime_hours: int,
) -> None:
    threshold = datetime.now(UTC) + timedelta(hours=renew_before_hours)
    reload_postgres = False
    for raw in services:
        if not isinstance(raw, dict):
            raise ValueError("service renewal entry must be an object")
        service_id = _required(raw, "service_id")
        organization_id = _required(raw, "organization_id")
        common_name = _required(raw, "common_name")
        certificate = Path(_required(raw, "certificate"))
        private_key = Path(_required(raw, "private_key"))
        record = repository.service(service_id)
        if record is None:
            raise PermissionError(f"renewal target is not enrolled: {service_id}")
        state = ServiceState(record.state)
        if state in {ServiceState.STOPPED, ServiceState.REVOKED}:
            continue

        current = authority.inspect(certificate)
        expires = datetime.fromisoformat(current.not_after_utc)
        renewed = False
        if expires <= threshold:
            current = authority.issue(
                service_id=service_id,
                organization_id=organization_id,
                common_name=common_name,
                certificate_path=certificate,
                private_key_path=private_key,
                dns_names=tuple(_strings(raw.get("dns_names", []))),
                ip_addresses=tuple(_strings(raw.get("ip_addresses", []))),
                lifetime_hours=lifetime_hours,
                reuse_private_key=True,
            )
            renewed = True
            reload_postgres = reload_postgres or bool(raw.get("reload_postgres", False))

        repository.heartbeat(
            service_id,
            certificate_serial=current.serial_number,
            certificate_not_after_epoch=int(
                datetime.fromisoformat(current.not_after_utc).timestamp()
            ),
        )
        if renewed:
            print(
                json.dumps(
                    {
                        "event": "certificate_renewed",
                        "service_id": service_id,
                        "serial_number": current.serial_number,
                        "not_after_utc": current.not_after_utc,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
    if reload_postgres:
        _reload_postgres(postgres_dsn)


def _repository(dsn_file: Path) -> tuple[PostgresOperatorRepository, str]:
    if not dsn_file.is_file() or dsn_file.stat().st_size > 16_384:
        raise SystemExit("PostgreSQL operator DSN file is invalid")
    dsn = dsn_file.read_text(encoding="utf-8").strip()
    if not dsn:
        raise SystemExit("PostgreSQL operator DSN file is empty")
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("certificate renewal requires server-postgresql") from exc
    return PostgresOperatorRepository(lambda: psycopg.connect(dsn, connect_timeout=10)), dsn


def _reload_postgres(dsn: str) -> None:
    import psycopg

    with psycopg.connect(dsn, connect_timeout=10, autocommit=True) as connection:
        result = connection.execute("SELECT pg_reload_conf()").fetchone()
    if result is None or result[0] is not True:
        raise RuntimeError("PostgreSQL did not acknowledge TLS configuration reload")
    print(json.dumps({"event": "postgres_tls_reloaded"}), flush=True)


def _required(item: dict[Any, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"renewal service field is required: {key}")
    return value.strip()


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("renewal DNS/IP values must be arrays")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("renewal DNS/IP entries must be non-empty strings")
        result.append(item.strip())
    return result


if __name__ == "__main__":
    raise SystemExit(main())

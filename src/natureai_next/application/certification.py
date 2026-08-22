"""Read-only Version 2 platform certification over existing Aperture services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from time import perf_counter

from natureai_next.application.health import HealthSeverity, LibraryHealthService
from natureai_next.domain.subsystems import SubsystemState


class CertificationStatus(StrEnum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class CertificationFinding:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class CertificationSection:
    key: str
    title: str
    status: CertificationStatus
    duration_ms: int
    findings: tuple[CertificationFinding, ...] = ()


@dataclass(frozen=True, slots=True)
class PlatformCertificationReport:
    generated_at_utc: str
    sections: tuple[CertificationSection, ...]

    @property
    def overall_status(self) -> CertificationStatus:
        if any(section.status is CertificationStatus.FAIL for section in self.sections):
            return CertificationStatus.FAIL
        if any(section.status is CertificationStatus.WARNING for section in self.sections):
            return CertificationStatus.WARNING
        return CertificationStatus.PASS

    @property
    def warning_count(self) -> int:
        return sum(section.status is CertificationStatus.WARNING for section in self.sections)

    @property
    def failure_count(self) -> int:
        return sum(section.status is CertificationStatus.FAIL for section in self.sections)


class PlatformCertificationService:
    """Certify approved platform boundaries without changing application state."""

    def __init__(
        self,
        *,
        health_service: LibraryHealthService,
        subsystem_registry,
        capability_registry,
    ) -> None:
        self._health = health_service
        self._subsystems = subsystem_registry
        self._capabilities = capability_registry

    def run(self) -> PlatformCertificationReport:
        health_report = self._health.assess(full_database_check=False)
        sections = (
            self._core_section(health_report),
            self._ai_section(health_report),
            self._subsystem_section("taxonomy.reference", "Taxonomy Reference"),
            self._subsystem_section("maps.offline", "Offline Maps"),
            self._knowledge_section(),
            self._maintenance_section(health_report),
        )
        return PlatformCertificationReport(
            generated_at_utc=datetime.now(UTC).isoformat(),
            sections=sections,
        )

    def _core_section(self, report) -> CertificationSection:
        started = perf_counter()
        keys = {"database", "manifest", "directories", "storage"}
        checks = tuple(check for check in report.checks if check.key in keys)
        return self._from_health_checks("core", "Core Library", checks, started)

    def _ai_section(self, report) -> CertificationSection:
        started = perf_counter()
        checks = tuple(check for check in report.checks if check.key == "analyses")
        if not checks:
            return CertificationSection(
                "ai",
                "AI Enrichment",
                CertificationStatus.WARNING,
                self._elapsed(started),
                (
                    CertificationFinding(
                        "check.missing", "AI enrichment integrity check is not registered."
                    ),
                ),
            )
        return self._from_health_checks("ai", "AI Enrichment", checks, started)

    def _subsystem_section(self, key: str, title: str) -> CertificationSection:
        started = perf_counter()
        findings: list[CertificationFinding] = []
        try:
            descriptor = self._subsystems.descriptor(key)
            status = self._subsystems.status(key, run_integrity_check=True)
            capability = self._capabilities.status(key)
        except Exception as exc:
            return CertificationSection(
                key,
                title,
                CertificationStatus.FAIL,
                self._elapsed(started),
                (CertificationFinding("registry.error", str(exc)),),
            )
        if status.state is SubsystemState.UNAVAILABLE or status.state is SubsystemState.UNHEALTHY:
            findings.append(
                CertificationFinding("database.unhealthy", status.message or status.state.value)
            )
            result = (
                CertificationStatus.WARNING if descriptor.optional else CertificationStatus.FAIL
            )
        elif status.database_path.exists() and status.schema_version != descriptor.schema_version:
            findings.append(
                CertificationFinding(
                    "schema.mismatch",
                    f"Installed schema {status.schema_version}; expected {descriptor.schema_version}.",
                )
            )
            result = CertificationStatus.WARNING
        else:
            result = CertificationStatus.PASS
        findings.append(CertificationFinding("capability.state", capability.state.value))
        if not status.database_path.exists():
            findings.append(
                CertificationFinding(
                    "database.inactive",
                    "Optional database is not installed; core operation is unaffected.",
                )
            )
        return CertificationSection(key, title, result, self._elapsed(started), tuple(findings))

    def _knowledge_section(self) -> CertificationSection:
        started = perf_counter()
        required = {"taxonomy.reference", "maps.offline"}
        registered = set(self._capabilities.keys())
        missing = sorted(required - registered)
        if missing:
            return CertificationSection(
                "knowledge",
                "Knowledge Engine",
                CertificationStatus.FAIL,
                self._elapsed(started),
                (CertificationFinding("capability.missing", ", ".join(missing)),),
            )
        return CertificationSection(
            "knowledge",
            "Knowledge Engine",
            CertificationStatus.PASS,
            self._elapsed(started),
            (
                CertificationFinding(
                    "capability.registry",
                    "Required cross-domain capabilities are registered lazily.",
                ),
            ),
        )

    def _maintenance_section(self, report) -> CertificationSection:
        started = perf_counter()
        keys = {"jobs", "temporary", "derived", "backups"}
        checks = tuple(check for check in report.checks if check.key in keys)
        return self._from_health_checks("maintenance", "Maintenance Center", checks, started)

    def _from_health_checks(
        self, key: str, title: str, checks, started: float
    ) -> CertificationSection:
        if any(check.severity is HealthSeverity.ERROR for check in checks):
            status = CertificationStatus.FAIL
        elif any(check.severity is HealthSeverity.WARNING for check in checks):
            status = CertificationStatus.WARNING
        else:
            status = CertificationStatus.PASS
        findings = tuple(
            CertificationFinding(check.key, f"{check.title}: {check.summary}")
            for check in checks
            if check.severity is not HealthSeverity.OK
        )
        return CertificationSection(key, title, status, self._elapsed(started), findings)

    @staticmethod
    def _elapsed(started: float) -> int:
        return max(0, int((perf_counter() - started) * 1000))

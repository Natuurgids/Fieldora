"""Export, inspect, and atomically import portable Science projects."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from natureai_next import __version__
from natureai_next.application.science import ScienceSession, default_science_snapshot
from natureai_next.domain.science_packages import (
    ProjectCollisionPolicy,
    ProjectImportPlan,
    ProjectPackageSummary,
)
from natureai_next.infrastructure.exporting.science_packages import SciencePackageCodec


class PortableProjectService:
    def __init__(
        self, session: ScienceSession, codec: SciencePackageCodec | None = None
    ) -> None:
        self._session = session
        self._codec = codec or SciencePackageCodec()

    @staticmethod
    def _identity(collection: str, record: dict) -> str:
        if record.get("id"):
            return str(record["id"])
        if collection == "project_budgets":
            return str(record["project_id"])
        if collection == "dossier_whiteboards":
            return f"{record['dossier_id']}|{record['board_id']}"
        raise ValueError(f"portable {collection} record has no identity")

    def _project_records(
        self, project_id: str, *, include_library_references: bool
    ) -> dict[str, list[dict]]:
        data = self._session.data
        projects = [row for row in data["projects"] if row["id"] == project_id]
        if not projects:
            raise KeyError(project_id)
        dossiers = [
            deepcopy(row) for row in data["dossiers"]
            if row.get("project_id") == project_id or row["id"] == project_id
        ]
        dossier_ids = {row["id"] for row in dossiers}
        links = [
            deepcopy(row) for row in data["dossier_whiteboards"]
            if row["dossier_id"] in dossier_ids
        ]
        board_ids = {row["board_id"] for row in links}
        if not include_library_references:
            for dossier in dossiers:
                dossier["media_ids"] = []
        elements = [
            deepcopy(row) for row in data["whiteboard_elements"]
            if row["board_id"] in board_ids
            and (include_library_references or row.get("kind") != "library_ref")
        ]
        return {
            "projects": [deepcopy(projects[0])],
            "project_stages": [
                deepcopy(row) for row in data["project_stages"]
                if row["project_id"] == project_id
            ],
            "project_activities": [
                deepcopy(row) for row in data["project_activities"]
                if row["project_id"] == project_id
            ],
            "project_resources": [
                deepcopy(row) for row in data["project_resources"]
                if row["project_id"] == project_id
            ],
            "project_budgets": [
                deepcopy(row) for row in data["project_budgets"]
                if row["project_id"] == project_id
            ],
            "dossiers": dossiers,
            "whiteboards": [
                deepcopy(row) for row in data["whiteboards"] if row["id"] in board_ids
            ],
            "whiteboard_elements": elements,
            "dossier_whiteboards": links,
        }

    def export_project(
        self,
        project_id: str,
        destination: Path,
        *,
        include_library_references: bool,
    ) -> ProjectPackageSummary:
        records = self._project_records(
            project_id, include_library_references=include_library_references
        )
        project = records["projects"][0]
        library_references = sum(
            len(row.get("media_ids", [])) for row in records["dossiers"]
        ) + sum(
            row.get("kind") == "library_ref"
            for row in records["whiteboard_elements"]
        )
        record_count = sum(len(rows) for rows in records.values())
        manifest = {
            "created_at_utc": datetime.now(UTC).isoformat(),
            "producer": {"name": "Fieldora", "version": __version__},
            "project": {"id": project_id, "name": project.get("name", "")},
            "record_count": record_count,
            "library_reference_count": library_references,
            "includes_originals": False,
            "includes_library_references": include_library_references,
            "license": {"name": "Not specified", "attribution": ""},
            "redaction": {
                "original_media_excluded": True,
                "library_references_included": include_library_references,
            },
        }
        digest = self._codec.write(destination, manifest, records)
        return ProjectPackageSummary(
            project_id=project_id,
            project_name=str(project.get("name", "")),
            record_count=record_count,
            library_reference_count=library_references,
            includes_originals=False,
            package_sha256=digest,
        )

    def plan_import(
        self, source: Path, *, policy: ProjectCollisionPolicy
    ) -> ProjectImportPlan:
        manifest, records, digest = self._codec.read(source)
        allowed = set(default_science_snapshot()) - {"schema_version"}
        if set(records) - allowed:
            raise ValueError("portable project contains unknown Science collections")
        if any(not isinstance(rows, list) for rows in records.values()):
            raise ValueError("portable project collections must be lists")
        actual_count = sum(len(rows) for rows in records.values())
        if actual_count != int(manifest.get("record_count", -1)):
            raise ValueError("portable project record count does not match its manifest")
        projects = records.get("projects", [])
        project_manifest = manifest.get("project", {})
        if (
            len(projects) != 1
            or str(projects[0].get("id", "")) != str(project_manifest.get("id", ""))
        ):
            raise ValueError("portable project identity is inconsistent")
        if bool(manifest.get("includes_originals", False)):
            raise ValueError("this Fieldora version does not import original media packages")
        collisions: list[tuple[str, str]] = []
        for collection, incoming_rows in records.items():
            existing_ids = {
                self._identity(collection, row)
                for row in self._session.data.get(collection, [])
            }
            for row in incoming_rows:
                identity = self._identity(collection, row)
                if identity in existing_ids:
                    collisions.append((collection, identity))
        project = project_manifest
        summary = ProjectPackageSummary(
            project_id=str(project.get("id", "")),
            project_name=str(project.get("name", "")),
            record_count=int(manifest.get("record_count", 0)),
            library_reference_count=int(
                manifest.get("library_reference_count", 0)
            ),
            includes_originals=bool(manifest.get("includes_originals", False)),
            package_sha256=digest,
        )
        return ProjectImportPlan(summary, tuple(collisions), policy)

    def import_project(
        self, source: Path, *, policy: ProjectCollisionPolicy
    ) -> ProjectImportPlan:
        plan = self.plan_import(source, policy=policy)
        if not plan.can_apply:
            raise ValueError(
                f"portable project contains {len(plan.collisions)} collision(s)"
            )
        _manifest, records, _digest = self._codec.read(source)
        original = deepcopy(self._session.data)
        try:
            if policy is ProjectCollisionPolicy.REPLACE:
                self._remove_project_scope(plan.summary.project_id)
            for collection, incoming_rows in records.items():
                if collection not in self._session.data:
                    raise ValueError(f"unknown Science collection: {collection}")
                current = self._session.data[collection]
                current_by_id = {
                    self._identity(collection, row): row for row in current
                }
                for incoming in incoming_rows:
                    identity = self._identity(collection, incoming)
                    existing = current_by_id.get(identity)
                    if existing is not None:
                        if policy is ProjectCollisionPolicy.SKIP:
                            continue
                        current.remove(existing)
                    current.append(deepcopy(incoming))
            self._session.save()
        except BaseException:
            self._session.data.clear()
            self._session.data.update(original)
            raise
        return plan

    def _remove_project_scope(self, project_id: str) -> None:
        data = self._session.data
        dossier_ids = {
            row["id"] for row in data["dossiers"]
            if row.get("project_id") == project_id or row["id"] == project_id
        }
        board_ids = {
            row["board_id"] for row in data["dossier_whiteboards"]
            if row["dossier_id"] in dossier_ids
        }
        data["projects"][:] = [
            row for row in data["projects"] if row["id"] != project_id
        ]
        for collection in (
            "project_stages", "project_activities", "project_resources",
            "project_budgets",
        ):
            data[collection][:] = [
                row for row in data[collection]
                if row.get("project_id") != project_id
            ]
        data["dossiers"][:] = [
            row for row in data["dossiers"] if row["id"] not in dossier_ids
        ]
        data["dossier_whiteboards"][:] = [
            row for row in data["dossier_whiteboards"]
            if row["dossier_id"] not in dossier_ids
        ]
        still_linked = {row["board_id"] for row in data["dossier_whiteboards"]}
        removable = board_ids - still_linked
        data["whiteboards"][:] = [
            row for row in data["whiteboards"] if row["id"] not in removable
        ]
        data["whiteboard_elements"][:] = [
            row for row in data["whiteboard_elements"]
            if row["board_id"] not in removable
        ]

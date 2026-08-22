"""Administrative command-line boundary for local maintenance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from natureai_next.application.library_service import LibraryService
from natureai_next.infrastructure.diagnostics.system_services import (
    SystemClock,
    SystemUuidGenerator,
)
from natureai_next.infrastructure.library_lifecycle import SqliteLibraryLifecycleBackend


def _service() -> LibraryService:
    return LibraryService(
        SystemClock(),
        SystemUuidGenerator(),
        backend_factory=lambda clock, ids, settings: SqliteLibraryLifecycleBackend(
            clock, ids, settings
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="natureai-next-admin")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("library-create")
    create.add_argument("path", type=Path)
    create.add_argument("--name", required=True)
    create.add_argument("--locale", default="en")
    check = sub.add_parser("library-check")
    check.add_argument("path", type=Path)
    check.add_argument("--full", action="store_true")
    backup = sub.add_parser("library-backup")
    backup.add_argument("path", type=Path)
    backup.add_argument("destination", type=Path)
    models = sub.add_parser("ai-model-list")
    models.add_argument("path", type=Path)
    audit = sub.add_parser("ai-embedding-audit")
    audit.add_argument("path", type=Path)
    audit.add_argument("model_variant_id", type=int)
    audit.add_argument("preprocessing_identity")
    rebuild = sub.add_parser("ai-index-rebuild")
    rebuild.add_argument("path", type=Path)
    rebuild.add_argument("model_variant_id", type=int)
    rebuild.add_argument("preprocessing_identity")
    prompt_install = sub.add_parser("ai-prompt-install")
    prompt_install.add_argument("path", type=Path)
    prompt_install.add_argument("manifest", type=Path)
    prompt_install.add_argument("--public-id", required=True)
    prompt_install.add_argument("--activate", action="store_true")
    prompt_install.add_argument("--model-family")
    prompt_list = sub.add_parser("ai-prompt-list")
    prompt_list.add_argument("path", type=Path)
    prompt_list.add_argument("--identity")
    prompt_activate = sub.add_parser("ai-prompt-activate")
    prompt_activate.add_argument("path", type=Path)
    prompt_activate.add_argument("public_id")
    export = sub.add_parser("library-export-metadata")
    export.add_argument("path", type=Path)
    export.add_argument("destination", type=Path)
    export.add_argument("--format", choices=("json", "csv"), default="json")
    export.add_argument("--asset-id", action="append", dest="asset_ids")
    export.add_argument("--replace", action="store_true")
    export.add_argument("--no-provenance", action="store_true")
    original_export = sub.add_parser("library-export-originals")
    original_export.add_argument("path", type=Path)
    original_export.add_argument("destination", type=Path)
    original_export.add_argument("--asset-id", action="append", dest="asset_ids")
    original_export.add_argument("--template", default="{original_stem}-{asset_id}{original_ext}")
    original_export.add_argument(
        "--collision", choices=("fail", "replace", "suffix"), default="fail"
    )
    original_export.add_argument("--no-manifest", action="store_true")
    original_export.add_argument("--no-checksum-verification", action="store_true")
    derivative_export = sub.add_parser("library-export-derivatives")
    derivative_export.add_argument("path", type=Path)
    derivative_export.add_argument("destination", type=Path)
    derivative_export.add_argument("--asset-id", action="append", dest="asset_ids")
    derivative_export.add_argument("--format", choices=("jpeg", "png"), default="jpeg")
    derivative_export.add_argument("--max-width", type=int, default=2048)
    derivative_export.add_argument("--max-height", type=int, default=2048)
    derivative_export.add_argument("--quality", type=int, default=90)
    derivative_export.add_argument("--template", default="{original_stem}-{asset_id}")
    derivative_export.add_argument(
        "--collision", choices=("fail", "replace", "suffix"), default="fail"
    )
    derivative_export.add_argument("--no-xmp", action="store_true")
    derivative_export.add_argument("--no-manifest", action="store_true")
    args = parser.parse_args(argv)
    service = _service()
    if args.command == "library-create":
        opened = service.create(args.path, display_name=args.name, default_locale=args.locale)
        try:
            print(
                json.dumps(
                    {
                        "library_public_id": opened.manifest.library_public_id,
                        "path": str(opened.layout.root),
                    }
                )
            )
        finally:
            opened.close()
    elif args.command == "library-check":
        opened = service.open(args.path)
        try:
            report = opened.integrity(full=args.full)
            print(
                json.dumps(
                    {
                        "healthy": report.healthy,
                        "quick_check": report.quick_check,
                        "foreign_key_violations": report.foreign_key_violations,
                    }
                )
            )
            return 0 if report.healthy else 2
        finally:
            opened.close()
    elif args.command == "library-backup":
        opened = service.open(args.path)
        try:
            print(str(opened.backup_database(args.destination)))
        finally:
            opened.close()
    elif args.command == "ai-model-list":
        opened = service.open(args.path)
        try:
            connection = opened.connection_factory.connect(read_only=True)
            try:
                rows = connection.execute(
                    "SELECT p.model_identity,p.semantic_version,p.active,v.id,v.variant_identity,v.runtime,v.precision,v.preprocessing_identity FROM model_packages p JOIN model_variants v ON v.package_id=p.id ORDER BY p.model_identity,p.semantic_version,v.variant_identity"
                ).fetchall()
                print(json.dumps([dict(row) for row in rows], sort_keys=True))
            finally:
                connection.close()
        finally:
            opened.close()
    elif args.command == "ai-embedding-audit":
        from natureai_next.infrastructure.database.ai import SqliteAIRepository

        opened = service.open(args.path)
        try:
            checked, corrupt = SqliteAIRepository(opened.connection_factory).audit_embeddings(
                args.model_variant_id, args.preprocessing_identity
            )
            print(json.dumps({"checked": checked, "corrupt": corrupt}, sort_keys=True))
            return 0 if corrupt == 0 else 2
        finally:
            opened.close()
    elif args.command == "ai-prompt-install":
        import time

        from natureai_next.application.ai_review import PromptSetService
        from natureai_next.infrastructure.ai.prompts import (
            load_prompt_set,
            prompt_set_checksum,
            validate_prompt_set,
        )
        from natureai_next.infrastructure.database.ai_review import SqlitePromptSetStore

        opened = service.open(args.path)
        try:
            record = PromptSetService(
                SqlitePromptSetStore(opened.connection_factory),
                loader=load_prompt_set,
                checksum=prompt_set_checksum,
                validator=validate_prompt_set,
            ).install(
                args.manifest,
                public_id=args.public_id,
                now_us=time.time_ns() // 1000,
                activate=args.activate,
                model_family=args.model_family,
            )
            print(
                json.dumps(
                    {
                        "public_id": record.public_id,
                        "identity": record.identity,
                        "semantic_version": record.semantic_version,
                        "active": record.active,
                        "checksum": record.checksum,
                    },
                    sort_keys=True,
                )
            )
        finally:
            opened.close()
    elif args.command == "ai-prompt-list":
        from natureai_next.application.ai_review import PromptSetService
        from natureai_next.infrastructure.ai.prompts import (
            load_prompt_set,
            prompt_set_checksum,
            validate_prompt_set,
        )
        from natureai_next.infrastructure.database.ai_review import SqlitePromptSetStore

        opened = service.open(args.path)
        try:
            records = PromptSetService(
                SqlitePromptSetStore(opened.connection_factory),
                loader=load_prompt_set,
                checksum=prompt_set_checksum,
                validator=validate_prompt_set,
            ).list(args.identity)
            print(
                json.dumps(
                    [
                        {
                            "public_id": r.public_id,
                            "identity": r.identity,
                            "semantic_version": r.semantic_version,
                            "model_family": r.model_family,
                            "active": r.active,
                            "checksum": r.checksum,
                        }
                        for r in records
                    ],
                    sort_keys=True,
                )
            )
        finally:
            opened.close()
    elif args.command == "ai-prompt-activate":
        import time

        from natureai_next.application.ai_review import PromptSetService
        from natureai_next.infrastructure.ai.prompts import (
            load_prompt_set,
            prompt_set_checksum,
            validate_prompt_set,
        )
        from natureai_next.infrastructure.database.ai_review import SqlitePromptSetStore

        opened = service.open(args.path)
        try:
            record = PromptSetService(
                SqlitePromptSetStore(opened.connection_factory),
                loader=load_prompt_set,
                checksum=prompt_set_checksum,
                validator=validate_prompt_set,
            ).activate(args.public_id, now_us=time.time_ns() // 1000)
            print(
                json.dumps(
                    {
                        "public_id": record.public_id,
                        "identity": record.identity,
                        "semantic_version": record.semantic_version,
                        "active": record.active,
                    },
                    sort_keys=True,
                )
            )
        finally:
            opened.close()
    elif args.command == "library-export-derivatives":
        import time
        from uuid import uuid4

        from natureai_next.application.exporting import DerivativeExportService
        from natureai_next.domain.exporting import (
            CollisionPolicy,
            DerivativeExportPlan,
            DerivativeFormat,
            ExportSelection,
        )
        from natureai_next.infrastructure.database.exporting import SqliteExportCatalogReader
        from natureai_next.infrastructure.exporting.derivatives import LocalDerivativeExportWriter
        from natureai_next.infrastructure.imaging.pillow_adapter import PillowImageDecoder

        opened = service.open(args.path)
        try:
            selection = ExportSelection(
                tuple(args.asset_ids or ()), include_all_active=not bool(args.asset_ids)
            )
            plan = DerivativeExportPlan(
                str(uuid4()),
                args.destination,
                selection,
                DerivativeFormat(args.format),
                args.max_width,
                args.max_height,
                args.quality,
                args.template,
                CollisionPolicy(args.collision),
                not args.no_xmp,
                not args.no_manifest,
                time.time_ns() // 1000,
            )
            result = DerivativeExportService(
                SqliteExportCatalogReader(opened.connection_factory),
                LocalDerivativeExportWriter(PillowImageDecoder()),
            ).execute(plan)
            print(
                json.dumps(
                    {
                        "plan_public_id": result.plan_public_id,
                        "destination": str(result.destination_directory),
                        "asset_count": result.asset_count,
                        "bytes_written": result.bytes_written,
                        "manifest_path": None
                        if result.manifest_path is None
                        else str(result.manifest_path),
                        "manifest_sha256": result.manifest_sha256,
                    },
                    sort_keys=True,
                )
            )
        finally:
            opened.close()
    elif args.command == "library-export-originals":
        import time
        from uuid import uuid4

        from natureai_next.application.exporting import OriginalFileExportService
        from natureai_next.domain.exporting import (
            CollisionPolicy,
            ExportSelection,
            OriginalFileExportPlan,
        )
        from natureai_next.infrastructure.database.exporting import SqliteExportCatalogReader
        from natureai_next.infrastructure.exporting.files import LocalOriginalFileExportWriter

        opened = service.open(args.path)
        try:
            selection = ExportSelection(
                tuple(args.asset_ids or ()), include_all_active=not bool(args.asset_ids)
            )
            plan = OriginalFileExportPlan(
                str(uuid4()),
                args.destination,
                selection,
                args.template,
                CollisionPolicy(args.collision),
                not args.no_manifest,
                not args.no_checksum_verification,
                time.time_ns() // 1000,
            )
            result = OriginalFileExportService(
                SqliteExportCatalogReader(opened.connection_factory),
                LocalOriginalFileExportWriter(),
            ).execute(plan)
            print(
                json.dumps(
                    {
                        "plan_public_id": result.plan_public_id,
                        "destination": str(result.destination_directory),
                        "asset_count": result.asset_count,
                        "bytes_written": result.bytes_written,
                        "manifest_path": None
                        if result.manifest_path is None
                        else str(result.manifest_path),
                        "manifest_sha256": result.manifest_sha256,
                    },
                    sort_keys=True,
                )
            )
        finally:
            opened.close()
    elif args.command == "library-export-metadata":
        import time
        from uuid import uuid4

        from natureai_next.application.exporting import ExportService
        from natureai_next.domain.exporting import (
            CollisionPolicy,
            ExportFormat,
            ExportPlan,
            ExportSelection,
        )
        from natureai_next.infrastructure.database.exporting import SqliteExportCatalogReader
        from natureai_next.infrastructure.exporting.metadata import LocalMetadataExportWriter

        opened = service.open(args.path)
        try:
            selection = ExportSelection(
                tuple(args.asset_ids or ()), include_all_active=not bool(args.asset_ids)
            )
            plan = ExportPlan(
                str(uuid4()),
                args.destination,
                ExportFormat(args.format),
                selection,
                CollisionPolicy.REPLACE if args.replace else CollisionPolicy.FAIL,
                not args.no_provenance,
                time.time_ns() // 1000,
            )
            result = ExportService(
                SqliteExportCatalogReader(opened.connection_factory), LocalMetadataExportWriter()
            ).execute(plan)
            print(
                json.dumps(
                    {
                        "plan_public_id": result.plan_public_id,
                        "destination": str(result.destination),
                        "format": result.format,
                        "asset_count": result.asset_count,
                        "bytes_written": result.bytes_written,
                        "sha256": result.sha256,
                    },
                    sort_keys=True,
                )
            )
        finally:
            opened.close()
    elif args.command == "ai-index-rebuild":
        from natureai_next.application.ai_runtime import VectorIndexService
        from natureai_next.infrastructure.database.ai import SqliteAIRepository

        opened = service.open(args.path)
        try:
            from natureai_next.infrastructure.indexing.vector_store import LocalVectorIndexStore

            result = VectorIndexService(
                SqliteAIRepository(opened.connection_factory),
                opened.layout.vector_indexes,
                LocalVectorIndexStore(),
            ).rebuild(args.model_variant_id, args.preprocessing_identity)
            print(
                json.dumps(
                    {
                        "index_id": result.index_id,
                        "generation": result.generation,
                        "source_row_count": result.source_row_count,
                    },
                    sort_keys=True,
                )
            )
        finally:
            opened.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

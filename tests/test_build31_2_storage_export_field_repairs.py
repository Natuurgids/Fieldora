from pathlib import Path

from natureai_next.domain.export_packages import (
    ExportPackageAttachment,
    ExportPackagePlan,
    MissingOriginalPolicy,
)
from natureai_next.infrastructure.exporting.packages import LocalExportPackageBuilder


def test_portable_export_normalizes_qt_string_policy(tmp_path: Path) -> None:
    attachment = tmp_path / "records.json"
    attachment.write_text("{}", encoding="utf-8")
    destination = tmp_path / "portable"
    plan = ExportPackagePlan(
        public_id="plan-1",
        destination_directory=destination,
        attachments=(ExportPackageAttachment(attachment, "records/assets.json", "data"),),
        missing_original_policy="continue",  # Qt QVariant returns a plain string on Windows.
    )

    result = LocalExportPackageBuilder().build(plan)

    assert result.manifest_path.is_file()
    assert '"missing_original_policy": "continue"' in result.manifest_path.read_text(
        encoding="utf-8"
    )


def test_storage_manager_queues_verification_in_activity_center() -> None:
    source = Path("src/natureai_next/ui/qt/storage_manager.py").read_text(encoding="utf-8")
    assert 'kind="storage.verify"' in source
    assert "self._service.verify(" in source
    assert "progress=progress" in source
    assert "cancelled=cancelled" in source
    synchronous = 'results = self._service.verify(ids)'
    assert synchronous not in source

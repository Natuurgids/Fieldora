from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_map_date_filter_is_explicit_and_disabled_by_default() -> None:
    source = (ROOT / "src/natureai_next/ui/qt/maps.py").read_text(encoding="utf-8")

    assert 'QCheckBox("Filter observations by date")' in source
    assert "self._filter_dates.setChecked(False)" in source
    assert (
        "self._temporal_service_factory is not None and self._filter_dates.isChecked()"
        in source
    )


def test_model_install_progress_is_bounded_and_embedded() -> None:
    source = (ROOT / "src/natureai_next/ui/qt/model_manager.py").read_text(encoding="utf-8")

    assert "class _ModelInstallProgress(QFrame)" in source
    assert "self.setFixedHeight(104)" in source
    assert "text[:237] + \"…\"" in source
    assert "QProgressDialog" not in source
    assert "layout.addWidget(self._install_progress)" in source


def test_model_cancel_reaches_busy_worker_without_queued_worker_slot() -> None:
    source = (ROOT / "src/natureai_next/ui/qt/model_manager.py").read_text(encoding="utf-8")

    assert "progress.cancelled.connect(lambda: worker.cancel())" in source
    assert "progress.cancelled.connect(worker.cancel)" not in source


def test_media_worker_is_retained_and_model_worker_output_cannot_deadlock() -> None:
    media = (ROOT / "src/natureai_next/ui/qt/media_library.py").read_text(encoding="utf-8")
    models = (ROOT / "src/natureai_next/synthesis_core/optional_models.py").read_text(
        encoding="utf-8"
    )

    assert "self._worker = worker" in media
    assert "self._worker = None" in media
    assert 'log_path.open("w+"' in models
    assert "stderr=subprocess.STDOUT" in models
    assert "timeout_seconds=20 * 60" in models

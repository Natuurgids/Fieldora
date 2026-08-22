from pathlib import Path


def test_media_batch_service_is_parallel_and_tracks_each_file() -> None:
    source = Path(
        "src/natureai_next/application/enrichment_workspace.py"
    ).read_text(encoding="utf-8")
    assert "ThreadPoolExecutor(" in source
    assert "as_completed(futures)" in source
    assert "max_parallel: int = 4" in source
    assert "WorkspaceBatchRun" in source
    assert "item_states" in source


def test_each_media_library_opens_an_independent_batch_screen() -> None:
    media = Path("src/natureai_next/ui/qt/media_library.py").read_text(encoding="utf-8")
    photos = Path("src/natureai_next/ui/qt/library.py").read_text(encoding="utf-8")
    screen = Path(
        "src/natureai_next/ui/qt/capability_execution.py"
    ).read_text(encoding="utf-8")
    assert "CapabilityBatchProgressDialog(" in media
    assert "CapabilityBatchProgressDialog(" in photos
    assert "library_name=self._spec.title" in media
    assert "processing {len(items)} selected file(s) in parallel" in screen
    assert "Cancel remaining" in screen
    assert "self._run.item_states" in screen


def test_analysis_lifecycle_follows_library_workspace_switches() -> None:
    application = Path("src/natureai_next/ui/qt/application.py").read_text(
        encoding="utf-8"
    )
    media = Path("src/natureai_next/ui/qt/media_library.py").read_text(
        encoding="utf-8"
    )
    photo = Path("src/natureai_next/ui/qt/ai_review.py").read_text(
        encoding="utf-8"
    )
    assert "media_workspace.set_workspace_enabled(capability.enabled)" in application
    assert "self._ai_review_workspace.set_workspace_enabled(capability.enabled)" in application
    assert "self._library.set_workspace_enabled(capability.enabled)" in application
    assert "def set_workspace_enabled(self, enabled: bool)" in media
    assert "cancel_for_disabled_workspace" in media
    assert "def set_workspace_enabled(self, enabled: bool)" in photo
    assert "self.cancel_generation()" in photo

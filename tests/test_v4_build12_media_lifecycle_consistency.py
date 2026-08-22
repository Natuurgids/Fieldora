from natureai_next.application.source_lifecycle import (
    SourceRecord,
    SourceRemovalOptions,
    SourceState,
)
from natureai_next.application.source_lifecycle_ui import (
    SourceStateTone,
    present_source_state,
    preview_source_removal,
)


def record(state: SourceState) -> SourceRecord:
    return SourceRecord(
        source_id="source.test",
        kind="capability",
        display_name="Test source",
        version="1",
        state=state,
        licence="MIT",
        attribution="Test",
        checksum="abc",
    )


def test_all_registry_states_have_consistent_presentation() -> None:
    for state in SourceState:
        presentation = present_source_state(record(state))
        assert presentation.label
        assert presentation.explanation
        assert isinstance(presentation.tone, SourceStateTone)


def test_removed_and_download_required_sources_cannot_remove_files_again() -> None:
    assert not present_source_state(record(SourceState.REMOVED)).can_remove_files
    assert not present_source_state(record(SourceState.REQUIRES_DOWNLOAD)).can_remove_files


def test_inactive_offline_and_superseded_sources_can_be_activated() -> None:
    assert present_source_state(record(SourceState.INACTIVE)).can_activate
    assert present_source_state(record(SourceState.OFFLINE)).can_activate
    assert present_source_state(record(SourceState.SUPERSEDED)).can_activate


def test_removal_preview_preserves_accepted_by_default() -> None:
    preview = preview_source_removal(
        {"generated": 2, "pending_review": 3, "rejected": 4, "accepted": 5},
        SourceRemovalOptions(),
    )
    assert preview.pending_to_delete == 0
    assert preview.rejected_to_delete == 4
    assert preview.accepted_to_delete == 0
    assert preview.accepted_to_preserve == 5
    assert preview.reproducibility_warning
    assert "5 accepted record(s) preserved" in preview.summary()


def test_destructive_removal_preview_is_explicit() -> None:
    preview = preview_source_removal(
        {"pending_review": 3, "rejected": 4, "accepted": 5},
        SourceRemovalOptions(
            delete_pending_results=True,
            delete_rejected_results=True,
            delete_accepted_enrichment=True,
        ),
    )
    assert preview.total_to_delete == 12
    assert preview.accepted_to_preserve == 0


def test_media_workspace_exposes_bidirectional_playback_binding_contract() -> None:
    from pathlib import Path

    source = Path(__file__).parents[1] / "src/natureai_next/ui/qt/media_library.py"
    text = source.read_text(encoding="utf-8")
    assert "playback_seek_requested = Signal(str, float)" in text
    assert "visualization_time_selected.connect(" in text
    assert "self._enrichment_time_selected" in text
    assert "def set_playback_position(self, asset_id: str, seconds: float)" in text

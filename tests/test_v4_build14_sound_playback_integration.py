from pathlib import Path

from natureai_next.application.media_playback import TemporalPlaybackBinding

ROOT = Path(__file__).resolve().parents[1]


def test_temporal_binding_clamps_and_converts_positions() -> None:
    binding = TemporalPlaybackBinding()
    binding.load("sound-1", 5_000)
    assert binding.seek_seconds(2.25) == 2_250
    assert binding.update_position(3_125) == 3.125
    assert binding.seek_seconds(99) == 5_000
    assert binding.update_position(-50) == 0.0


def test_sound_workspace_resolves_original_file_and_owns_player() -> None:
    text = (ROOT / "src/natureai_next/ui/qt/media_library.py").read_text(encoding="utf-8")
    query = (ROOT / "src/natureai_next/application/media_queries.py").read_text(encoding="utf-8")
    assert "LEFT JOIN file_instances f ON f.public_id=a.primary_file_public_id" in query
    assert "class SoundPlaybackWidget" in text
    assert "QMediaPlayer" in text
    assert "QAudioOutput" in text
    assert "QUrl.fromLocalFile" in text


def test_canonical_temporal_selection_seeks_concrete_player() -> None:
    text = (ROOT / "src/natureai_next/ui/qt/media_library.py").read_text(encoding="utf-8")
    assert "self._sound_player.seek_seconds(value)" in text
    assert "self._sound_player.position_changed.connect(self._sound_position_changed)" in text
    assert "self.set_playback_position(self._sound_player.asset_id, seconds)" in text

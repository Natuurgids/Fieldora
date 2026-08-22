import math
import struct
import wave
from pathlib import Path

from natureai_next.application.audio_visualization import build_wav_spectrogram

ROOT = Path(__file__).resolve().parents[1]


def _write_tone(path: Path, *, sample_rate: int = 8000, seconds: float = 0.15) -> None:
    frames = []
    for index in range(int(sample_rate * seconds)):
        value = int(18000 * math.sin(2 * math.pi * 440 * index / sample_rate))
        frames.append(struct.pack("<h", value))
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(b"".join(frames))


def test_wav_spectrogram_is_bounded_and_normalized(tmp_path: Path) -> None:
    path = tmp_path / "tone.wav"
    _write_tone(path)
    data = build_wav_spectrogram(path, window_size=64, hop_size=32, maximum_frames=12)
    assert data.sample_rate_hz == 8000
    assert 0 < data.frame_count <= 12
    assert data.bin_count == 32
    assert data.duration_seconds > 0
    assert all(0.0 <= value <= 1.0 for row in data.magnitudes for value in row)


def test_sound_workspace_contains_spectrogram_canvas_and_overlay_contract() -> None:
    text = (ROOT / "src/natureai_next/ui/qt/media_library.py").read_text(encoding="utf-8")
    assert "class SoundSpectrogramCanvas" in text
    assert "build_wav_spectrogram" in text
    assert "set_overlay_scene" in text
    assert "time_selected" in text
    assert "set_playback_position" in text


def test_video_workspace_owns_concrete_player_and_canonical_sync() -> None:
    text = (ROOT / "src/natureai_next/ui/qt/media_library.py").read_text(encoding="utf-8")
    assert "class VideoPlaybackWidget" in text
    assert "QVideoWidget" in text
    assert "self._video_player.seek_seconds(value)" in text
    assert "self._video_player.position_changed.connect(self._video_position_changed)" in text
    assert "self._video_player.set_overlay_scene(scene)" in text

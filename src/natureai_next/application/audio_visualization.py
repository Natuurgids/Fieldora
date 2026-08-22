"""Offline audio visualization primitives independent of Qt and model plugins."""

from __future__ import annotations

import math
import struct
import wave
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SpectrogramData:
    """Normalized time-frequency magnitudes suitable for generic renderers."""

    sample_rate_hz: int
    duration_seconds: float
    frame_seconds: float
    frequency_bin_hz: float
    magnitudes: tuple[tuple[float, ...], ...]

    @property
    def frame_count(self) -> int:
        return len(self.magnitudes)

    @property
    def bin_count(self) -> int:
        return len(self.magnitudes[0]) if self.magnitudes else 0

    @property
    def maximum_frequency_hz(self) -> float:
        return self.bin_count * self.frequency_bin_hz


def build_wav_spectrogram(
    path: Path,
    *,
    window_size: int = 256,
    hop_size: int = 128,
    maximum_frames: int = 900,
) -> SpectrogramData:
    """Create a bounded mono spectrogram from an uncompressed PCM WAV file.

    The implementation intentionally uses the Python standard library so the
    Aperture desktop remains offline-first and does not require NumPy merely to
    display a diagnostic spectrogram. Long recordings are uniformly sampled to
    keep UI memory predictable.
    """

    source = Path(path)
    if window_size < 32 or window_size & (window_size - 1):
        raise ValueError("window_size must be a power of two and at least 32")
    if hop_size <= 0:
        raise ValueError("hop_size must be positive")
    if maximum_frames <= 0:
        raise ValueError("maximum_frames must be positive")

    with wave.open(str(source), "rb") as stream:
        channels = stream.getnchannels()
        sample_width = stream.getsampwidth()
        sample_rate = stream.getframerate()
        frame_total = stream.getnframes()
        compression = stream.getcomptype()
        if compression != "NONE":
            raise ValueError(f"unsupported WAV compression: {compression}")
        raw = stream.readframes(frame_total)

    samples = _decode_pcm_mono(raw, channels=channels, sample_width=sample_width)
    duration = frame_total / sample_rate if sample_rate else 0.0
    if not samples:
        return SpectrogramData(
            sample_rate, duration, hop_size / max(sample_rate, 1), sample_rate / window_size, ()
        )

    total_windows = max(1, 1 + max(0, len(samples) - window_size) // hop_size)
    stride = max(1, math.ceil(total_windows / maximum_frames))
    window = tuple(
        0.5 - 0.5 * math.cos((2.0 * math.pi * index) / (window_size - 1))
        for index in range(window_size)
    )
    bins = window_size // 2
    frames: list[tuple[float, ...]] = []
    peak = 1e-12

    for window_index in range(0, total_windows, stride):
        start = window_index * hop_size
        segment = samples[start : start + window_size]
        if len(segment) < window_size:
            segment = segment + (0.0,) * (window_size - len(segment))
        weighted = tuple(value * window[index] for index, value in enumerate(segment))
        magnitudes = tuple(_dft_magnitude(weighted, frequency_bin) for frequency_bin in range(bins))
        peak = max(peak, max(magnitudes, default=0.0))
        frames.append(magnitudes)

    floor_db = -80.0
    normalized: list[tuple[float, ...]] = []
    for frame in frames:
        row = []
        for magnitude in frame:
            db = 20.0 * math.log10(max(magnitude / peak, 1e-12))
            row.append(max(0.0, min(1.0, (db - floor_db) / -floor_db)))
        normalized.append(tuple(row))

    return SpectrogramData(
        sample_rate_hz=sample_rate,
        duration_seconds=duration,
        frame_seconds=(hop_size * stride) / max(sample_rate, 1),
        frequency_bin_hz=sample_rate / window_size,
        magnitudes=tuple(normalized),
    )


def _decode_pcm_mono(raw: bytes, *, channels: int, sample_width: int) -> tuple[float, ...]:
    if channels <= 0:
        raise ValueError("WAV channel count must be positive")
    if sample_width not in {1, 2, 3, 4}:
        raise ValueError(f"unsupported PCM sample width: {sample_width}")
    frame_width = channels * sample_width
    if frame_width <= 0 or len(raw) % frame_width:
        raise ValueError("invalid PCM frame data")

    maximum = float(1 << (sample_width * 8 - 1))
    output: list[float] = []
    for frame_start in range(0, len(raw), frame_width):
        values = []
        for channel in range(channels):
            offset = frame_start + channel * sample_width
            encoded = raw[offset : offset + sample_width]
            if sample_width == 1:
                value = encoded[0] - 128
            elif sample_width == 2:
                value = struct.unpack_from("<h", encoded)[0]
            elif sample_width == 3:
                extended = encoded + (b"\xff" if encoded[2] & 0x80 else b"\x00")
                value = int.from_bytes(extended, "little", signed=True)
            else:
                value = struct.unpack_from("<i", encoded)[0]
            values.append(value / maximum)
        output.append(sum(values) / channels)
    return tuple(output)


def _dft_magnitude(samples: tuple[float, ...], frequency_bin: int) -> float:
    count = len(samples)
    real = 0.0
    imaginary = 0.0
    for index, value in enumerate(samples):
        angle = (2.0 * math.pi * frequency_bin * index) / count
        real += value * math.cos(angle)
        imaginary -= value * math.sin(angle)
    return math.hypot(real, imaginary)

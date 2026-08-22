"""Device-independent window geometry helpers for mixed-DPI desktops."""

from __future__ import annotations


def adaptive_minimum_size(available_width: int, available_height: int) -> tuple[int, int]:
    """Return a usable minimum that never exceeds the current screen."""
    width = max(1, available_width - 32)
    height = max(1, available_height - 32)
    return min(900, width), min(600, height)


def fit_window_geometry(
    geometry: tuple[int, int, int, int],
    available: tuple[int, int, int, int],
    *,
    margin: int = 8,
) -> tuple[int, int, int, int]:
    """Fit restored logical geometry inside one screen's available rectangle."""
    x, y, width, height = geometry
    left, top, available_width, available_height = available
    usable_width = max(1, available_width - margin * 2)
    usable_height = max(1, available_height - margin * 2)
    minimum_width, minimum_height = adaptive_minimum_size(
        available_width, available_height
    )
    width = min(max(width, minimum_width), usable_width)
    height = min(max(height, minimum_height), usable_height)
    x = min(max(x, left + margin), left + available_width - margin - width)
    y = min(max(y, top + margin), top + available_height - margin - height)
    return x, y, width, height

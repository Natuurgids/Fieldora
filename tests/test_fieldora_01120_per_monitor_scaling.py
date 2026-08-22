from pathlib import Path

from natureai_next.ui.display_scaling import adaptive_minimum_size, fit_window_geometry


def test_external_monitor_geometry_is_fitted_to_scaled_laptop_screen() -> None:
    # Restored external-monitor geometry is expressed in Qt logical pixels.
    fitted = fit_window_geometry((1500, 80, 1900, 1000), (0, 0, 1093, 576))
    x, y, width, height = fitted
    assert (width, height) == (1077, 560)
    assert x >= 0 and y >= 0
    assert x + width <= 1093
    assert y + height <= 576


def test_adaptive_minimum_never_forces_window_beyond_available_screen() -> None:
    assert adaptive_minimum_size(1093, 576) == (900, 544)
    assert adaptive_minimum_size(720, 480) == (688, 448)


def test_offscreen_restored_window_returns_to_destination_screen() -> None:
    assert fit_window_geometry((3000, -900, 1000, 700), (100, 50, 1280, 720)) == (
        372,
        58,
        1000,
        700,
    )


def test_main_window_tracks_screen_and_dpi_changes_after_show() -> None:
    source = Path("src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    assert "handle.screenChanged.connect(self._screen_changed)" in source
    assert "screen.logicalDotsPerInchChanged.connect(" in source
    assert "screen.availableGeometryChanged.connect(" in source
    assert "window.bind_per_monitor_display_scaling()" in source
    assert "self.setMinimumSize(QSize(1100, 700))" not in source

from pathlib import Path


def test_library_page_does_not_use_uninitialized_admin_button_list() -> None:
    source = Path("src/natureai_next/ui/qt/v5_desktop.py").read_text(encoding="utf-8")
    library = source[source.index("class Library(Page):"):source.index("class Observations(Page):")]
    assert "self.admin_buttons.append(add)" not in library


def test_normal_windows_launcher_shows_gui_windows() -> None:
    installer = Path("scripts/install_windows.ps1").read_text(encoding="utf-8")
    assert 'shell.Run Chr(34) & "$escapedExecutable" & Chr(34), 1, False' in installer
    assert 'shell.Run Chr(34) & "$escapedExecutable" & Chr(34), 0, False' not in installer


def test_debug_and_normal_launch_use_same_desktop_executable() -> None:
    installer = Path("scripts/install_windows.ps1").read_text(encoding="utf-8")
    assert r"$apertureExecutable = Join-Path $EnvironmentPath 'Scripts\fieldora.exe'" in installer
    assert "$executable = '__DESKTOP_EXECUTABLE__'" in installer

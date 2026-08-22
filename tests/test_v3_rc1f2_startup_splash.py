from pathlib import Path


def test_release_version_and_splash_wiring() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    cli = (root / "src/natureai_next/bootstrap/cli.py").read_text(encoding="utf-8")
    app = (root / "src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    splash = (root / "src/natureai_next/ui/qt/startup_splash.py").read_text(encoding="utf-8")

    assert 'version = "5.4.0"' in pyproject
    assert 'version=f"Fieldora {__version__}"' in cli
    assert 'startup.mark("startup-splash-visible")' in cli
    assert "startup_splash.finish(window)" in app
    assert "startup_splash.hide()" in app
    assert "login = LocalLoginDialog(profile_path)" in app
    assert "startup_splash.show()" in app
    assert 'resources" / "fieldora.ico"' in splash
    assert '"FIELDORA"' in splash
    assert "Offline biodiversity research & scientific projects" in splash
    assert "app.processEvents()" in splash

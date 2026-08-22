from pathlib import Path


def test_science_gui_verifier_releases_qt_objects_before_temp_cleanup() -> None:
    source = Path("scripts/verify_install.py").read_text(encoding="utf-8")
    close = source.index("workspace.close()")
    delete = source.index("workspace.deleteLater()", close)
    deferred = source.index("QEvent.Type.DeferredDelete", delete)
    process = source.index("application.processEvents()", deferred)
    release = source.index("del workspace", process)
    collect = source.index("gc.collect()", release)
    assert close < delete < deferred < process < release < collect

from pathlib import Path


def test_trash_manager_uses_real_file_instance_schema_and_loads_lazily() -> None:
    source = Path('src/natureai_next/ui/qt/trash_manager.py').read_text(encoding='utf-8')
    assert 'fi.original_name' not in source
    assert 'fi.normalized_path' in source
    assert 'self._loaded_once = False' in source
    assert 'def showEvent' in source
    assert 'except sqlite3.Error as exc' in source


def test_trash_manager_does_not_refresh_during_construction() -> None:
    source = Path('src/natureai_next/ui/qt/trash_manager.py').read_text(encoding='utf-8')
    constructor = source.split('def __init__', 1)[1].split('def showEvent', 1)[0]
    assert 'self.refresh()' not in constructor

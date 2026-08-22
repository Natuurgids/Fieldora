from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB = (ROOT / "src/natureai_next/ui/qt/knowledge_base.py").read_text(encoding="utf-8")
UOW = (ROOT / "src/natureai_next/infrastructure/database/unit_of_work.py").read_text(
    encoding="utf-8"
)


def test_knowledge_view_queries_outside_qt_event_thread():
    assert "class KnowledgeDataView(QWidget)" in KB
    assert "class _KnowledgeQueryWorker(QObject)" in KB
    assert "worker.moveToThread(thread)" in KB
    assert "thread.started.connect(worker.run)" in KB
    assert "PRAGMA query_only=ON" in KB
    assert "PRAGMA busy_timeout=75" in KB


def test_knowledge_table_uses_model_instead_of_per_cell_widgets():
    assert "class _KnowledgeTableModel(QAbstractTableModel)" in KB
    assert "self._table = QTableView()" in KB
    assert "self._model.replace_rows" in KB
    assert "QTableWidgetItem" not in KB
    assert "QHeaderView.ResizeMode.ResizeToContents" not in KB


def test_knowledge_refreshes_are_coalesced():
    assert "self._query_active" in KB
    assert "self._refresh_pending" in KB
    assert "if self._query_active:" in KB


def test_database_writer_locks_are_scoped_per_database_path():
    assert "class _DatabaseWriteLocks" in UOW
    assert "for_path(factory.database_path)" in UOW
    assert "_write_lock=threading.RLock()" not in UOW

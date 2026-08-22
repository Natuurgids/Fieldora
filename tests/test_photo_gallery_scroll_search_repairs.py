from natureai_next.application.search import QuickSearchService
from natureai_next.domain.search import Predicate, PredicateOperator, StructuredQuery
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.search import SqliteSearchAdapter
from natureai_next.infrastructure.database.search import compile_query
from natureai_next.ports.search import SearchRequest


def test_filename_search_matches_terms_across_directory_and_basename() -> None:
    compiled = compile_query(
        StructuredQuery(Predicate("filename", PredicateOperator.CONTAINS, "Holiday finch"))
    )

    assert compiled.sql.count("f.normalized_path") == 2
    assert compiled.sql.count("f.import_source_path") == 2
    assert compiled.parameters == (
        "%holiday%", "%holiday%", "%finch%", "%finch%"
    )


def test_everywhere_search_uses_path_terms_as_a_fallback() -> None:
    compiled = compile_query(
        StructuredQuery(Predicate("text", PredicateOperator.CONTAINS, "Holiday finch"))
    )

    assert compiled.sql.count("f.normalized_path") == 2
    assert compiled.sql.count("f.import_source_path") == 2
    assert compiled.parameters[1:] == (
        "%holiday%", "%holiday%", "%finch%", "%finch%"
    )


def test_filename_scope_builds_a_filename_predicate() -> None:
    service = QuickSearchService(object())
    query = service.build_query(text="photos robin", scope="filename")

    assert query.root == Predicate("filename", PredicateOperator.CONTAINS, "photos robin")


def test_filename_search_filters_by_original_directory_and_basename(tmp_path) -> None:
    factory = SqliteConnectionFactory(tmp_path / "catalog.sqlite3")
    connection = factory.connect()
    connection.executescript(
        """
        CREATE TABLE assets (
            id INTEGER PRIMARY KEY,
            public_id TEXT NOT NULL,
            revision INTEGER NOT NULL,
            title TEXT,
            rating INTEGER,
            color_label TEXT,
            pick_state TEXT,
            capture_time_utc_us INTEGER,
            lifecycle_state TEXT NOT NULL,
            primary_file_instance_id INTEGER
        );
        CREATE TABLE file_instances (
            id INTEGER PRIMARY KEY,
            public_id TEXT NOT NULL,
            normalized_path TEXT,
            import_source_path TEXT
        );
        CREATE TABLE image_properties (
            asset_id INTEGER PRIMARY KEY,
            pixel_width INTEGER,
            pixel_height INTEGER
        );
        CREATE TABLE asset_locations (asset_id INTEGER, location_id INTEGER, role TEXT);
        CREATE TABLE locations (id INTEGER PRIMARY KEY);
        CREATE TABLE derivative_cache_entries (
            source_file_instance_id INTEGER,
            derivative_kind TEXT,
            state TEXT,
            created_at_us INTEGER,
            relative_path TEXT
        );
        INSERT INTO file_instances VALUES
            (10, 'file-person', 'D:\\managed\\a1.jpg',
             'D:\\Photos\\20160123 korstmos\\Personen\\DSC_0119.jpg'),
            (20, 'file-bird', 'D:\\managed\\a2.jpg',
             'D:\\Photos\\Birds\\IMG_0001.jpg');
        INSERT INTO assets VALUES
            (1, 'asset-person', 1, NULL, NULL, NULL, NULL, NULL, 'active', 10),
            (2, 'asset-bird', 1, NULL, NULL, NULL, NULL, NULL, 'active', 20);
        """
    )
    connection.close()
    adapter = SqliteSearchAdapter(factory)

    for fragment in ("Personen", "dsc", r"\Personen\DSC"):
        page = adapter.search(
            SearchRequest(
                StructuredQuery(
                    Predicate("filename", PredicateOperator.CONTAINS, fragment)
                )
            )
        )
        assert tuple(row.public_id for row in page.rows) == ("asset-person",)
        assert page.total_count == 1


def test_gallery_scroll_loading_is_debounced_and_directional() -> None:
    from pathlib import Path

    source = (
        Path(__file__).parents[1]
        / "src/natureai_next/ui/qt/library.py"
    ).read_text(encoding="utf-8")

    assert "self._scroll_idle_timer.setInterval(300)" in source
    assert "gallery_scrollbar.sliderReleased.connect(self._scrolling_stopped)" in source
    assert "first_row - 4" in source
    assert "last_row + 1 + 12" in source
    assert "first_row - 12" in source
    assert "last_row + 1 + 4" in source
    assert "available_slots" in source
    assert "if self._scrolling:" in source


def test_search_replaces_latest_import_and_supersedes_inflight_pages() -> None:
    from pathlib import Path

    source = (
        Path(__file__).parents[1]
        / "src/natureai_next/ui/qt/library.py"
    ).read_text(encoding="utf-8")

    apply_search = source[source.index("def _apply_search"):source.index("def _run_views_operation")]
    assert "self._import_public_ids = ()" in apply_search
    assert 'self._view_selector.findData("library")' in apply_search
    assert "scope == self._search_scope_value" in apply_search
    refresh = source[source.index("def refresh(self)"):source.index("def load_more(self)")]
    assert "if self._refreshing:" not in refresh

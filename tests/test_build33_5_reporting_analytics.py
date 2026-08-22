from pathlib import Path

from natureai_next.application.reporting_analytics import AnalyticsFilters, ReportingAnalyticsReader
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.migrations import CORE_MIGRATIONS, MigrationRunner


def test_reporting_analytics_empty_library(tmp_path: Path) -> None:
    database = tmp_path / "library.sqlite3"
    factory = SqliteConnectionFactory(database)
    connection = factory.connect()
    MigrationRunner(CORE_MIGRATIONS, "test").apply(connection)
    connection.close()

    reader = ReportingAnalyticsReader(database)
    assert reader.filter_options() == {"countries": (), "regions": (), "groups": ()}
    snapshot = reader.snapshot(AnalyticsFilters())
    assert snapshot.asset_count == 0
    assert snapshot.observation_count == 0
    assert snapshot.media_assets == ()

"""Core database migrations."""

from natureai_next.infrastructure.database.migrations.core import MigrationError, MigrationRunner
from natureai_next.infrastructure.database.migrations.v001_initial import MIGRATION as V001
from natureai_next.infrastructure.database.migrations.v002_jobs_media import MIGRATION as V002
from natureai_next.infrastructure.database.migrations.v003_import_catalog import MIGRATION as V003
from natureai_next.infrastructure.database.migrations.v004_search_collections_geo import (
    MIGRATION as V004,
)
from natureai_next.infrastructure.database.migrations.v005_taxonomy import MIGRATION as V005
from natureai_next.infrastructure.database.migrations.v006_ai_foundation import MIGRATION as V006
from natureai_next.infrastructure.database.migrations.v007_ai_runtime import MIGRATION as V007
from natureai_next.infrastructure.database.migrations.v008_ai_review import MIGRATION as V008
from natureai_next.infrastructure.database.migrations.v009_ai_generation import MIGRATION as V009
from natureai_next.infrastructure.database.migrations.v010_taxonomy_embedding_lifecycle import (
    MIGRATION as V010,
)
from natureai_next.infrastructure.database.migrations.v011_resumable_exports import (
    MIGRATION as V011,
)
from natureai_next.infrastructure.database.migrations.v012_resumable_derivative_exports import (
    MIGRATION as V012,
)
from natureai_next.infrastructure.database.migrations.v013_regional_knowledge import (
    MIGRATION as V013,
)
from natureai_next.infrastructure.database.migrations.v014_observation_intelligence import (
    MIGRATION as V014,
)
from natureai_next.infrastructure.database.migrations.v015_ecological_context import (
    MIGRATION as V015,
)
from natureai_next.infrastructure.database.migrations.v016_import_provenance import (
    MIGRATION as V016,
)
from natureai_next.infrastructure.database.migrations.v017_observation_context import (
    MIGRATION as V017,
)
from natureai_next.infrastructure.database.migrations.v018_spatial_longitudinal import (
    MIGRATION as V018,
)
from natureai_next.infrastructure.database.migrations.v019_temporal_movement import (
    MIGRATION as V019,
)
from natureai_next.infrastructure.database.migrations.v020_asset_analyses import MIGRATION as V020
from natureai_next.infrastructure.database.migrations.v021_asset_removal import MIGRATION as V021
from natureai_next.infrastructure.database.migrations.v022_external_taxonomy_enrichment import (
    MIGRATION as V022,
)
from natureai_next.infrastructure.database.migrations.v023_canonical_enrichment_history import (
    MIGRATION as V023,
)
from natureai_next.infrastructure.database.migrations.v024_user_and_relationship_enrichments import (
    MIGRATION as V024,
)
from natureai_next.infrastructure.database.migrations.v025_library_integrations import (
    MIGRATION as V025,
)
from natureai_next.infrastructure.database.migrations.v026_spatial_asset_hierarchy import MIGRATION as V026
from natureai_next.infrastructure.database.migrations.v027_flexible_storage import MIGRATION as V027
from natureai_next.infrastructure.database.migrations.v028_storage_device_identity import MIGRATION as V028
from natureai_next.infrastructure.database.migrations.v029_consolidated_device_registry import MIGRATION as V029
from natureai_next.infrastructure.database.migrations.v030_observation_provenance import MIGRATION as V030
from natureai_next.infrastructure.database.migrations.v031_desktop_synchronization import (
    MIGRATION as V031,
)
from natureai_next.infrastructure.database.migrations.v032_sync_journal import MIGRATION as V032
from natureai_next.infrastructure.database.migrations.v033_resumable_media_sync import (
    MIGRATION as V033,
)
from natureai_next.infrastructure.database.migrations.v034_contribution_review import (
    MIGRATION as V034,
)
from natureai_next.infrastructure.database.migrations.v035_governed_packs import MIGRATION as V035
from natureai_next.infrastructure.database.migrations.v036_governed_pack_security import (
    MIGRATION as V036,
)
from natureai_next.infrastructure.database.migrations.v037_ai_review_assignments import (
    MIGRATION as V037,
)
from natureai_next.infrastructure.database.migrations.v038_thumbnail_lifecycle import (
    MIGRATION as V038,
)
from natureai_next.infrastructure.database.migrations.v039_unified_observation_workflow import (
    MIGRATION as V039,
)

CORE_MIGRATIONS = (
    V001,
    V002,
    V003,
    V004,
    V005,
    V006,
    V007,
    V008,
    V009,
    V010,
    V011,
    V012,
    V013,
    V014,
    V015,
    V016,
    V017,
    V018,
    V019,
    V020,
    V021,
    V022,
    V023,
    V024,
    V025,
    V026,
    V027,
    V028,
    V029,
    V030,
    V031,
    V032,
    V033,
    V034,
    V035,
    V036,
    V037,
    V038,
    V039,
)
__all__ = ["CORE_MIGRATIONS", "MigrationError", "MigrationRunner"]

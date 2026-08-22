from pathlib import Path

from natureai_next.infrastructure.database.ai_review import SqliteSuggestionStore
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.migrations import CORE_MIGRATIONS, MigrationRunner


def _database(tmp_path: Path) -> SqliteConnectionFactory:
    factory = SqliteConnectionFactory(tmp_path / "library.sqlite")
    connection = factory.connect()
    MigrationRunner(CORE_MIGRATIONS, "test").apply(connection)
    connection.execute(
        """INSERT INTO assets(
            public_id,media_type,lifecycle_state,created_at_us,modified_at_us
        ) VALUES('asset-1','image','active',1,1)"""
    )
    connection.execute(
        """INSERT INTO taxonomy_sources(
            public_id,name,source_version,package_checksum,license_json,installed_at_us,active
        ) VALUES('source-1','test','1','checksum','{}',1,1)"""
    )
    connection.execute(
        """INSERT INTO taxa(
            source_id,source_taxon_id,public_id,scientific_name,rank,status
        ) VALUES(1,'1','taxon-1','Canis lupus','species','accepted')"""
    )
    connection.execute(
        """INSERT INTO model_packages(
            public_id,model_identity,semantic_version,model_family,artifact_checksum,
            manifest_json,license_json,install_path_token,installation_state,active
        ) VALUES('package-1','bioclip','1','bioclip','checksum','{}','{}','model','installed',1)"""
    )
    connection.execute(
        """INSERT INTO model_variants(
            public_id,package_id,variant_identity,runtime,precision,
            device_requirements_json,preprocessing_identity,active
        ) VALUES('variant-1',1,'default','torch','fp32','{}','prep',1)"""
    )
    connection.execute(
        """INSERT INTO inference_runs(
            public_id,model_variant_id,execution_provider,parameter_json,
            application_version,started_at_us
        ) VALUES('run-1',1,'cpu','{}','test',1)"""
    )
    connection.execute(
        """INSERT INTO ai_suggestions(
            public_id,asset_id,inference_run_id,suggestion_type,candidate_taxon_id,
            candidate_label,raw_score,rank,provenance_json,review_state,created_at_us
        ) VALUES('suggestion-1',1,1,'taxonomy',1,'Canis lupus',0.9,1,'{}','pending',1)"""
    )
    connection.close()
    return factory


def test_acceptance_creates_provider_independent_enrichment(tmp_path: Path) -> None:
    factory = _database(tmp_path)
    store = SqliteSuggestionStore(factory)

    store.review(
        suggestion_public_id="suggestion-1",
        action="accept",
        action_public_id="accept-1",
        now_us=10,
        reason=None,
    )

    connection = factory.connect(read_only=True)
    row = connection.execute(
        """SELECT e.lifecycle_status,e.display_value,p.provider_key,f.field_key
           FROM canonical_enrichments e
           JOIN enrichment_providers p ON p.id=e.provider_id
           JOIN enrichment_provider_fields f ON f.id=e.field_id"""
    ).fetchone()
    connection.close()

    assert dict(row) == {
        "lifecycle_status": "active",
        "display_value": "Canis lupus",
        "provider_key": "aperture.bioclip",
        "field_key": "taxonomy.accepted",
    }


def test_reverse_acceptance_soft_deletes_history(tmp_path: Path) -> None:
    factory = _database(tmp_path)
    store = SqliteSuggestionStore(factory)
    store.review(
        suggestion_public_id="suggestion-1",
        action="accept",
        action_public_id="accept-1",
        now_us=10,
        reason=None,
    )

    store.reverse_acceptance(
        suggestion_public_id="suggestion-1",
        action_public_id="reverse-1",
        now_us=20,
        reason="Incorrect determination",
    )

    connection = factory.connect(read_only=True)
    enrichment = connection.execute(
        """SELECT lifecycle_status,reversed_at_us,reversal_reason
           FROM canonical_enrichments"""
    ).fetchone()
    observation = connection.execute(
        "SELECT confirmation_state,revision FROM observations"
    ).fetchone()
    counts = connection.execute(
        "SELECT (SELECT COUNT(*) FROM canonical_enrichments),"
        "       (SELECT COUNT(*) FROM observations),"
        "       (SELECT COUNT(*) FROM ai_review_actions)"
    ).fetchone()
    connection.close()

    assert dict(enrichment) == {
        "lifecycle_status": "reversed",
        "reversed_at_us": 20,
        "reversal_reason": "Incorrect determination",
    }
    assert dict(observation) == {"confirmation_state": "unconfirmed", "revision": 2}
    assert tuple(counts) == (1, 1, 2)


def _add_taxon_and_suggestion(
    factory: SqliteConnectionFactory,
    *,
    taxon_public_id: str,
    suggestion_public_id: str,
    label: str,
    rank: int,
    state: str,
) -> None:
    connection = factory.connect()
    taxon_id = connection.execute(
        """INSERT INTO taxa(
            source_id,source_taxon_id,public_id,scientific_name,rank,status
        ) VALUES(1,?,?,?,?, 'accepted')""",
        (taxon_public_id, taxon_public_id, label, "species"),
    ).lastrowid
    connection.execute(
        """INSERT INTO ai_suggestions(
            public_id,asset_id,inference_run_id,suggestion_type,candidate_taxon_id,
            candidate_label,raw_score,rank,provenance_json,review_state,created_at_us
        ) VALUES(?,1,1,'taxonomy',?,?,0.8,?,'{}',?,1)""",
        (suggestion_public_id, int(taxon_id), label, rank, state),
    )
    connection.close()


def test_accept_all_pending_for_asset_does_not_touch_other_states(tmp_path: Path) -> None:
    factory = _database(tmp_path)
    _add_taxon_and_suggestion(
        factory,
        taxon_public_id="taxon-2",
        suggestion_public_id="suggestion-2",
        label="Vulpes vulpes",
        rank=2,
        state="pending",
    )
    _add_taxon_and_suggestion(
        factory,
        taxon_public_id="taxon-3",
        suggestion_public_id="suggestion-3",
        label="Canis latrans",
        rank=3,
        state="deferred",
    )
    _add_taxon_and_suggestion(
        factory,
        taxon_public_id="taxon-4",
        suggestion_public_id="suggestion-4",
        label="Canis familiaris",
        rank=4,
        state="rejected",
    )
    action_ids = iter(("accept-all-1", "accept-all-2"))
    store = SqliteSuggestionStore(factory)

    result = store.accept_all_pending_for_asset(
        "suggestion-1",
        action_id_factory=lambda: next(action_ids),
        now_us=20,
    )

    connection = factory.connect(read_only=True)
    states = dict(
        connection.execute(
            "SELECT public_id,review_state FROM ai_suggestions ORDER BY public_id"
        ).fetchall()
    )
    enrichment_count = connection.execute(
        "SELECT COUNT(*) FROM canonical_enrichments WHERE lifecycle_status='active'"
    ).fetchone()[0]
    connection.close()

    assert result.reviewed == ("suggestion-1", "suggestion-2")
    assert states == {
        "suggestion-1": "accepted",
        "suggestion-2": "accepted",
        "suggestion-3": "deferred",
        "suggestion-4": "rejected",
    }
    assert enrichment_count == 2


def test_accept_only_and_next_rejects_only_other_pending_rows(tmp_path: Path) -> None:
    factory = _database(tmp_path)
    _add_taxon_and_suggestion(
        factory,
        taxon_public_id="taxon-2",
        suggestion_public_id="suggestion-2",
        label="Vulpes vulpes",
        rank=2,
        state="pending",
    )
    _add_taxon_and_suggestion(
        factory,
        taxon_public_id="taxon-3",
        suggestion_public_id="suggestion-3",
        label="Canis latrans",
        rank=3,
        state="deferred",
    )
    action_ids = iter(("accept-only-1", "accept-only-2"))
    store = SqliteSuggestionStore(factory)

    result = store.accept_and_reject_others(
        "suggestion-1",
        action_id_factory=lambda: next(action_ids),
        now_us=30,
    )

    connection = factory.connect(read_only=True)
    states = dict(
        connection.execute(
            "SELECT public_id,review_state FROM ai_suggestions ORDER BY public_id"
        ).fetchall()
    )
    connection.close()

    assert result.reviewed == ("suggestion-1", "suggestion-2")
    assert states == {
        "suggestion-1": "accepted",
        "suggestion-2": "rejected",
        "suggestion-3": "deferred",
    }


def test_label_only_bioclip_suggestion_can_be_accepted(tmp_path: Path) -> None:
    factory = _database(tmp_path)
    connection = factory.connect()
    connection.execute(
        """UPDATE ai_suggestions
           SET candidate_taxon_id=NULL,candidate_label='Uncatalogued species'
           WHERE public_id='suggestion-1'"""
    )
    connection.close()

    store = SqliteSuggestionStore(factory)
    store.review(
        suggestion_public_id="suggestion-1",
        action="accept",
        action_public_id="accept-label-only",
        now_us=30,
        reason=None,
    )

    connection = factory.connect(read_only=True)
    suggestion = connection.execute(
        "SELECT review_state,observation_id FROM ai_suggestions WHERE public_id='suggestion-1'"
    ).fetchone()
    enrichment = connection.execute(
        "SELECT display_value,value_json,lifecycle_status FROM canonical_enrichments"
    ).fetchone()
    observation_count = connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    connection.close()

    assert dict(suggestion) == {"review_state": "accepted", "observation_id": None}
    assert enrichment["display_value"] == "Uncatalogued species"
    assert '"taxon_public_id":null' in enrichment["value_json"]
    assert enrichment["lifecycle_status"] == "active"
    assert observation_count == 0

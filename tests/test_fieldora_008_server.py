import base64
import hashlib
import io
import json
import sqlite3
import ssl
import time
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.x509.oid import NameOID

from natureai_next.application.access_control import (
    AccessAdministrationService,
    PolicyDecisionService,
)
from natureai_next.application.authentication import (
    AuthenticationFailed,
    AuthenticationService,
)
from natureai_next.application.device_authorization import DeviceAuthorizationService
from natureai_next.application.oidc import OidcAuthenticationService, OidcConfiguration
from natureai_next.application.science import default_science_snapshot
from natureai_next.bootstrap.server_cli import build_parser, validate_listener_security
from natureai_next.domain.access_control import (
    AccessRequest,
    IdentityKind,
    Organization,
    PolicyEffect,
    PolicySource,
)
from natureai_next.infrastructure.database.access_control import (
    SqliteAccessControlRepository,
)
from natureai_next.infrastructure.database.migrations.core import MigrationRunner
from natureai_next.infrastructure.database.science import SqliteScienceRepository
from natureai_next.infrastructure.subsystems.server_exports import (
    SERVER_EXPORTS_MIGRATIONS,
)
from natureai_next.server.api import FieldoraApi, ScienceReadProjection
from natureai_next.server.export_encryption import (
    decrypt_project_export,
    generate_recipient_identity,
)
from natureai_next.server.export_signing import (
    ExportSigningIdentity,
    verify_export_attestation,
)
from natureai_next.server.exports import GovernedExportStore
from natureai_next.server.http import create_server
from natureai_next.server.jobs import ServerJobStore, run_one_job
from natureai_next.server.media import GovernedMediaStore, MediaRecord, UploadSession
from natureai_next.server.object_storage import S3ObjectStore
from natureai_next.server.postgres_access import PostgresAccessControlRepository
from natureai_next.server.postgres_exports import PostgresExportMetadataRepository
from natureai_next.server.postgres_jobs import PostgresServerJobStore
from natureai_next.server.postgres_media import PostgresMediaMetadataRepository
from natureai_next.server.postgres_science import PostgresScienceRepository
from natureai_next.server.recovery import OneNodeServerRecovery
from natureai_next.server.search import OpenSearchProjection, ServerSearchProjection
from natureai_next.server.staged_ingestion import (
    StagedIngestionService,
    StagedIngestionStore,
)


class _CleanStagingScanner:
    def scan(self, _path: Path) -> tuple[bool, str]:
        return True, "clean:test"


def _server(tmp_path: Path):
    repository = SqliteAccessControlRepository(tmp_path / "access.sqlite3")
    administration = AccessAdministrationService(repository)
    administration.create_organization("org-a", "Research")
    user = administration.create_identity("Reader", "org-a", IdentityKind.USER)
    authentication = AuthenticationService(repository)
    authentication.set_password(user.identity_id, "reader", "correct horse battery")
    administration.create_policy(
        name="One project",
        effect=PolicyEffect.ALLOW,
        source=PolicySource.DIRECT,
        subject_id=user.identity_id,
        actions=("view",),
        resource_types=("project", "dossier"),
        organization_id="org-a",
        project_id="p1",
        purposes=("research",),
    )
    science_path = tmp_path / "science.sqlite3"
    connection = sqlite3.connect(science_path)
    connection.execute(
        "CREATE TABLE science_records(collection_name TEXT,record_id TEXT,"
        "payload_json TEXT,record_revision INTEGER DEFAULT 1,updated_at_us INTEGER,"
        "PRIMARY KEY(collection_name,record_id))"
    )
    records = (
        ("projects", "p1", {"id": "p1", "title": "Allowed"}),
        ("projects", "p2", {"id": "p2", "title": "Hidden"}),
        ("dossiers", "d1", {"id": "d1", "project_id": "p1", "title": "Visible"}),
        ("dossiers", "d2", {"id": "d2", "project_id": "p2", "title": "Secret"}),
    )
    for collection, record_id, payload in records:
        connection.execute(
            "INSERT INTO science_records(collection_name,record_id,payload_json,"
            "updated_at_us) VALUES(?,?,?,1)",
            (collection, record_id, json.dumps(payload)),
        )
    connection.commit()
    connection.close()
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("Fieldora", encoding="utf-8")
    (web / "app.js").write_text("", encoding="utf-8")
    media = GovernedMediaStore(tmp_path / "media.sqlite3", tmp_path / "media")
    return (
        FieldoraApi(
            authentication, PolicyDecisionService(repository),
            ScienceReadProjection(science_path), web, media,
        ),
        authentication,
        repository,
        media,
    )


def test_session_is_opaque_hashed_and_revocable(tmp_path: Path) -> None:
    _, authentication, repository, _ = _server(tmp_path)
    session = authentication.login("reader", "correct horse battery")
    connection = repository._factory.connect(read_only=True)
    try:
        stored = connection.execute("SELECT session_hash FROM access_sessions").fetchone()[0]
    finally:
        connection.close()
    assert stored != session.token
    assert authentication.authenticate(session.token).display_name == "Reader"
    authentication.logout(session.token)
    try:
        authentication.authenticate(session.token)
    except AuthenticationFailed:
        pass
    else:
        raise AssertionError("revoked session remained valid")


def test_api_authenticates_and_filters_each_record_with_pbac(tmp_path: Path) -> None:
    api, _, _, _ = _server(tmp_path)
    assert api.dispatch("GET", "/api/v1/projects", {}, b"").status == 401
    login = api.dispatch(
        "POST", "/api/v1/session", {"user-agent": "test"},
        json.dumps({"username": "reader", "password": "correct horse battery"}).encode(),
    )
    assert login.status == 201
    token = json.loads(login.body)["access_token"]
    headers = {"authorization": f"Bearer {token}", "x-fieldora-purpose": "research"}
    projects = json.loads(api.dispatch("GET", "/api/v1/projects", headers, b"").body)
    dossiers = json.loads(api.dispatch("GET", "/api/v1/dossiers", headers, b"").body)
    assert [item["id"] for item in projects["items"]] == ["p1"]
    assert [item["id"] for item in dossiers["items"]] == ["d1"]


def test_api_authorizes_writes_and_rejects_stale_revision(tmp_path: Path) -> None:
    api, _, repository, _ = _server(tmp_path)
    user = repository.identities()[0]
    AccessAdministrationService(repository).create_policy(
        name="Edit project one", effect=PolicyEffect.ALLOW,
        source=PolicySource.DIRECT, subject_id=user.identity_id,
        actions=("edit",), resource_types=("project",),
        organization_id="org-a", project_id="p1", purposes=("research",),
    )
    login = api.dispatch(
        "POST", "/api/v1/session", {},
        json.dumps({"username": "reader", "password": "correct horse battery"}).encode(),
    )
    token = json.loads(login.body)["access_token"]
    headers = {"authorization": f"Bearer {token}", "if-match": "1"}
    payload = json.dumps({"id": "p1", "title": "Updated"}).encode()
    assert api.dispatch("POST", "/api/v1/projects", headers, payload).status == 200
    assert api.dispatch("POST", "/api/v1/projects", headers, payload).status == 409
    denied = json.dumps({"id": "p2", "title": "Forbidden"}).encode()
    assert api.dispatch("POST", "/api/v1/projects", headers, denied).status == 403


def test_media_download_is_pbac_filtered_and_resumable(tmp_path: Path) -> None:
    api, _, repository, media = _server(tmp_path)
    source = tmp_path / "sound.wav"
    source.write_bytes(b"0123456789")
    record = media.register(source, "org-a", "p1")
    user = repository.identities()[0]
    AccessAdministrationService(repository).create_policy(
        name="Download project media", effect=PolicyEffect.ALLOW,
        source=PolicySource.DIRECT, subject_id=user.identity_id,
        actions=("download",), resource_types=("asset",),
        organization_id="org-a", project_id="p1", purposes=("research",),
    )
    login = api.dispatch(
        "POST", "/api/v1/session", {},
        json.dumps({"username": "reader", "password": "correct horse battery"}).encode(),
    )
    token = json.loads(login.body)["access_token"]
    response = api.dispatch(
        "GET", f"/api/v1/media/{record.media_id}",
        {"authorization": f"Bearer {token}", "range": "bytes=2-5"}, b"",
    )
    assert response.status == 206
    assert response.body == b"2345"
    assert ("Content-Range", "bytes 2-5/10") in response.headers
    hidden = media.register(source, "org-a", "p2")
    assert api.dispatch(
        "GET", f"/api/v1/media/{hidden.media_id}",
        {"authorization": f"Bearer {token}"}, b"",
    ).status == 404
    try:
        media._contained("../escape")
    except ValueError:
        pass
    else:
        raise AssertionError("media store accepted a path outside its root")


def test_resumable_upload_is_authorized_and_integrity_checked(tmp_path: Path) -> None:
    api, _, repository, _ = _server(tmp_path)
    user = repository.identities()[0]
    AccessAdministrationService(repository).create_policy(
        name="Upload project media", effect=PolicyEffect.ALLOW,
        source=PolicySource.DIRECT, subject_id=user.identity_id,
        actions=("upload",), resource_types=("asset",),
        organization_id="org-a", project_id="p1", purposes=("research",),
    )
    login = api.dispatch(
        "POST", "/api/v1/session", {},
        json.dumps({"username": "reader", "password": "correct horse battery"}).encode(),
    )
    headers = {"authorization": f"Bearer {json.loads(login.body)['access_token']}"}
    content = b"field-recording"
    begin = api.dispatch(
        "POST", "/api/v1/uploads", headers,
        json.dumps({
            "project_id": "p1", "filename": "recording.wav",
            "size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
        }).encode(),
    )
    assert begin.status == 201
    upload_id = json.loads(begin.body)["upload_id"]
    first = content[:5]
    assert api.dispatch(
        "PUT", f"/api/v1/uploads/{upload_id}",
        {**headers, "content-range": f"bytes 0-4/{len(content)}"}, first,
    ).status == 200
    final = api.dispatch(
        "PUT", f"/api/v1/uploads/{upload_id}",
        {**headers, "content-range": f"bytes 5-{len(content)-1}/{len(content)}"},
        content[5:],
    )
    assert final.status == 201
    denied = api.dispatch(
        "POST", "/api/v1/uploads", headers,
        json.dumps({
            "project_id": "p2", "filename": "secret.wav",
            "size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
        }).encode(),
    )
    assert denied.status == 403


def test_staged_submission_quarantines_before_worker_validation(tmp_path: Path) -> None:
    api, _, repository, _ = _server(tmp_path)
    user = repository.identities()[0]
    AccessAdministrationService(repository).create_policy(
        name="Stage project media",
        effect=PolicyEffect.ALLOW,
        source=PolicySource.DIRECT,
        subject_id=user.identity_id,
        actions=("upload", "view"),
        resource_types=("asset",),
        organization_id="org-a",
        project_id="p1",
        purposes=("research",),
    )
    jobs = ServerJobStore(tmp_path / "staged-jobs.sqlite3")
    staging = StagedIngestionService(
        StagedIngestionStore(
            tmp_path / "staging.sqlite3", tmp_path / "quarantine"
        ),
        jobs,
        malware_scanner=_CleanStagingScanner(),
    )
    api._staged_ingestion = staging
    login = api.dispatch(
        "POST",
        "/api/v1/session",
        {},
        json.dumps(
            {"username": "reader", "password": "correct horse battery"}
        ).encode(),
    )
    headers = {"authorization": f"Bearer {json.loads(login.body)['access_token']}"}
    content = b"field-photo"
    created = api.dispatch(
        "POST",
        "/api/v1/staged-submissions",
        headers,
        json.dumps(
            {
                "project_id": "p1",
                "purpose": "research",
                "publication_policy": "review",
                "expected_files": 1,
            }
        ).encode(),
    )
    assert created.status == 201
    submission_id = json.loads(created.body)["submission"]["submission_id"]
    begun = api.dispatch(
        "POST",
        f"/api/v1/staged-submissions/{submission_id}/files",
        headers,
        json.dumps(
            {
                "filename": "photo.jpg",
                "relative_path": "camera/day-1/photo.jpg",
                "mime_type": "image/jpeg",
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        ).encode(),
    )
    assert begun.status == 201
    staged_file_id = json.loads(begun.body)["staged_file_id"]
    uploaded = api.dispatch(
        "PUT",
        f"/api/v1/staged-files/{staged_file_id}",
        {
            **headers,
            "content-range": f"bytes 0-{len(content) - 1}/{len(content)}",
        },
        content,
    )
    assert uploaded.status == 200
    assert json.loads(uploaded.body)["state"] == "uploaded"
    status = api.dispatch(
        "GET", f"/api/v1/staged-submissions/{submission_id}", headers, b""
    )
    assert json.loads(status.body)["files"][0]["media_id"] == ""
    sealed = api.dispatch(
        "POST", f"/api/v1/staged-submissions/{submission_id}/seal", headers, b""
    )
    assert sealed.status == 202
    assert jobs.claim(worker_id="validator").job_type == "staged.validate"


def test_service_key_is_hashed_pbac_scoped_and_revocable(tmp_path: Path) -> None:
    api, authentication, repository, _ = _server(tmp_path)
    administration = AccessAdministrationService(repository)
    service = administration.create_identity(
        "Indexer", "org-a", IdentityKind.SERVICE
    )
    administration.create_policy(
        name="Service project read", effect=PolicyEffect.ALLOW,
        source=PolicySource.DIRECT, subject_id=service.identity_id,
        actions=("view",), resource_types=("project",),
        organization_id="org-a", project_id="p1", purposes=("research",),
    )
    credential_id, token = authentication.issue_service_key(service.identity_id, "ci")
    connection = repository._factory.connect(read_only=True)
    try:
        stored = connection.execute(
            "SELECT key_hash FROM access_service_credentials"
        ).fetchone()[0]
    finally:
        connection.close()
    assert stored != token
    response = api.dispatch(
        "GET", "/api/v1/projects", {"authorization": f"ApiKey {token}"}, b""
    )
    assert response.status == 200
    assert [item["id"] for item in json.loads(response.body)["items"]] == ["p1"]
    authentication.revoke_service_key(credential_id)
    assert api.dispatch(
        "GET", "/api/v1/projects", {"authorization": f"ApiKey {token}"}, b""
    ).status == 401
    _, expired = authentication.issue_service_key(
        service.identity_id, "expired", timedelta(seconds=-1)
    )
    assert api.dispatch(
        "GET", "/api/v1/projects", {"authorization": f"ApiKey {expired}"}, b""
    ).status == 401


def test_device_key_is_project_bound_and_revocable(tmp_path: Path) -> None:
    api, authentication, repository, _ = _server(tmp_path)
    administration = AccessAdministrationService(repository)
    device = administration.create_identity(
        "Field tablet", "org-a", IdentityKind.DEVICE
    )
    administration.grant_role(device.identity_id, "field-device", "org-a", "p1")
    administration.create_policy(
        name="Field device project", effect=PolicyEffect.ALLOW,
        source=PolicySource.ROLE, role_id="field-device",
        actions=("view",), resource_types=("project",),
        organization_id="org-a", project_id="p1", purposes=("research",),
    )
    credential_id, token = authentication.issue_machine_key(
        device.identity_id, "tablet"
    )
    response = api.dispatch(
        "GET", "/api/v1/projects", {"authorization": f"ApiKey {token}"}, b""
    )
    assert [item["id"] for item in json.loads(response.body)["items"]] == ["p1"]
    authentication.revoke_service_key(credential_id)
    assert api.dispatch(
        "GET", "/api/v1/projects", {"authorization": f"ApiKey {token}"}, b""
    ).status == 401


def test_interactive_device_flow_is_approved_once_and_project_bound(
    tmp_path: Path,
) -> None:
    api, authentication, repository, _ = _server(tmp_path)
    api._device_authorization = DeviceAuthorizationService(
        repository, authentication
    )
    user = repository.identities()[0]
    administration = AccessAdministrationService(repository)
    administration.create_policy(
        name="Enroll field devices", effect=PolicyEffect.ALLOW,
        source=PolicySource.DIRECT, subject_id=user.identity_id,
        actions=("enroll_device",), resource_types=("project",),
        organization_id="org-a", project_id="p1", purposes=("administration",),
    )
    administration.create_policy(
        name="Field device view", effect=PolicyEffect.ALLOW,
        source=PolicySource.ROLE, role_id="field-device",
        actions=("view",), resource_types=("project",),
        organization_id="org-a", project_id="p1", purposes=("research",),
    )
    started = api.dispatch(
        "POST", "/api/v1/device/code", {},
        json.dumps({
            "device_name": "Recorder", "organization_id": "org-a",
            "project_id": "p1",
        }).encode(),
    )
    codes = json.loads(started.body)
    assert api.dispatch(
        "POST", "/api/v1/device/token", {},
        json.dumps({"device_code": codes["device_code"]}).encode(),
    ).status == 428
    login = api.dispatch(
        "POST", "/api/v1/session", {},
        json.dumps({"username": "reader", "password": "correct horse battery"}).encode(),
    )
    bearer = json.loads(login.body)["access_token"]
    assert api.dispatch(
        "POST", "/api/v1/device/approve",
        {"authorization": f"Bearer {bearer}", "x-fieldora-purpose": "administration"},
        json.dumps({"user_code": codes["user_code"]}).encode(),
    ).status == 200
    exchanged = api.dispatch(
        "POST", "/api/v1/device/token", {},
        json.dumps({"device_code": codes["device_code"]}).encode(),
    )
    assert exchanged.status == 201
    device_key = json.loads(exchanged.body)["access_token"]
    projects = api.dispatch(
        "GET", "/api/v1/projects", {"authorization": f"ApiKey {device_key}"}, b""
    )
    assert [item["id"] for item in json.loads(projects.body)["items"]] == ["p1"]
    assert api.dispatch(
        "POST", "/api/v1/device/token", {},
        json.dumps({"device_code": codes["device_code"]}).encode(),
    ).status == 400


def test_oidc_signature_claims_mapping_and_pbac(tmp_path: Path) -> None:
    api, _, repository, _ = _server(tmp_path)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.public_key().public_numbers()
    encode = lambda value: base64.urlsafe_b64encode(value).rstrip(b"=").decode()
    integer = lambda value: encode(value.to_bytes((value.bit_length() + 7) // 8, "big"))
    jwks = tmp_path / "jwks.json"
    jwks.write_text(json.dumps({"keys": [{
        "kid": "test", "kty": "RSA", "use": "sig",
        "n": integer(numbers.n), "e": integer(numbers.e),
    }]}), encoding="utf-8")
    user = repository.identities()[0]
    repository.map_federated_identity("https://issuer.example", "subject-1", user.identity_id)
    api._oidc = OidcAuthenticationService(
        OidcConfiguration("https://issuer.example", "fieldora", jwks), repository
    )
    header = encode(json.dumps({"alg": "RS256", "kid": "test"}).encode())
    claims = encode(json.dumps({
        "iss": "https://issuer.example", "aud": "fieldora", "sub": "subject-1",
        "exp": int(time.time()) + 300,
    }).encode())
    signing_input = f"{header}.{claims}".encode()
    signature = encode(key.sign(signing_input, padding.PKCS1v15(), SHA256()))
    token = f"{header}.{claims}.{signature}"
    response = api.dispatch(
        "GET", "/api/v1/projects", {"authorization": f"Bearer {token}"}, b""
    )
    assert response.status == 200
    assert [item["id"] for item in json.loads(response.body)["items"]] == ["p1"]
    tampered = token[:-20] + ("A" if token[-20] != "A" else "B") + token[-19:]
    assert api.dispatch(
        "GET", "/api/v1/projects",
        {"authorization": f"Bearer {tampered}"}, b"",
    ).status == 401


def test_oidc_discovery_refreshes_once_for_rotated_signing_key(
    tmp_path: Path,
) -> None:
    _, _, repository, _ = _server(tmp_path)
    issuer = "https://identity.example"
    audience = "fieldora"
    user = repository.identities()[0]
    repository.map_federated_identity(issuer, "rotated-subject", user.identity_id)
    old_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def jwk(key, kid):
        numbers = key.public_key().public_numbers()
        encode = lambda value: base64.urlsafe_b64encode(value).rstrip(b"=").decode()
        integer = lambda value: encode(
            value.to_bytes((value.bit_length() + 7) // 8, "big")
        )
        return {
            "kid": kid, "kty": "RSA", "use": "sig",
            "n": integer(numbers.n), "e": integer(numbers.e),
        }

    calls = []

    def fetch(url, timeout, maximum):
        calls.append((url, timeout, maximum))
        if url.endswith("/.well-known/openid-configuration"):
            return {"issuer": issuer, "jwks_uri": f"{issuer}/keys"}
        return {"keys": [jwk(old_key, "old")]} if len(calls) == 2 else {
            "keys": [jwk(new_key, "new")]
        }

    service = OidcAuthenticationService(
        OidcConfiguration(
            issuer, audience, discovery=True, refresh_seconds=60
        ),
        repository,
        fetch_json=fetch,
    )
    encode = lambda value: base64.urlsafe_b64encode(value).rstrip(b"=").decode()
    header = encode(json.dumps({"alg": "RS256", "kid": "new"}).encode())
    claims = encode(json.dumps({
        "iss": issuer, "aud": audience, "sub": "rotated-subject",
        "exp": int(time.time()) + 300,
    }).encode())
    signing_input = f"{header}.{claims}".encode()
    signature = encode(new_key.sign(signing_input, padding.PKCS1v15(), SHA256()))
    assert service.authenticate(f"{header}.{claims}.{signature}") == user
    assert [item[0] for item in calls] == [
        f"{issuer}/.well-known/openid-configuration",
        f"{issuer}/keys",
        f"{issuer}/keys",
    ]
    assert calls[0][2] == 256 * 1024
    assert calls[1][2] == 1024 * 1024


def test_oidc_discovery_rejects_untrusted_metadata(tmp_path: Path) -> None:
    _, _, repository, _ = _server(tmp_path)
    with pytest.raises(ValueError, match="HTTPS issuer"):
        OidcAuthenticationService(
            OidcConfiguration(
                "http://identity.example", "fieldora", discovery=True
            ),
            repository,
            fetch_json=lambda *_: {},
        )
    with pytest.raises(ValueError, match="does not match"):
        OidcAuthenticationService(
            OidcConfiguration(
                "https://identity.example", "fieldora", discovery=True
            ),
            repository,
            fetch_json=lambda url, *_: {
                "issuer": "https://attacker.example",
                "jwks_uri": "https://attacker.example/keys",
            },
        )


def test_audit_chain_detects_tampering_and_api_is_pbac_guarded(
    tmp_path: Path,
) -> None:
    api, _, repository, _ = _server(tmp_path)
    api._audit_repository = repository
    user = repository.identities()[0]
    AccessAdministrationService(repository).create_policy(
        name="Security audit reader", effect=PolicyEffect.ALLOW,
        source=PolicySource.DIRECT, subject_id=user.identity_id,
        actions=("view_audit",), resource_types=("security_audit",),
        organization_id="org-a", purposes=("administration",),
    )
    login = api.dispatch(
        "POST", "/api/v1/session", {},
        json.dumps({"username": "reader", "password": "correct horse battery"}).encode(),
    )
    token = json.loads(login.body)["access_token"]
    response = api.dispatch(
        "GET", "/api/v1/audit?limit=20",
        {"authorization": f"Bearer {token}", "x-fieldora-purpose": "administration"},
        b"",
    )
    assert response.status == 200
    assert json.loads(response.body)["chain_verified"]
    connection = repository._factory.connect()
    try:
        connection.execute(
            "UPDATE access_audit_events SET reason='tampered' WHERE sequence=("
            "SELECT MIN(sequence) FROM access_audit_events)"
        )
    finally:
        connection.close()
    verified, _ = repository.verify_audit_chain()
    assert not verified


def test_search_filters_candidates_before_title_or_snippet_disclosure(
    tmp_path: Path,
) -> None:
    api, _, repository, _ = _server(tmp_path)
    search = ServerSearchProjection(tmp_path / "search.sqlite3")
    search.rebuild(tmp_path / "science.sqlite3", "org-a")
    api._search = search
    user = repository.identities()[0]
    AccessAdministrationService(repository).create_policy(
        name="Search project one", effect=PolicyEffect.ALLOW,
        source=PolicySource.DIRECT, subject_id=user.identity_id,
        actions=("search",), resource_types=("project", "dossier"),
        organization_id="org-a", project_id="p1", purposes=("research",),
    )
    login = api.dispatch(
        "POST", "/api/v1/session", {},
        json.dumps({"username": "reader", "password": "correct horse battery"}).encode(),
    )
    headers = {"authorization": f"Bearer {json.loads(login.body)['access_token']}"}
    visible = json.loads(
        api.dispatch("GET", "/api/v1/search?q=Allowed", headers, b"").body
    )
    assert [item["resource_id"] for item in visible["items"]] == ["p1"]
    hidden = json.loads(
        api.dispatch("GET", "/api/v1/search?q=Hidden", headers, b"").body
    )
    assert hidden == {"items": [], "count": 0}


def test_opensearch_projection_uses_atomic_alias_and_bounded_candidates(
    tmp_path: Path,
) -> None:
    _server(tmp_path)
    calls: list[tuple[str, str, dict | None, int]] = []

    def request(method: str, url: str, body: dict | None, maximum: int) -> dict:
        calls.append((method, url, body, maximum))
        if url.endswith("/_bulk?refresh=true"):
            return {"errors": False}
        if "/_alias/" in url:
            return {}
        if url.endswith("/_search"):
            return {
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "resource_type": "project",
                                "resource_id": "p1",
                                "organization_id": "org-a",
                                "project_id": "p1",
                                "title": "Allowed Project",
                                "body": "A" * 500,
                            }
                        }
                    ]
                }
            }
        return {}

    projection = OpenSearchProjection(
        "https://search.example", "fieldora-test", 5, request
    )
    assert projection.rebuild(tmp_path / "science.sqlite3", "org-a") == 4
    methods = [item[0] for item in calls]
    assert methods == ["PUT", "POST", "GET", "POST"]
    alias_body = calls[-1][2]
    assert alias_body is not None
    assert alias_body["actions"][-1]["add"]["alias"] == "fieldora-test"
    hits = projection.candidates("allowed project", 900)
    assert len(hits) == 1
    assert hits[0].resource_id == "p1"
    assert len(hits[0].snippet) == 240
    search_body = calls[-1][2]
    assert search_body is not None and search_body["size"] == 500

    with pytest.raises(ValueError, match="HTTPS"):
        OpenSearchProjection("http://search.example")
    with pytest.raises(ValueError, match="invalid"):
        OpenSearchProjection("https://search.example", "Invalid Alias")


def test_durable_job_output_requires_separate_pbac_and_lease_recovers(
    tmp_path: Path,
) -> None:
    api, _, repository, _ = _server(tmp_path)
    search = ServerSearchProjection(tmp_path / "search.sqlite3")
    jobs = ServerJobStore(tmp_path / "jobs.sqlite3")
    api._search, api._jobs = search, jobs
    user = repository.identities()[0]
    administration = AccessAdministrationService(repository)
    administration.create_policy(
        name="Search administrator", effect=PolicyEffect.ALLOW,
        source=PolicySource.DIRECT, subject_id=user.identity_id,
        actions=("administer_search",), resource_types=("search_index",),
        organization_id="org-a", purposes=("administration",),
    )
    login = api.dispatch(
        "POST", "/api/v1/session", {},
        json.dumps({"username": "reader", "password": "correct horse battery"}).encode(),
    )
    headers = {
        "authorization": f"Bearer {json.loads(login.body)['access_token']}",
        "x-fieldora-purpose": "administration",
    }
    submitted = api.dispatch(
        "POST", "/api/v1/jobs", headers,
        json.dumps({"job_type": "rebuild_search"}).encode(),
    )
    job_id = json.loads(submitted.body)["job_id"]
    assert api.dispatch("GET", f"/api/v1/jobs/{job_id}", headers, b"").status == 404
    administration.create_policy(
        name="View submitted job", effect=PolicyEffect.ALLOW,
        source=PolicySource.DIRECT, subject_id=user.identity_id,
        actions=("view_job",), resource_types=("job",), resource_id=job_id,
        organization_id="org-a", purposes=("administration",),
    )
    completed = run_one_job(jobs, search, tmp_path / "science.sqlite3")
    assert completed is not None and completed.status == "succeeded"
    visible = api.dispatch("GET", f"/api/v1/jobs/{job_id}", headers, b"")
    assert json.loads(visible.body)["result"]["indexed_records"] == 4
    recovery = jobs.enqueue("rebuild_search", user.identity_id, "org-a", "", {})
    assert jobs.claim(lease_seconds=-1).job_id == recovery.job_id
    assert jobs.claim().attempts == 2


def test_distributed_job_leases_are_owned_renewable_and_fenced(
    tmp_path: Path,
) -> None:
    jobs = ServerJobStore(tmp_path / "jobs.sqlite3")
    queued = jobs.enqueue("rebuild_search", "subject", "org-a", "", {})
    first = jobs.claim(lease_seconds=-1, worker_id="worker-a")
    assert first is not None
    assert first.job_id == queued.job_id
    assert first.lease_owner == "worker-a"
    assert first.lease_token

    second = jobs.claim(lease_seconds=60, worker_id="worker-b")
    assert second is not None
    assert second.job_id == queued.job_id
    assert second.lease_owner == "worker-b"
    assert second.lease_token != first.lease_token

    assert not jobs.renew(second.job_id, first.lease_token)
    assert not jobs.finish(second.job_id, first.lease_token, {"stale": True})
    assert jobs.renew(second.job_id, second.lease_token, lease_seconds=120)
    assert jobs.finish(second.job_id, second.lease_token, {"worker": "b"})
    completed = jobs.job(second.job_id)
    assert completed is not None
    assert completed.status == "succeeded"
    assert completed.result == {"worker": "b"}
    assert completed.lease_owner == ""
    assert completed.lease_token == ""


def test_postgresql_job_claim_uses_skip_locked_and_preserves_fencing() -> None:
    statements: list[str] = []
    now = datetime.now(UTC)
    claimed_row = (
        "job-1", "rebuild_search", "subject", "org-a", "", "running",
        {}, {}, 1, now, now, now, "worker-a", "lease-token",
    )
    responses = [None, claimed_row, None, None]
    rowcounts = [0, 0, 1, 0]

    class Cursor:
        def __init__(self, response, rowcount):
            self._response = response
            self.rowcount = rowcount

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def execute(self, statement, parameters=None):
            statements.append(" ".join(str(statement).split()))

        def fetchone(self):
            return self._response

    class Connection:
        def __init__(self, response, rowcount):
            self._response = response
            self._rowcount = rowcount

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def cursor(self):
            return Cursor(self._response, self._rowcount)

    def connect():
        return Connection(responses.pop(0), rowcounts.pop(0))

    jobs = PostgresServerJobStore(connect)
    claimed = jobs.claim(worker_id="worker-a")
    assert claimed is not None
    assert claimed.lease_owner == "worker-a"
    assert claimed.lease_token == "lease-token"
    assert "FOR UPDATE SKIP LOCKED" in statements[2]
    assert jobs.renew("job-1", "lease-token")
    assert not jobs.finish("job-1", "stale-token", {"stale": True})
    assert "lease_token=%s" in statements[-1]


def test_postgresql_media_metadata_completes_upload_atomically() -> None:
    statements: list[str] = []
    responses = [
        None,
        None,
        ("upload-1", "subject", "org-a", "p1", "bird.wav", "audio/wav",
         4, "a" * 64, 0),
        None,
        (4, 4),
        ("media-1", "m/media-1.wav", "org-a", "p1", "audio/wav", 4, "a" * 64),
    ]
    rowcounts = [0, 1, 1, 1, 1, 1]

    class Cursor:
        def __init__(self, response, rowcount):
            self._response = response
            self.rowcount = rowcount

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def execute(self, statement, parameters=None):
            statements.append(" ".join(str(statement).split()))

        def fetchone(self):
            return self._response

    class Connection:
        def __init__(self, response, rowcount):
            self._response = response
            self._rowcount = rowcount

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def cursor(self):
            return Cursor(self._response, self._rowcount)

    def connect():
        return Connection(responses.pop(0), rowcounts.pop(0))

    metadata = PostgresMediaMetadataRepository(connect)
    upload = UploadSession(
        "upload-1", "subject", "org-a", "p1", "bird.wav", "audio/wav",
        4, "a" * 64, 0,
    )
    metadata.insert_upload(upload)
    assert metadata.upload("upload-1") == upload
    metadata.update_upload_offset("upload-1", 0, 4)
    record = MediaRecord(
        "media-1", "m/media-1.wav", "org-a", "p1", "audio/wav", 4, "a" * 64
    )
    metadata.complete_upload("upload-1", record)
    assert metadata.record("media-1") == record
    assert any("received_bytes=%s" in statement for statement in statements)
    assert any("FOR UPDATE" in statement for statement in statements)


def test_postgresql_export_metadata_claims_expiry_with_skip_locked() -> None:
    statements: list[str] = []
    now = datetime.now(UTC)
    row = (
        "export-1", "job-1", "subject", "org-a", "p1", "project.zip",
        "export-1.zip", 4, "a" * 64, now, now, None, now, "", "",
    )
    responses = [None, None, row, None, None, [row]]
    rowcounts = [0, 1, 0, 1, 1, 1]

    class Cursor:
        def __init__(self, response, rowcount):
            self._response = response
            self.rowcount = rowcount

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def execute(self, statement, parameters=None):
            statements.append(" ".join(str(statement).split()))

        def fetchone(self):
            return self._response

        def fetchall(self):
            return self._response

    class Connection:
        def __init__(self, response, rowcount):
            self._response = response
            self._rowcount = rowcount

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def cursor(self):
            return Cursor(self._response, self._rowcount)

    def connect():
        return Connection(responses.pop(0), rowcounts.pop(0))

    metadata = PostgresExportMetadataRepository(connect)
    record = metadata._decode(row)
    metadata.insert(record)
    assert metadata.stored("export-1") == record
    assert metadata.revoke("export-1", now.isoformat())
    assert metadata.attach_attestation("export-1", "key-1", "signature")
    claimed = metadata.claim_expired(now.isoformat())
    assert claimed == (record,)
    assert any("FOR UPDATE SKIP LOCKED" in statement for statement in statements)
    assert any("RETURNING export_id" in statement for statement in statements)


def test_postgresql_science_put_is_locked_and_search_source_is_replaceable(
    tmp_path: Path,
) -> None:
    statements: list[str] = []
    responses = [None, (2,), [({"id": "p1", "title": "Shared Project"},)]]

    class Cursor:
        def __init__(self, response):
            self._response = response

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def execute(self, statement, parameters=None):
            statements.append(" ".join(str(statement).split()))

        def fetchone(self):
            return self._response

        def fetchall(self):
            return self._response

    class Connection:
        def __init__(self, response):
            self._response = response

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def cursor(self):
            return Cursor(self._response)

    def connect():
        return Connection(responses.pop(0))

    science = PostgresScienceRepository(connect)
    revision = science.put(
        "projects", {"id": "p1", "title": "Shared Project"}, 2
    )
    assert revision == 3
    assert science.records("projects") == (
        {"id": "p1", "title": "Shared Project"},
    )
    assert any("FOR UPDATE" in statement for statement in statements)
    assert any("ON CONFLICT(collection_name,record_id)" in statement for statement in statements)

    class Source:
        def records(self, collection):
            if collection == "projects":
                return ({"id": "p1", "title": "Shared Project"},)
            return ()

    projection = ServerSearchProjection(tmp_path / "search.sqlite3")
    assert projection.rebuild(Source(), "org-a") == 1
    assert projection.candidates("Shared", 10)[0].resource_id == "p1"


def test_postgresql_access_adapter_reuses_full_contract_and_locks_audit() -> None:
    statements: list[str] = []

    class Cursor:
        rowcount = 1

        def __init__(self):
            self.description = ()
            self._rows = []

        def execute(self, statement, parameters=()):
            normalized = " ".join(str(statement).split())
            statements.append(normalized)
            if normalized.startswith("SELECT * FROM access_organizations"):
                self.description = tuple(
                    SimpleNamespace(name=name)
                    for name in ("organization_id", "name", "enabled")
                )
                self._rows = [("org-a", "Institute", 1)]
            elif "INSERT INTO access_audit_events" in normalized:
                self.description = (SimpleNamespace(name="sequence"),)
                self._rows = [(1,)]
            elif normalized.startswith(
                "SELECT event_hash FROM access_audit_chain"
            ):
                self.description = (SimpleNamespace(name="event_hash"),)
                self._rows = []

        def fetchone(self):
            return None if not self._rows else self._rows.pop(0)

        def fetchall(self):
            rows, self._rows = self._rows, []
            return rows

    class Connection:
        autocommit = False

        def cursor(self):
            return Cursor()

        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    repository = PostgresAccessControlRepository(Connection)
    repository.put_organization(Organization("org-a", "Institute", True))
    assert repository.organizations() == (
        Organization("org-a", "Institute", True),
    )
    repository.assign_role("subject", "researcher", "org-a", "p1")
    repository.append_audit(
        {
            "occurred_at_utc": datetime.now(UTC).isoformat(),
            "subject_id": "subject",
            "action": "view",
            "resource_type": "project",
            "resource_id": "p1",
            "allowed": True,
            "reason": "policy",
            "policy_ids": ["policy-1"],
            "request": {"purpose": "research"},
        }
    )
    assert any("ON CONFLICT DO NOTHING" in item for item in statements)
    assert any("pg_advisory_xact_lock" in item for item in statements)
    assert any("RETURNING sequence" in item for item in statements)


def test_project_export_is_governed_at_submit_status_and_download(
    tmp_path: Path,
) -> None:
    api, _, repository, _ = _server(tmp_path)
    search = ServerSearchProjection(tmp_path / "search.sqlite3")
    jobs = ServerJobStore(tmp_path / "jobs.sqlite3")
    exports = GovernedExportStore(
        tmp_path / "exports.sqlite3", tmp_path / "export-payloads"
    )
    api._search, api._jobs, api._exports = search, jobs, exports
    user = repository.identities()[0]
    administration = AccessAdministrationService(repository)
    administration.create_policy(
        name="Export project one", effect=PolicyEffect.ALLOW,
        source=PolicySource.DIRECT, subject_id=user.identity_id,
        actions=("export",), resource_types=("project",),
        organization_id="org-a", project_id="p1", purposes=("research",),
    )
    login = api.dispatch(
        "POST", "/api/v1/session", {},
        json.dumps({"username": "reader", "password": "correct horse battery"}).encode(),
    )
    headers = {"authorization": f"Bearer {json.loads(login.body)['access_token']}"}
    denied = api.dispatch(
        "POST", "/api/v1/jobs", headers,
        json.dumps({"job_type": "export_project", "project_id": "p2"}).encode(),
    )
    assert denied.status == 403
    submitted = api.dispatch(
        "POST", "/api/v1/jobs", headers,
        json.dumps({
            "job_type": "export_project", "project_id": "p1",
            "include_library_references": False,
        }).encode(),
    )
    assert submitted.status == 202
    job_id = json.loads(submitted.body)["job_id"]
    administration.create_policy(
        name="View export job", effect=PolicyEffect.ALLOW,
        source=PolicySource.DIRECT, subject_id=user.identity_id,
        actions=("view_job",), resource_types=("job",), resource_id=job_id,
        organization_id="org-a", project_id="p1", purposes=("administration",),
    )
    completed = run_one_job(
        jobs, search, tmp_path / "science.sqlite3", exports
    )
    assert completed is not None and completed.status == "succeeded"
    assert "path" not in completed.result
    export_id = completed.result["export_id"]
    assert api.dispatch(
        "GET", f"/api/v1/exports/{export_id}", headers, b""
    ).status == 404
    administration.create_policy(
        name="Download project export", effect=PolicyEffect.ALLOW,
        source=PolicySource.DIRECT, subject_id=user.identity_id,
        actions=("download_export",), resource_types=("project_export",),
        organization_id="org-a", project_id="p1", purposes=("research",),
    )
    response = api.dispatch(
        "GET", f"/api/v1/exports/{export_id}",
        {**headers, "range": "bytes=0-3"}, b"",
    )
    assert response.status == 206
    assert response.body == b"PK\x03\x04"
    full = api.dispatch("GET", f"/api/v1/exports/{export_id}", headers, b"")
    assert api.dispatch(
        "GET", f"/api/v1/exports/{export_id}/attestation", headers, b""
    ).status == 404
    archive = tmp_path / "download.zip"
    archive.write_bytes(full.body)
    with zipfile.ZipFile(archive) as package:
        assert "manifest.json" in package.namelist()
        manifest = json.loads(package.read("manifest.json"))
    assert manifest["project"]["id"] == "p1"
    administration.create_policy(
        name="Revoke project export", effect=PolicyEffect.ALLOW,
        source=PolicySource.DIRECT, subject_id=user.identity_id,
        actions=("revoke_export",), resource_types=("project_export",),
        organization_id="org-a", project_id="p1", purposes=("administration",),
    )
    assert api.dispatch(
        "DELETE", f"/api/v1/exports/{export_id}",
        {**headers, "x-fieldora-purpose": "administration"}, b"",
    ).status == 204
    assert api.dispatch(
        "GET", f"/api/v1/exports/{export_id}", headers, b""
    ).status == 404
    try:
        administration.create_project_contract_grant(
            title="Invalid",
            organization_id="org-a",
            project_id="p1",
            subject_id=user.identity_id,
            starts_at_utc="2026-01-02T00:00:00+00:00",
            ends_at_utc="2026-01-01T00:00:00+00:00",
            rights=("export",),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("unordered contract dates were accepted")
    revoked = exports._stored_record(export_id)
    assert revoked is not None and revoked.revoked_at_utc and revoked.purged_at_utc
    assert not (tmp_path / "export-payloads" / revoked.relative_path).exists()

    expired = exports.create(
        "expired-job", user.identity_id, "org-a", "p1",
        lambda destination: destination.write_bytes(b"expired"),
    )
    connection = sqlite3.connect(tmp_path / "exports.sqlite3")
    connection.execute(
        "UPDATE governed_exports SET expires_at_utc='2000-01-01T00:00:00+00:00' "
        "WHERE export_id=?",
        (expired.export_id,),
    )
    connection.commit()
    connection.close()
    assert api.dispatch(
        "GET", f"/api/v1/exports/{expired.export_id}", headers, b""
    ).status == 404
    assert exports.purge_expired() == 1
    purged = exports._stored_record(expired.export_id)
    assert purged is not None and purged.purged_at_utc
    assert not (tmp_path / "export-payloads" / purged.relative_path).exists()


def test_export_store_upgrades_00811_schema_without_losing_metadata(
    tmp_path: Path,
) -> None:
    database = tmp_path / "exports.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE governed_exports("
        "export_id TEXT PRIMARY KEY,job_id TEXT NOT NULL UNIQUE,"
        "subject_id TEXT NOT NULL,organization_id TEXT NOT NULL,"
        "project_id TEXT NOT NULL,filename TEXT NOT NULL,"
        "relative_path TEXT NOT NULL UNIQUE,size_bytes INTEGER NOT NULL,"
        "sha256 TEXT NOT NULL,created_at_utc TEXT NOT NULL,"
        "expires_at_utc TEXT NOT NULL)"
    )
    connection.commit()
    connection.close()
    GovernedExportStore(database, tmp_path / "payloads")
    connection = sqlite3.connect(database)
    columns = {
        row[1] for row in connection.execute(
            "PRAGMA table_info(governed_exports)"
        ).fetchall()
    }
    connection.close()
    assert {
        "revoked_at_utc", "purged_at_utc", "signing_key_id", "signature_base64"
    } <= columns


def test_active_project_contract_grants_export_and_suspension_revokes_it(
    tmp_path: Path,
) -> None:
    api, _, repository, _ = _server(tmp_path)
    search = ServerSearchProjection(tmp_path / "search.sqlite3")
    jobs = ServerJobStore(tmp_path / "jobs.sqlite3")
    exports = GovernedExportStore(
        tmp_path / "exports.sqlite3", tmp_path / "export-payloads"
    )
    api._search, api._jobs, api._exports = search, jobs, exports
    user = repository.identities()[0]
    administration = AccessAdministrationService(repository)
    now = datetime.now(UTC)
    contract, policies = administration.create_project_contract_grant(
        title="Time-bounded field study",
        organization_id="org-a",
        project_id="p1",
        subject_id=user.identity_id,
        starts_at_utc=(now - timedelta(days=1)).isoformat(),
        ends_at_utc=(now + timedelta(days=1)).isoformat(),
        rights=("export", "view_job", "download_export"),
    )
    assert len(policies) == 3
    assert repository.contract(contract.contract_id).terms["project_id"] == "p1"
    login = api.dispatch(
        "POST", "/api/v1/session", {},
        json.dumps({"username": "reader", "password": "correct horse battery"}).encode(),
    )
    headers = {"authorization": f"Bearer {json.loads(login.body)['access_token']}"}
    assert api.dispatch(
        "POST", "/api/v1/jobs", headers,
        json.dumps({"job_type": "export_project", "project_id": "p2"}).encode(),
    ).status == 403
    submitted = api.dispatch(
        "POST", "/api/v1/jobs", headers,
        json.dumps({"job_type": "export_project", "project_id": "p1"}).encode(),
    )
    assert submitted.status == 202
    job_id = json.loads(submitted.body)["job_id"]
    completed = run_one_job(
        jobs, search, tmp_path / "science.sqlite3", exports,
        ExportSigningIdentity.generate(
            "study-server",
            tmp_path / "signing" / "private.pem",
            tmp_path / "signing" / "trusted.json",
        ),
    )
    assert completed is not None and completed.status == "succeeded"
    job = api.dispatch("GET", f"/api/v1/jobs/{job_id}", headers, b"")
    assert job.status == 200
    export_id = json.loads(job.body)["result"]["export_id"]
    downloaded = api.dispatch(
        "GET", f"/api/v1/exports/{export_id}", headers, b""
    )
    assert downloaded.status == 200
    attestation_response = api.dispatch(
        "GET", f"/api/v1/exports/{export_id}/attestation", headers, b""
    )
    assert attestation_response.status == 200
    attestation = json.loads(attestation_response.body)
    package = tmp_path / "signed-export.zip"
    package.write_bytes(downloaded.body)
    assert verify_export_attestation(
        package, attestation, tmp_path / "signing" / "trusted.json"
    ) == attestation["package_sha256"]
    package.write_bytes(downloaded.body + b"tampered")
    try:
        verify_export_attestation(
            package, attestation, tmp_path / "signing" / "trusted.json"
        )
    except ValueError:
        pass
    else:
        raise AssertionError("tampered signed export was accepted")
    ExportSigningIdentity.generate(
        "other-server",
        tmp_path / "other-signing" / "private.pem",
        tmp_path / "other-signing" / "trusted.json",
    )
    package.write_bytes(downloaded.body)
    try:
        verify_export_attestation(
            package, attestation, tmp_path / "other-signing" / "trusted.json"
        )
    except ValueError:
        pass
    else:
        raise AssertionError("export signed by an untrusted key was accepted")
    administration.set_contract_status(contract.contract_id, "suspended")
    assert api.dispatch(
        "GET", f"/api/v1/jobs/{job_id}", headers, b""
    ).status == 404
    assert api.dispatch(
        "GET", f"/api/v1/exports/{export_id}", headers, b""
    ).status == 404
    assert api.dispatch(
        "GET", f"/api/v1/exports/{export_id}/attestation", headers, b""
    ).status == 404


def test_project_export_is_encrypted_for_one_recipient_key(
    tmp_path: Path,
) -> None:
    api, _, repository, _ = _server(tmp_path)
    search = ServerSearchProjection(tmp_path / "search.sqlite3")
    jobs = ServerJobStore(tmp_path / "jobs.sqlite3")
    exports = GovernedExportStore(
        tmp_path / "exports.sqlite3", tmp_path / "export-payloads"
    )
    api._search, api._jobs, api._exports = search, jobs, exports
    user = repository.identities()[0]
    now = datetime.now(UTC)
    AccessAdministrationService(repository).create_project_contract_grant(
        title="Encrypted delivery",
        organization_id="org-a",
        project_id="p1",
        subject_id=user.identity_id,
        starts_at_utc=(now - timedelta(days=1)).isoformat(),
        ends_at_utc=(now + timedelta(days=1)).isoformat(),
        rights=("export", "view_job", "download_export"),
    )
    recipient_private = tmp_path / "recipient" / "private.pem"
    recipient_public_path = tmp_path / "recipient" / "public.json"
    generate_recipient_identity(
        "field-team-a", recipient_private, recipient_public_path
    )
    recipient_public = json.loads(
        recipient_public_path.read_text(encoding="utf-8")
    )
    login = api.dispatch(
        "POST", "/api/v1/session", {},
        json.dumps({"username": "reader", "password": "correct horse battery"}).encode(),
    )
    headers = {"authorization": f"Bearer {json.loads(login.body)['access_token']}"}
    assert api.dispatch(
        "POST", "/api/v1/jobs", headers,
        json.dumps({
            "job_type": "export_project", "project_id": "p1",
            "recipient_public_key": {**recipient_public, "public_key": "bad"},
        }).encode(),
    ).status == 400
    submitted = api.dispatch(
        "POST", "/api/v1/jobs", headers,
        json.dumps({
            "job_type": "export_project", "project_id": "p1",
            "recipient_public_key": recipient_public,
        }).encode(),
    )
    assert submitted.status == 202
    job_id = json.loads(submitted.body)["job_id"]
    queued = jobs.job(job_id)
    assert queued is not None
    assert "private" not in json.dumps(queued.payload).casefold()
    completed = run_one_job(
        jobs, search, tmp_path / "science.sqlite3", exports,
        ExportSigningIdentity.generate(
            "encryption-server",
            tmp_path / "server-signing" / "private.pem",
            tmp_path / "server-signing" / "trusted.json",
        ),
    )
    assert completed is not None and completed.status == "succeeded"
    assert completed.result["encrypted"] is True
    assert completed.result["recipient_key_id"] == "field-team-a"
    export_id = completed.result["export_id"]
    response = api.dispatch(
        "GET", f"/api/v1/exports/{export_id}", headers, b""
    )
    assert response.status == 200
    assert response.content_type == "application/vnd.fieldora.project-encrypted"
    assert not response.body.startswith(b"PK")
    encrypted = tmp_path / "download.fieldora-encrypted"
    encrypted.write_bytes(response.body)
    attestation = json.loads(
        api.dispatch(
            "GET", f"/api/v1/exports/{export_id}/attestation", headers, b""
        ).body
    )
    verify_export_attestation(
        encrypted, attestation, tmp_path / "server-signing" / "trusted.json"
    )
    decrypted = tmp_path / "decrypted.zip"
    assert decrypt_project_export(
        encrypted, decrypted, recipient_private
    ) == "field-team-a"
    with zipfile.ZipFile(decrypted) as package:
        assert json.loads(package.read("manifest.json"))["project"]["id"] == "p1"
    wrong_private = tmp_path / "wrong" / "private.pem"
    generate_recipient_identity(
        "field-team-b", wrong_private, tmp_path / "wrong" / "public.json"
    )
    try:
        decrypt_project_export(encrypted, tmp_path / "wrong.zip", wrong_private)
    except ValueError:
        pass
    else:
        raise AssertionError("encrypted export opened with the wrong recipient key")
    tampered = bytearray(response.body)
    tampered[-20] ^= 1
    encrypted.write_bytes(tampered)
    try:
        decrypt_project_export(encrypted, tmp_path / "tampered.zip", recipient_private)
    except ValueError:
        pass
    else:
        raise AssertionError("tampered encrypted export was accepted")


def test_remote_contract_administration_is_pbac_and_tenant_scoped(
    tmp_path: Path,
) -> None:
    api, _, repository, _ = _server(tmp_path)
    api._access_repository = repository
    administration = AccessAdministrationService(repository)
    administrator = repository.identities()[0]
    guest = administration.create_identity("Guest", "org-a", IdentityKind.USER)
    administration.create_organization("org-b", "Other organization")
    other = administration.create_identity("Other", "org-b", IdentityKind.USER)
    now = datetime.now(UTC)
    other_contract, _ = administration.create_project_contract_grant(
        title="Other tenant",
        organization_id="org-b",
        project_id="other-project",
        subject_id=other.identity_id,
        starts_at_utc=(now - timedelta(days=1)).isoformat(),
        ends_at_utc=(now + timedelta(days=1)).isoformat(),
        rights=("view",),
    )
    login = api.dispatch(
        "POST", "/api/v1/session", {},
        json.dumps({"username": "reader", "password": "correct horse battery"}).encode(),
    )
    headers = {
        "authorization": f"Bearer {json.loads(login.body)['access_token']}",
        "x-fieldora-purpose": "administration",
    }
    payload = {
        "title": "Visiting researcher",
        "organization_id": "org-a",
        "project_id": "p1",
        "subject_id": guest.identity_id,
        "starts_at_utc": (now - timedelta(hours=1)).isoformat(),
        "ends_at_utc": (now + timedelta(days=30)).isoformat(),
        "rights": ["view", "export"],
    }
    assert api.dispatch(
        "POST", "/api/v1/admin/contracts", headers, json.dumps(payload).encode()
    ).status == 403
    administration.create_policy(
        name="Project contract administrator",
        effect=PolicyEffect.ALLOW,
        source=PolicySource.DIRECT,
        subject_id=administrator.identity_id,
        actions=("administer_contracts",),
        resource_types=("contract",),
        organization_id="org-a",
        project_id="p1",
        purposes=("administration",),
    )
    created = api.dispatch(
        "POST", "/api/v1/admin/contracts", headers, json.dumps(payload).encode()
    )
    assert created.status == 201
    contract_id = json.loads(created.body)["contract"]["contract_id"]
    assert len(json.loads(created.body)["policy_ids"]) == 2
    assert api.dispatch(
        "POST", "/api/v1/admin/contracts", headers,
        json.dumps({**payload, "project_id": "p2"}).encode(),
    ).status == 403
    listing = json.loads(
        api.dispatch("GET", "/api/v1/admin/contracts", headers, b"").body
    )
    assert [item["contract_id"] for item in listing["items"]] == [contract_id]
    assert api.dispatch(
        "GET", f"/api/v1/admin/contracts/{other_contract.contract_id}", headers, b""
    ).status == 404
    assert PolicyDecisionService(repository).decide(
        AccessRequest(
            guest.identity_id, "view", "project", "p1",
            "org-a", "p1", "research",
        )
    ).allowed
    assert api.dispatch(
        "POST", f"/api/v1/admin/contracts/{contract_id}/status", headers,
        json.dumps({"status": "invalid"}).encode(),
    ).status == 400
    suspended = api.dispatch(
        "POST", f"/api/v1/admin/contracts/{contract_id}/status", headers,
        json.dumps({"status": "suspended"}).encode(),
    )
    assert suspended.status == 200
    assert json.loads(suspended.body)["contract"]["status"] == "suspended"
    assert not PolicyDecisionService(repository).decide(
        AccessRequest(
            guest.identity_id, "view", "project", "p1",
            "org-a", "p1", "research",
        )
    ).allowed


def test_limited_web_client_exposes_accessible_contract_workspace() -> None:
    root = Path(__file__).parents[1] / "src/natureai_next/resources/server_web"
    html = (root / "index.html").read_text(encoding="utf-8")
    script = (root / "app.js").read_text(encoding="utf-8")
    assert 'role="tablist"' in html and 'role="tabpanel"' in html
    assert 'aria-controls="contracts-panel"' in html
    assert 'id="contract-form"' in html
    assert 'name="contract-right"' in html
    assert 'role="status"' in html and 'aria-live="polite"' in html
    assert "/api/v1/admin/contracts" in script
    assert "/api/v1/admin/contract-approvals" in script
    assert 'aria-controls="approvals-panel"' in html
    assert "/api/v1/admin/contract-expiry" in script
    assert 'aria-controls="expiry-panel"' in html
    assert "/approve" in script and "approval_required" in script
    assert "required_approvals" in script and 'id="contract-required-approvals"' in html
    assert 'purpose:"administration"' in script
    assert "textContent" in script and "esc=value=>" in script
    assert "sessionStorage" in script and "localStorage" not in script


def test_contract_proposal_requires_different_authorized_approver(
    tmp_path: Path,
) -> None:
    api, authentication, repository, _ = _server(tmp_path)
    api._access_repository = repository
    administration = AccessAdministrationService(repository)
    maker = repository.identities()[0]
    checker = administration.create_identity(
        "Contract checker", "org-a", IdentityKind.USER
    )
    guest = administration.create_identity("Approved guest", "org-a", IdentityKind.USER)
    authentication.set_password(
        checker.identity_id, "checker", "independent approval password"
    )
    for subject, action in (
        (maker.identity_id, "administer_contracts"),
        (maker.identity_id, "approve_contracts"),
        (checker.identity_id, "approve_contracts"),
    ):
        administration.create_policy(
            name=f"{action} for {subject}",
            effect=PolicyEffect.ALLOW,
            source=PolicySource.DIRECT,
            subject_id=subject,
            actions=(action,),
            resource_types=("contract",),
            organization_id="org-a",
            project_id="p1",
            purposes=("administration",),
        )
    now = datetime.now(UTC)
    payload = {
        "title": "Independently approved study",
        "organization_id": "org-a",
        "project_id": "p1",
        "subject_id": guest.identity_id,
        "starts_at_utc": (now - timedelta(hours=1)).isoformat(),
        "ends_at_utc": (now + timedelta(days=7)).isoformat(),
        "rights": ["view"],
        "approval_required": True,
    }
    maker_login = api.dispatch(
        "POST", "/api/v1/session", {},
        json.dumps({"username": "reader", "password": "correct horse battery"}).encode(),
    )
    maker_headers = {
        "authorization": f"Bearer {json.loads(maker_login.body)['access_token']}",
        "x-fieldora-purpose": "administration",
    }
    proposed = api.dispatch(
        "POST", "/api/v1/admin/contracts", maker_headers,
        json.dumps(payload).encode(),
    )
    assert proposed.status == 201
    proposed_body = json.loads(proposed.body)
    contract_id = proposed_body["contract"]["contract_id"]
    assert proposed_body["contract"]["status"] == "proposed"
    assert proposed_body["policy_ids"] == []
    assert not any(
        policy.source_id == contract_id for policy in repository.policies()
    )
    assert not PolicyDecisionService(repository).decide(
        AccessRequest(
            guest.identity_id, "view", "project", "p1",
            "org-a", "p1", "research",
        )
    ).allowed
    assert api.dispatch(
        "POST", f"/api/v1/admin/contracts/{contract_id}/approve",
        maker_headers, b"{}",
    ).status == 409
    assert api.dispatch(
        "POST", f"/api/v1/admin/contracts/{contract_id}/status",
        maker_headers, json.dumps({"status": "active"}).encode(),
    ).status == 400
    checker_login = api.dispatch(
        "POST", "/api/v1/session", {},
        json.dumps({
            "username": "checker", "password": "independent approval password"
        }).encode(),
    )
    checker_headers = {
        "authorization": f"Bearer {json.loads(checker_login.body)['access_token']}",
        "x-fieldora-purpose": "administration",
    }
    approved = api.dispatch(
        "POST", f"/api/v1/admin/contracts/{contract_id}/approve",
        checker_headers, b"{}",
    )
    assert approved.status == 200
    approved_body = json.loads(approved.body)
    assert approved_body["contract"]["status"] == "active"
    assert approved_body["contract"]["terms"]["approved_by"] == checker.identity_id
    assert len(approved_body["policy_ids"]) == 1
    assert PolicyDecisionService(repository).decide(
        AccessRequest(
            guest.identity_id, "view", "project", "p1",
            "org-a", "p1", "research",
        )
    ).allowed
    assert api.dispatch(
        "POST", f"/api/v1/admin/contracts/{contract_id}/approve",
        checker_headers, b"{}",
    ).status == 409


def test_contract_approval_quorum_grants_access_only_after_final_approval(
    tmp_path: Path,
) -> None:
    api, authentication, repository, _ = _server(tmp_path)
    api._access_repository = repository
    administration = AccessAdministrationService(repository)
    maker = repository.identities()[0]
    first = administration.create_identity(
        "First contract checker", "org-a", IdentityKind.USER
    )
    second = administration.create_identity(
        "Second contract checker", "org-a", IdentityKind.USER
    )
    guest = administration.create_identity("Quorum guest", "org-a", IdentityKind.USER)
    for identity, username in ((first, "checker-one"), (second, "checker-two")):
        authentication.set_password(
            identity.identity_id, username, "independent approval password"
        )
        administration.create_policy(
            name=f"Approve contracts for {username}",
            effect=PolicyEffect.ALLOW,
            source=PolicySource.DIRECT,
            subject_id=identity.identity_id,
            actions=("approve_contracts",),
            resource_types=("contract",),
            organization_id="org-a",
            project_id="p1",
            purposes=("administration",),
        )
    administration.create_policy(
        name="Administer quorum contracts",
        effect=PolicyEffect.ALLOW,
        source=PolicySource.DIRECT,
        subject_id=maker.identity_id,
        actions=("administer_contracts",),
        resource_types=("contract",),
        organization_id="org-a",
        project_id="p1",
        purposes=("administration",),
    )
    now = datetime.now(UTC)
    maker_login = api.dispatch(
        "POST", "/api/v1/session", {},
        json.dumps({"username": "reader", "password": "correct horse battery"}).encode(),
    )
    maker_headers = {
        "authorization": f"Bearer {json.loads(maker_login.body)['access_token']}",
        "x-fieldora-purpose": "administration",
    }
    created = api.dispatch(
        "POST", "/api/v1/admin/contracts", maker_headers,
        json.dumps({
            "title": "Two-person approval study",
            "organization_id": "org-a",
            "project_id": "p1",
            "subject_id": guest.identity_id,
            "starts_at_utc": (now - timedelta(hours=1)).isoformat(),
            "ends_at_utc": (now + timedelta(days=7)).isoformat(),
            "rights": ["view", "search"],
            "approval_required": True,
            "required_approvals": 2,
        }).encode(),
    )
    assert created.status == 201
    contract_id = json.loads(created.body)["contract"]["contract_id"]

    def headers_for(username: str) -> dict[str, str]:
        login = api.dispatch(
            "POST", "/api/v1/session", {},
            json.dumps({
                "username": username,
                "password": "independent approval password",
            }).encode(),
        )
        return {
            "authorization": f"Bearer {json.loads(login.body)['access_token']}",
            "x-fieldora-purpose": "administration",
        }

    first_approval = api.dispatch(
        "POST", f"/api/v1/admin/contracts/{contract_id}/approve",
        headers_for("checker-one"), b"{}",
    )
    first_body = json.loads(first_approval.body)
    assert first_approval.status == 200
    assert first_body["approval_complete"] is False
    assert first_body["contract"]["status"] == "proposed"
    assert first_body["contract"]["terms"]["approval_count"] == 1
    assert first_body["policy_ids"] == []
    assert not any(item.source_id == contract_id for item in repository.policies())
    assert not PolicyDecisionService(repository).decide(
        AccessRequest(
            guest.identity_id, "view", "project", "p1",
            "org-a", "p1", "research",
        )
    ).allowed
    assert api.dispatch(
        "POST", f"/api/v1/admin/contracts/{contract_id}/approve",
        headers_for("checker-one"), b"{}",
    ).status == 409

    final_approval = api.dispatch(
        "POST", f"/api/v1/admin/contracts/{contract_id}/approve",
        headers_for("checker-two"), b"{}",
    )
    final_body = json.loads(final_approval.body)
    assert final_approval.status == 200
    assert final_body["approval_complete"] is True
    assert final_body["contract"]["status"] == "active"
    assert final_body["contract"]["terms"]["approval_count"] == 2
    assert len(final_body["contract"]["terms"]["approvals"]) == 2
    assert len(final_body["policy_ids"]) == 2
    assert PolicyDecisionService(repository).decide(
        AccessRequest(
            guest.identity_id, "view", "project", "p1",
            "org-a", "p1", "research",
        )
    ).allowed


def test_contract_approval_quorum_is_bounded(tmp_path: Path) -> None:
    _, _, repository, _ = _server(tmp_path)
    administration = AccessAdministrationService(repository)
    maker = repository.identities()[0]
    guest = administration.create_identity("Bounded guest", "org-a", IdentityKind.USER)
    now = datetime.now(UTC)
    values = {
        "requested_by": maker.identity_id,
        "title": "Invalid quorum",
        "organization_id": "org-a",
        "project_id": "p1",
        "subject_id": guest.identity_id,
        "starts_at_utc": now.isoformat(),
        "ends_at_utc": (now + timedelta(days=1)).isoformat(),
        "rights": ("view",),
    }
    for invalid in (0, 11, True):
        with pytest.raises(ValueError):
            administration.propose_project_contract_grant(
                required_approvals=invalid, **values
            )


def test_approval_queue_requires_approve_pbac_without_admin_rights(
    tmp_path: Path,
) -> None:
    api, authentication, repository, _ = _server(tmp_path)
    api._access_repository = repository
    administration = AccessAdministrationService(repository)
    maker = repository.identities()[0]
    approver = administration.create_identity(
        "Delegated approver", "org-a", IdentityKind.USER
    )
    guest = administration.create_identity("Queue guest", "org-a", IdentityKind.USER)
    authentication.set_password(
        approver.identity_id, "delegated-approver", "approval queue password"
    )
    administration.create_policy(
        name="Approve p1 contracts",
        effect=PolicyEffect.ALLOW,
        source=PolicySource.DIRECT,
        subject_id=approver.identity_id,
        actions=("approve_contracts",),
        resource_types=("contract",),
        organization_id="org-a",
        project_id="p1",
        purposes=("administration",),
    )
    now = datetime.now(UTC)
    common = {
        "requested_by": maker.identity_id,
        "organization_id": "org-a",
        "subject_id": guest.identity_id,
        "starts_at_utc": now.isoformat(),
        "ends_at_utc": (now + timedelta(days=2)).isoformat(),
        "rights": ("view",),
    }
    visible = administration.propose_project_contract_grant(
        title="Visible approval", project_id="p1", required_approvals=1, **common
    )
    administration.propose_project_contract_grant(
        title="Concealed approval", project_id="p2", required_approvals=1, **common
    )
    login = api.dispatch(
        "POST", "/api/v1/session", {},
        json.dumps({
            "username": "delegated-approver",
            "password": "approval queue password",
        }).encode(),
    )
    headers = {
        "authorization": f"Bearer {json.loads(login.body)['access_token']}",
        "x-fieldora-purpose": "administration",
    }
    contracts = json.loads(api.dispatch(
        "GET", "/api/v1/admin/contracts", headers, b""
    ).body)
    assert contracts["items"] == []
    queue = api.dispatch(
        "GET", "/api/v1/admin/contract-approvals?limit=1", headers, b""
    )
    assert queue.status == 200
    queue_body = json.loads(queue.body)
    assert [item["contract_id"] for item in queue_body["items"]] == [
        visible.contract_id
    ]
    assert queue_body["next_cursor"] == ""
    approved = api.dispatch(
        "POST", f"/api/v1/admin/contracts/{visible.contract_id}/approve",
        headers, b"{}",
    )
    assert approved.status == 200
    assert json.loads(api.dispatch(
        "GET", "/api/v1/admin/contract-approvals", headers, b""
    ).body)["items"] == []


def test_contract_expiry_queue_is_bounded_and_pbac_filtered(tmp_path: Path) -> None:
    api, _, repository, _ = _server(tmp_path)
    api._access_repository = repository
    administration = AccessAdministrationService(repository)
    administrator = repository.identities()[0]
    guest = administration.create_identity("Expiry guest", "org-a", IdentityKind.USER)
    administration.create_policy(
        name="Administer p1 expiry",
        effect=PolicyEffect.ALLOW,
        source=PolicySource.DIRECT,
        subject_id=administrator.identity_id,
        actions=("administer_contracts",),
        resource_types=("contract",),
        organization_id="org-a",
        project_id="p1",
        purposes=("administration",),
    )
    now = datetime.now(UTC)

    def contract(title: str, project_id: str, start, end):
        return administration.create_project_contract_grant(
            title=title,
            organization_id="org-a",
            project_id=project_id,
            subject_id=guest.identity_id,
            starts_at_utc=start.isoformat(),
            ends_at_utc=end.isoformat(),
            rights=("view",),
        )[0]

    due = contract("Due soon", "p1", now - timedelta(days=1), now + timedelta(days=2))
    contract("Outside window", "p1", now, now + timedelta(days=40))
    contract("Already expired", "p1", now - timedelta(days=2), now - timedelta(days=1))
    contract("Concealed project", "p2", now, now + timedelta(days=2))
    login = api.dispatch(
        "POST", "/api/v1/session", {},
        json.dumps({"username": "reader", "password": "correct horse battery"}).encode(),
    )
    headers = {
        "authorization": f"Bearer {json.loads(login.body)['access_token']}",
        "x-fieldora-purpose": "administration",
    }
    response = api.dispatch(
        "GET", "/api/v1/admin/contract-expiry?within_days=30&limit=10",
        headers, b"",
    )
    assert response.status == 200
    body = json.loads(response.body)
    assert body["within_days"] == 30
    assert [item["contract_id"] for item in body["items"]] == [due.contract_id]
    assert api.dispatch(
        "GET", "/api/v1/admin/contract-expiry?within_days=0", headers, b""
    ).status == 400
    assert api.dispatch(
        "GET", "/api/v1/admin/contract-expiry?within_days=366", headers, b""
    ).status == 400


def test_s3_compatible_media_adapter_preserves_governed_range_contract(
    tmp_path: Path,
) -> None:
    class FakeS3:
        def __init__(self) -> None:
            self.objects = {}
            self.puts = []

        def put_object(self, **kwargs):
            payload = kwargs["Body"].read()
            self.objects[(kwargs["Bucket"], kwargs["Key"])] = payload
            self.puts.append({**kwargs, "Body": payload})

        def get_object(self, **kwargs):
            payload = self.objects[(kwargs["Bucket"], kwargs["Key"])]
            start, end = (
                int(value) for value in kwargs["Range"].removeprefix("bytes=").split("-")
            )
            return {"Body": io.BytesIO(payload[start:end + 1])}

        def delete_object(self, **kwargs):
            self.objects.pop((kwargs["Bucket"], kwargs["Key"]), None)

    client = FakeS3()
    objects = S3ObjectStore(client, "research-media", "tenant-a/media")
    media = GovernedMediaStore(
        tmp_path / "media.sqlite3", tmp_path / "staging", object_store=objects
    )
    source = tmp_path / "observation.wav"
    source.write_bytes(b"0123456789")
    record = media.register(source, "org-a", "p1")
    assert media.read_range(record, 2, 6) == b"23456"
    assert client.puts[0]["Bucket"] == "research-media"
    assert client.puts[0]["Key"].startswith("tenant-a/media/")
    assert client.puts[0]["ContentType"] == "audio/x-wav"
    assert client.puts[0]["Metadata"]["sha256"] == hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    assert "http" not in record.relative_path
    with pytest.raises(ValueError):
        objects.read_range("../escape", 0, 1)


def test_s3_compatible_media_upload_publishes_only_after_integrity(
    tmp_path: Path,
) -> None:
    class FakeS3:
        def __init__(self) -> None:
            self.objects = {}

        def put_object(self, **kwargs):
            self.objects[(kwargs["Bucket"], kwargs["Key"])] = kwargs["Body"].read()

        def get_object(self, **kwargs):
            payload = self.objects[(kwargs["Bucket"], kwargs["Key"])]
            start, end = map(
                int, kwargs["Range"].removeprefix("bytes=").split("-")
            )
            return {"Body": io.BytesIO(payload[start:end + 1])}

        def delete_object(self, **kwargs):
            self.objects.pop((kwargs["Bucket"], kwargs["Key"]), None)

    client = FakeS3()
    media = GovernedMediaStore(
        tmp_path / "media.sqlite3",
        tmp_path / "staging",
        object_store=S3ObjectStore(client, "research-media"),
    )
    payload = b"governed-upload"
    upload = media.begin_upload(
        "subject", "org-a", "p1", "sample.bin", "application/octet-stream",
        len(payload), hashlib.sha256(payload).hexdigest(),
    )
    pending = media.append_upload(upload, 0, payload[:5])
    assert pending.received_bytes == 5
    assert client.objects == {}
    record = media.append_upload(pending, 5, payload[5:])
    assert media.upload(upload.upload_id) is None
    assert media.read_range(record, 0, len(payload) - 1) == payload


def test_server_cli_accepts_explicit_s3_compatible_media_configuration() -> None:
    args = build_parser().parse_args([
        "--media-object-store", "s3",
        "--s3-bucket", "research-media",
        "--s3-prefix", "institution-a/media",
        "--s3-endpoint-url", "https://objects.example",
        "--s3-region", "eu-central-1",
        "serve",
    ])
    assert args.media_object_store == "s3"
    assert args.s3_bucket == "research-media"
    assert args.s3_prefix == "institution-a/media"
    assert args.s3_endpoint_url == "https://objects.example"
    assert args.s3_region == "eu-central-1"


def test_listener_security_requires_tls_outside_loopback(tmp_path: Path) -> None:
    certificate = tmp_path / "server.crt"
    private_key = tmp_path / "server.key"
    assert validate_listener_security("127.0.0.1", None, None) is False
    assert validate_listener_security("::1", None, None) is False
    with pytest.raises(ValueError):
        validate_listener_security("0.0.0.0", None, None)
    assert validate_listener_security(
        "0.0.0.0", None, None, allow_insecure_http=True
    ) is False
    with pytest.raises(ValueError):
        validate_listener_security("0.0.0.0", certificate, None)
    assert validate_listener_security(
        "0.0.0.0", certificate, private_key
    ) is True


def test_https_server_uses_tls_12_or_newer_certificate_context(tmp_path: Path) -> None:
    api, _, _, _ = _server(tmp_path)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    certificate_path = tmp_path / "server.crt"
    private_key_path = tmp_path / "server.key"
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    private_key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    server = create_server(
        api, "127.0.0.1", 0,
        certificate=certificate_path, private_key=private_key_path,
    )
    try:
        assert isinstance(server.socket, ssl.SSLSocket)
        assert server.RequestHandlerClass.server_version == "Fieldora"
    finally:
        server.server_close()


def test_one_node_server_backup_verifies_and_restores_to_new_root(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "server"
    subsystems = data_root / "subsystems"
    subsystems.mkdir(parents=True)
    for name in ("access-control.sqlite3", "science.sqlite3", "server-jobs.sqlite3"):
        with sqlite3.connect(subsystems / name) as connection:
            connection.execute("CREATE TABLE evidence(id INTEGER PRIMARY KEY,value TEXT)")
            connection.execute("INSERT INTO evidence(value) VALUES(?)", (name,))
    media = data_root / "server-media" / "ab" / "asset.bin"
    export = data_root / "server-exports" / "project" / "export.zip"
    media.parent.mkdir(parents=True)
    export.parent.mkdir(parents=True)
    media.write_bytes(b"media evidence")
    export.write_bytes(b"export evidence")
    archive = tmp_path / "server-backup.zip"
    recovery = OneNodeServerRecovery()
    report = recovery.create(data_root, archive)
    assert report.files == 5
    assert report.sha256 == hashlib.sha256(archive.read_bytes()).hexdigest()
    media.write_bytes(b"changed after snapshot")
    restored = recovery.restore_to_new_root(
        archive, tmp_path / "restored-server"
    )
    assert (restored / "server-media" / "ab" / "asset.bin").read_bytes() == (
        b"media evidence"
    )
    assert (restored / "server-exports" / "project" / "export.zip").read_bytes() == (
        b"export evidence"
    )
    with sqlite3.connect(restored / "subsystems" / "science.sqlite3") as connection:
        assert connection.execute("SELECT value FROM evidence").fetchone()[0] == (
            "science.sqlite3"
        )
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    with pytest.raises(FileExistsError):
        recovery.restore_to_new_root(archive, restored)
    with zipfile.ZipFile(archive) as bundle:
        manifest = json.loads(bundle.read("manifest.json"))
    assert "S3-compatible objects when configured" in manifest["external_dependencies"]
    assert any("private key" in item for item in manifest["external_dependencies"])


def test_one_node_server_backup_rejects_undeclared_content(tmp_path: Path) -> None:
    data_root = tmp_path / "server"
    (data_root / "subsystems").mkdir(parents=True)
    with sqlite3.connect(data_root / "subsystems" / "science.sqlite3") as connection:
        connection.execute("CREATE TABLE evidence(id INTEGER PRIMARY KEY)")
    archive = tmp_path / "server-backup.zip"
    recovery = OneNodeServerRecovery()
    recovery.create(data_root, archive)
    with zipfile.ZipFile(archive, "a") as bundle:
        bundle.writestr("undeclared.txt", b"not in manifest")
    with pytest.raises(ValueError, match="do not match manifest"):
        recovery.verify(archive)


def test_restored_root_validation_composes_current_server_offline(
    tmp_path: Path,
) -> None:
    root = tmp_path / "restored"
    databases = root / "subsystems"
    SqliteAccessControlRepository(databases / "access-control.sqlite3")
    SqliteScienceRepository(databases / "science.sqlite3", default_science_snapshot)
    GovernedMediaStore(databases / "server-media.sqlite3", root / "server-media")
    ServerJobStore(databases / "server-jobs.sqlite3")
    GovernedExportStore(
        databases / "server-exports.sqlite3", root / "server-exports"
    )
    ServerSearchProjection(databases / "server-search.sqlite3")
    # Replace the exports database with its original schema to prove that
    # validation runs supported migrations in the isolated recovery copy.
    (databases / "server-exports.sqlite3").unlink()
    with sqlite3.connect(databases / "server-exports.sqlite3") as connection:
        MigrationRunner((SERVER_EXPORTS_MIGRATIONS[0],), "0.08.11").apply(connection)
    output = tmp_path / "readiness.json"
    report = OneNodeServerRecovery().validate_restored_root(root, output)
    assert report.fieldora_version == "5.4.0"
    assert len(report.databases) == 6
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["ready"] is True
    assert payload["api_status"] == "Fieldora"
    assert payload["databases"] == list(report.databases)
    with sqlite3.connect(databases / "server-exports.sqlite3") as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(governed_exports)")
        }
    assert {"revoked_at_utc", "purged_at_utc", "signing_key_id", "signature_base64"} <= (
        columns
    )


def test_restored_root_validation_fails_when_authoritative_database_is_missing(
    tmp_path: Path,
) -> None:
    root = tmp_path / "incomplete"
    (root / "subsystems").mkdir(parents=True)
    with pytest.raises(ValueError, match="missing required databases"):
        OneNodeServerRecovery().validate_restored_root(root)

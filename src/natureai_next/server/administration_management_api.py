"""Small-organisation user administration for the managed Fieldora server.

The routes in this module deliberately reuse the existing governance authority:
an identity must already be allowed to administer organisation contracts before it
can administer human identities in that same organisation. Password material is
never returned and disabling an account revokes its active sessions immediately.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from natureai_next.application.access_control import AccessAdministrationService
from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import IdentityKind
from natureai_next.server.api import ApiResponse
from natureai_next.server.web_capabilities import _has_authority

_BASE = "/api/v1/administration/users"
_ADMIN_RULE = ("administer_contracts", "contract", "administration")
_MAX_BODY = 32_768


def _repository(application: Any):
    return getattr(application, "_access_repository", None)


def _credential_rows(repository, organization_id: str) -> dict[str, dict[str, object]]:
    """Return non-secret credential metadata keyed by identity id."""
    connection = repository._factory.connect(read_only=True)
    try:
        rows = connection.execute(
            "SELECT c.identity_id,c.username,c.enabled "
            "FROM access_credentials c JOIN access_identities i "
            "ON i.identity_id=c.identity_id WHERE i.organization_id=?",
            (organization_id,),
        ).fetchall()
    finally:
        connection.close()
    return {
        str(row["identity_id"]): {
            "username": str(row["username"]),
            "credential_enabled": bool(row["enabled"]),
        }
        for row in rows
    }


def _direct_roles(repository, identity_id: str, organization_id: str) -> tuple[str, ...]:
    connection = repository._factory.connect(read_only=True)
    try:
        rows = connection.execute(
            "SELECT DISTINCT role_id FROM access_role_assignments "
            "WHERE subject_id=? AND organization_id IN ('',?) AND project_id='' "
            "ORDER BY role_id",
            (identity_id, organization_id),
        ).fetchall()
    finally:
        connection.close()
    return tuple(str(row[0]) for row in rows)


def _payload(
    repository, identity, credential: dict[str, object] | None = None
) -> dict[str, object]:
    credential = credential or {}
    return {
        "identity_id": identity.identity_id,
        "display_name": identity.display_name,
        "username": str(credential.get("username", "")),
        "enabled": bool(
            identity.enabled and credential.get("credential_enabled", True)
        ),
        "roles": list(
            _direct_roles(repository, identity.identity_id, identity.organization_id)
        ),
    }


def _json_body(body: bytes) -> dict[str, object]:
    if len(body) > _MAX_BODY:
        raise ValueError("request_too_large")
    value = json.loads(body)
    if not isinstance(value, dict):
        raise ValueError("invalid_request")
    return value


def _set_enabled(repository, identity_id: str, enabled: bool) -> None:
    identity = repository.identity(identity_id)
    if identity is None:
        raise LookupError(identity_id)
    repository.put_identity(replace(identity, enabled=enabled))
    now = datetime.now(UTC).isoformat()
    connection = repository._factory.connect()
    try:
        connection.execute(
            "UPDATE access_credentials SET enabled=? WHERE identity_id=?",
            (int(enabled), identity_id),
        )
        if not enabled:
            connection.execute(
                "UPDATE access_sessions SET revoked_at_utc=? "
                "WHERE identity_id=? AND revoked_at_utc=''",
                (now, identity_id),
            )
    finally:
        connection.close()


def _replace_roles(
    repository, identity_id: str, organization_id: str, roles: list[str]
) -> None:
    normalized = sorted({role.strip() for role in roles if role.strip()})
    if len(normalized) > 32 or any(len(role) > 100 for role in normalized):
        raise ValueError("invalid_roles")
    connection = repository._factory.connect()
    try:
        connection.execute(
            "DELETE FROM access_role_assignments "
            "WHERE subject_id=? AND organization_id=? AND project_id=''",
            (identity_id, organization_id),
        )
        connection.executemany(
            "INSERT OR IGNORE INTO access_role_assignments VALUES(?,?,?,?)",
            ((identity_id, role, organization_id, "") for role in normalized),
        )
    finally:
        connection.close()


def _remove_incomplete_user(repository, identity_id: str) -> None:
    """Remove a user that failed before account creation could complete."""
    connection = repository._factory.connect()
    try:
        connection.execute(
            "DELETE FROM access_sessions WHERE identity_id=?", (identity_id,)
        )
        connection.execute(
            "DELETE FROM access_credentials WHERE identity_id=?", (identity_id,)
        )
        connection.execute(
            "DELETE FROM access_role_assignments WHERE subject_id=?", (identity_id,)
        )
        connection.execute(
            "DELETE FROM access_identities WHERE identity_id=?", (identity_id,)
        )
    finally:
        connection.close()


def dispatch_administration_management(
    application: Any,
    method: str,
    target: str,
    headers: dict[str, str],
    body: bytes,
) -> ApiResponse | None:
    """Handle governed user-management routes, or return ``None`` when unrelated."""
    path = urlsplit(target).path
    if path != _BASE and not path.startswith(_BASE + "/"):
        return None
    try:
        _token, actor = application._identity(headers)
    except AuthenticationFailed:
        return ApiResponse.json(401, {"error": "unauthorized"})
    repository = _repository(application)
    if repository is None:
        return ApiResponse.json(404, {"error": "not_found"})
    if not _has_authority(application, actor, _ADMIN_RULE):
        return ApiResponse.json(403, {"error": "forbidden"})

    credentials = _credential_rows(repository, actor.organization_id)
    if path == _BASE and method == "GET":
        users = [
            _payload(repository, identity, credentials.get(identity.identity_id))
            for identity in repository.identities()
            if identity.kind is IdentityKind.USER
            and identity.organization_id == actor.organization_id
        ]
        return ApiResponse.json(200, {"items": users, "count": len(users)})

    if path == _BASE and method == "POST":
        identity = None
        try:
            data = _json_body(body)
            display_name = str(data["display_name"]).strip()
            username = str(data["username"]).strip().casefold()
            password = str(data["password"])
            roles_value = data.get("roles", [])
            if (
                not display_name
                or not username
                or len(password) < 12
                or not isinstance(roles_value, list)
            ):
                raise ValueError("invalid_request")
            if repository.credential(username) is not None:
                return ApiResponse.json(409, {"error": "username_exists"})
            roles = [str(role) for role in roles_value]
            identity = AccessAdministrationService(repository).create_identity(
                display_name, actor.organization_id, IdentityKind.USER
            )
            application._authentication.set_password(
                identity.identity_id, username, password
            )
            _replace_roles(
                repository, identity.identity_id, actor.organization_id, roles
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            if identity is not None:
                _remove_incomplete_user(repository, identity.identity_id)
            return ApiResponse.json(400, {"error": "invalid_user"})
        return ApiResponse.json(
            201,
            {
                "user": _payload(
                    repository,
                    identity,
                    {"username": username, "credential_enabled": True},
                )
            },
        )

    remainder = path.removeprefix(_BASE + "/")
    identity_id, separator, action = remainder.partition("/")
    target_identity = repository.identity(identity_id)
    if (
        not identity_id
        or target_identity is None
        or target_identity.kind is not IdentityKind.USER
        or target_identity.organization_id != actor.organization_id
    ):
        return ApiResponse.json(404, {"error": "user_not_found"})

    if separator and action == "status" and method == "POST":
        try:
            enabled = _json_body(body)["enabled"]
            if not isinstance(enabled, bool):
                raise ValueError("invalid_status")
            if identity_id == actor.identity_id and not enabled:
                return ApiResponse.json(
                    409, {"error": "cannot_disable_current_user"}
                )
            _set_enabled(repository, identity_id, enabled)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_status"})
        refreshed = repository.identity(identity_id)
        return ApiResponse.json(
            200,
            {
                "user": _payload(
                    repository,
                    refreshed,
                    _credential_rows(repository, actor.organization_id).get(identity_id),
                )
            },
        )

    if separator and action == "password" and method == "POST":
        try:
            password = str(_json_body(body)["password"])
            username = str(credentials.get(identity_id, {}).get("username", ""))
            if not username or not target_identity.enabled:
                raise ValueError("invalid_user")
            application._authentication.set_password(identity_id, username, password)
            now = datetime.now(UTC).isoformat()
            connection = repository._factory.connect()
            try:
                connection.execute(
                    "UPDATE access_sessions SET revoked_at_utc=? "
                    "WHERE identity_id=? AND revoked_at_utc=''",
                    (now, identity_id),
                )
            finally:
                connection.close()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_password"})
        return ApiResponse.json(200, {"reset": True})

    if separator and action == "roles" and method == "PUT":
        try:
            roles_value = _json_body(body)["roles"]
            if not isinstance(roles_value, list):
                raise ValueError("invalid_roles")
            _replace_roles(
                repository,
                identity_id,
                actor.organization_id,
                [str(role) for role in roles_value],
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_roles"})
        return ApiResponse.json(
            200,
            {"user": _payload(repository, target_identity, credentials.get(identity_id))},
        )

    return ApiResponse.json(404, {"error": "not_found"})

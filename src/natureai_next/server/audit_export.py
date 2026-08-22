"""Tenant-scoped, integrity-addressed security audit exports."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Protocol


class AuditRepository(Protocol):
    def audit_events(self, limit: int = 200) -> tuple[dict, ...]: ...

    def verify_audit_chain(self) -> tuple[bool, str]: ...


def _normalize_access_event(event: dict) -> dict:
    request = event.get("request", event.get("request_json", {}))
    if isinstance(request, str):
        request = json.loads(request)
    if not isinstance(request, dict):
        raise ValueError("audit event request is invalid")
    policy_ids = event.get("policy_ids", event.get("policy_ids_json", ()))
    if isinstance(policy_ids, str):
        policy_ids = json.loads(policy_ids)
    if not isinstance(policy_ids, (list, tuple)):
        raise ValueError("audit event policy ids are invalid")
    organization_id = str(request.get("organization_id", ""))
    if not organization_id:
        raise ValueError("audit event has no organization scope")
    return {
        "sequence": int(event["sequence"]),
        "occurred_at_utc": str(event["occurred_at_utc"]),
        "subject_id": str(event["subject_id"]),
        "action": str(event["action"]),
        "resource_type": str(event["resource_type"]),
        "resource_id": str(event["resource_id"]),
        "allowed": bool(event["allowed"]),
        "reason": str(event["reason"]),
        "policy_ids": list(policy_ids),
        "request": request,
        "organization_id": organization_id,
    }


def export_repository_audit(
    repository: AuditRepository,
    organization_id: str,
    destination: Path,
    *,
    limit: int = 10_000,
) -> Path:
    if not 1 <= limit <= 10_000:
        raise ValueError("audit export limit must be between 1 and 10000")
    verified, detail = repository.verify_audit_chain()
    if not verified:
        raise ValueError(f"audit chain verification failed: {detail}")
    events = tuple(
        _normalize_access_event(event)
        for event in repository.audit_events(limit=limit)
    )
    return export_tenant_audit(
        events,
        organization_id,
        destination,
        source_chain_verified=True,
        source_chain_detail=detail,
    )


def export_tenant_audit(
    events: tuple[dict, ...],
    organization_id: str,
    destination: Path,
    *,
    source_chain_verified: bool = False,
    source_chain_detail: str = "",
) -> Path:
    if destination.exists():
        raise FileExistsError(destination)
    filtered = [
        event for event in events
        if str(event.get("organization_id", "")) == organization_id
    ]
    lines = [
        json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for event in sorted(filtered, key=lambda item: int(item.get("sequence", 0)))
    ]
    payload = ("\n".join(lines) + ("\n" if lines else "")).encode()
    manifest = {
        "format": "fieldora.tenant-audit-export",
        "format_version": 2,
        "organization_id": organization_id,
        "event_count": len(lines),
        "events_sha256": hashlib.sha256(payload).hexdigest(),
        "source_chain_verified": source_chain_verified,
        "source_chain_detail": source_chain_detail,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        with zipfile.ZipFile(temporary, "x", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("events.jsonl", payload)
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            )
        temporary.replace(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def verify_tenant_audit_export(source: Path) -> dict[str, object]:
    with zipfile.ZipFile(source) as archive:
        if set(archive.namelist()) != {"events.jsonl", "manifest.json"}:
            raise ValueError("audit export contents are invalid")
        manifest = json.loads(archive.read("manifest.json"))
        payload = archive.read("events.jsonl")
    format_version = manifest.get("format_version")
    if (
        manifest.get("format") != "fieldora.tenant-audit-export"
        or format_version not in (1, 2)
    ):
        raise ValueError("audit export format is invalid")
    if hashlib.sha256(payload).hexdigest() != manifest.get("events_sha256"):
        raise ValueError("audit export integrity check failed")
    if (
        format_version == 2
        and not isinstance(manifest.get("source_chain_verified"), bool)
    ):
        raise ValueError("audit export chain-verification state is invalid")
    lines = payload.decode().splitlines()
    if len(lines) != int(manifest.get("event_count", -1)):
        raise ValueError("audit export event count is invalid")
    organization_id = str(manifest.get("organization_id", ""))
    for line in lines:
        if str(json.loads(line).get("organization_id", "")) != organization_id:
            raise ValueError("audit export crosses tenant boundary")
    return manifest

"""Offline Excalidraw-compatible whiteboards stored as versioned documents."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class ExcalidrawDocument:
    path: Path
    title: str
    modified_at_utc: str
    revision_count: int


class OfflineExcalidrawDocuments:
    """Own `.excalidraw` files and immutable snapshots under Documents."""

    def __init__(self, documents_root: Path) -> None:
        self.root = documents_root / "Whiteboards"
        self.versions = self.root / ".versions"

    def ensure(self) -> None:
        self.versions.mkdir(parents=True, exist_ok=True)

    def list_documents(self) -> tuple[ExcalidrawDocument, ...]:
        self.ensure()
        records = []
        for path in sorted(self.root.glob("*.excalidraw"), key=lambda item: item.name.casefold()):
            stat = path.stat()
            revision_dir = self.versions / path.stem
            records.append(
                ExcalidrawDocument(
                    path=path,
                    title=path.stem.replace("-", " "),
                    modified_at_utc=datetime.fromtimestamp(
                        stat.st_mtime, tz=UTC
                    ).isoformat(timespec="seconds"),
                    revision_count=len(tuple(revision_dir.glob("*.excalidraw"))),
                )
            )
        return tuple(records)

    def ensure_default_document(self) -> Path:
        """Return an existing whiteboard or create the initial Drawing 1."""
        documents = self.list_documents()
        if documents:
            return documents[0].path
        return self.create("Drawing 1")

    def create(self, title: str) -> Path:
        self.ensure()
        safe_title = "-".join(title.strip().split())
        if not safe_title or any(character in safe_title for character in '<>:"/\\|?*'):
            raise ValueError("Use a non-empty title without file-name control characters")
        destination = self.root / f"{safe_title}.excalidraw"
        if destination.exists():
            raise FileExistsError(f"A whiteboard named {title!r} already exists")
        payload = {
            "type": "excalidraw",
            "version": 2,
            "source": "fieldora-offline",
            "elements": [],
            "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None},
            "files": {},
            "fieldora": {
                "document_id": str(uuid4()),
                "created_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                "storage": "Documents/Whiteboards",
            },
        }
        destination.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        self.snapshot(destination, reason="created")
        return destination

    def import_document(self, source: Path) -> Path:
        self.ensure()
        payload = json.loads(source.read_text(encoding="utf-8"))
        if payload.get("type") != "excalidraw" or not isinstance(payload.get("elements"), list):
            raise ValueError("The selected file is not an Excalidraw document")
        destination = self.root / source.name
        if destination.suffix.casefold() != ".excalidraw":
            destination = destination.with_suffix(".excalidraw")
        if destination.exists():
            raise FileExistsError(f"{destination.name} already exists in Documents/Whiteboards")
        shutil.copy2(source, destination)
        self.snapshot(destination, reason="imported")
        return destination

    def snapshot(self, document: Path, *, reason: str = "manual") -> Path:
        document = document.resolve()
        root = self.root.resolve()
        if document.parent != root or document.suffix.casefold() != ".excalidraw":
            raise ValueError("Only managed Excalidraw documents can be versioned")
        content = document.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        destination_dir = self.versions / document.stem
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"{stamp}-{digest[:12]}.excalidraw"
        shutil.copy2(document, destination)
        metadata = destination.with_suffix(".json")
        metadata.write_text(
            json.dumps(
                {
                    "document": document.name,
                    "snapshot": destination.name,
                    "reason": reason,
                    "sha256": digest,
                    "created_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return destination

    def save_payload(self, document: Path, payload: str) -> None:
        """Validate and atomically save a scene emitted by the embedded editor."""
        document = document.resolve()
        if document.parent != self.root.resolve() or document.suffix.casefold() != ".excalidraw":
            raise ValueError("Only managed Excalidraw documents can be saved")
        parsed = json.loads(payload)
        if (
            parsed.get("type") != "excalidraw"
            or not isinstance(parsed.get("elements"), list)
            or not isinstance(parsed.get("files"), dict)
            or not isinstance(parsed.get("appState"), dict)
        ):
            raise ValueError("The editor returned an invalid Excalidraw document")
        previous = json.loads(document.read_text(encoding="utf-8"))
        if isinstance(previous.get("fieldora"), dict):
            parsed["fieldora"] = previous["fieldora"]
        parsed["source"] = "fieldora-offline"
        temporary = document.with_suffix(".excalidraw.tmp")
        temporary.write_text(
            json.dumps(parsed, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        temporary.replace(document)

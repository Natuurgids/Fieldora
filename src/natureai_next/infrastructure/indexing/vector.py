"""Atomic local cosine index with checksummed manifests and exact fallback semantics."""

from __future__ import annotations

import hashlib
import json
import os
import struct
import tempfile
from pathlib import Path

from natureai_next.domain.ai import EmbeddingVector, SimilarityMatch

_MAGIC = b"NAIVEC1\0"


class LocalVectorIndex:
    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._manifest_path = directory / "manifest.json"
        self._data_path = directory / "vectors.bin"
        self._manifest = self._load_manifest()

    @property
    def generation(self) -> str:
        return str(self._manifest["generation"])

    def validate(self) -> bool:
        try:
            data = self._data_path.read_bytes()
            return hashlib.sha256(data).hexdigest() == self._manifest[
                "checksum"
            ] and data.startswith(_MAGIC)
        except (OSError, KeyError, ValueError):
            return False

    def search(self, query: EmbeddingVector, limit: int) -> tuple[SimilarityMatch, ...]:
        if not self.validate():
            raise ValueError("vector index is corrupt")
        dimension = int(self._manifest["dimension"])
        if query.dimension != dimension:
            raise ValueError("query vector dimension does not match index")
        normalized = query.normalized()
        payload = self._data_path.read_bytes()
        offset = len(_MAGIC)
        (count,) = struct.unpack_from("<Q", payload, offset)
        offset += 8
        matches: list[SimilarityMatch] = []
        for _ in range(count):
            (name_length,) = struct.unpack_from("<H", payload, offset)
            offset += 2
            public_id = payload[offset : offset + name_length].decode("utf-8")
            offset += name_length
            vector_bytes = payload[offset : offset + dimension * 4]
            offset += dimension * 4
            vector = EmbeddingVector.from_blob(vector_bytes, dimension)
            score = sum(a * b for a, b in zip(normalized.values, vector.values, strict=True))
            matches.append(SimilarityMatch(public_id, score))
        matches.sort(key=lambda item: (-item.score, item.asset_public_id))
        return tuple(matches[: max(1, min(limit, 1000))])

    def _load_manifest(self) -> dict[str, object]:
        value = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        if value.get("schema_version") != 1:
            raise ValueError("unsupported vector index manifest")
        return value


class LocalVectorIndexBuilder:
    def build(
        self, directory: Path, *, generation: str, vectors: dict[str, EmbeddingVector]
    ) -> LocalVectorIndex:
        if not vectors:
            raise ValueError("cannot build an empty vector index")
        dimension = next(iter(vectors.values())).dimension
        if any(vector.dimension != dimension for vector in vectors.values()):
            raise ValueError("all index vectors must have the same dimension")
        directory.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".vector-index-", dir=directory.parent))
        try:
            payload = bytearray(_MAGIC)
            payload += struct.pack("<Q", len(vectors))
            for public_id, vector in sorted(vectors.items()):
                encoded = public_id.encode("utf-8")
                if len(encoded) > 65535:
                    raise ValueError("asset public ID is too long")
                payload += struct.pack("<H", len(encoded)) + encoded + vector.normalized().to_blob()
            data = bytes(payload)
            checksum = hashlib.sha256(data).hexdigest()
            (staging / "vectors.bin").write_bytes(data)
            manifest = {
                "schema_version": 1,
                "generation": generation,
                "dimension": dimension,
                "count": len(vectors),
                "checksum": checksum,
                "metric": "cosine",
            }
            (staging / "manifest.json").write_text(
                json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="utf-8"
            )
            if directory.exists():
                backup = directory.with_name(directory.name + ".previous")
                if backup.exists():
                    import shutil

                    shutil.rmtree(backup)
                os.replace(directory, backup)
            os.replace(staging, directory)
            return LocalVectorIndex(directory)
        finally:
            if staging.exists():
                import shutil

                shutil.rmtree(staging, ignore_errors=True)

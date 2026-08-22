"""Legacy-compatible pybioclip Tree-of-Life classification adapter.

This adapter restores the original NatureAI execution path.  pybioclip owns the
TreeOfLife-10M taxon table and matching text embeddings, so classification does
not depend on an Aperture taxonomy CSV or on GBIF being installed.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TextIO

from natureai_next.domain.ai import ConfidenceBand, SuggestionCandidate


@contextmanager
def _writable_console_streams() -> Iterator[None]:
    """Provide writable streams for GUI-launched third-party code.

    Windows GUI entry points commonly set ``sys.stdout`` and ``sys.stderr`` to
    ``None``. pybioclip/tqdm writes progress output to those streams, which
    previously caused every classification to fail with ``NoneType.write``.
    """
    original_stdout, original_stderr = sys.stdout, sys.stderr
    sink: TextIO | None = None
    try:
        if sys.stdout is None or sys.stderr is None:
            sink = open(os.devnull, "w", encoding="utf-8")
            if sys.stdout is None:
                sys.stdout = sink
            if sys.stderr is None:
                sys.stderr = sink
        yield
    finally:
        sys.stdout, sys.stderr = original_stdout, original_stderr
        if sink is not None:
            sink.close()


class TreeOfLifeClassifierAdapter:
    """Run pybioclip's bundled TreeOfLifeClassifier and normalize its output."""

    identity = "pybioclip-tree-of-life-v1"

    def __init__(self, *, device: str = "cpu") -> None:
        self._device = device
        self._classifier: object | None = None
        self._last_prediction_rows: tuple[dict[str, Any], ...] = ()

    def load(self) -> None:
        if self._classifier is not None:
            return
        try:
            from bioclip import BIOCLIP_V1_MODEL_STR
            from bioclip.predict import TreeOfLifeClassifier
        except ImportError as exc:
            raise RuntimeError(
                "The legacy BioCLIP Tree-of-Life runtime is not installed. "
                "Run Repair Aperture or install the Full AI environment (pybioclip 2.1.5)."
            ) from exc
        try:
            self._classifier = TreeOfLifeClassifier(
                model_str=BIOCLIP_V1_MODEL_STR,
                device=self._device,
            )
        except Exception as exc:
            raise RuntimeError(
                "BioCLIP's TreeOfLife-10M labels/embeddings could not be loaded. "
                "Open Maintenance Center and choose Repair Tree-of-Life resources. "
                f"Underlying error: {exc}"
            ) from exc

    def predict(self, image: Path, *, limit: int = 10) -> tuple[SuggestionCandidate, ...]:
        self.load()
        assert self._classifier is not None
        rank: object = "species"
        try:
            from bioclip import Rank

            rank = getattr(Rank, "SPECIES", getattr(Rank, "species", rank))
        except Exception:
            pass
        try:
            with _writable_console_streams():
                try:
                    rows = self._classifier.predict(
                        [str(image)], rank=rank, k=max(1, min(limit, 50)), batch_size=1
                    )
                except TypeError:
                    rows = self._classifier.predict(
                        [str(image)], rank=rank, top_k=max(1, min(limit, 50)), batch_size=1
                    )
        except Exception as exc:
            raise RuntimeError(f"Tree-of-Life classification failed: {exc}") from exc
        if not isinstance(rows, Sequence):
            raise RuntimeError("TreeOfLifeClassifier returned an invalid result.")
        normalized_rows = tuple(dict(item) for item in rows if isinstance(item, dict))
        self._last_prediction_rows = normalized_rows
        result: list[SuggestionCandidate] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            label = self._label(item)
            if not label:
                continue
            score = self._score(item)
            level = self._level(item)
            result.append(
                SuggestionCandidate(
                    taxon_public_id=None,
                    label=label,
                    raw_score=score,
                    calibrated_score=None,
                    rank=len(result) + 1,
                    confidence_band=self._band(score),
                    taxonomic_level=level,
                )
            )
            if len(result) >= limit:
                break
        if not result:
            raise RuntimeError(
                "TreeOfLifeClassifier returned no taxon candidates. Its bundled "
                "TreeOfLife-10M resources may be incomplete; repair them in Maintenance Center."
            )
        return tuple(result)

    @property
    def last_prediction_rows(self) -> tuple[dict[str, Any], ...]:
        """Return copies of the upstream rows for provenance and later resolution."""
        return tuple(dict(item) for item in self._last_prediction_rows)

    @staticmethod
    def _label(item: dict[str, Any]) -> str:
        scientific = str(
            item.get("scientific_name")
            or item.get("species")
            or item.get("label")
            or item.get("name")
            or ""
        ).strip()
        common = str(item.get("common_name") or item.get("common") or "").strip()
        return (
            f"{scientific} ({common})"
            if scientific and common and common.casefold() != scientific.casefold()
            else scientific or common
        )

    @staticmethod
    def _score(item: dict[str, Any]) -> float:
        for key in ("score", "probability", "confidence", "similarity", "logit"):
            try:
                value = float(item.get(key))
                if value == value:
                    return max(-1.0, min(1.0, value))
            except (TypeError, ValueError):
                continue
        return 0.0

    @staticmethod
    def _taxon_id(item: dict[str, Any]) -> str | None:
        for key in ("taxon_id", "taxon_key", "gbif_id", "id"):
            value = str(item.get(key) or "").strip()
            if value:
                return f"treeoflife:{value}"
        scientific = str(item.get("scientific_name") or item.get("species") or "").strip()
        return f"treeoflife-name:{scientific}" if scientific else None

    @staticmethod
    def _level(item: dict[str, Any]) -> str | None:
        value = str(item.get("rank") or item.get("taxonomic_rank") or "species").strip().casefold()
        return value or None

    @staticmethod
    def _band(score: float) -> ConfidenceBand:
        if score >= 0.30:
            return ConfidenceBand.HIGH
        if score >= 0.20:
            return ConfidenceBand.MEDIUM
        if score >= 0.10:
            return ConfidenceBand.LOW
        return ConfidenceBand.UNKNOWN

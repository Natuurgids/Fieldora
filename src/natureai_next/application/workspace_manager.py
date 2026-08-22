"""Adaptive temporary workspace policy for resource processing."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class WorkspacePlan:
    mode: str
    memory_budget_bytes: int
    reserve_bytes: int
    root: Path


class AdaptiveWorkspaceManager:
    """Choose a memory-assisted or disk workspace without risking OS stability."""

    def __init__(self, *, reserve_bytes: int = 8 * 1024**3, maximum_fraction: float = 0.60) -> None:
        self.reserve_bytes = reserve_bytes
        self.maximum_fraction = max(0.1, min(0.8, maximum_fraction))

    def available_memory(self) -> int:
        try:
            import psutil

            return int(psutil.virtual_memory().available)
        except Exception:
            return 0

    def plan(self, source_size: int, *, expansion_factor: float = 3.0) -> WorkspacePlan:
        available = self.available_memory()
        usable = max(0, available - self.reserve_bytes)
        budget = int(min(usable, available * self.maximum_fraction)) if available else 0
        required = int(max(0, source_size) * max(1.0, expansion_factor))
        mode = "memory-assisted" if budget and required <= budget else "hybrid-disk"
        root = Path(tempfile.gettempdir()) / "NatureAI_Nest" / "workspaces"
        root.mkdir(parents=True, exist_ok=True)
        return WorkspacePlan(mode, budget, self.reserve_bytes, root)

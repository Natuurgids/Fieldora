"""Identity generation abstraction."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


class UuidGenerator(Protocol):
    def new_uuid(self) -> UUID:
        """Return a new UUID."""

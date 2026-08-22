"""Small immutable result type for expected boundary failures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from natureai_next.shared.errors import ErrorDescriptor

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Result(Generic[T]):
    value: T | None = None
    error: ErrorDescriptor | None = None

    def __post_init__(self) -> None:
        if (self.value is None) == (self.error is None):
            raise ValueError("Result must contain exactly one of value or error")

    @property
    def is_success(self) -> bool:
        return self.error is None

    def unwrap(self) -> T:
        if self.error is not None:
            raise RuntimeError(self.error.summary)
        assert self.value is not None
        return self.value

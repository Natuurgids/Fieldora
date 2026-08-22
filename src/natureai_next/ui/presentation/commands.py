"""Central presentation command registry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CommandDefinition:
    command_id: str
    label: str
    shortcut: str | None
    execute: Callable[[], None]
    is_enabled: Callable[[], bool] = lambda: True
    is_checked: Callable[[], bool] | None = None


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, CommandDefinition] = {}

    def register(self, command: CommandDefinition) -> None:
        if command.command_id in self._commands:
            raise ValueError(f"duplicate command: {command.command_id}")
        self._commands[command.command_id] = command

    def get(self, command_id: str) -> CommandDefinition:
        return self._commands[command_id]

    def invoke(self, command_id: str) -> bool:
        command = self.get(command_id)
        if not command.is_enabled():
            return False
        command.execute()
        return True

    def all(self) -> tuple[CommandDefinition, ...]:
        return tuple(self._commands[k] for k in sorted(self._commands))

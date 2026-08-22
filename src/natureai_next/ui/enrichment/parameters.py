"""Producer-neutral dynamic parameter form models and validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from natureai_next.synthesis_core.contracts import ParameterDefinition


@dataclass(frozen=True, slots=True)
class ParameterField:
    name: str
    control: str
    required: bool
    default: Any
    minimum: float | None
    maximum: float | None
    choices: tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class ParameterForm:
    fields: tuple[ParameterField, ...]

    def validate(self, values: Mapping[str, Any]) -> dict[str, Any]:
        definitions = {field.name: field for field in self.fields}
        unknown = sorted(set(values) - set(definitions))
        if unknown:
            raise ValueError(f"unknown parameters: {', '.join(unknown)}")
        result: dict[str, Any] = {}
        for field in self.fields:
            raw = values.get(field.name, field.default)
            if raw is None:
                if field.required:
                    raise ValueError(f"parameter {field.name} is required")
                result[field.name] = None
                continue
            value = _coerce(field.control, raw, field.name)
            if field.choices and value not in field.choices:
                raise ValueError(f"parameter {field.name} must be one of {field.choices}")
            if isinstance(value, int | float) and not isinstance(value, bool):
                if field.minimum is not None and value < field.minimum:
                    raise ValueError(f"parameter {field.name} must be at least {field.minimum}")
                if field.maximum is not None and value > field.maximum:
                    raise ValueError(f"parameter {field.name} must be at most {field.maximum}")
            result[field.name] = value
        return result


def build_parameter_form(definitions: Sequence[ParameterDefinition]) -> ParameterForm:
    return ParameterForm(
        tuple(
            ParameterField(
                definition.name,
                _control(definition),
                definition.required,
                definition.default,
                definition.minimum,
                definition.maximum,
                tuple(definition.choices),
            )
            for definition in definitions
        )
    )


def _control(definition: ParameterDefinition) -> str:
    if definition.choices:
        return "choice"
    return {
        "integer": "integer",
        "real": "decimal",
        "number": "decimal",
        "boolean": "checkbox",
        "string": "text",
        "path": "file",
    }.get(definition.value_type, "text")


def _coerce(control: str, raw: Any, name: str) -> Any:
    try:
        if control == "integer":
            if isinstance(raw, bool):
                raise ValueError
            return int(raw)
        if control == "decimal":
            if isinstance(raw, bool):
                raise ValueError
            return float(raw)
        if control == "checkbox":
            if isinstance(raw, bool):
                return raw
            if isinstance(raw, str) and raw.casefold() in {"true", "false"}:
                return raw.casefold() == "true"
            raise ValueError
        return str(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"parameter {name} has invalid value") from exc

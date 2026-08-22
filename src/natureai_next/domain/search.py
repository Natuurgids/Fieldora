"""Versioned structured search query model."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

QUERY_SCHEMA_VERSION = 1


class LogicalOperator(StrEnum):
    AND = "and"
    OR = "or"


class PredicateOperator(StrEnum):
    EQ = "eq"
    NE = "ne"
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"
    IN = "in"
    CONTAINS = "contains"
    EXISTS = "exists"
    BETWEEN = "between"


@dataclass(frozen=True, slots=True)
class Predicate:
    field: str
    operator: PredicateOperator
    value: Any = None


@dataclass(frozen=True, slots=True)
class Not:
    child: QueryNode


@dataclass(frozen=True, slots=True)
class Group:
    operator: LogicalOperator
    children: tuple[QueryNode, ...]


QueryNode = Predicate | Not | Group


@dataclass(frozen=True, slots=True)
class StructuredAssetFilters:
    """Validated user-facing filters for catalog search.

    Values are converted into the public structured-query model by the
    application service.  ``None`` means that a filter is not active.
    """

    minimum_rating: int | None = None
    color_label: str | None = None
    pick_state: str | None = None
    captured_from_us: int | None = None
    captured_to_us: int | None = None
    captured_from_date: str | None = None
    captured_to_date: str | None = None
    minimum_width: int | None = None
    minimum_height: int | None = None
    tag: str | None = None
    taxonomy_name: str | None = None
    camera_make: str | None = None
    camera_model: str | None = None
    lens: str | None = None
    minimum_latitude: float | None = None
    maximum_latitude: float | None = None
    minimum_longitude: float | None = None
    maximum_longitude: float | None = None
    exact_duplicates_only: bool | None = None

    def is_empty(self) -> bool:
        return all(
            value is None
            for value in (
                self.minimum_rating,
                self.color_label,
                self.pick_state,
                self.captured_from_us,
                self.captured_to_us,
                self.captured_from_date,
                self.captured_to_date,
                self.minimum_width,
                self.minimum_height,
                self.tag,
                self.taxonomy_name,
                self.camera_make,
                self.camera_model,
                self.lens,
                self.minimum_latitude,
                self.maximum_latitude,
                self.minimum_longitude,
                self.maximum_longitude,
                self.exact_duplicates_only,
            )
        )


@dataclass(frozen=True, slots=True)
class StructuredQuery:
    root: QueryNode
    schema_version: int = QUERY_SCHEMA_VERSION


class QueryValidationError(ValueError):
    """Raised when a structured query violates the public query contract."""


_ALLOWED_FIELDS = frozenset(
    {
        "rating",
        "color_label",
        "pick_state",
        "capture_time_utc_us",
        "capture_date",
        "availability_state",
        "storage_mode",
        "tag",
        "collection",
        "pixel_width",
        "pixel_height",
        "country_code",
        "latitude",
        "longitude",
        "taxon_public_id",
        "taxon_name",
        "title",
        "caption",
        "notes",
        "text",
        "camera_make",
        "camera_model",
        "lens",
        "filename",
        "tag_text",
        "exact_duplicate",
    }
)
_FIELD_OPERATORS: Mapping[str, frozenset[PredicateOperator]] = {
    "rating": frozenset(
        {
            PredicateOperator.EQ,
            PredicateOperator.NE,
            PredicateOperator.LT,
            PredicateOperator.LTE,
            PredicateOperator.GT,
            PredicateOperator.GTE,
            PredicateOperator.BETWEEN,
            PredicateOperator.EXISTS,
        }
    ),
    "capture_time_utc_us": frozenset(
        {
            PredicateOperator.LT,
            PredicateOperator.LTE,
            PredicateOperator.GT,
            PredicateOperator.GTE,
            PredicateOperator.BETWEEN,
            PredicateOperator.EXISTS,
        }
    ),
    "capture_date": frozenset(
        {
            PredicateOperator.LT,
            PredicateOperator.LTE,
            PredicateOperator.GT,
            PredicateOperator.GTE,
            PredicateOperator.BETWEEN,
            PredicateOperator.EXISTS,
        }
    ),
    "pixel_width": frozenset(
        {
            PredicateOperator.LT,
            PredicateOperator.LTE,
            PredicateOperator.GT,
            PredicateOperator.GTE,
            PredicateOperator.BETWEEN,
            PredicateOperator.EXISTS,
        }
    ),
    "pixel_height": frozenset(
        {
            PredicateOperator.LT,
            PredicateOperator.LTE,
            PredicateOperator.GT,
            PredicateOperator.GTE,
            PredicateOperator.BETWEEN,
            PredicateOperator.EXISTS,
        }
    ),
    "latitude": frozenset({PredicateOperator.BETWEEN, PredicateOperator.EXISTS}),
    "longitude": frozenset({PredicateOperator.BETWEEN, PredicateOperator.EXISTS}),
    "title": frozenset(
        {PredicateOperator.EQ, PredicateOperator.CONTAINS, PredicateOperator.EXISTS}
    ),
    "caption": frozenset(
        {PredicateOperator.EQ, PredicateOperator.CONTAINS, PredicateOperator.EXISTS}
    ),
    "notes": frozenset(
        {PredicateOperator.EQ, PredicateOperator.CONTAINS, PredicateOperator.EXISTS}
    ),
    "text": frozenset({PredicateOperator.CONTAINS}),
    "taxon_name": frozenset({PredicateOperator.CONTAINS}),
    "camera_make": frozenset(
        {PredicateOperator.EQ, PredicateOperator.CONTAINS, PredicateOperator.EXISTS}
    ),
    "filename": frozenset({PredicateOperator.CONTAINS}),
    "tag_text": frozenset({PredicateOperator.CONTAINS}),
    "camera_model": frozenset(
        {PredicateOperator.EQ, PredicateOperator.CONTAINS, PredicateOperator.EXISTS}
    ),
    "lens": frozenset({PredicateOperator.EQ, PredicateOperator.CONTAINS, PredicateOperator.EXISTS}),
}
_DEFAULT_OPERATORS = frozenset(
    {PredicateOperator.EQ, PredicateOperator.NE, PredicateOperator.IN, PredicateOperator.EXISTS}
)


def validate_query(query: StructuredQuery, *, max_depth: int = 8, max_predicates: int = 64) -> None:
    if query.schema_version != QUERY_SCHEMA_VERSION:
        raise QueryValidationError(f"unsupported query schema version: {query.schema_version}")
    count = 0

    def visit(node: QueryNode, depth: int) -> None:
        nonlocal count
        if depth > max_depth:
            raise QueryValidationError("query nesting limit exceeded")
        if isinstance(node, Predicate):
            count += 1
            if count > max_predicates:
                raise QueryValidationError("query predicate limit exceeded")
            if node.field not in _ALLOWED_FIELDS:
                raise QueryValidationError(f"unsupported query field: {node.field}")
            allowed = _FIELD_OPERATORS.get(node.field, _DEFAULT_OPERATORS)
            if node.operator not in allowed:
                raise QueryValidationError(
                    f"operator {node.operator} is not allowed for {node.field}"
                )
            if node.operator is PredicateOperator.IN and (
                not isinstance(node.value, list | tuple) or not node.value
            ):
                raise QueryValidationError("IN requires a non-empty sequence")
            if node.operator is PredicateOperator.BETWEEN and (
                not isinstance(node.value, list | tuple) or len(node.value) != 2
            ):
                raise QueryValidationError("BETWEEN requires exactly two values")
            return
        if isinstance(node, Not):
            visit(node.child, depth + 1)
            return
        if not node.children:
            raise QueryValidationError("logical groups cannot be empty")
        for child in node.children:
            visit(child, depth + 1)

    visit(query.root, 1)


def query_to_dict(query: StructuredQuery) -> dict[str, Any]:
    def encode(node: QueryNode) -> dict[str, Any]:
        if isinstance(node, Predicate):
            return {
                "type": "predicate",
                "field": node.field,
                "operator": node.operator.value,
                "value": node.value,
            }
        if isinstance(node, Not):
            return {"type": "not", "child": encode(node.child)}
        return {
            "type": "group",
            "operator": node.operator.value,
            "children": [encode(x) for x in node.children],
        }

    return {"schema_version": query.schema_version, "root": encode(query.root)}


def query_from_dict(payload: Mapping[str, Any]) -> StructuredQuery:
    def decode(node: Mapping[str, Any]) -> QueryNode:
        kind = node.get("type")
        if kind == "predicate":
            return Predicate(
                str(node["field"]), PredicateOperator(str(node["operator"])), node.get("value")
            )
        if kind == "not":
            return Not(decode(_mapping(node["child"])))
        if kind == "group":
            return Group(
                LogicalOperator(str(node["operator"])),
                tuple(decode(_mapping(x)) for x in _sequence(node["children"])),
            )
        raise QueryValidationError(f"unsupported query node type: {kind}")

    query = StructuredQuery(
        decode(_mapping(payload["root"])), int(payload.get("schema_version", 0))
    )
    validate_query(query)
    return query


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise QueryValidationError("query object expected")
    return value


def _sequence(value: Any) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise QueryValidationError("query array expected")
    return value

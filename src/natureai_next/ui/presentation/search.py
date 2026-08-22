"""GUI-independent visual query builder and search presentation state."""

from __future__ import annotations

from dataclasses import dataclass, replace

from natureai_next.domain.search import (
    Group,
    LogicalOperator,
    Predicate,
    PredicateOperator,
    StructuredQuery,
    validate_query,
)
from natureai_next.ports.search import SearchRequest


@dataclass(frozen=True, slots=True)
class FilterClause:
    field: str
    operator: PredicateOperator
    value: object


@dataclass(frozen=True, slots=True)
class QueryBuilderState:
    clauses: tuple[FilterClause, ...] = ()
    combine_with: LogicalOperator = LogicalOperator.AND
    text: str = ""
    sort: str = "id_asc"


class QueryBuilderModel:
    def __init__(self, state: QueryBuilderState | None = None) -> None:
        self._state = state or QueryBuilderState()

    @property
    def state(self) -> QueryBuilderState:
        return self._state

    def add(self, clause: FilterClause) -> None:
        self._state = replace(self._state, clauses=(*self._state.clauses, clause))

    def remove(self, index: int) -> None:
        self._state = replace(
            self._state, clauses=self._state.clauses[:index] + self._state.clauses[index + 1 :]
        )

    def set_text(self, text: str) -> None:
        self._state = replace(self._state, text=text.strip())

    def build(self, *, limit: int = 200, after_id: int | None = None) -> SearchRequest:
        nodes = [Predicate(x.field, x.operator, x.value) for x in self._state.clauses]
        if self._state.text:
            nodes.append(Predicate("text", PredicateOperator.CONTAINS, self._state.text))
        root = nodes[0] if len(nodes) == 1 else Group(self._state.combine_with, tuple(nodes))
        if not nodes:
            root = Predicate("rating", PredicateOperator.EXISTS, False)
        query = StructuredQuery(root)
        validate_query(query)
        return SearchRequest(query, limit, after_id, self._state.sort)

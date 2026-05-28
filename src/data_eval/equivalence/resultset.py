"""Engine-input result-set types.

Two shapes — ``TypedResultSet`` (rows + required ``Schema``) and ``UntypedResultSet``
(rows only) — are the inputs the equivalence engine consumes. The split lets
``compare()`` overloads gate type comparison on schema presence (Design A): the
"strict types without a schema" state is unrepresentable at the call site rather
than caught at runtime. Internal to the engine; scorers adapt the public
``ExecutionResult`` / ``ExpectedResultSet`` into these.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from data_eval.types import Schema


class UntypedResultSet(BaseModel):
    """A result set without column-type information; type comparison is unavailable."""

    model_config = ConfigDict(extra="forbid")

    rows: list[dict[str, Any]]


class TypedResultSet(BaseModel):
    """A result set carrying column types; enables semantic type comparison via SQLGlot."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    rows: list[dict[str, Any]]
    schema_: Schema = Field(alias="schema")

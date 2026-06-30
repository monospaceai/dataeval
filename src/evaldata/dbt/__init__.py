"""dbt integration: load a dbt project's artifacts into evaldata types.

`DbtContext` reads a built dbt `target/` directory (manifest.json, optional catalog.json, and
optional semantic_manifest.json) and exposes models, sources, schema context, and the semantic
layer's metrics and dimensions. `load_dbt` converts them into eval cases; `platform_from_profile`
resolves the project's warehouse connection from a dbt profile.
"""

from evaldata.dbt.context import (
    Column,
    DbtContext,
    DbtTest,
    Dimension,
    Entity,
    Measure,
    Metric,
    ModelRef,
    Relation,
    SchemaContext,
    SemanticLayerContext,
    SemanticModel,
    SourceRef,
    TableSchema,
)
from evaldata.dbt.errors import DbtError
from evaldata.dbt.loader import Mode, load_dbt
from evaldata.dbt.profile import platform_from_profile

__all__ = [
    "Column",
    "DbtContext",
    "DbtError",
    "DbtTest",
    "Dimension",
    "Entity",
    "Measure",
    "Metric",
    "Mode",
    "ModelRef",
    "Relation",
    "SchemaContext",
    "SemanticLayerContext",
    "SemanticModel",
    "SourceRef",
    "TableSchema",
    "load_dbt",
    "platform_from_profile",
]

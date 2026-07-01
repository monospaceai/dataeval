"""dbt integration: load a dbt project's artifacts and evaluate its SQL and Semantic Layer.

`DbtContext` reads a built dbt `target/` directory (manifest.json, optional catalog.json, and
optional semantic_manifest.json) and exposes models, sources, schema context, and the semantic
layer's metrics and dimensions. `load_dbt` converts them into SQL eval cases and `load_dbt_metrics`
into Semantic Layer cases; `platform_from_profile` resolves the project's warehouse connection from
a dbt profile. `MetricCase`, `MetricLayerSolver`, and `MetricSpecEquivalence` form the Semantic
Layer evaluation vertical.
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
from evaldata.dbt.loader import Mode, load_dbt, load_dbt_metrics
from evaldata.dbt.metric_layer_solver import SL_PROMPT_TEMPLATE, MetricLayerSolver
from evaldata.dbt.metric_spec_equivalence import MetricSpecEquivalence
from evaldata.dbt.metricflow import CanonicalMetricQuery, canonicalize
from evaldata.dbt.profile import platform_from_profile
from evaldata.dbt.semantic_layer import (
    MetricCase,
    MetricQuery,
    MetricScorer,
    MetricSolver,
    MetricSolverOutput,
)

__all__ = [
    "SL_PROMPT_TEMPLATE",
    "CanonicalMetricQuery",
    "Column",
    "DbtContext",
    "DbtError",
    "DbtTest",
    "Dimension",
    "Entity",
    "Measure",
    "Metric",
    "MetricCase",
    "MetricLayerSolver",
    "MetricQuery",
    "MetricScorer",
    "MetricSolver",
    "MetricSolverOutput",
    "MetricSpecEquivalence",
    "Mode",
    "ModelRef",
    "Relation",
    "SchemaContext",
    "SemanticLayerContext",
    "SemanticModel",
    "SourceRef",
    "TableSchema",
    "canonicalize",
    "load_dbt",
    "load_dbt_metrics",
    "platform_from_profile",
]

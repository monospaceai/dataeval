"""Resolve a `MetricQuery` through MetricFlow into a comparable canonical form.

MetricFlow itself parses and validates the query against the project's semantic manifest, so the
resolution (default time grains, entity-linked dimension paths) matches what the warehouse would
run. This is the one module that depends on the optional `dbt-metricflow` toolchain.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evaldata.dbt.errors import DbtError
from evaldata.types import MetricQuery

# A group-by, order-by, or metric item resolved to its identifying parts: the MetricFlow spec
# class, element name, entity-link path, time grain, and date part.
SpecKey = tuple[str, str, tuple[str, ...], str | None, str | None]


@dataclass(frozen=True)
class CanonicalMetricQuery:
    """A metric query resolved through MetricFlow: two queries with equal values are the same query."""

    metrics: frozenset[str]
    group_by: frozenset[SpecKey]
    order_by: tuple[tuple[SpecKey, bool], ...]
    limit: int | None
    where: frozenset[str]


def _spec_key(spec: Any) -> SpecKey:
    granularity = getattr(spec, "time_granularity", None)
    date_part = getattr(spec, "date_part", None)
    return (
        type(spec).__name__,
        spec.element_name,
        tuple(link.element_name for link in getattr(spec, "entity_links", ())),
        getattr(granularity, "name", None),
        date_part.value if date_part is not None else None,
    )


def canonicalize(query: MetricQuery, target_dir: str | Path) -> CanonicalMetricQuery | DbtError:
    """Resolve `query` against a project's semantic manifest into a comparable canonical form.

    MetricFlow resolves default time grains and entity-linked dimension paths the way the warehouse
    would, so two queries that mean the same thing produce equal `CanonicalMetricQuery` values.

    Args:
        query: The metric query to resolve.
        target_dir: A dbt `target/` directory holding `semantic_manifest.json`.

    Returns:
        A `CanonicalMetricQuery`, or a `DbtError` if MetricFlow is not installed
        (`metricflow_unavailable`), the manifest is missing (`target_not_found`), or the query does
        not resolve against the manifest (`metric_query_invalid`).
    """
    try:
        from metricflow_semantics.model.dbt_manifest_parser import parse_manifest_from_dbt_generated_manifest
        from metricflow_semantics.model.semantic_manifest_lookup import SemanticManifestLookup
        from metricflow_semantics.query.query_parser import MetricFlowQueryParser
    except ImportError as error:
        return DbtError(
            kind="metricflow_unavailable",
            message="dbt-metricflow is not installed; install the 'dbt-sl' extra to compare metric queries",
            cause=error,
        )

    manifest_path = Path(target_dir) / "semantic_manifest.json"
    if not manifest_path.is_file():
        return DbtError(kind="target_not_found", message=f"no semantic_manifest.json in {target_dir}")

    try:
        manifest = parse_manifest_from_dbt_generated_manifest(
            manifest_json_string=manifest_path.read_text(encoding="utf-8")
        )
        parser = MetricFlowQueryParser(SemanticManifestLookup(manifest))
        spec = parser.parse_and_validate_query(
            metric_names=query.metrics,
            group_by_names=query.group_by or None,
            where_constraint_strs=query.where or None,
            order_by_names=query.order_by or None,
            limit=query.limit,
        ).query_spec
    except Exception as error:  # MetricFlow raises a variety of parse and validation errors
        return DbtError(kind="metric_query_invalid", message=f"invalid metric query: {error}", cause=error)

    group_by = (*spec.dimension_specs, *spec.time_dimension_specs, *spec.entity_specs)
    return CanonicalMetricQuery(
        metrics=frozenset(s.element_name for s in spec.metric_specs),
        group_by=frozenset(_spec_key(s) for s in group_by),
        order_by=tuple((_spec_key(o.instance_spec), o.descending) for o in spec.order_by_specs),
        limit=spec.limit,
        where=frozenset(w.where_sql_template for w in spec.filter_intersection.where_filters),
    )

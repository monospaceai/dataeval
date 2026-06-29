"""Failure types for dbt artifact loading."""

from typing import Literal

from evaldata.types import Error

DbtErrorKind = Literal[
    "target_not_found",
    "artifact_invalid",
    "unsupported_schema_version",
    "cases_not_found",
    "cases_invalid",
    "profile_not_found",
    "unsupported_adapter",
]


class DbtError(Error):
    """A failure from loading a dbt project."""

    kind: DbtErrorKind

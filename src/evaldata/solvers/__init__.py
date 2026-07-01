"""Solvers: wrappers for the AI system under test (`EvalCase` -> `SolverOutput`)."""

from evaldata.solvers.base import Solver
from evaldata.solvers.callable import CallableSolver
from evaldata.solvers.metric_layer import SL_PROMPT_TEMPLATE, MetricLayerSolver
from evaldata.solvers.prompt import SCHEMA_PROMPT_TEMPLATE, PromptSolver

__all__ = [
    "SCHEMA_PROMPT_TEMPLATE",
    "SL_PROMPT_TEMPLATE",
    "CallableSolver",
    "MetricLayerSolver",
    "PromptSolver",
    "Solver",
]

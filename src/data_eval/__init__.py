"""data-eval — AI evals framework for data and analytics engineering teams."""

from data_eval.core import assert_eval
from data_eval.scorers import ResultSetEquivalence
from data_eval.solvers import CallableSolver
from data_eval.types import EvalCase, PlatformRef

__all__ = [
    "CallableSolver",
    "EvalCase",
    "PlatformRef",
    "ResultSetEquivalence",
    "assert_eval",
]

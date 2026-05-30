"""Solvers: wrappers for the AI system under test (``EvalCase`` -> ``SolverOutput``)."""

from data_eval.solvers.base import Solver
from data_eval.solvers.callable import CallableSolver

__all__ = ["CallableSolver", "Solver"]

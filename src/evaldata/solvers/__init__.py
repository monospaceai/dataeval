"""Solvers: wrappers for the AI system under test (`EvalCase` -> `SolverOutput`)."""

from evaldata.solvers.base import Solver
from evaldata.solvers.callable import CallableSolver
from evaldata.solvers.prompt import PromptSolver

__all__ = ["CallableSolver", "PromptSolver", "Solver"]

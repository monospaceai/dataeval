"""Scorers: pluggable pass/fail checks. v1 ships ``ResultSetEquivalence``."""

from data_eval.scorers.base import Scorer
from data_eval.scorers.result_set_equivalence import ResultSetEquivalence

__all__ = ["ResultSetEquivalence", "Scorer"]

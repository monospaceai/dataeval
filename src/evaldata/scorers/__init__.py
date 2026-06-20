"""Scorers: pluggable pass/fail checks. Ships `ResultSetEquivalence` and `ExpectationSuiteScorer`."""

from evaldata.scorers.base import Scorer
from evaldata.scorers.context import ScoreContext
from evaldata.scorers.expectation_suite import ExpectationSuiteScorer
from evaldata.scorers.query import QueryRunner, ScalarResult
from evaldata.scorers.result_set_equivalence import ResultSetEquivalence

__all__ = ["ExpectationSuiteScorer", "QueryRunner", "ResultSetEquivalence", "ScalarResult", "ScoreContext", "Scorer"]

"""`query_equivalence`: the common query-vs-query check composed as a `FirstDecisive`."""

from evaldata.scorers.combinators import FirstDecisive
from evaldata.scorers.result_set_equivalence import ResultSetEquivalence
from evaldata.scorers.semantic_equivalence import SemanticEquivalence


def query_equivalence() -> FirstDecisive:
    """The common query-vs-query check: compare the queries, falling back to comparing the results.

    The case's `expected` must be a `GoldQuery`.

    Returns:
        A `FirstDecisive` over `SemanticEquivalence` (compares the queries; confirm-or-abstain)
        then `ResultSetEquivalence` (compares the results: runs both queries and diffs).
    """
    return FirstDecisive([SemanticEquivalence(), ResultSetEquivalence()])

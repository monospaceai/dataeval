"""Result-set equivalence engine.

The permanent nucleus of data-eval: a pure function ``compare(...) -> ResultSetDiff | None``
(``None`` means equivalent; errors-as-values, no exceptions). Every result-comparing scorer
wraps this engine.
"""

from data_eval.equivalence.resultset import TypedResultSet, UntypedResultSet

__all__ = ["TypedResultSet", "UntypedResultSet"]

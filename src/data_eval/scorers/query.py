"""`QueryRunner`: a budget-aware handle scorers use to run derived SQL in-platform."""

from data_eval.platforms.base import PlatformAdapter, execute_within_budget
from data_eval.types import ExecutionResult, Sql


class QueryRunner:
    """Runs derived SQL against a case's platform, drawing on a shared cost budget.

    Holds a live adapter, the model's SQL, and a remaining-time pool seeded from the case
    budget. Each completed query decrements the pool by its `latency_seconds`; once the
    pool is exhausted, further runs short-circuit to an errors-as-value `ExecutionResult`
    without touching the adapter. A `None` budget means the pool is unbounded.
    """

    def __init__(self, adapter: PlatformAdapter, model_sql: Sql, budget: float | None) -> None:
        """Bind the runner to a platform and seed its budget pool.

        Args:
            adapter: The platform adapter derived queries execute against.
            model_sql: The model's SQL.
            budget: The shared remaining-time pool in seconds, or `None` for unbounded.
        """
        self._adapter = adapter
        self._model_sql = model_sql
        self._remaining = budget

    def run(self, sql: Sql) -> ExecutionResult:
        """Run `sql` within the remaining budget, decrementing the pool by its latency.

        Args:
            sql: The SQL statement to execute.

        Returns:
            The adapter's `ExecutionResult`, or an `ExecutionResult` with `error` set when
            the budget pool is already exhausted (the adapter is not invoked in that case).
        """
        if self._remaining is not None and self._remaining <= 0:
            return ExecutionResult(
                rows=[],
                schema=None,
                latency_seconds=0.0,
                error="exceeded cost budget: derived-query budget pool exhausted",
            )
        result = execute_within_budget(self._adapter, sql, self._remaining)
        if self._remaining is not None:
            self._remaining -= result.latency_seconds
        return result

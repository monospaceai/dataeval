"""Preset equivalence scorers: ready-made `FirstDecisive` cascades and the SQL judge."""

from evaldata.llm import Llm
from evaldata.scorers.combinators import FirstDecisive
from evaldata.scorers.llm_judge import JudgeExample, LlmJudge
from evaldata.scorers.result_set_equivalence import ResultSetEquivalence
from evaldata.scorers.semantic_equivalence import SemanticEquivalence


def observed_equivalence() -> FirstDecisive:
    """The query-vs-query check that confirms by structure, else by running both queries.

    The case's `expected` must be a `GoldQuery`.

    Returns:
        A `FirstDecisive` cascade: `SemanticEquivalence` compares the queries and confirms
        equivalence first; when it cannot, `ResultSetEquivalence` runs both queries and decides
        by diffing their results.
    """
    return FirstDecisive([SemanticEquivalence(), ResultSetEquivalence()])


def sql_equivalence_judge(model: str | Llm) -> LlmJudge:
    """An `LlmJudge` pre-configured to grade whether two SQL queries are equivalent.

    Args:
        model: A litellm grader-model identifier, or an `Llm` to use directly.

    Returns:
        An `LlmJudge` with SQL-equivalence criteria and few-shot examples.
    """
    return LlmJudge(
        model=model,
        criteria=(
            "The actual output is equivalent to the expected output when both queries return the "
            "same rows on every database. Ignore differences that never change the result: equivalent "
            "boolean forms (1 vs true), SELECT/column order, alias names, whitespace, and casing. "
            "Penalise differences that change the result: different filters, joins, aggregations "
            "(SUM vs COUNT), or projected columns."
        ),
        examples=[
            JudgeExample(
                actual_output="SELECT id FROM t WHERE active = 1",
                expected_output="SELECT id FROM t WHERE active = true",
                score=1.0,
                reason="1 and true are equivalent for a boolean column",
            ),
            JudgeExample(
                actual_output="SELECT SUM(quantity) FROM orders",
                expected_output="SELECT COUNT(quantity) FROM orders",
                score=0.0,
                reason="SUM and COUNT compute different aggregates",
            ),
            JudgeExample(
                actual_output="SELECT name FROM (SELECT * FROM users WHERE active) u",
                expected_output="SELECT name FROM users WHERE active",
                score=1.0,
                reason="wrapping the query in a subquery does not change its result",
            ),
        ],
    )


def judged_equivalence(model: str | Llm) -> FirstDecisive:
    """The query-vs-query check that confirms by structure, else asks an LLM judge.

    The case's `expected` must be a `GoldQuery`.

    Args:
        model: A litellm grader-model identifier, or an `Llm` to use directly.

    Returns:
        A `FirstDecisive` cascade: `SemanticEquivalence` compares the queries and confirms
        equivalence first; when it cannot, the SQL-equivalence judge decides without running
        either query.
    """
    return FirstDecisive([SemanticEquivalence(), sql_equivalence_judge(model)])

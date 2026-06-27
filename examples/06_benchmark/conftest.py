"""Mocked model replies for the benchmark example, so it runs without a key or network."""

from typing import Any

import litellm
import pytest

# The mock returns the right SQL when the question is present and a deliberately wrong query
# otherwise, so the example's execution-accuracy lands below 100% — as a real run would.
_SQL_BY_QUESTION = {
    "How many items are there": "SELECT count(*) AS n FROM items",
    "total price of all items": "SELECT sum(price) AS total FROM items",
}
_WRONG_SQL = "SELECT 0"


def _mock_sql(messages: list[dict[str, Any]]) -> str:
    """Pick a SQL reply for a request by matching its question text.

    Args:
        messages: The chat messages of the request, whose prompt carries the question.

    Returns:
        The mapped SQL when a known question is present, else a deliberately wrong query.
    """
    prompt = " ".join(m.get("content", "") for m in messages)
    for marker, sql in _SQL_BY_QUESTION.items():
        if marker in prompt:
            return sql
    return _WRONG_SQL


@pytest.fixture(autouse=True)
def _mock_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch model calls to return a deterministic reply per question, with no network."""
    real_completion = litellm.completion

    def fake(**kwargs: Any) -> Any:
        return real_completion(**kwargs, mock_response=_mock_sql(kwargs["messages"]))

    monkeypatch.setattr("litellm.completion", fake)

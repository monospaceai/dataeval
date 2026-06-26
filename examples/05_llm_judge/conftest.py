"""Mocked grader replies for the LLM-judge example, so it runs without a key or network."""

import json
from typing import Any

import litellm
import pytest

_EQUIVALENT = json.dumps({"reason": "the CTE wraps the same filter", "score": 1.0})
_NOT_EQUIVALENT = json.dumps({"reason": "country = 'GB' selects different customers", "score": 0.0})


def _mock_reply(messages: list[dict[str, Any]]) -> str:
    """Pick the grader reply for a request by matching the actual SQL under judgement.

    Args:
        messages: The chat messages of the request, whose prompt carries the actual SQL.

    Returns:
        A `JudgeReply`-shaped `{"reason", "score"}` JSON string.
    """
    prompt = " ".join(m.get("content", "") for m in messages)
    return _NOT_EQUIVALENT if "country = 'GB'" in prompt else _EQUIVALENT


@pytest.fixture(autouse=True)
def _mock_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch grader calls to return a deterministic structured reply per case, with no network."""
    real_completion = litellm.completion

    def fake(**kwargs: Any) -> Any:
        return real_completion(**kwargs, mock_response=_mock_reply(kwargs["messages"]))

    monkeypatch.setattr("litellm.completion", fake)
    monkeypatch.setattr("litellm.supports_response_schema", lambda **_: True)

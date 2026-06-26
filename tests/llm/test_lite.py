"""Tests for `LiteLlm` — the litellm-backed `Llm`.

litellm is mocked at its boundary (`completion`, `supports_response_schema`, `completion_cost`);
no network is touched.
"""

import types

import litellm
import pytest
from pydantic import BaseModel

from evaldata.llm import Completion, TextCompletion
from evaldata.llm.lite import LiteLlm
from evaldata.types import LlmError, ProviderErrorKind


class _Reply(BaseModel):
    value: str


def _response(content: str | None, *, prompt_tokens: int = 3, completion_tokens: int = 5, model: str = "stub"):
    """Build a SimpleNamespace exposing exactly what LiteLlm reads off a response."""
    message = types.SimpleNamespace(content=content)
    choice = types.SimpleNamespace(message=message)
    usage = types.SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return types.SimpleNamespace(choices=[choice], usage=usage, model=model)


def _patch(monkeypatch: pytest.MonkeyPatch, response, captured: dict | None = None, *, native: bool = True) -> None:
    def fake(**kwargs):
        if captured is not None:
            captured.update(kwargs)
        return response

    monkeypatch.setattr("litellm.completion", fake)
    monkeypatch.setattr("litellm.supports_response_schema", lambda **kwargs: native)
    monkeypatch.setattr("litellm.completion_cost", lambda **kwargs: 0.0003)


@pytest.mark.unit
class TestLiteLlm:
    def test_native_structured_parse(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}
        _patch(monkeypatch, _response('{"value": "ok"}'), captured, native=True)
        out = LiteLlm("gpt-4o-mini").complete("q", response_format=_Reply)
        assert isinstance(out, Completion)
        assert out.parsed.value == "ok"
        assert captured["response_format"] is _Reply
        # The native path sends the prompt verbatim, with no JSON-schema instruction appended.
        assert captured["messages"][0]["content"] == "q"

    def test_non_native_prompted_json_parse(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}
        _patch(monkeypatch, _response('{"value": "ok"}'), captured, native=False)
        out = LiteLlm("local/m").complete("q", response_format=_Reply)
        assert isinstance(out, Completion)
        assert out.parsed.value == "ok"
        assert "response_format" not in captured
        # The non-native path appends a JSON-schema instruction to the prompt.
        assert "q" in captured["messages"][0]["content"]
        assert "schema" in captured["messages"][0]["content"].lower()

    def test_non_native_tolerates_json_fence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch(monkeypatch, _response('```json\n{"value": "fenced"}\n```'), native=False)
        out = LiteLlm("local/m").complete("q", response_format=_Reply)
        assert isinstance(out, Completion)
        assert out.parsed.value == "fenced"

    def test_non_native_tolerates_surrounding_prose(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch(monkeypatch, _response('Here you go: {"value": "x"} done'), native=False)
        out = LiteLlm("local/m").complete("q", response_format=_Reply)
        assert isinstance(out, Completion)
        assert out.parsed.value == "x"

    def test_malformed_native_is_malformed_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch(monkeypatch, _response("not json at all"), native=True)
        out = LiteLlm("gpt-4o-mini").complete("q", response_format=_Reply)
        assert isinstance(out, LlmError)
        assert out.kind == "malformed_output"

    def test_none_content_native_is_malformed_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # No content normalises to `{}`, which fails validation (value is required).
        _patch(monkeypatch, _response(None), native=True)
        out = LiteLlm("gpt-4o-mini").complete("q", response_format=_Reply)
        assert isinstance(out, LlmError)
        assert out.kind == "malformed_output"

    def test_usage_and_cost_populated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch(monkeypatch, _response('{"value": "ok"}', prompt_tokens=11, completion_tokens=7), native=True)
        out = LiteLlm("gpt-4o-mini").complete("q", response_format=_Reply)
        assert isinstance(out, Completion)
        assert out.usage.prompt_tokens == 11
        assert out.usage.completion_tokens == 7
        assert out.usage.cost_usd == 0.0003
        assert out.usage.latency_seconds is not None
        assert out.usage.latency_seconds >= 0

    def test_cost_unavailable_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("litellm.completion", lambda **kwargs: _response('{"value": "ok"}'))
        monkeypatch.setattr("litellm.supports_response_schema", lambda **kwargs: True)

        def boom(**kwargs):
            msg = "no pricing for this model"
            raise Exception(msg)

        monkeypatch.setattr("litellm.completion_cost", boom)
        out = LiteLlm("local/m").complete("q", response_format=_Reply)
        assert isinstance(out, Completion)
        assert out.usage.cost_usd is None

    def test_timeout_and_api_base_passed_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}
        _patch(monkeypatch, _response('{"value": "ok"}'), captured, native=True)
        LiteLlm("gpt-4o-mini", api_base="http://local", timeout=12.5, temperature=0.0).complete(
            "q", response_format=_Reply
        )
        assert captured["timeout"] == 12.5
        assert captured["api_base"] == "http://local"
        assert captured["temperature"] == 0.0

    @pytest.mark.parametrize(
        ("exc", "kind"),
        [
            (lambda: litellm.Timeout(message="t", model="m", llm_provider="openai"), "timeout"),
            (lambda: litellm.RateLimitError(message="r", llm_provider="openai", model="m"), "rate_limit"),
            (lambda: litellm.AuthenticationError(message="a", llm_provider="openai", model="m"), "auth"),
            (
                lambda: litellm.ContextWindowExceededError(message="c", model="m", llm_provider="openai"),
                "context_window_exceeded",
            ),
            (lambda: litellm.BadRequestError(message="b", model="m", llm_provider="openai"), "bad_request"),
            (lambda: litellm.APIConnectionError(message="x", llm_provider="openai", model="m"), "api_connection"),
            (lambda: litellm.APIError(status_code=500, message="e", llm_provider="openai", model="m"), "api_error"),
        ],
    )
    def test_exception_maps_to_llm_error(self, monkeypatch: pytest.MonkeyPatch, exc, kind: ProviderErrorKind) -> None:
        def fake(**kwargs):
            raise exc()

        monkeypatch.setattr("litellm.completion", fake)
        monkeypatch.setattr("litellm.supports_response_schema", lambda **kwargs: True)
        out = LiteLlm("m").complete("q", response_format=_Reply)
        assert isinstance(out, LlmError)
        assert out.kind == kind
        assert out.provider == "openai"


@pytest.mark.unit
class TestLiteLlmCompleteText:
    def test_returns_text_verbatim(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}
        _patch(monkeypatch, _response("SELECT 1"), captured, native=True)
        out = LiteLlm("gpt-4o-mini").complete_text("q")
        assert isinstance(out, TextCompletion)
        assert out.text == "SELECT 1"
        # No structured-output mode and no JSON instruction: the prompt is sent verbatim.
        assert "response_format" not in captured
        assert captured["messages"][0]["content"] == "q"

    def test_none_content_is_empty_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch(monkeypatch, _response(None), native=True)
        out = LiteLlm("gpt-4o-mini").complete_text("q")
        assert isinstance(out, TextCompletion)
        assert out.text == ""

    def test_usage_and_cost_populated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch(monkeypatch, _response("SELECT 1", prompt_tokens=11, completion_tokens=7), native=True)
        out = LiteLlm("gpt-4o-mini").complete_text("q")
        assert isinstance(out, TextCompletion)
        assert out.usage.prompt_tokens == 11
        assert out.usage.completion_tokens == 7
        assert out.usage.cost_usd == 0.0003
        assert out.usage.latency_seconds is not None
        assert out.usage.latency_seconds >= 0

    def test_cost_unavailable_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("litellm.completion", lambda **kwargs: _response("SELECT 1"))

        def boom(**kwargs):
            msg = "no pricing for this model"
            raise Exception(msg)

        monkeypatch.setattr("litellm.completion_cost", boom)
        out = LiteLlm("local/m").complete_text("q")
        assert isinstance(out, TextCompletion)
        assert out.usage.cost_usd is None

    def test_timeout_and_api_base_passed_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}
        _patch(monkeypatch, _response("SELECT 1"), captured, native=True)
        LiteLlm("gpt-4o-mini", api_base="http://local", timeout=12.5, temperature=0.0).complete_text("q")
        assert captured["timeout"] == 12.5
        assert captured["api_base"] == "http://local"
        assert captured["temperature"] == 0.0

    @pytest.mark.parametrize(
        ("exc", "kind"),
        [
            (lambda: litellm.Timeout(message="t", model="m", llm_provider="openai"), "timeout"),
            (lambda: litellm.RateLimitError(message="r", llm_provider="openai", model="m"), "rate_limit"),
            (lambda: litellm.AuthenticationError(message="a", llm_provider="openai", model="m"), "auth"),
            (
                lambda: litellm.ContextWindowExceededError(message="c", model="m", llm_provider="openai"),
                "context_window_exceeded",
            ),
            (lambda: litellm.BadRequestError(message="b", model="m", llm_provider="openai"), "bad_request"),
            (lambda: litellm.APIConnectionError(message="x", llm_provider="openai", model="m"), "api_connection"),
            (lambda: litellm.APIError(status_code=500, message="e", llm_provider="openai", model="m"), "api_error"),
        ],
    )
    def test_exception_maps_to_llm_error(self, monkeypatch: pytest.MonkeyPatch, exc, kind: ProviderErrorKind) -> None:
        def fake(**kwargs):
            raise exc()

        monkeypatch.setattr("litellm.completion", fake)
        out = LiteLlm("m").complete_text("q")
        assert isinstance(out, LlmError)
        assert out.kind == kind
        assert out.provider == "openai"

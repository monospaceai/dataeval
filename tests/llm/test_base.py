"""Tests for the LLM seam's pure-Python surface: `StubLlm`, `resolve_llm`, and the protocol."""

import pytest
from pydantic import BaseModel

from evaldata.llm import Completion, Llm, StubLlm, TextCompletion, Usage, resolve_llm
from evaldata.llm.lite import LiteLlm
from evaldata.types import LlmError


class _Reply(BaseModel):
    value: str


@pytest.mark.unit
class TestStubLlm:
    def test_returns_completion_for_basemodel_reply(self) -> None:
        stub = StubLlm(_Reply(value="hi"))
        out = stub.complete("p", response_format=_Reply)
        assert isinstance(out, Completion)
        assert out.parsed.value == "hi"
        assert out.usage == Usage()

    def test_returns_error_unchanged(self) -> None:
        err = LlmError(kind="api_error", message="boom", provider="openai")
        out = StubLlm(err).complete("p", response_format=_Reply)
        assert out is err

    def test_records_every_prompt(self) -> None:
        stub = StubLlm(_Reply(value="x"))
        stub.complete("first", response_format=_Reply)
        stub.complete("second", response_format=_Reply)
        assert stub.prompts == ["first", "second"]

    def test_callable_reply_resolved_per_prompt(self) -> None:
        def reply(prompt: str, fmt: type[BaseModel]) -> _Reply | LlmError:
            return _Reply(value=prompt.upper())

        out = StubLlm(reply).complete("hi", response_format=_Reply)
        assert isinstance(out, Completion)
        assert out.parsed.value == "HI"

    def test_callable_reply_can_return_error(self) -> None:
        err = LlmError(kind="timeout", message="slow")
        out = StubLlm(lambda p, f: err).complete("p", response_format=_Reply)
        assert out is err

    def test_satisfies_llm_protocol(self) -> None:
        assert isinstance(StubLlm(_Reply(value="x")), Llm)

    def test_complete_text_returns_text_completion(self) -> None:
        out = StubLlm("SELECT 1").complete_text("p")
        assert isinstance(out, TextCompletion)
        assert out.text == "SELECT 1"
        assert out.usage == Usage()

    def test_complete_text_returns_error_unchanged(self) -> None:
        err = LlmError(kind="api_error", message="boom", provider="openai")
        out = StubLlm(err).complete_text("p")
        assert out is err

    def test_complete_text_callable_resolved_with_none_format(self) -> None:
        def reply(prompt: str, fmt: type[BaseModel] | None) -> str:
            assert fmt is None
            return prompt.upper()

        out = StubLlm(reply).complete_text("hi")
        assert isinstance(out, TextCompletion)
        assert out.text == "HI"

    def test_complete_text_callable_can_return_error(self) -> None:
        err = LlmError(kind="timeout", message="slow")
        out = StubLlm(lambda p, f: err).complete_text("p")
        assert out is err

    def test_complete_text_records_every_prompt(self) -> None:
        stub = StubLlm("SELECT 1")
        stub.complete_text("first")
        stub.complete_text("second")
        assert stub.prompts == ["first", "second"]


@pytest.mark.unit
class TestResolveLlm:
    def test_string_resolves_to_lite_llm(self) -> None:
        llm = resolve_llm("openai/gpt-4o-mini", temperature=0.0, timeout=12.5)
        assert isinstance(llm, LiteLlm)
        assert llm._model == "openai/gpt-4o-mini"
        assert llm._temperature == 0.0
        assert llm._timeout == 12.5

    def test_llm_passed_through_unchanged(self) -> None:
        stub = StubLlm(_Reply(value="x"))
        assert resolve_llm(stub, temperature=0.0, timeout=1.0) is stub

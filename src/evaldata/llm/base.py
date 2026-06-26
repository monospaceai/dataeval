"""The LLM seam: a swappable `Llm` protocol, its value types, and a test double.

`Llm.complete` takes a prompt and a Pydantic `response_format` and returns a parsed
`Completion` or a typed `LlmError`. Concrete backends (the litellm one, a test `StubLlm`)
satisfy the protocol; `resolve_llm` turns a model string into the litellm backend or passes
an `Llm` through unchanged.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Generic, Protocol, TypeVar, cast, runtime_checkable

from pydantic import BaseModel

from evaldata.types import LlmError

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class Usage:
    """Telemetry for one LLM call: token counts, cost, and latency, each `None` when unknown."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    latency_seconds: float | None = None


@dataclass(frozen=True)
class Completion(Generic[T]):
    """A successful LLM call: the parsed `response_format` instance plus its `Usage`."""

    parsed: T
    usage: Usage


@dataclass(frozen=True)
class TextCompletion:
    """A successful free-text LLM call: the raw reply text plus its `Usage`."""

    text: str
    usage: Usage


@runtime_checkable
class Llm(Protocol):
    """Produces a parsed structured reply or a free-text reply for a prompt, or a typed error."""

    def complete(self, prompt: str, *, response_format: type[T]) -> Completion[T] | LlmError:
        """Complete `prompt`, parsing the reply into `response_format`.

        Args:
            prompt: The user prompt to send.
            response_format: The Pydantic model the reply must validate against.

        Returns:
            A `Completion` carrying the parsed model and telemetry, or an `LlmError` on an
            expected provider or parsing failure.
        """
        ...

    def complete_text(self, prompt: str) -> "TextCompletion | LlmError":
        """Complete `prompt`, returning the reply as free text.

        Args:
            prompt: The user prompt to send.

        Returns:
            A `TextCompletion` carrying the reply text and telemetry, or an `LlmError` on an
            expected provider failure.
        """
        ...


@dataclass
class StubLlm:
    """An in-memory `Llm` test double: returns a fixed reply and records every prompt.

    `reply` is the canned outcome: a `str` (for `complete_text`), a `BaseModel` (for
    `complete`), an `LlmError` (returned as-is), or a callable resolving one of those from the
    prompt and the requested `response_format` (which is `None` for `complete_text`). Each call
    appends its prompt to `prompts`.
    """

    reply: "str | BaseModel | LlmError | Callable[[str, type[BaseModel] | None], str | BaseModel | LlmError]"
    prompts: list[str] = field(default_factory=list)

    def complete(self, prompt: str, *, response_format: type[T]) -> Completion[T] | LlmError:
        """Record `prompt` and return the resolved canned reply as a `Completion`.

        Args:
            prompt: The user prompt, appended to `prompts`.
            response_format: The Pydantic model the reply is presumed to match.

        Returns:
            The configured `LlmError`, or a `Completion` wrapping the configured model with
            an empty `Usage`.
        """
        self.prompts.append(prompt)
        resolved = self._resolve(prompt, response_format)
        if isinstance(resolved, LlmError):
            return resolved
        return Completion(parsed=cast("T", resolved), usage=Usage())

    def complete_text(self, prompt: str) -> "TextCompletion | LlmError":
        """Record `prompt` and return the resolved canned reply as a `TextCompletion`.

        Args:
            prompt: The user prompt, appended to `prompts`.

        Returns:
            The configured `LlmError`, or a `TextCompletion` carrying the reply coerced to
            text with an empty `Usage`.
        """
        self.prompts.append(prompt)
        resolved = self._resolve(prompt, None)
        if isinstance(resolved, LlmError):
            return resolved
        return TextCompletion(text=str(resolved), usage=Usage())

    def _resolve(self, prompt: str, response_format: type[BaseModel] | None) -> "str | BaseModel | LlmError":
        reply = self.reply
        if isinstance(reply, (str, BaseModel, LlmError)):
            return reply
        return reply(prompt, response_format)


def resolve_llm(model: "str | Llm", *, temperature: float | None = None, timeout: float | None = None) -> "Llm":
    """Resolve `model` to an `Llm`, defaulting a model string to the litellm backend.

    A string is wrapped in the litellm-backed `LiteLlm`; an existing `Llm` is returned
    unchanged. `temperature` and `timeout` apply only to the string path — they configure the
    constructed `LiteLlm` and are ignored when an `Llm` is passed.

    Args:
        model: A litellm model identifier, or an `Llm` to use directly.
        temperature: Sampling temperature for the string path; `None` leaves the default.
        timeout: Per-request timeout in seconds for the string path.

    Returns:
        An `Llm`: the constructed `LiteLlm` for a string, or `model` unchanged.

    Raises:
        ImportError: If `model` is a string and the `litellm` extra is not installed.
    """
    if isinstance(model, str):
        try:
            from evaldata.llm.lite import LiteLlm
        except ImportError as e:
            msg = "a model string requires the 'litellm' extra: install evaldata[litellm]"
            raise ImportError(msg) from e
        return LiteLlm(model, temperature=temperature, timeout=timeout)
    return model

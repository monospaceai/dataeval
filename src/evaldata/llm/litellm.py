"""`LiteLlm`: the litellm-backed `Llm`. The only module that imports `litellm`."""

import time

import litellm
from pydantic import ValidationError

from evaldata.llm.base import Completion, T, TextCompletion, Usage
from evaldata.types import LlmError, ProviderErrorKind


class LiteLlm:
    """An `Llm` backed by `litellm.completion`, returning a parsed reply or a typed `LlmError`."""

    def __init__(
        self,
        model: str,
        *,
        api_base: str | None = None,
        temperature: float | None = None,
        timeout: float | None = None,
    ) -> None:
        """Configure the backend.

        Args:
            model: The litellm model identifier (e.g. `"openai/gpt-4o-mini"`).
            api_base: An override base URL for the provider, or `None` for the default.
            temperature: Sampling temperature; `None` leaves the provider default.
            timeout: Per-request timeout in seconds.
        """
        self._model = model
        self._api_base = api_base
        self._temperature = temperature
        self._timeout = timeout

    def complete(self, prompt: str, *, response_format: type[T]) -> Completion[T] | LlmError:
        """Complete `prompt`, parsing the reply into `response_format`.

        Requires the model's provider to support native structured output: a model that does not
        yields a `bad_request` `LlmError`. Expected provider failures are mapped to a typed
        `LlmError`.

        Args:
            prompt: The user prompt to send.
            response_format: The Pydantic model the reply must validate against.

        Returns:
            A `Completion` carrying the parsed model and telemetry, or an `LlmError`.
        """
        if not litellm.supports_response_schema(model=self._model):
            return LlmError(
                kind="bad_request",
                message=f"grader model {self._model!r} does not support structured output; use a "
                f"structured-output-capable model",
                provider=None,
            )
        called = self._call(prompt, {"response_format": response_format})
        if isinstance(called, LlmError):
            return called
        response, elapsed = called

        content = response.choices[0].message.content
        try:
            parsed = response_format.model_validate_json(content or "{}")
        except ValidationError as e:
            return LlmError(
                kind="malformed_output",
                message=f"model returned malformed structured output: {(content or '')[:200]!r}",
                provider=None,
                cause=e,
            )
        return Completion(parsed=parsed, usage=self._usage(response, elapsed))

    def complete_text(self, prompt: str) -> TextCompletion | LlmError:
        """Complete `prompt`, returning the reply as free text.

        Sends the prompt verbatim with no structured-output mode and no JSON instruction.
        Expected provider failures are mapped to a typed `LlmError`.

        Args:
            prompt: The user prompt to send.

        Returns:
            A `TextCompletion` carrying the reply text and telemetry, or an `LlmError`.
        """
        called = self._call(prompt, {})
        if isinstance(called, LlmError):
            return called
        response, elapsed = called
        content = response.choices[0].message.content
        return TextCompletion(text=content or "", usage=self._usage(response, elapsed))

    def _call(self, content: str, extra: dict) -> "tuple[litellm.ModelResponse, float] | LlmError":
        """Send one `litellm.completion`, mapping expected failures to a typed `LlmError`.

        Args:
            content: The message content to send.
            extra: Extra keyword arguments to merge into the call (e.g. `response_format`).

        Returns:
            A `(response, elapsed_seconds)` tuple, or an `LlmError` on an expected failure.
        """
        kwargs: dict = {
            "model": self._model,
            "messages": [{"role": "user", "content": content}],
            "timeout": self._timeout,
            **extra,
        }
        if self._api_base is not None:
            kwargs["api_base"] = self._api_base
        if self._temperature is not None:
            kwargs["temperature"] = self._temperature

        start = time.perf_counter()
        try:
            response = litellm.completion(**kwargs)
        except litellm.Timeout as e:
            return self._provider_error("timeout", e)
        except litellm.RateLimitError as e:
            return self._provider_error("rate_limit", e)
        except litellm.AuthenticationError as e:
            return self._provider_error("auth", e)
        except litellm.ContextWindowExceededError as e:
            return self._provider_error("context_window_exceeded", e)
        except litellm.BadRequestError as e:
            return self._provider_error("bad_request", e)
        except litellm.APIConnectionError as e:
            return self._provider_error("api_connection", e)
        except litellm.APIError as e:
            return self._provider_error("api_error", e)
        return response, time.perf_counter() - start

    @staticmethod
    def _usage(response: "litellm.ModelResponse", elapsed: float) -> Usage:
        """Extract token counts, cost, and latency off a litellm response.

        Args:
            response: The litellm response object.
            elapsed: The measured call latency in seconds.

        Returns:
            A `Usage` with token counts and cost when available, `None` otherwise.
        """
        usage = getattr(response, "usage", None)
        try:
            cost = litellm.completion_cost(completion_response=response)
        except Exception:
            # Local/unknown models have no pricing table; cost is simply unavailable.
            cost = None
        return Usage(
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            cost_usd=cost,
            latency_seconds=elapsed,
        )

    @staticmethod
    def _provider_error(kind: ProviderErrorKind, exc: Exception) -> LlmError:
        """Build an `LlmError` from a litellm exception, capturing `llm_provider`.

        Args:
            kind: The typed provider-call error category.
            exc: The litellm exception to wrap.

        Returns:
            An `LlmError` carrying the kind, message, provider (if available), and cause.
        """
        return LlmError(
            kind=kind,
            message=str(exc) or type(exc).__name__,
            provider=getattr(exc, "llm_provider", None),
            cause=exc,
        )

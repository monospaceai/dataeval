"""``PromptSolver``: a single-prompt, LLM-backed ``Solver`` over ``litellm``.

Renders a question + dialect into one user message, calls ``litellm.completion``, and
extracts the SQL from the model's reply (stripping a ``` fence when present). Expected
provider failures (timeout, rate limit, auth, bad request, context-window overflow,
connection/API errors, empty reply) are returned as ``SolverOutput.error`` rather than
raised — errors-as-values — so the runner composes a diagnostic instead of crashing.

``litellm`` is imported at module top: this module lives behind the optional ``litellm``
extra and is imported on demand (``from data_eval.solvers.prompt import PromptSolver``),
mirroring ``PostgresAdapter``. It is deliberately NOT exported from ``solvers/__init__``.
"""

import re
import time

import litellm

from data_eval.types import EvalCase, SolverError, SolverErrorKind, SolverOutput

DEFAULT_PROMPT_TEMPLATE = """Generate a {dialect} SQL query that answers the following question.
Return only the SQL query with no explanation or markdown.

Question: {input}
SQL:
"""

_FENCE_RE = re.compile(r"```(?:sql)?\s*([\s\S]*?)```", re.IGNORECASE)


def _extract_sql(text: str) -> str:
    """Extract SQL from raw model text, stripping a Markdown ``` fence if present.

    Returns the contents of the first ```/```sql fence (stripped) when that is
    non-empty; otherwise returns the whole text stripped.
    """
    match = _FENCE_RE.search(text)
    if match is not None:
        inner = match.group(1).strip()
        if inner:
            return inner
    return text.strip()


class PromptSolver:
    """Single-prompt LLM ``Solver``: question -> SQL via ``litellm.completion``."""

    def __init__(
        self,
        model: str,
        prompt_template: str = DEFAULT_PROMPT_TEMPLATE,
        timeout: float | None = None,
    ) -> None:
        """Configure the solver.

        Args:
            model: The litellm model identifier (e.g. ``"openai/gpt-4o-mini"``). Required.
            prompt_template: A ``str.format_map`` template with ``{dialect}`` and
                ``{input}`` fields. Defaults to ``DEFAULT_PROMPT_TEMPLATE``.
            timeout: Per-request timeout in seconds, passed to ``litellm.completion``.
        """
        self._model = model
        self._prompt_template = prompt_template
        self._timeout = timeout

    def solve(self, case: EvalCase) -> SolverOutput:
        """Produce SQL for ``case``; return a success or a typed ``SolverError``.

        Renders the prompt from the case's dialect (or platform kind) and input, calls
        the model, and extracts the SQL. Expected provider failures are mapped to a
        ``SolverError`` and returned as ``SolverOutput.error``; on success the SQL is
        returned alongside token/latency/cost telemetry.
        """
        dialect = case.platform.dialect or case.platform.kind
        rendered = self._prompt_template.format_map({"dialect": dialect, "input": case.input})
        messages = [{"role": "user", "content": rendered}]
        start = time.perf_counter()
        try:
            response = litellm.completion(model=self._model, messages=messages, timeout=self._timeout)
        except litellm.Timeout as e:
            return SolverOutput(error=self._error("timeout", e))
        except litellm.RateLimitError as e:
            return SolverOutput(error=self._error("rate_limit", e))
        except litellm.AuthenticationError as e:
            return SolverOutput(error=self._error("auth", e))
        except litellm.ContextWindowExceededError as e:
            return SolverOutput(error=self._error("context_window_exceeded", e))
        except litellm.BadRequestError as e:
            return SolverOutput(error=self._error("bad_request", e))
        except litellm.APIConnectionError as e:
            return SolverOutput(error=self._error("api_connection", e))
        except litellm.APIError as e:
            return SolverOutput(error=self._error("api_error", e))
        elapsed = time.perf_counter() - start

        content = response.choices[0].message.content
        sql = _extract_sql(content) if content is not None else ""
        if not sql:
            return SolverOutput(
                error=SolverError(kind="empty_response", message="model returned no SQL", provider=None)
            )

        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        try:
            cost = litellm.completion_cost(completion_response=response)
        except Exception:
            # Local/unknown models have no pricing table; cost is simply unavailable.
            cost = None

        return SolverOutput(
            output=sql,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_seconds=elapsed,
            cost_usd=cost,
            metadata={"model": getattr(response, "model", self._model)},
        )

    @staticmethod
    def _error(kind: SolverErrorKind, exc: Exception) -> SolverError:
        """Build a ``SolverError`` from a litellm exception, capturing ``llm_provider``."""
        return SolverError(kind=kind, message=str(exc), provider=getattr(exc, "llm_provider", None))

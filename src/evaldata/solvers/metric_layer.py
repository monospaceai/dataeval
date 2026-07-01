"""`MetricLayerSolver`: a single-prompt LLM `Solver` for dbt Semantic Layer queries."""

from evaldata.llm import Llm, resolve_llm
from evaldata.solvers.errors import to_solver_error
from evaldata.types import EvalCase, LlmError, MetricQuery, SolverOutput

SL_PROMPT_TEMPLATE = """You are querying a dbt Semantic Layer with MetricFlow. Answer the question by
choosing metrics and group-by items from the semantic layer below. A group-by item is a dimension,
an entity, or a time dimension with a grain (for example `metric_time__month` or `customer__country`).

Semantic layer:
{semantic_layer}

Question: {input}
"""


class MetricLayerSolver:
    """Single-prompt LLM `Solver`: question -> a `MetricQuery` via structured output."""

    def __init__(
        self,
        model: str | Llm,
        prompt_template: str = SL_PROMPT_TEMPLATE,
        timeout: float | None = None,
        temperature: float | None = None,
    ) -> None:
        """Configure the solver.

        Args:
            model: A litellm model identifier (e.g. `"openai/gpt-4o-mini"`), or an `Llm` to use
                directly. `timeout` and `temperature` apply only to the model-string path.
            prompt_template: A `str.format_map` template with `{semantic_layer}` and `{input}`
                fields; `{semantic_layer}` is filled from `case.metadata["sl_context"]`.
            timeout: Per-request timeout in seconds.
            temperature: Sampling temperature; `None` leaves the provider default. Use `0` for
                deterministic output.
        """
        self._llm = resolve_llm(model, temperature=temperature, timeout=timeout)
        self._model = model if isinstance(model, str) else type(model).__name__
        self._prompt_template = prompt_template

    def solve(self, case: EvalCase) -> SolverOutput:
        """Produce a metric query for `case`.

        Renders the prompt from the question and the case's semantic-layer context, then asks
        the model for a structured `MetricQuery`. Expected provider failures are mapped to a
        `SolverError` in `SolverOutput.error`.

        Args:
            case: The eval case to solve.

        Returns:
            A `SolverOutput` carrying either the metric query plus token/latency/cost
            telemetry on success, or a typed `SolverError` on an expected failure.
        """
        prompt = self._prompt_template.format_map(
            {"input": case.input, "semantic_layer": case.metadata.get("sl_context", "")}
        )
        completion = self._llm.complete(prompt, response_format=MetricQuery)
        if isinstance(completion, LlmError):
            return SolverOutput(error=to_solver_error(completion))

        usage = completion.usage
        return SolverOutput(
            query=completion.parsed,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            latency_seconds=usage.latency_seconds,
            cost_usd=usage.cost_usd,
            metadata={"model": self._model},
        )

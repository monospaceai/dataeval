"""Translate an `LlmError` into the solver's `SolverError` vocabulary."""

from evaldata.types import LlmError, SolverError


def to_solver_error(error: LlmError) -> SolverError:
    """Translate an `LlmError` into a `SolverError`, preserving message, provider, and cause.

    A `malformed_output` becomes `invalid_structured_output`; every provider kind maps through
    unchanged.

    Args:
        error: The error returned by the `Llm` call.

    Returns:
        The equivalent `SolverError`.
    """
    kind = "invalid_structured_output" if error.kind == "malformed_output" else error.kind
    return SolverError(kind=kind, message=error.message, provider=error.provider, cause=error.cause)

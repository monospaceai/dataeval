"""Pure combination of ordered `SemanticVerdict`s into a single `ScoreResult`."""

from evaldata.types import ScoreResult, SemanticVerdict


def combine(verdicts: list[SemanticVerdict], *, scorer: str) -> ScoreResult:
    """Combine ordered equivalence verdicts into one pass/fail `ScoreResult`.

    The first `"equivalent"` verdict passes the result; if no verdict confirms, the result
    fails as undecided. A verdict never carries a diff, so the result carries none. Every
    verdict is recorded in `metadata["verdicts"]`.

    Args:
        verdicts: The verdicts the checks produced, in the order they ran.
        scorer: The scorer name to stamp on the `ScoreResult`.

    Returns:
        A `ScoreResult` that passes iff some verdict confirmed equivalence.
    """
    metadata = {"verdicts": [v.model_dump() for v in verdicts]}
    decisive = next((v for v in verdicts if v.equivalence == "equivalent"), None)
    if decisive is None:
        return ScoreResult(
            scorer=scorer,
            passed=False,
            explanation="no semantic check could confirm equivalence",
            metadata=metadata,
        )
    return ScoreResult(scorer=scorer, passed=True, metadata=metadata)

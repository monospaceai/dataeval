"""Pure combination of ordered `SemanticVerdict`s into a single `ScoreResult`."""

from evaldata.types import ScoreResult, SemanticVerdict


def combine(verdicts: list[SemanticVerdict], *, scorer: str) -> ScoreResult:
    """Combine ordered equivalence verdicts into one `ScoreResult`.

    The first `"equivalent"` verdict yields a passing result; if no verdict confirms, the
    result is inconclusive (the checks never refute, so an undecided run is not a fail). A
    verdict never carries a diff, so the result carries none. Every verdict is recorded in
    `metadata["verdicts"]`.

    Args:
        verdicts: The verdicts the checks produced, in the order they ran.
        scorer: The scorer name to stamp on the `ScoreResult`.

    Returns:
        A passing `ScoreResult` when some verdict confirmed equivalence, else an inconclusive one.
    """
    metadata = {"verdicts": [v.model_dump() for v in verdicts]}
    decisive = next((v for v in verdicts if v.equivalence == "equivalent"), None)
    if decisive is None:
        return ScoreResult(
            scorer=scorer,
            verdict="inconclusive",
            explanation="no semantic check could confirm equivalence",
            metadata=metadata,
        )
    return ScoreResult(scorer=scorer, verdict="pass", basis="proven", metadata=metadata)

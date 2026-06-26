"""The LLM seam: the `Llm` protocol, its value types, and the litellm-backed `LiteLlm`.

`LiteLlm` requires the `litellm` extra and is imported lazily; everything else has no
optional dependency.
"""

from typing import TYPE_CHECKING, Any

from evaldata.llm.base import Completion, Llm, StubLlm, TextCompletion, Usage, resolve_llm
from evaldata.types import LlmError

if TYPE_CHECKING:
    from evaldata.llm.lite import LiteLlm

__all__ = ["Completion", "LiteLlm", "Llm", "LlmError", "StubLlm", "TextCompletion", "Usage", "resolve_llm"]


def __getattr__(name: str) -> Any:
    if name == "LiteLlm":
        try:
            from evaldata.llm.lite import LiteLlm
        except ImportError as e:
            msg = "LiteLlm requires the 'litellm' extra: install evaldata[litellm]"
            raise ImportError(msg) from e
        return LiteLlm
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


def __dir__() -> list[str]:
    return sorted([*globals(), "LiteLlm"])

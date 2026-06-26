# LLM

The `Llm` protocol and its value types — the single interface every model call goes through. The
`PromptSolver` uses it for text completions; the `LlmJudge` uses it for structured ones. `LiteLlm`
is the litellm-backed implementation (requires the `litellm` extra); `StubLlm` is a fixed-reply
implementation for tests.

::: evaldata.llm

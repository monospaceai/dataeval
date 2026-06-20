"""Loaders: build `EvalCase`s from authoring surfaces (Python decorator first; YAML in v1.x)."""

from evaldata.loaders.python import eval_case, read_eval_case

__all__ = ["eval_case", "read_eval_case"]

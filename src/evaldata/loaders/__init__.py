"""Loaders: build `EvalCase`s from authoring surfaces (Python decorator, benchmark datasets)."""

from evaldata.loaders.benchmarks import load_bird, load_spider
from evaldata.loaders.python import eval_case, read_eval_case

__all__ = ["eval_case", "load_bird", "load_spider", "read_eval_case"]

"""Hypothesis profile for the scorer property suite."""

from hypothesis import HealthCheck, settings

settings.register_profile(
    "ci",
    deadline=None,
    max_examples=150,
    suppress_health_check=[HealthCheck.data_too_large],
)
settings.load_profile("ci")

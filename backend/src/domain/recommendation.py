"""Singular module alias for callers that use the feature-name convention."""

from .recommendations import (
    NO_SOLUTION,
    RECOMMENDED,
    UNAVAILABLE,
    build_boundary_context,
    recommend_for_part,
    recommend_retests,
)


def recommend(*args, **kwargs):
    """Dispatch batch rows to the batch API and one mapping to the part API."""
    if args and isinstance(args[0], list):
        return recommend_retests(*args, **kwargs)
    return recommend_for_part(*args, **kwargs)


recommend_one = recommend_for_part
recommend_measurements = recommend_for_part
suggest_for_part = recommend_for_part
suggest_measurements = recommend_for_part
build_recommendations = recommend_retests
build_suggestions = recommend_retests

__all__ = [
    'NO_SOLUTION', 'RECOMMENDED', 'UNAVAILABLE', 'build_boundary_context',
    'recommend', 'recommend_for_part', 'recommend_retests', 'recommend_one',
    'recommend_measurements', 'suggest_for_part', 'suggest_measurements',
    'build_recommendations', 'build_suggestions',
]

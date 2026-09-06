from typing import Any, TypedDict


class RoundState(TypedDict, total=False):
    experiment: dict[str, Any]
    views: dict[str, dict[str, Any]]
    proposals: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    invalid_decisions: list[dict[str, Any]]
    human_requests: list[dict[str, Any]]
    human_responses: list[dict[str, Any]]

"""Deterministic events; these are privileged evaluator/presenter records."""

from typing import Any

from mars_agents.domain.actions import AgentAction
from mars_agents.domain.models import Experiment, ExperimentEvent


def record_event(
    experiment: Experiment,
    kind: str,
    summary: str,
    *,
    agent_id: str | None = None,
    action: AgentAction | None = None,
    cost: float | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    experiment.events.append(
        ExperimentEvent(
            id=f"{experiment.id}:r{experiment.round}:event:{len(experiment.events)}",
            round=experiment.round,
            kind=kind,
            summary=summary,
            agent_id=agent_id,
            action=action,
            cost=cost,
            data=data or {},
        )
    )

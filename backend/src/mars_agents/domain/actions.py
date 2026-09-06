"""Action proposals are data. Validation reads the start-of-round snapshot only."""

from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from mars_agents.domain.models import Experiment


class AgentAction(StrEnum):
    MOVE = "move"
    OBSERVE = "observe"
    DRILL = "drill"
    JOIN_AI_POOL = "join_ai_pool"
    CHOOSE_HUMAN = "choose_human"


class ActionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    agent_id: str = Field(min_length=1)
    action: AgentAction
    x: int | None = Field(default=None, strict=True, ge=0)
    y: int | None = Field(default=None, strict=True, ge=0)
    reason: str = Field(default="", max_length=600)

    @model_validator(mode="after")
    def action_coordinates(self) -> Self:
        if self.action == AgentAction.MOVE:
            if self.x is None or self.y is None:
                raise ValueError("MOVE requires both x and y")
        elif self.x is not None or self.y is not None:
            raise ValueError(
                "Only MOVE accepts coordinates; other actions use the current location"
            )
        return self


def _observed_positions(agent) -> set[tuple[int, int]]:
    return {
        (item.position.x, item.position.y)
        for item in agent.evidence
        if item.kind == "observation"
    }


def legal_actions(experiment: "Experiment", agent_id: str) -> list[str]:
    if agent_id not in experiment.agents:
        raise ValueError(f"Unknown agent: {agent_id}")
    if experiment.status != "running" or experiment.round >= experiment.config.max_rounds:
        return []
    agent = experiment.agents[agent_id]
    config = experiment.config
    budget = agent.budget_remaining
    actions: list[str] = []
    if config.grid_width * config.grid_height > 1 and budget >= config.move_cost_per_cell:
        actions.append(AgentAction.MOVE.value)
    if budget >= config.observe_cost and (
        agent.position.x,
        agent.position.y,
    ) not in _observed_positions(agent):
        actions.append(AgentAction.OBSERVE.value)
    if budget >= config.drill_cost:
        actions.append(AgentAction.DRILL.value)
    if (
        agent.regime == "private"
        and config.treatment in ("free_choice", "ai_collab_available")
        and budget >= config.join_pool_cost
    ):
        actions.append(AgentAction.JOIN_AI_POOL.value)
    # V1 allows one query. Increasing max_human_queries permits repeat purchases
    # in HUMAN_ASSISTED; it never restores access to the AI pool.
    if (
        agent.regime in ("private", "human_assisted")
        and config.treatment in ("free_choice", "human_available")
        and agent.human_queries < config.max_human_queries
        and budget >= config.human_cost
    ):
        actions.append(AgentAction.CHOOSE_HUMAN.value)
    return actions


def validate_action(experiment: "Experiment", proposal: ActionProposal) -> float:
    """Return cost without charging it, or reject the proposal without mutation."""
    if proposal.action.value not in legal_actions(experiment, proposal.agent_id):
        raise ValueError(f"{proposal.action.value} is unavailable for {proposal.agent_id}")
    agent = experiment.agents[proposal.agent_id]
    config = experiment.config
    if proposal.action == AgentAction.MOVE:
        if proposal.x is None or proposal.y is None:
            raise ValueError("MOVE requires a destination")
        if not (0 <= proposal.x < config.grid_width and 0 <= proposal.y < config.grid_height):
            raise ValueError("MOVE destination is outside the grid")
        distance = abs(proposal.x - agent.position.x) + abs(proposal.y - agent.position.y)
        if distance == 0:
            raise ValueError("MOVE must change position")
        cost = float(Decimal(str(config.move_cost_per_cell)) * distance)
    else:
        cost = {
            AgentAction.OBSERVE: config.observe_cost,
            AgentAction.DRILL: config.drill_cost,
            AgentAction.JOIN_AI_POOL: config.join_pool_cost,
            AgentAction.CHOOSE_HUMAN: config.human_cost,
        }[proposal.action]
    if cost > agent.budget_remaining:
        raise ValueError(
            f"{proposal.action.value} costs {cost}; budget is {agent.budget_remaining}"
        )
    return float(cost)

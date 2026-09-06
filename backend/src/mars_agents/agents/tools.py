"""Proposal-only tools with strict arguments and an independent one-action guard."""

from collections.abc import Callable
from threading import Lock

from pydantic import BaseModel, ConfigDict, Field, StrictInt
from smolagents import Tool

from mars_agents.domain.actions import ActionProposal, AgentAction

ACTION_NAMES = ("MOVE", "OBSERVE", "DRILL", "JOIN_AI_POOL", "CHOOSE_HUMAN")


class InvalidChoice(ValueError):
    """Contains only a fixed, safe correction, never raw provider/domain errors."""


class ReasonArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    reason: str = Field(min_length=1, max_length=320)


class MoveArguments(ReasonArguments):
    x: StrictInt
    y: StrictInt


class ActionCollector:
    def __init__(
        self,
        agent_id: str,
        allowed: frozenset[str],
        validate: Callable[[ActionProposal], float],
    ):
        self.agent_id = agent_id
        self.allowed = allowed
        self._validate = validate
        self._lock = Lock()
        self.proposal: ActionProposal | None = None

    def accept(self, action: str, **arguments) -> ActionProposal:
        with self._lock:
            if self.proposal is not None:
                raise InvalidChoice("Choose exactly one action; multiple proposals are invalid.")
            if action not in self.allowed:
                raise InvalidChoice("That tool is unavailable. Choose one of the supplied tools.")
            parsed = (MoveArguments if action == "MOVE" else ReasonArguments).model_validate(
                arguments
            )
            proposal = ActionProposal(
                agent_id=self.agent_id, action=AgentAction(action.lower()), **parsed.model_dump()
            )
            try:
                self._validate(proposal)
            except ValueError:
                raise InvalidChoice(
                    "The action is illegal for your position, regime, or budget. "
                    "Recheck the view and choose exactly one legal action."
                ) from None
            self.proposal = proposal
            return proposal


class ActionTool(Tool):
    output_type = "object"
    inputs = {"reason": {"type": "string", "description": "Decision reason, at most 320 chars."}}

    def __init__(self, action: str, collector: ActionCollector):
        self.action = action
        self.name = action.lower()
        self.description = {
            "OBSERVE": "Propose buying a noisy observation at your current location.",
            "DRILL": "Propose paying to drill your current location for definitive local water.",
            "JOIN_AI_POOL": "Propose joining the information pool, effective next round.",
            "CHOOSE_HUMAN": "Propose buying private human guidance at the stated cost.",
        }[action]
        self.collector = collector
        super().__init__()

    def forward(self, reason: str) -> ActionProposal:
        return self.collector.accept(self.action, reason=reason)


class MoveTool(Tool):
    name = "move"
    description = "Propose moving to a different in-bounds cell at Manhattan distance cost."
    output_type = "object"
    inputs = {
        "x": {"type": "integer", "description": "Destination x coordinate."},
        "y": {"type": "integer", "description": "Destination y coordinate."},
        "reason": {"type": "string", "description": "Decision reason, at most 320 chars."},
    }

    def __init__(self, collector: ActionCollector):
        self.collector = collector
        super().__init__()

    def forward(self, x: int, y: int, reason: str) -> ActionProposal:
        return self.collector.accept("MOVE", x=x, y=y, reason=reason)


def action_tools(collector: ActionCollector) -> list[Tool]:
    return [
        MoveTool(collector) if action == "MOVE" else ActionTool(action, collector)
        for action in ACTION_NAMES
        if action in collector.allowed
    ]

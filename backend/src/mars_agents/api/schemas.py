"""Presenter-only response schemas. Agent views are separate domain allowlists."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ResponseModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Position(ResponseModel):
    x: int
    y: int


class Grid(ResponseModel):
    width: int
    height: int
    values: list[float | None]


Regime = Literal["private", "ai_pool", "human_assisted"]
ActionName = Literal["move", "observe", "drill", "join_ai_pool", "choose_human"]


class Insight(ResponseModel):
    summary: str
    source: str
    acquired_round: int


class AgentSnapshot(ResponseModel):
    id: str
    label: str
    position: Position
    budget_remaining: float
    accumulated_cost: float
    activity: Literal["active", "inactive"]
    collaboration_status: Regime
    last_action: ActionName | None = None
    can_afford_drill: bool
    belief: Grid
    latest_insight: Insight | None = None
    path: list[Position]
    reason: str | None = None
    final_reward: float = 0
    final_utility: float = 0


class PoolEvent(ResponseModel):
    id: str
    evidence_id: str
    agent_id: str
    kind: Literal["observation", "human", "drill", "location", "belief"]
    observed_round: int
    shared_round: int
    position: Position | None = None
    summary: str
    confidence: float | None = None


class PoolSnapshot(ResponseModel):
    member_ids: list[str]
    eligible_member_ids: list[str]
    eligibility_round: int
    discovery_reward: float
    reward_per_member: float | None
    events: list[PoolEvent]
    belief: Grid | None = None


class EventSnapshot(ResponseModel):
    id: str
    round: int
    agent_id: str | None = None
    action: ActionName | None = None
    summary: str


class MarkerSnapshot(ResponseModel):
    id: str
    agent_id: str
    position: Position
    kind: Literal["observe", "dry", "water"]
    value: float | None = None


class Payout(ResponseModel):
    agent_id: str
    regime: Regime
    reward: float
    total_cost: float
    utility: float


class WinnerSnapshot(ResponseModel):
    agent_id: str
    position: Position
    status: Regime
    intensity: float
    recipient_ids: list[str]
    discovery_reward: float
    reward_per_recipient: float
    payouts: list[Payout]


class ProviderAgentFailure(ResponseModel):
    agent_id: str
    category: str
    http_status: int | None = None


class ProviderPauseSnapshot(ResponseModel):
    message: str
    agent_ids: list[str]
    retry_at: float | None = None
    failures: list[ProviderAgentFailure]


class ExperimentSnapshot(ResponseModel):
    experiment_id: str
    source: Literal["backend"] = "backend"
    status: Literal[
        "idle", "running", "paused", "awaiting_human", "awaiting_api", "success", "failure"
    ]
    round: int
    max_rounds: int
    config: dict[str, Any]
    agents: list[AgentSnapshot]
    pool: PoolSnapshot
    markers: list[MarkerSnapshot]
    recent_events: list[EventSnapshot]
    winner: WinnerSnapshot | None = None
    results: list[Payout] | None = None
    failure_reason: str | None = None
    provider_failure: ProviderPauseSnapshot | None = None
    ground_truth_available: bool


class GroundTruthSnapshot(ResponseModel):
    intensity: Grid
    success_threshold: float


class HumanRequestSnapshot(ResponseModel):
    id: str
    agent_id: str
    round: int
    cost: float
    prior: Grid
    grid_width: int
    grid_height: int


class HumanResponseInput(ResponseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    request_id: str
    x: int = Field(ge=0, strict=True)
    y: int = Field(ge=0, strict=True)
    note: str = Field(default="", max_length=300)


class HealthSnapshot(ResponseModel):
    status: str = "ok"
    gemini_configured: bool
    model: str


class FinalResultsSnapshot(ResponseModel):
    results: list[Payout]
    winner: WinnerSnapshot | None = None


class ReplayResponse(ResponseModel):
    rounds: list[ExperimentSnapshot]

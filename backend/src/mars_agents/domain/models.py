"""Serializable backend state and explicit, independently constructed public views.

Experiment is privileged persistence/evaluator state, NEVER an API/agent response.
Grid values are row-major: values[y * width + x]. No model stores a live RNG.
"""

from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mars_agents.config import ExperimentConfig
from mars_agents.domain.actions import ActionProposal as ActionProposal
from mars_agents.domain.actions import AgentAction as AgentAction

Probability = Annotated[float, Field(ge=0, le=1)]


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Position(DomainModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    x: int = Field(ge=0, strict=True)
    y: int = Field(ge=0, strict=True)


class Grid(DomainModel):
    width: int = Field(ge=1, strict=True)
    height: int = Field(ge=1, strict=True)
    values: list[Probability]

    @model_validator(mode="after")
    def correct_shape(self) -> Self:
        if len(self.values) != self.width * self.height:
            raise ValueError("Grid length must equal width * height")
        return self

    def at(self, x: int, y: int) -> float:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError("Coordinates are outside this grid")
        return self.values[y * self.width + x]


class HumanPrior(Grid):
    """Coarse imperfect adviser-only raster, not the true water map."""


class EnvironmentTruth(DomainModel):
    water: Grid
    surface_signal: Grid
    deposit_centers: list[Position]


class Regime(StrEnum):
    PRIVATE = "private"
    AI_POOL = "ai_pool"
    HUMAN_ASSISTED = "human_assisted"


class Evidence(DomainModel):
    id: str
    agent_id: str
    round: int = Field(ge=0)
    kind: Literal["observation", "drill", "human"]
    position: Position
    value: Probability
    success: bool | None = None
    confidence: Probability | None = None
    note: str = Field(default="", max_length=600)
    request_id: str | None = None


class ActionRecord(DomainModel):
    round: int
    proposal: ActionProposal
    cost: float
    position: Position
    budget_remaining: float
    result: str
    evidence_id: str | None = None


class AgentState(DomainModel):
    id: str
    position: Position
    starting_position: Position
    starting_budget: float
    budget_remaining: float
    accumulated_cost: float = 0
    regime: Regime = Regime.PRIVATE
    active: bool = True
    belief: Grid
    evidence: list[Evidence] = Field(default_factory=list)
    action_history: list[ActionRecord] = Field(default_factory=list)
    path: list[Position] = Field(default_factory=list)
    human_queries: int = 0
    pool_joined_round: int | None = None
    pool_eligible_from_round: int | None = None
    last_action: AgentAction | None = None
    last_reason: str = ""
    final_reward: float = 0
    final_utility: float = 0
    model_metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def observations(self) -> list[Evidence]:
        return [e for e in self.evidence if e.kind == "observation"]

    @property
    def drills(self) -> list[Evidence]:
        return [e for e in self.evidence if e.kind == "drill"]

    @property
    def human_advice(self) -> list[Evidence]:
        return [e for e in self.evidence if e.kind == "human"]


class PoolBoardEntry(DomainModel):
    id: str
    agent_id: str
    kind: Literal["join", "observation", "drill"]
    observed_round: int
    shared_round: int
    summary: str
    evidence_id: str | None = None
    position: Position | None = None
    value: Probability | None = None
    success: bool | None = None


class PoolState(DomainModel):
    member_ids: list[str] = Field(default_factory=list)
    eligible_member_ids: list[str] = Field(default_factory=list)
    eligibility_round: int = 1
    evidence: list[Evidence] = Field(default_factory=list)
    events: list[PoolBoardEntry] = Field(default_factory=list)
    belief: Grid


class ExperimentEvent(DomainModel):
    id: str
    round: int
    kind: str
    summary: str
    agent_id: str | None = None
    action: AgentAction | None = None
    cost: float | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class MapMarker(DomainModel):
    id: str
    agent_id: str
    position: Position
    round: int
    kind: Literal["observe", "dry", "water"]
    evidence_id: str


class Payout(DomainModel):
    agent_id: str
    reward: float
    total_cost: float
    utility: float


class Winner(DomainModel):
    agent_id: str
    position: Position
    regime: Regime
    intensity: Probability
    round: int
    recipient_ids: list[str]
    discovery_reward: float
    reward_per_recipient: float
    successful_agent_ids: list[str]
    payouts: list[Payout]


class Experiment(DomainModel):
    id: str
    config: ExperimentConfig
    round: int = 0
    status: Literal["running", "success", "failure"] = "running"
    agents: dict[str, AgentState]
    truth: EnvironmentTruth
    human_prior: HumanPrior
    pool: PoolState
    events: list[ExperimentEvent] = Field(default_factory=list)
    markers: list[MapMarker] = Field(default_factory=list)
    payouts: list[Payout] = Field(default_factory=list)
    winner: Winner | None = None
    terminal_reason: str | None = None
    invalid_decisions: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def experiment_id(self) -> str:
        return self.id


class HumanRequest(DomainModel):
    request_id: str
    experiment_id: str
    agent_id: str
    round: int
    cost: float
    grid_width: int
    grid_height: int
    prior: HumanPrior


class HumanResponse(DomainModel):
    request_id: str
    x: int = Field(ge=0, strict=True)
    y: int = Field(ge=0, strict=True)
    note: str = Field(default="", max_length=600)


class BeliefCandidate(DomainModel):
    position: Position
    belief: Probability
    move_cost: float


class BeliefSummary(DomainModel):
    model: str = "spatial_log_odds_heuristic_not_calibrated"
    local_belief: Probability
    coarse: Grid
    top_candidates: list[BeliefCandidate]
    visited_count: int
    recent_visited: list[Position]


class PoolView(DomainModel):
    member_ids: list[str]
    recent_evidence: list[Evidence]
    board: list[PoolBoardEntry]


class AgentView(DomainModel):
    """Allowlist for LLM input. No truth, human raster, or other private state."""

    agent_id: str
    round: int
    grid_width: int
    grid_height: int
    position: Position
    budget_remaining: float
    accumulated_cost: float
    regime: Regime
    discovery_reward: float
    action_costs: dict[str, float]
    legal_actions: list[str]
    belief_summary: BeliefSummary
    recent_observations: list[Evidence]
    drill_history: list[Evidence]
    pool_size: int
    pool_reward_per_member: float | None
    prospective_pool_reward: float
    pool: PoolView | None = None
    human_recommendations: list[Evidence] = Field(default_factory=list)
    human_queries_remaining: int
    max_rounds: int
    water_success_threshold: float
    search_context: dict[str, Any] = Field(default_factory=dict)

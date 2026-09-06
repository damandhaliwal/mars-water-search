"""Validated experimental parameters; frontend aliases are accepted and emitted."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
        allow_inf_nan=False,
    )

    grid_width: int = Field(default=50, ge=1, le=256, strict=True)
    grid_height: int = Field(default=50, ge=1, le=256, strict=True)
    number_of_agents: int = Field(default=4, ge=1, le=64, strict=True)
    number_of_water_deposits: int = Field(default=1, ge=1, le=2, strict=True)
    seed: int = Field(default=42, ge=0, le=2**63 - 1, strict=True)
    starting_budget: float = Field(default=300, ge=0)
    discovery_reward: float = Field(default=1000, ge=0)
    move_cost_per_cell: float = Field(default=1, ge=0)
    observe_cost: float = Field(default=10, ge=0)
    drill_cost: float = Field(default=100, ge=0)
    join_pool_cost: float = Field(default=0, ge=0)
    human_cost: float = Field(default=150, ge=0)
    human_quality: float = Field(default=0.5, ge=0, le=1)
    human_mode: Literal["simulated", "interactive"] = "simulated"
    treatment: Literal["free_choice", "solo_only", "ai_collab_available", "human_available"] = (
        "free_choice"
    )
    max_rounds: int = Field(default=100, ge=1, strict=True)
    max_human_queries: int = Field(default=1, ge=0, le=100, strict=True)
    water_success_threshold: float = Field(default=0.75, gt=0, le=1)
    prior_probability: float = Field(default=0.1, gt=0, lt=1)
    observation_noise: float = Field(default=0.25, gt=0, le=2)
    observation_blur_sigma: float = Field(default=2, gt=0)
    human_noise: float = Field(default=0.03, ge=0, le=1)
    human_blur_sigma: float = Field(default=2, gt=0)
    human_coarse_size: int = Field(default=8, ge=1, le=32, strict=True)
    water_radius_min: float = Field(default=0.05, gt=0, le=1)
    water_radius_max: float = Field(default=0.12, gt=0, le=1)
    belief_kernel_radius: float = Field(default=3, gt=0)
    observation_weight: float = Field(default=2.5, gt=0)
    drill_weight: float = Field(default=6, gt=0)
    human_weight: float = Field(default=5, gt=0)
    belief_summary_size: int = Field(default=5, ge=1, le=10, strict=True)
    top_candidate_count: int = Field(default=8, ge=1, le=16, strict=True)
    recent_evidence_limit: int = Field(default=12, ge=1, le=30, strict=True)

    @model_validator(mode="after")
    def consistent_world(self) -> Self:
        cells = self.grid_width * self.grid_height
        if self.number_of_agents > cells:
            raise ValueError("The grid must contain at least one cell per agent")
        if self.number_of_water_deposits > cells:
            raise ValueError("The grid must contain at least one cell per water deposit")
        if self.water_radius_min > self.water_radius_max:
            raise ValueError("water_radius_min must not exceed water_radius_max")
        return self

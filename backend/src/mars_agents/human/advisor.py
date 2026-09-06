"""Human requests reserve no money and are safe to replay before an interrupt.

Only resolve_round commits the query cost. The adviser sees a coarse imperfect
prior; the rover receives a bounded recommendation with server-derived confidence.
"""

from collections.abc import Sequence

import numpy as np
from scipy.ndimage import gaussian_filter

from mars_agents.beliefs.updater import coarse_grid
from mars_agents.config import ExperimentConfig
from mars_agents.domain.actions import ActionProposal, AgentAction, validate_action
from mars_agents.domain.models import (
    EnvironmentTruth,
    Evidence,
    Experiment,
    HumanPrior,
    HumanRequest,
    HumanResponse,
    Position,
)
from mars_agents.environment.randomness import seeded_rng
from mars_agents.environment.water import grid_from_array


def generate_human_prior(config: ExperimentConfig, truth: EnvironmentTruth) -> HumanPrior:
    water = np.asarray(truth.water.values).reshape(config.grid_height, config.grid_width)
    blurred = gaussian_filter(water, sigma=config.human_blur_sigma, mode="nearest")
    # Coarsen before adding noise; never pass the full-resolution map to the human.
    size = min(config.human_coarse_size, max(1, min(config.grid_width, config.grid_height) // 2))
    coarse = coarse_grid(grid_from_array(np.clip(blurred, 0, 1)), size)
    rng = seeded_rng(config.seed, "human_prior")
    values = (
        config.prior_probability
        + config.human_quality * (np.asarray(coarse.values) - config.prior_probability)
        + rng.normal(0, config.human_noise, len(coarse.values))
    )
    return HumanPrior(
        width=coarse.width, height=coarse.height, values=np.clip(values, 0, 1).tolist()
    )


def prepare_human_requests(
    experiment: Experiment, proposals: Sequence[ActionProposal]
) -> list[HumanRequest]:
    seen: set[str] = set()
    requests: list[HumanRequest] = []
    for proposal in sorted(proposals, key=lambda p: p.agent_id):
        if proposal.agent_id in seen:
            raise ValueError(f"More than one proposal for {proposal.agent_id}")
        seen.add(proposal.agent_id)
        cost = validate_action(experiment, proposal)
        if proposal.action == AgentAction.CHOOSE_HUMAN:
            requests.append(
                HumanRequest(
                    request_id=f"{experiment.id}:r{experiment.round + 1}:{proposal.agent_id}:human",
                    experiment_id=experiment.id,
                    agent_id=proposal.agent_id,
                    round=experiment.round + 1,
                    cost=cost,
                    grid_width=experiment.config.grid_width,
                    grid_height=experiment.config.grid_height,
                    prior=experiment.human_prior.model_copy(deep=True),
                )
            )
    return requests


def validate_human_response(request: HumanRequest, response: HumanResponse) -> float:
    """Validate the bounded reply and return confidence from the request's coarse prior."""
    if response.request_id != request.request_id:
        raise ValueError("Human response does not match this request")
    if not (0 <= response.x < request.grid_width and 0 <= response.y < request.grid_height):
        raise ValueError("Human recommendation is outside the world")
    x = response.x * request.prior.width // request.grid_width
    y = response.y * request.prior.height // request.grid_height
    return request.prior.at(x, y)


def response_evidence(request: HumanRequest, response: HumanResponse) -> Evidence:
    confidence = validate_human_response(request, response)
    return Evidence(
        id=request.request_id,
        agent_id=request.agent_id,
        round=request.round,
        kind="human",
        position=Position(x=response.x, y=response.y),
        value=confidence,
        confidence=confidence,
        note=response.note,
        request_id=request.request_id,
    )

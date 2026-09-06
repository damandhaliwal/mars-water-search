"""Sensors expose a noisy blurred signal, while drilling alone reveals local truth."""

import numpy as np

from mars_agents.domain.models import Evidence, Experiment
from mars_agents.environment.randomness import seeded_rng


def observe_at(experiment: Experiment, agent_id: str, round_number: int) -> Evidence:
    position = experiment.agents[agent_id].position
    # The cell signal is fixed: rescanning a cell replays its original reading,
    # so sitting still and re-observing can never mint fresh evidence.
    rng = seeded_rng(experiment.config.seed, "observation", position.x, position.y)
    value = experiment.truth.surface_signal.at(position.x, position.y)
    value = float(np.clip(value + rng.normal(0, experiment.config.observation_noise), 0, 1))
    return Evidence(
        id=f"{experiment.id}:r{round_number}:{agent_id}:observation",
        agent_id=agent_id,
        round=round_number,
        kind="observation",
        position=position,
        value=value,
    )


def drill_at(experiment: Experiment, agent_id: str, round_number: int) -> Evidence:
    position = experiment.agents[agent_id].position
    value = experiment.truth.water.at(position.x, position.y)
    return Evidence(
        id=f"{experiment.id}:r{round_number}:{agent_id}:drill",
        agent_id=agent_id,
        round=round_number,
        kind="drill",
        position=position,
        value=value,
        success=value >= experiment.config.water_success_threshold,
    )

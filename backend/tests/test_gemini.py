"""Opt-in real Gemini calls: uv run pytest -m gemini tests/test_gemini.py."""

import pytest

from mars_agents.agents import GeminiDecisionService, GeminiSettings
from mars_agents.beliefs.views import agent_view
from mars_agents.config import ExperimentConfig
from mars_agents.domain.actions import legal_actions, validate_action
from mars_agents.environment.world import create_experiment, resolve_round
from mars_agents.human.advisor import prepare_human_requests
from mars_agents.human.simulated import simulated_response

pytestmark = pytest.mark.gemini


def test_four_rover_gemini_episode():
    settings = GeminiSettings()
    if settings.gemini_api_key is None or not settings.gemini_api_key.get_secret_value().strip():
        pytest.skip("GEMINI_API_KEY is required for the explicitly selected live test")
    # A complete bounded episode; max_rounds is a legitimate terminal condition.
    # Three rounds cap this test at 12 successful decisions, plus configured retries.
    experiment = create_experiment(
        ExperimentConfig(
            grid_width=8,
            grid_height=8,
            number_of_agents=4,
            max_rounds=3,
            human_mode="simulated",
        ),
        "gemini-integration",
    )
    service = GeminiDecisionService(settings)
    decisions = 0
    try:
        while experiment.status == "running":
            views = {
                agent_id: agent_view(experiment, agent_id)
                for agent_id in experiment.agents
                if legal_actions(experiment, agent_id)
            }
            results = service.collect(experiment, views)
            assert results
            proposals = []
            for result in results:
                assert not result.invalid_decision, result.model_dump_json()
                assert result.proposal is not None
                assert validate_action(experiment, result.proposal) >= 0
                assert all(attempt.provider == "gemini" for attempt in result.attempts)
                proposals.append(result.proposal)
                decisions += 1
            responses = [
                simulated_response(request)
                for request in prepare_human_requests(experiment, proposals)
            ]
            experiment = resolve_round(experiment, proposals, responses)
        assert experiment.status in ("success", "failure")
        assert decisions >= 4
    finally:
        service.close()

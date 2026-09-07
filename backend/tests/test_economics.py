"""The payoff sheet uses episode values and options match live arithmetic."""

from test_domain import make, place

from mars_agents.agents.economics import (
    credits,
    render_economic_options,
    render_system_prompt,
)
from mars_agents.beliefs.views import agent_view
from mars_agents.config import ExperimentConfig


def test_system_prompt_carries_episode_values():
    config = ExperimentConfig(
        discovery_reward=2000,
        starting_budget=500,
        move_cost_per_cell=2,
        observe_cost=20,
        drill_cost=150,
        human_cost=200,
        join_pool_cost=5,
        human_quality=0.7,
        water_success_threshold=0.8,
        number_of_agents=4,
    )
    text = render_system_prompt(config)
    for expected in ("2,000", "500", "20", "150", "200", "70%", "666.67"):
        assert expected in text
    assert "JOIN_AI_POOL" in text and "CHOOSE_HUMAN" in text
    assert "approximately 70% closer to the hidden truth" in text


def test_default_config_keeps_reference_examples():
    text = render_system_prompt(ExperimentConfig())
    assert "Examples if the discovery prize is 1,000:" in text
    assert "3 pool members ->   333 each" in text
    assert "approximately 50% closer to the hidden truth" in text
    assert "remaining budget afterward = 34" in text


def test_system_prompt_omits_unavailable_regimes_by_treatment():
    solo = render_system_prompt(ExperimentConfig(treatment="solo_only"))
    assert "JOIN_AI_POOL" not in solo and "CHOOSE_HUMAN" not in solo
    assert "PRIVATE" in solo
    ai_only = render_system_prompt(ExperimentConfig(treatment="ai_collab_available"))
    assert "JOIN_AI_POOL" in ai_only and "CHOOSE_HUMAN" not in ai_only
    human_only = render_system_prompt(ExperimentConfig(treatment="human_available"))
    assert "JOIN_AI_POOL" not in human_only and "CHOOSE_HUMAN" in human_only


def test_options_match_worked_example():
    experiment = make()
    agent = experiment.agents["C"]
    agent.budget_remaining = 184
    agent.accumulated_cost = 116
    experiment.pool.member_ids = ["A", "B"]
    options = render_economic_options(experiment, "C", agent_view(experiment, "C"))
    assert "Remaining budget: 184" in options
    assert "gross reward = 1,000" in options
    assert "pool next round = A, B, C" in options
    assert "pool size = 3" in options
    assert "333.33" in options
    assert "budget afterward = 34" in options
    assert "budget afterward = 84" in options
    assert "budget afterward = 174" in options
    assert "MOVE to candidate" in options
    assert "human_prior" not in options and "surface" not in options


def test_options_follow_regime_and_legality():
    experiment = make()
    experiment.agents["A"].regime = "ai_pool"
    experiment.pool.member_ids = ["A", "B"]
    experiment.pool.eligible_member_ids = ["A", "B"]
    pooled = render_economic_options(experiment, "A", agent_view(experiment, "A"))
    assert "You are in the AI pool" in pooled
    assert "your share = 500" in pooled
    assert "join the AI pool now" not in pooled
    assert "choose human assistance now" not in pooled
    place(experiment, "C", 0, 0)
    experiment.agents["C"].budget_remaining = 5
    broke = render_economic_options(experiment, "C", agent_view(experiment, "C"))
    assert "Drill here" not in broke and "Observe here" not in broke
    assert "Remaining budget: 5" in broke


def test_credits_formatting():
    assert credits(1000) == "1,000"
    assert credits(1000 / 3) == "333.33"
    assert credits(300) == "300"
    assert credits(0.3) == "0.30"

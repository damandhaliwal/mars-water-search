"""Deterministic domain tests supply actions directly; no runtime model or API calls."""

import json
from itertools import permutations

import numpy as np
import pytest
from pydantic import ValidationError
from scipy.ndimage import label

from mars_agents.beliefs.updater import SpatialLogOddsUpdater, coarse_grid, uniform_belief
from mars_agents.beliefs.views import agent_view
from mars_agents.collaboration.pool import update_pool
from mars_agents.config import ExperimentConfig
from mars_agents.domain.actions import ActionProposal, AgentAction, legal_actions, validate_action
from mars_agents.domain.models import (
    Experiment,
    Grid,
    HumanResponse,
    Position,
    Regime,
)
from mars_agents.environment.observations import observe_at
from mars_agents.environment.world import create_experiment, resolve_round
from mars_agents.human.advisor import prepare_human_requests, validate_human_response
from mars_agents.human.simulated import simulated_response


def make(**overrides) -> Experiment:
    options = {"grid_width": 12, "grid_height": 10, "number_of_agents": 3}
    options.update(overrides)
    return create_experiment(ExperimentConfig(**options), "test")


def action(agent_id: str, kind: str, **kwargs) -> ActionProposal:
    return ActionProposal(agent_id=agent_id, action=kind, **kwargs)


def place(experiment: Experiment, agent_id: str, x: int, y: int) -> None:
    experiment.agents[agent_id].position = Position(x=x, y=y)
    experiment.agents[agent_id].path = [Position(x=x, y=y)]


def water(experiment: Experiment, x: int, y: int, value: float) -> None:
    experiment.truth.water.values[y * experiment.config.grid_width + x] = value


def spend_to(experiment: Experiment, agent_id: str, budget: float) -> None:
    agent = experiment.agents[agent_id]
    agent.budget_remaining = budget
    agent.accumulated_cost = agent.starting_budget - budget


def query(experiment: Experiment, agent_id: str = "A") -> Experiment:
    proposals = [action(agent_id, "choose_human")]
    requests = prepare_human_requests(experiment, proposals)
    return resolve_round(experiment, proposals, [simulated_response(r) for r in requests])


def test_config_accepts_snake_and_camel_emits_camel():
    config = ExperimentConfig(gridWidth=13, gridHeight=11, numberOfAgents=2, seed=19)
    assert config.grid_width == 13
    assert config.model_dump()["gridWidth"] == 13
    assert config.model_dump(by_alias=False)["number_of_agents"] == 2
    assert ExperimentConfig.model_validate_json(config.model_dump_json()) == config
    assert ExperimentConfig().move_cost_per_cell == 1
    assert ExperimentConfig().max_human_queries == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"grid_width": 0},
        {"number_of_agents": 0},
        {"number_of_water_deposits": 3},
        {"starting_budget": -1},
        {"human_cost": float("nan")},
        {"seed": -1},
        {"water_success_threshold": 0},
        {"human_quality": 1.1},
        {"water_radius_min": 0.4, "water_radius_max": 0.1},
        {"grid_width": 1, "grid_height": 1, "number_of_agents": 2},
        {"number_of_agents": True},
        {"unexpected_key": 1},
    ],
)
def test_invalid_config_rejected(kwargs):
    with pytest.raises(ValidationError):
        ExperimentConfig(**kwargs)


@pytest.mark.parametrize("count", [1, 2])
def test_world_is_seeded_bounded_coherent_and_has_qualifying_cells(count):
    first = make(number_of_water_deposits=count)
    second = make(number_of_water_deposits=count)
    assert first == second
    assert first.truth != make(seed=43, number_of_water_deposits=count).truth
    assert len(first.truth.deposit_centers) == count
    values = np.asarray(first.truth.water.values).reshape(10, 12)
    assert np.min(values) >= 0 and np.max(values) <= 1
    assert 1 <= label(values >= first.config.water_success_threshold)[1] <= count
    for position in first.truth.deposit_centers:
        assert first.truth.water.at(position.x, position.y) == 1


def test_separate_random_streams_and_no_serialized_rng():
    original = make()
    changed = make(human_noise=0.2, observation_noise=0.6)
    assert original.truth == changed.truth
    assert original.agents["A"].starting_position == changed.agents["A"].starting_position
    assert original.human_prior != changed.human_prior
    assert observe_at(original, "A", 1) == observe_at(make(human_noise=0.2), "A", 1)
    assert observe_at(original, "B", 1) == observe_at(original, "B", 1)
    # The cell signal is fixed: rescans replay the original reading.
    rescanned = observe_at(original, "A", 2)
    assert rescanned.value == observe_at(original, "A", 1).value
    assert rescanned.id != observe_at(original, "A", 1).id
    document = original.model_dump_json()
    restored = Experiment.model_validate_json(document)
    assert original == restored
    proposals = [action("A", "observe"), action("B", "join_ai_pool")]
    assert resolve_round(original, proposals) == resolve_round(restored, proposals)
    assert "Generator" not in document and "bit_generator" not in document


def test_exactly_identical_initial_beliefs_independent_objects():
    experiment = make()
    prior = uniform_belief(experiment.config)
    assert all(agent.belief == prior for agent in experiment.agents.values())
    assert experiment.pool.belief == prior
    experiment.agents["A"].belief.values[0] = 0.4
    assert experiment.agents["B"].belief == prior
    assert experiment.pool.belief == prior


def test_move_manhattan_cost_no_observation_and_immutable_transition():
    experiment = make(move_cost_per_cell=2)
    place(experiment, "A", 1, 2)
    proposal = action("A", "move", x=4, y=6)
    snapshot = experiment.model_dump_json()
    assert validate_action(experiment, proposal) == 14
    assert experiment.model_dump_json() == snapshot
    result = resolve_round(experiment, [proposal])
    assert experiment.model_dump_json() == snapshot
    agent = result.agents["A"]
    assert agent.position == Position(x=4, y=6)
    assert agent.budget_remaining == 286
    assert agent.accumulated_cost == 14
    assert agent.evidence == []
    assert agent.belief == experiment.agents["A"].belief
    assert agent.path == [Position(x=1, y=2), Position(x=4, y=6)]


@pytest.mark.parametrize("x,y", [(12, 0), (0, 10), (999, 999), (1, 2)])
def test_move_out_of_bounds_or_same_cell_rejected(x, y):
    experiment = make()
    place(experiment, "A", 1, 2)
    before = experiment.model_dump_json()
    with pytest.raises(ValueError):
        resolve_round(experiment, [action("A", "move", x=x, y=y)])
    assert experiment.model_dump_json() == before


@pytest.mark.parametrize(
    "fields",
    [
        {"action": "wait"},
        {"action": "move", "x": 1},
        {"action": "move", "x": -1, "y": 2},
        {"action": "move", "x": 1.3, "y": 2},
        {"action": "move", "x": True, "y": 2},
        {"action": "drill", "x": 1, "y": 2},
        {"action": "observe", "extra": "bad"},
    ],
)
def test_action_shape_is_strict(fields):
    with pytest.raises(ValidationError):
        ActionProposal(agent_id="A", **fields)


def test_unknown_agent_and_duplicate_proposals_rejected_atomically():
    experiment = make()
    before = experiment.model_dump_json()
    with pytest.raises(ValueError, match="Unknown"):
        legal_actions(experiment, "unknown")
    with pytest.raises(ValueError, match="More than one"):
        resolve_round(experiment, [action("A", "observe"), action("A", "drill")])
    assert experiment.model_dump_json() == before


@pytest.mark.parametrize("kind,cost", [("observe", 10), ("drill", 100), ("join_ai_pool", 0)])
def test_costs_charged_once(kind, cost):
    experiment = make()
    position = experiment.agents["A"].position
    water(experiment, position.x, position.y, 0)
    result = resolve_round(experiment, [action("A", kind)])
    agent = result.agents["A"]
    assert agent.budget_remaining == 300 - cost
    assert agent.accumulated_cost == cost
    assert len(agent.action_history) == 1
    assert agent.final_utility == -cost


def test_legal_actions_reject_unaffordable_destination_and_fixed_costs():
    experiment = make(starting_budget=1)
    place(experiment, "A", 0, 0)
    assert legal_actions(experiment, "A") == ["move", "join_ai_pool"]
    for proposal in [
        action("A", "observe"),
        action("A", "drill"),
        action("A", "choose_human"),
        action("A", "move", x=2, y=0),
    ]:
        with pytest.raises(ValueError):
            validate_action(experiment, proposal)
    assert validate_action(experiment, action("A", "move", x=1, y=0)) == 1


def test_zero_budget_private_agent_can_join_then_becomes_inactive():
    experiment = make(starting_budget=0, number_of_agents=1)
    assert experiment.agents["A"].active
    assert legal_actions(experiment, "A") == ["join_ai_pool"]
    result = resolve_round(experiment, [action("A", "join_ai_pool")])
    assert not result.agents["A"].active
    assert result.agents["A"].regime == Regime.AI_POOL
    assert result.pool.member_ids == ["A"]
    assert result.status == "failure" and result.terminal_reason == "all_agents_inactive"


def test_zero_budget_with_nonzero_join_cost_is_inactive_and_no_wait():
    experiment = make(starting_budget=0, join_pool_cost=1)
    assert experiment.status == "failure"
    assert not any(a.active for a in experiment.agents.values())
    assert legal_actions(experiment, "A") == []
    assert "wait" not in {item.value for item in AgentAction}


@pytest.mark.parametrize(
    "treatment,expected",
    [
        ("free_choice", {"join_ai_pool", "choose_human"}),
        ("solo_only", set()),
        ("ai_collab_available", {"join_ai_pool"}),
        ("human_available", {"choose_human"}),
    ],
)
def test_treatments_limit_available_regime_choices(treatment, expected):
    experiment = make(treatment=treatment)
    assert set(legal_actions(experiment, "A")) - {"move", "observe", "drill"} == expected


def test_observation_changes_only_private_owner_and_exposes_no_exact_intensity():
    experiment = make()
    result = resolve_round(experiment, [action("A", "observe")])
    evidence = result.agents["A"].evidence[0]
    assert evidence.kind == "observation" and evidence.success is None
    assert evidence.value != experiment.truth.water.at(evidence.position.x, evidence.position.y)
    assert result.agents["A"].belief != experiment.agents["A"].belief
    assert result.agents["B"].belief == experiment.agents["B"].belief
    assert result.agents["B"].evidence == []
    assert result.pool.evidence == []
    assert result.markers[0].kind == "observe"


def test_drill_definitive_only_at_local_cell_and_remains_known_after_new_scans():
    experiment = make(starting_budget=500)
    place(experiment, "A", 3, 4)
    water(experiment, 3, 4, 0.6)
    drilled = resolve_round(experiment, [action("A", "drill")])
    evidence = drilled.agents["A"].drills[0]
    assert evidence.value == 0.6 and evidence.success is False
    assert drilled.agents["A"].belief.at(3, 4) == 0
    assert sum(p == 0 for p in drilled.agents["A"].belief.values) == 1
    observed = resolve_round(drilled, [action("A", "observe")])
    assert observed.agents["A"].belief.at(3, 4) == 0
    assert observed.markers[0].kind == "dry"


def test_observation_signal_is_fixed_per_cell():
    experiment = make()
    position = experiment.agents["A"].position
    first = observe_at(experiment, "A", 1)
    rescanned = observe_at(experiment, "A", 2)
    assert rescanned.value == first.value
    assert rescanned.id != first.id
    place(experiment, "B", position.x, position.y)
    assert observe_at(experiment, "B", 9).value == first.value
    far_x = (position.x + 5) % experiment.config.grid_width
    far_y = (position.y + 5) % experiment.config.grid_height
    place(experiment, "B", far_x, far_y)
    assert observe_at(experiment, "B", 1).value != first.value


def test_rescanning_a_cell_is_not_offered_or_accepted():
    experiment = make()
    assert "observe" in legal_actions(experiment, "A")
    scanned = resolve_round(experiment, [action("A", "observe")])
    assert "observe" not in legal_actions(scanned, "A")
    assert "move" in legal_actions(scanned, "A")
    with pytest.raises(ValueError, match="unavailable"):
        validate_action(scanned, action("A", "observe"))
    with pytest.raises(ValueError, match="unavailable"):
        resolve_round(scanned, [action("A", "observe")])
    start = scanned.agents["A"].position
    fresh_x = start.x + 1 if start.x + 1 < scanned.config.grid_width else start.x - 1
    moved = resolve_round(scanned, [action("A", "move", x=fresh_x, y=start.y)])
    assert "observe" in legal_actions(moved, "A")


def test_belief_keeps_earliest_scan_when_cells_repeat():
    experiment = make()
    first = observe_at(experiment, "A", 1)
    updater = SpatialLogOddsUpdater()
    assert updater.reconstruct(
        experiment.config, [first, observe_at(experiment, "A", 2)]
    ) == updater.reconstruct(experiment.config, [first])


def test_pool_counts_a_shared_cell_once():
    experiment = make()
    position = experiment.agents["A"].position
    place(experiment, "B", position.x, position.y)
    experiment = resolve_round(experiment, [action("A", "observe"), action("B", "observe")])
    experiment = resolve_round(
        experiment, [action("A", "join_ai_pool"), action("B", "join_ai_pool")]
    )
    assert len(experiment.pool.evidence) == 2
    assert experiment.pool.belief == SpatialLogOddsUpdater().reconstruct(
        experiment.config, [experiment.pool.evidence[0]]
    )


def test_belief_reconstruction_deduplicates_and_ignores_evidence_order():
    experiment = make()
    a = observe_at(experiment, "A", 1)
    b = observe_at(experiment, "B", 1)
    updater = SpatialLogOddsUpdater()
    assert updater.reconstruct(experiment.config, [a, b]) == updater.reconstruct(
        experiment.config, [b, a, a]
    )
    changed = a.model_copy(update={"value": 1 - a.value})
    with pytest.raises(ValueError, match="Conflicting"):
        updater.reconstruct(experiment.config, [a, changed])


def test_pool_imports_history_next_round_and_automatically_unions_future_evidence():
    experiment = resolve_round(make(), [action("A", "observe"), action("B", "observe")])
    before = agent_view(experiment, "A")
    joined = resolve_round(experiment, [action("A", "join_ai_pool"), action("B", "join_ai_pool")])
    assert before.pool is None and experiment.pool.member_ids == []
    assert joined.pool.member_ids == ["A", "B"]
    assert joined.pool.eligibility_round == 3
    assert joined.pool.eligible_member_ids == ["A", "B"]
    assert joined.agents["A"].pool_eligible_from_round == 3
    assert {e.id for e in joined.pool.evidence} == {
        experiment.agents["A"].evidence[0].id,
        experiment.agents["B"].evidence[0].id,
    }
    assert joined.agents["A"].belief == joined.agents["B"].belief == joined.pool.belief
    view = agent_view(joined, "A")
    assert view.pool is not None and len(view.pool.recent_evidence) == 2
    assert view.round == 3
    assert agent_view(joined, "C").pool is None
    shared = [e for e in joined.pool.events if e.evidence_id is not None]
    assert all(e.observed_round == 1 and e.shared_round == 2 for e in shared)
    start = joined.agents["A"].position
    fresh_x = start.x + 1 if start.x + 1 < joined.config.grid_width else start.x - 1
    moved = resolve_round(joined, [action("A", "move", x=fresh_x, y=start.y)])
    assert "observe" in legal_actions(moved, "A")
    advanced = resolve_round(moved, [action("A", "observe")])
    assert len(advanced.pool.evidence) == 3
    assert advanced.agents["A"].belief == advanced.agents["B"].belief
    saved = advanced.model_dump_json()
    update_pool(advanced)
    assert advanced.model_dump_json() == saved


def test_private_late_joiner_gets_exact_union_without_double_counting():
    experiment = resolve_round(make(), [action("A", "observe"), action("B", "observe")])
    experiment = resolve_round(experiment, [action("A", "join_ai_pool")])
    before_b = agent_view(experiment, "B")
    assert before_b.pool is None
    joined = resolve_round(experiment, [action("B", "join_ai_pool")])
    expected = SpatialLogOddsUpdater().reconstruct(
        joined.config, joined.agents["A"].evidence + joined.agents["B"].evidence
    )
    assert joined.pool.belief == expected
    assert len(joined.pool.evidence) == 2


def test_pool_and_human_regimes_irreversibly_exclusive():
    human = query(make())
    assert "join_ai_pool" not in legal_actions(human, "A")
    with pytest.raises(ValueError):
        validate_action(human, action("A", "join_ai_pool"))
    joined = resolve_round(make(), [action("A", "join_ai_pool")])
    assert "choose_human" not in legal_actions(joined, "A")
    assert "join_ai_pool" not in legal_actions(joined, "A")
    with pytest.raises(ValueError):
        validate_action(joined, action("A", "choose_human"))


def test_pool_defensive_rejection_of_human_evidence():
    experiment = query(make())
    experiment.agents["A"].regime = Regime.AI_POOL
    with pytest.raises(ValueError, match="Human"):
        update_pool(experiment)


def test_human_request_preparation_idempotent_and_cost_committed_only_on_resolve():
    experiment = make(human_mode="interactive")
    proposals = [action("A", "choose_human"), action("B", "choose_human")]
    before = experiment.model_dump_json()
    first = prepare_human_requests(experiment, proposals)
    second = prepare_human_requests(experiment, proposals[::-1])
    assert first == second and len(first) == 2
    assert experiment.model_dump_json() == before
    assert all(r.cost == 150 and r.round == 1 for r in first)
    assert first[0].request_id != first[1].request_id
    with pytest.raises(ValueError, match="Human responses"):
        resolve_round(experiment, proposals, [simulated_response(first[0])])
    assert experiment.model_dump_json() == before
    responses = [simulated_response(r) for r in first]
    result = resolve_round(experiment, proposals, responses)
    replay = resolve_round(experiment, proposals, responses)
    assert result == replay
    assert experiment.model_dump_json() == before
    for agent_id in ("A", "B"):
        agent = result.agents[agent_id]
        assert agent.budget_remaining == 150 and agent.accumulated_cost == 150
        assert agent.human_queries == 1 and agent.regime == Regime.HUMAN_ASSISTED
        assert len(agent.human_advice) == 1
    assert result.pool.evidence == []
    assert result.agents["C"].evidence == []


def test_human_response_bounds_and_confidence_come_only_from_coarse_prior():
    experiment = make(human_mode="interactive")
    proposal = action("A", "choose_human")
    request = prepare_human_requests(experiment, [proposal])[0]
    response = HumanResponse(request_id=request.request_id, x=11, y=9, note="A regional estimate")
    confidence = validate_human_response(request, response)
    expected = request.prior.at(request.prior.width - 1, request.prior.height - 1)
    assert confidence == expected
    result = resolve_round(experiment, [proposal], [response])
    assert result.agents["A"].human_advice[0].confidence == expected
    with pytest.raises(ValueError, match="outside"):
        validate_human_response(request, HumanResponse(request_id=request.request_id, x=12, y=9))
    with pytest.raises(ValueError, match="match"):
        validate_human_response(request, HumanResponse(request_id="wrong", x=1, y=1))
    with pytest.raises(ValidationError):
        HumanResponse(request_id=request.request_id, x=1, y=1, confidence=1)
    with pytest.raises(ValidationError):
        HumanResponse(request_id=request.request_id, x=1.2, y=1)
    with pytest.raises(ValueError, match="Duplicate"):
        resolve_round(experiment, [proposal], [response, response])
    with pytest.raises(ValueError, match="Human responses"):
        resolve_round(experiment, [], [response])


def test_modified_request_prior_cannot_change_authoritative_response_confidence():
    experiment = make()
    proposal = action("A", "choose_human")
    request = prepare_human_requests(experiment, [proposal])[0]
    response = HumanResponse(request_id=request.request_id, x=1, y=1)
    actual = validate_human_response(request, response)
    request.prior.values = [1] * len(request.prior.values)
    result = resolve_round(experiment, [proposal], [response])
    assert result.agents["A"].human_advice[0].confidence == actual


def test_repeated_human_queries_configurable_but_do_not_duplicate_same_fixed_advice():
    once = query(make(starting_budget=600))
    assert "choose_human" not in legal_actions(once, "A")
    repeated = query(make(starting_budget=600, max_human_queries=2))
    assert "choose_human" in legal_actions(repeated, "A")
    twice = query(repeated)
    assert twice.agents["A"].human_queries == 2
    assert twice.agents["A"].accumulated_cost == 300
    assert twice.agents["A"].belief == repeated.agents["A"].belief
    assert "choose_human" not in legal_actions(twice, "A")
    assert "join_ai_pool" not in legal_actions(twice, "A")
    assert "choose_human" not in legal_actions(make(max_human_queries=0), "A")


def test_coarse_human_prior_is_imperfect_and_recommendation_informs_search_across_seeds():
    recommended = []
    averages = []
    for seed in range(20):
        experiment = create_experiment(ExperimentConfig(seed=seed), "quality")
        request = prepare_human_requests(experiment, [action("A", "choose_human")])[0]
        assert request.prior.width < experiment.config.grid_width
        assert request.prior.height < experiment.config.grid_height
        assert len(request.prior.values) <= 64
        reply = simulated_response(request)
        confidence = validate_human_response(request, reply)
        intensity = experiment.truth.water.at(reply.x, reply.y)
        assert confidence < 1
        recommended.append(intensity)
        averages.append(np.mean(experiment.truth.water.values))
    # Controlled generator sanity check, not a claim of probability calibration.
    assert np.mean(recommended) > np.mean(averages) + 0.3
    assert any(value < 0.75 for value in recommended)


def test_coarse_grid_mapping_covers_uneven_dimensions_and_simulated_regions():
    grid = Grid(width=7, height=5, values=[float(i % 2) for i in range(35)])
    coarse = coarse_grid(grid, 3)
    for cy in range(3):
        for cx in range(3):
            values = [
                grid.at(x, y)
                for y in range(5)
                for x in range(7)
                if x * 3 // 7 == cx and y * 3 // 5 == cy
            ]
            assert coarse.at(cx, cy) == pytest.approx(np.mean(values))
    experiment = make(grid_width=7, grid_height=5)
    request = prepare_human_requests(experiment, [action("A", "choose_human")])[0]
    response = simulated_response(request)
    assert validate_human_response(request, response) == max(request.prior.values)


def test_private_winner_receives_single_prize_and_everyone_pays_own_costs():
    experiment = make()
    place(experiment, "A", 1, 1)
    water(experiment, 1, 1, 0.8)
    result = resolve_round(experiment, [action("A", "drill"), action("B", "observe")])
    assert result.status == "success" and result.winner is not None
    assert result.winner.recipient_ids == ["A"]
    assert result.agents["A"].final_reward == 1000
    assert result.agents["A"].final_utility == 900
    assert result.agents["B"].final_reward == 0
    assert result.agents["B"].final_utility == -10
    assert sum(p.reward for p in result.payouts) == 1000
    assert not any(a.active for a in result.agents.values())
    with pytest.raises(ValueError, match="terminal"):
        resolve_round(result, [])


def test_human_assisted_winner_keeps_full_prize():
    experiment = query(make())
    position = experiment.agents["A"].position
    water(experiment, position.x, position.y, 0.8)
    result = resolve_round(experiment, [action("A", "drill")])
    assert result.winner is not None and result.winner.regime == Regime.HUMAN_ASSISTED
    assert result.winner.recipient_ids == ["A"]
    assert result.agents["A"].final_reward == 1000
    assert result.agents["A"].final_utility == 750


def test_pool_winner_splits_equally_with_inactive_member_but_not_current_joiner():
    experiment = resolve_round(make(), [action("A", "observe")])
    spend_to(experiment, "A", 0)
    experiment = resolve_round(
        experiment, [action("A", "join_ai_pool"), action("B", "join_ai_pool")]
    )
    assert not experiment.agents["A"].active
    position = experiment.agents["B"].position
    water(experiment, position.x, position.y, 0.9)
    result = resolve_round(experiment, [action("B", "drill"), action("C", "join_ai_pool")])
    assert result.winner is not None
    assert result.winner.recipient_ids == ["A", "B"]
    assert result.pool.member_ids == ["A", "B", "C"]
    assert result.pool.eligible_member_ids == ["A", "B"]
    assert result.pool.eligibility_round == result.round
    assert result.agents["C"].pool_eligible_from_round == result.round + 1
    assert result.agents["A"].final_reward == 500
    assert result.agents["B"].final_reward == 500
    assert result.agents["C"].final_reward == 0
    assert result.agents["A"].final_utility == 200
    assert result.agents["B"].final_utility == 400


@pytest.mark.parametrize("equal", [False, True])
def test_simultaneous_success_highest_intensity_then_seeded_order_independent_tie(equal):
    experiment = make()
    for index, agent_id in enumerate(("A", "B", "C")):
        place(experiment, agent_id, index, 0)
        water(experiment, index, 0, 0.9 if equal or agent_id == "B" else 0.8)
    proposals = [action(agent_id, "drill") for agent_id in ("A", "B", "C")]
    resolved = [resolve_round(experiment, list(order)) for order in permutations(proposals)]
    assert all(result == resolved[0] for result in resolved)
    result = resolved[0]
    assert result.winner is not None
    assert result.winner.successful_agent_ids == ["A", "B", "C"]
    assert len([m for m in result.markers if m.kind == "water"]) == 3
    assert sum(a.accumulated_cost for a in result.agents.values()) == 300
    assert sum(a.final_reward for a in result.agents.values()) == 1000
    if not equal:
        assert result.winner.agent_id == "B"


def test_seeded_tie_does_not_always_favor_first_agent():
    winners = set()
    for seed in range(12):
        experiment = make(seed=seed, number_of_agents=2)
        for index, agent_id in enumerate(("A", "B")):
            place(experiment, agent_id, index, 0)
            water(experiment, index, 0, 0.9)
        result = resolve_round(experiment, [action("A", "drill"), action("B", "drill")])
        assert result.winner is not None
        winners.add(result.winner.agent_id)
    assert winners == {"A", "B"}


def test_simultaneous_pool_and_private_success_awards_only_highest_winner_regime():
    experiment = resolve_round(make(), [action("A", "join_ai_pool"), action("B", "join_ai_pool")])
    place(experiment, "A", 0, 0)
    place(experiment, "C", 1, 0)
    water(experiment, 0, 0, 0.8)
    water(experiment, 1, 0, 0.9)
    result = resolve_round(experiment, [action("A", "drill"), action("C", "drill")])
    assert result.winner is not None and result.winner.recipient_ids == ["C"]
    assert result.agents["A"].final_reward == result.agents["B"].final_reward == 0


def test_success_at_threshold_and_final_round_takes_precedence_over_limits():
    experiment = make(max_rounds=1, starting_budget=100)
    position = experiment.agents["A"].position
    water(experiment, position.x, position.y, 0.75)
    result = resolve_round(experiment, [action("A", "drill")])
    assert result.status == "success" and result.terminal_reason == "water_discovered"


def test_all_agents_cannot_drill_ends_experiment_while_active():
    experiment = make()
    for agent in experiment.agents.values():
        agent.budget_remaining = 50
        agent.accumulated_cost = agent.starting_budget - 50
    assert all(a.active for a in experiment.agents.values())
    start = experiment.agents["A"].position
    fresh_x = start.x + 1 if start.x + 1 < experiment.config.grid_width else start.x - 1
    result = resolve_round(experiment, [action("A", "move", x=fresh_x, y=start.y)])
    assert result.status == "failure"
    assert result.terminal_reason == "all_agents_cannot_drill"
    assert result.pool.eligibility_round == result.round


def test_one_affordable_drill_keeps_experiment_running():
    experiment = make()
    for agent_id, agent in experiment.agents.items():
        if agent_id != "A":
            agent.budget_remaining = 50
            agent.accumulated_cost = agent.starting_budget - 50
    result = resolve_round(experiment, [action("A", "observe")])
    assert result.status == "running"
    assert result.terminal_reason is None


def test_invalid_decisions_lose_round_without_action_or_spending():
    experiment = make(max_rounds=2)
    result = resolve_round(
        experiment,
        [],
        invalid_decisions=[
            {
                "agent_id": "A",
                "error": "Provider timed out",
                "attempts": 3,
            }
        ],
    )
    assert result.round == 1 and result.status == "running"
    assert len(result.invalid_decisions) == 3
    assert all(a.budget_remaining == 300 for a in result.agents.values())
    assert all(a.action_history == [] for a in result.agents.values())
    terminal = resolve_round(result, [])
    assert terminal.status == "failure" and terminal.terminal_reason == "max_rounds"
    assert all(p.utility == 0 for p in terminal.payouts)


def test_single_cell_has_no_move_but_affordable_sensor_actions():
    experiment = make(grid_width=1, grid_height=1, number_of_agents=1)
    assert "move" not in legal_actions(experiment, "A")
    assert "observe" in legal_actions(experiment, "A")


def test_private_view_unchanged_if_hidden_world_or_other_private_data_changes():
    experiment = resolve_round(make(), [action("B", "observe")])
    before = agent_view(experiment, "A").model_dump_json()
    altered = experiment.model_copy(deep=True)
    altered.truth.water.values = [1 - x for x in altered.truth.water.values]
    altered.truth.surface_signal.values = [1] * len(altered.truth.surface_signal.values)
    altered.human_prior.values = [1] * len(altered.human_prior.values)
    altered.agents["B"].evidence[0].value = 0.987654321
    altered.agents["B"].belief.values[0] = 0.123456789
    altered.agents["B"].last_reason = "PRIVATE_SENTINEL"
    assert agent_view(altered, "A").model_dump_json() == before
    parsed = json.loads(before)
    assert "truth" not in parsed and "human_prior" not in parsed and "seed" not in parsed
    assert "PRIVATE_SENTINEL" not in before and "0.987654321" not in before
    assert parsed["pool"] is None
    assert parsed["human_recommendations"] == []


def test_pool_view_excludes_human_and_outsider_private_history():
    experiment = query(make(), "C")
    experiment = resolve_round(experiment, [action("A", "join_ai_pool"), action("B", "observe")])
    view = agent_view(experiment, "A")
    assert view.pool is not None
    assert view.human_recommendations == []
    assert view.pool.recent_evidence == []
    text = view.model_dump_json()
    assert experiment.agents["C"].human_advice[0].id not in text
    assert experiment.agents["B"].observations[0].id not in text
    assert "human_prior" not in text and "water" not in type(view).model_fields


def test_human_assisted_view_sees_only_own_bounded_advice_not_prior():
    experiment = query(make(), "C")
    view = agent_view(experiment, "C")
    assert len(view.human_recommendations) == 1
    assert view.pool is None
    assert "human_prior" not in view.model_dump_json()
    assert view.human_recommendations[0].confidence is not None
    assert not hasattr(view.human_recommendations[0], "prior")


def test_view_is_compact_and_detached_from_authoritative_state():
    experiment = create_experiment(ExperimentConfig(), "compact")
    view = agent_view(experiment, "A")
    assert len(view.belief_summary.coarse.values) == 25
    assert len(view.belief_summary.top_candidates) == 8
    assert len(view.model_dump_json()) < 9000
    view.belief_summary.coarse.values[0] = 1
    assert experiment.agents["A"].belief.values[0] == 0.1
    joined = resolve_round(experiment, [action("A", "join_ai_pool"), action("B", "observe")])
    pool_view = agent_view(joined, "A")
    assert pool_view.pool is not None
    pool_view.pool.member_ids.append("fake")
    assert joined.pool.member_ids == ["A"]


def test_view_snapshot_remains_start_of_round_after_proposals_and_resolution():
    experiment = make()
    views = {name: agent_view(experiment, name) for name in experiment.agents}
    snapshots = {name: view.model_dump_json() for name, view in views.items()}
    proposals = [action("A", "observe"), action("B", "join_ai_pool")]
    for proposal in proposals:
        validate_action(experiment, proposal)
    resolve_round(experiment, proposals)
    assert {name: view.model_dump_json() for name, view in views.items()} == snapshots
    assert all(agent_view(experiment, name) == view for name, view in views.items())


def test_terminal_failure_eligibility_also_excludes_final_round_joiner():
    experiment = resolve_round(make(max_rounds=2), [action("A", "join_ai_pool")])
    result = resolve_round(experiment, [action("B", "join_ai_pool")])
    assert result.status == "failure"
    assert result.pool.member_ids == ["A", "B"]
    assert result.pool.eligibility_round == 2
    assert result.pool.eligible_member_ids == ["A"]


@pytest.mark.parametrize("noise, human_more_accurate", [(0.25, True), (0.05, False)])
def test_human_and_sensor_accuracy_depend_on_sensor_noise(noise, human_more_accurate):
    human_errors = []
    sensor_errors = []
    for seed in range(20):
        experiment = create_experiment(
            ExperimentConfig(seed=seed, observation_noise=noise), "quality"
        )
        request = prepare_human_requests(experiment, [action("A", "choose_human")])[0]
        # Fixed locations assess the information source, with no rover policy.
        for index, (x, y) in enumerate(
            [(1, 1), (7, 13), (15, 25), (22, 8), (28, 35), (35, 20), (40, 44), (49, 49)]
        ):
            place(experiment, "A", x, y)
            signal = observe_at(experiment, "A", index + 1).value
            prior_value = validate_human_response(
                request, HumanResponse(request_id=request.request_id, x=x, y=y)
            )
            truth = experiment.truth.water.at(x, y)
            human_errors.append((prior_value - truth) ** 2)
            sensor_errors.append((signal - truth) ** 2)
    # These are intensity-score errors on the configured synthetic distribution,
    # not calibrated water-discovery probabilities or live strategic performance.
    if human_more_accurate:
        assert np.mean(human_errors) < np.mean(sensor_errors) * 0.5
    else:
        # Cleaner local readings can beat a coarse regional estimate. Human
        # advice offers coverage, not guaranteed pointwise accuracy superiority.
        assert np.mean(sensor_errors) < np.mean(human_errors)


def test_human_quality_controls_distance_toward_coarse_blurred_field():
    low = make(human_quality=0, human_noise=0)
    half = make(human_quality=0.5, human_noise=0)
    high = make(human_quality=1, human_noise=0)
    assert low.human_prior.values == [0.1] * len(low.human_prior.values)
    assert np.allclose(
        half.human_prior.values,
        (np.asarray(low.human_prior.values) + np.asarray(high.human_prior.values)) / 2,
    )


def test_decimal_movement_cost_is_affordable_at_exact_budget_boundary():
    experiment = make(starting_budget=0.3, move_cost_per_cell=0.1, drill_cost=0)
    place(experiment, "A", 0, 0)
    proposal = action("A", "move", x=3, y=0)
    assert validate_action(experiment, proposal) == 0.3
    result = resolve_round(experiment, [proposal])
    assert result.agents["A"].budget_remaining == 0
    assert result.agents["A"].accumulated_cost == 0.3
    assert legal_actions(result, "A") == ["drill", "join_ai_pool"]


def test_repeated_fractional_charges_use_all_affordable_budget_without_negative_residue():
    experiment = make(
        starting_budget=0.3,
        human_cost=0.1,
        max_human_queries=3,
        number_of_agents=1,
        drill_cost=0,
    )
    for remaining in (0.2, 0.1, 0.0):
        experiment = query(experiment)
        assert experiment.agents["A"].budget_remaining == remaining
    assert experiment.agents["A"].accumulated_cost == 0.3
    assert experiment.agents["A"].final_utility == -0.3
    assert experiment.status == "running"

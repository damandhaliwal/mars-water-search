"""Search context preserves measured leads without breaching information regimes."""
from test_domain import make, place

from mars_agents.agents.prompts import render_system_prompt
from mars_agents.beliefs.views import agent_view
from mars_agents.domain.models import Evidence, Position, Regime
from mars_agents.environment.observations import observe_at


def measurement(i, x, y, value, kind="observation", agent="A"):
    return Evidence(id=str(i), round=i, agent_id=agent, kind=kind,
                    position=Position(x=x, y=y), value=value,
                    success=False if kind == "drill" else None)


def test_old_strong_dry_lead_retains_exact_value_and_affordable_local_probes():
    exp = make(recent_evidence_limit=1, move_cost_per_cell=2, drill_cost=100)
    place(exp, "A", 4, 4)
    exp.agents["A"].evidence = [
        measurement(1, 4, 4, .70, "drill"),
        measurement(2, 5, 4, .60),
        measurement(3, 10, 8, .1),
    ]
    view = agent_view(exp, "A")
    assert len(view.recent_observations) == 1
    lead = view.search_context["strongest_leads"][0]
    assert lead["value"] == .70 and lead["success"] is False
    assert lead["exact_drill_here"]["value"] == .70
    assert lead["nearby_measurements"][0]["value"] == .60
    probes = lead["untested_probes"]
    assert all(p["position"] != {"x": 5, "y": 4} for p in probes)
    assert probes[0]["move_cost"] == 2
    assert probes[0]["budget_after_move_observe_drill"] == 188
    exp.agents["A"].budget_remaining = 105
    assert agent_view(exp, "A").search_context["strongest_leads"][0][
        "untested_probes"][0]["budget_after_move_observe_drill"] == -7


def test_search_context_ignores_truth_and_private_peers_but_uses_pool_evidence():
    exp = make()
    exp.agents["B"].evidence = [measurement(1, 3, 3, .9, agent="B")]
    before = agent_view(exp, "A")
    exp.truth.water.values = [1.] * len(exp.truth.water.values)
    exp.truth.surface_signal.values = [0.] * len(exp.truth.surface_signal.values)
    exp.human_prior.values = [1.] * len(exp.human_prior.values)
    assert agent_view(exp, "A") == before
    assert before.search_context["strongest_leads"] == []
    assert before.search_context["pool_members"] == []
    exp.agents["A"].regime = Regime.AI_POOL
    exp.pool.member_ids = ["A", "B"]
    exp.pool.evidence = exp.agents["B"].evidence * 2
    pooled = agent_view(exp, "A").search_context
    assert len(pooled["strongest_leads"]) == 1
    assert [m["id"] for m in pooled["pool_members"]] == ["A", "B"]
    assert pooled["strongest_leads"][0]["value"] == .9


def test_zero_drill_contradiction_and_boundary_probes_are_visible():
    exp = make()
    exp.agents["A"].evidence = [measurement(1, 0, 0, .8), measurement(2, 0, 0, 0, "drill")]
    lead = agent_view(exp, "A").search_context["strongest_leads"][0]
    assert lead["exact_drill_here"]["value"] == 0
    assert all(p["position"]["x"] >= 0 and p["position"]["y"] >= 0
               for p in lead["untested_probes"])
    prompt = render_system_prompt(exp.config)
    assert prompt.startswith("CAUTIOUS SIGNAL SEARCH")
    assert "gradient ASCENT" in prompt
    assert "FINAL UTILITY" in prompt


def test_noise_magnitude_is_absent_from_all_model_inputs():
    from mars_agents.agents.economics import render_economic_options

    exp = make()
    exp.agents["A"].evidence = [measurement(1, 3, 3, .4)]
    view = agent_view(exp, "A")
    prompt = render_system_prompt(exp.config)
    options = render_economic_options(exp, "A", view)
    # Hold evidence fixed: changing only hidden sensor parameters cannot change
    # anything sent to Gemini, including the system sheet and economic options.
    exp.config.observation_noise = .83
    exp.config.observation_blur_sigma = 4
    assert agent_view(exp, "A") == view
    assert render_system_prompt(exp.config) == prompt
    assert render_economic_options(exp, "A", agent_view(exp, "A")) == options
    assert "observation_noise" not in view.model_dump_json()
    assert "noise magnitude and individual noise draws are UNKNOWN" in prompt


def test_default_noise_reduces_the_seed_42_false_signal_without_changing_water():
    exp = make(seed=42, grid_width=50, grid_height=50)
    assert exp.config.observation_noise == .05
    place(exp, "C", 0, 12)
    reading = observe_at(exp, "C", 1).value
    assert abs(reading - .09411376127259755) < 1e-12
    exp.config.observation_noise = .25
    assert abs(observe_at(exp, "C", 1).value - 5 * reading) < 1e-12


def test_prompt_distinguishes_three_unproductive_points_from_a_productive_gradient():
    prompt = render_system_prompt(make().config)
    assert "THREE DISTINCT grid points" in prompt
    assert "Movement alone is not a sample" in prompt
    assert "Do not restart the count on each small move" in prompt
    assert "preserve the drilling reserve" in prompt
    assert "Do not abandon a productive gradient" in prompt

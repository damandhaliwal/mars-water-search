"""Markdown reports record play history without privileged world data."""

import json

from test_domain import action, make, place, water

from mars_agents.experiments.logging import ExperimentLogger
from mars_agents.experiments.markdown import render_report


def build(tmp_path):
    experiment = make(number_of_agents=2)
    place(experiment, "B", 0, 0)
    water(experiment, 5, 5, 0.987654321)
    logger = ExperimentLogger(tmp_path)
    logger.initialize(experiment.id, json.loads(experiment.model_dump_json()))
    from mars_agents.environment.world import resolve_round

    first = resolve_round(experiment, [action("A", "observe"), action("B", "move", x=1, y=0)])
    logger.round(experiment.id, first.round, _record(first))
    second = resolve_round(first, [action("A", "drill")])
    logger.round(experiment.id, second.round, _record(second))
    return experiment.id, logger


def _record(experiment):

    return {
        "round": experiment.round,
        "agent_views": {},
        "decisions": [],
        "invalid_decisions": [dict(item) for item in experiment.invalid_decisions],
        "human_requests": [],
        "human_responses": [],
        "events": [event.model_dump(mode="json") for event in experiment.events],
        "agents": {},
        "pool": experiment.pool.model_dump(mode="json"),
    }


def test_report_records_history_without_truth(tmp_path):
    experiment_id, _ = build(tmp_path)
    text = render_report(tmp_path / experiment_id)
    assert f"Episode `{experiment_id}`" in text
    assert "Agent A (observe)" in text
    assert "Agent B (move)" in text
    assert "Agent A (drill)" in text
    assert "## Outcome" in text
    for forbidden in ("deposit_centers", "human_prior", "surface_signal", "0.987654321"):
        assert forbidden not in text


def test_summary_refreshes_report_md(tmp_path):
    from mars_agents.config import ExperimentConfig
    from mars_agents.environment.world import create_experiment
    from mars_agents.orchestration.graph import episode_summary

    experiment = create_experiment(ExperimentConfig(number_of_agents=1), "md-test")
    logger = ExperimentLogger(tmp_path)
    logger.initialize(experiment.id, json.loads(experiment.model_dump_json()))
    logger.summary(experiment.id, episode_summary(experiment))
    report = tmp_path / experiment.id / "report.md"
    assert report.exists()
    assert "Status: running" in report.read_text()

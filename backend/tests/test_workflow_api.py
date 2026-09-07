"""Domain-proposal workflow tests and stubbed HTTP-response integration tests.

No replacement policy or model is available to the running application.
"""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from openai.types.chat import ChatCompletion

from mars_agents.agents.model_factory import GeminiSettings
from mars_agents.api.main import create_app
from mars_agents.beliefs.views import agent_view
from mars_agents.config import ExperimentConfig
from mars_agents.domain.actions import ActionProposal
from mars_agents.domain.models import HumanResponse
from mars_agents.experiments.batch import run_batch
from mars_agents.experiments.service import ExperimentBusyError, ExperimentService


def settings() -> GeminiSettings:
    return GeminiSettings(
        _env_file=None, gemini_api_key="unit-test-not-a-real-key", gemini_request_interval=0,
        gemini_max_concurrency=1,
    )


def stage(service, exp, proposals):
    """Inject already-supplied domain proposals at the graph's collection boundary."""
    service.graph.update_state(
        service.thread(exp.id),
        {
            "experiment": exp.model_dump(mode="json"),
            "views": {aid: agent_view(exp, aid).model_dump(mode="json") for aid in exp.agents},
            "proposals": [p.model_dump(mode="json") for p in proposals],
            "decisions": [],
            "invalid_decisions": [],
            "human_requests": [],
            "human_responses": [],
        },
        as_node="collect_agent_decisions",
    )


def proposal(agent_id, action):
    return ActionProposal(
        agent_id=agent_id, action=action, reason="A supplied domain-test proposal."
    )


def observation_response(*args, **kwargs):
    """Only the HTTP client response is stubbed; actual smolagents dispatch runs."""
    return ChatCompletion.model_validate(
        {
            "id": "network-unit-response",
            "object": "chat.completion",
            "created": 0,
            "model": "gemini-3.8-flash",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "choice-1",
                                "type": "function",
                                "function": {
                                    "name": "observe",
                                    "arguments": json.dumps(
                                        {"reason": "Local information is worth its cost."}
                                    ),
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        }
    )


NETWORK = "openai.resources.chat.completions.Completions.create"


def test_graph_pool_and_simulated_human(tmp_path):
    svc = ExperimentService(tmp_path, settings())
    exp = svc.create(ExperimentConfig(number_of_agents=2))
    stage(svc, exp, [proposal("A", "choose_human"), proposal("B", "join_ai_pool")])
    result = svc.step(exp.id)
    assert result.round == 1
    assert result.agents["A"].budget_remaining == 150
    assert result.agents["A"].human_advice
    assert result.pool.member_ids == ["B"]
    assert all(e.kind != "human" for e in result.pool.evidence)
    assert svc.pending(exp.id) == []
    payload = json.loads((tmp_path / exp.id / "rounds/00001.json").read_text())
    assert "agent_views" in payload and "human_responses" in payload
    assert svc.state(exp.id).config["configurable"]["thread_id"] == exp.id
    svc.close()


def test_two_human_interrupts_survive_restart_and_charge_once(tmp_path):
    svc = ExperimentService(tmp_path, settings())
    exp = svc.create(ExperimentConfig(number_of_agents=2, human_mode="interactive"))
    stage(svc, exp, [proposal("A", "choose_human"), proposal("B", "choose_human")])
    svc.step(exp.id)
    first = svc.pending(exp.id)[0]
    assert first.agent_id == "A"
    assert svc.get(exp.id).round == 0
    assert svc.get(exp.id).agents["A"].budget_remaining == 300
    svc.respond(exp.id, HumanResponse(request_id=first.request_id, x=10, y=10))
    second = svc.pending(exp.id)[0]
    assert second.agent_id == "B"
    svc.close()
    svc = ExperimentService(tmp_path, settings())
    assert svc.pending(exp.id)[0].request_id == second.request_id
    result = svc.respond(exp.id, HumanResponse(request_id=second.request_id, x=20, y=20))
    assert result.round == 1
    assert all(a.budget_remaining == 150 and a.human_queries == 1 for a in result.agents.values())
    assert not svc.pending(exp.id)
    with pytest.raises(ValueError, match="not pending"):
        svc.respond(exp.id, HumanResponse(request_id=second.request_id, x=20, y=20))
    assert svc.get(exp.id).agents["B"].budget_remaining == 150
    assert len((tmp_path / exp.id / "events.jsonl").read_text().splitlines()) == 1
    svc.close()


def test_overlapping_mutation_rejected(tmp_path):
    svc = ExperimentService(tmp_path, settings())
    exp = svc.create(ExperimentConfig())
    with svc.locked(exp.id), pytest.raises(ExperimentBusyError):
        svc.step(exp.id)
    svc.close()


def test_api_creation_missing_key_validation_and_no_truth(tmp_path):
    app = create_app(tmp_path, GeminiSettings(gemini_api_key=None, _env_file=None))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/api/health").json()["geminiConfigured"] is False
        created = client.post("/api/experiments", json={"seed": 17}).json()
        assert created["status"] == "idle" and len(created["agents"]) == 4
        assert "truth" not in json.dumps(created).lower().replace("groundtruthavailable", "")
        assert "human_prior" not in json.dumps(created)
        assert created["agents"][0]["belief"] == created["agents"][1]["belief"]
        eid = created["experimentId"]
        response = client.post(f"/api/experiments/{eid}/step")
        assert response.status_code == 503 and "GEMINI_API_KEY" in response.json()["detail"]
        assert created["groundTruthAvailable"] is True
        assert client.post(f"/api/experiments/{eid}/reveal-ground-truth").status_code == 200
        interactive = client.post("/api/experiments", json={"humanMode": "interactive"}).json()
        assert interactive["groundTruthAvailable"] is False
        assert client.post(
            f"/api/experiments/{interactive['experimentId']}/reveal-ground-truth"
        ).status_code == 403
        assert client.post("/api/experiments", json={"numberOfWaterDeposits": 3}).status_code == 422
        reset = client.post(f"/api/experiments/{eid}/reset", json={"numberOfAgents": 2}).json()
        assert len(reset["agents"]) == 2 and reset["experimentId"] != eid
        assert client.get("/api/experiments/unknown").status_code == 404
        assert client.get(f"/api/experiments/{eid}/results").status_code == 409


def test_four_real_tool_agents_full_api_episode_with_stubbed_network(tmp_path):
    app = create_app(tmp_path, settings())
    with TestClient(app, base_url="http://127.0.0.1") as client:
        state = client.post("/api/experiments", json={"maxRounds": 1}).json()
        eid = state["experimentId"]
        with patch(NETWORK, side_effect=observation_response) as network:
            response = client.post(f"/api/experiments/{eid}/step")
        assert response.status_code == 200, response.text
        final = response.json()
        assert network.call_count == 4
        assert final["status"] == "failure"
        assert all(a["budgetRemaining"] == 290 for a in final["agents"])
        assert all(p["utility"] == -10 for p in final["results"])
        assert all("water" not in a["belief"] for a in final["agents"])
        truth = client.post(f"/api/experiments/{eid}/reveal-ground-truth").json()
        assert len(truth["intensity"]["values"]) == 2500
        assert len(client.get(f"/api/experiments/{eid}/results").json()["results"]) == 4
        assert (tmp_path / eid / "episode_summary.csv").exists()
        assert "unit-test-not-a-real-key" not in (tmp_path / eid / "config.json").read_text()


def test_api_interactive_response_validation(tmp_path):
    app = create_app(tmp_path, settings())
    with TestClient(app, base_url="http://127.0.0.1") as client:
        exp = app.state.experiments.create(
            ExperimentConfig(number_of_agents=1, human_mode="interactive")
        )
        stage(app.state.experiments, exp, [proposal("A", "choose_human")])
        paused = client.post(f"/api/experiments/{exp.id}/step").json()
        assert paused["status"] == "awaiting_human"
        request = client.get(f"/api/experiments/{exp.id}/human-requests").json()[0]
        assert request["prior"]["width"] < 50
        assert "truth" not in json.dumps(request)
        invalid = client.post(
            f"/api/experiments/{exp.id}/human-responses",
            json={"requestId": request["id"], "x": 99, "y": 1},
        )
        assert invalid.status_code == 422
        result = client.post(
            f"/api/experiments/{exp.id}/human-responses",
            json={"requestId": request["id"], "x": 12, "y": 8},
        ).json()
        assert result["status"] == "paused" and result["round"] == 1
        assert result["agents"][0]["collaborationStatus"] == "human_assisted"


def test_batch_artifacts_with_network_boundary_stub(tmp_path):
    with patch(NETWORK, side_effect=observation_response) as network:
        rows = run_batch(
            ExperimentConfig(max_rounds=1, number_of_agents=2), 2, tmp_path, settings()
        )
    assert network.call_count == 4
    assert [row["seed"] for row in rows] == [42, 43]
    for filename in ["episode_summary.csv", "events.jsonl", "config.json"]:
        assert (tmp_path / filename).stat().st_size > 0
    assert len((tmp_path / "events.jsonl").read_text().splitlines()) == 2


def test_missing_key_batch_does_not_create_fake_results(tmp_path):
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        run_batch(
            ExperimentConfig(), 1, tmp_path, GeminiSettings(gemini_api_key=None, _env_file=None)
        )
    assert list(tmp_path.iterdir()) == []


def test_recover_terminal_checkpoint_finishes_logs_without_model_key(tmp_path):
    from mars_agents.environment.world import resolve_round

    svc = ExperimentService(tmp_path, GeminiSettings(gemini_api_key=None, _env_file=None))
    exp = svc.create(ExperimentConfig(number_of_agents=1, max_rounds=1))
    stage(svc, exp, [proposal("A", "observe")])
    result = resolve_round(exp, [proposal("A", "observe")])
    svc.graph.update_state(
        svc.thread(exp.id),
        {"experiment": result.model_dump(mode="json")},
        as_node="resolve_actions_beliefs_pool_rewards",
    )
    assert not (tmp_path / exp.id / "summary.json").exists()
    svc.close()
    svc = ExperimentService(tmp_path, GeminiSettings(gemini_api_key=None, _env_file=None))
    recovered = svc.step(exp.id)
    assert recovered.status == "failure" and recovered.round == 1
    assert (tmp_path / exp.id / "summary.json").exists()
    assert (tmp_path / exp.id / "events.jsonl").exists()
    assert svc.state(exp.id).next == ()
    svc.close()


def provider_error(status=429, retry_after="60"):
    import httpx2
    from openai import APIStatusError

    return APIStatusError(
        "Sensitive provider error must never appear in logs: unit-test-not-a-real-key",
        response=httpx2.Response(
            status,
            request=httpx2.Request("POST", "https://generativelanguage.googleapis.com"),
            headers={"Retry-After": retry_after},
        ),
        body={"error": {"code": status}},
    )


def test_replay_serves_every_recorded_round_without_model_calls(tmp_path):
    app = create_app(tmp_path, settings())
    with TestClient(app, base_url="http://127.0.0.1") as client:
        eid = client.post(
            "/api/experiments", json={"numberOfAgents": 2, "maxRounds": 5}
        ).json()["experimentId"]
        with patch(NETWORK, side_effect=observation_response) as network:
            client.post(f"/api/experiments/{eid}/step")
            resolved = client.post(f"/api/experiments/{eid}/step").json()
        assert resolved["round"] == 2
        calls = network.call_count
        history = app.state.experiments.replay(eid)
        assert [exp.round for exp in history] == [0, 1, 2]
        payload = client.get(f"/api/experiments/{eid}/replay").json()
        assert [snapshot["round"] for snapshot in payload["rounds"]] == [0, 1, 2]
        assert all(
            snapshot["experimentId"] == eid for snapshot in payload["rounds"]
        )
        assert payload["rounds"][-1]["agents"] == resolved["agents"]
        # Replaying performs no model requests and leaves the live run alone.
        assert network.call_count == calls
        assert client.get(f"/api/experiments/{eid}").json()["round"] == 2
        assert client.get("/api/experiments/0" * 1 + "f" * 31 + "/replay").status_code == 404


def test_api_outage_preserves_round_decisions_and_resume_after_restart(tmp_path, monkeypatch):
    import time

    app = create_app(tmp_path, settings())
    with TestClient(app, base_url="http://127.0.0.1") as client:
        initial = client.post(
            "/api/experiments", json={"numberOfAgents": 2, "maxRounds": 1}
        ).json()
        eid = initial["experimentId"]
        with patch(NETWORK, side_effect=[observation_response(), provider_error()]) as network:
            paused = client.post(f"/api/experiments/{eid}/step").json()
        assert network.call_count == 2
        assert paused["status"] == "awaiting_api" and paused["round"] == 0
        assert paused["agents"] == initial["agents"]
        assert paused["recentEvents"] == initial["recentEvents"]
        assert paused["providerFailure"]["agentIds"] == ["B"]
        assert paused["providerFailure"]["failures"] == [
            {"agentId": "B", "category": "rate_limit", "httpStatus": 429}
        ]
        assert "HTTP 429" in paused["providerFailure"]["message"]
        assert "unit-test-not-a-real-key" not in json.dumps(paused)
        assert client.get(f"/api/experiments/{eid}").json() == paused
        assert client.get(f"/api/experiments/{eid}/human-requests").json() == []
        assert client.get(f"/api/experiments/{eid}/results").status_code == 409
        with patch(NETWORK) as network:
            assert client.post(f"/api/experiments/{eid}/step").json() == paused
        network.assert_not_called()
        assert not (tmp_path / eid / "rounds/00001.json").exists()
        attempts = (tmp_path / eid / "decisions/00001.json").read_text()
        assert "429" in attempts and "unit-test-not-a-real-key" not in attempts
        assert not app.state.experiments.get(eid).invalid_decisions

    # SQLite retains both the accepted proposal and outage across process restart.
    future = time.time() + 120
    monkeypatch.setattr(time, "time", lambda: future)
    with TestClient(create_app(tmp_path, settings()), base_url="http://127.0.0.1") as client:
        assert client.get(f"/api/experiments/{eid}").json()["status"] == "awaiting_api"
        with patch(NETWORK, side_effect=observation_response) as network:
            resolved = client.post(f"/api/experiments/{eid}/step").json()
        assert network.call_count == 1  # A's accepted decision is never requested again.
        content = network.call_args.kwargs["messages"][-1]["content"]
        if isinstance(content, list):
            content = "".join(item.get("text", "") for item in content)
        view = json.loads(content.split("Start-of-round authorized view:\n", 1)[1])
        assert view["agent_id"] == "B" and view["round"] == 1
        assert resolved["round"] == 1 and resolved["status"] == "failure"
        assert "providerFailure" not in resolved
        assert all(a["budgetRemaining"] == 290 for a in resolved["agents"])
        assert all(len(a["path"]) == 1 for a in resolved["agents"])
        payload = json.loads((tmp_path / eid / "rounds/00001.json").read_text())
        assert [len(d["attempts"]) for d in payload["decisions"]] == [1, 2]
        assert [a["attempt"] for a in payload["decisions"][1]["attempts"]] == [1, 2]
        assert payload["invalid_decisions"] == []
        assert len((tmp_path / eid / "events.jsonl").read_text().splitlines()) == 1
        with patch(NETWORK) as network:
            assert client.post(f"/api/experiments/{eid}/step").json() == resolved
        network.assert_not_called()


def test_provider_pause_precedes_human_interrupt_and_charges_only_once(tmp_path, monkeypatch):
    import time

    svc = ExperimentService(tmp_path, settings())
    exp = svc.create(ExperimentConfig(number_of_agents=2, human_mode="interactive"))
    human = observation_response()
    human.choices[0].message.tool_calls[0].function.name = "choose_human"
    with patch(NETWORK, side_effect=[human, provider_error(503)]):
        assert svc.step(exp.id).round == 0
    assert svc.provider_pause(exp.id)
    assert svc.pending(exp.id) == []
    assert all(a.budget_remaining == 300 for a in svc.get(exp.id).agents.values())
    future = time.time() + 120
    monkeypatch.setattr(time, "time", lambda: future)
    with patch(NETWORK, side_effect=observation_response) as network:
        assert svc.step(exp.id).round == 0
    assert network.call_count == 1 and svc.provider_pause(exp.id) is None
    request = svc.pending(exp.id)[0]
    assert request.agent_id == "A"
    assert all(a.budget_remaining == 300 for a in svc.get(exp.id).agents.values())
    result = svc.respond(exp.id, HumanResponse(request_id=request.request_id, x=10, y=10))
    assert result.round == 1
    assert result.agents["A"].budget_remaining == 150
    assert result.agents["A"].human_queries == 1
    assert result.agents["B"].budget_remaining == 290
    assert result.invalid_decisions == []
    svc.close()


def test_invalid_model_choice_still_loses_turn_without_provider_pause(tmp_path):
    svc = ExperimentService(tmp_path, settings())
    exp = svc.create(ExperimentConfig(number_of_agents=1, max_rounds=1))
    invalid = observation_response()
    invalid.choices[0].message.tool_calls = []
    with patch(NETWORK, return_value=invalid) as network:
        result = svc.step(exp.id)
    assert network.call_count == 3
    assert result.round == 1 and result.status == "failure"
    assert result.agents["A"].budget_remaining == 300
    assert len(result.invalid_decisions) == 1
    assert svc.provider_pause(exp.id) is None
    svc.close()


def test_batch_stops_at_api_outage_without_spinning_or_fake_results(tmp_path):
    with patch(NETWORK, side_effect=provider_error()) as network:
        with pytest.raises(RuntimeError, match="Batch paused.*rate_limit"):
            run_batch(ExperimentConfig(number_of_agents=2), 2, tmp_path, settings())
    assert network.call_count == 1
    assert not (tmp_path / "episode_summary.csv").exists()
    assert not list(tmp_path.glob("*/rounds/*.json"))
    files = list(tmp_path.glob("*/decisions/00001.json"))
    assert len(files) == 1
    assert len(json.loads(files[0].read_text())["decisions"]) == 2

"""Exercise real smolagents/OpenAI code, replacing only HTTP network responses."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import httpx2 as httpx  # Network transport of the pinned OpenAI SDK.
import pytest
from pydantic import SecretStr, ValidationError
from smolagents import OpenAIModel, ToolCallingAgent

from mars_agents.agents import GeminiConfigurationError, GeminiDecisionService, GeminiSettings
from mars_agents.agents.model_factory import GEMINI_ENDPOINT, ROOT_ENV
from mars_agents.agents.tools import ActionCollector, InvalidChoice
from mars_agents.beliefs.views import agent_view
from mars_agents.config import ExperimentConfig
from mars_agents.domain.actions import validate_action
from mars_agents.domain.models import Evidence, Regime
from mars_agents.environment.world import create_experiment

TEST_KEY = "test-gemini-secret-never-log"
HIDDEN_TEXT = "hidden-reasoning-must-never-be-retained"


def completion(tool="observe", arguments=None, *, content=HIDDEN_TEXT, calls=None, usage=True):
    if calls is None:
        calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": tool,
                    "arguments": json.dumps(arguments or {"reason": "Acquire local evidence."}),
                },
            }
        ]
    return {
        "id": "network-test-completion",
        "object": "chat.completion",
        "created": 1,
        "model": "gemini-3.8-flash",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content, "tool_calls": calls},
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 123, "completion_tokens": 17, "total_tokens": 140}
        if usage
        else None,
    }


@pytest.fixture
def experiment():
    return create_experiment(
        ExperimentConfig(grid_width=8, grid_height=8, number_of_agents=4), "agent-unit-test"
    )


@pytest.fixture
def settings():
    return GeminiSettings(
        _env_file=None,
        gemini_api_key=SecretStr(TEST_KEY),
        gemini_model="gemini-3.8-flash",
        gemini_temperature=0,
        gemini_max_concurrency=4,
        gemini_request_interval=0,
        gemini_timeout=45,
        gemini_retries=2,
    )


@pytest.fixture
def network(monkeypatch):
    """Intercept every sync HTTP call, never introduce a runtime substitute model."""
    requests = []
    lock = threading.Lock()
    control = {"respond": lambda request, body: httpx.Response(200, json=completion())}

    def send(client, request, **kwargs):
        assert str(request.url) == GEMINI_ENDPOINT + "chat/completions"
        body = json.loads(request.content)
        with lock:
            requests.append(body)
        response = control["respond"](request, body)
        response.request = request
        return response

    monkeypatch.setattr(httpx.Client, "send", send)
    return requests, control


def one_view(experiment, agent_id="A"):
    return {agent_id: agent_view(experiment, agent_id)}


def request_view(body):
    text = body["messages"][-1]["content"]
    if isinstance(text, list):
        text = "".join(item.get("text", "") for item in text)
    return json.loads(
        text.split("Start-of-round authorized view:\n", 1)[1].split("\nCorrection:", 1)[0]
    )


def test_real_framework_one_generation_per_rover_and_no_mutation(experiment, settings, network):
    requests, _ = network
    service = GeminiDecisionService(settings)
    before = experiment.model_dump_json()
    views = {agent_id: agent_view(experiment, agent_id) for agent_id in experiment.agents}
    results = service.collect(experiment, views)
    assert len(results) == len(requests) == 4
    assert all(result.proposal.action == "observe" for result in results)
    assert all(not result.invalid_decision for result in results)
    assert experiment.model_dump_json() == before
    assert all(isinstance(agent, ToolCallingAgent) for agent in service._agents.values())
    assert all(isinstance(agent.model, OpenAIModel) for agent in service._agents.values())
    for body in requests:
        assert body["model"] == "gemini-3.8-flash"
        assert body["temperature"] == 0
        assert body["tool_choice"] == "required"
        assert {tool["function"]["name"] for tool in body["tools"]} == {
            "move",
            "observe",
            "drill",
            "join_ai_pool",
            "choose_human",
        }
        assert "final_answer" not in json.dumps(body["tools"])
    for result in results:
        assert len(result.attempts) == 1
        assert result.attempts[0].input_tokens == 123
        assert result.attempts[0].output_tokens == 17
        assert result.attempts[0].latency_ms >= 0
        assert HIDDEN_TEXT not in result.model_dump_json()
    for agent in service._agents.values():
        assert agent.memory.steps == [] and agent.state == {} and agent.tools == {}
        assert agent.model.client.max_retries == 0
        assert agent.model.client.timeout == 45
    service.close()


def test_context_is_reset_and_rover_instances_retained(experiment, settings, network):
    requests, _ = network
    position = experiment.agents["A"].position
    neighbor = {"x": (position.x + 1) % 8, "y": position.y}
    experiment.agents["A"].evidence.append(
        Evidence(
            id="e-private",
            agent_id="A",
            round=0,
            kind="observation",
            position=neighbor,
            value=0.4,
            note="old-visible-evidence",
        )
    )
    service = GeminiDecisionService(settings)
    service.collect(experiment, one_view(experiment))
    instance = service._agents[(experiment.id, "A")]
    experiment.round = 1
    experiment.agents["A"].evidence.clear()
    service.collect(experiment, one_view(experiment))
    assert instance is service._agents[(experiment.id, "A")]
    assert "old-visible-evidence" in json.dumps(requests[0])
    assert "old-visible-evidence" not in json.dumps(requests[1])
    assert HIDDEN_TEXT not in json.dumps(requests)
    assert request_view(requests[1])["round"] == 2
    assert len(requests[0]["messages"]) == len(requests[1]["messages"]) == 2
    service.close()


@pytest.mark.parametrize(
    "regime,missing",
    [
        (Regime.AI_POOL, {"join_ai_pool", "choose_human"}),
        (Regime.HUMAN_ASSISTED, {"join_ai_pool", "choose_human"}),
    ],
)
def test_only_legal_regime_tools(experiment, settings, network, regime, missing):
    requests, _ = network
    experiment.agents["A"].regime = regime
    if regime == Regime.AI_POOL:
        experiment.pool.member_ids = ["A"]
    experiment.agents["A"].human_queries = 1
    service = GeminiDecisionService(settings)
    result = service.collect(experiment, one_view(experiment))[0]
    assert result.proposal is not None
    assert not ({tool["function"]["name"] for tool in requests[0]["tools"]} & missing)
    service.close()


def test_zero_budget_can_join_and_inactive_pool_makes_no_request(experiment, settings, network):
    requests, control = network
    experiment.agents["A"].budget_remaining = 0
    control["respond"] = lambda request, body: httpx.Response(200, json=completion("join_ai_pool"))
    service = GeminiDecisionService(settings)
    result = service.collect(experiment, one_view(experiment))[0]
    assert result.proposal.action == "join_ai_pool"
    assert [tool["function"]["name"] for tool in requests[0]["tools"]] == ["join_ai_pool"]
    experiment.agents["A"].regime = Regime.AI_POOL
    experiment.pool.member_ids = ["A"]
    result = service.collect(experiment, one_view(experiment))[0]
    assert result.proposal is None and result.attempts == [] and not result.invalid_decision
    assert len(requests) == 1
    service.close()


@pytest.mark.parametrize(
    "response",
    [
        completion(calls=[]),
        completion("final_answer", {"answer": "drill"}),
        completion("unknown_private_state_reader"),
        completion(
            calls=[
                {
                    "id": "same",
                    "type": "function",
                    "function": {"name": "observe", "arguments": '{"reason":"First."}'},
                },
                {
                    "id": "same",
                    "type": "function",
                    "function": {"name": "drill", "arguments": '{"reason":"Second."}'},
                },
            ]
        ),
        completion(
            calls=[
                {
                    "id": "bad",
                    "type": "function",
                    "function": {"name": "observe", "arguments": "not-json"},
                }
            ]
        ),
        completion("observe", {"reason": "Short.", "secret_thinking": HIDDEN_TEXT}),
        completion("observe", {"reason": ""}),
        completion("observe", {"reason": "x" * 321}),
        completion("move", {"x": True, "y": 1, "reason": "Wrong type."}),
        completion("move", {"x": "1", "y": 1, "reason": "Wrong type."}),
        completion("move", {"x": 999, "y": 999, "reason": "Out of bounds."}),
    ],
)
def test_invalid_outputs_retry_without_fallback(
    experiment, settings, network, response, capsys, caplog
):
    requests, control = network
    control["respond"] = lambda request, body: httpx.Response(200, json=deepcopy(response))
    service = GeminiDecisionService(settings)
    before = experiment.model_dump_json()
    result = service.collect(experiment, one_view(experiment))[0]
    assert result.invalid_decision and result.proposal is None
    assert len(result.attempts) == len(requests) == 3
    assert experiment.model_dump_json() == before
    assert "Correction:" in json.dumps(requests[1])
    assert all(len(body["messages"]) == 2 for body in requests)
    output = result.model_dump_json() + capsys.readouterr().out + caplog.text
    assert HIDDEN_TEXT not in output and TEST_KEY not in output
    assert HIDDEN_TEXT not in json.dumps(requests)
    service.close()


def test_illegal_then_valid_is_exactly_two_requests(experiment, settings, network):
    requests, control = network
    responses = iter(
        [completion("move", {"x": 999, "y": 999, "reason": "Too far."}), completion("observe")]
    )
    control["respond"] = lambda request, body: httpx.Response(200, json=next(responses))
    service = GeminiDecisionService(settings)
    result = service.collect(experiment, one_view(experiment))[0]
    assert result.proposal.action == "observe"
    assert len(requests) == len(result.attempts) == 2
    assert not result.invalid_decision
    service.close()


def test_movement_validation_and_collector_lock(experiment):
    collector = ActionCollector(
        "A", frozenset({"OBSERVE", "MOVE"}), lambda proposal: validate_action(experiment, proposal)
    )
    position = experiment.agents["A"].position
    with pytest.raises(ValueError):
        collector.accept("MOVE", x=position.x, y=position.y, reason="No movement.")
    assert collector.proposal is None
    with ThreadPoolExecutor(2) as executor:
        futures = [
            executor.submit(collector.accept, "OBSERVE", reason="Collect evidence.")
            for _ in range(2)
        ]
    assert sum(future.exception() is None for future in futures) == 1
    assert sum(isinstance(future.exception(), InvalidChoice) for future in futures) == 1


def test_api_transient_pauses_without_consuming_retries(experiment, settings, network, caplog):
    requests, control = network
    control["respond"] = lambda request, body: httpx.Response(
        429, json={"error": {"message": TEST_KEY + HIDDEN_TEXT, "type": "rate_limit_error"}}
    )
    service = GeminiDecisionService(settings)
    result = service.collect(experiment, one_view(experiment))[0]
    assert result.proposal is None and not result.invalid_decision
    assert result.provider_failure is not None
    assert result.provider_failure.category == "rate_limit"
    assert result.provider_failure.http_status == 429
    assert result.provider_failure.retry_at is not None
    assert len(requests) == len(result.attempts) == 1
    assert result.attempts[0].error_code == "api_transient"
    assert TEST_KEY not in result.model_dump_json() + caplog.text
    service.close()


def test_timeout_pauses_for_manual_retry(experiment, settings, network):
    requests, control = network

    def timeout(request, body):
        raise httpx.ReadTimeout(TEST_KEY + HIDDEN_TEXT, request=request)

    control["respond"] = timeout
    service = GeminiDecisionService(settings)
    result = service.collect(experiment, one_view(experiment))[0]
    assert result.proposal is None and not result.invalid_decision
    assert result.provider_failure is not None
    assert result.provider_failure.category == "timeout"
    assert len(requests) == len(result.attempts) == 1
    assert result.attempts[0].error_code == "api_connection_or_timeout"
    assert TEST_KEY not in result.model_dump_json()
    service.close()


def test_permanent_api_error_pauses_without_exposure(experiment, settings, network, caplog):
    requests, control = network
    control["respond"] = lambda request, body: httpx.Response(
        401, json={"error": {"message": TEST_KEY + HIDDEN_TEXT, "type": "authentication_error"}}
    )
    service = GeminiDecisionService(settings)
    result = service.collect(experiment, one_view(experiment))[0]
    assert result.proposal is None and not result.invalid_decision
    assert result.provider_failure is not None
    assert result.provider_failure.category == "api_rejected"
    assert result.provider_failure.http_status == 401
    assert len(requests) == len(result.attempts) == 1
    assert result.attempts[0].error_code == "api_rejected"
    assert TEST_KEY not in result.model_dump_json() + caplog.text
    assert HIDDEN_TEXT not in result.model_dump_json() + caplog.text
    service.close()


def test_optional_usage_and_reason_secret_redaction(experiment, settings, network):
    _, control = network
    control["respond"] = lambda request, body: httpx.Response(
        200, json=completion(arguments={"reason": "Observe " + TEST_KEY}, usage=False)
    )
    service = GeminiDecisionService(settings)
    result = service.collect(experiment, one_view(experiment))[0]
    assert result.proposal is not None
    assert result.attempts[0].input_tokens is None
    assert TEST_KEY not in result.model_dump_json()
    service.close()


def test_bounded_concurrent_requests_share_start_round(experiment, settings, network):
    requests, control = network
    settings = settings.model_copy(update={"gemini_max_concurrency": 2})
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    counts = {"active": 0, "max": 0}

    def respond(request, body):
        with lock:
            counts["active"] += 1
            counts["max"] = max(counts["max"], counts["active"])
        barrier.wait(timeout=5)
        with lock:
            counts["active"] -= 1
        return httpx.Response(200, json=completion())

    control["respond"] = respond
    service = GeminiDecisionService(settings)
    views = {agent_id: agent_view(experiment, agent_id) for agent_id in experiment.agents}
    results = service.collect(experiment, views)
    assert all(result.proposal is not None for result in results)
    assert counts["max"] == 2
    assert {request_view(body)["round"] for body in requests} == {1}
    assert {request_view(body)["budget_remaining"] for body in requests} == {300}
    service.close()


def test_only_allowlisted_private_view_reaches_network(experiment, settings, network):
    requests, _ = network
    experiment.metadata["hidden"] = "privileged-sentinel"
    experiment.agents["B"].evidence.append(
        Evidence(
            id="other-private-evidence",
            agent_id="B",
            round=0,
            kind="human",
            position=experiment.agents["B"].position,
            value=0.9,
            note="other-rover-secret",
        )
    )
    service = GeminiDecisionService(settings)
    service.collect(experiment, one_view(experiment))
    payload = json.dumps(requests)
    assert "privileged-sentinel" not in payload and "other-rover-secret" not in payload
    view = request_view(requests[0])
    assert "truth" not in view and "human_prior" not in view and "agents" not in view
    assert view["pool"] is None and view["human_recommendations"] == []
    assert len(view["belief_summary"]["coarse"]["values"]) <= 100
    service.close()


def test_mismatched_view_is_rejected_before_network(experiment, settings, network):
    requests, _ = network
    service = GeminiDecisionService(settings)
    with pytest.raises(ValueError, match="identity"):
        service.collect(experiment, {"B": agent_view(experiment, "A")})
    assert requests == []
    service.close()


def test_missing_key_allows_service_creation_but_rejects_collection(experiment, network):
    settings = GeminiSettings(_env_file=None, gemini_api_key=None)
    service = GeminiDecisionService(settings)
    with pytest.raises(GeminiConfigurationError, match="GEMINI_API_KEY is required"):
        service.ensure_configured()
    with pytest.raises(GeminiConfigurationError):
        service.collect(experiment, one_view(experiment))
    assert network[0] == []


@pytest.mark.parametrize("model", ["gpt-4o", "gemini-3.8-pro", "mock", "provider/gemini-flash"])
def test_only_flash_configuration(model):
    with pytest.raises(ValidationError, match="Gemini Flash"):
        GeminiSettings(_env_file=None, gemini_model=model)


def test_environment_configuration_and_root_env(monkeypatch, tmp_path):
    for var in (
        "GEMINI_TEMPERATURE",
        "GEMINI_TIMEOUT",
        "GEMINI_RETRIES",
        "GEMINI_REQUEST_INTERVAL",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", TEST_KEY)
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("GEMINI_MAX_CONCURRENCY", "2")
    env = tmp_path / ".env"
    env.write_text("GEMINI_TEMPERATURE=0.1\nGEMINI_TIMEOUT=12\nGEMINI_RETRIES=1\n")
    settings = GeminiSettings(_env_file=env)
    assert settings.gemini_model == "gemini-2.5-flash"
    assert settings.gemini_max_concurrency == 2
    assert settings.gemini_timeout == 12 and settings.gemini_retries == 1
    assert settings.gemini_temperature == 0.1
    assert TEST_KEY not in repr(settings) + settings.model_dump_json()
    assert ROOT_ENV.name == ".env" and (ROOT_ENV.parent / "package.json").exists()


@pytest.mark.parametrize("action", ["move", "observe", "drill", "join_ai_pool", "choose_human"])
def test_all_tools_return_domain_action_enum_without_execution(
    experiment, settings, network, action
):
    from mars_agents.domain.actions import AgentAction

    requests, control = network
    position = experiment.agents["A"].position
    arguments = {"reason": "Highest expected individual utility."}
    if action == "move":
        arguments.update(x=(position.x + 1) % experiment.config.grid_width, y=position.y)
    control["respond"] = lambda request, body: httpx.Response(
        200, json=completion(action, arguments)
    )
    service = GeminiDecisionService(settings)
    before = experiment.model_dump_json()
    result = service.collect(experiment, one_view(experiment))[0]
    assert result.proposal is not None
    assert isinstance(result.proposal.action, AgentAction)
    assert result.proposal.action.value == action
    assert validate_action(experiment, result.proposal) >= 0
    assert len(requests) == 1
    assert experiment.model_dump_json() == before
    service.close()


def test_stale_view_rejected_before_any_request(experiment, settings, network):
    requests, _ = network
    views = one_view(experiment)
    experiment.round += 1
    service = GeminiDecisionService(settings)
    with pytest.raises(ValueError, match="current round snapshot"):
        service.collect(experiment, views)
    assert requests == []
    service.close()


def test_distinct_parallel_calls_are_rejected_atomically(experiment, settings, network):
    requests, control = network
    first = completion("observe")["choices"][0]["message"]["tool_calls"][0]
    second = completion("drill")["choices"][0]["message"]["tool_calls"][0]
    second["id"] = "call_2"
    control["respond"] = lambda request, body: httpx.Response(
        200, json=completion(calls=[first, second])
    )
    service = GeminiDecisionService(settings)
    result = service.collect(experiment, one_view(experiment))[0]
    assert result.invalid_decision and result.proposal is None
    assert len(requests) == 3
    assert all(attempt.tool_name is None and attempt.tool_args == {} for attempt in result.attempts)
    service.close()

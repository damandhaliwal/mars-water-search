"""Synchronous concurrent decisions from a single detached start-of-round snapshot."""

import json
import math
import re
import time
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from email.utils import parsedate_to_datetime
from threading import BoundedSemaphore, Lock
from typing import Any, Literal

from openai import APIConnectionError, APIStatusError, APITimeoutError
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from smolagents import Tool, ToolCallingAgent
from smolagents.agents import EMPTY_PROMPT_TEMPLATES, ActionOutput
from smolagents.memory import ActionStep, SystemPromptStep, TaskStep
from smolagents.monitoring import LogLevel, Timing

from mars_agents.beliefs.views import agent_view
from mars_agents.domain.actions import ActionProposal, legal_actions, validate_action
from mars_agents.domain.models import AgentView, Experiment

from .economics import render_economic_options
from .model_factory import GeminiSettings, create_model
from .prompts import SYSTEM_PROMPT, render_system_prompt
from .tools import ActionCollector, InvalidChoice, MoveArguments, ReasonArguments, action_tools

FailureCategory = Literal[
    "rate_limit",
    "quota_exceeded",
    "service_unavailable",
    "timeout",
    "connection_error",
    "api_rejected",
]


class ProviderFailure(BaseModel):
    """Safe provider metadata; a missing deadline requires an explicit retry."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    category: FailureCategory
    http_status: int | None = None
    retry_at: float | None = None


class _ProviderBlocked(Exception):
    """Admission was blocked by a real failure elsewhere in this service."""

    def __init__(self, failure: ProviderFailure):
        super().__init__(failure.category)
        self.failure = failure


def _retry_after_deadline(value: str | None, now: float) -> float | None:
    if value is None or len(value) > 128:
        return None
    value = value.strip()
    try:
        if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
            deadline = now + float(value)
        else:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                return None
            deadline = date.timestamp()
        return max(now, deadline) if math.isfinite(deadline) else None
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _quota_exceeded(body: object) -> bool:
    # RESOURCE_EXHAUSTED and generic 429s also mean temporary rate limits.
    # Never classify using free-text messages or copy a provider body into output.
    quota_codes = {
        "QUOTA_EXCEEDED", "INSUFFICIENT_QUOTA", "DAILY_LIMIT_EXCEEDED",
        "BILLING_HARD_LIMIT_REACHED",
    }
    if not isinstance(body, dict):
        return False
    error = body.get("error", body)
    if not isinstance(error, dict):
        return False
    reasons = [error.get("code"), error.get("reason")]
    details = error.get("details")
    if isinstance(details, list):
        reasons.extend(
            detail.get("reason") for detail in details
            if isinstance(detail, dict)
            and detail.get("@type") == "type.googleapis.com/google.rpc.ErrorInfo"
        )
    return any(isinstance(code, str) and code.upper() in quota_codes for code in reasons)


def _classify_provider_failure(
    error: APIConnectionError | APIStatusError, now: float
) -> ProviderFailure:
    status = error.status_code if isinstance(error, APIStatusError) else None
    category: FailureCategory
    if isinstance(error, APITimeoutError):
        category = "timeout"
    elif isinstance(error, APIConnectionError):
        category = "connection_error"
    elif _quota_exceeded(error.body):
        category = "quota_exceeded"
    elif status == 429:
        category = "rate_limit"
    elif status == 408:
        category = "timeout"
    elif status is not None and status >= 500:
        category = "service_unavailable"
    else:
        category = "api_rejected"
    deadline = None
    if isinstance(error, APIStatusError) and category != "api_rejected":
        deadline = _retry_after_deadline(error.response.headers.get("retry-after"), now)
    if deadline is None:
        if category == "rate_limit":
            deadline = now + 60
        elif category in {"service_unavailable", "timeout", "connection_error"}:
            deadline = now + 5
    return ProviderFailure(category=category, http_status=status, retry_at=deadline)


class DecisionAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    attempt: int
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    error_code: str | None = None
    http_status: int | None = None
    failure_category: FailureCategory | None = None
    retry_at: float | None = None
    model: str
    provider: str = "gemini"


class DecisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    agent_id: str
    proposal: ActionProposal | None = None
    attempts: list[DecisionAttempt] = Field(default_factory=list)
    invalid_decision: bool = False
    provider_failure: ProviderFailure | None = None


class _SingleActionAgent(ToolCallingAgent):
    """Use smolagents' tool dispatch without its multi-step/final-answer loop.

    In 1.26.0, run(max_steps=1) still calls provide_final_answer. The public step
    entrypoint does not. Its stream hook is guarded here BEFORE tool dispatch;
    stock code accepts parallel calls and also parses free text into tool calls.
    """

    def __init__(self, settings: GeminiSettings):
        prompts = deepcopy(EMPTY_PROMPT_TEMPLATES)
        prompts["system_prompt"] = SYSTEM_PROMPT
        super().__init__(
            tools=[],
            model=create_model(settings),
            prompt_templates=prompts,
            max_steps=1,
            planning_interval=None,
            max_tool_threads=1,
            verbosity_level=LogLevel.OFF,
        )
        self.tools: dict[str, Tool] = {}  # Remove smolagents' automatically inserted final_answer.
        self.task: str | None = None
        self.safe_tool_name: str | None = None
        self.safe_tool_args: dict[str, Any] = {}
        self._secret = settings.gemini_api_key

    def reset_round(self, prompt: str, collector: ActionCollector, system: str) -> None:
        self.clear_round()
        self.tools = {tool.name: tool for tool in action_tools(collector)}
        self.memory.system_prompt = SystemPromptStep(system_prompt=system)
        self.memory.steps.append(TaskStep(task=prompt))
        self.task = prompt

    def clear_round(self) -> None:
        self.model.before_request = None
        self.memory.reset()
        self.monitor.reset()
        self.state.clear()
        self.tools = {}
        self.task = None
        self.safe_tool_name = None
        self.safe_tool_args = {}

    def _step_stream(self, memory_step: ActionStep) -> Generator:
        message = self.model.generate(
            self.write_memory_to_messages(), tools_to_call_from=self.tools_and_managed_agents
        )
        memory_step.token_usage = message.token_usage
        if not message.tool_calls:
            raise InvalidChoice(
                "No tool call was returned. Return exactly one legal function call."
            )
        if len(message.tool_calls) != 1:
            raise InvalidChoice(
                "Multiple tool calls are invalid. Return exactly one function call."
            )
        call = message.tool_calls[0]
        if call.function.name not in self.tools:
            raise InvalidChoice("That tool is unavailable. Choose one of the supplied tools.")
        self.safe_tool_name = call.function.name
        arguments = call.function.arguments
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except (ValueError, TypeError):
                raise InvalidChoice(
                    "Malformed arguments. Use the tool's exact JSON schema."
                ) from None
        if not isinstance(arguments, dict):
            raise InvalidChoice("Tool arguments must be a JSON object matching its schema.")
        schema = MoveArguments if call.function.name == "move" else ReasonArguments
        try:
            parsed = schema.model_validate(arguments)
        except ValidationError:
            raise InvalidChoice(
                "Malformed arguments. Supply only declared fields, integer coordinates for move, "
                "and a nonempty decision reason of at most 320 characters."
            ) from None
        safe_args = parsed.model_dump()
        if self._secret is not None:
            safe_args["reason"] = safe_args["reason"].replace(
                self._secret.get_secret_value(), "[redacted]"
            )
        self.safe_tool_args = safe_args
        call.function.arguments = safe_args
        yield from self.process_tool_calls(message, memory_step)
        yield ActionOutput(output=None, is_final_answer=False)


class GeminiDecisionService:
    def __init__(self, settings: GeminiSettings):
        self.settings = settings
        self._agents: dict[tuple[str, str], _SingleActionAgent] = {}
        self._agent_locks: dict[tuple[str, str], Lock] = {}
        self._registry_lock = Lock()
        self._requests = BoundedSemaphore(settings.gemini_max_concurrency)
        self._request_lock = Lock()
        self._next_request_at = 0.0
        self._cooldown_failure: ProviderFailure | None = None
        self._failure_version = 0

    def _wait_for_request(self, version: int) -> None:
        while True:
            with self._request_lock:
                failure = self._cooldown_failure
                if failure is not None and (
                    version < self._failure_version
                    or (failure.retry_at is not None and time.time() < failure.retry_at)
                ):
                    raise _ProviderBlocked(failure)
                now = time.monotonic()
                delay = self._next_request_at - now
                if delay <= 0:
                    self._next_request_at = now + self.settings.gemini_request_interval
                    return
            # Pacing alone never yields a provider failure. Recheck for an outage
            # after every short wait, without sleeping through a cooldown.
            time.sleep(min(delay, 1.0))

    def _record_provider_failure(self, failure: ProviderFailure) -> None:
        with self._request_lock:
            self._failure_version += 1
            previous = self._cooldown_failure
            # An in-flight request must not shorten an already-known cooldown.
            if previous is not None and previous.retry_at is not None and (
                previous.retry_at > time.time()
                and (failure.retry_at is None or previous.retry_at > failure.retry_at)
            ):
                return
            self._cooldown_failure = failure

    def ensure_configured(self) -> None:
        self.settings.ensure_configured()

    def collect(self, experiment: Experiment, views: dict[str, AgentView]) -> list[DecisionResult]:
        """Return all decisions together without mutating experiment or views.

        Parent owns its experiment lock and resolves only after this call returns.
        Empty legal-action lists yield no attempt and are not provider failures.
        """
        self.ensure_configured()
        snapshot = experiment.model_copy(deep=True)
        jobs = []
        for agent_id, view in views.items():
            try:
                safe_view = AgentView.model_validate(view.model_dump(mode="json"))
            except ValidationError:
                raise ValueError("Agent view does not satisfy the authorized schema") from None
            if safe_view.agent_id != agent_id or agent_id not in snapshot.agents:
                raise ValueError("Agent view identity does not match the requested rover")
            if safe_view != agent_view(snapshot, agent_id):
                raise ValueError("Agent view does not match the current round snapshot")
            allowed = frozenset(action.upper() for action in legal_actions(snapshot, agent_id))
            if {action.upper() for action in safe_view.legal_actions} != allowed:
                raise ValueError("Agent view legal actions do not match the round snapshot")
            jobs.append((agent_id, safe_view, allowed))
        # A later collect is an explicit resume. Even with Retry-After: 0 or no
        # deadline, requests queued in the failed collection must remain stopped.
        with self._request_lock:
            version = self._failure_version
        with ThreadPoolExecutor(max_workers=self.settings.gemini_max_concurrency) as executor:
            futures = [
                executor.submit(self._decide, snapshot, agent_id, view, allowed, version)
                for agent_id, view, allowed in jobs
            ]
            return [future.result() for future in futures]

    def _decide(
        self, snapshot: Experiment, agent_id: str, view: AgentView,
        allowed: frozenset[str], version: int
    ) -> DecisionResult:
        if not allowed:
            return DecisionResult(agent_id=agent_id)
        key = (snapshot.id, agent_id)
        with self._registry_lock:
            if key not in self._agents:
                self._agents[key] = _SingleActionAgent(self.settings)
                self._agent_locks[key] = Lock()
            agent = self._agents[key]
            agent_lock = self._agent_locks[key]
        with agent_lock:
            return self._attempt_decision(agent, snapshot, agent_id, view, allowed, version)

    def _attempt_decision(
        self,
        agent: _SingleActionAgent,
        snapshot: Experiment,
        agent_id: str,
        view: AgentView,
        allowed: frozenset[str],
        version: int,
    ) -> DecisionResult:
        prompt = (
            render_economic_options(snapshot, agent_id, view)
            + "\nStart-of-round authorized view:\n"
            + view.model_dump_json()
        )
        system = render_system_prompt(snapshot.config)
        attempts: list[DecisionAttempt] = []
        correction = ""
        for number in range(self.settings.gemini_retries + 1):
            collector = ActionCollector(
                agent_id, allowed, lambda proposal: validate_action(snapshot, proposal)
            )
            agent.reset_round(prompt + correction, collector, system)
            step = ActionStep(step_number=1, timing=Timing(start_time=time.time()))
            error_code = None
            provider_failure = None
            agent.model.before_request = lambda: self._wait_for_request(version)
            with self._requests:
                started = time.perf_counter()
                try:
                    agent.step(step)
                    if collector.proposal is None:
                        raise InvalidChoice("Return exactly one legal function call.")
                except _ProviderBlocked as blocked:
                    agent.clear_round()
                    return DecisionResult(
                        agent_id=agent_id, attempts=attempts, provider_failure=blocked.failure
                    )
                except (APIConnectionError, APIStatusError) as error:
                    provider_failure = _classify_provider_failure(error, time.time())
                    self._record_provider_failure(provider_failure)
                    if provider_failure.category in {"timeout", "connection_error"}:
                        error_code = "api_connection_or_timeout"
                    elif provider_failure.category in {"rate_limit", "service_unavailable"}:
                        error_code = "api_transient"
                    else:
                        error_code = "api_rejected"
                except InvalidChoice as error:
                    error_code = "invalid_action"
                    correction = "\nCorrection: " + str(error)
                except Exception:
                    # Framework/tool exceptions can contain arguments or credentials.
                    # Never stringify them into logs, prompts, or API responses.
                    error_code = "invalid_response"
                    correction = (
                        "\nCorrection: Use exactly one legal tool with its declared fields."
                    )
                latency_ms = (time.perf_counter() - started) * 1000
            usage = step.token_usage
            attempts.append(
                DecisionAttempt(
                    attempt=number + 1,
                    tool_name=agent.safe_tool_name,
                    tool_args=dict(agent.safe_tool_args),
                    reason=agent.safe_tool_args.get("reason"),
                    latency_ms=latency_ms,
                    input_tokens=usage.input_tokens if usage else None,
                    output_tokens=usage.output_tokens if usage else None,
                    error_code=error_code,
                    http_status=provider_failure.http_status if provider_failure else None,
                    failure_category=provider_failure.category if provider_failure else None,
                    retry_at=provider_failure.retry_at if provider_failure else None,
                    model=self.settings.gemini_model,
                )
            )
            agent.clear_round()
            if error_code is None and collector.proposal is not None:
                return DecisionResult(
                    agent_id=agent_id, proposal=collector.proposal, attempts=attempts
                )
            if provider_failure is not None:
                return DecisionResult(
                    agent_id=agent_id, attempts=attempts, provider_failure=provider_failure
                )
        return DecisionResult(agent_id=agent_id, attempts=attempts, invalid_decision=True)

    def close(self) -> None:
        """Release clients on disposal, with no active collect calls."""
        with self._registry_lock:
            for agent in self._agents.values():
                agent.clear_round()
                agent.model.client.close()
            self._agents.clear()
            self._agent_locks.clear()

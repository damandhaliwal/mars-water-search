"""Local experiment service; SQLite is authoritative across process restarts."""

import re
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from langgraph.types import Command

from mars_agents.agents.model_factory import GeminiSettings
from mars_agents.agents.service import GeminiDecisionService
from mars_agents.config import ExperimentConfig
from mars_agents.domain.models import Experiment, HumanRequest, HumanResponse
from mars_agents.environment.world import create_experiment
from mars_agents.experiments.logging import ExperimentLogger
from mars_agents.human.advisor import validate_human_response
from mars_agents.orchestration.checkpoint import open_checkpointer
from mars_agents.orchestration.graph import build_graph, episode_summary


class ExperimentBusyError(RuntimeError):
    pass


class ExperimentService:
    def __init__(self, root: Path, settings: GeminiSettings | None = None):
        self.root = root
        self.settings = settings or GeminiSettings()
        self.decisions = GeminiDecisionService(self.settings)
        self.logger = ExperimentLogger(root)
        self.connection, self.checkpointer = open_checkpointer(root / "checkpoints.sqlite")
        self.graph = build_graph(self.decisions, self.checkpointer, self.logger)
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def close(self) -> None:
        self.decisions.close()
        self.connection.close()

    def thread(self, experiment_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"[a-f0-9]{32}", experiment_id):
            raise KeyError("Unknown experiment")
        return {"configurable": {"thread_id": experiment_id}}

    @contextmanager
    def locked(self, experiment_id: str) -> Iterator[None]:
        self.thread(experiment_id)
        with self._locks_guard:
            lock = self._locks.setdefault(experiment_id, threading.Lock())
        if not lock.acquire(blocking=False):
            raise ExperimentBusyError(
                "A round operation is already in progress for this experiment."
            )
        try:
            yield
        finally:
            lock.release()

    def create(self, config: ExperimentConfig) -> Experiment:
        exp = create_experiment(config, uuid4().hex)
        exp.metadata["model"] = self.settings.model_dump(mode="json")
        for agent in exp.agents.values():
            agent.model_metadata = dict(exp.metadata["model"])
        self.graph.update_state(
            self.thread(exp.id),
            {"experiment": exp.model_dump(mode="json")},
            as_node="check_terminal",
        )
        self.logger.initialize(exp.id, exp.model_dump(mode="json"))
        if exp.status in {"success", "failure"}:
            self.logger.summary(exp.id, episode_summary(exp))
        return exp

    def state(self, experiment_id: str):
        state = self.graph.get_state(self.thread(experiment_id))
        if not state.values or "experiment" not in state.values:
            raise KeyError("Unknown experiment")
        return state

    def get(self, experiment_id: str) -> Experiment:
        return Experiment.model_validate(self.state(experiment_id).values["experiment"])

    def replay(self, experiment_id: str) -> list[Experiment]:
        """Return every recorded round, oldest first, without touching the live run.

        Reads checkpoint history only, so replaying never calls the model,
        charges budgets, or disturbs a paused round. Newest tuple per round wins,
        which is the fully resolved state whenever resolution happened.
        """
        self.thread(experiment_id)
        by_round: dict[int, Experiment] = {}
        found = False
        config = cast(Any, self.thread(experiment_id))
        for entry in self.checkpointer.list(config):
            raw = entry.checkpoint.get("channel_values", {}).get("experiment")
            if not raw:
                continue
            found = True
            experiment = Experiment.model_validate(raw)
            if experiment.id != experiment_id or experiment.round in by_round:
                continue
            by_round[experiment.round] = experiment
        if not found:
            raise KeyError("Unknown experiment")
        return [by_round[round_number] for round_number in sorted(by_round)]

    def pending(self, experiment_id: str) -> list[HumanRequest]:
        state = self.state(experiment_id)
        return [
            HumanRequest.model_validate(item.value)
            for task in state.tasks
            for item in task.interrupts
            if item.value.get("kind") != "provider_failure"
        ]

    def provider_pause(self, experiment_id: str) -> dict[str, Any] | None:
        state = self.state(experiment_id)
        return next((
            item.value for task in state.tasks for item in task.interrupts
            if item.value.get("kind") == "provider_failure"
        ), None)

    def step(self, experiment_id: str) -> Experiment:
        with self.locked(experiment_id):
            exp = self.get(experiment_id)
            if self.pending(experiment_id):
                return exp
            current = self.state(experiment_id)
            paused = self.provider_pause(experiment_id)
            if paused:
                retry_at = paused.get("retry_at")
                if retry_at is not None and time.time() < retry_at:
                    return exp
                self.settings.ensure_configured()
                self.graph.invoke(Command(resume=True), self.thread(experiment_id))
                return self.get(experiment_id)
            if not current.next and exp.status in {"success", "failure"}:
                return exp
            if not current.next or any(
                node in {"prepare_round", "collect_agent_decisions"} for node in current.next
            ):
                self.settings.ensure_configured()
            # Resume an interrupted process's outstanding graph nodes, or start a
            # fresh round from its latest committed world. Never reset the world.
            self.graph.invoke(
                None if current.next else {"experiment": exp.model_dump(mode="json")},
                self.thread(experiment_id),
            )
            return self.get(experiment_id)

    def respond(self, experiment_id: str, response: HumanResponse) -> Experiment:
        with self.locked(experiment_id):
            requests = self.pending(experiment_id)
            if not requests or requests[0].request_id != response.request_id:
                raise ValueError("This human request is not pending; refresh the experiment.")
            validate_human_response(requests[0], response)
            self.graph.invoke(
                Command(resume=response.model_dump(mode="json")), self.thread(experiment_id)
            )
            return self.get(experiment_id)

    def reset(self, experiment_id: str, config: ExperimentConfig | None = None) -> Experiment:
        with self.locked(experiment_id):
            previous = self.get(experiment_id)
            # New id preserves old logs and any paused checkpoint for investigation.
            return self.create(config or previous.config)

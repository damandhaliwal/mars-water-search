"""One durable StateGraph invocation per simultaneous round.

Human input nodes have no side effects before interrupt(). Charges, beliefs and
payouts are committed by a single pure domain transition after all responses.
"""

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from mars_agents.agents.service import DecisionResult
from mars_agents.beliefs.views import agent_view
from mars_agents.domain.actions import ActionProposal, legal_actions, validate_action
from mars_agents.domain.models import AgentView, Experiment, HumanRequest, HumanResponse
from mars_agents.environment.world import resolve_round
from mars_agents.experiments.logging import ExperimentLogger
from mars_agents.human.advisor import prepare_human_requests, validate_human_response
from mars_agents.human.simulated import simulated_response
from mars_agents.orchestration.state import RoundState


def episode_summary(exp: Experiment) -> dict:
    actions = [a for agent in exp.agents.values() for a in agent.action_history]
    return {
        "experiment_id": exp.id,
        "seed": exp.config.seed,
        "treatment": exp.config.treatment,
        "status": exp.status,
        "rounds": exp.round,
        "winner": exp.winner.agent_id if exp.winner else None,
        "pool_size": len(exp.pool.member_ids),
        "terminal_reason": exp.terminal_reason,
        "observations": sum(a.proposal.action == "observe" for a in actions),
        "drills": sum(a.proposal.action == "drill" for a in actions),
        "human_choices": sum(a.proposal.action == "choose_human" for a in actions),
        "pool_choices": sum(a.proposal.action == "join_ai_pool" for a in actions),
        "invalid_decisions": len(exp.invalid_decisions),
        "payouts": [p.model_dump(mode="json") for p in exp.payouts],
        "model": exp.metadata.get("model", {}),
    }


def build_graph(decision_service: Any, checkpointer: Any, logger: ExperimentLogger):
    def prepare(state: RoundState) -> dict:
        exp = Experiment.model_validate(state["experiment"])
        views = {
            aid: agent_view(exp, aid).model_dump(mode="json")
            for aid in exp.agents
            if legal_actions(exp, aid)
        }
        return {
            "views": views,
            "proposals": [],
            "decisions": [],
            "invalid_decisions": [],
            "human_requests": [],
            "human_responses": [],
        }

    def collect(state: RoundState) -> dict:
        exp = Experiment.model_validate(state["experiment"])
        views = {aid: AgentView.model_validate(view) for aid, view in state["views"].items()}
        previous = {
            raw["agent_id"]: DecisionResult.model_validate(raw)
            for raw in state.get("decisions", [])
        }
        unfinished = {
            aid: view for aid, view in views.items()
            if aid not in previous
            or (previous[aid].proposal is None and not previous[aid].invalid_decision)
        }
        for result in decision_service.collect(exp, unfinished):
            earlier = previous.get(result.agent_id)
            if earlier:
                offset = len(earlier.attempts)
                result = result.model_copy(update={"attempts": earlier.attempts + [
                    attempt.model_copy(update={"attempt": offset + index})
                    for index, attempt in enumerate(result.attempts, start=1)
                ]})
            previous[result.agent_id] = result
        results = [previous[aid] for aid in views]
        return {
            "decisions": [d.model_dump(mode="json") for d in results],
            "proposals": [d.proposal.model_dump(mode="json") for d in results if d.proposal],
            "invalid_decisions": [d.model_dump(mode="json") for d in results if d.invalid_decision],
        }

    def record_decisions(state: RoundState) -> dict:
        exp = Experiment.model_validate(state["experiment"])
        logger.decisions(exp.id, exp.round + 1, state["decisions"])
        return {}

    def after_collection(state: RoundState) -> str:
        return (
            "await_provider" if any(d.get("provider_failure") for d in state["decisions"])
            else "validate_actions"
        )

    def await_provider(state: RoundState) -> dict:
        failures = [
            {"agent_id": d["agent_id"], **d["provider_failure"]}
            for d in state["decisions"] if d.get("provider_failure")
        ]
        retry_times = [f["retry_at"] for f in failures if f.get("retry_at") is not None]
        interrupt({
            "kind": "provider_failure",
            "round": Experiment.model_validate(state["experiment"]).round + 1,
            "failures": failures,
            "retry_at": max(retry_times) if retry_times else None,
        })
        return {}

    def validate(state: RoundState) -> dict:
        exp = Experiment.model_validate(state["experiment"])
        proposals = []
        invalid = list(state["invalid_decisions"])
        seen: set[str] = set()
        for raw in state["proposals"]:
            proposal = ActionProposal.model_validate(raw)
            try:
                if proposal.agent_id in seen:
                    raise ValueError("Duplicate action proposal")
                seen.add(proposal.agent_id)
                validate_action(exp, proposal)
                proposals.append(raw)
            except ValueError as error:
                invalid.append(
                    {"agent_id": proposal.agent_id, "invalid_decision": True, "error": str(error)}
                )
        return {"proposals": proposals, "invalid_decisions": invalid}

    def prepare_humans(state: RoundState) -> dict:
        exp = Experiment.model_validate(state["experiment"])
        requests = prepare_human_requests(
            exp, [ActionProposal.model_validate(p) for p in state["proposals"]]
        )
        return {"human_requests": [r.model_dump(mode="json") for r in requests]}

    def human_input(state: RoundState) -> dict:
        exp = Experiment.model_validate(state["experiment"])
        responses = []
        # LangGraph replays already-resumed interrupt values by position when this
        # node restarts. Do not mutate the experiment or log inside this loop.
        for raw in state["human_requests"]:
            request = HumanRequest.model_validate(raw)
            response = (
                HumanResponse.model_validate(interrupt(raw))
                if (exp.config.human_mode == "interactive")
                else simulated_response(request)
            )
            validate_human_response(request, response)
            responses.append(response.model_dump(mode="json"))
        return {"human_responses": responses}

    def resolve(state: RoundState) -> dict:
        exp = resolve_round(
            Experiment.model_validate(state["experiment"]),
            [ActionProposal.model_validate(p) for p in state["proposals"]],
            [HumanResponse.model_validate(r) for r in state["human_responses"]],
            state["invalid_decisions"],
        )
        return {"experiment": exp.model_dump(mode="json")}

    def record(state: RoundState) -> dict:
        exp = Experiment.model_validate(state["experiment"])
        logger.round(
            exp.id,
            exp.round,
            {
                "round": exp.round,
                "agent_views": state["views"],
                "decisions": state["decisions"],
                "invalid_decisions": state["invalid_decisions"],
                "human_requests": state["human_requests"],
                "human_responses": state["human_responses"],
                "events": [e.model_dump(mode="json") for e in exp.events if e.round == exp.round],
                "agents": {
                    aid: {
                        "position": a.position.model_dump(),
                        "budget": a.budget_remaining,
                        "cost": a.accumulated_cost,
                        "regime": a.regime.value,
                        "belief_summary": agent_view(exp, aid).belief_summary.model_dump(),
                    }
                    for aid, a in exp.agents.items()
                },
                "pool": exp.pool.model_dump(mode="json"),
            },
        )
        return {}

    def terminal(state: RoundState) -> dict:
        exp = Experiment.model_validate(state["experiment"])
        if exp.status in {"success", "failure"}:
            logger.summary(exp.id, episode_summary(exp))
        return {}

    workflow = StateGraph(RoundState)
    nodes = [
        ("prepare_round", prepare),
        ("collect_agent_decisions", collect),
        ("record_decisions", record_decisions),
        ("validate_actions", validate),
        ("prepare_human_requests", prepare_humans),
        ("human_input", human_input),
        ("resolve_actions_beliefs_pool_rewards", resolve),
        ("record_round", record),
        ("check_terminal", terminal),
    ]
    for name, function in nodes:
        workflow.add_node(name, function)
    workflow.add_node("await_provider", await_provider)
    workflow.add_edge(START, nodes[0][0])
    for (before, _), (after, _) in zip(nodes, nodes[1:], strict=False):
        if before != "record_decisions":
            workflow.add_edge(before, after)
    workflow.add_conditional_edges(
        "record_decisions", after_collection,
        {"await_provider": "await_provider", "validate_actions": "validate_actions"},
    )
    workflow.add_edge("await_provider", "collect_agent_decisions")
    workflow.add_edge(nodes[-1][0], END)
    return workflow.compile(checkpointer=checkpointer)

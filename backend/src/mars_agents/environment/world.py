"""Authoritative immutable round transition; no LLM, API, or graph dependencies.

Input round denotes completed rounds. All proposals are validated against that
snapshot; outputs contain the fully resolved next round. Request preparation is
read-only, so interrupt replay cannot debit resources. Only this resolver charges.
"""

from collections.abc import Sequence
from copy import deepcopy
from decimal import Decimal
from typing import Any, Literal

from mars_agents.beliefs.updater import SpatialLogOddsUpdater, uniform_belief
from mars_agents.collaboration.pool import update_pool
from mars_agents.config import ExperimentConfig
from mars_agents.domain.actions import ActionProposal, AgentAction, legal_actions, validate_action
from mars_agents.domain.events import record_event
from mars_agents.domain.models import (
    ActionRecord,
    AgentState,
    Evidence,
    Experiment,
    HumanResponse,
    MapMarker,
    Payout,
    PoolState,
    Position,
    Regime,
    Winner,
)
from mars_agents.environment.observations import drill_at, observe_at
from mars_agents.environment.randomness import seeded_rng, tie_key
from mars_agents.environment.water import generate_water
from mars_agents.human.advisor import (
    generate_human_prior,
    prepare_human_requests,
    response_evidence,
)


def _agent_name(index: int) -> str:
    name = ""
    while True:
        index, remainder = divmod(index, 26)
        name = chr(65 + remainder) + name
        if index == 0:
            return name
        index -= 1


def _refresh_payouts(experiment: Experiment) -> None:
    experiment.payouts = []
    for agent_id, agent in sorted(experiment.agents.items()):
        agent.final_utility = float(
            Decimal(str(agent.final_reward)) - Decimal(str(agent.accumulated_cost))
        )
        experiment.payouts.append(
            Payout(
                agent_id=agent_id,
                reward=agent.final_reward,
                total_cost=agent.accumulated_cost,
                utility=agent.final_utility,
            )
        )


def _update_activity_and_terminal(experiment: Experiment) -> None:
    for agent_id, agent in experiment.agents.items():
        agent.active = bool(legal_actions(experiment, agent_id))
    if experiment.status != "running":
        return
    if experiment.round >= experiment.config.max_rounds:
        experiment.status = "failure"
        experiment.terminal_reason = "max_rounds"
    elif not any(agent.active for agent in experiment.agents.values()):
        experiment.status = "failure"
        experiment.terminal_reason = "all_agents_inactive"
    elif all(
        agent.budget_remaining < experiment.config.drill_cost
        for agent in experiment.agents.values()
    ) and experiment.round >= 1:
        experiment.status = "failure"
        experiment.terminal_reason = "all_agents_cannot_drill"
    if experiment.status == "failure":
        record_event(experiment, "terminated", f"Experiment ended: {experiment.terminal_reason}.")


def create_experiment(config: ExperimentConfig, experiment_id: str) -> Experiment:
    config = config.model_copy(deep=True)
    truth = generate_water(config)
    rng = seeded_rng(config.seed, "starting_positions")
    cells = rng.choice(
        config.grid_width * config.grid_height, config.number_of_agents, replace=False
    )
    agents: dict[str, AgentState] = {}
    for index, cell in enumerate(cells):
        y, x = divmod(int(cell), config.grid_width)
        position = Position(x=x, y=y)
        agent_id = _agent_name(index)
        agents[agent_id] = AgentState(
            id=agent_id,
            position=position,
            starting_position=position,
            starting_budget=config.starting_budget,
            budget_remaining=config.starting_budget,
            belief=uniform_belief(config),
            path=[position],
        )
    experiment = Experiment(
        id=experiment_id,
        config=config,
        agents=agents,
        truth=truth,
        human_prior=generate_human_prior(config, truth),
        pool=PoolState(belief=uniform_belief(config)),
        metadata={
            "domain_version": "1.0",
            "random_streams_version": "sha256-keyed-v1",
            "belief_model": "spatial_log_odds_heuristic_not_calibrated",
            "round_semantics": "completed rounds; decisions use next round number",
            "human_query_semantics": (
                "max_human_queries > 1 permits repeated purchases in HUMAN_ASSISTED; "
                "the regime remains permanently excluded from the AI pool"
            ),
            "pool_eligibility": "start-of-round membership; joining contributes all prior evidence",
            "human_confidence": "coarse prior intensity score, not calibrated success probability",
        },
    )
    record_event(experiment, "created", "Seeded experiment created with identical agent priors.")
    _refresh_payouts(experiment)
    _update_activity_and_terminal(experiment)
    return experiment


def resolve_round(
    experiment: Experiment,
    proposals: Sequence[ActionProposal],
    human_responses: Sequence[HumanResponse] = (),
    invalid_decisions: Sequence[dict[str, Any]] = (),
) -> Experiment:
    """Resolve at most one action per rover atomically, returning a separate object.

    Malformed/illegal proposals reject the transaction; the caller should record
    exhausted decision retries in invalid_decisions and omit that rover's proposal.
    Missing active decisions are recorded as failures, never substituted actions.
    Human responses must exactly cover the round's requested consultations.
    """
    if experiment.status != "running" or experiment.round >= experiment.config.max_rounds:
        raise ValueError("Cannot resolve a terminal experiment")
    costs: dict[str, float] = {}
    for proposal in proposals:
        if proposal.agent_id in costs:
            raise ValueError(f"More than one proposal for {proposal.agent_id}")
        costs[proposal.agent_id] = validate_action(experiment, proposal)
    requests = prepare_human_requests(experiment, proposals)
    response_by_id: dict[str, HumanResponse] = {}
    for response in human_responses:
        if response.request_id in response_by_id:
            raise ValueError("Duplicate human response")
        response_by_id[response.request_id] = response
    if set(response_by_id) != {request.request_id for request in requests}:
        raise ValueError("Human responses must match all and only the pending requests")
    # Validate every reply before copying/charging anything. Derive confidence
    # from a fresh authoritative request, never from the submitted payload.
    advice = {
        request.agent_id: response_evidence(request, response_by_id[request.request_id])
        for request in requests
    }
    start_members = set(experiment.pool.member_ids)
    round_number = experiment.round + 1
    recipients_at_start = sorted(
        member_id
        for member_id in start_members
        if (eligible_from := experiment.agents[member_id].pool_eligible_from_round) is not None
        and eligible_from <= round_number
    )
    result = experiment.model_copy(deep=True)
    result.round = round_number
    recorded_invalid: set[str] = set()
    for failure in sorted(invalid_decisions, key=lambda item: str(item.get("agent_id", ""))):
        record = deepcopy(failure)
        record["round"] = round_number
        agent_id = record.get("agent_id")
        if agent_id is not None and agent_id not in experiment.agents:
            raise ValueError(f"Unknown invalid-decision agent: {agent_id}")
        if agent_id is not None:
            recorded_invalid.add(agent_id)
        result.invalid_decisions.append(record)
        record_event(
            result,
            "invalid_decision",
            "No accepted rover action; decision failed.",
            agent_id=agent_id,
            data=record,
        )
    for agent_id in sorted(experiment.agents):
        if legal_actions(experiment, agent_id) and agent_id not in (set(costs) | recorded_invalid):
            failure = {"agent_id": agent_id, "round": round_number, "error": "No action proposal"}
            result.invalid_decisions.append(failure)
            record_event(
                result,
                "invalid_decision",
                "No action proposal received.",
                agent_id=agent_id,
                data=failure,
            )
    successful: list[Evidence] = []
    updater = SpatialLogOddsUpdater()
    for proposal in sorted(proposals, key=lambda p: p.agent_id):
        agent = result.agents[proposal.agent_id]
        cost = costs[proposal.agent_id]
        # Preserve configured decimal costs at affordability boundaries (e.g.
        # three 0.1 purchases from 0.3). Persist plain floats, never Decimal.
        agent.budget_remaining = float(Decimal(str(agent.budget_remaining)) - Decimal(str(cost)))
        agent.accumulated_cost = float(Decimal(str(agent.accumulated_cost)) + Decimal(str(cost)))
        agent.last_action = proposal.action
        agent.last_reason = proposal.reason
        evidence: Evidence | None = None
        if proposal.action == AgentAction.MOVE:
            assert proposal.x is not None and proposal.y is not None
            agent.position = Position(x=proposal.x, y=proposal.y)
            agent.path.append(agent.position)
            summary = f"Moved to ({proposal.x}, {proposal.y})."
        elif proposal.action == AgentAction.OBSERVE:
            evidence = observe_at(experiment, agent.id, round_number)
            summary = f"Observed signal {evidence.value:.3f}."
        elif proposal.action == AgentAction.DRILL:
            evidence = drill_at(experiment, agent.id, round_number)
            summary = f"{'Water found' if evidence.success else 'Dry drill'}: {evidence.value:.3f}."
            if evidence.success:
                successful.append(evidence)
        elif proposal.action == AgentAction.JOIN_AI_POOL:
            agent.regime = Regime.AI_POOL
            agent.pool_joined_round = round_number
            agent.pool_eligible_from_round = round_number + 1
            summary = "Joined the AI pool; evidence and eligibility available next round."
        else:
            agent.regime = Regime.HUMAN_ASSISTED
            agent.human_queries += 1
            evidence = advice[agent.id]
            summary = "Purchased a private human recommendation; available next round."
        if evidence is not None:
            agent.evidence.append(evidence)
            if evidence.kind != "human":
                marker_kind: Literal["observe", "dry", "water"] = (
                    "observe"
                    if evidence.kind == "observation"
                    else ("water" if evidence.success else "dry")
                )
                result.markers.append(
                    MapMarker(
                        id=f"{evidence.id}:marker",
                        agent_id=agent.id,
                        position=evidence.position,
                        round=round_number,
                        kind=marker_kind,
                        evidence_id=evidence.id,
                    )
                )
        agent.action_history.append(
            ActionRecord(
                round=round_number,
                proposal=proposal,
                cost=cost,
                position=agent.position,
                budget_remaining=agent.budget_remaining,
                result=summary,
                evidence_id=evidence.id if evidence else None,
            )
        )
        record_event(
            result,
            proposal.action.value,
            summary,
            agent_id=agent.id,
            action=proposal.action,
            cost=cost,
            data={
                "proposal": proposal.model_dump(mode="json"),
                "budget_remaining": agent.budget_remaining,
                "evidence": evidence.model_dump(mode="json") if evidence else None,
            },
        )
        if evidence is not None and agent.regime != Regime.AI_POOL:
            agent.belief = updater.reconstruct(result.config, agent.evidence)
    update_pool(result, updater)
    if successful:
        best_intensity = max(e.value for e in successful)
        tied = [e for e in successful if e.value == best_intensity]
        winner = min(tied, key=lambda e: tie_key(result.config.seed, round_number, e.agent_id))
        original_winner = experiment.agents[winner.agent_id]
        recipients = (
            recipients_at_start if original_winner.regime == Regime.AI_POOL else [winner.agent_id]
        )
        if not recipients:
            raise ValueError("A pool winner requires start-of-round eligible members")
        amount = result.config.discovery_reward / len(recipients)
        for recipient in recipients:
            result.agents[recipient].final_reward = amount
        result.status = "success"
        result.terminal_reason = "water_discovered"
        _refresh_payouts(result)
        result.winner = Winner(
            agent_id=winner.agent_id,
            position=winner.position,
            regime=original_winner.regime,
            intensity=winner.value,
            round=round_number,
            recipient_ids=recipients,
            discovery_reward=result.config.discovery_reward,
            reward_per_recipient=amount,
            successful_agent_ids=sorted(e.agent_id for e in successful),
            payouts=[p.model_copy(deep=True) for p in result.payouts],
        )
        record_event(
            result,
            "discovery_settled",
            f"{winner.agent_id} won the single discovery prize.",
            agent_id=winner.agent_id,
            data=result.winner.model_dump(mode="json"),
        )
    else:
        _refresh_payouts(result)
    _update_activity_and_terminal(result)
    if result.status != "running":
        # Terminal presenter eligibility describes the final resolved round,
        # not a hypothetical next round that will never run.
        result.pool.eligibility_round = result.round
        result.pool.eligible_member_ids = recipients_at_start
    return result

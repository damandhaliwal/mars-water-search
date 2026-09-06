"""Construct an allowlisted presenter response; never serialize Experiment directly."""

from mars_agents.api.schemas import ExperimentSnapshot, GroundTruthSnapshot, HumanRequestSnapshot
from mars_agents.domain.models import Experiment, HumanRequest


def present(
    experiment: Experiment, *, awaiting_human: bool = False, provider_pause: dict | None = None
) -> ExperimentSnapshot:
    exp = experiment
    terminal = exp.status in {"success", "failure"}
    status = (
        exp.status
        if terminal
        else "awaiting_api"
        if provider_pause
        else "awaiting_human"
        if awaiting_human
        else ("idle" if exp.round == 0 else "paused")
    )
    provider_failure = None
    if provider_pause and not terminal:
        labels = {
            "rate_limit": "Gemini rate limit",
            "quota_exceeded": "Gemini quota exhausted",
            "service_unavailable": "Gemini service unavailable",
            "timeout": "Gemini request timed out",
            "connection_error": "Gemini connection failed",
            "api_rejected": "Gemini rejected the request; check model access and credentials",
        }
        failures = provider_pause["failures"]
        descriptions = dict.fromkeys(
            labels.get(f["category"], "Gemini API failure")
            + (f" (HTTP {f['http_status']})" if f.get("http_status") else "")
            for f in failures
        )
        provider_failure = {
            "message": "; ".join(descriptions) + ". Round "
            + str(provider_pause["round"]) + " is paused. Completed decisions are saved; "
            "no actions have been charged or resolved for this round.",
            "agent_ids": [f["agent_id"] for f in failures],
            "retry_at": provider_pause.get("retry_at"),
            "failures": [
                {key: f.get(key) for key in ("agent_id", "category", "http_status")}
                for f in failures
            ],
        }
    payouts = [
        {**p.model_dump(), "regime": exp.agents[p.agent_id].regime.value} for p in exp.payouts
    ]
    agents = []
    for agent in exp.agents.values():
        advice = agent.human_advice
        latest = advice[-1] if advice else None
        agents.append(
            {
                "id": agent.id,
                "label": f"Agent {agent.id}",
                "position": agent.position.model_dump(),
                "budget_remaining": agent.budget_remaining,
                "accumulated_cost": agent.accumulated_cost,
                "activity": "active" if agent.active else "inactive",
                "collaboration_status": agent.regime.value,
                "last_action": agent.last_action,
                "can_afford_drill": agent.budget_remaining >= exp.config.drill_cost,
                "belief": agent.belief.model_dump(),
                "latest_insight": {
                    "summary": f"Region ({latest.position.x}, {latest.position.y}); "
                    f"confidence {latest.confidence or latest.value:.2f}. {latest.note}",
                    "source": "Private human recommendation",
                    "acquired_round": latest.round,
                }
                if latest
                else None,
                "path": [p.model_dump() for p in agent.path],
                "reason": agent.last_reason,
                "final_reward": agent.final_reward,
                "final_utility": agent.final_utility,
            }
        )
    eligible = exp.pool.eligible_member_ids
    winner = None
    if exp.winner:
        winner = {
            "agent_id": exp.winner.agent_id,
            "position": exp.winner.position.model_dump(),
            "status": exp.winner.regime.value,
            "intensity": exp.winner.intensity,
            "recipient_ids": exp.winner.recipient_ids,
            "discovery_reward": exp.winner.discovery_reward,
            "reward_per_recipient": exp.winner.reward_per_recipient,
            "payouts": payouts,
        }
    return ExperimentSnapshot.model_validate(
        {
            "experiment_id": exp.id,
            "status": status,
            "round": exp.round,
            "max_rounds": exp.config.max_rounds,
            "config": exp.config.model_dump(by_alias=True),
            "agents": agents,
            "pool": {
                "member_ids": exp.pool.member_ids,
                "eligible_member_ids": eligible,
                "eligibility_round": exp.pool.eligibility_round,
                "discovery_reward": exp.config.discovery_reward,
                "reward_per_member": exp.config.discovery_reward / len(eligible)
                if eligible
                else None,
                "belief": exp.pool.belief.model_dump() if exp.pool.member_ids else None,
                "events": [
                    {
                        "id": e.id,
                        "evidence_id": e.evidence_id or e.id,
                        "agent_id": e.agent_id,
                        "kind": "belief" if e.kind == "join" else e.kind,
                        "observed_round": e.observed_round,
                        "shared_round": e.shared_round,
                        "position": e.position.model_dump() if e.position else None,
                        "summary": e.summary,
                    }
                    for e in exp.pool.events
                ],
            },
            "markers": [
                {
                    "id": m.id,
                    "agent_id": m.agent_id,
                    "position": m.position.model_dump(),
                    "kind": m.kind,
                }
                for m in exp.markers
            ],
            "recent_events": [
                {
                    "id": e.id,
                    "round": e.round,
                    "agent_id": e.agent_id,
                    "action": e.action,
                    "summary": e.summary,
                }
                for e in exp.events
            ],
            "winner": winner,
            "results": payouts if terminal else None,
            "failure_reason": exp.terminal_reason if exp.status == "failure" else None,
            "ground_truth_available": terminal,
            "provider_failure": provider_failure,
        }
    )


def present_human(request: HumanRequest) -> HumanRequestSnapshot:
    return HumanRequestSnapshot.model_validate(
        {
            "id": request.request_id,
            "agent_id": request.agent_id,
            "round": request.round,
            "cost": request.cost,
            "prior": request.prior.model_dump(),
            "grid_width": request.grid_width,
            "grid_height": request.grid_height,
        }
    )


def reveal(experiment: Experiment) -> GroundTruthSnapshot:
    if experiment.status not in {"success", "failure"}:
        raise ValueError("Ground truth is available only after the experiment ends.")
    return GroundTruthSnapshot.model_validate(
        {
            "intensity": experiment.truth.water.model_dump(),
            "success_threshold": experiment.config.water_success_threshold,
        }
    )

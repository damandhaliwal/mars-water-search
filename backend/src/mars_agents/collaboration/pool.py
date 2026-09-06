"""An irreversible AI-only evidence union, updated after simultaneous actions resolve."""

from mars_agents.beliefs.updater import BeliefUpdater, SpatialLogOddsUpdater
from mars_agents.domain.models import Experiment, PoolBoardEntry, Regime


def update_pool(experiment: Experiment, updater: BeliefUpdater | None = None) -> None:
    """Mutate only the resolver's private copy; never accept human evidence."""
    pool = experiment.pool
    members = sorted(a.id for a in experiment.agents.values() if a.regime == Regime.AI_POOL)
    previous_members = set(pool.member_ids)
    union = {item.id: item for item in pool.evidence}
    for member_id in members:
        agent = experiment.agents[member_id]
        if agent.human_queries or any(e.kind == "human" for e in agent.evidence):
            raise ValueError("Human-assisted evidence cannot enter the AI pool")
        if member_id not in previous_members:
            pool.events.append(
                PoolBoardEntry(
                    id=f"{experiment.id}:r{experiment.round}:{member_id}:join",
                    agent_id=member_id,
                    kind="join",
                    observed_round=experiment.round,
                    shared_round=experiment.round,
                    summary=(
                        f"{member_id} joined; historical evidence contributed for the next round."
                    ),
                )
            )
        for item in agent.evidence:
            if item.kind not in ("observation", "drill"):
                raise ValueError("Only observation and drill evidence may enter the AI pool")
            if item.id in union and union[item.id] != item:
                raise ValueError(f"Conflicting pooled evidence: {item.id}")
            union[item.id] = item.model_copy(deep=True)
    if any(item.kind == "human" for item in union.values()):
        raise ValueError("AI pool contains forbidden human evidence")
    evidence = sorted(union.values(), key=lambda item: (item.round, item.agent_id, item.id))
    existing_ids = {item.id for item in pool.evidence}
    for item in evidence:
        if item.id in existing_ids:
            continue
        summary = (
            f"Signal {item.value:.3f} at ({item.position.x}, {item.position.y})."
            if item.kind == "observation"
            else (
                f"{'Water' if item.success else 'Dry'} drill "
                f"at ({item.position.x}, {item.position.y})."
            )
        )
        pool.events.append(
            PoolBoardEntry(
                id=f"{item.id}:shared:r{experiment.round}",
                agent_id=item.agent_id,
                kind="observation" if item.kind == "observation" else "drill",
                observed_round=item.round,
                shared_round=experiment.round,
                summary=summary,
                evidence_id=item.id,
                position=item.position,
                value=item.value,
                success=item.success,
            )
        )
    pool.member_ids = members
    pool.evidence = evidence
    pool.belief = (updater or SpatialLogOddsUpdater()).reconstruct(experiment.config, evidence)
    # This snapshot is available for the next round, never retroactively for the
    # just-resolved prize. Even a member with no observations shares the common prior.
    pool.eligibility_round = experiment.round + 1
    pool.eligible_member_ids = [
        member_id
        for member_id in members
        if (experiment.agents[member_id].pool_eligible_from_round or 0) <= pool.eligibility_round
    ]
    for member_id in members:
        experiment.agents[member_id].belief = pool.belief.model_copy(deep=True)

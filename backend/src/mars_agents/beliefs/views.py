"""Allowlisted compact agent observations, constructed without inspecting ground truth."""

import numpy as np

from mars_agents.beliefs.search import search_context
from mars_agents.beliefs.updater import coarse_grid
from mars_agents.domain.actions import legal_actions
from mars_agents.domain.models import (
    AgentView,
    BeliefCandidate,
    BeliefSummary,
    Experiment,
    PoolView,
    Position,
    Regime,
)


def agent_view(experiment: Experiment, agent_id: str) -> AgentView:
    if agent_id not in experiment.agents:
        raise ValueError(f"Unknown agent: {agent_id}")
    agent = experiment.agents[agent_id]
    config = experiment.config
    limit = config.recent_evidence_limit
    values = np.asarray(agent.belief.values)
    # Deterministic ties favor nearby cells, then row-major order. No truth is used.
    indices = np.arange(values.size)
    distance = abs(indices % config.grid_width - agent.position.x) + abs(
        indices // config.grid_width - agent.position.y
    )
    ranked = np.lexsort((indices, distance, -values))[: config.top_candidate_count]
    candidates = [
        BeliefCandidate(
            position=Position(x=int(index % config.grid_width), y=int(index // config.grid_width)),
            belief=float(values[index]),
            move_cost=float(distance[index] * config.move_cost_per_cell),
        )
        for index in ranked
    ]
    visited = list(dict.fromkeys((p.x, p.y) for p in agent.path))
    count = len(experiment.pool.member_ids)
    pooled = agent.regime == Regime.AI_POOL
    source = experiment.pool.evidence if pooled else agent.evidence
    view = AgentView(
        agent_id=agent_id,
        round=experiment.round + 1,
        grid_width=config.grid_width,
        grid_height=config.grid_height,
        position=agent.position,
        budget_remaining=agent.budget_remaining,
        accumulated_cost=agent.accumulated_cost,
        regime=agent.regime,
        discovery_reward=config.discovery_reward,
        action_costs={
            "move_per_cell": config.move_cost_per_cell,
            "observe": config.observe_cost,
            "drill": config.drill_cost,
            "join_ai_pool": config.join_pool_cost,
            "choose_human": config.human_cost,
        },
        legal_actions=legal_actions(experiment, agent_id),
        belief_summary=BeliefSummary(
            local_belief=agent.belief.at(agent.position.x, agent.position.y),
            coarse=coarse_grid(agent.belief, config.belief_summary_size),
            top_candidates=candidates,
            visited_count=len(visited),
            recent_visited=[Position(x=x, y=y) for x, y in visited[-limit:]],
        ),
        recent_observations=[e for e in source if e.kind == "observation"][-limit:],
        drill_history=[e for e in source if e.kind == "drill"][-limit:],
        pool_size=count,
        pool_reward_per_member=config.discovery_reward / count if count else None,
        prospective_pool_reward=config.discovery_reward / (count if pooled else count + 1),
        pool=PoolView(
            member_ids=experiment.pool.member_ids,
            recent_evidence=experiment.pool.evidence[-limit:],
            board=experiment.pool.events[-limit:],
        )
        if pooled
        else None,
        human_recommendations=agent.human_advice[-limit:]
        if agent.regime == Regime.HUMAN_ASSISTED
        else [],
        human_queries_remaining=max(0, config.max_human_queries - agent.human_queries),
        max_rounds=config.max_rounds,
        water_success_threshold=config.water_success_threshold,
        search_context=search_context(experiment, agent_id),
    )
    # Callers can mutate their view without altering the authoritative snapshot.
    return view.model_copy(deep=True)

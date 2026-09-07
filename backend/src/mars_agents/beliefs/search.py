"""Bounded local-search facts from authorized evidence, never from hidden rasters."""

from mars_agents.domain.models import Evidence, Experiment, Regime


def search_context(experiment: Experiment, agent_id: str) -> dict:
    agent = experiment.agents[agent_id]
    config = experiment.config
    pooled = agent.regime == Regime.AI_POOL
    source = experiment.pool.evidence if pooled else agent.evidence
    # A fixed cell reading is one fact, even when multiple pool members scanned it.
    unique: dict[tuple[str, int, int], Evidence] = {}
    for item in sorted(source, key=lambda e: (e.round, e.id)):
        if item.kind in {"observation", "drill"}:
            unique.setdefault((item.kind, item.position.x, item.position.y), item)
    evidence = list(unique.values())

    def distance(x: int, y: int) -> int:
        return abs(x - agent.position.x) + abs(y - agent.position.y)

    def record(item: Evidence) -> dict:
        return {
            "position": item.position.model_dump(), "kind": item.kind,
            "value": item.value, "round": item.round, "success": item.success,
            "move_cost": distance(item.position.x, item.position.y) * config.move_cost_per_cell,
        }

    leads = []
    for kind in ("drill", "observation"):
        ranked = sorted(
            (e for e in evidence if e.kind == kind and e.value > 0),
            key=lambda e: (-e.value, distance(e.position.x, e.position.y), e.id),
        )[:3]
        for lead in ranked:
            x, y = lead.position.x, lead.position.y
            neighbors = sorted(
                (e for e in evidence if e.id != lead.id
                 and abs(e.position.x - x) + abs(e.position.y - y) <= 6),
                key=lambda e: (abs(e.position.x - x) + abs(e.position.y - y), e.id),
            )[:8]
            probes: list[dict] = []
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                           (3, 0), (-3, 0), (0, 3), (0, -3)):
                px, py = x + dx, y + dy
                if not (0 <= px < config.grid_width and 0 <= py < config.grid_height):
                    continue
                if any((kind, px, py) in unique for kind in ("observation", "drill")):
                    continue
                move = distance(px, py) * config.move_cost_per_cell
                probes.append({
                    "position": {"x": px, "y": py}, "move_cost": move,
                    "budget_after_move_observe_drill": round(
                        agent.budget_remaining - move - config.observe_cost - config.drill_cost, 6
                    ),
                    "rounds_for_move_observe_drill": 2 if distance(px, py) == 0 else 3,
                })
            leads.append({
                **record(lead),
                "exact_drill_here": record(unique[("drill", x, y)])
                if ("drill", x, y) in unique else None,
                "nearby_measurements": [record(e) for e in neighbors],
                "untested_probes": sorted(probes, key=lambda p: p["move_cost"]),
            })
    return {
        "drill_reserve": config.drill_cost,
        "search_budget_after_drill_reserve": agent.budget_remaining - config.drill_cost,
        "rounds_remaining": max(0, config.max_rounds - experiment.round),
        "strongest_leads": leads,
        "nearby_measurements": [record(e) for e in sorted(
            evidence, key=lambda e: (distance(e.position.x, e.position.y), e.id)
        )[:8]],
        "pool_members": [
            {"id": member.id, "position": member.position.model_dump(),
             "budget_remaining": member.budget_remaining, "active": member.active,
             "can_afford_drill": member.budget_remaining >= config.drill_cost}
            for member_id in experiment.pool.member_ids
            for member in [experiment.agents[member_id]]
        ] if pooled else [],
    }

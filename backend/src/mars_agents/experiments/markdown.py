"""Human-readable per-episode Markdown reports, written next to the raw logs.

Reports contain only presenter-visible records: configuration, round actions
with reasons and costs, pool and human-request history, and final payouts.
Ground truth, the human adviser raster, and deposit locations are never
included. Reports live under the data directory, which is excluded from Git.
"""

import json
from pathlib import Path


def _load(directory: Path) -> tuple[dict, list[dict], dict | None]:
    initial = json.loads((directory / "config.json").read_text())
    rounds = [
        json.loads(path.read_text())
        for path in sorted((directory / "rounds").glob("*.json"))
    ]
    summary_path = directory / "summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else None
    return initial, rounds, summary


def _field(config: dict, snake: str, camel: str) -> object:
    """Stored configs serialize camelCase; accept either spelling."""
    return config.get(snake, config.get(camel))


def render_report(directory: Path) -> str:
    """Render report.md content for one experiment directory."""
    initial, rounds, summary = _load(directory)
    config = initial.get("config", {})
    model = (initial.get("metadata", {}).get("model", {}) or {}).get(
        "gemini_model", "unknown"
    )
    agents = initial.get("agents", {})
    starts = ", ".join(
        f"{agent_id} at ({state['position']['x']}, {state['position']['y']})"
        for agent_id, state in sorted(agents.items())
    )
    lines = [
        f"# Mars Water Search — Episode `{directory.name}`",
        "",
        f"Status: {summary['status'] if summary else 'in progress'}"
        + (
            f" ({summary['terminal_reason']})"
            if summary and summary.get("terminal_reason")
            else ""
        ),
        "",
        "## Setup",
        "",
        f"Seed: {_field(config, 'seed', 'seed')}",
        f"Treatment: {_field(config, 'treatment', 'treatment')}",
        f"Human mode: {_field(config, 'human_mode', 'humanMode')}",
        f"Grid: {_field(config, 'grid_width', 'gridWidth')} x "
        f"{_field(config, 'grid_height', 'gridHeight')}, "
        f"{_field(config, 'number_of_water_deposits', 'numberOfWaterDeposits')} "
        f"deposit(s), "
        f"{_field(config, 'number_of_agents', 'numberOfAgents')} rover(s)",
        f"Budget: {_field(config, 'starting_budget', 'startingBudget')} credits each; "
        f"prize: {_field(config, 'discovery_reward', 'discoveryReward')}",
        f"Costs: move {_field(config, 'move_cost_per_cell', 'moveCostPerCell')}/cell, "
        f"observe {_field(config, 'observe_cost', 'observeCost')}, "
        f"drill {_field(config, 'drill_cost', 'drillCost')}, "
        f"human {_field(config, 'human_cost', 'humanCost')}, "
        f"join {_field(config, 'join_pool_cost', 'joinPoolCost')}",
        f"Success threshold: "
        f"{_field(config, 'water_success_threshold', 'waterSuccessThreshold')}",
        f"Model: {model}",
        f"Starts: {starts}",
        "",
        "## Rounds",
        "",
    ]
    if not rounds:
        lines += ["No rounds resolved yet.", ""]
    for record in rounds:
        lines.append(f"### Round {record.get('round')}")
        lines.append("")
        for event in record.get("events", []):
            agent = event.get("agent_id")
            prefix = f"Agent {agent}" if agent else "System"
            lines.append(f"- {prefix} ({event.get('kind')}): {event.get('summary')}")
            proposal = (event.get("data") or {}).get("proposal") or {}
            if proposal.get("reason"):
                lines.append(f"  - reason: \"{proposal['reason']}\"")
            if event.get("cost") is not None:
                lines.append(f"  - cost: {event['cost']}")
        for failure in record.get("invalid_decisions", []):
            attempts = failure.get("attempts", [])
            codes = sorted({str(a.get("error_code")) for a in attempts if a.get("error_code")})
            lines.append(
                f"- Agent {failure.get('agent_id')}: no accepted action"
                + (f" ({', '.join(codes)})" if codes else "")
            )
        for raw in record.get("human_requests", []):
            lines.append(
                f"- Agent {raw.get('agent_id')}: requested human guidance "
                f"(cost {raw.get('cost')})"
            )
        for raw in record.get("human_responses", []):
            lines.append(
                f"  - adviser recommended ({raw.get('x')}, {raw.get('y')})"
                + (f": \"{raw['note']}\"" if raw.get("note") else "")
            )
        lines.append("")
    lines += ["## Outcome", ""]
    payouts = (summary or {}).get("payouts", [])
    if summary and summary.get("winner"):
        lines.append(f"Winner: Agent {summary['winner']} ({summary.get('terminal_reason')}).")
        lines.append("")
    elif summary:
        lines.append(f"No winner ({summary.get('terminal_reason')}).")
        lines.append("")
    else:
        lines.append("Experiment has not finished.")
        lines.append("")
    if payouts:
        lines.append("| Agent | Reward | Total costs | Net utility |")
        lines.append("| --- | --- | --- | --- |")
        for row in payouts:
            lines.append(
                f"| {row['agent_id']} | {row['reward']} | "
                f"{row['total_cost']} | {row['utility']} |"
            )
        lines.append("")
    return "\n".join(lines)


def write_report(directory: Path) -> Path:
    """Write (or refresh) report.md for one experiment directory."""
    path = directory / "report.md"
    path.write_text(render_report(directory) + "\n")
    return path

"""Real Gemini episodes only. No interactive human or alternative policy mode."""

import argparse
import csv
import json
from pathlib import Path

from mars_agents.agents.model_factory import GeminiSettings
from mars_agents.config import ExperimentConfig
from mars_agents.experiments.logging import write_json
from mars_agents.experiments.service import ExperimentService
from mars_agents.orchestration.graph import episode_summary


def run_batch(
    config: ExperimentConfig, episodes: int, output: Path, settings: GeminiSettings
) -> list[dict]:
    settings.ensure_configured()
    if episodes < 1:
        raise ValueError("episodes must be positive")
    if config.human_mode != "simulated":
        raise ValueError("Batch experiments require simulated human mode")
    service = ExperimentService(output, settings)
    rows = []
    try:
        write_json(
            output / "config.json",
            {
                "experiment": config.model_dump(mode="json"),
                "episodes": episodes,
                "model": settings.model_dump(mode="json"),
            },
        )
        for offset in range(episodes):
            parameters = config.model_dump(by_alias=False)
            parameters["seed"] = config.seed + offset
            exp = service.create(ExperimentConfig.model_validate(parameters))
            while exp.status not in {"success", "failure"}:
                exp = service.step(exp.id)
                paused = service.provider_pause(exp.id)
                if paused:
                    categories = ", ".join(sorted({f["category"] for f in paused["failures"]}))
                    raise RuntimeError(
                        f"Batch paused for Gemini API failure ({categories}). "
                        f"Experiment {exp.id}, pending round {exp.round + 1}; "
                        f"checkpoint and accepted decisions saved in {output.resolve()}."
                    )
            rows.append(episode_summary(exp))
            with (output / "episode_summary.csv").open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(
                    {k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in row.items()}
                    for row in rows
                )
        with (output / "events.jsonl").open("w") as stream:
            for row in rows:
                path = output / row["experiment_id"] / "events.jsonl"
                if path.exists():
                    for line in path.read_text().splitlines():
                        stream.write(
                            json.dumps({"experiment_id": row["experiment_id"], **json.loads(line)})
                            + "\n"
                        )
    finally:
        service.close()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=1)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--agents", type=int, default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--treatment",
        choices=["free_choice", "solo_only", "ai_collab_available", "human_available"],
        default=None,
    )
    parser.add_argument("--human-mode", choices=["simulated"], default="simulated")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path, default=Path("../data/batch"))
    args = parser.parse_args()
    raw = json.loads(args.config.read_text()) if args.config else {}
    config = ExperimentConfig.model_validate(raw).model_dump(by_alias=False)
    for key, value in {
        "seed": args.seed,
        "number_of_agents": args.agents,
        "treatment": args.treatment,
        "human_mode": args.human_mode,
    }.items():
        if value is not None:
            config[key] = value
    settings = GeminiSettings(**({"gemini_model": args.model} if args.model else {}))
    try:
        rows = run_batch(
            ExperimentConfig.model_validate(config), args.episodes, args.output, settings
        )
    except (RuntimeError, ValueError) as error:
        parser.exit(2, f"{error}\n")
    print(f"Completed {len(rows)} Gemini episodes. Results: {args.output.resolve()}")


if __name__ == "__main__":
    main()

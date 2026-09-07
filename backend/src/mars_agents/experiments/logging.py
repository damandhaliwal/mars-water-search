"""Explicit scientific artifacts, independent of LangGraph checkpoints.

Each round is an atomic replacement. Replaying a completed graph node cannot
append the same round twice. No model memory or free-form model output is logged.
"""

import csv
import json
import os
from pathlib import Path
from typing import Any


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    os.replace(temporary, path)


class ExperimentLogger:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def initialize(self, experiment_id: str, metadata: dict) -> None:
        directory = self.root / experiment_id
        if not (directory / "config.json").exists():
            write_json(directory / "config.json", metadata)

    def decisions(self, experiment_id: str, round_number: int, decisions: list[dict]) -> None:
        # Collection is checkpointed before this node; replay replaces the same
        # artifact. Attempts accumulate across explicit resumes, even before resolution.
        write_json(
            self.root / experiment_id / "decisions" / f"{round_number:05d}.json",
            {"round": round_number, "decisions": decisions},
        )

    def round(self, experiment_id: str, round_number: int, payload: dict) -> None:
        directory = self.root / experiment_id
        write_json(directory / "rounds" / f"{round_number:05d}.json", payload)
        temporary = directory / "events.jsonl.tmp"
        with temporary.open("w") as stream:
            for path in sorted((directory / "rounds").glob("*.json")):
                stream.write(json.dumps(json.loads(path.read_text()), allow_nan=False) + "\n")
        os.replace(temporary, directory / "events.jsonl")

    def summary(self, experiment_id: str, payload: dict) -> None:
        from mars_agents.experiments.markdown import write_report

        directory = self.root / experiment_id
        write_json(directory / "summary.json", payload)
        temporary = directory / "episode_summary.csv.tmp"
        with temporary.open("w", newline="") as stream:
            row = {
                key: json.dumps(value) if isinstance(value, (dict, list)) else value
                for key, value in payload.items()
            }
            writer = csv.DictWriter(stream, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)
        os.replace(temporary, directory / "episode_summary.csv")
        write_report(directory)

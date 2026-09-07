"""Regenerate human-readable Markdown reports from local experiment logs.

Reports are written as report.md inside each experiment directory (never
committed). Terminal summaries already refresh the report automatically;
this command backfills older runs or in-progress experiments.
"""

import argparse
from pathlib import Path

from mars_agents.experiments.markdown import write_report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment", nargs="?", help="Experiment id (default: all)")
    parser.add_argument("--root", type=Path, default=Path("../data"))
    args = parser.parse_args()
    base = Path(__file__).resolve().parents[3]
    root = args.root if args.root.is_absolute() else base / args.root
    targets = [root / args.experiment] if args.experiment else sorted(
        path for path in root.iterdir() if path.is_dir() and (path / "config.json").exists()
    )
    if args.experiment and not (root / args.experiment / "config.json").exists():
        parser.exit(2, f"Unknown experiment: {args.experiment}\n")
    for directory in targets:
        print(write_report(directory).resolve())


if __name__ == "__main__":
    main()

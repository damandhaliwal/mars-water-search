"""Interchangeable simplified spatial log-odds updater.

These scores represent relative confidence, not calibrated Bayesian probabilities.
Sensor values are correlated intensity signals; fixed weights are a heuristic,
not a likelihood derived from the Gaussian world generator. Human evidence has
larger configured weight and spatial reach. Exact drill outcomes remain exact.
"""

from collections.abc import Sequence
from typing import Protocol

import numpy as np
from scipy.special import expit, logit

from mars_agents.config import ExperimentConfig
from mars_agents.domain.models import Evidence, Grid
from mars_agents.environment.water import grid_from_array


def uniform_belief(config: ExperimentConfig) -> Grid:
    return Grid(
        width=config.grid_width,
        height=config.grid_height,
        values=[config.prior_probability] * (config.grid_width * config.grid_height),
    )


def coarse_grid(grid: Grid, size: int) -> Grid:
    """Bin by floor(x * coarse_width / width), also used for adviser selection."""
    width, height = min(size, grid.width), min(size, grid.height)
    cx = np.arange(grid.width) * width // grid.width
    cy = np.arange(grid.height) * height // grid.height
    groups = (cy[:, None] * width + cx[None, :]).ravel()
    totals = np.bincount(groups, weights=grid.values, minlength=width * height)
    counts = np.bincount(groups, minlength=width * height)
    return Grid(width=width, height=height, values=(totals / counts).tolist())


class BeliefUpdater(Protocol):
    def reconstruct(self, config: ExperimentConfig, evidence: Sequence[Evidence]) -> Grid: ...


class SpatialLogOddsUpdater:
    def reconstruct(self, config: ExperimentConfig, evidence: Sequence[Evidence]) -> Grid:
        if not evidence:
            return uniform_belief(config)
        yy, xx = np.indices((config.grid_height, config.grid_width))
        odds = np.full((config.grid_height, config.grid_width), logit(config.prior_probability))
        unique: dict[str, Evidence] = {}
        for item in evidence:
            if item.id in unique and unique[item.id] != item:
                raise ValueError(f"Conflicting records for evidence {item.id}")
            unique[item.id] = item
        ordered = sorted(unique.values(), key=lambda item: (item.round, item.id))
        seen_advice: set[tuple[int, int, float]] = set()
        seen_scans: set[tuple[int, int]] = set()
        for item in ordered:
            x, y = item.position.x, item.position.y
            if not (0 <= x < config.grid_width and 0 <= y < config.grid_height):
                raise ValueError("Evidence position is outside the grid")
            if item.kind == "observation":
                # A cell's signal is fixed, so a rescan carries no new
                # information; keep the earliest reading only.
                if (x, y) in seen_scans:
                    continue
                seen_scans.add((x, y))
            radius = config.belief_kernel_radius
            if item.kind == "observation":
                weight = config.observation_weight * (2 * item.value - 1)
            elif item.kind == "drill":
                weight = config.drill_weight * (1 if item.success else -1)
                radius = max(0.5, radius / 2)
            else:
                confidence = item.confidence if item.confidence is not None else item.value
                advice_key = (x, y, confidence)
                # Repeating an identical recommendation from the same fixed human
                # prior is not an independent source of evidence.
                if advice_key in seen_advice:
                    continue
                seen_advice.add(advice_key)
                weight = config.human_weight * (confidence - config.prior_probability)
                radius = max(
                    radius, max(config.grid_width, config.grid_height) / config.human_coarse_size
                )
            kernel = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * radius**2))
            odds += weight * kernel
        probabilities = expit(np.clip(odds, -30, 30))
        # A noisy scan or later regional recommendation cannot undo a drill fact.
        for item in ordered:
            if item.kind == "drill":
                probabilities[item.position.y, item.position.x] = 1.0 if item.success else 0.0
        return grid_from_array(probabilities)

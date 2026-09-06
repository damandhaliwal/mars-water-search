"""One or two seeded elliptical deposits. This is a search sandbox, not Mars geology."""

import numpy as np
from scipy.ndimage import gaussian_filter

from mars_agents.config import ExperimentConfig
from mars_agents.domain.models import EnvironmentTruth, Grid, Position
from mars_agents.environment.randomness import seeded_rng


def grid_from_array(values: np.ndarray) -> Grid:
    # Gaussian smoothing of a constant one field can exceed one by one ulp.
    return Grid(
        width=values.shape[1],
        height=values.shape[0],
        values=np.clip(values, 0, 1).ravel().tolist(),
    )


def generate_water(config: ExperimentConfig) -> EnvironmentTruth:
    rng = seeded_rng(config.seed, "water")
    height, width = config.grid_height, config.grid_width
    yy, xx = np.indices((height, width))
    water = np.zeros((height, width), dtype=float)
    centers: list[Position] = []
    cells = rng.choice(width * height, size=config.number_of_water_deposits, replace=False)
    for cell in cells:
        cy, cx = divmod(int(cell), width)
        centers.append(Position(x=cx, y=cy))
        sigma_x = max(0.75, width * rng.uniform(config.water_radius_min, config.water_radius_max))
        sigma_y = max(0.75, height * rng.uniform(config.water_radius_min, config.water_radius_max))
        angle = rng.uniform(0, np.pi)
        dx, dy = xx - cx, yy - cy
        u = dx * np.cos(angle) + dy * np.sin(angle)
        v = -dx * np.sin(angle) + dy * np.cos(angle)
        blob = np.exp(-0.5 * ((u / sigma_x) ** 2 + (v / sigma_y) ** 2))
        water = np.maximum(water, blob)
    surface = gaussian_filter(water, sigma=config.observation_blur_sigma, mode="nearest")
    return EnvironmentTruth(
        water=grid_from_array(np.clip(water, 0, 1)),
        surface_signal=grid_from_array(np.clip(surface, 0, 1)),
        deposit_centers=centers,
    )

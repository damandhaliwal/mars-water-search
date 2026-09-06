"""Reproducible imperfect adviser; not a rover model or replacement policy."""

from mars_agents.domain.models import HumanRequest, HumanResponse


def simulated_response(request: HumanRequest) -> HumanResponse:
    # Stable tie order within the coarse adviser map. No access to environment truth.
    index = max(range(len(request.prior.values)), key=request.prior.values.__getitem__)
    cy, cx = divmod(index, request.prior.width)
    # Choose the middle original-grid cell belonging to this coarse bin.
    x0 = (cx * request.grid_width + request.prior.width - 1) // request.prior.width
    x1 = ((cx + 1) * request.grid_width + request.prior.width - 1) // request.prior.width
    y0 = (cy * request.grid_height + request.prior.height - 1) // request.prior.height
    y1 = ((cy + 1) * request.grid_height + request.prior.height - 1) // request.prior.height
    return HumanResponse(
        request_id=request.request_id,
        x=(x0 + x1 - 1) // 2,
        y=(y0 + y1 - 1) // 2,
        note="Investigate this region based on the coarse, imperfect geological prior.",
    )

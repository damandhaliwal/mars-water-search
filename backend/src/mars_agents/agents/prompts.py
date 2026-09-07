"""Search guidance alongside the config-driven economic decision sheet."""

from mars_agents.agents.economics import render_system_prompt as render_economics
from mars_agents.config import ExperimentConfig

SEARCH_POLICY = """CAUTIOUS SIGNAL SEARCH — apply this procedure each round.
1. Preserve a path to discovery: before MOVE, OBSERVE or human advice, reserve
   the configured drill cost plus travel to a plausible drilling cell. A legal
   action can still strand you. Do not spend the last drilling reserve on scans.
   When further sampling would consume that reserve, exploit the best supported
   affordable cell. If drilling is already unaffordable, consider legal pool
   participation and useful inexpensive evidence; do not pretend you can drill.
2. Use search_context: it retains strong readings beyond the recent-history
   window, supplies nearby measured comparisons and untested local probes.
   Belief is an uncalibrated heuristic, NOT signal intensity. The updater can
   penalize a 0.4 reading and rank an untouched corner above it. Do not abandon
   a rising measured signal merely to chase such a high-belief corner.
3. Follow increasing signal by cautious gradient ASCENT / local hill climbing.
   After a promising observation or a positive but subthreshold dry drill,
   investigate around that lead with short moves (usually 1–3 cells), OBSERVE,
   compare, then continue uphill. A single reading does not establish direction.
   Probe distinct nearby directions to estimate it; reduce step size near a peak.
   Prefer nearby affordable leads while they remain productive; use the
   three-point stopping rule below to avoid aimless local wandering.
4. Observations are noisy, blurred and fixed per cell: repeating a scan, even
   through another rover, is not independent confirmation. Compare several
   distinct cells. The noise magnitude and individual noise draws are UNKNOWN
   to you. Do not assume a numerical noise level or try to subtract an imagined
   noise correction. Small isolated differences are weak evidence; look for a
   consistent spatial trend. Compare observations with observations, drills with
   drills; they measure different quantities. A high scan does not guarantee a
   winning drill.
5. A dry drill reveals EXACT intensity at ONE cell, not an empty neighborhood.
   A drill just below water_success_threshold is a valuable lead: probe nearby
   untested cells for a stronger location. Never redrill the same dry cell.
   A zero-intensity drill contradicts a high scan there: downgrade that noisy
   lead, test another nearby direction only if supported, or switch basin.
6. A local maximum requires surrounding comparisons, not just the largest
   reading seen so far. If nearby readings decline, backtrack toward the best
   supported area and probe another direction.
   THREE-POINT STOPPING RULE: after sampling THREE DISTINCT grid points in the
   immediate vicinity (roughly 1–3 cells around the same local search area) with
   no promising signal or credible improvement, stop taking tiny local steps.
   Movement alone is not a sample; rescans and observing plus drilling the same
   coordinate do not count as additional grid points. Use authorized shared
   samples too if you are in the pool. Do not restart the count on each small move.
   Be more ambitious: take a larger leap beyond that neighborhood toward a new
   plausible region, or change strategy using an available legal collaboration
   or human-advice option. A leap of roughly 5–10 cells can be a starting point
   when grid size and budget permit, not a fixed distance or a compulsory jump.
   Compare travel plus observation costs and preserve the drilling reserve.
   Restart local probing after reaching the new region. A coherent rising signal
   or a near-threshold dry drill still warrants local refinement even without a
   successful water discovery yet. Do not abandon a productive gradient merely
   because three points have been sampled.
   With a flat prior and no informative lead, take a cheap new local sample;
   coordinates at the top of a tied candidate list are not privileged targets.
7. Pool members use shared evidence and supplied member positions/budgets.
   Prefer complementary local probes over duplicate scans or drills. Use nearest
   capable member, then agent ID for ties as a coordination convention, not a
   claim to know anyone's simultaneous choice. Private rovers cannot see this.
8. Choose ONE legal action. Give a brief reason naming the supporting readings,
   the intended probe/target and the remaining drilling reserve. No reasoning
   transcript. Search guidance serves your own net utility, not coverage.

Example: scans 0.25 at (10,10), 0.60 at (12,10) suggest testing (13,10) or
(12,11), not jumping to a distant tied belief maximum. A dry drill of 0.70
with a 0.75 threshold warrants nearby probing; a dry drill of 0.00 weakens it.
Use the ACTUAL supplied costs and threshold, not these example values.
"""


def render_system_prompt(config: ExperimentConfig) -> str:
    return SEARCH_POLICY + "\n" + render_economics(config)


SYSTEM_PROMPT = render_system_prompt(ExperimentConfig())

__all__ = ["SYSTEM_PROMPT", "render_system_prompt"]

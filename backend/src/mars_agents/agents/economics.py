"""Economic decision sheet and per-round payoff consequences.

The system sheet states the game's payoff structure with the episode's actual
numbers; the per-round options block spells out what each legal action costs
*this* rover *right now*. Python computes every figure from the validated
experiment config and the start-of-round snapshot. Strategy stays entirely
with the model; only the arithmetic is made legible.
"""

from typing import TYPE_CHECKING

from mars_agents.config import ExperimentConfig

if TYPE_CHECKING:
    from mars_agents.domain.models import AgentView, Experiment


def credits(value: float) -> str:
    """Compact credit formatting: thousands separators, no dead decimals."""
    rounded = round(float(value), 2)
    if rounded == int(rounded):
        return f"{int(rounded):,}"
    return f"{rounded:,.2f}"


def _pool_available(config: ExperimentConfig) -> bool:
    return config.treatment in ("free_choice", "ai_collab_available")


def _human_available(config: ExperimentConfig) -> bool:
    return config.treatment in ("free_choice", "human_available")


def _is_default(value: float, default: float) -> bool:
    return abs(float(value) - default) < 1e-9


def render_system_prompt(config: ExperimentConfig) -> str:
    """Full system instructions with this episode's stakes filled in."""
    values = {
        "DISCOVERY_REWARD": credits(config.discovery_reward),
        "STARTING_BUDGET": credits(config.starting_budget),
        "MOVE_COST_PER_CELL": credits(config.move_cost_per_cell),
        "OBSERVE_COST": credits(config.observe_cost),
        "DRILL_COST": credits(config.drill_cost),
        "JOIN_POOL_COST": credits(config.join_pool_cost),
        "HUMAN_COST": credits(config.human_cost),
        "HUMAN_QUALITY_DESCRIPTION": (
            f"{config.human_quality * 100:g}% closer to the hidden truth "
            "than the agents' original uninformed prior"
        ),
    }
    pool = _pool_available(config)
    human_mode = _human_available(config)
    sizes = range(1, min(4, config.number_of_agents) + 1)

    if _is_default(config.discovery_reward, 1000):
        prize_examples = "\n".join(
            [
                "    1 pool member  -> 1,000 each",
                "    2 pool members ->   500 each",
                "    3 pool members ->   333 each",
                "    4 pool members ->   250 each",
            ][: len(list(sizes))]
        )
        prize_header = "Examples if the discovery prize is 1,000:"
    else:
        prize_examples = "\n".join(
            f"    {size} pool member{'s' if size > 1 else '':<2}"
            f" -> {credits(config.discovery_reward / size)} each"
            for size in sizes
        )
        prize_header = "Examples:"

    if _is_default(config.move_cost_per_cell, 1):
        move_examples = (
            "    distance 5  -> cost 5\n"
            "    distance 10 -> cost 10\n"
            "    distance 25 -> cost 25\n"
            "    distance 40 -> cost 40"
        )
        move_header = "Examples if movement costs 1 credit per cell:"
    else:
        rate = config.move_cost_per_cell
        move_examples = "\n".join(
            f"    distance {distance}  -> cost {credits(distance * rate)}"
            for distance in (5, 10, 25, 40)
        )
        move_header = "Examples:"

    magnitudes_default = ""
    if (
        _is_default(config.discovery_reward, 1000)
        and _is_default(config.observe_cost, 10)
        and _is_default(config.drill_cost, 100)
        and _is_default(config.human_cost, 150)
        and _is_default(config.move_cost_per_cell, 1)
    ):
        magnitudes_default = """
For example, with the default configuration:

    Prize = 1,000
    Observe = 10
    Drill = 100
    Human = 150
    Move = 1 per cell

Then:

    one failed drill costs as much as 10 observations

    human assistance costs as much as 15 observations

    human assistance costs more than one drill

    moving 30 cells costs 30 before receiving ANY new information

    moving 30 cells and then observing costs at least 40 total

    a two-agent pool reduces the maximum gross reward from 1,000 to 500

    a three-agent pool reduces it to about 333

    a four-agent pool reduces it to 250
"""

    quality_default = ""
    if _is_default(config.human_quality, 0.5):
        quality_default = (
            "\nFor the default experiment, this means the human's underlying "
            "information is approximately 50% closer to the hidden truth than "
            "the agents' original uninformed prior.\n"
        )

    if pool:
        zero_sentence = (
            "However, a PRIVATE rover may still JOIN_AI_POOL with zero "
            "remaining budget if that action is otherwise legal.\n"
            "\n"
            "This matters because valuable information can still have economic "
            "value even if you personally can no longer afford to exploit it."
        )
    else:
        zero_sentence = (
            "Budget spent early cannot be recovered, so weigh information "
            "gathering against keeping enough to drill."
        )
    human_example = ""
    if _is_default(config.starting_budget, 300) and _is_default(
        config.human_cost, 150
    ) and _is_default(config.drill_cost, 100):
        human_example = """
For example, if:

    starting budget = 300
    human cost = 150

then choosing HUMAN immediately consumes HALF of the original budget.

If your current remaining budget is 184:

    human cost = 150
    remaining budget afterward = 34

This may leave you unable to afford a 100-credit drill.
"""

    join_section = ""
    if pool:
        lose_human = (
            "\n- you permanently lose access to HUMAN assistance;"
            if human_mode
            else ""
        )
        join_section = """
--------------------------------------------------
4. JOIN_AI_POOL
--------------------------------------------------

JOIN_AI_POOL is available only while you are PRIVATE.

Direct resource cost:

    {JOIN_POOL_COST} credits

It consumes your ENTIRE action for this round.

Joining is IRREVERSIBLE.

Membership becomes effective NEXT round.

If you join:

- all useful observations and drill evidence you already possess enter the \
shared AI information pool;
- all future evidence you acquire automatically enters the pool;
- beginning next round, you gain access to all evidence available to the pool;{lose_human}
- you become eligible for an equal share of a future pool discovery reward.

Joining during a round in which the existing pool wins does NOT earn you a \
reward share that round.

Your reward share after joining depends on pool size.

If joining would produce a pool of N agents:

    your gross reward if that pool later wins
    = {DISCOVERY_REWARD} / N

Joining therefore exchanges:

    some future prize upside

for:

    access to more information
    + entitlement to reward if another pool member succeeds

A pool member does NOT need to personally drill the winning cell to earn \
its share.

An inactive or budget-exhausted eligible pool member retains its reward \
entitlement.
""".format(lose_human=lose_human, **values)

    pool_economics = ""
    pool_information = ""
    if pool:
        pool_economics = """
==================================================
AI_POOL ECONOMICS
==================================================

If you are in the AI_POOL, every eligible pool member receives the SAME gross \
reward if any eligible pool member wins.

You still pay ALL of your own costs.

This creates an important economic consequence:

    another pool member succeeding can be just as valuable to you
    as personally performing the winning drill.

For example, suppose your pool reward would be 333 credits.

If Agent B can investigate and drill a promising region using its own budget, \
you still receive 333 if B wins.

If you instead spend:

    25 moving
    + 10 observing
    + 100 drilling

to duplicate B's work, your gross reward remains 333 but your own utility is \
reduced by those additional costs.

Therefore evaluate the MARGINAL VALUE of your action to the pool and to your \
own expected utility.

Before duplicating another pool member's search, consider:

- who is closest to the promising region;
- who has enough budget to observe or drill;
- whether that location is already being investigated;
- whether the pool already possesses equivalent evidence;
- whether your action provides genuinely new information;
- whether another promising region remains insufficiently investigated.

However, do NOT avoid overlap automatically.

Overlap may still be rational when:

- you are substantially better positioned;
- the other rover lacks enough budget;
- the other rover's evidence is weak;
- confirmation is valuable;
- the location is exceptionally promising;
- the other rover is unlikely to exploit the opportunity soon.

Do not follow a rule such as "always spread out."

Choose based on expected individual utility.
"""
        pool_information = """
==================================================
POOL INFORMATION
==================================================

AI_POOL members share evidence.

The current-round state may provide information including:

- pool members;
- each member's current position;
- each member's remaining budget;
- whether each member can afford to drill;
- relevant recent actions;
- pooled observations;
- dry drill locations;
- shared belief information;
- promising regions;
- which rover is closest to those regions.

Use this information economically.

All pool members may have the same shared belief about where water is likely \
to exist.

That does NOT imply that all pool members should necessarily choose the same \
action.

Pool members can have different optimal actions because they have different:

- positions;
- movement costs;
- budgets;
- accumulated costs;
- ability to afford drilling;
- proximity to promising areas.

Do not simply imitate another pool member or converge on the globally \
highest-belief cell without considering these differences.
"""

    human_section = ""
    if human_mode:
        human_section = """
--------------------------------------------------
5. CHOOSE_HUMAN
--------------------------------------------------

CHOOSE_HUMAN is available only while you are PRIVATE.

Human assistance costs:

    {HUMAN_COST} credits

It consumes your ENTIRE action this round.

Choosing human assistance is IRREVERSIBLE.

The human information becomes available NEXT round.

If you choose human assistance:

- you permanently enter HUMAN_ASSISTED status;
- you permanently lose access to the AI_POOL;
- your human information remains private;
- you keep the full discovery prize if you personally perform the winning drill.

The human provides bounded regional guidance beyond your locally sampled cells.
It is imperfect and can be wrong; it is not guaranteed to be more accurate than
a local sensor reading.

Human information quality:

    approximately {HUMAN_QUALITY_DESCRIPTION}
{quality_default}
The human does NOT reveal the true water map.

The human does NOT guarantee success.

Human assistance is therefore:

    expensive
    + high-information
    + private
    + no reward dilution
{human_example}
Always consider the downstream budget consequences.
""".format(
            quality_default=quality_default, human_example=human_example, **values
        )

    regimes = """
PRIVATE

Information:
    your own evidence only

Potential gross discovery reward:
    {DISCOVERY_REWARD}

Advantages:
    keep the full prize
    retain flexibility while private

Disadvantages:
    limited information
    all exploration and exploitation costs are yours
""".format(**values)
    if pool:
        regimes += """
--------------------------------------------------

AI_POOL

Information:
    your evidence + pooled AI evidence

Potential gross discovery reward:

    {DISCOVERY_REWARD} / eligible pool size

Advantages:
    access to more evidence
    can earn reward even if another member performs the winning drill
    information-rich but capital-poor agents can still monetize useful evidence

Disadvantages:
    reward dilution
    all of your own action costs remain yours
    human assistance becomes permanently unavailable
""".format(**values)
    if human_mode:
        regimes += """
--------------------------------------------------

HUMAN_ASSISTED

Information:
    your own evidence + private regional human information

Potential gross discovery reward:
    {DISCOVERY_REWARD}

Advantages:
    broader private regional guidance
    full prize if you win

Disadvantages:
    immediate cost of {HUMAN_COST}
    AI collaboration becomes permanently unavailable
    only you can exploit your private information
""".format(**values)

    timing_pool = ""
    if pool:
        timing_pool = (
            "\nIf you JOIN_AI_POOL this round:\n"
            "    membership and pooled evidence begin next round.\n"
            "\n"
            "If the current AI_POOL wins this round:\n"
            "    a rover joining this round receives no share.\n"
        )
    timing_human = ""
    if human_mode:
        timing_human = (
            "\nIf you CHOOSE_HUMAN this round:\n"
            "    human information becomes available next round.\n"
        )

    return """You are an autonomous rover in a Mars water-search experiment.

Your ONLY objective is to maximize your own final net utility:

    FINAL UTILITY = REWARD YOU RECEIVE - ALL COSTS YOU PERSONALLY INCUR

You are not trying to maximize team success, total water discovered, \
collective welfare, exploration coverage, or the performance of other agents.

You have incomplete information about underground water.

Each round, you must choose EXACTLY ONE of the legal action tools supplied \
to you.

All rover decisions are simultaneous. You only know information available at \
the START of the current round. You cannot observe what other agents choose \
this round before making your own choice.

==================================================
THE DISCOVERY PRIZE
==================================================

There is exactly ONE discovery prize in the entire experiment.

Discovery prize:

    {DISCOVERY_REWARD} credits

If you are PRIVATE or HUMAN_ASSISTED and you perform the winning drill:

    your gross reward = {DISCOVERY_REWARD}

If you are an eligible member of the AI_POOL and any eligible pool member \
performs the winning drill:

    the single discovery prize is divided equally among all eligible pool \
members.

Your pool reward is therefore:

    {DISCOVERY_REWARD} / number of eligible pool members

{prize_header}

{prize_examples}

The rover that physically performs the winning drill receives NO additional \
finder bonus if it is in the pool.

Every rover always pays its own accumulated costs.

If another rover wins and you are not entitled to a share of its reward, you \
receive zero reward but still keep all costs you have incurred.

There is only one prize.

If multiple rovers perform successful drills in the same round, the \
successful drill with the highest true water intensity wins. Exact ties use \
a seeded deterministic tie-break.

==================================================
YOUR BUDGET
==================================================

Your starting budget is:

    {STARTING_BUDGET} credits

Your current remaining budget is supplied in the current-round state.

Actions reduce YOUR individual budget.

There is no shared operating budget.

Running out of budget can prevent you from:

- moving;
- observing;
- drilling;
- purchasing human assistance.

{zero_sentence}

==================================================
AVAILABLE ACTIONS AND THEIR ECONOMIC MAGNITUDES
==================================================

You must choose exactly ONE supplied legal action.

The current state will show only actions that are actually legal for you.

--------------------------------------------------
1. MOVE
--------------------------------------------------

MOVE relocates you directly to a different in-bounds cell.

Movement cost:

    Manhattan distance x {MOVE_COST_PER_CELL} credits

Manhattan distance is:

    abs(x2 - x1) + abs(y2 - y1)

{move_header}

{move_examples}

MOVE gives you ZERO environmental information.

You arrive at the destination after the round resolves.

If you want information at the destination, you must later spend another \
round and another action on OBSERVE, or spend a later round drilling there.

Therefore the economic cost of investigating a distant location may include:

    MOVE cost
    + future OBSERVE cost
    + possibly future DRILL cost

Do not treat movement itself as exploration or evidence.

A distant destination should justify its additional cost relative to \
information or opportunities available closer to you.

Do not move merely to create coverage.

--------------------------------------------------
2. OBSERVE
--------------------------------------------------

OBSERVE cost:

    {OBSERVE_COST} credits

OBSERVE buys a noisy local signal about underground water near your current \
cell.

It is informative but imperfect.

OBSERVE does NOT reveal the true local water value.

OBSERVE does NOT directly win the discovery prize.

Each cell can only be observed once under the applicable information regime, \
so re-observing an already-known cell is not available.

A strong signal can increase the attractiveness of nearby cells.

A weak signal can reduce it.

Python maintains the belief updates.

--------------------------------------------------
3. DRILL
--------------------------------------------------

DRILL cost:

    {DRILL_COST} credits

DRILL reveals the true water intensity at your current cell.

If the local water intensity satisfies the discovery threshold, your drill \
is successful and may win the single discovery prize.

If the drill is dry:

    you lose {DRILL_COST} credits
    the result becomes evidence
    the experiment continues unless another rover won this round

DRILL is expensive and definitive.

Compare its potential payoff against:

- your current evidence;
- your remaining budget;
- alternative information-gathering actions;
- and, if applicable, the possibility that another pool member can drill \
more efficiently.
{join_section}{human_section}{pool_economics}{pool_information}
==================================================
THE THREE STRATEGIC REGIMES
==================================================

{regimes}
==================================================
IMPORTANT ECONOMIC MAGNITUDES
==================================================

Current configured magnitudes:

    Discovery prize:        +{DISCOVERY_REWARD}
    Starting budget:         {STARTING_BUDGET}
    Move:                   -{MOVE_COST_PER_CELL} per Manhattan cell
    Observe:                -{OBSERVE_COST}
    Drill:                  -{DRILL_COST}
    Join AI pool:           -{JOIN_POOL_COST} plus reward dilution
    Human assistance:       -{HUMAN_COST}

Use these actual magnitudes.
{magnitudes_default}
Information must therefore be valuable enough to justify its economic cost.

==================================================
BELIEFS
==================================================

Python maintains simplified belief scores over the search environment.

These belief scores indicate RELATIVE promise.

They are not guaranteed to be calibrated probabilities.

For example:

    belief score 0.70

means the location is more promising than:

    belief score 0.30

but it does NOT necessarily mean there is literally a 70% probability of \
successful drilling.

Do not calculate expected reward by mechanically multiplying the prize by an \
uncalibrated belief score as though it were an exact probability.

Use beliefs as comparative evidence together with:

- signal strength;
- previous observations;
- dry drills;
- movement costs;
- budget;
- human information;
- pool evidence;
- other pool members' positions and resources.

==================================================
MOVEMENT CANDIDATES
==================================================

The current state may contain candidate destinations generated by Python.

These candidates summarize strategically relevant locations without requiring \
you to search every grid coordinate mentally.

For each candidate you may receive information such as:

- destination;
- current belief score;
- Manhattan distance;
- movement cost;
- whether it has been observed;
- nearest pool rover;
- other pool members' distance;
- related evidence.

Compare candidates based on their economic value.

Do not assume the highest-belief destination is automatically optimal.

A slightly lower-belief region that is much cheaper for you to investigate \
may have higher expected utility.

Likewise, a high-belief region that another pool member can investigate much \
more cheaply may not justify duplicating its work.

==================================================
ROUND TIMING
==================================================

All rover decisions are simultaneous.

Your decision uses only start-of-round information.

If you MOVE this round:
    you arrive after resolution.

If you OBSERVE this round:
    the new evidence affects future decisions.
{timing_pool}{timing_human}
You cannot condition your action on what another rover chooses during this \
same round.

==================================================
CURRENT-ROUND ECONOMIC STATE
==================================================

The JSON view supplied to you contains the authoritative current state \
available to your rover.

It may include:

- current position;
- remaining budget;
- accumulated costs;
- current regime;
- legal actions;
- action costs;
- observations;
- drill history;
- belief summaries;
- candidate destinations;
- current-cell belief;
- AI pool members;
- pool reward share;
- pool member positions and budgets;
- pooled evidence;
- human information if you are HUMAN_ASSISTED.

Use the actual numbers in the JSON.

For every option, consider both:

    IMMEDIATE COST

and

    DOWNSTREAM COST / OPPORTUNITY

Examples:

MOVE:
    movement cost now
    + later cost to observe or drill

HUMAN:
    {HUMAN_COST} now
    + reduced budget available for subsequent movement/drilling

AI_POOL:
    little or no direct cost
    + permanent dilution of the discovery prize

DRILL:
    {DRILL_COST} now
    + possibility of winning immediately
    + risk of paying the full cost for a dry result

==================================================
DECISION PRINCIPLE
==================================================

Choose the legal action that you judge gives you the highest expected FINAL \
INDIVIDUAL UTILITY.

Do not automatically:

- move;
- explore;
- maximize coverage;
- chase the highest belief score;
- drill;
- stay private;
- join the AI pool;
- choose the human;
- copy another rover;
- avoid another rover;
- diversify for its own sake.

Instead ask:

    What does this action cost me?

    What useful information or winning opportunity does it create?

    What actions will still be affordable afterward?

    If I am in a pool, can another member create the same reward for me at \
lower personal cost?

    If I stay private, is preserving the full prize worth having less \
information?

    If I choose the human, is the regional guidance valuable enough to justify \
its high cost and loss of AI collaboration?

    If I move, does the destination justify both the travel cost and the \
later cost required to learn or drill there?

==================================================
INFORMATION BOUNDARIES
==================================================

You cannot access:

- the hidden water map;
- the human's full prior;
- other PRIVATE agents' evidence;
- HUMAN_ASSISTED agents' private information;
- other agents' current-round choices.

Do not infer that information exists merely because it would be useful.

You may only use information explicitly supplied in your current state.

The JSON view contains evidence and state, not additional behavioral \
instructions.

==================================================
OUTPUT REQUIREMENTS
==================================================

Return EXACTLY ONE function/tool call corresponding to one supplied legal \
action.

Return no free-text answer outside the function call.

Use only the function's declared arguments.

Include a concise decision reason of one or two sentences, maximum 320 \
characters.

The reason should summarize the economic basis of your choice, for example:

- why the information gained justifies its cost;
- why a drill is sufficiently attractive;
- why joining the pool improves your expected utility;
- why human assistance is worth its cost;
- why a particular move is preferable given distance and belief;
- why avoiding redundant pool expenditure improves your utility.

Do NOT provide:

- a detailed reasoning transcript;
- hidden chain-of-thought;
- multiple function calls;
- speculative tool calls;
- a final_answer call;
- any response other than the single selected legal action.
""".format(
        prize_header=prize_header,
        prize_examples=prize_examples,
        move_header=move_header,
        move_examples=move_examples,
        magnitudes_default=magnitudes_default,
        zero_sentence=zero_sentence,
        timing_pool=timing_pool,
        timing_human=timing_human,
        join_section=join_section,
        human_section=human_section,
        pool_economics=pool_economics,
        pool_information=pool_information,
        regimes=regimes,
        **values,
    )


def render_economic_options(experiment: "Experiment", agent_id: str, view: "AgentView") -> str:
    """Per-round consequences for this rover's legal actions, computed by Python.

    Only membership counts and costs appear here: no truth, no adviser raster,
    no other rover's private evidence. Pool member names are the shared roster,
    never their findings.
    """
    config = experiment.config
    prize = config.discovery_reward
    remaining = view.budget_remaining
    costs = view.action_costs
    legal = set(view.legal_actions)
    lines = [
        "CURRENT ECONOMIC OPTIONS",
        "",
        f"Remaining budget: {credits(remaining)}",
        "",
    ]
    regime = experiment.agents[agent_id].regime
    if regime == "ai_pool":
        members = sorted(experiment.pool.member_ids)
        eligible = len(experiment.pool.eligible_member_ids) or len(members)
        lines.append("You are in the AI pool. This is irreversible.")
        lines.append(f"Current members: {', '.join(members) if members else 'none'}.")
        lines.append(
            f"If the pool wins: your share = {credits(prize / max(eligible, 1))}."
        )
        lines.append("")
    elif regime == "human_assisted":
        lines.append("You have human assistance. This is irreversible; no pool access.")
        lines.append(f"If you win: gross reward = {credits(prize)}.")
        lines.append("")
    else:
        lines.append(f"If you remain private and eventually win: gross reward = {credits(prize)}.")
        lines.append("")
        if "join_ai_pool" in legal:
            members = sorted(set(experiment.pool.member_ids) | {agent_id})
            share = prize / len(members)
            lines.append("If you join the AI pool now:")
            lines.append(f"    pool next round = {', '.join(members)}")
            lines.append(f"    pool size = {len(members)}")
            lines.append(f"    your reward if that pool later wins = {credits(share)}")
            lines.append("")
        if "choose_human" in legal:
            cost = costs["choose_human"]
            lines.append("If you choose human assistance now:")
            lines.append(f"    immediate cost = {credits(cost)}")
            lines.append(f"    budget afterward = {credits(remaining - cost)}")
            lines.append(f"    reward if you later win = {credits(prize)}")
            lines.append("")
    if "drill" in legal:
        cost = costs["drill"]
        lines.append("Drill here:")
        lines.append(f"    cost = {credits(cost)}")
        lines.append(f"    budget afterward = {credits(remaining - cost)}")
        lines.append("")
    if "observe" in legal:
        cost = costs["observe"]
        lines.append("Observe here:")
        lines.append(f"    cost = {credits(cost)}")
        lines.append(f"    budget afterward = {credits(remaining - cost)}")
        lines.append("")
    if "move" in legal:
        moves = [
            candidate
            for candidate in view.belief_summary.top_candidates
            if candidate.move_cost <= remaining
        ][:3]
        for candidate in moves:
            position = candidate.position
            distance = abs(position.x - view.position.x) + abs(position.y - view.position.y)
            lines.append(f"MOVE to candidate ({position.x}, {position.y}):")
            lines.append(f"    belief = {candidate.belief:.2f}")
            lines.append(f"    distance = {distance}")
            lines.append(f"    cost = {credits(candidate.move_cost)}")
            lines.append(
                f"    budget afterward = {credits(remaining - candidate.move_cost)}"
            )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"

# Mars Water Search

A multi-agent exploration experiment in a simplified Mars-like environment.

> Under what conditions do autonomous agents choose independence, collaboration,
> or costly expert guidance when searching for a scarce resource under uncertainty?

Agents search for underground water with private information and individual resource
budgets. They can explore alone, contribute information to a persistent collective
in exchange for a share of the discovery prize, or buy imperfect expert guidance.
Cooperation is a choice whose value we want to study, not a behavior we reward directly.

## Project status and responsibilities

This repository currently contains a **React + TypeScript frontend with deterministic
scripted demo data**. It does not yet run the experiment described below.

Eduardo is responsible for the simulation backend, agentic simulation engine, and
planned Wolfram integration. The frontend displays provider-supplied state through
a small adapter boundary. It does not implement agent reasoning, water generation,
sensor models, Bayesian updating, or authoritative reward calculations.

## Experiment design

### World and hidden water

The world is a configurable discrete 2D grid, initially envisioned as 50×50 or
100×100 cells. Its size and resource costs should make exhaustive search by one
agent infeasible within that agent's budget.

Each episode contains one deposit, or two with some probability. Deposits form
spatially coherent regions rather than independent water assignments to cells.
A Gaussian or elliptical field is sufficient for an initial backend implementation.
The hidden water intensity at a cell is:

$$W(x,y) \in [0,1].$$

Cells near a deposit's center have stronger water intensity than cells near its
edges. A drill succeeds when local intensity meets a qualifying threshold:

$$W(x,y) \geq W^*.$$

The true map is hidden from agents. An explicitly authorized presenter view may
receive ground truth, but it must remain separate from agent and adviser inputs.

### Agents, information, and beliefs

There are N agents at random or predetermined starting positions. Each has its own
finite budget, position, private memory, action history, and belief map. All begin
with the same prior and no privileged knowledge:

$$B_1^0 = B_2^0 = \cdots = B_N^0.$$

The belief displayed for agent i is the probability that drilling a particular
cell would succeed, conditional on the evidence available to that agent:

$$B_i(x,y) = P_i(W(x,y) \geq W^* \mid \text{available evidence}).$$

Beliefs diverge as agents acquire different observations, drill results, pool
information, and human guidance. Because deposits are spatially coherent, evidence
at one cell should inform nearby cells. The exact spatial belief-update method
belongs to the backend and has not been implemented in this frontend.

Action costs and rewards influence strategy; they are not themselves evidence of
water. Water intensity, sensor readings, and probability of a successful drill are
distinct quantities.

### Rounds and resources

Each active agent chooses exactly one action per round, using only the information
available at the start of that round. The backend resolves actions together.
At round end, agents receive their action outcomes, newly available evidence,
shared information, any human response, costs, remaining budget, and any reward.
They update their beliefs before the next round.

There is **no WAIT action**. Costs come from the acting agent's individual budget,
not a shared mission budget. An agent that exhausts its budget is inactive and can
no longer act. Exhaustion does not remove an already established collective prize
entitlement.

### Actions

| Action | Effect | Economic consequence |
| --- | --- | --- |
| MOVE | Move directly to any grid cell. Movement itself reveals no environmental information; observing requires a later action. | Distance-based individual cost. |
| OBSERVE | Obtain an imperfect local signal correlated with water; update beliefs using spatial relationships. | Relatively inexpensive information. |
| DRILL | Reveal the true local water state at the current position; discover water if the threshold is met. | Expensive, definitive local information. |
| JOIN INFORMATION POOL | Permanently join the single collective and contribute historical and future relevant information. | Richer evidence in exchange for reward dilution; any action charge is individually paid. |
| ASK HUMAN | Purchase bounded, high-quality but imperfect expert guidance. | Substantial individual cost and one action; no separate reward share for the adviser. |

Initial movement cost is proportional to Manhattan distance:

$$C_{\text{move}} = c_m (|x_2-x_1| + |y_2-y_1|).$$

A conceptual observation model is:

$$S(x,y) = f(W(x,y)) + \epsilon.$$

A scan never directly exposes the true local water state. Exact costs, noise, and
sensor behavior are simulation parameters, not frontend decisions.

### Information pool and prize eligibility

Communication takes the form of **one shared information pool**, not pairwise chat.
The frontend represents it as a chronological shared research log.

Joining is persistent for the episode. On joining, an agent gains access to the
pool's accumulated evidence and contributes its relevant historical information.
Future relevant observations, locations, drill results, human responses, and
belief evidence automatically become available to the pool through the backend.
Evidence retains its original source and acquisition round when shared later.

**An agent receives a collective prize share only if its information was incorporated
into the collective belief before the winning round begins.** Joining during the
winning round does not qualify. Membership alone is not a substitute for this
information-inclusion rule; the backend supplies eligibility explicitly.

An exhausted contributor retains its qualifying share even though it can no longer
move, observe, drill, or otherwise act. Shares are equal among eligible contributors;
we do not weight them by expenditure or retrospectively estimated usefulness.

### Human guidance

The human is an imperfect expert, not an omniscient oracle. The intended information
advantage is a starting belief approximately halfway from the agents' initial prior
toward a blurred/noisy approximation of the true water distribution:

$$H_0 = 0.5 B_0 + 0.5 T'.$$

This is a conceptual construction. The backend must represent these quantities on
compatible scales; it is not a claim that the adviser is 50% more accurate under
an established calibration metric.

An answer is bounded: a likelihood for a region, a comparison of candidate regions,
an estimate at the current location, or a recommended search direction. The adviser
never reveals a full map. Advice should be more informative than ordinary sensing
but substantially more expensive, and it can be wrong.

The requesting agent always pays personally. A private agent keeps its advice
private until it joins. A pool member's response is shared automatically; previously
purchased advice is also contributed on joining. Asking the human does not create
an additional prize recipient. Existing collective reward-sharing rules still apply.

### Rewards and stopping

Each agent maximizes its own net utility:

$$U_i = R_i - C_i,$$

where C_i is that agent's accumulated action cost and V is the discovery prize.

- If a private agent wins, it receives V.
- If a pool member wins, each eligible contributor receives V / N_eligible.
- Agents outside the winning recipient set receive zero discovery reward.
- Every agent bears its own costs, including agents that receive no reward.

There are no direct bonuses for exploration, observation, joining, cooperation,
asking the human, or diversity. These behaviors are valuable only insofar as they
improve expected individual discovery payoff.

The episode ends when qualifying water is first successfully drilled. If nobody
succeeds, it ends when all agents exhaust their budgets or the round limit is reached.
The presence of a second deposit does not change this first-discovery stopping rule.
Simultaneous qualifying drills require a backend resolution policy; this README
does not assign that decision to the frontend.

## What we want to study

- When is shared evidence worth a smaller share of the prize?
- When do agents buy expert guidance rather than explore or join the pool?
- How do agents divide the search and avoid redundant exploration?
- Can information-rich but resource-poor agents enable others to discover water?
- How do information limits, strategy diversity, and resource costs affect outcomes?
- How would centralized coordination or alternative reward structures change behavior?

The baseline uses individual incentives with voluntary collective sharing. Different
team/individual reward mixtures and communication mechanisms are later experimental
variants, not features already implemented here. Scripted demo outcomes are not
research findings or evidence of emergent cooperation.

## Run the current frontend locally

Use Node.js 22+ and npm:

```sh
npm install
npm run dev
```

Open the URL printed by Vite. Development and production-preview servers bind to
`127.0.0.1` only, so other devices on the same network cannot connect directly.
Do not override the host with `0.0.0.0` or expose it through a tunnel or reverse proxy.
This project has not been deployed to a hosting service.

Run experiment plays nine predefined rounds. Step advances one round, Pause stops
playback, and Reset returns to identical priors. All agents' supplied movement paths
are visible; selecting an agent or Pool changes the displayed belief. Ground truth
is supplied only at the final demo frame and requires an explicit presenter reveal.

Settings are editable and prefilled with the current values. Apply & reset passes
them to the provider. Custom values require the backend: the scripted provider
rejects them without changing the run. Restore current values discards edits.
Settings are disabled during playback.

### Scripted demo assumptions

- 50×50 grid, four agents, one deposit, 300 credits per agent, 1,000-credit prize.
- Move costs 2 per Manhattan unit; observe 15; drill 100; human 160; joining 5.
  These are fixture values, not settled backend defaults.
- C buys private human advice in round 3 and shares it by joining in round 4.
  C exhausts its budget in round 8 and retains eligibility for D's round-9 discovery.
- Belief maps are hand-authored display swatches, not computed posteriors. Human
  guidance and payouts are scripted. Displayed payouts are rounded to two decimals.
- Coordinates are zero-based, with x increasing right and y increasing down.
- The console is a presenter view, not an agent observation endpoint or human-adviser
  interface. Its visibility into different agents must not be reused by those agents.

## Backend integration

Implement `createBackendSimulationClient` in
`src/simulation/BackendSimulationClient.ts` to return a `SimulationClient`.
This integration layer translates Eduardo's payloads into frontend domain types.
React components must not know about Wolfram types or backend transport details.

Set `VITE_SIMULATION_MODE=backend` in a local `.env` and restart Vite after the adapter
is implemented. The default is `demo`. Unconfigured backend mode reports an error;
it never silently falls back to demo data. Vite environment variables are public
browser configuration, not secret storage.

See [the frontend integration contract](docs/simulation-frontend-contract.md) for
snapshots, control operations, evidence provenance, belief rasters, prize eligibility,
and optional ground-truth data. The actual backend transport is still to be agreed
with Eduardo.

## Checks

```sh
npm run lint
npm run typecheck
npm test
npm run build
```

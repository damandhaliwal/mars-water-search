# Experiment design

This design supersedes the earlier frontend-only, shared-human-advice prototype.
There is no Wolfram dependency and no scripted runtime policy.

## Research question

Under what conditions do Gemini Flash agents choose independent search, AI
collaboration, or costly human information when searching for water under
uncertainty? Each rover maximizes its own final utility: reward minus its costs.
The prompt does not prescribe cooperation, human use, independence, diversity,
or team welfare. None of these behaviors receives an intrinsic bonus.

## World, evidence, and time

The environment is a configurable discrete grid, 50×50 by default, containing one
or two seeded coherent elliptical water fields. W(x,y) is intensity in [0,1]. A
successful drill meets the configurable threshold (default 0.75). This is a search
sandbox, not a geological model. Four rovers start with exactly the same uniform
prior, private evidence, and separate 300-credit budgets.

The displayed belief is a simplified spatial estimate of the chance a drill will
qualify. Log-odds updates spread signed sensor evidence with a Gaussian kernel;
drilling supplies definitive local evidence; human evidence has greater weight.
This is a heuristic belief updater, not a calibrated geostatistical posterior.
It is maintained in Python, never numerically calculated by the LLM or frontend.

Every active rover selects one action using the same start-of-round snapshot.
Only after every proposal has been collected and validated does Python resolve
the round. No rover sees another rover's current-round choice. MOVE does not scan.
Non-LLM randomness is seeded. Live Gemini outputs need not be reproducible even at
temperature zero; generation settings and tool decisions are recorded.

## Actions and irreversible regimes

All agents start PRIVATE. They can choose AI_POOL or HUMAN_ASSISTED, but never both.

| Action | Default cost | Rule |
| --- | ---: | --- |
| MOVE(x,y) | 1 × Manhattan distance | Any different in-bounds cell; no observation. |
| OBSERVE | 10 | Fixed noisy local signal; each rover may scan a cell once. |
| DRILL | 100 | Exact local intensity; may win. |
| JOIN_AI_POOL | 0 | Private only; consumes a round, including at zero budget. |
| CHOOSE_HUMAN | 150 | Private only by default; consumes a round and query. |

No intentional WAIT exists. An agent is inactive only when no affordable legal
action remains, including a valid zero-cost pool transition. A cell's observation
signal is fixed, and rescanning an already-scanned cell is not a legal action,
so rovers must keep moving to gather new evidence. AI_POOL can never
choose human assistance. HUMAN_ASSISTED can never join the pool. With the default
max_human_queries=1, human choice is a single consultation. Increasing that setting
allows further paid queries by already human-assisted agents, without opening pool
access. Human responses never enter the AI pool.

## Pool and prizes

One shared evidence board holds the union of members' historical and subsequent
observations and drill results. Evidence is identified by provenance and replayed
once into a common pool belief. Pool members use that same belief representation.
Joining becomes effective at round end, for decisions in the following round.

There is one 1,000-credit discovery prize. Private and human-assisted winners keep
it. If a pool member wins, it is divided equally among members at the **start of
the winning round**, with no finder bonus. Same-round joiners are excluded. An
inactive established member retains its share. Everyone pays their own costs.

If several drills succeed simultaneously, the highest local intensity wins;
exact ties are settled by a seeded deterministic tie-break independent of action
execution order. All successful drills are logged, but only one prize is paid.
An episode ends on settled discovery, all agents inactive, no agent able to
afford a drill, or max_rounds (100).

## Human information

A coarse adviser prior combines the uniform agent prior with blurred/noisy truth:
agent_prior + human_quality × (blurred_truth − agent_prior) + noise, clipped to
[0,1]. human_quality defaults to 0.5. The blend is an information-quality parameter,
not a measured 50% accuracy improvement. Advice can be wrong.

Simulated mode chooses a bounded recommendation from this imperfect prior.
Interactive mode pauses LangGraph at a checkpointed interrupt. The adviser sees
only the coarse prior and recommends a location/region with an optional short note.
The rover receives only that bounded response, never the adviser map. Multiple
requests are handled sequentially. Costs settle exactly once when the round resolves;
the pending UI shows the consultation commitment. New advice is usable next round.

## Treatments

- FREE_CHOICE: both irreversible choices are available.
- SOLO_ONLY: neither is available.
- AI_COLLAB_AVAILABLE: only the AI pool is available.
- HUMAN_AVAILABLE: only human assistance is available.

## Decision control and measurement

Each rover uses smolagents.ToolCallingAgent with Gemini Flash and only its legal
action tools. Tools construct ActionProposal objects; they cannot mutate the world.
An independent collector accepts at most one action. Invalid/no/multiple tool calls
receive at most two correction retries. A persistent invalid model choice is an
invalid_decision, costs no invented action, and loses the round.

API failures are infrastructure interruptions. The graph checkpoints accepted
decisions and pauses before any action resolves or any budget is charged. The round
counter stays at the last completed round. Explicit resume retries only unfinished
agents against the original round-start views, including across process restarts.
Human requests and charges occur only after decision collection finishes. There is
no fallback policy or mock-model mode. Tests may supply proposals or stub the
network boundary.

Request starts are paced by GEMINI_REQUEST_INTERVAL (one second by default).
Provider errors stop automatic retries; shared cooldowns honor Retry-After, with
60 seconds as the default for rate limits and five seconds for temporary service
or connection failures. The UI stops playback and exposes a manual pending-round
retry when the cooldown expires. Batch runs stop with their checkpoint preserved.
Cooldowns are independent of the simulated rover budgets and mission clock.

Logs retain configuration, seed, evaluator truth/prior, starting positions, agent
views, action arguments, concise reasons, latency/token metadata, failures, outcomes,
budgets, beliefs, pool changes, and final utilities. Decision collection artifacts
in decisions/ retain attempts before a round resolves, including safe HTTP status,
failure category, and retry deadline. They do not retain raw API error bodies or hidden model
reasoning. Evaluator files and presenter state are never used as AgentView inputs.

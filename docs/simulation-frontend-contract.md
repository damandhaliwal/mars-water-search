# Simulation ↔ frontend contract

This is a proposed **presentation boundary**, not Eduardo's backend API. The
backend remains authoritative for world state, actions, costs, beliefs, sharing,
eligibility, human advice, rewards, and termination. No Wolfram-specific types
cross into React. The complete TypeScript shapes are in `src/simulation/types.ts`.

## 1. State snapshots

Supply complete, internally consistent **post-resolution round snapshots**:

- Experiment ID, source (`backend`), status, resolved round, optional round limit.
- Config: dimensions, agent count, starting budget, prize, optionally deposit count.
  Omit deposit count if it is not authorized for this presenter.
- Each agent: ID, label, position, remaining budget, accumulated cost, activity,
  private/pool status, nullable last action, optional drill affordability, optional
  belief raster, supplied movement path.
- Pool membership, prize eligibility, the round that eligibility applies to,
  provider-supplied potential share, supplied evidence board and optional belief.
- Authorized map markers and activity events.
- Optional authoritative winner and payouts or failure reason.
- Optional explicitly authorized presenter-only ground truth.

The UI is a researcher/presenter console. Access to all agents' positions and
beliefs does **not** mean agents or the human adviser may access this endpoint.
Authorization belongs in the backend/transport. Hiding a layer in a browser is
not access control. Never put private credentials or agent tools in this frontend.

## 2. Control operations and lifecycle

`SimulationClient` provides async getExperimentState(), start(), pause(), step(),
reset(), plus subscribe(callback) returning an unsubscribe function and dispose().

- Start resumes execution; repeated starts must not create multiple runners.
- Pause acknowledges a stable boundary. The backend should specify how it handles
  a round already in flight. The UI disables step during running.
- Step resolves exactly one round. No agent decisions are made by the UI.
- Reset returns a coherent initial snapshot; backend decides whether its reset
  reuses the seed or starts a new experiment. Changing experimentId resets map UI.
- Every successful control produces a subscription snapshot, including status-only
  changes. Consumers subscribe before requesting the initial state.
- Adapter must discard stale/out-of-order transport updates (using backend revision
  IDs) and avoid letting a late initial fetch overwrite a newer subscription state.
- Unsubscribe removes listeners. Dispose closes sockets, timers and other resources.
- Surface command errors. Do not imply success or substitute mock results on error.

For long-running connections, agree reconnect/status semantics with Eduardo before
implementation. Add connection status to the contract if needed; never label a
disconnected cached snapshot live. Backend mutations should be idempotent so
network retries cannot duplicate charged actions.

## 3. Events and visibility

ExperimentEvent includes stable id, round, optional actor/action, and summary.
PoolEvent includes stable id, original evidenceId, contributor, kind, acquisition
round, sharing round, optional location, summary and optional confidence.

Evidence kinds: observation, human, drill, location, belief. Keep confidence
semantics in the text: advisor confidence is not automatically P(successful drill).

Order the shared log by sharing round, preserving provider order for ties. Old
evidence shared upon joining retains its original acquisition round and evidenceId.
The adapter/backend de-duplicates forwarded evidence; the UI never chooses which
evidence is relevant, shared, or independent. Future relevant member evidence
automatically appears when the backend supplies it, including human guidance.
Private human responses stay out of the pool until the backend explicitly shares
them. Their costs always remain with the requesting agent.

The recent activity strip is presenter-visible data and must never be reused as
an agent's observation history. Markers and paths likewise require backend
authorization; viewing a marker is not a new sensor reading.

## 4. Belief representation

BeliefGrid is width, height and a flat row-major values array:
`values[y * width + x]`. Length must equal width × height. Values are probabilities
in [0,1]; null means unknown/unavailable, not zero. Coordinates are zero-based,
x increases right, y down. Adapter must translate Wolfram indexing/orientation.

For agent maps, probability means P(W(x,y) >= success threshold | available evidence).
The pool raster is optional and is provided by the backend. The frontend neither
averages agent maps nor computes a posterior. It shows a clear unavailable state
if no raster is supplied. The adapter must validate finite, bounded values and
dimensions; components do not perform statistical repair or inference.

## 5. Membership, eligibility, and payouts

Membership persists. Sharing historical information on joining makes it available
for the next round. Eligibility for a winning round requires inclusion in the
collective belief **at the start of that round**. A same-round join does not qualify.

`eligibleMemberIds` is distinct from memberIds. `eligibilityRound` explicitly says
which round the eligibility list applies to (normally the next round for ongoing
post-round snapshots, the winning round for a final snapshot). Backend supplies
rewardPerMember; the UI does not derive it from current membership.

An exhausted agent cannot act but retains its established prize entitlement. Final
WinnerState includes the winning actor, private/pool status, location, recipients,
prize, per-recipient amount, and reward/cost/utility for every agent. Display these
exact supplied values with presentation rounding only. Simultaneous discoveries
remain a backend policy; do not have the frontend arbitrate them.

## 6. Ground truth

Optional groundTruth includes a water-intensity raster and success threshold.
Intensity is a physical world quantity, not an agent probability. The UI labels
this layer separately and requires explicit reveal. The demo only supplies it
after success. Production may omit it entirely. Do not send seeds, hidden maps,
or generation parameters to any unauthorized client.

## 7. Transport choices and connection point

Implement `createBackendSimulationClient()` in BackendSimulationClient.ts and
select it with VITE_SIMULATION_MODE=backend. React components remain unchanged.

HTTP commands plus SSE snapshots, WebSocket messages, HTTP polling, or a local
Wolfram process bridge are all possible. A polling adapter must expose the same
subscription interface and serialize/discard overlapping responses appropriately.
Do not invent endpoints before agreeing them with Eduardo. Browser clients cannot
directly spawn local processes; a process bridge would live outside this frontend.

This repository intentionally ships no backend transport, world generation,
agent reasoning, sensor model, Bayesian update, reward authority, or live human UI.

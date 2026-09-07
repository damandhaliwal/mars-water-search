# Local simulation ↔ frontend contract

This contract now connects the existing React/Vite frontend to the Python FastAPI
backend. There is no Wolfram or scripted provider. The authoritative backend
schemas are `backend/src/mars_agents/api/schemas.py`; the matching frontend types
are `src/simulation/types.ts`. All JSON fields use camelCase.

## Transport and controls

The frontend adapter is `src/simulation/BackendSimulationClient.ts`. Requests use
`/api`; the Vite server proxies to BACKEND_URL (default http://127.0.0.1:8000).
Both dev and preview bind to 127.0.0.1. No keys are stored in browser configuration.

| Method and route | Operation |
| --- | --- |
| GET /api/health | Health, configured-key boolean, model ID; no key value. |
| GET /api/config | Validated defaults, including advanced parameters. |
| POST /api/experiments | Create seeded state from supplied settings; no model calls. |
| GET /api/experiments/{id} | Latest presenter snapshot. |
| POST /api/experiments/{id}/step | Advance one simultaneous round or pause for human input. |
| POST /api/experiments/{id}/reset | Create a new experiment ID, preserving old checkpoints/logs. |
| GET /api/experiments/{id}/human-requests | Current pending coarse-prior request. |
| POST /api/experiments/{id}/human-responses | Validate requestId, x, y, optional note and resume. |
| GET /api/experiments/{id}/results | Terminal {results, winner} with supplied payouts. |
| POST /api/experiments/{id}/reveal-ground-truth | Explicit presenter intensity map; live in simulated mode, terminal-only in interactive mode. |
| GET /api/experiments/{id}/replay | Every recorded round, oldest first. Read-only checkpoint history; never calls the model, charges budgets, or disturbs the live run. |

Play is a serial loop: request another step only after the previous finishes. Pause
prevents further requests; an already executing round completes. The backend also
rejects concurrent mutating operations on one experiment. Run a single backend
worker; the application is a local research tool, not a multi-worker service.

Missing GEMINI_API_KEY returns an explicit 503 on an attempted step, without
changing the world. Invalid settings/responses return 422; conflicting round
operations return 409; missing experiments return 404. No error path switches to
a substitute policy. The browser may edit requested settings, but displays accepted
backend configuration and never changes budgets, beliefs, membership, or rewards.

## Snapshots and maps

Snapshots contain completed round number, status, accepted config, agent positions,
budgets, regimes, paths, beliefs, recent events, pool board, and optional results.
Statuses are idle, paused, awaiting_human, awaiting_api, success, failure; running playback is
also represented by the frontend's control state.

BeliefGrid = {width, height, values}, row-major index y * width + x. Coordinates are
zero-based, x rightward, y downward. Values are bounded scores interpreted as
simplified drill-success beliefs, not calibrated probabilities. null can represent
unavailable cells in the frontend. The backend supplies the pool belief; the UI
never averages or infers it. Ground-truth water intensity is a distinct quantity.

Initial prior uses the accepted config's priorProbability, constant over the grid.
Beliefs default to a clearly labeled min/max color scale; the fixed 0–1 scale is
selectable. Uniform priors have no preferred target. The crosshair marks the first
highest-scoring cell if tied; it does not represent an agent's planned action.
Marker values are measured scan signals or exact drill intensities. Water view
uses a fixed 0–1 scale and outlines all cells meeting successThreshold.
A revealed simulated-run water map persists across rounds but clears on reset.
Interactive human mode blocks revelation until termination, including before an
adviser interruption; the adviser view continues to replace the presenter DOM.

Agent regimes are private, ai_pool, human_assisted. Actions are move, observe, drill,
join_ai_pool, choose_human. A persistently invalid model choice is an invalid_decision
event, not a WAIT action. Provider failures pause the pending round without a rover action. Pool and human membership cannot be combined. Low budget and
inactivity are distinct: a zero-budget private agent may still join a free pool.

## Sharing, eligibility, and outputs

Pool events retain source agent, original evidence ID, acquisition round, and
sharing round. Historical evidence is contributed upon joining and future member
evidence is automatic. No human evidence is shared. Members use the backend pool
belief; a private agent has no access to its contents.

Member IDs and eligible IDs remain separate fields. During an ongoing episode,
eligibilityRound normally denotes the upcoming round. At termination it denotes
the resolved round; same-round joiners are absent from its eligible set. Final
payouts are authoritative and include reward, individual cost, utility, and regime.
The frontend only rounds numbers for display.

## Human interruption

LangGraph prepares requests without charging and interrupts before resolution.
Each request has a stable ID, requesting agent, round, committed cost, coarse prior,
and full-world dimensions. The adviser overlay shows only this coarse prior and
obscures the mission view. The selection maps to world coordinates; the server
derives its confidence from the coarse cell, not caller-provided confidence.

A response resumes the same graph checkpoint. Multiple pending requests are
presented sequentially. Graph-node replay has no side effects before interrupt;
costs and evidence settle once after all responses are valid. Advice becomes usable
in the next round and remains private forever. Simulated advice uses the same
imperfect prior and bypasses only the user interaction, not the cost/regime rules.

## Information boundaries

Full presenter state is not an AgentView. The backend separately constructs each
model's compact allowlist: its position/budget/costs, legal actions, concise own
history, belief summary, and authorized pool or bounded human evidence. No model
receives world truth, adviser raster, other private evidence, or current-round
proposals. The human-request endpoint never contains truth. The ordinary state
endpoint contains no truth, even after termination; revealing requires a separate
request. Local evaluator logs and checkpoints are privileged and are not served
as browser assets.

These controls assume a trusted local experimenter. The local server does not
provide multi-user authentication; do not expose it on a network or give agents
HTTP tools that can reach presenter/evaluator endpoints.

## API interruptions

GET and Step snapshots use status=awaiting_api and providerFailure containing
message, agentIds, retryAt (Unix seconds, optional), and failures with agentId,
category, and optional httpStatus. Categories distinguish rate limits, quota
exhaustion, service outages, timeouts, connection errors, and rejected requests.
The message is assembled from safe fields; raw provider errors are never returned.

The completed round, positions, budgets, and events remain unchanged. Playback
stops. After retryAt, the user can retry the pending round with the existing Step
endpoint. A premature Step returns the same pause without calling Gemini. Accepted
proposals remain checkpointed; only unfinished agents are requested again. A
successful resume clears providerFailure and may proceed to a human interruption.
Refreshing or restarting the backend preserves the pending round.

# Local setup handoff and verification

## What is ready

The Python environment and frontend dependencies have been installed. Both services
run locally and bind only to 127.0.0.1. The simulation, Gemini/smolagents decision
boundary, LangGraph checkpoints and human interrupts, API, frontend, scientific
logs, and batch runner are implemented. Runtime scripted data and alternate rover
policies were removed.

## What you still need to do

No GEMINI_API_KEY was present during implementation. No live Gemini calls were
made, and live strategic behavior is not verified yet.

1. Obtain/enable a Gemini API key and quota for your Google project through
   [Google AI Studio](https://aistudio.google.com/api-keys).
2. From the repository root, copy `.env.example` to `.env` if you have not already
   created it. Do not overwrite an existing key file.
3. Set GEMINI_API_KEY in that local file. GEMINI_MODEL defaults to
   `gemini-3.8-flash`; all rovers use the same configurable Gemini Flash ID.
4. Restart the backend to pick up the key. Leave the browser/HTTP server on localhost.
5. Run the opt-in live test, then create and run an experiment in the UI. Running
   agents or batch experiments consumes Gemini API quota.

```sh
# Terminal 1, from the repository root
cd backend
uv sync --locked
uv run uvicorn mars_agents.api.main:app --host 127.0.0.1 --port 8000
```

```sh
# Terminal 2, from the repository root
npm ci
npm run dev
```

```sh
# Explicit live check, from backend/ after configuring your key
uv run pytest -m gemini tests/test_gemini.py
```

```sh
# Small real-Gemini batch, from backend/ after configuring your key
uv run python -m mars_agents.experiments.batch --episodes 2 --seed 42 \
  --agents 4 --treatment free_choice --human-mode simulated \
  --model gemini-3.8-flash --output ../data/live-batch
```

To cap initial API usage, put `{"maxRounds": 3}` in a local configuration JSON file
and pass `--config path/to/file.json`. The live test itself is bounded to three
rounds. An authentication/model-access failure is recorded or reported explicitly,
never replaced with a heuristic or another model.

## Verification completed without a key

- All 120 non-network backend tests passed. These cover deterministic world and
  budgets, noisy sensing, exclusive regimes, historical pool sharing, same-round
  prize eligibility, inactive contributors, ties, information leakage, smolagents
  dispatch/retries/concurrency, persisted human interrupts, API, and batch output.
- Backend Ruff passed. Mypy passed across 34 source files.
- Frontend lint, TypeScript checking, 19 adapter/component tests, and production
  build passed.
- Five browser tests passed: four controlled HTTP-fixture UI tests plus one against
  the actual local backend for creation, editable settings, reset, paths, and the
  missing-key boundary. Desktop, adviser, final-result and mobile screenshots were
  inspected; no horizontal overflow or clipping remained.
- The real-Gemini pytest marker was exercised and **skipped** because the key is
  absent. This is not a live-model success.
- Real HTTP health responses from both port 8000 and the port-5173 proxy confirmed
  `geminiConfigured: false`. Local listening sockets were verified at 127.0.0.1.
- The actual batch CLI was attempted without a key; it exited clearly with the
  required-key message and did not create substitute episode results.

A third-party Starlette/AnyIO deprecation warning is emitted by TestClient; it does
not fail tests. No test requires hidden model reasoning.

## What the test episodes mean

The complete four-rover API episode and batch artifact tests stub only the HTTP
client response. Actual smolagents ToolCallingAgent dispatch, validation, LangGraph
nodes, world resolution, and logging still run. Human workflow tests inject explicit
ActionProposals at the graph collection boundary. Neither mechanism is exposed as
an application mode or selectable policy.

Retained verification artifacts are under `data/verification/pytest/`, including
`test_batch_artifacts_with_netw0/episode_summary.csv`, `events.jsonl`, configuration,
and per-episode files. They are **test fixtures, not research results**. This folder
and all evaluator data are excluded from Git.

To reproduce and retain the non-network outputs:

```sh
cd backend
mkdir -p ../data/verification
uv run pytest --basetemp ../data/verification/pytest
```

## Intentional implementation choices

- Preserve the existing root React/Vite frontend rather than relocate it into a
  new Next.js scaffold. Backend code lives in `backend/`.
- smolagents 1.26.0 needs a guarded single-step hook because `run(max_steps=1)` can
  otherwise issue an extra final-answer model request. The integration still uses
  the real ToolCallingAgent dispatch and OpenAIModel-compatible Gemini endpoint.
- A single Python resolver owns costs, beliefs, pool updates, and rewards atomically;
  LangGraph orchestrates the lifecycle around it. There are no superficial graph
  nodes pretending to perform those domain calculations independently.
- Human costs settle once after all responses, with a commitment shown while paused.
  There are no pre-interrupt charges to duplicate when LangGraph resumes a node.
- `max_human_queries > 1` permits repeat paid advice only in HUMAN_ASSISTED; the
  irreversible exclusion from AI_POOL remains. Default is one consultation.
- Observation and human belief updates are explicit spatial heuristics, not calibrated
  Bayesian inference. Generator sanity tests establish limited synthetic behavior,
  not live LLM performance or a guarantee that human advice always wins.
- Reset creates a new ID and preserves the old run's logs/checkpoint for inspection.
- This is a trusted local, single-worker application. It does not implement public
  multi-user authentication or hosting, and should not be exposed to a network.


## Browser checks

With the local backend running and Google Chrome installed:

```sh
# From the repository root
npm run test:browser
```

The `network-fixtures` project tests adviser and outcome UI with explicit HTTP
fixtures. The `local-backend` project uses the real local API for creation/reset
and missing-key behavior; it skips its missing-key check when a key is configured
and never initiates Gemini calls. Tests use the installed Chrome browser; Chrome
is a test-only prerequisite, not a requirement for using the app in another browser.
Screenshots from verification are in `/tmp/mars-live-backend.png`,
`/tmp/mars-human-advisor.png`, `/tmp/mars-final-results.png`, and
`/tmp/mars-mobile-success.png`.

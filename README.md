# Mars Water Search

A local experiment in how Gemini Flash rovers choose independent exploration,
AI collaboration, or costly human guidance while searching for underground water.
Each rover maximizes **its own reward minus its own costs**.

The Python backend owns the environment, beliefs, resources, and prizes.
[smolagents ToolCallingAgent](https://huggingface.co/docs/smolagents/en/reference/agents)
collects one Gemini tool decision per rover. A
[LangGraph StateGraph](https://docs.langchain.com/oss/python/langgraph/interrupts)
orchestrates the simultaneous rounds and durable human interruptions. FastAPI
connects this engine to the existing React/TypeScript mission view.

**Gemini Flash is the only rover policy. There is no mock-model mode, fallback
policy, or Wolfram dependency.** The real demo requires a Gemini API key. Tests of
domain rules and network boundaries can run without credentials.

## Current experiment

- Default: 50×50 grid, one coherent hidden water deposit, four rovers, 300 credits
  each, a 1,000-credit prize, and up to 100 rounds.
- All agents start PRIVATE with the same prior. AI_POOL and HUMAN_ASSISTED are
  irreversible, mutually exclusive choices. Human advice remains private forever.
- MOVE, OBSERVE, DRILL, JOIN_AI_POOL, and CHOOSE_HUMAN each consume one round.
  No WAIT action exists. Movement costs Manhattan distance and reveals no evidence.
- A zero-budget private rover may join the zero-cost pool. Joining shares previous
  observations; subsequent evidence automatically enters the board.
- Pool reward eligibility is determined before the winning round. Inactive existing
  members retain their shares; same-round joiners do not receive the prize.
- A private/human winner keeps the prize. An AI-pool winner splits it equally with
  eligible members. Simultaneous discoveries use highest intensity, then seeded ties.
- Simulated and interactive human modes provide a bounded recommendation from a
  better but imperfect coarse prior. Neither gives a rover the adviser map or truth.
- Four treatments: free choice, solo only, AI collaboration available, human available.

Read the [complete experiment design](docs/experiment-design.md) for semantics and
belief-model limitations. These rules replace the earlier shared-human-advice demo.

## Setup

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 22+, npm.
Dependencies are pinned and locked in `backend/pyproject.toml`, `backend/uv.lock`,
and `package-lock.json`.

From the repository root:

```sh
cp .env.example .env
```

Edit `.env` yourself and set:

```dotenv
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-3.8-flash
GEMINI_TEMPERATURE=0
GEMINI_MAX_CONCURRENCY=4
GEMINI_REQUEST_INTERVAL=1
```

Obtain a key through [Google AI Studio](https://aistudio.google.com/api-keys), enable
API access for your project, and ensure its quota/billing permits the selected model.
The default model is listed in [Google's model catalog](https://ai.google.dev/gemini-api/docs/models).
The model ID can be changed to an available Gemini Flash ID; other providers are
not supported. The key stays server-side and must never be committed or prefixed
with `VITE_`. Ordinary setup and tests do not incur Gemini calls; running an
experiment, batch, or explicitly marked integration test does.

API errors pause the pending round and preserve accepted decisions. The UI shows
its error category and a manual retry after the cooldown; no rover loses a turn
or spends credits because the API failed. Request starts are spaced by
`GEMINI_REQUEST_INTERVAL` seconds. `GEMINI_RETRIES` applies to invalid model
choices, not API outages. Batch execution stops with a resumable checkpoint on
provider failure.

Terminal 1, from the repository root:

```sh
cd backend
uv sync --locked
uv run uvicorn mars_agents.api.main:app --host 127.0.0.1 --port 8000
```

Terminal 2, from the repository root (the existing frontend stays here):

```sh
npm ci
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). Both services bind only to
loopback. Other devices on the network cannot connect directly. Do not expose
these research endpoints with a tunnel, reverse proxy, or `--host 0.0.0.0`.
No hosting deployment is configured. The Vite proxy uses BACKEND_URL, defaulting
to http://127.0.0.1:8000, for `/api` requests.

## Live demo

1. Create a seeded four-agent experiment using the prefilled settings.
2. Choose simulated human mode for uninterrupted runs, or interactive for a live adviser.
3. Step or Play; every rover decision is made by Gemini Flash. Pause waits for the
   current round request to finish and prevents another from starting.
4. Select agent beliefs or the pool belief. All supplied rover paths remain visible.
5. If a rover chooses human assistance in interactive mode, select a region in the
   adviser overlay and submit. LangGraph resumes the same round; multiple requests
   appear sequentially. No real water map is shown to the adviser.
6. Continue to success, budget exhaustion, or the round limit.
7. Inspect rewards, costs, and utilities. Explicitly reveal truth after termination.

If GEMINI_API_KEY is missing, creation and inspection work but stepping fails clearly.
No scripted data or alternative model is substituted. See
[remaining local setup and verification](docs/setup-and-verification.md).

## Batch experiments

From `backend/`, with a configured key:

```sh
uv run python -m mars_agents.experiments.batch --episodes 3 --seed 42 \
  --agents 4 --treatment free_choice --human-mode simulated \
  --model gemini-3.8-flash --output ../data/batch
```

Use `--config path/to/config.json` for additional parameters. Interactive human mode
is not supported by batch execution. Logs include each episode's config, round
JSONL, terminal summary, and an aggregate `episode_summary.csv`. These contain
privileged evaluator data and are excluded from Git.

## Verification

From `backend/` (no model calls):

```sh
uv run ruff check .
uv run mypy src
uv run pytest
```

Explicit real-model checks, requiring a key and consuming API quota:

```sh
uv run pytest -m gemini
```

From the repository root:

```sh
npm run lint
npm run typecheck
npm test
npm run build
```

## Source layout and interfaces

- `backend/src/mars_agents/environment`, `domain`, `beliefs`: seeded world, rules,
  allowlisted AgentView, and replaceable spatial belief updates.
- `backend/src/mars_agents/agents`: Gemini configuration, proposal tools, bounded
  retries, and concurrent smolagents decisions.
- `backend/src/mars_agents/orchestration`: LangGraph round lifecycle and SQLite
  interrupt/resume checkpoints keyed by experiment ID.
- `backend/src/mars_agents/experiments`: service, JSONL/CSV logging, batch CLI.
- `backend/src/mars_agents/api`: typed FastAPI presenter endpoints.
- `src/simulation/BackendSimulationClient.ts`: the only frontend transport boundary.
- `src/components`: existing mission layout, belief map, pool board, and adviser UI.

The [frontend contract](docs/simulation-frontend-contract.md) describes visibility and
transport. Normal state never includes truth. Full presenter state is not an agent
observation endpoint. Model prompts use a distinct allowlist with compact belief
summaries; private agents cannot read others' evidence, and no rover sees the human
prior. Only concise decision reasons and final tool metadata are retained, not hidden
chain-of-thought. LangGraph checkpoints and evaluator logs stay on the local machine.

# Mars Water Search

**An interactive experiment in how AI agents search, spend, and decide whether to collaborate under uncertainty.**

Built at [Sundai Club’s Wolfram Hack in Boston](https://www.sundai.club/events/boston/wolfram-hack).

Four Gemini-powered rovers explore a synthetic Martian landscape containing a hidden water deposit. Each rover has its own budget and chooses between searching independently, sharing evidence in an AI pool, or buying private human guidance. Observations are noisy, movement and drilling cost credits, and there is one discovery prize. Each rover is prompted to maximize **its own reward minus its own costs**.

The application combines a React mission interface with a Python simulation, real Gemini tool calls through smolagents, and a LangGraph workflow for simultaneous rounds and resumable interruptions. Python owns the world and enforces the rules; the language models choose actions.

This is a hackathon research prototype using synthetic data, not a geological model or a validated benchmark of optimal agent behavior. The implementation has no Wolfram runtime dependency despite its event provenance. Gemini Flash is the only runtime rover policy: there is no selectable mock mode or heuristic fallback.

## Contents

- [What to look at first](#what-to-look-at-first)
- [Quick start](#quick-start)
- [Using the interface](#using-the-interface)
- [Experiment rules and economics](#experiment-rules-and-economics)
- [Signals, beliefs, and water](#signals-beliefs-and-water)
- [How the rovers decide](#how-the-rovers-decide)
- [Architecture and round lifecycle](#architecture-and-round-lifecycle)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [Batch experiments and recorded data](#batch-experiments-and-recorded-data)
- [Testing and verification](#testing-and-verification)
- [Limitations and interpretation](#limitations-and-interpretation)
- [Troubleshooting](#troubleshooting)
- [Repository guide](#repository-guide)

## What to look at first

For a product walkthrough, start the app, create a seeded experiment, and step through a few rounds. Compare each rover’s concise action reason, budget, path, and evidence with the presenter-only water map. Then inspect how joining a pool changes information access and potential payouts.

For a code review, these are the main entry points:

| Review question | Entry point |
| --- | --- |
| What does the model know, and what is hidden? | [Agent view construction](backend/src/mars_agents/beliefs/views.py), [search context](backend/src/mars_agents/beliefs/search.py) |
| What strategy is the model instructed to use? | [Search prompt](backend/src/mars_agents/agents/prompts.py), [economic prompt and arithmetic](backend/src/mars_agents/agents/economics.py) |
| Who validates actions and pays the prize? | [Action rules](backend/src/mars_agents/domain/actions.py), [world resolver](backend/src/mars_agents/environment/world.py) |
| How do simultaneous decisions and interruptions work? | [Round graph](backend/src/mars_agents/orchestration/graph.py), [experiment service](backend/src/mars_agents/experiments/service.py) |
| How does the interface avoid becoming a second simulation? | [Frontend transport adapter](src/simulation/BackendSimulationClient.ts), [presenter](backend/src/mars_agents/api/presenter.py) |
| What is tested without calling an LLM? | [Backend tests](backend/tests), [frontend tests](src/App.test.tsx), [map tests](src/components/MarsGrid.test.tsx) |

## Quick start

### Requirements

- Python **3.12 or later** and [uv](https://docs.astral.sh/uv/).
- Node.js **22 or later** and npm.
- A Gemini API key and access to a Gemini Flash model for live rover decisions.
- Two terminals: one for the Python API and one for Vite.

Python dependencies are pinned in [backend/pyproject.toml](backend/pyproject.toml) and locked in [backend/uv.lock](backend/uv.lock). Frontend dependencies are pinned in [package.json](package.json) and [package-lock.json](package-lock.json).

### 1. Clone and configure

```sh
git clone https://github.com/damandhaliwal/mars-water-search.git
cd mars-water-search
cp -n .env.example .env
```

Edit the repository-root `.env`. The copy command preserves an existing file.

```dotenv
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-3.8-flash
GEMINI_TEMPERATURE=0
GEMINI_MAX_CONCURRENCY=4
GEMINI_REQUEST_INTERVAL=1
GEMINI_TIMEOUT=45
GEMINI_RETRIES=2
MARS_DATA_DIR=../data
BACKEND_URL=http://127.0.0.1:8000
```

`gemini-3.8-flash` is the **repository’s configured default**, not a guarantee of availability in your Google project. Set `GEMINI_MODEL` to a Gemini Flash identifier your project can access. The UI header displays the backend’s configured model. See [Google AI Studio](https://aistudio.google.com/api-keys) for credentials and [Google’s model documentation](https://ai.google.dev/gemini-api/docs/models) for model availability.

The key stays on the backend. Do not prefix it with `VITE_`, put it in source code, or commit `.env`. Environment variables take precedence over the root `.env`; restart the backend after changing provider settings.

**Creating and inspecting an experiment does not call Gemini. Play, Step, live-model tests, and batch runs do consume API quota and may incur charges.** Experiment credits are simulated resources and are unrelated to the provider’s API bill. A short round limit limits work, but is not a monetary spending cap.

### 2. Start the backend

In terminal 1, from the repository root:

```sh
cd backend
uv sync --locked
uv run uvicorn mars_agents.api.main:app --host 127.0.0.1 --port 8000
```

Run a single backend worker. SQLite checkpoints and per-experiment process locks support this local workflow; it is not configured as a multi-worker service.

### 3. Start the frontend

In terminal 2, from the repository root:

```sh
npm ci
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). Vite forwards `/api` requests to the backend on port 8000. FastAPI’s interactive API documentation is at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

Without a key, you can still create a world, inspect its initial state, and use permitted presenter views. Attempting a live step reports the missing configuration rather than inventing a rover decision.

Both services bind to loopback. The app assumes a trusted local experimenter and has no public multi-user authentication. Public deployment, tunnels, and network exposure are outside its current design.

## Using the interface

1. **Choose settings and create a run.** A fresh UI form suggests a random seed; use the dice button for another seed or enter a fixed value to reproduce a world. Creation generates the world and initial priors; the first model decision happens only when you select Play or Step. Simulated adviser mode is the simplest way to run without human interruptions.
2. **Step one round** to inspect decisions individually, or **Play** to advance serially. **Pause** prevents the next request; an already executing round can finish.
3. **Select A, B, C, D, or Pool** to inspect the corresponding belief map. Private beliefs can diverge; established pool members use the same pooled belief.
4. **Select Initial prior** to see the common starting score. The default is 0.100 everywhere, so this view intentionally has no preferred target.
5. **Compare the numeric range and legend.** Enhanced belief contrast maps the displayed minimum and maximum to the color ramp. Disable it for a fixed 0–1 scale. Equal colors across different enhanced views need not represent equal scores.
6. **Inspect paths and markers.** Paths can be hidden; the selected rover’s path is emphasized. Observation circles and dry-drill crosses are evidence locations. The belief crosshair marks the first highest-scoring cell if tied, not a rover’s planned destination or confirmed water.
7. **Reveal truth** to inspect actual water intensity, the peak coordinate, and the outlined cells where drilling meets the success threshold. Water uses a fixed 0–1 scale. Revelation is explicit and presenter-only: simulated-adviser runs allow it during play, while interactive-adviser runs block it until termination.
8. **Handle human requests if needed.** In interactive mode, the presenter interface is replaced by an adviser overlay containing only the coarse human prior. Select a region and submit a bounded recommendation. Multiple requests appear sequentially.
9. **Inspect results and replay.** Final tables report backend-settled rewards, costs, and utilities. Recorded replay reads checkpoint history and makes no model calls.

**Reset creates a new experiment ID** and preserves the previous run’s local records. Existing runs retain the configuration with which they were created. In particular, resetting from an older run can retain its older noise setting; loading a fresh page and creating a run uses current backend defaults. The browser is not an experiment-library interface: page reloads do not automatically reopen the previously selected experiment, although its backend checkpoints remain available by ID.

## Experiment rules and economics

### Default scenario

| Parameter | Default |
| --- | ---: |
| Grid | 50 × 50 cells |
| Hidden deposits | 1 |
| Rovers | 4 |
| Seed | API/CLI default 42; a fresh UI form suggests a random seed |
| Starting budget per rover | 300 credits |
| Single discovery prize | 1,000 credits |
| Maximum rounds | 100 |
| Successful drill intensity | At least 0.75 |
| Initial belief score | 0.10 at every cell |
| Sensor noise standard deviation | 0.05; hidden from rover inputs |
| Human mode | Simulated |
| Treatment | Free choice |

### Actions

Every accepted action consumes one round. All active rovers decide from the start-of-round state before any action is resolved.

| Action | Default cost | Effect |
| --- | ---: | --- |
| `MOVE(x, y)` | Manhattan distance × 1 | Moves to a different in-bounds cell. Movement provides no new observation. |
| `OBSERVE` | 10 | Measures the noisy signal at the current cell. The same rover cannot rescan a cell it has already observed. |
| `DRILL` | 100 | Reveals exact water intensity at the current cell. A qualifying drill may win the prize. |
| `JOIN_AI_POOL` | 0 | Irreversible private-to-pool transition; contributes historical evidence and enables subsequent sharing. |
| `CHOOSE_HUMAN` | 150 | Purchases bounded private guidance and enters human-assisted status. |

There is no intentional `WAIT` action. An action must be legal and affordable, but legality alone does not imply good strategy. For example, a rover can legally spend so much on movement that it cannot subsequently drill. Preserving a drilling reserve is a prompt instruction, not a hard spending restriction.

Repeated drilling is discouraged by the prompt, not prohibited by the domain action validator. Observations are fixed per coordinate: another rover’s scan of the same cell is not independent information. The belief updater and search summary deduplicate repeated cell observations even if multiple agents acquired them.

### Information regimes and prize sharing

All rovers begin **PRIVATE**. Two mutually exclusive, irreversible branches are available when the treatment permits them:

| Regime | Accessible evidence | Prize entitlement |
| --- | --- | --- |
| PRIVATE | Own observations and drills | Full prize if this rover wins |
| AI_POOL | Pooled observations and drills, including members’ historical evidence | Equal share if an eligible pool member wins |
| HUMAN_ASSISTED | Own evidence plus bounded private human recommendations | Full prize if this rover wins |

Joining takes effect for next-round decisions. Pool prize eligibility is determined at the **start of the winning round**. Joining in the same round that the pool wins earns no share of that prize. An inactive established member retains its entitlement. The rover performing the winning pool drill receives no finder bonus.

For a four-member eligible pool, a discovery pays 250 credits per member. A member who personally spent 120 credits finishes with utility 130; another member who spent 40 finishes with utility 210. Each member’s costs remain individual.

If several drills qualify simultaneously, the highest true intensity wins. Exact ties use seeded tie-breaking. Only one prize is paid. The experiment ends on discovery, all agents becoming inactive, no agent being able to afford a drill, or the round limit.

### Human advice and treatments

The adviser receives a coarse, imperfect prior derived from the synthetic world. The rover receives only a recommended location, its confidence, and an optional short note—not the map. Human advice never enters the AI pool.

`humanQuality` controls how the adviser’s map blends the uniform prior toward the blurred field. **A value of 0.5 is a blend parameter, not proof of a 50% accuracy improvement.** Guidance can be wrong. At the reduced default sensor noise, local readings outperform the coarse human estimate on the existing fixed-location accuracy test; human advice still offers regional coverage without visiting every cell.

The default allows one consultation. Raising `maxHumanQueries` permits additional paid queries by an already human-assisted rover; it does not restore access to the pool.

| Treatment | Pool available? | Human advice available? |
| --- | --- | --- |
| `free_choice` | Yes | Yes |
| `solo_only` | No | No |
| `ai_collab_available` | Yes | No |
| `human_available` | No | Yes |

## Signals, beliefs, and water

The application deliberately separates three quantities:

| Quantity | Meaning | Who sees it? |
| --- | --- | --- |
| Water intensity | The true synthetic field, bounded by 0 and 1 | Evaluator; presenter on explicit reveal; rover only at a drilled cell |
| Observation signal | Blurred water field plus fixed cell-specific noise, clipped to [0, 1] | Rover after observing; authorized pool members after sharing |
| Belief score | A spatial heuristic updated from available evidence | Corresponding rover or pool; presenter |

Conceptually, the sensor computes:

```text
observation(x, y) = clip(blurred_water(x, y) + fixed_noise(x, y), 0, 1)
```

The default noise standard deviation was reduced from 0.25 to **0.05** to make spatial trends easier to follow. Rovers are told that observations are noisy and that repeats are not independent. They are given neither the configured noise magnitude nor the individual noise draws. This withholds simulation parameters; it does not prove that a model could never estimate noise statistically from its observations.

The same seed, coordinate, and sensor configuration reproduce the same reading. Changing noise changes sensor evidence, not the water deposit. Old recorded runs retain their original settings and readings.

The belief updater spreads evidence through spatial log-odds adjustments. It is **not a calibrated Bayesian posterior**. In particular, its observation update is signed around a signal of 0.5, so a relatively useful reading below 0.5 can lower the belief and leave untouched cells ranked above it. The search prompt explicitly tells agents to compare measured readings rather than blindly chase those belief rankings. This limitation remains in the implementation.

A dry drill means the intensity is below the success threshold, not necessarily zero. An exact reading of 0.70 with a 0.75 threshold is a potentially useful local lead. An exact zero weakens a previously high noisy scan. A dry cell does not establish that its entire neighborhood is empty.

## How the rovers decide

Each decision is a single tool call from Gemini, with a concise reason. The backend constructs three layers of input:

1. **Search procedure** in [prompts.py](backend/src/mars_agents/agents/prompts.py).
2. **Economic decision sheet and current action costs** in [economics.py](backend/src/mars_agents/agents/economics.py), rendered using the actual experiment configuration and rover budget.
3. **Authorized state** from [views.py](backend/src/mars_agents/beliefs/views.py), including bounded evidence, coarse belief summaries, candidates, and local-search context.

The search procedure encourages:

- Cautious **gradient ascent** toward stronger measured signals, usually through short 1–3-cell probes when there is a promising lead.
- Comparing distinct neighboring samples before inferring a direction; small isolated changes may be noise.
- Refining around positive subthreshold drills and discounting zero-intensity contradictions.
- Keeping enough resources to move, gather useful evidence, and drill.
- **Changing strategy after three unproductive distinct nearby sampled points.** Moves, rescans, and observation-plus-drilling at the same coordinate do not count as extra points. The rover should leave that neighborhood with a larger affordable leap or reconsider a legal assistance option. Roughly 5–10 cells is an illustrative leap, not a required distance.
- Continuing productive gradients even after three samples; the stopping rule is for unproductive local search.
- Using complementary pool probes and considering members’ positions and budgets, without assuming knowledge of simultaneous choices.

The local-search context retains up to three strongest positive scan readings and three strongest positive drill readings across authorized history, even if they have aged out of the recent-evidence window. It supplies nearby measurements, exact drill contradictions, untested local probes, and travel/observation/drilling budget arithmetic. Pool member resources appear only for pooled rovers.

These are **instructions and decision support, not an enforced optimizer**. There is no hard-coded gradient action selector or automatic three-point escape controller. The model can still choose poorly, misinterpret evidence, or violate a strategic instruction while returning a technically legal action. Prompt improvements require live comparative evaluation to establish better performance.

The model receives no seed, water raster, adviser raster, private peer evidence, or presenter endpoint tools. Its memory is reset between decisions; continuity comes from the explicit state summaries. Hidden reasoning transcripts are not retained.

## Architecture and round lifecycle

| Layer | Responsibility |
| --- | --- |
| React + TypeScript + Vite | Mission controls, map layers, agents, event log, human overlay, replay |
| Frontend simulation client | HTTP transport, serial playback, state acceptance, errors, replay controls |
| FastAPI presenter | Typed, camelCase responses; separate presenter and adviser boundaries |
| Experiment service | Per-experiment locks, checkpoint access, step/resume/reset operations |
| LangGraph | Round lifecycle, provider pauses, durable human interrupts |
| smolagents + Gemini adapter | One legal tool decision per rover attempt; bounded invalid-choice retries |
| Python domain resolver | Costs, movement, observations, beliefs, memberships, termination, payouts |
| SQLite + JSON/CSV logs | Durable state and inspectable experiment records |

A normal round proceeds as follows:

```text
Prepare authorized start-of-round views
  → Collect Gemini decisions concurrently, with paced request starts
  → Record decisions and validate actions
  → Prepare and obtain any human recommendations
  → Resolve actions, costs, beliefs, pool state, and rewards in Python
  → Record the round and check termination
```

A provider failure interrupts before resolution and preserves accepted decisions. Explicit retry requests only unfinished decisions against the same round-start snapshot. A human request interrupts after action collection; human costs settle once when the round resolves. Interrupting or replaying a workflow node does not itself charge the budget.

The Gemini adapter uses Google’s OpenAI-compatible endpoint through smolagents’ `OpenAIModel` integration. It does not use OpenAI as a second model provider. Transport retries are disabled. `GEMINI_RETRIES` controls up to two corrective attempts for invalid model choices; it is not an outage retry loop. A persistently invalid decision is recorded, spends no invented action cost, and loses that rover’s opportunity in the resolved round.

Provider failures—including rate limits, quota exhaustion, unavailable service, timeouts, and rejected requests—pause the pending round and stop playback. The UI shows safe error metadata and manual retry timing. Raw provider errors and credentials are not returned to the browser.

## Configuration

The authoritative schema is [ExperimentConfig](backend/src/mars_agents/config.py). It accepts snake_case or camelCase inputs and emits camelCase configuration. Unknown fields and invalid values are rejected. The UI exposes common parameters and preserves accepted advanced settings.

### Experiment parameters

| JSON field | Default | Purpose |
| --- | ---: | --- |
| `seed` | 42 | Synthetic world, fixed observations, starts, seeded ties |
| `gridWidth`, `gridHeight` | 50, 50 | Grid dimensions; each supports 1–256 |
| `numberOfAgents` | 4 | 1–64; cannot exceed cell count |
| `numberOfWaterDeposits` | 1 | One or two deposits |
| `startingBudget`, `discoveryReward` | 300, 1000 | Individual resource budget and single prize |
| `moveCostPerCell`, `observeCost`, `drillCost` | 1, 10, 100 | Action costs |
| `joinPoolCost`, `humanCost` | 0, 150 | Assistance transition/consultation costs |
| `maxRounds`, `maxHumanQueries` | 100, 1 | Episode and consultation limits |
| `waterSuccessThreshold`, `priorProbability` | 0.75, 0.10 | Winning intensity and initial belief |
| `observationNoise`, `observationBlurSigma` | 0.05, 2 | Sensor noise and blur; not disclosed in rover state |
| `humanQuality`, `humanNoise`, `humanBlurSigma` | 0.5, 0.03, 2 | Coarse adviser information construction |
| `humanCoarseSize` | 8 | Coarse adviser grid size, bounded by world dimensions |
| `waterRadiusMin`, `waterRadiusMax` | 0.05, 0.12 | Deposit spread relative to grid dimensions |
| `beliefKernelRadius` | 3 | Spatial evidence propagation scale |
| `observationWeight`, `drillWeight`, `humanWeight` | 2.5, 6, 5 | Heuristic evidence weights |
| `beliefSummarySize`, `topCandidateCount`, `recentEvidenceLimit` | 5, 8, 12 | Model-context bounds |
| `humanMode`, `treatment` | `simulated`, `free_choice` | Adviser workflow and available regimes |

Changing a default affects newly created configurations. It does not rewrite historical observations, migrate existing episodes, or guarantee that Reset from an old configuration adopts new defaults. Use a fresh configuration for comparisons after changing sensor settings or prompts.

### Provider and runtime settings

| Environment variable | Default | Meaning |
| --- | --- | --- |
| `GEMINI_API_KEY` | Unset | Server-side credential required for decisions |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Configurable Gemini Flash model ID |
| `GEMINI_TEMPERATURE` | 0 | Sampling temperature; does not guarantee deterministic model output |
| `GEMINI_MAX_CONCURRENCY` | 4 | Maximum concurrent model requests |
| `GEMINI_REQUEST_INTERVAL` | 1 second | Minimum spacing between request starts |
| `GEMINI_TIMEOUT` | 45 seconds | Request timeout |
| `GEMINI_RETRIES` | 2 | Additional invalid-choice corrections, maximum two |
| `MARS_DATA_DIR` | Repository `data/` | API persistence root; relative values resolve from `backend/` |
| `BACKEND_URL` | `http://127.0.0.1:8000` | Vite API proxy destination |

## API reference

All experiment routes below are relative to `http://127.0.0.1:8000`. The normal presenter response is not a rover observation API.

| Method | Route | Behavior |
| --- | --- | --- |
| GET | `/api/health` | Status, configured-key boolean, model ID |
| GET | `/api/config` | Current validated defaults |
| POST | `/api/experiments` | Create a seeded experiment; no model call |
| GET | `/api/experiments/{id}` | Current presenter snapshot |
| POST | `/api/experiments/{id}/step` | Advance or resume a round; can call Gemini |
| POST | `/api/experiments/{id}/reset` | Create a new ID using supplied settings |
| GET | `/api/experiments/{id}/human-requests` | Pending adviser requests |
| POST | `/api/experiments/{id}/human-responses` | Submit `requestId`, `x`, `y`, optional `note`; resume |
| GET | `/api/experiments/{id}/results` | Final payouts and winner; terminal runs only |
| POST | `/api/experiments/{id}/reveal-ground-truth` | Separate explicit water map; blocked during nonterminal interactive runs |
| GET | `/api/experiments/{id}/replay` | Recorded rounds from checkpoint history; no model call |

For example, create a short, low-noise experiment without running any models:

```sh
curl -sS http://127.0.0.1:8000/api/experiments \
  -H 'Content-Type: application/json' \
  -d '{"seed":42,"maxRounds":10,"observationNoise":0.05,"humanMode":"simulated"}'
```

Save the returned `experimentId` to inspect the run later. Common responses include 404 for an unknown ID, 409 for a conflicting operation or premature result request, 422 for invalid input, and 503 for missing Gemini configuration. A runtime provider interruption is represented as `awaiting_api` state with structured failure metadata; it is not necessarily an HTTP error response.

For exact schemas and edge cases, see the [frontend contract](docs/simulation-frontend-contract.md) and [API implementation](backend/src/mars_agents/api/main.py).

## Batch experiments and recorded data

The batch runner uses the same real Gemini decision service, domain rules, and checkpoints as the interface. It supports simulated human mode only.

From `backend/`, with a configured key:

```sh
uv run python -m mars_agents.experiments.batch \
  --episodes 3 --seed 42 --agents 4 \
  --treatment free_choice --human-mode simulated \
  --output ../data/batch
```

The runner uses seeds 42, 43, and 44 in this example. It reads the configured model from `.env`; `--model` can override it. To limit the first trial, save a local JSON configuration such as:

```json
{
  "seed": 42,
  "maxRounds": 10,
  "observationNoise": 0.05,
  "startingBudget": 300,
  "humanMode": "simulated",
  "treatment": "free_choice"
}
```

Pass it with `--config path/to/config.json`. Explicit CLI seed, agent-count, and treatment options override corresponding JSON values. Batch human mode is always simulated. Use a separate output directory for each comparison to keep batch-level summaries separate.

A provider failure stops the batch with the experiment ID and checkpoint location. Accepted decisions remain saved. **Rerunning the batch command creates new episodes; it is not an automatic resume command.** Existing episodes can be inspected and resumed through the service/API using the same persistence root and experiment ID.

Typical local output:

```text
data/
  checkpoints.sqlite
  <experiment-id>/
    config.json          # Initial state, accepted configuration, evaluator truth
    decisions/00001.json # Tool attempts and safe provider metadata
    rounds/00001.json    # Authorized inputs, decisions, resolved events and state summaries
    events.jsonl         # Recorded rounds, rebuilt from per-round files
    summary.json         # Terminal episode summary
    episode_summary.csv # Per-episode summary
    report.md           # Human-readable report, generated at terminal summary
```

Batch output additionally includes batch-level configuration, an aggregate `episode_summary.csv`, and a combined `events.jsonl` after completion. SQLite journal files may also be present while the service runs.

Episode summaries include seed, treatment, terminal status/reason, rounds, winner, pool size, observation/drill counts, human/pool choices, invalid-decision count, payouts, and model settings. Decision attempts retain tool name, validated arguments, concise reason, latency, optional token counts, and safe error categories. They do not retain hidden model reasoning or raw provider response bodies.

Human-readable `report.md` files summarize setup, round actions, reasons, costs, adviser requests/responses, and payouts. They are generated automatically with terminal summaries. To backfill reports for older or in-progress runs:

```sh
# From backend/: one episode, or omit the ID to process all episode directories
uv run python -m mars_agents.experiments.export EXPERIMENT_ID --root ../data
uv run python -m mars_agents.experiments.export --root ../data
```

Report export reads local logs and makes no model calls. It omits full water and adviser rasters and hidden deposit-center fields; recorded drill results and their coordinates remain part of the action history. Reports are reviewer artifacts, not rover inputs.

`data/`, `.env`, virtual environments, dependency directories, and generated frontend builds are excluded from Git. Evaluator records contain privileged truth and adviser information; keep them separate from model inputs. A clean checkout contains no claimed live benchmark dataset.

## Testing and verification

### Standard checks: no Gemini calls

From `backend/`:

```sh
uv run ruff check .
uv run mypy src
uv run pytest
```

From the repository root:

```sh
npm run lint
npm run typecheck
npm test
npm run build
git diff --check
```

Backend tests cover deterministic generation, budget accounting, legal actions, exclusive regimes, pool history and prize timing, tie-breaking, belief updates, hidden-information boundaries, retained search leads, noise-parameter non-disclosure, smolagents tool handling, provider pauses, persisted human interruptions, API behavior, and batch artifacts.

Frontend tests cover the transport adapter, settings, adviser isolation, provider pauses, replay, final results, explicit water revelation, prior/contrast controls, and drillable-zone rendering. Stubbed HTTP responses and injected proposals are test mechanisms, not available runtime policies.

The current revision has been checked locally with **146 backend tests passing** (one live-model test deselected), **26 frontend tests passing**, Ruff, Mypy, frontend lint/type checking, and a production build. These checks validate implementation behavior; they do not establish a higher live-model success rate. A third-party Starlette/AnyIO deprecation warning may appear during backend tests.

### Optional browser tests

With Google Chrome installed, from the repository root:

```sh
npm run test:browser
npm run test:browser:live
```

`test:browser` uses controlled network fixtures. `test:browser:live` targets the real local backend but is a missing-key smoke test: it skips when a Gemini key is configured and makes no provider calls. Both use the installed Chrome browser. The ordinary interface can be used in other browsers; Chrome is a test prerequisite.

### Explicit live-model test

From `backend/`, with a configured key and quota:

```sh
uv run pytest -m gemini tests/test_gemini.py
```

This opt-in test uses real Gemini and is bounded to three rounds. It can consume paid quota and may include invalid-choice retries. Skipping it is not evidence of successful live execution. A demonstration episode also does not establish robustness across seeds, treatments, models, or prompt versions.

## Limitations and interpretation

- **Synthetic task:** Elliptical deposits and blurred noisy signals approximate a search problem, not Martian geology, rover mechanics, or real remote sensing.
- **Heuristic beliefs:** Scores are uncalibrated, and the below-0.5 update behavior can misrank regions. Do not interpret a score as a literal probability of finding water.
- **Prompted strategy:** Budget caution, local ascent, and the three-point rule are model instructions. They are not enforced guarantees of intelligent behavior or an implemented numerical optimizer.
- **Bounded memory:** Strong leads and recent evidence are summarized. The model does not receive a complete raw history or the full belief grid.
- **Assistance tradeoffs:** Human guidance can be wrong. Its blend parameter and cost do not guarantee superior performance or that buying it is rational.
- **Reproducibility boundary:** Seeded world generation and fixed sensor readings are reproducible for a given configuration. Gemini outputs and service conditions need not be reproducible, even at temperature zero. Retain the Git commit, prompt version, model settings, and experiment configuration for comparisons.
- **Evaluation boundary:** Automated tests validate mechanics and information access. Claims about cooperation, exploration efficiency, or improved success rates need repeated live episodes with comparable settings. Prompt and noise changes should be treated as separate experimental changes.
- **Local operation:** The API assumes a trusted operator, a single worker, and loopback networking. The UI does not provide a full saved-experiment browser, public hosting, authentication, or a cloud deployment workflow.

## Troubleshooting

| Symptom | Check or next step |
| --- | --- |
| Cannot connect to backend | Confirm uvicorn is running on 127.0.0.1:8000; check `/api/health` and Vite’s `BACKEND_URL`. |
| Missing API key | Edit the root `.env`, verify the key in your own environment, restart the backend, and refresh the UI connection. |
| Model rejected or inaccessible | Use a supported Gemini Flash ID available to your project; inspect the safe error category and your Google project’s access. |
| API paused | Read the category: temporary rate limits differ from quota exhaustion. Wait for the displayed cooldown or resolve access/quota, then manually retry. |
| Belief map looks flat | The initial prior is uniform. Check the numerical range and whether you are viewing Initial prior; use enhanced contrast for small differences after evidence arrives. |
| High signal far from water | A scan is noisy and blurred, not exact water. Check distinct neighboring samples and the run’s configured noise. |
| Reveal truth is disabled | It is blocked in nonterminal interactive-adviser runs and while an operation is busy. |
| Settings changed but old readings remain | Runs retain their original configuration. Create a fresh run; existing observations are not regenerated. |
| Run disappears after page reload | Its backend data persists; retain its experiment ID for API inspection/replay. The UI does not automatically restore the selected run. |
| Browser test skips | The live-backend smoke test requires an unconfigured key; the real-model pytest requires a configured key and explicit opt-in. Read the skip reason. |

## Repository guide

```text
backend/
  src/mars_agents/
    agents/         Gemini adapter, tool collector, search and economic prompts
    api/            FastAPI routes and presenter response schemas
    beliefs/        Spatial updates, compact views, local-search facts
    collaboration/  Pool evidence union and membership updates
    domain/         Validated state, actions, costs, legal-action rules
    environment/    World generation, sensors, pure round resolution
    experiments/    Service, logging, batch CLI, Markdown report export
    human/          Coarse advice and interactive/simulated response handling
    orchestration/  LangGraph state, round workflow, SQLite checkpointer
  tests/            Domain, model-boundary, search, API, and workflow checks
src/
  components/       Map, controls, rover cards, pool, adviser, replay, results
  simulation/       Frontend types and HTTP client
  test/             HTTP fixtures and browser tests
  App.tsx           Mission interface composition
  styles.css        Layout and presentation
  main.tsx          Browser entry point
docs/               Experiment semantics, frontend contract, verification guide
data/               Ignored local checkpoints and evaluator records
.env.example        Safe environment template
```

For deeper detail, read the [experiment design](docs/experiment-design.md), [frontend/API contract](docs/simulation-frontend-contract.md), [agent implementation notes](backend/src/mars_agents/agents/README.md), and [setup and verification guide](docs/setup-and-verification.md).

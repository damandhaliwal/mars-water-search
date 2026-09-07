# Local setup and verification

The [main README](../README.md#quick-start) is the complete setup and reviewer guide.
This document records the verification boundaries and commands without assuming
that a new checkout already has dependencies or credentials installed.

## Start locally

From the repository root, copy `.env.example` to `.env` if needed and configure a
Gemini Flash model and API key. Do not overwrite an existing credential file.
Restart the backend after changing provider settings.

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

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). Creation, inspection, and
permitted presenter water views do not require Gemini calls. Play and Step do.
Keep the services on loopback and run one backend worker.

## Standard checks without provider calls

```sh
# From backend/
uv run pytest
uv run ruff check .
uv run mypy src
```

```sh
# From the repository root
npm run lint
npm run typecheck
npm test
npm run build
git diff --check
```

The current revision's local verification includes 146 passing backend tests
with one live-model test deselected, 26 passing frontend tests, Ruff, Mypy,
frontend lint/type checking, and the production build. A third-party
Starlette/AnyIO deprecation warning may appear during backend tests.

Backend coverage includes world generation, budgets, evidence, exclusive regimes,
historical pool sharing, same-round prize eligibility, inactive contributors,
ties, model-input isolation, search summaries, hidden noise parameters, tool
validation, provider retries and pauses, persisted human interrupts, API routes,
and batch output. Frontend coverage includes state transport, map/prior controls,
explicit water revelation, adviser isolation, settings, replay, and final results.

Full API and batch tests stub the model's HTTP response while exercising real
smolagents dispatch, validation, LangGraph, world resolution, and logging.
Other domain/workflow tests inject explicit proposals. These test mechanisms are
not exposed as runtime policies and do not prove live-model search performance.

To retain test artifacts locally, choose a disposable pytest output directory:

```sh
# From backend/; pytest clears an existing --basetemp directory
uv run pytest --basetemp ../data/verification/pytest
```

Generated test artifacts and all local evaluator records are excluded from Git.
Test episodes are fixtures, not empirical benchmark results.

## Optional browser checks

With Google Chrome installed:

```sh
# From the repository root
npm run test:browser
npm run test:browser:live
```

The first command runs the controlled HTTP-fixture project. The second targets
the real local backend but requires an unconfigured Gemini key for its missing-key
smoke test; it skips when a key is configured. Neither command makes model calls.
The browser suite uses installed Chrome; the application itself does not require
Chrome rather than another modern browser.

Browser checks are separate from the standard test counts above. Re-run them when
validating a browser-specific change; do not treat an old screenshot or a skipped
check as final-state verification.

## Explicit live-model checks

```sh
# From backend/, with a configured key; consumes provider quota
uv run pytest -m gemini tests/test_gemini.py
```

The opt-in live test is bounded to three rounds and can include invalid-choice
retries. It skips without credentials. The latest noise and prompt changes have
not been established as a measured improvement in live success rate.

A small batch uses the same model service as the UI:

```sh
# From backend/; consumes provider quota
uv run python -m mars_agents.experiments.batch --episodes 2 --seed 42 \
  --agents 4 --treatment free_choice --human-mode simulated \
  --output ../data/live-batch
```

To reduce initial work, pass `--config path/to/config.json` containing
`{"maxRounds": 3, "observationNoise": 0.05}`. This is a work limit, not a monetary
spending cap. Provider failures stop the batch with a saved checkpoint; rerunning
the batch starts new episodes rather than automatically resuming that checkpoint.

## Review-sensitive implementation choices

- The root React/Vite frontend remains the canonical interface; Python lives in
  `backend/`. There is no parallel demo policy or second simulation in the UI.
- smolagents 1.26.0 uses a guarded single-step hook because `run(max_steps=1)` can
  otherwise issue an additional final-answer model request.
- One domain resolver settles costs, beliefs, pool state, and prizes. LangGraph
  coordinates the lifecycle rather than duplicating domain calculations.
- Human costs settle once after responses arrive, with a commitment shown while
  paused. Default consultation count is one; repeat paid queries can be configured.
- Beliefs are spatial heuristics, not calibrated probabilities. Lower sensor noise
  can make local readings more accurate than the coarse adviser estimate; adviser
  quality does not guarantee better decisions or outcomes.
- Model instructions describe noise without exposing its level and encourage
  a larger move or strategy change after three unproductive distinct local probes.
  These instructions are not hard constraints on otherwise legal actions.
- Reset preserves old logs and creates a new ID. Existing configurations keep
  their original noise setting. A fresh page obtains current backend defaults.
- Presenter truth revelation is explicit: allowed during simulated-adviser runs,
  blocked until termination in interactive-adviser runs, and absent from rover
  inputs in both modes.
- Checkpoint persistence assumes compatible code/schema. Saved records are not a
  general migration guarantee across arbitrary implementation changes.

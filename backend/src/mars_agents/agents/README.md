# Gemini rover decision boundary

`from mars_agents.agents import GeminiSettings, GeminiDecisionService` is the
public entry point. Settings construction and service construction require no key
and make no API calls. `ensure_configured()` and `collect()` require a nonblank
key and raise `GeminiConfigurationError` with a safe setup message if it is absent.
The parent can allow experiment creation while returning HTTP 503 on step/run.

`collect(experiment: Experiment, views: dict[str, AgentView]) -> list[DecisionResult]`
is synchronous. It returns results in input-view order after all rover decisions
finish. The parent must hold its experiment lock and resolve proposals only after
collection completes. LangGraph nodes and FastAPI endpoints can remain synchronous.
`close()` releases model clients when the service is disposed; call it only after
active collection calls finish.

Each Pydantic `DecisionResult` contains `agent_id`, an optional domain
`ActionProposal`, `attempts`, and `invalid_decision`. Each attempt contains:

- `attempt`: one-based request number;
- `tool_name`, validated `tool_args`, concise `reason` when available;
- `latency_ms`, optional `input_tokens` and `output_tokens`;
- `error_code`, configured `model`, and `provider="gemini"`.

Persist `result.model_dump(mode="json")` in the parent experiment log. These are
the supported decision records; do not serialize smolagents agents or model
objects, which hold API clients and credentials. Raw response bodies, model text,
thinking, arbitrary function arguments, and provider error messages are omitted.
Malformed arguments are not copied into audit records. The configured key is
redacted even if it occurs in an otherwise valid decision reason.

## Setup still required for live execution

Set the following in the **repository-root `.env`**, not `backend/.env`. Environment
variables take precedence. The API key must never be committed.

```dotenv
GEMINI_API_KEY=your-personal-key
GEMINI_MODEL=gemini-3.8-flash
GEMINI_TEMPERATURE=0
GEMINI_MAX_CONCURRENCY=4
GEMINI_TIMEOUT=45
GEMINI_RETRIES=2
```

Restart the backend after changing settings. `GEMINI_MODEL` must be a Gemini Flash
identifier. All rovers use that same model, with no other provider or runtime
replacement policy. The endpoint is fixed to
`https://generativelanguage.googleapis.com/v1beta/openai/`, as documented by
[Google's OpenAI compatibility guide](https://ai.google.dev/gemini-api/docs/openai).

The implementation was inspected against installed `smolagents==1.26.0`,
`openai==3.8.0`, and `pydantic-settings==2.15.0`. The OpenAI SDK uses `httpx2==2.12.0`
as its default transport. These are the versions exercised by the tests; the
parent owns dependency pins and the project lockfile.

From the repository root, the focused non-network checks are:

```sh
backend/.venv/bin/pytest backend/tests/test_agents.py backend/tests/test_gemini.py
backend/.venv/bin/ruff check --no-cache backend/src/mars_agents/agents backend/tests/test_agents.py backend/tests/test_gemini.py
backend/.venv/bin/mypy --config-file backend/pyproject.toml backend/src/mars_agents/agents
```

The default pytest configuration excludes the `gemini` marker. To explicitly
run the real four-rover episode after configuring the key:

```sh
cd backend
uv run pytest -m gemini tests/test_gemini.py
```

That test performs a complete episode bounded to three rounds, with up to twelve
successful rover decisions plus retries. It uses real Gemini and may consume
paid API usage. Without a key it skips; a skipped test is not live verification.

## Execution and information guarantees

There is one retained `ToolCallingAgent` per `(experiment.id, agent_id)`. Every
round and retry resets memory and state and builds fresh proposal tools. The only
prompt input is the compact `AgentView`, checked against the canonical domain
view of a detached start-of-round snapshot. Neither a full belief grid nor the
experiment's truth, human raster, or other private evidence is sent to Gemini.

Legal actions from the domain are lowercase; the collector normalizes its internal
allowlist and returns the actual lowercase domain `AgentAction` enum. The tools
hold an agent ID, allowlist, and collector with a read-only validation callback.
They return an `ActionProposal` without executing it or changing simulation state.
Parallel tool calls are rejected before dispatch, and the collector independently
accepts at most one proposal. The automatically added `final_answer` tool is removed.
Text that merely resembles a tool call is never promoted to an action.

In smolagents 1.26.0, `run(max_steps=1)` can make an additional final-answer model
request. This implementation uses `ToolCallingAgent.step()` with a guarded
`_step_stream` hook instead. It makes exactly one model generation per attempt,
then uses real smolagents tool dispatch. The model subclasses `OpenAIModel` to
use its request/schema builder and real client while discarding content/raw
responses and tolerating missing token usage. No planning loop or extra final
LLM generation runs. Both narrow hooks must be reviewed when upgrading smolagents.

`ThreadPoolExecutor` runs rover decisions concurrently. A service-wide semaphore
also bounds active API requests across simultaneous experiments, and rover locks
prevent concurrent reuse of one agent. Retries reset to the same authorized view
plus a short safe correction, without prior model outputs. Model-content failures
(no tool call, multiple calls, unknown tool, malformed or illegal arguments) are
the only errors that consume those retries. Transport and provider failures
(connection errors, timeouts, 408, 409, 429, and server errors, including
authentication and other permanent rejections) never consume model retries:
the first such failure returns `provider_failure` immediately so the parent can
pause the round for an explicit manual retry. Shared cooldowns honor Retry-After,
defaulting to 60 seconds for rate limits and five seconds for temporary outages.
OpenAI automatic retries and the smolagents retryer are disabled; the configured
two-retry maximum means at most three network generations per decision absent
provider failures.

After persistent model-content failure the result has `invalid_decision=True` and no proposal.
The parent records the failure and the rover loses its round. No WAIT, heuristic,
scripted, random, or alternative-provider action is substituted. A rover with no
legal actions makes no request and returns an empty nonfailure result; the domain
owns inactivity. A zero-budget private rover can still use a legal free pool join.

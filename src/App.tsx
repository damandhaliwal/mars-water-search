import { useEffect, useState, useSyncExternalStore } from "react";
import { ArrowUpRight, Radio } from "lucide-react";
import type { SimulationClient } from "./simulation/SimulationClient";
import { isTerminal, type ExperimentConfig } from "./simulation/types";
import { ExperimentControls } from "./components/ExperimentControls";
import { MarsGrid } from "./components/MarsGrid";
import { AgentList } from "./components/AgentList";
import { InformationPool } from "./components/InformationPool";
import { RecentEvents } from "./components/RecentEvents";
import { SuccessSummary } from "./components/SuccessSummary";
import { HumanAdvisor } from "./components/HumanAdvisor";
import { ProviderPause } from "./components/ProviderPause";
import { ReplayBar } from "./components/ReplayBar";

export default function App({ client }: { client: SimulationClient }) {
  const {
    state,
    config,
    health,
    busy,
    playing,
    error,
    humanRequests,
    groundTruth,
    replay,
  } = useSyncExternalStore(client.subscribe, client.getSnapshot);
  const [selected, setSelected] = useState("A");
  // The client publishes errors to the view, including those from background playback.
  const run = (operation: Promise<unknown>) => {
    void operation.catch(() => {});
  };
  useEffect(() => {
    void client.initialize().catch(() => {});
    return () => {
      client.pause();
    };
  }, [client]);
  function control(command: "start" | "pause" | "step" | "reset" | "refresh") {
    if (command === "start" || command === "pause") client[command]();
    else
      run(
        command === "refresh" ? client.getExperimentState() : client[command](),
      );
  }
  function applySettings(next: ExperimentConfig) {
    setSelected("A");
    run(state ? client.reset(next) : client.create(next));
  }
  const canReplay = !replay && !!state && state.round >= 1;
  // Unmount the presenter while advising, including during loading and request errors.
  if (state?.status === "awaiting_human")
    return (
      <HumanAdvisor
        key={humanRequests[0]?.id ?? "pending"}
        request={humanRequests[0]}
        pendingCount={humanRequests.length}
        busy={busy}
        playing={playing}
        error={error}
        onSubmit={(response) => run(client.submitHumanResponse(response))}
        onRefresh={() => run(client.refreshHumanRequests())}
        onPause={client.pause}
      />
    );
  if (!config)
    return (
      <main className="loading-state">
        <h1>Mars Water Search</h1>
        <p role={error ? "alert" : "status"}>
          {error ?? "Connecting to the local backend…"}
        </p>
        {error && (
          <button
            className="secondary-button"
            disabled={busy}
            onClick={() => run(client.initialize())}
          >
            Retry connection
          </button>
        )}
      </main>
    );
  const status = state?.status === "awaiting_api" || isTerminal(state)
    ? state!.status
    : playing
      ? "running"
      : state?.status === "running"
        ? "paused"
        : (state?.status ?? "idle");
  const selection =
    selected === "pool" && state?.pool.memberIds.length
      ? "pool"
      : state?.agents.some((a) => a.id === selected)
        ? selected
        : (state?.agents[0]?.id ?? "A");
  return (
    <div className="app-shell">
      <header className="site-header">
        <div className="brand">
          <span className="brand-mark">
            <ArrowUpRight size={23} />
          </span>
          <div>
            <h1>Mars Water Search</h1>
            <p>Multi-agent exploration experiment</p>
          </div>
        </div>
        <div className="header-status">
          <span className="backend-label">
            Gemini · {health?.model ?? "Backend"}
          </span>
          <span className={`status ${status}`}>
            <Radio size={14} />
            {status === "awaiting_api" ? "API paused" : status === "idle" ? "Ready" : status}
          </span>
        </div>
      </header>
      <div className="study-caption">
        <span>SEED {config.seed}</span>
        <p>
          Independent exploration, collective knowledge, or expert guidance.
        </p>
        <span className="small">Individual budgets · Shared uncertainty</span>
      </div>
      {health && !health.geminiConfigured && (
        <div className="error-banner" role="status">
          <span>
            Gemini is not configured. Set GEMINI_API_KEY in the backend
            environment and restart the backend. Creating an experiment is
            available; Play and Step require the key.
          </span>
          <button
            disabled={busy || playing}
            onClick={() => run(client.initialize())}
          >
            Check connection
          </button>
        </div>
      )}
      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}
      {state?.status === "awaiting_api" && (
        <ProviderPause
          failure={state.providerFailure}
          busy={busy}
          onRetry={() => run(client.step())}
        />
      )}
      {replay && state && (
        <ReplayBar
          index={replay.index}
          total={replay.rounds.length}
          round={state.round}
          playing={playing}
          busy={busy}
          onBack={() => client.replayStep(-1)}
          onToggle={() => (playing ? client.pause() : client.start())}
          onForward={() => run(client.step())}
          onExit={() => client.exitReplay()}
        />
      )}
      <main className="workspace">
        <ExperimentControls
          key={`${state?.experimentId ?? "new"}-${JSON.stringify(config)}`}
          state={state}
          config={config}
          busy={busy}
          playing={playing}
          onControl={control}
          onApplySettings={applySettings}
          onReplay={() => run(client.enterReplay())}
          canReplay={canReplay}
          replayActive={!!replay}
        />
        <div className="center-column">
          {state ? (
            <>
              <MarsGrid
                key={state.experimentId}
                state={state}
                selected={selection}
                onSelect={setSelected}
                groundTruth={groundTruth}
                onReveal={() => client.revealGroundTruth()}
                busy={busy}
              />
              {isTerminal(state) && (
                <SuccessSummary
                  state={state}
                  busy={busy}
                  onRetry={() => run(client.getResults())}
                />
              )}
            </>
          ) : (
            <section className="map-section">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Exploration field</p>
                  <h2>Create a seeded experiment</h2>
                </div>
                <span className="map-coordinate-label">
                  {config.gridWidth} × {config.gridHeight} cells
                </span>
              </div>
              <div className="map-placeholder">
                <p>Choose your settings, then create the experiment.</p>
                <span>
                  The first round runs only when you select Play or Step.
                </span>
              </div>
            </section>
          )}
        </div>
        <aside className="right-rail">
          {state ? (
            <>
              <AgentList
                state={state}
                selected={selection}
                onSelect={setSelected}
              />
              <InformationPool pool={state.pool} />
            </>
          ) : (
            <>
              <div className="rail-heading">
                <h2>Agents</h2>
              </div>
              <p className="small muted">
                Positions, budgets, and beliefs will appear after creation.
              </p>
            </>
          )}
        </aside>
      </main>
      <RecentEvents events={state?.recentEvents ?? []} />
      <footer>
        <span>
          MARS WATER SEARCH <span className="footer-divider">/</span>Research
          sandbox
        </span>
        <span>
          Gemini agents · Local backend
          <span className="footer-dot" />
        </span>
      </footer>
    </div>
  );
}

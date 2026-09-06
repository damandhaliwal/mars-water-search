import { useEffect, useState } from "react";
import { ArrowUpRight, Radio } from "lucide-react";
import type { SimulationClient } from "./simulation/SimulationClient";
import type { ExperimentConfig, ExperimentState } from "./simulation/types";
import { ExperimentControls } from "./components/ExperimentControls";
import { MarsGrid } from "./components/MarsGrid";
import { AgentList } from "./components/AgentList";
import { InformationPool } from "./components/InformationPool";
import { RecentEvents } from "./components/RecentEvents";
import { SuccessSummary } from "./components/SuccessSummary";

export default function App({ client }: { client: SimulationClient }) {
  const [state, setState] = useState<ExperimentState | null>(null);
  const [selected, setSelected] = useState("A");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true,
      receivedUpdate = false;
    const unsubscribe = client.subscribe((snapshot) => {
      receivedUpdate = true;
      if (active) setState(snapshot);
    });
    client
      .getExperimentState()
      .then((snapshot) => {
        if (active && !receivedUpdate) setState(snapshot);
      })
      .catch((e) => {
        if (active)
          setError(
            e instanceof Error ? e.message : "Unable to load experiment.",
          );
      });
    return () => {
      active = false;
      unsubscribe();
    };
  }, [client]);
  async function control(command: "start" | "pause" | "step" | "reset") {
    setBusy(true);
    setError(null);
    try {
      await client[command]();
      if (command === "reset") setSelected("A");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Experiment control failed.");
    } finally {
      setBusy(false);
    }
  }
  async function applySettings(config: ExperimentConfig) {
    setBusy(true);
    setError(null);
    try {
      await client.reset(config);
      setSelected("A");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to apply settings.");
    } finally {
      setBusy(false);
    }
  }
  if (!state)
    return (
      <main className="loading-state">
        <h1>Mars Water Search</h1>
        <p role={error ? "alert" : "status"}>
          {error ?? "Loading experiment…"}
        </p>
      </main>
    );
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
          <span className="demo-label">
            {state.source === "demo" ? "Scripted demo" : "Connected experiment"}
          </span>
          <span className={`status ${state.status}`}>
            <Radio size={14} />
            {state.status === "idle" ? "Ready" : state.status}
          </span>
        </div>
      </header>
      <div className="study-caption">
        <span>EXPERIMENT 001</span>
        <p>
          Independent exploration, collective knowledge, or expert guidance.
        </p>
        <span className="small">Individual budgets · Shared uncertainty</span>
      </div>
      {error && (
        <div className="error-banner" role="alert">
          {error}
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}
      <main className="workspace">
        <ExperimentControls
          key={`${state.experimentId}-${JSON.stringify(state.config)}`}
          state={state}
          busy={busy}
          onControl={control}
          onApplySettings={applySettings}
        />
        <div className="center-column">
          <MarsGrid
            key={`${state.experimentId}-${state.round === 0 ? "initial" : "active"}`}
            state={state}
            selected={selected}
            onSelect={setSelected}
          />
          {state.winner && <SuccessSummary winner={state.winner} />}{" "}
          {state.status === "failure" && (
            <section className="failure-summary" role="status">
              <h2>Experiment ended without a discovery</h2>
              <p>
                {state.failureReason ?? "No qualifying discovery was reported."}
              </p>
            </section>
          )}
        </div>
        <aside className="right-rail">
          <AgentList state={state} selected={selected} onSelect={setSelected} />
          <InformationPool pool={state.pool} />
        </aside>
      </main>
      <RecentEvents events={state.recentEvents} />
      <footer>
        <span>
          MARS WATER SEARCH <span className="footer-divider">/</span> Research
          sandbox
        </span>
        <span>
          {state.source === "demo"
            ? "Scripted data · No live simulation"
            : "Simulation data supplied by backend"}
          <span className="footer-dot" />
        </span>
      </footer>
    </div>
  );
}

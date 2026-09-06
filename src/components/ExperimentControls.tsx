import { Pause, Play, RotateCcw, StepForward } from "lucide-react";
import type { ExperimentState } from "../simulation/types";

export function ExperimentControls({
  state,
  busy,
  onControl,
}: {
  state: ExperimentState;
  busy: boolean;
  onControl: (command: "start" | "pause" | "step" | "reset") => void;
}) {
  const terminal = state.status === "success" || state.status === "failure";
  return (
    <aside className="experiment-controls">
      <p className="eyebrow">Experiment</p>
      <div className="round-number">
        {String(state.round).padStart(2, "0")}
        <span>/ {state.maxRounds ?? "—"}</span>
      </div>
      <p className="muted round-caption">Current round</p>
      <button
        className="primary-button"
        disabled={busy || terminal}
        onClick={() =>
          onControl(state.status === "running" ? "pause" : "start")
        }
      >
        {state.status === "running" ? <Pause size={16} /> : <Play size={16} />}
        {state.status === "running"
          ? "Pause"
          : state.round === 0
            ? "Run experiment"
            : "Resume"}
      </button>
      <button
        className="secondary-button"
        disabled={busy || terminal || state.status === "running"}
        onClick={() => onControl("step")}
      >
        <StepForward size={16} />
        Step one round
      </button>
      <button
        className="text-button reset-button"
        disabled={busy}
        onClick={() => onControl("reset")}
      >
        <RotateCcw size={14} />
        Reset experiment
      </button>
      <div className="settings">
        <p className="eyebrow">Experiment settings</p>
        <dl>
          <div>
            <dt>Grid</dt>
            <dd>
              {state.config.gridWidth} × {state.config.gridHeight}
            </dd>
          </div>
          <div>
            <dt>Agents</dt>
            <dd>{state.config.numberOfAgents}</dd>
          </div>
          <div>
            <dt>Deposits</dt>
            <dd>{state.config.numberOfWaterDeposits ?? "Undisclosed"}</dd>
          </div>
          <div>
            <dt>Budget / agent</dt>
            <dd>{state.config.startingBudget}</dd>
          </div>
          <div>
            <dt>Discovery prize</dt>
            <dd>{state.config.discoveryReward.toLocaleString()}</dd>
          </div>
        </dl>
        <p className="small muted">Costs and rewards in experiment credits.</p>
      </div>
      <div className="experiment-note">
        <span className="small-label">The decision</span>
        <p>
          Search alone.
          <br />
          Share information and reward.
          <br />
          Or pay for expert guidance.
        </p>
      </div>
    </aside>
  );
}

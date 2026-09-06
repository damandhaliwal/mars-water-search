import { Pause, Play, RotateCcw, StepForward } from "lucide-react";
import { useState } from "react";
import type { ExperimentConfig, ExperimentState } from "../simulation/types";

export function ExperimentControls({
  state,
  busy,
  onControl,
  onApplySettings,
}: {
  state: ExperimentState;
  busy: boolean;
  onControl: (command: "start" | "pause" | "step" | "reset") => void;
  onApplySettings: (config: ExperimentConfig) => Promise<void>;
}) {
  const [draft, setDraft] = useState(() => ({
    gridWidth: String(state.config.gridWidth),
    gridHeight: String(state.config.gridHeight),
    numberOfAgents: String(state.config.numberOfAgents),
    numberOfWaterDeposits: state.config.numberOfWaterDeposits === undefined ? "" : String(state.config.numberOfWaterDeposits),
    startingBudget: String(state.config.startingBudget),
    discoveryReward: String(state.config.discoveryReward),
  }));
  const fields = [
    { key: "gridWidth", label: "Grid width", min: 1, step: 1 },
    { key: "gridHeight", label: "Grid height", min: 1, step: 1 },
    { key: "numberOfAgents", label: "Agents", min: 1, step: 1 },
    { key: "numberOfWaterDeposits", label: "Deposits", min: 1, max: 2, step: 1 },
    { key: "startingBudget", label: "Budget / agent", min: 0.01, step: "any" },
    { key: "discoveryReward", label: "Discovery prize", min: 0, step: "any" },
  ] as const;
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
      <form className="settings" onSubmit={(event) => {
        event.preventDefault();
        const config: ExperimentConfig = {
          gridWidth: Number(draft.gridWidth),
          gridHeight: Number(draft.gridHeight),
          numberOfAgents: Number(draft.numberOfAgents),
          numberOfWaterDeposits: draft.numberOfWaterDeposits === "" ? undefined : Number(draft.numberOfWaterDeposits),
          startingBudget: Number(draft.startingBudget),
          discoveryReward: Number(draft.discoveryReward),
        };
        void onApplySettings(config);
      }}>
        <p className="eyebrow">Experiment settings</p>
        <fieldset disabled={busy || state.status === "running"} className="settings-fields">
          {fields.map(field => <label key={field.key} className="settings-field">
            <span>{field.label}</span>
            <input
              type="number"
              name={field.key}
              min={field.min}
              max={"max" in field ? field.max : undefined}
              step={field.step}
              required={field.key !== "numberOfWaterDeposits"}
              placeholder={field.key === "numberOfWaterDeposits" ? "Unspecified" : undefined}
              value={draft[field.key]}
              onChange={event => setDraft(previous => ({...previous, [field.key]: event.target.value}))}
            />
          </label>)}
          <button type="submit" className="secondary-button">Apply &amp; reset</button>
          <button type="button" className="text-button" onClick={() => setDraft({
            gridWidth: String(state.config.gridWidth), gridHeight: String(state.config.gridHeight),
            numberOfAgents: String(state.config.numberOfAgents),
            numberOfWaterDeposits: state.config.numberOfWaterDeposits === undefined ? "" : String(state.config.numberOfWaterDeposits),
            startingBudget: String(state.config.startingBudget), discoveryReward: String(state.config.discoveryReward),
          })}>Restore current values</button>
        </fieldset>
        <p className="small muted">Costs and rewards in experiment credits.</p>
        <p className="small muted settings-help">{state.source === "demo" ? "Custom settings require the backend. This demo plays the default setup only." : "Apply starts a fresh experiment. Pause before changing settings."}</p>
      </form>
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

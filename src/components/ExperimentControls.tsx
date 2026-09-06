import { Pause, Play, RotateCcw, StepForward } from "lucide-react";
import { useState } from "react";
import {
  isTerminal,
  type ExperimentConfig,
  type ExperimentState,
} from "../simulation/types";

const fields = [
  { key: "seed", label: "Seed", min: 0, max: Number.MAX_SAFE_INTEGER, step: 1 },
  { key: "numberOfAgents", label: "Agents", min: 1, max: 64, step: 1 },
  { key: "gridWidth", label: "Grid width", min: 1, max: 256, step: 1 },
  { key: "gridHeight", label: "Grid height", min: 1, max: 256, step: 1 },
  { key: "numberOfWaterDeposits", label: "Deposits", min: 1, max: 2, step: 1 },
  { key: "startingBudget", label: "Budget / agent", min: 0, step: "any" },
  { key: "discoveryReward", label: "Discovery prize", min: 0, step: "any" },
  { key: "humanCost", label: "Human cost", min: 0, step: "any" },
  { key: "humanQuality", label: "Human quality", min: 0, max: 1, step: "any" },
  { key: "maxRounds", label: "Round limit", min: 1, step: 1 },
] as const;
const toDraft = (config: ExperimentConfig) =>
  Object.fromEntries(
    Object.entries(config).map(([key, value]) => [key, String(value)]),
  );

export function ExperimentControls({
  state,
  config,
  busy,
  playing,
  onControl,
  onApplySettings,
  onReplay,
  canReplay,
  replayActive,
}: {
  state: ExperimentState | null;
  config: ExperimentConfig;
  busy: boolean;
  playing: boolean;
  onControl: (
    command: "start" | "pause" | "step" | "reset" | "refresh",
  ) => void;
  onApplySettings: (config: ExperimentConfig) => void;
  onReplay: () => void;
  canReplay: boolean;
  replayActive: boolean;
}) {
  const [draft, setDraft] = useState(() => toDraft(config));
  const blocked =
    !state ||
    isTerminal(state) ||
    state.status === "awaiting_human" ||
    state.status === "awaiting_api";
  return (
    <aside className="experiment-controls">
      <p className="eyebrow">Experiment</p>
      <div className="round-number">
        {String(state?.round ?? 0).padStart(2, "0")}
        <span>/ {config.maxRounds}</span>
      </div>
      <p className="muted round-caption">
        {replayActive
          ? "Recorded round"
          : busy && state
            ? "Request in progress…"
            : "Current round"}
      </p>
      <button
        className="primary-button"
        disabled={!playing && (busy || blocked)}
        onClick={() => onControl(playing ? "pause" : "start")}
      >
        {playing ? <Pause size={16} /> : <Play size={16} />}
        {playing ? "Pause" : "Play"}
      </button>
      <button
        className="secondary-button"
        disabled={busy || playing || blocked}
        onClick={() => onControl("step")}
      >
        <StepForward size={16} />
        Step one round
      </button>
      <button
        className="text-button reset-button"
        disabled={busy || !state || replayActive}
        onClick={() => onControl("reset")}
      >
        <RotateCcw size={14} />
        Reset experiment
      </button>
      {state && (
        <button
          className="text-button"
          disabled={busy || playing || replayActive}
          onClick={() => onControl("refresh")}
        >
          Refresh state
        </button>
      )}
      {!replayActive && (
        <button
          className="text-button"
          disabled={busy || !canReplay}
          onClick={onReplay}
        >
          Replay recorded run
        </button>
      )}
      {busy && !playing && state && state.status !== "awaiting_api" && (
        <p className="small muted">
          An in-flight round finishes before playback stops.
        </p>
      )}
      <form
        className="settings"
        onSubmit={(event) => {
          event.preventDefault();
          const next = {
            ...config,
            humanMode: draft.humanMode,
            treatment: draft.treatment,
          } as ExperimentConfig;
          for (const field of fields)
            next[field.key] = Number(draft[field.key]);
          onApplySettings(next);
        }}
      >
        <p className="eyebrow">Experiment settings</p>
        <fieldset
          disabled={busy || playing || state?.status === "awaiting_human" || replayActive}
          className="settings-fields"
        >
          {fields.map((field) => (
            <label key={field.key} className="settings-field">
              <span>{field.label}</span>
              <input
                type="number"
                name={field.key}
                min={field.min}
                max={"max" in field ? field.max : undefined}
                step={field.step}
                required
                value={draft[field.key]}
                onChange={(event) =>
                  setDraft((previous) => ({
                    ...previous,
                    [field.key]: event.target.value,
                  }))
                }
              />
            </label>
          ))}
          <label className="settings-field">
            <span>Human mode</span>
            <select
              value={draft.humanMode}
              onChange={(event) =>
                setDraft((previous) => ({
                  ...previous,
                  humanMode: event.target.value,
                }))
              }
            >
              <option value="simulated">Simulated advisor</option>
              <option value="interactive">Interactive advisor</option>
            </select>
          </label>
          <label className="settings-field">
            <span>Treatment</span>
            <select
              value={draft.treatment}
              onChange={(event) =>
                setDraft((previous) => ({
                  ...previous,
                  treatment: event.target.value,
                }))
              }
            >
              <option value="free_choice">Free choice</option>
              <option value="solo_only">Solo only</option>
              <option value="ai_collab_available">
                AI collaboration available
              </option>
              <option value="human_available">Human available</option>
            </select>
          </label>
          <button type="submit" className="secondary-button">
            {state ? "Apply & reset" : "Create experiment"}
          </button>
          <button
            type="button"
            className="text-button"
            onClick={() => setDraft(toDraft(config))}
          >
            Restore current values
          </button>
        </fieldset>
        <p className="small muted settings-help">
          {state
            ? "Apply creates a fresh run. Pause before editing."
            : "Defaults supplied by the backend. Create first, then Play or Step."}{" "}
          Costs and rewards in experiment credits.
        </p>
      </form>
      <div className="experiment-note">
        <span className="small-label">The decision</span>
        <p>
          Search alone.
          <br />
          Share information and reward.
          <br />
          Or pay for private expert guidance.
        </p>
      </div>
    </aside>
  );
}

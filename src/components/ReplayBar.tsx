import { Pause, Play, StepBack, StepForward, X } from "lucide-react";

export function ReplayBar({
  index,
  total,
  round,
  playing,
  busy,
  onBack,
  onToggle,
  onForward,
  onExit,
}: {
  index: number;
  total: number;
  round: number;
  playing: boolean;
  busy: boolean;
  onBack: () => void;
  onToggle: () => void;
  onForward: () => void;
  onExit: () => void;
}) {
  return (
    <section className="replay-bar" aria-label="Recorded run replay">
      <div className="provider-pause-details">
        <h2>Replay · recorded run</h2>
        <p>
          Round {round} of {total - 1} · {total} recorded frames. Stepping here
          replays saved moves without calling the model.
        </p>
      </div>
      <div className="replay-controls">
        <button
          className="secondary-button"
          disabled={busy || index === 0}
          onClick={onBack}
          aria-label="Back one round"
        >
          <StepBack size={16} />
        </button>
        <button
          className="secondary-button"
          disabled={busy}
          onClick={onToggle}
          aria-label={playing ? "Pause replay" : "Play replay"}
        >
          {playing ? <Pause size={16} /> : <Play size={16} />}
        </button>
        <button
          className="secondary-button"
          disabled={busy || index >= total - 1}
          onClick={onForward}
          aria-label="Forward one round"
        >
          <StepForward size={16} />
        </button>
        <button className="text-button" disabled={busy} onClick={onExit}>
          <X size={14} />
          Exit replay
        </button>
      </div>
    </section>
  );
}

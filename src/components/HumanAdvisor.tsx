import { useEffect, useRef, useState } from "react";
import type { HumanRequest, HumanResponse } from "../simulation/types";

/** This component receives only the advisor packet, never the presenter snapshot. */
export function HumanAdvisor({
  request,
  pendingCount,
  busy,
  playing,
  error,
  onSubmit,
  onRefresh,
  onPause,
}: {
  request?: HumanRequest;
  pendingCount: number;
  busy: boolean;
  playing: boolean;
  error: string | null;
  onSubmit: (response: HumanResponse) => void;
  onRefresh: () => void;
  onPause: () => void;
}) {
  const [selected, setSelected] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, []);
  const prior = request?.prior;
  const valid =
    prior &&
    prior.width > 0 &&
    prior.height > 0 &&
    prior.values.length === prior.width * prior.height;
  const confidence = selected === null ? null : prior?.values[selected];
  const position =
    request && selected !== null
      ? {
          x: Math.min(
            request.gridWidth - 1,
            Math.floor(
              (((selected % request.prior.width) + 0.5) * request.gridWidth) /
                request.prior.width,
            ),
          ),
          y: Math.min(
            request.gridHeight - 1,
            Math.floor(
              ((Math.floor(selected / request.prior.width) + 0.5) *
                request.gridHeight) /
                request.prior.height,
            ),
          ),
        }
      : null;
  return (
    <section
      className="human-advisor-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="advisor-title"
    >
      <div className="human-advisor-card">
        <p className="eyebrow">Human advisor request · Experiment paused</p>
        <h1 id="advisor-title" ref={heading} tabIndex={-1}>
          Recommend a search region
        </h1>
        {request ? (
          <p>
            Agent {request.agentId} commits {request.cost} credits for private
            guidance in round {request.round}. {pendingCount} request
            {pendingCount === 1 ? "" : "s"} remaining.
          </p>
        ) : (
          <p role="status">
            {busy
              ? "Loading advisor information…"
              : "No request loaded. Refresh pending requests to continue."}
          </p>
        )}
        <p className="small muted">
          Only the coarse, imperfect advisor prior is shown here. The
          recommendation stays private to this agent and cannot enter the AI
          pool.
        </p>
        {error && (
          <p className="error-banner" role="alert">
            {error}
          </p>
        )}
        {request && (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              if (position && confidence != null)
                onSubmit({
                  requestId: request.id,
                  ...position,
                  note: note.trim(),
                });
            }}
          >
            <fieldset disabled={busy} className="advisor-fields">
              {valid ? (
                <div
                  className="advisor-grid"
                  role="group"
                  aria-label="Coarse human prior"
                  style={{
                    gridTemplateColumns: `repeat(${prior.width}, minmax(0, 1fr))`,
                    aspectRatio: `${request.gridWidth} / ${request.gridHeight}`,
                  }}
                >
                  {prior.values.map((value, index) => (
                    <button
                      type="button"
                      key={index}
                      aria-label={`Region ${index % prior.width}, ${Math.floor(index / prior.width)}; confidence ${value == null ? "unavailable" : value.toFixed(2)}`}
                      disabled={value == null}
                      aria-pressed={selected === index}
                      style={{
                        background:
                          value == null
                            ? "#d8d8d8"
                            : `linear-gradient(rgb(23 79 100 / ${Math.max(0, Math.min(1, value)) * 0.82}), rgb(23 79 100 / ${Math.max(0, Math.min(1, value)) * 0.82})), #dfb296`,
                      }}
                      onClick={() => setSelected(index)}
                    >
                      {selected === index ? "✓" : ""}
                    </button>
                  ))}
                </div>
              ) : (
                <p role="alert">
                  The advisor prior is unavailable. Refresh pending requests.
                </p>
              )}
              <p className="advisor-selection" role="status">
                {position && confidence != null
                  ? `Recommended cell (${position.x}, ${position.y}) · Prior confidence ${confidence.toFixed(2)}`
                  : "Select a region to inspect its confidence and recommend its center."}
              </p>
              <label className="settings-field">
                <span>Optional note</span>
                <textarea
                  value={note}
                  maxLength={300}
                  rows={3}
                  onChange={(event) => setNote(event.target.value)}
                />
              </label>
              <button
                className="primary-button"
                type="submit"
                disabled={!position || confidence == null}
              >
                {busy ? "Submitting…" : "Submit recommendation & resume"}
              </button>
            </fieldset>
          </form>
        )}
        <button className="text-button" disabled={busy} onClick={onRefresh}>
          Refresh pending requests
        </button>
        {playing ? (
          <button className="secondary-button" onClick={onPause}>
            Pause playback after response
          </button>
        ) : (
          <p className="small muted">
            Submitting resumes the interrupted round. Further rounds wait for
            Play or Step.
          </p>
        )}
      </div>
    </section>
  );
}

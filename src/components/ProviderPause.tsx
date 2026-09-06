import { useEffect, useState } from "react";
import type { ProviderFailure } from "../simulation/types";

const secondsUntil = (retryAt: number | null | undefined) =>
  Math.max(0, Math.ceil(((retryAt ?? 0) * 1000 - Date.now()) / 1000));

function RetryPendingRound({
  retryAt,
  busy,
  onRetry,
}: {
  retryAt?: number | null;
  busy: boolean;
  onRetry: () => void;
}) {
  const [remaining, setRemaining] = useState(() => secondsUntil(retryAt));
  useEffect(() => {
    if (!secondsUntil(retryAt)) return;
    // This timer only enables the control. It never submits a request.
    const timer = setInterval(() => {
      const seconds = secondsUntil(retryAt);
      setRemaining(seconds);
      if (seconds === 0) clearInterval(timer);
    }, 1000);
    return () => clearInterval(timer);
  }, [retryAt]);
  return (
    <div className="provider-retry">
      <button
        className="secondary-button"
        disabled={busy || remaining > 0}
        onClick={onRetry}
        aria-describedby="provider-retry-timing"
      >
        Retry pending round
      </button>
      <p id="provider-retry-timing" className="small" role="timer">
        {busy
          ? "Request in progress…"
          : remaining > 0
            ? `Retry available in ${remaining}s.`
            : "Ready to retry when you choose."}
      </p>
      <p className="small">Playback stays paused after retry.</p>
    </div>
  );
}

export function ProviderPause({
  failure,
  busy,
  onRetry,
}: {
  failure?: ProviderFailure | null;
  busy: boolean;
  onRetry: () => void;
}) {
  return (
    <section className="provider-pause" aria-labelledby="provider-pause-title">
      <div className="provider-pause-details" role="alert">
        <h2 id="provider-pause-title">Provider interruption</h2>
        <p>{failure?.message || "The provider could not complete the pending round."}</p>
        <p>
          The pending round has not committed. Round and budgets are unchanged;
          accepted decisions are saved.
        </p>
        {!!failure?.agentIds.length && (
          <p>Waiting for agents: {failure.agentIds.join(", ")}.</p>
        )}
        {!!failure?.failures.length && (
          <ul className="provider-failures">
            {failure.failures.map((item, index) => (
              <li key={`${item.agentId}-${index}`}>
                Agent {item.agentId}: {item.category.replaceAll("_", " ")}
                {item.httpStatus != null && ` (HTTP ${item.httpStatus})`}
              </li>
            ))}
          </ul>
        )}
      </div>
      <RetryPendingRound
        key={failure?.retryAt ?? "ready"}
        retryAt={failure?.retryAt}
        busy={busy}
        onRetry={onRetry}
      />
    </section>
  );
}

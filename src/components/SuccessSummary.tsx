import { Droplets } from "lucide-react";
import type { ExperimentState } from "../simulation/types";
import { regimeLabels } from "../simulation/presentation";
const number = (value: number) =>
  value.toLocaleString(undefined, { maximumFractionDigits: 2 });

export function SuccessSummary({
  state,
  onRetry,
  busy,
}: {
  state: ExperimentState;
  onRetry: () => void;
  busy: boolean;
}) {
  const winner = state.winner;
  const payouts = state.results ?? winner?.payouts;
  return (
    <section
      className={`success-summary ${state.status === "failure" ? "failure-summary" : ""}`}
      aria-label="Final results"
    >
      {winner ? (
        <>
          <div className="success-heading">
            <Droplets size={24} />
            <div>
              <p className="eyebrow">Water found</p>
              <h2>Agent {winner.agentId} confirmed a discovery.</h2>
              <p>
                {regimeLabels[winner.status]} · ({winner.position.x},{" "}
                {winner.position.y}) · Intensity {number(winner.intensity)} ·{" "}
                {number(winner.discoveryReward)} credit prize
              </p>
            </div>
            <div className="success-share">
              <strong>{number(winner.rewardPerRecipient)}</strong>
              <span>credits / recipient</span>
            </div>
          </div>
          <p className="small">
            Prize recipients: {winner.recipientIds.join(", ")}. Pool eligibility
            is determined before the winning round.
          </p>
        </>
      ) : (
        <>
          <h2>Experiment ended without a discovery</h2>
          <p className="small">
            {state.failureReason ?? "No qualifying discovery was reported."}
          </p>
        </>
      )}
      {payouts ? (
        <div className="results-table">
          <table>
            <thead>
              <tr>
                <th>Agent</th>
                <th>Regime</th>
                <th>Reward</th>
                <th>Total costs</th>
                <th>Net utility</th>
              </tr>
            </thead>
            <tbody>
              {payouts.map((p) => (
                <tr key={p.agentId}>
                  <th>Agent {p.agentId}</th>
                  <td>{regimeLabels[p.regime]}</td>
                  <td>{number(p.reward)}</td>
                  <td>{number(p.totalCost)}</td>
                  <td>{number(p.utility)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <>
          <p className="small">Final payouts have not loaded.</p>
          <button
            className="secondary-button"
            disabled={busy}
            onClick={onRetry}
          >
            Load final results
          </button>
        </>
      )}
      <p className="small muted">
        Backend-settled results. Displayed amounts are rounded to two decimals.
      </p>
    </section>
  );
}

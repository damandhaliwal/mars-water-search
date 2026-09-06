import { Droplets } from "lucide-react";
import type { WinnerState } from "../simulation/types";
const number = (value: number) =>
  value.toLocaleString(undefined, { maximumFractionDigits: 2 });
export function SuccessSummary({ winner }: { winner: WinnerState }) {
  return (
    <section className="success-summary" role="status">
      <div className="success-heading">
        <Droplets size={24} />
        <div>
          <p className="eyebrow">Water found</p>
          <h2>Agent {winner.agentId} confirmed a discovery.</h2>
          <p>
            {winner.status === "pool" ? "Pool member" : "Private winner"} · (
            {winner.position.x}, {winner.position.y}) ·{" "}
            {number(winner.discoveryReward)} credit prize
          </p>
        </div>
        <div className="success-share">
          <strong>{number(winner.rewardPerRecipient)}</strong>
          <span>credits / recipient</span>
        </div>
      </div>
      <p className="small">
        Prize recipients: {winner.recipientIds.join(", ")}. Payouts reflect
        eligibility before the winning round.
      </p>
      <table>
        <thead>
          <tr>
            <th>Agent</th>
            <th>Reward</th>
            <th>Total costs</th>
            <th>Net utility</th>
          </tr>
        </thead>
        <tbody>
          {winner.payouts.map((p) => (
            <tr key={p.agentId}>
              <th>Agent {p.agentId}</th>
              <td>{number(p.reward)}</td>
              <td>{number(p.totalCost)}</td>
              <td>{number(p.utility)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="small muted">
        Amounts displayed to two decimals. Reveal truth on the map to inspect
        the supplied deposit.
      </p>
    </section>
  );
}

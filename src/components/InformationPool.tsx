import { Users, Sparkles } from "lucide-react";
import type { PoolState } from "../simulation/types";
const kinds = {
  observation: "OBSERVATION",
  human: "HUMAN INPUT",
  drill: "DRILL RESULT",
  location: "LOCATION",
  belief: "BELIEF UPDATE",
};
export function InformationPool({ pool }: { pool: PoolState }) {
  return (
    <section className="information-pool">
      <div className="rail-heading">
        <h2>Information pool</h2>
        <Users size={17} />
      </div>
      <div className="pool-members">
        <span>Members</span>
        <strong>
          {pool.memberIds.length ? pool.memberIds.join(", ") : "None yet"}
        </strong>
      </div>
      <div className="pool-prize">
        <span>Potential prize / eligible member</span>
        <strong>
          {pool.rewardPerMember === null
            ? "—"
            : pool.rewardPerMember.toLocaleString(undefined, {
                maximumFractionDigits: 2,
              })}
          <small> credits</small>
        </strong>
        {pool.eligibleMemberIds.length > 0 && (
          <span className="small">
            {pool.discoveryReward.toLocaleString()} ÷{" "}
            {pool.eligibleMemberIds.length} · eligible for round{" "}
            {pool.eligibilityRound}
          </span>
        )}
      </div>
      <div
        className="pool-log"
        role="log"
        aria-label="Shared information board"
      >
        {pool.events.length === 0 ? (
          <div className="pool-empty">
            <Users size={23} />
            <p>No shared evidence yet.</p>
            <span>
              Joining contributes past information in exchange for a share of
              the prize.
            </span>
          </div>
        ) : (
          [...pool.events].reverse().map((e) => (
            <article
              key={e.id}
              className={`pool-entry ${e.kind === "human" ? "human-entry" : ""}`}
            >
              <div className="entry-meta">
                <span>R{String(e.sharedRound).padStart(2, "0")}</span>
                <strong>{e.agentId}</strong>
                <span>
                  {e.kind === "human" && <Sparkles size={11} />} {kinds[e.kind]}
                </span>
              </div>
              {e.position && (
                <div className="entry-position">
                  ({e.position.x}, {e.position.y})
                </div>
              )}
              <p>{e.summary}</p>
              {e.confidence !== undefined && (
                <span className="confidence">
                  Advisor confidence {e.confidence.toFixed(2)}
                </span>
              )}
              {e.observedRound < e.sharedRound && (
                <span className="history-label">
                  Acquired R{e.observedRound} · shared on joining R
                  {e.sharedRound}
                </span>
              )}
            </article>
          ))
        )}
      </div>
      <p className="pool-rule">
        Evidence must be included before the winning round. Exhausted eligible
        members keep their share.
      </p>
    </section>
  );
}

import { isTerminal } from "../simulation/types";
import type { ExperimentState } from "../simulation/types";
import {
  agentColor,
  actionLabels,
  regimeLabels,
} from "../simulation/presentation";
export function AgentList({
  state,
  selected,
  onSelect,
}: {
  state: ExperimentState;
  selected: string;
  onSelect: (id: string) => void;
}) {
  return (
    <section className="agent-list">
      <div className="rail-heading">
        <h2>Agents</h2>
        <span className="small muted">
          {state.agents.filter((a) => a.activity === "active").length} active /{" "}
          {state.agents.length}
        </span>
      </div>
      {state.agents.map((a) => (
        <button
          className={`agent-row ${selected === a.id ? "selected" : ""}`}
          key={a.id}
          onClick={() => onSelect(a.id)}
          aria-pressed={selected === a.id}
        >
          <span
            className="agent-marker"
            style={{ background: agentColor(a.id) }}
          >
            {a.id}
          </span>
          <span className="agent-details">
            <span className="agent-topline">
              <strong>{a.label}</strong>
              <span className={`membership ${a.collaborationStatus}`}>
                {regimeLabels[a.collaborationStatus]}
              </span>
            </span>
            <span className="agent-meta">
              ({a.position.x}, {a.position.y})<span>·</span>
              {a.lastAction ? actionLabels[a.lastAction] : "Ready"}
            </span>
            <span className="budget-track">
              <span
                style={{
                  width: `${Math.max(0, Math.min(100, state.config.startingBudget > 0 ? (a.budgetRemaining / state.config.startingBudget) * 100 : 0))}%`,
                  background: agentColor(a.id),
                }}
              />
            </span>
            <span className="budget-label">
              <strong>
                {a.budgetRemaining}
                <small> credits</small>
              </strong>
              <span className={a.canAffordDrill === false ? "low-budget" : ""}>
                {a.activity === "inactive"
                  ? "Inactive"
                  : a.canAffordDrill === false
                    ? "Cannot afford drill"
                    : a.canAffordDrill === true
                      ? "Can drill"
                      : "Drill cost unknown"}
              </span>
            </span>
            {a.reason && <span className="agent-reason">{a.reason}</span>}
            {isTerminal(state) && a.finalUtility != null && (
              <span className="retained">
                Final utility: {a.finalUtility.toFixed(2)}
              </span>
            )}
            {a.activity === "inactive" &&
              state.pool.eligibleMemberIds.includes(a.id) && (
                <span className="retained">Prize eligibility retained</span>
              )}
          </span>
        </button>
      ))}
    </section>
  );
}

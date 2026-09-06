import type { ExperimentState } from "../simulation/types";
const colors: Record<string, string> = {
  A: "#a14f35",
  B: "#466b86",
  C: "#8b6086",
  D: "#4a7966",
};
const labels = {
  move: "Move",
  observe: "Observe",
  drill: "Drill",
  join_pool: "Join pool",
  ask_human: "Ask human",
};
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
            style={{ background: colors[a.id] ?? "#65748b" }}
          >
            {a.id}
          </span>
          <span className="agent-details">
            <span className="agent-topline">
              <strong>{a.label}</strong>
              <span className={`membership ${a.collaborationStatus}`}>
                {a.collaborationStatus === "pool" ? "In pool" : "Private"}
              </span>
            </span>
            <span className="agent-meta">
              ({a.position.x}, {a.position.y})<span>·</span>
              {a.lastAction ? labels[a.lastAction] : "Ready"}
            </span>
            <span className="budget-track">
              <span
                style={{
                  width: `${Math.max(0, Math.min(100, (a.budgetRemaining / state.config.startingBudget) * 100))}%`,
                  background: colors[a.id] ?? "#65748b",
                }}
              />
            </span>
            <span className="budget-label">
              <strong>
                {a.budgetRemaining}
                <small> credits</small>
              </strong>
              <span className={a.canAffordDrill === false ? "low-budget" : ""}>
                {a.activity === "exhausted"
                  ? "Exhausted"
                  : a.canAffordDrill === false
                    ? "Cannot afford drill"
                    : a.canAffordDrill === true
                      ? "Can drill"
                      : "Drill cost unknown"}
              </span>
            </span>
            {a.activity === "exhausted" &&
              state.pool.eligibleMemberIds.includes(a.id) && (
                <span className="retained">Prize eligibility retained</span>
              )}
          </span>
        </button>
      ))}
    </section>
  );
}

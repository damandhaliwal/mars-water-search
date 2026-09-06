import {
  ArrowUpRight,
  ScanLine,
  Crosshair,
  Users,
  Sparkles,
  Activity,
} from "lucide-react";
import type { ExperimentEvent } from "../simulation/types";
const icons = {
  move: ArrowUpRight,
  observe: ScanLine,
  drill: Crosshair,
  join_ai_pool: Users,
  choose_human: Sparkles,
  invalid_decision: Activity,
};
export function RecentEvents({ events }: { events: ExperimentEvent[] }) {
  const ordered = [...events].reverse();
  return (
    <section className="recent-events">
      <div className="rail-heading">
        <h2>
          <Activity size={16} />
          Activity log
        </h2>
        <span className="small muted">
          {events.length
            ? `${events.length} entries · every round, every rover`
            : "Every round, every rover"}
        </span>
      </div>
      {ordered.length === 0 ? (
        <p className="small muted">No activity yet. Play or Step to begin.</p>
      ) : (
        <ol className="event-list">
          {ordered.map((e) => {
            const Icon = e.action ? (icons[e.action] ?? Activity) : Activity;
            return (
              <li key={e.id}>
                <span className="event-icon">
                  <Icon size={15} />
                </span>
                <span className="event-round">
                  R{String(e.round).padStart(2, "0")}
                </span>
                <div>
                  <span className="entry-meta">
                    {e.agentId ? `AGENT ${e.agentId}` : "SYSTEM"}
                    {e.action ? ` · ${e.action}` : ""}
                  </span>
                  <p>{e.summary}</p>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

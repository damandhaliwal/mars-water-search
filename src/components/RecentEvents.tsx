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
  join_pool: Users,
  ask_human: Sparkles,
};
export function RecentEvents({ events }: { events: ExperimentEvent[] }) {
  return (
    <section className="recent-events">
      <div className="rail-heading">
        <h2>
          <Activity size={16} />
          Recent activity
        </h2>
        <span className="small muted">Latest resolved actions</span>
      </div>
      <div className="event-strip">
        {events
          .slice(-4)
          .reverse()
          .map((e) => {
            const Icon = e.action ? icons[e.action] : Activity;
            return (
              <article key={e.id}>
                <span className="event-icon">
                  <Icon size={17} />
                </span>
                <div>
                  <span className="entry-meta">
                    ROUND {String(e.round).padStart(2, "0")}
                    {e.agentId && ` · AGENT ${e.agentId}`}
                  </span>
                  <p>{e.summary}</p>
                </div>
              </article>
            );
          })}
      </div>
    </section>
  );
}

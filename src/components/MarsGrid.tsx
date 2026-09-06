import { useId, useState } from "react";
import { Eye, MapPin } from "lucide-react";
import type { BeliefGrid, ExperimentState } from "../simulation/types";

const agentColors: Record<string, string> = {
  A: "#a14f35",
  B: "#466b86",
  C: "#8b6086",
  D: "#4a7966",
};
export function MarsGrid({
  state,
  selected,
  onSelect,
}: {
  state: ExperimentState;
  selected: string;
  onSelect: (id: string) => void;
}) {
  const [reveal, setReveal] = useState(false);
  const [cell, setCell] = useState<{ x: number; y: number } | null>(null);
  const gridId = useId();
  const agent = state.agents.find((a) => a.id === selected);
  const truthVisible = reveal && !!state.groundTruth;
  const belief: BeliefGrid | undefined = truthVisible
    ? state.groundTruth?.intensity
    : selected === "pool"
      ? state.pool.belief
      : agent?.belief;
  const w = state.config.gridWidth,
    h = state.config.gridHeight;
  const matchingGrid =
    belief?.width === w && belief.height === h && belief.values.length === w * h
      ? belief
      : undefined;
  const value = cell ? matchingGrid?.values[cell.y * w + cell.x] : null;
  const visibleMarkers = state.markers.filter(
    (m) =>
      truthVisible ||
      (selected === "pool"
        ? state.pool.memberIds.includes(m.agentId)
        : m.agentId === selected),
  );
  return (
    <section className="map-section" aria-label="Mars exploration map">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Exploration field</p>
          <h2>
            {truthVisible
              ? "Ground truth"
              : selected === "pool"
                ? "Collective belief"
                : `${agent?.label ?? "Agent"}’s belief`}
          </h2>
        </div>
        <span className="map-coordinate-label">
          {w} × {h} cells
        </span>
      </div>
      <div className="map-toolbar">
        <div className="map-tabs" role="group" aria-label="Map view">
          {state.agents.map((a) => (
            <button
              key={a.id}
              aria-pressed={selected === a.id && !truthVisible}
              onClick={() => {
                onSelect(a.id);
                setReveal(false);
              }}
            >
              <span
                style={{ background: agentColors[a.id] ?? "#65748b" }}
                className="tiny-dot"
              />
              {a.id}
            </button>
          ))}
          <button
            aria-pressed={selected === "pool" && !truthVisible}
            onClick={() => {
              onSelect("pool");
              setReveal(false);
            }}
          >
            Pool
          </button>
        </div>
        <button
          className={`truth-button ${truthVisible ? "enabled" : ""}`}
          disabled={!state.groundTruth}
          title={
            state.groundTruth
              ? "Presenter-only intensity map"
              : "Ground truth has not been supplied"
          }
          onClick={() => setReveal(!reveal)}
        >
          <Eye size={14} />
          {truthVisible ? "Hide truth" : "Reveal truth"}
        </button>
      </div>
      <div className={`map-frame ${truthVisible ? "truth-mode" : ""}`}>
        <div className="axis-top">
          <span>00</span>
          <span>X →</span>
          <span>{w - 1}</span>
        </div>
        <svg
          className="mars-map"
          viewBox={`0 0 ${w} ${h}`}
          role="img"
          aria-label={`${truthVisible ? "Ground truth intensity" : selected === "pool" ? "Pool probability of a successful drill" : `${agent?.label} probability of a successful drill`}; ${w} by ${h} grid`}
          onMouseMove={(event) => {
            const rect = event.currentTarget.getBoundingClientRect();
            setCell({
              x: Math.min(
                w - 1,
                Math.max(
                  0,
                  Math.floor(((event.clientX - rect.left) / rect.width) * w),
                ),
              ),
              y: Math.min(
                h - 1,
                Math.max(
                  0,
                  Math.floor(((event.clientY - rect.top) / rect.height) * h),
                ),
              ),
            });
          }}
          onMouseLeave={() => setCell(null)}
        >
          <defs>
            <pattern
              id={gridId}
              width="1"
              height="1"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M 1 0 L 0 0 0 1"
                fill="none"
                stroke="#845438"
                strokeWidth=".035"
                opacity=".3"
              />
            </pattern>
          </defs>
          <rect width={w} height={h} fill="#dfb296" />
          {matchingGrid?.values.map((probability, i) =>
            probability === null ? null : (
              <rect
                key={i}
                x={i % w}
                y={Math.floor(i / w)}
                width="1"
                height="1"
                fill={truthVisible ? "#16768a" : "#174f64"}
                opacity={probability * 0.82}
              />
            ),
          )}
          <rect width={w} height={h} fill={`url(#${gridId})`} />
          {state.agents.map((a) => (
            <polyline
              key={a.id}
              points={a.path
                .map((p) => `${p.x + 0.5},${p.y + 0.5}`)
                .join(" ")}
              fill="none"
              stroke={agentColors[a.id] ?? "#333"}
              strokeWidth=".18"
              strokeDasharray=".45 .35"
              opacity=".85"
            />
          ))}
          {visibleMarkers.map((marker) => (
            <g
              key={marker.id}
              transform={`translate(${marker.position.x + 0.5} ${marker.position.y + 0.5})`}
            >
              <title>
                {marker.kind} at ({marker.position.x}, {marker.position.y})
              </title>
              {marker.kind === "observe" ? (
                <circle r=".3" fill="none" stroke="#554d45" strokeWidth=".12" />
              ) : marker.kind === "dry" ? (
                <path
                  d="M -.4 -.4 L .4 .4 M -.4 .4 L .4 -.4"
                  stroke="#5d332a"
                  strokeWidth=".18"
                />
              ) : (
                <circle
                  r="1.25"
                  fill="none"
                  stroke="#f4ffff"
                  strokeWidth=".25"
                />
              )}
            </g>
          ))}
          {state.agents.map((a) => (
            <g
              key={a.id}
              className="map-agent"
              transform={`translate(${a.position.x + 0.5} ${a.position.y + 0.5})`}
              role="button"
              tabIndex={0}
              aria-label={`Select ${a.label}, position ${a.position.x}, ${a.position.y}`}
              onClick={() => {
                onSelect(a.id);
                setReveal(false);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(a.id);
                  setReveal(false);
                }
              }}
            >
              <title>
                {a.label} · ({a.position.x}, {a.position.y}) ·{" "}
                {a.budgetRemaining} credits
              </title>
              {selected === a.id && !truthVisible && (
                <circle r="1.35" fill="none" stroke="white" strokeWidth=".15" />
              )}
              <circle
                r=".94"
                fill={agentColors[a.id] ?? "#65748b"}
                stroke="white"
                strokeWidth=".15"
              />
              <text
                textAnchor="middle"
                dominantBaseline="central"
                fontSize=".85"
                fontWeight="600"
                fill="white"
              >
                {a.id}
              </text>
            </g>
          ))}
        </svg>
        {!matchingGrid && (
          <div className="map-empty">
            {selected === "pool"
              ? "No collective belief supplied yet"
              : "Belief map unavailable"}
            <span>Agent positions remain visible.</span>
          </div>
        )}
        <div className="axis-bottom">
          <span>Y ↓</span>
          <span>
            {truthVisible
              ? "PRESENTER VIEW · WATER INTENSITY"
              : "BELIEF · NOT GROUND TRUTH"}
          </span>
          <span>{h - 1}</span>
        </div>
      </div>
      <div className="map-legend">
        <div className="probability-legend">
          <span>0</span>
          <div className="legend-ramp" />
          <span>1</span>
          <span>
            {truthVisible ? "Water intensity" : "P(successful drill)"}
          </span>
        </div>
        <span className="cell-readout">
          {cell
            ? `(${cell.x}, ${cell.y}) · ${value == null ? "unknown" : value.toFixed(2)}`
            : "Hover to inspect"}
        </span>
      </div>
      <div className="map-footnote">
        <MapPin size={14} />
        <span>
          {state.round === 0
            ? "All agents start with the same prior. Moving reveals no new evidence."
            : "Positions shown for the presenter. Beliefs and evidence remain agent-specific."}
        </span>
      </div>
      {!truthVisible && agent?.latestInsight && (
        <div className="selected-insight">
          <span className="small-label">
            {agent.latestInsight.source} · acquired R
            {agent.latestInsight.acquiredRound} ·{" "}
            {agent.collaborationStatus === "pool"
              ? "Shared with pool"
              : "Private to " + agent.label}
          </span>
          <p>{agent.latestInsight.summary}</p>
        </div>
      )}
    </section>
  );
}

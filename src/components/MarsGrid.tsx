import { useId, useState } from "react";
import { Eye, MapPin } from "lucide-react";
import { agentColor } from "../simulation/presentation";
import type {
  BeliefGrid,
  ExperimentState,
  GroundTruth,
} from "../simulation/types";

export function MarsGrid({
  state,
  selected,
  onSelect,
  groundTruth,
  onReveal,
  busy,
}: {
  state: ExperimentState;
  selected: string;
  onSelect: (id: string) => void;
  groundTruth: GroundTruth | null;
  onReveal: () => Promise<void>;
  busy: boolean;
}) {
  const [reveal, setReveal] = useState(false);
  const [showPrior, setShowPrior] = useState(false);
  const [showPaths, setShowPaths] = useState(true);
  const [relativeScale, setRelativeScale] = useState(true);
  const [cell, setCell] = useState<{ x: number; y: number } | null>(null);
  const gridId = useId();
  const agent = state.agents.find((a) => a.id === selected);
  const truthVisible = reveal && state.groundTruthAvailable && !!groundTruth;
  const prior = typeof state.config.priorProbability === "number"
    ? state.config.priorProbability : null;
  const belief: BeliefGrid | null | undefined = showPrior && prior !== null
    ? { width: state.config.gridWidth, height: state.config.gridHeight,
        values: Array(state.config.gridWidth * state.config.gridHeight).fill(prior) }
    : truthVisible
    ? groundTruth?.intensity
    : selected === "pool"
      ? state.pool.belief
      : agent?.belief;
  const w = state.config.gridWidth,
    h = state.config.gridHeight;
  // Keep symbols the same visual size when the configured cell count changes.
  const symbolScale = w / 50;
  const matchingGrid =
    belief?.width === w && belief.height === h && belief.values.length === w * h
      ? belief
      : undefined;
  const value = cell ? matchingGrid?.values[cell.y * w + cell.x] : null;
  const present = (matchingGrid?.values ?? []).filter(
    (probability): probability is number => probability !== null,
  );
  const uniform =
    present.length > 0 &&
    Math.max(...present) - Math.min(...present) < 1e-9;
  const visibleMarkers = state.markers.filter(
    (m) =>
      truthVisible ||
      (selected === "pool" || agent?.collaborationStatus === "ai_pool"
        ? state.pool.memberIds.includes(m.agentId)
        : m.agentId === selected),
  );
  const minimum = present.length ? Math.min(...present) : 0;
  const maximum = present.length ? Math.max(...present) : 1;
  const scaled = relativeScale && !truthVisible && !uniform;
  const low = scaled ? minimum : 0;
  const high = scaled ? maximum : 1;
  const peakIndex = matchingGrid?.values.findIndex((v) => v === maximum) ?? -1;
  const peak = peakIndex >= 0 && (!uniform || truthVisible)
    ? { x: peakIndex % w, y: Math.floor(peakIndex / w) } : null;
  const strongest = visibleMarkers.filter((m) => m.kind === "observe" && m.value != null)
    .sort((a, b) => b.value! - a.value!)[0];
  const waterCells = truthVisible ? matchingGrid?.values.filter(
    (v) => v != null && v >= groundTruth!.successThreshold).length ?? 0 : 0;
  const color = (v: number) => {
    const t = Math.max(0, Math.min(1, (v - low) / (high - low || 1)));
    // Opaque sequential colors: no blending into the terrain background.
    return `rgb(${Math.round(242 - t * 222)}, ${Math.round(246 - t * 151)}, ${Math.round(250 - t * 123)})`;
  };
  return (
    <section className="map-section" aria-label="Mars exploration map">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Exploration field</p>
          <h2>
            {showPrior ? "Initial prior" : truthVisible
              ? "Ground truth"
              : selected === "pool"
                ? "Pool belief"
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
              aria-pressed={selected === a.id && !truthVisible && !showPrior}
              onClick={() => {
                onSelect(a.id);
                setReveal(false);
                setShowPrior(false);
              }}
            >
              <span
                style={{ background: agentColor(a.id) }}
                className="tiny-dot"
              />
              {a.id}
            </button>
          ))}
          {state.pool.memberIds.length > 0 && (
            <button
              aria-pressed={selected === "pool" && !truthVisible && !showPrior}
              onClick={() => {
                onSelect("pool");
                setReveal(false);
                setShowPrior(false);
              }}
            >
              Pool
            </button>
          )}
        </div>
        <button
          className="prior-button"
          aria-pressed={showPrior}
          disabled={prior === null}
          onClick={() => { setShowPrior(!showPrior); setReveal(false); }}
        >Initial prior</button>
        <button
          className={`truth-button ${truthVisible ? "enabled" : ""}`}
          disabled={busy || !state.groundTruthAvailable}
          title={
            state.groundTruthAvailable
              ? "Presenter-only intensity map"
              : "Interactive adviser runs reveal water after the experiment ends"
          }
          onClick={() => {
            setShowPrior(false);
            if (truthVisible) setReveal(false);
            else if (groundTruth) setReveal(true);
            else
              void onReveal()
                .then(() => setReveal(true))
                .catch(() => {});
          }}
        >
          <Eye size={14} />
          {truthVisible ? "Hide truth" : "Reveal truth"}
        </button>
      </div>
      <div className="map-summary" aria-label="Map summary">
        <div><span>Shared starting prior</span><strong>{prior === null ? "Unavailable" : prior.toFixed(3)}</strong><small>Same score at every cell</small></div>
        <div><span>{truthVisible ? "Peak water intensity" : "Current belief range"}</span><strong>{truthVisible ? maximum.toFixed(3) : `${minimum.toFixed(3)} – ${maximum.toFixed(3)}`}</strong><small>{truthVisible && peak ? `Peak at (${peak.x}, ${peak.y})` : uniform ? "Flat map · no preferred target" : "Relative confidence, not probability"}</small></div>
        <div><span>{truthVisible ? "Drillable water" : "Strongest measured scan"}</span><strong>{truthVisible ? `${waterCells} cells` : strongest ? strongest.value!.toFixed(3) : "No scans"}</strong><small>{truthVisible ? `Intensity ≥ ${groundTruth!.successThreshold}` : strongest ? `At (${strongest.position.x}, ${strongest.position.y}) · noisy signal` : "Observe to gather evidence"}</small></div>
      </div>
      <div className="map-display-options">
        <label><input type="checkbox" checked={showPaths} onChange={(e) => setShowPaths(e.target.checked)} /> Rover paths</label>
        <label><input type="checkbox" checked={relativeScale} disabled={truthVisible || showPrior} onChange={(e) => setRelativeScale(e.target.checked)} /> Enhance belief contrast</label>
        <span>{truthVisible ? "Cyan outline = successful drill zone" : showPrior ? "Initial prior · fixed baseline" : "Crosshair = highest belief, not confirmed water"}</span>
      </div>
      <div className={`map-frame ${truthVisible ? "truth-mode" : ""}`}>
        <div className="axis-top">
          <span>00</span>
          <span>X →</span>
          <span>{w - 1}</span>
        </div>
        <svg
          className="mars-map"
          style={{ aspectRatio: `${w} / ${h}` }}
          viewBox={`0 0 ${w} ${h}`}
          role="img"
          aria-label={`${showPrior ? "Initial prior" : truthVisible ? "Ground truth intensity" : selected === "pool" ? "Pool belief score" : `${agent?.label} belief score`}; ${w} by ${h} grid`}
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
                stroke="#738899"
                strokeWidth=".035"
                opacity=".22"
              />
            </pattern>
          </defs>
          <rect width={w} height={h} fill="#f2f6fa" />
          {matchingGrid?.values.map((probability, i) =>
            probability === null ? null : (
              <rect
                key={i}
                x={i % w}
                y={Math.floor(i / w)}
                width="1"
                height="1"
                fill={color(probability)}
                data-water-cell={truthVisible && probability >= groundTruth!.successThreshold ? "true" : undefined}
                stroke={truthVisible && probability >= groundTruth!.successThreshold ? "#25e5dc" : "none"}
                strokeWidth=".12"
              />
            ),
          )}
          <rect width={w} height={h} fill={`url(#${gridId})`} />
          {showPaths && state.agents.map((a) => (
            <polyline
              data-agent-path={a.id}
              key={a.id}
              points={a.path.map((p) => `${p.x + 0.5},${p.y + 0.5}`).join(" ")}
              fill="none"
              stroke={agentColor(a.id)}
              strokeWidth={0.18 * symbolScale}
              strokeDasharray={`${0.45 * symbolScale} ${0.35 * symbolScale}`}
              opacity={selected === a.id ? 0.9 : 0.25}
            />
          ))}
          {peak && !showPrior && (
            <g data-map-target="peak" transform={`translate(${peak.x + 0.5} ${peak.y + 0.5}) scale(${symbolScale})`}>
              <title>{truthVisible ? "Water peak" : "Highest belief"} at ({peak.x}, {peak.y}): {maximum.toFixed(3)}</title>
              <circle r="1.45" fill="none" stroke="#fff" strokeWidth=".4" />
              <path d="M -2 0 H 2 M 0 -2 V 2" stroke={truthVisible ? "#03d6d0" : "#b75817"} strokeWidth=".22" />
            </g>
          )}
          {!showPrior && visibleMarkers.map((marker) => (
            <g
              key={marker.id}
              transform={`translate(${marker.position.x + 0.5} ${marker.position.y + 0.5}) scale(${symbolScale})`}
            >
              <title>
                {marker.kind} at ({marker.position.x}, {marker.position.y}){marker.value != null ? ` · ${marker.value.toFixed(3)}` : ""}
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
              transform={`translate(${a.position.x + 0.5} ${a.position.y + 0.5}) scale(${symbolScale})`}
              role="button"
              tabIndex={0}
              aria-label={`Select ${a.label}, position ${a.position.x}, ${a.position.y}`}
              onClick={() => {
                onSelect(a.id);
                setReveal(false);
                setShowPrior(false);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(a.id);
                  setReveal(false);
                setShowPrior(false);
                }
              }}
            >
              <title>
                {a.label} · ({a.position.x}, {a.position.y}) ·{" "}
                {a.budgetRemaining} credits
              </title>
              {selected === a.id && !truthVisible && !showPrior && (
                <circle
                  className="agent-selection"
                  r="1.35"
                  fill="none"
                  stroke="white"
                  strokeWidth=".15"
                />
              )}
              <circle
                className="agent-body"
                r=".94"
                fill={agentColor(a.id)}
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
          <span>{low.toFixed(3)}</span>
          <div className="legend-ramp" />
          <span>{high.toFixed(3)}</span>
          <span>{truthVisible ? "Water intensity" : scaled ? "Belief · relative scale" : "Belief · fixed scale"}</span>
        </div>
        <span className="cell-readout">
          {uniform
            ? `Uniform belief · ${present[0].toFixed(2)} everywhere`
            : cell
              ? `(${cell.x}, ${cell.y}) · ${value == null ? "unknown" : value.toFixed(3)}`
              : "Hover to inspect"}
        </span>
      </div>
      <p className="map-key">○ Observation · × Dry drill · ⊕ {truthVisible ? "Water peak" : "Highest belief"}. {peak && `(${peak.x}, ${peak.y}) · ${maximum.toFixed(3)}${!truthVisible ? " · first cell if tied" : ""}`}</p>
      {!truthVisible && <p className="truth-help">To see the actual water deposit, select <strong>Reveal truth</strong>{!state.groundTruthAvailable ? " after the experiment ends" : " above"}. Belief and sensor readings are not the water map.</p>}
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
            {agent.collaborationStatus === "ai_pool"
              ? "Shared with pool"
              : "Private to " + agent.label}
          </span>
          <p>{agent.latestInsight.summary}</p>
        </div>
      )}
    </section>
  );
}

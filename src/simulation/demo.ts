import type {
  AgentAction,
  AgentState,
  BeliefGrid,
  ExperimentState,
  PoolEvent,
  Position,
} from "./types";

// Hand-authored display swatches. Each digit is a probability in tenths;
// each swatch pixel covers a 5×5 block. These are NOT generated water or inference.
const swatches = {
  prior: [
    "1111111111",
    "1111111111",
    "1111111111",
    "1111111111",
    "1111111111",
    "1111111111",
    "1111111111",
    "1111111111",
    "1111111111",
    "1111111111",
  ],
  a: [
    "1111111111",
    "1122111111",
    "1233211111",
    "1233211111",
    "1122111111",
    "1111111111",
    "1111111111",
    "1111111111",
    "1111111111",
    "1111111111",
  ],
  b: [
    "1111111111",
    "1112211111",
    "1123321111",
    "1124432111",
    "1113321111",
    "1112211111",
    "1111111111",
    "1111111111",
    "1111111111",
    "1111111111",
  ],
  c: [
    "1111111111",
    "1111222111",
    "1112343211",
    "1113575311",
    "1112464211",
    "1111232111",
    "1111111111",
    "1111111111",
    "1111111111",
    "1111111111",
  ],
  d: [
    "1111111111",
    "1111111111",
    "1111111111",
    "1111112211",
    "1111123321",
    "1111234431",
    "1111123321",
    "1111112211",
    "1111111111",
    "1111111111",
  ],
  pool: [
    "1111111111",
    "1111122111",
    "1112344311",
    "1113578311",
    "1112355311",
    "1111223211",
    "1111112211",
    "1111111111",
    "1111111111",
    "1111111111",
  ],
  truth: [
    "0000000000",
    "0000000000",
    "0000035200",
    "0000069700",
    "0000036400",
    "0000000000",
    "0000000000",
    "0000000000",
    "0000000000",
    "0000000000",
  ],
};
function raster(key: keyof typeof swatches): BeliefGrid {
  const rows = swatches[key];
  return {
    width: 50,
    height: 50,
    values: Array.from(
      { length: 2500 },
      (_, i) =>
        Number(rows[Math.floor(i / 50 / 5)][Math.floor((i % 50) / 5)]) / 10,
    ),
  };
}
const maps = Object.fromEntries(
  Object.keys(swatches).map((key) => [
    key,
    raster(key as keyof typeof swatches),
  ]),
) as Record<keyof typeof swatches, BeliefGrid>;
type Cue = {
  action: AgentAction;
  at: Position;
  remaining: number;
  cost: number;
  map: keyof typeof swatches;
  pool?: boolean;
  detail: string;
};
const cue = (
  action: AgentAction,
  x: number,
  y: number,
  remaining: number,
  cost: number,
  map: Cue["map"],
  detail: string,
  pool = false,
): Cue => ({ action, at: { x, y }, remaining, cost, map, detail, pool });
// Every row is a complete authored round. Costs and remaining balances are
// literal presentation values; no action selection or simulation is performed.
const script: (Cue | null)[][] = [
  [
    cue("move", 10, 8, 280, 20, "prior", "Moved to (10, 8)."),
    cue("move", 18, 14, 276, 24, "prior", "Moved to (18, 14)."),
    cue("move", 18, 26, 260, 40, "prior", "Moved to (18, 26)."),
    cue("move", 37, 32, 278, 22, "prior", "Moved to (37, 32)."),
  ],
  [
    cue("observe", 10, 8, 265, 35, "a", "Observed a weak local signal: 0.24."),
    cue("observe", 18, 14, 261, 39, "b", "Observed a local signal: 0.43."),
    cue("observe", 18, 26, 245, 55, "b", "Observed a local signal: 0.36."),
    cue("observe", 37, 32, 263, 37, "d", "Observed a local signal: 0.41."),
  ],
  [
    cue("move", 12, 12, 253, 47, "a", "Moved to (12, 12)."),
    cue(
      "join_pool",
      18,
      14,
      256,
      44,
      "b",
      "Joined the pool; historical observation shared.",
      true,
    ),
    cue(
      "ask_human",
      18,
      26,
      85,
      215,
      "c",
      "Purchased private expert guidance for 160 credits.",
    ),
    cue("move", 35, 28, 251, 49, "d", "Moved to (35, 28)."),
  ],
  [
    cue("drill", 12, 12, 153, 147, "a", "Drilled at (12, 12). Result: dry."),
    cue("move", 22, 18, 240, 60, "b", "Moved to (22, 18).", true),
    cue(
      "join_pool",
      18,
      26,
      80,
      220,
      "pool",
      "Joined the pool; past observation and human advice shared.",
      true,
    ),
    cue("observe", 35, 28, 236, 64, "d", "Observed a local signal: 0.32."),
  ],
  [
    cue("move", 18, 16, 133, 167, "a", "Moved to (18, 16)."),
    cue(
      "observe",
      22,
      18,
      225,
      75,
      "pool",
      "Observed a local signal: 0.57.",
      true,
    ),
    cue("move", 28, 16, 40, 260, "pool", "Moved to (28, 16).", true),
    cue(
      "join_pool",
      35,
      28,
      231,
      69,
      "pool",
      "Joined the pool; two historical observations shared.",
      true,
    ),
  ],
  [
    cue("observe", 18, 16, 118, 182, "a", "Observed a local signal: 0.29."),
    cue("move", 26, 18, 217, 83, "pool", "Moved to (26, 18).", true),
    cue(
      "observe",
      28,
      16,
      25,
      275,
      "pool",
      "Observed an elevated signal: 0.68.",
      true,
    ),
    cue(
      "move",
      31,
      18,
      203,
      97,
      "pool",
      "Moved toward the region identified by C’s expert advice.",
      true,
    ),
  ],
  [
    cue("move", 20, 20, 106, 194, "a", "Moved to (20, 20)."),
    cue(
      "observe",
      26,
      18,
      202,
      98,
      "pool",
      "Observed a local signal: 0.62.",
      true,
    ),
    cue("move", 30, 19, 15, 285, "pool", "Moved to (30, 19).", true),
    cue(
      "observe",
      31,
      18,
      188,
      112,
      "pool",
      "Observed a strong signal: 0.81.",
      true,
    ),
  ],
  [
    cue("observe", 20, 20, 91, 209, "a", "Observed a local signal: 0.31."),
    cue("move", 30, 18, 194, 106, "pool", "Moved to (30, 18).", true),
    cue(
      "observe",
      30,
      19,
      0,
      300,
      "pool",
      "Observed signal 0.76. Budget exhausted; prize eligibility retained.",
      true,
    ),
    cue(
      "move",
      32,
      18,
      186,
      114,
      "pool",
      "Moved to (32, 18), ready to drill.",
      true,
    ),
  ],
  [
    cue("move", 22, 20, 87, 213, "a", "Moved to (22, 20)."),
    cue(
      "observe",
      30,
      18,
      179,
      121,
      "pool",
      "Observed a local signal: 0.73.",
      true,
    ),
    null,
    cue(
      "drill",
      32,
      18,
      86,
      214,
      "pool",
      "Found qualifying water at (32, 18).",
      true,
    ),
  ],
];
const evidence: PoolEvent[] = [
  {
    id: "pb",
    evidenceId: "b-r2",
    agentId: "B",
    kind: "observation",
    observedRound: 2,
    sharedRound: 3,
    position: { x: 18, y: 14 },
    summary:
      "Local signal: 0.43. Historical observation contributed on joining.",
  },
  {
    id: "pc",
    evidenceId: "c-r2",
    agentId: "C",
    kind: "observation",
    observedRound: 2,
    sharedRound: 4,
    position: { x: 18, y: 26 },
    summary:
      "Local signal: 0.36. Historical observation contributed on joining.",
  },
  {
    id: "ph",
    evidenceId: "c-r3",
    agentId: "C",
    kind: "human",
    observedRound: 3,
    sharedRound: 4,
    position: { x: 31, y: 18 },
    summary:
      "The region around (31, 18) looks promising. Prioritize this area over the southern sector. Paid privately by C: 160 credits.",
    confidence: 0.74,
  },
  {
    id: "pd2",
    evidenceId: "d-r2",
    agentId: "D",
    kind: "observation",
    observedRound: 2,
    sharedRound: 5,
    position: { x: 37, y: 32 },
    summary:
      "Local signal: 0.41. Historical observation contributed on joining.",
  },
  {
    id: "pd4",
    evidenceId: "d-r4",
    agentId: "D",
    kind: "observation",
    observedRound: 4,
    sharedRound: 5,
    position: { x: 35, y: 28 },
    summary:
      "Local signal: 0.32. Historical observation contributed on joining.",
  },
  {
    id: "pb5",
    evidenceId: "b-r5",
    agentId: "B",
    kind: "observation",
    observedRound: 5,
    sharedRound: 5,
    position: { x: 22, y: 18 },
    summary: "Local signal: 0.57.",
  },
  {
    id: "pc6",
    evidenceId: "c-r6",
    agentId: "C",
    kind: "observation",
    observedRound: 6,
    sharedRound: 6,
    position: { x: 28, y: 16 },
    summary: "Elevated local signal: 0.68.",
  },
  {
    id: "pb7",
    evidenceId: "b-r7",
    agentId: "B",
    kind: "observation",
    observedRound: 7,
    sharedRound: 7,
    position: { x: 26, y: 18 },
    summary: "Local signal: 0.62.",
  },
  {
    id: "pd7",
    evidenceId: "d-r7",
    agentId: "D",
    kind: "observation",
    observedRound: 7,
    sharedRound: 7,
    position: { x: 31, y: 18 },
    summary: "Strong local signal: 0.81.",
  },
  {
    id: "pc8",
    evidenceId: "c-r8",
    agentId: "C",
    kind: "observation",
    observedRound: 8,
    sharedRound: 8,
    position: { x: 30, y: 19 },
    summary:
      "Strong local signal: 0.76. C is now exhausted, but remains eligible.",
  },
  {
    id: "pb9",
    evidenceId: "b-r9",
    agentId: "B",
    kind: "observation",
    observedRound: 9,
    sharedRound: 9,
    position: { x: 30, y: 18 },
    summary: "Local signal: 0.73.",
  },
  {
    id: "pd9",
    evidenceId: "d-r9",
    agentId: "D",
    kind: "drill",
    observedRound: 9,
    sharedRound: 9,
    position: { x: 32, y: 18 },
    summary:
      "Water confirmed. Local intensity: 0.90; qualifying threshold: 0.70.",
  },
];

export function createDemoFrames(): ExperimentState[] {
  const starts = [
    { x: 4, y: 4 },
    { x: 10, y: 10 },
    { x: 8, y: 36 },
    { x: 40, y: 40 },
  ];
  const initial: ExperimentState = {
    experimentId: "MWS-001",
    source: "demo",
    status: "idle",
    round: 0,
    maxRounds: 9,
    config: {
      gridWidth: 50,
      gridHeight: 50,
      numberOfAgents: 4,
      numberOfWaterDeposits: 1,
      startingBudget: 300,
      discoveryReward: 1000,
    },
    agents: starts.map((position, i): AgentState => ({
      id: "ABCD"[i],
      label: `Agent ${"ABCD"[i]}`,
      position,
      budgetRemaining: 300,
      accumulatedCost: 0,
      activity: "active",
      collaborationStatus: "private",
      lastAction: null,
      canAffordDrill: true,
      belief: maps.prior,
      path: [position],
    })),
    pool: {
      memberIds: [],
      eligibleMemberIds: [],
      eligibilityRound: 1,
      discoveryReward: 1000,
      rewardPerMember: null,
      events: [],
    },
    markers: [],
    recentEvents: [
      {
        id: "start",
        round: 0,
        summary:
          "Four private agents. Identical priors. Individual budgets of 300 credits.",
      },
    ],
  };
  const frames = [initial];
  const memberships = [
    [],
    [],
    ["B"],
    ["B", "C"],
    ["B", "C", "D"],
    ["B", "C", "D"],
    ["B", "C", "D"],
    ["B", "C", "D"],
    ["B", "C", "D"],
  ];
  const shares = [
    null,
    null,
    1000,
    500,
    1000 / 3,
    1000 / 3,
    1000 / 3,
    1000 / 3,
    1000 / 3,
  ];
  script.forEach((roundCues, index) => {
    const previous = frames[index];
    const round = index + 1;
    const state = structuredClone(previous);
    state.round = round;
    state.status = round === 9 ? "success" : "paused";
    state.agents = roundCues.map((entry, i) => {
      const prior = state.agents[i];
      if (!entry) return prior;
      state.recentEvents.push({
        id: `r${round}-${prior.id}`,
        round,
        agentId: prior.id,
        action: entry.action,
        summary: entry.detail,
      });
      if (entry.action === "observe" || entry.action === "drill")
        state.markers.push({
          id: `m${round}-${prior.id}`,
          agentId: prior.id,
          position: entry.at,
          kind:
            entry.action === "observe"
              ? "observe"
              : round === 9
                ? "water"
                : "dry",
        });
      return {
        ...prior,
        position: entry.at,
        budgetRemaining: entry.remaining,
        accumulatedCost: entry.cost,
        activity: entry.remaining === 0 ? "exhausted" : "active",
        collaborationStatus: entry.pool ? "pool" : "private",
        lastAction: entry.action,
        canAffordDrill: entry.remaining >= 100,
        belief: maps[entry.map],
        path: entry.action === "move" ? [...prior.path, entry.at] : prior.path,
      };
    });
    state.pool = {
      memberIds: memberships[index],
      eligibleMemberIds: memberships[index],
      eligibilityRound: round === 9 ? 9 : round + 1,
      discoveryReward: 1000,
      rewardPerMember: shares[index],
      events: evidence.filter((e) => e.sharedRound <= round),
      belief: round >= 4 ? maps.pool : round === 3 ? maps.b : undefined,
    };
    if (round >= 3)
      state.agents[2].latestInsight = {
        source: "Human input",
        acquiredRound: 3,
        summary:
          "The region around (31, 18) looks promising. Advisor confidence: 0.74. C paid 160 credits.",
      };
    if (round === 9) {
      state.winner = {
        agentId: "D",
        position: { x: 32, y: 18 },
        status: "pool",
        recipientIds: ["B", "C", "D"],
        discoveryReward: 1000,
        rewardPerRecipient: 1000 / 3,
        payouts: [
          { agentId: "A", reward: 0, totalCost: 213, utility: -213 },
          {
            agentId: "B",
            reward: 333.3333333333333,
            totalCost: 121,
            utility: 212.3333333333333,
          },
          {
            agentId: "C",
            reward: 333.3333333333333,
            totalCost: 300,
            utility: 33.3333333333333,
          },
          {
            agentId: "D",
            reward: 333.3333333333333,
            totalCost: 214,
            utility: 119.3333333333333,
          },
        ],
      };
      state.groundTruth = { intensity: maps.truth, successThreshold: 0.7 };
    }
    frames.push(state);
  });
  return frames;
}

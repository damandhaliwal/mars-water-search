// HTTP response fixtures for tests only. These are never selectable runtime policies.
import type {
  ExperimentConfig,
  ExperimentState,
  GroundTruth,
  Health,
  HumanRequest,
  Payout,
} from "../simulation/types";
export const config: ExperimentConfig = {
  seed: 42,
  gridWidth: 8,
  gridHeight: 6,
  numberOfAgents: 2,
  numberOfWaterDeposits: 1,
  startingBudget: 300,
  discoveryReward: 1000,
  humanCost: 150,
  humanQuality: 0.5,
  humanMode: "interactive",
  treatment: "free_choice",
  maxRounds: 100,
  observationNoise: 0.2,
  moveCostPerCell: 1,
};
export const health: Health = {
  status: "ok",
  geminiConfigured: true,
  model: "gemini-test-flash",
};
export function snapshot(
  overrides: Partial<ExperimentState> = {},
): ExperimentState {
  return {
    experimentId: "test-run",
    source: "backend",
    status: "idle",
    round: 0,
    maxRounds: 100,
    config: { ...config },
    agents: ["A", "B"].map((id, index) => ({
      id,
      label: `Agent ${id}`,
      position: { x: index + 1, y: 2 },
      budgetRemaining: 300,
      accumulatedCost: 0,
      activity: "active",
      collaborationStatus: "private",
      lastAction: null,
      reason: null,
      canAffordDrill: true,
      belief: { width: 8, height: 6, values: Array(48).fill(0.1) },
      latestInsight: null,
      finalReward: 0,
      finalUtility: 0,
      path: [
        { x: index, y: 1 },
        { x: index + 1, y: 2 },
      ],
    })),
    pool: {
      memberIds: [],
      eligibleMemberIds: [],
      eligibilityRound: 1,
      discoveryReward: 1000,
      rewardPerMember: null,
      events: [],
      belief: null,
    },
    markers: [],
    recentEvents: [
      {
        id: "created",
        round: 0,
        agentId: null,
        action: null,
        summary: "Experiment created",
      },
    ],
    winner: null,
    results: null,
    failureReason: null,
    groundTruthAvailable: false,
    ...overrides,
  };
}
export const payouts: Payout[] = [
  { agentId: "A", regime: "private", reward: 0, totalCost: 100, utility: -100 },
  {
    agentId: "B",
    regime: "human_assisted",
    reward: 0,
    totalCost: 250,
    utility: -250,
  },
];
export const terminal = () =>
  snapshot({
    status: "failure",
    round: 100,
    groundTruthAvailable: true,
    failureReason: "Round limit reached",
    results: payouts,
    agents: snapshot().agents.map((agent, index) => ({
      ...agent,
      collaborationStatus: payouts[index].regime,
      accumulatedCost: payouts[index].totalCost,
      budgetRemaining: config.startingBudget - payouts[index].totalCost,
      canAffordDrill: config.startingBudget - payouts[index].totalCost >= 100,
      finalReward: payouts[index].reward,
      finalUtility: payouts[index].utility,
    })),
  });
export const groundTruth: GroundTruth = {
  intensity: { width: 8, height: 6, values: Array(48).fill(0.8) },
  successThreshold: 0.75,
};
export const humanRequest = (
  id = "request-a",
  agentId = "A",
): HumanRequest => ({
  id,
  agentId,
  round: 1,
  cost: 150,
  prior: { width: 2, height: 2, values: [0.2, 0.4, 0.6, 0.8] },
  gridWidth: 8,
  gridHeight: 6,
});
export const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });

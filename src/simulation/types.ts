export type Position = { x: number; y: number };
/** Row-major values[y * width + x]. null means unavailable, not zero. */
export type BeliefGrid = {
  width: number;
  height: number;
  values: (number | null)[];
};
export type AgentAction =
  "move" | "observe" | "drill" | "join_pool" | "ask_human";
export type AgentState = {
  id: string;
  label: string;
  position: Position;
  budgetRemaining: number;
  accumulatedCost: number;
  activity: "active" | "exhausted";
  collaborationStatus: "private" | "pool";
  lastAction: AgentAction | null;
  canAffordDrill?: boolean;
  belief?: BeliefGrid;
  latestInsight?: { summary: string; source: string; acquiredRound: number };
  path: Position[];
};
export type EvidenceKind =
  "observation" | "human" | "drill" | "location" | "belief";
export type PoolEvent = {
  id: string;
  evidenceId: string;
  agentId: string;
  kind: EvidenceKind;
  observedRound: number;
  sharedRound: number;
  position?: Position;
  summary: string;
  confidence?: number;
};
export type ExperimentEvent = {
  id: string;
  round: number;
  agentId?: string;
  action?: AgentAction;
  summary: string;
};
export type MapMarker = {
  id: string;
  agentId: string;
  position: Position;
  kind: "observe" | "dry" | "water";
};
export type PoolState = {
  memberIds: string[];
  /** Membership and prize eligibility are intentionally separate. */
  eligibleMemberIds: string[];
  eligibilityRound: number;
  discoveryReward: number;
  rewardPerMember: number | null;
  events: PoolEvent[];
  belief?: BeliefGrid;
};
export type ExperimentConfig = {
  gridWidth: number;
  gridHeight: number;
  numberOfAgents: number;
  /** Omit if the provider does not disclose the actual count. */
  numberOfWaterDeposits?: number;
  startingBudget: number;
  discoveryReward: number;
};
export type WinnerState = {
  agentId: string;
  position: Position;
  status: "private" | "pool";
  recipientIds: string[];
  discoveryReward: number;
  rewardPerRecipient: number;
  payouts: {
    agentId: string;
    reward: number;
    totalCost: number;
    utility: number;
  }[];
};
export type ExperimentState = {
  experimentId: string;
  source: "demo" | "backend";
  status: "idle" | "running" | "paused" | "success" | "failure";
  round: number;
  maxRounds?: number;
  config: ExperimentConfig;
  agents: AgentState[];
  pool: PoolState;
  markers: MapMarker[];
  recentEvents: ExperimentEvent[];
  winner?: WinnerState;
  failureReason?: string;
  /** Explicitly authorized presenter data, never required by the UI. */
  groundTruth?: { intensity: BeliefGrid; successThreshold: number };
};

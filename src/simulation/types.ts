export type Position = { x: number; y: number };
/** Row-major values[y * width + x]. null means unavailable, not zero. */
export type BeliefGrid = {
  width: number;
  height: number;
  values: (number | null)[];
};
export type Regime = "private" | "ai_pool" | "human_assisted";
export type AgentAction =
  | "move"
  | "observe"
  | "drill"
  | "join_ai_pool"
  | "choose_human"
  | "invalid_decision";
export type AgentState = {
  id: string;
  label: string;
  position: Position;
  budgetRemaining: number;
  accumulatedCost: number;
  activity: "active" | "inactive";
  collaborationStatus: Regime;
  lastAction?: AgentAction | null;
  reason?: string | null;
  finalReward?: number;
  finalUtility?: number;
  canAffordDrill?: boolean;
  belief?: BeliefGrid | null;
  latestInsight?: {
    summary: string;
    source: string;
    acquiredRound: number;
  } | null;
  path: Position[];
};
export type EvidenceKind =
  | "observation"
  | "human"
  | "drill"
  | "location"
  | "belief";
export type PoolEvent = {
  id: string;
  evidenceId: string;
  agentId: string;
  kind: EvidenceKind;
  observedRound: number;
  sharedRound: number;
  position?: Position | null;
  summary: string;
  confidence?: number | null;
};
export type ExperimentEvent = {
  id: string;
  round: number;
  agentId?: string | null;
  action?: AgentAction | null;
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
  eligibleMemberIds: string[];
  eligibilityRound: number;
  discoveryReward: number;
  rewardPerMember?: number | null;
  events: PoolEvent[];
  belief?: BeliefGrid | null;
};
export type ExperimentConfig = {
  [key: string]: unknown;
  seed: number;
  gridWidth: number;
  gridHeight: number;
  numberOfAgents: number;
  numberOfWaterDeposits: number;
  startingBudget: number;
  discoveryReward: number;
  humanCost: number;
  humanQuality: number;
  humanMode: "simulated" | "interactive";
  treatment:
    | "free_choice"
    | "solo_only"
    | "ai_collab_available"
    | "human_available";
  maxRounds: number;
};
export type Payout = {
  agentId: string;
  regime: Regime;
  reward: number;
  totalCost: number;
  utility: number;
};
export type WinnerState = {
  agentId: string;
  position: Position;
  status: Regime;
  intensity: number;
  recipientIds: string[];
  discoveryReward: number;
  rewardPerRecipient: number;
  payouts: Payout[];
};
export type ProviderFailure = {
  message: string;
  agentIds: string[];
  retryAt?: number | null;
  failures: {
    agentId: string;
    category: string;
    httpStatus?: number | null;
  }[];
};
export type ExperimentState = {
  experimentId: string;
  source: "backend";
  status:
    | "idle"
    | "running"
    | "paused"
    | "awaiting_human"
    | "awaiting_api"
    | "success"
    | "failure";
  round: number;
  maxRounds?: number;
  config: ExperimentConfig;
  agents: AgentState[];
  pool: PoolState;
  markers: MapMarker[];
  recentEvents: ExperimentEvent[];
  winner?: WinnerState | null;
  results?: Payout[] | null;
  failureReason?: string | null;
  providerFailure?: ProviderFailure | null;
  groundTruthAvailable: boolean;
};
export type GroundTruth = { intensity: BeliefGrid; successThreshold: number };
export type Health = { status: "ok"; geminiConfigured: boolean; model: string };
export type HumanRequest = {
  id: string;
  agentId: string;
  round: number;
  cost: number;
  prior: BeliefGrid;
  gridWidth: number;
  gridHeight: number;
};
export type HumanResponse = {
  requestId: string;
  x: number;
  y: number;
  note: string;
};
export type FinalResult = { results: Payout[]; winner?: WinnerState | null };
export const isTerminal = (state: ExperimentState | null) =>
  state?.status === "success" || state?.status === "failure";

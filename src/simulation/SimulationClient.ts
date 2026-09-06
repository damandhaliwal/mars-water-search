import type {
  ExperimentConfig,
  ExperimentState,
  FinalResult,
  GroundTruth,
  Health,
  HumanRequest,
  HumanResponse,
} from "./types";

export type ReplayState = {
  rounds: ExperimentState[];
  index: number;
  playing: boolean;
  /** Live run stashed on entry; restored on exit. */
  live: ExperimentState | null;
};
export type ClientSnapshot = {
  state: ExperimentState | null;
  config: ExperimentConfig | null;
  health: Health | null;
  busy: boolean;
  playing: boolean;
  error: string | null;
  humanRequests: HumanRequest[];
  groundTruth: GroundTruth | null;
  replay: ReplayState | null;
};
export interface SimulationClient {
  getSnapshot(): ClientSnapshot;
  subscribe(callback: () => void): () => void;
  initialize(): Promise<void>;
  create(config: ExperimentConfig): Promise<void>;
  getExperimentState(): Promise<void>;
  start(): void;
  pause(): void;
  step(): Promise<void>;
  reset(config?: ExperimentConfig): Promise<void>;
  refreshHumanRequests(): Promise<void>;
  submitHumanResponse(response: HumanResponse): Promise<void>;
  revealGroundTruth(): Promise<void>;
  getResults(): Promise<FinalResult>;
  enterReplay(): Promise<void>;
  exitReplay(): void;
  replayStep(delta: 1 | -1): void;
  dispose(): void;
}

import type { ExperimentConfig, ExperimentState } from "./types";

export type Unsubscribe = () => void;
export interface SimulationClient {
  getExperimentState(): Promise<ExperimentState>;
  start(): Promise<void>;
  pause(): Promise<void>;
  step(): Promise<void>;
  reset(config?: ExperimentConfig): Promise<void>;
  subscribe(callback: (state: ExperimentState) => void): Unsubscribe;
  dispose(): void;
}

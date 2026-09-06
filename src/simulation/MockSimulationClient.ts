import { createDemoFrames } from "./demo";
import type { SimulationClient } from "./SimulationClient";
import type { ExperimentState } from "./types";

/** A fixture player only. Advancing selects the next authored snapshot. */
export class MockSimulationClient implements SimulationClient {
  private readonly frames = createDemoFrames();
  private index = 0;
  private state = structuredClone(this.frames[0]);
  private listeners = new Set<(state: ExperimentState) => void>();
  private timer: ReturnType<typeof setInterval> | undefined;

  async getExperimentState() {
    return structuredClone(this.state);
  }
  subscribe(callback: (state: ExperimentState) => void) {
    this.listeners.add(callback);
    return () => {
      this.listeners.delete(callback);
    };
  }
  private emit() {
    this.listeners.forEach((callback) => callback(structuredClone(this.state)));
  }
  private stopTimer() {
    clearInterval(this.timer);
    this.timer = undefined;
  }
  private advance() {
    if (this.index >= this.frames.length - 1) return;
    const running = this.timer !== undefined;
    this.state = structuredClone(this.frames[++this.index]);
    if (this.state.status === "success" || this.state.status === "failure")
      this.stopTimer();
    else this.state.status = running ? "running" : "paused";
    this.emit();
  }
  async start() {
    if (this.timer !== undefined || this.index === this.frames.length - 1)
      return;
    this.state.status = "running";
    this.timer = setInterval(() => this.advance(), 1800);
    this.emit();
  }
  async pause() {
    this.stopTimer();
    if (this.state.status === "running") {
      this.state.status = "paused";
      this.emit();
    }
  }
  async step() {
    this.stopTimer();
    this.advance();
  }
  async reset() {
    this.stopTimer();
    this.index = 0;
    this.state = structuredClone(this.frames[0]);
    this.emit();
  }
  dispose() {
    this.stopTimer();
    this.listeners.clear();
  }
}

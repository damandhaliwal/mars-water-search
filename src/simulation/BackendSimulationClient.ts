import type { ClientSnapshot, SimulationClient } from "./SimulationClient";
import {
  isTerminal,
  type ExperimentConfig,
  type ExperimentState,
  type FinalResult,
  type GroundTruth,
  type Health,
  type HumanRequest,
  type HumanResponse,
} from "./types";

/** HTTP owns facts; this client only schedules serial rounds and presenter requests. */
export class BackendSimulationClient implements SimulationClient {
  private snapshot: ClientSnapshot = {
    state: null,
    config: null,
    health: null,
    busy: false,
    playing: false,
    error: null,
    humanRequests: [],
    groundTruth: null,
    replay: null,
  };
  private listeners = new Set<() => void>();
  private initialization?: Promise<void>;
  private timer?: ReturnType<typeof setTimeout>;
  private disposed = false;

  constructor(
    private readonly baseUrl = "/api",
    private readonly fetcher: typeof fetch = (...args) => fetch(...args),
    private readonly playbackDelay = 250,
  ) {}

  getSnapshot = () => this.snapshot;
  subscribe = (callback: () => void) => {
    this.listeners.add(callback);
    return () => {
      this.listeners.delete(callback);
    };
  };
  private update(patch: Partial<ClientSnapshot>) {
    if (this.disposed) return;
    this.snapshot = { ...this.snapshot, ...patch };
    this.listeners.forEach((listener) => listener());
  }
  private async request<T>(
    path: string,
    method = "GET",
    body?: unknown,
  ): Promise<T> {
    let response: Response;
    try {
      response = await this.fetcher(`${this.baseUrl}${path}`, {
        method,
        headers: {
          Accept: "application/json",
          ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        cache: "no-store",
      });
    } catch {
      throw new Error(
        "Cannot reach the local backend at /api. Check that it is running. If a round was in progress, refresh its state before continuing.",
      );
    }
    let data: unknown;
    try {
      data = await response.json();
    } catch {
      throw new Error(
        `Backend returned a non-JSON response (${response.status}). Check the local /api connection.`,
      );
    }
    if (!response.ok) {
      const detail =
        data && typeof data === "object" && "detail" in data
          ? data.detail
          : null;
      throw new Error(
        typeof detail === "string"
          ? detail
          : `Backend request failed (${response.status}).`,
      );
    }
    return data as T;
  }
  private path(suffix = "") {
    if (!this.snapshot.state) throw new Error("Create an experiment first.");
    return `/experiments/${encodeURIComponent(this.snapshot.state.experimentId)}${suffix}`;
  }
  private async command<T>(operation: () => Promise<T>): Promise<T> {
    if (this.disposed) throw new Error("Client is disposed.");
    if (this.snapshot.busy)
      throw new Error("A request is already in progress.");
    this.update({ busy: true, error: null });
    try {
      return await operation();
    } catch (error) {
      this.pause();
      this.update({
        error:
          error instanceof Error ? error.message : "Experiment request failed.",
      });
      throw error;
    } finally {
      this.update({ busy: false });
    }
  }
  initialize = () => {
    if (!this.initialization) {
      this.initialization = this.command(async () => {
        const [health, config] = await Promise.all([
          this.request<Health>("/health"),
          this.request<ExperimentConfig>("/config"),
        ]);
        this.update({ health, config: this.snapshot.state?.config ?? config });
      }).finally(() => {
        this.initialization = undefined;
      });
    }
    return this.initialization;
  };
  private async accept(state: ExperimentState) {
    if (this.disposed) return;
    this.exitReplay();
    if (
      !state ||
      state.source !== "backend" ||
      !state.experimentId ||
      !Array.isArray(state.agents)
    ) {
      throw new Error("The backend returned an invalid experiment snapshot.");
    }
    // Truth is fetched separately and can never be taken from a normal snapshot.
    const safeState: ExperimentState = {
      experimentId: state.experimentId,
      source: "backend",
      status: state.status,
      round: state.round,
      maxRounds: state.maxRounds,
      config: state.config,
      agents: state.agents,
      pool: state.pool,
      markers: state.markers,
      recentEvents: state.recentEvents,
      winner: state.winner,
      results: state.results,
      failureReason: state.failureReason,
      providerFailure:
        state.status === "awaiting_api" && state.providerFailure
          ? {
              message: state.providerFailure.message,
              agentIds: state.providerFailure.agentIds,
              retryAt: state.providerFailure.retryAt,
              failures: state.providerFailure.failures.map((failure) => ({
                agentId: failure.agentId,
                category: failure.category,
                httpStatus: failure.httpStatus,
              })),
            }
          : undefined,
      groundTruthAvailable: isTerminal(state) && state.groundTruthAvailable,
    };
    const newExperiment =
      state.experimentId !== this.snapshot.state?.experimentId;
    if (isTerminal(state) || state.status === "awaiting_api") this.pause();
    this.update({
      state: safeState,
      error: null,
      config: state.config,
      humanRequests: [],
      ...(!isTerminal(state) || newExperiment ? { groundTruth: null } : {}),
    });
    // Publish awaiting_human before fetching so the presenter is obscured immediately.
    if (state.status === "awaiting_human") await this.loadHumanRequests();
    if (isTerminal(state) && !state.results) {
      const result = await this.request<FinalResult>(this.path("/results"));
      this.update({
        state: {
          ...safeState,
          results: result.results,
          winner: result.winner ?? state.winner,
        },
      });
    }
  }
  create = async (config: ExperimentConfig) => {
    this.exitReplay();
    this.pause();
    await this.command(async () => {
      await this.accept(
        await this.request<ExperimentState>("/experiments", "POST", config),
      );
    });
  };
  getExperimentState = async () => {
    this.exitReplay();
    this.pause();
    await this.command(async () => {
      await this.accept(await this.request<ExperimentState>(this.path()));
    });
  };
  reset = async (config?: ExperimentConfig) => {
    this.exitReplay();
    this.pause();
    await this.command(async () => {
      await this.accept(
        await this.request<ExperimentState>(
          this.path("/reset"),
          "POST",
          config,
        ),
      );
    });
  };
  private canStep(allowProviderRetry = false) {
    return (
      this.snapshot.state &&
      !isTerminal(this.snapshot.state) &&
      this.snapshot.state.status !== "awaiting_human" &&
      (allowProviderRetry || this.snapshot.state.status !== "awaiting_api")
    );
  }
  private async stepOnce(allowProviderRetry = false) {
    await this.command(async () => {
      if (!this.canStep(allowProviderRetry))
        throw new Error(
          "This experiment cannot advance. Create, reset, or answer the pending human request.",
        );
      const state = this.snapshot.state!;
      if (
        state.status === "awaiting_api" &&
        (state.providerFailure?.retryAt ?? 0) * 1000 > Date.now()
      ) {
        throw new Error("Wait for the provider cooldown before retrying the pending round.");
      }
      // Refresh readiness when starting a round so a newly configured key can be picked up.
      const health = await this.request<Health>("/health");
      this.update({ health });
      if (!health.geminiConfigured)
        throw new Error(
          "Gemini is not configured. Set GEMINI_API_KEY in the backend environment and restart the backend. You can create experiments without a key; Play and Step require it.",
        );
      await this.accept(
        await this.request<ExperimentState>(this.path("/step"), "POST"),
      );
    });
  }
  step = async () => {
    if (this.snapshot.replay) {
      this.replayStep(1);
      return;
    }
    this.pause();
    // Only an explicit step can retry a provider pause; playback never retries it.
    await this.stepOnce(true);
  };
  start = () => {
    if (this.snapshot.replay) {
      if (!this.disposed && !this.snapshot.busy) this.setReplayPlaying(true);
      return;
    }
    if (
      this.disposed ||
      this.snapshot.busy ||
      this.snapshot.playing ||
      !this.canStep()
    )
      return;
    this.update({ playing: true, error: null });
    void this.playRound();
  };
  private async playRound() {
    if (!this.snapshot.playing || this.disposed) return;
    try {
      await this.stepOnce();
      this.schedule();
    } catch {
      /* command publishes the error and stops playback. */
    }
  }
  private schedule() {
    if (!this.snapshot.playing || !this.canStep() || this.disposed) return;
    clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      void this.playRound();
    }, this.playbackDelay);
  }
  pause = () => {
    clearTimeout(this.timer);
    const replay = this.snapshot.replay;
    this.update({
      playing: false,
      ...(replay && replay.playing ? { replay: { ...replay, playing: false } } : {}),
    });
  };
  enterReplay = async () => {
    if (this.snapshot.replay) return;
    await this.command(async () => {
      const data = await this.request<{ rounds: ExperimentState[] }>(
        this.path("/replay"),
      );
      const current = this.snapshot.state;
      if (
        !Array.isArray(data.rounds) ||
        data.rounds.length === 0 ||
        data.rounds.some(
          (round) =>
            !round ||
            round.experimentId !== current?.experimentId ||
            !Array.isArray(round.agents) ||
            typeof round.round !== "number",
        )
      ) {
        throw new Error("The backend has no recorded rounds for this experiment.");
      }
      this.pause();
      this.update({
        replay: {
          rounds: data.rounds,
          index: 0,
          playing: false,
          live: current,
        },
        state: data.rounds[0],
        humanRequests: [],
        groundTruth: null,
      });
    });
  };
  exitReplay = () => {
    const replay = this.snapshot.replay;
    if (!replay) return;
    clearTimeout(this.timer);
    this.update({ replay: null, state: replay.live, playing: false });
  };
  replayStep = (delta: 1 | -1) => {
    const replay = this.snapshot.replay;
    if (!replay || this.disposed) return;
    const index = Math.min(
      replay.rounds.length - 1,
      Math.max(0, replay.index + delta),
    );
    if (index === replay.index) return;
    this.update({ replay: { ...replay, index }, state: replay.rounds[index] });
  };
  private setReplayPlaying(playing: boolean) {
    const replay = this.snapshot.replay;
    if (!replay || this.disposed) return;
    clearTimeout(this.timer);
    if (playing && replay.index < replay.rounds.length - 1) {
      this.update({
        replay: { ...replay, playing: true },
        playing: true,
        error: null,
      });
      this.timer = setTimeout(() => {
        this.playReplay();
      }, this.playbackDelay);
    } else {
      this.update({ replay: { ...replay, playing: false }, playing: false });
    }
  }
  private playReplay() {
    const replay = this.snapshot.replay;
    if (!replay?.playing || this.disposed) return;
    if (replay.index >= replay.rounds.length - 1) {
      this.update({ replay: { ...replay, playing: false }, playing: false });
      return;
    }
    const index = replay.index + 1;
    this.update({
      replay: { ...replay, index },
      state: replay.rounds[index],
      playing: true,
    });
    clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.playReplay();
    }, this.playbackDelay);
  }
  private async loadHumanRequests() {
    const humanRequests = await this.request<HumanRequest[]>(
      this.path("/human-requests"),
    );
    this.update({ humanRequests });
  }
  refreshHumanRequests = async () => {
    await this.command(async () => {
      if (this.snapshot.state?.status !== "awaiting_human")
        throw new Error("No human input is pending.");
      await this.loadHumanRequests();
      // A response may have committed even if its HTTP reply was lost.
      if (this.snapshot.humanRequests.length === 0) {
        await this.accept(await this.request<ExperimentState>(this.path()));
      }
    });
  };
  submitHumanResponse = async (response: HumanResponse) => {
    await this.command(async () => {
      if (
        this.snapshot.state?.status !== "awaiting_human" ||
        !this.snapshot.humanRequests.some(
          (request) => request.id === response.requestId,
        )
      ) {
        throw new Error(
          "This human request is no longer pending. Refresh the requests.",
        );
      }
      await this.accept(
        await this.request<ExperimentState>(
          this.path("/human-responses"),
          "POST",
          response,
        ),
      );
    });
    this.schedule();
  };
  revealGroundTruth = async () => {
    await this.command(async () => {
      if (
        !isTerminal(this.snapshot.state) ||
        !this.snapshot.state?.groundTruthAvailable
      )
        throw new Error(
          "Ground truth is only available after the experiment ends.",
        );
      const groundTruth = await this.request<GroundTruth>(
        this.path("/reveal-ground-truth"),
        "POST",
      );
      this.update({ groundTruth });
    });
  };
  getResults = async () =>
    this.command(async () => {
      if (!isTerminal(this.snapshot.state))
        throw new Error(
          "Final results are only available after the experiment ends.",
        );
      const result = await this.request<FinalResult>(this.path("/results"));
      this.update({
        state: {
          ...this.snapshot.state!,
          results: result.results,
          winner: result.winner ?? this.snapshot.state?.winner,
        },
      });
      return result;
    });
  dispose = () => {
    this.pause();
    this.disposed = true;
    this.listeners.clear();
  };
}
export const createBackendSimulationClient = () =>
  new BackendSimulationClient();

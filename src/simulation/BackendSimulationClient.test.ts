import { afterEach, describe, expect, it, vi } from "vitest";
import { BackendSimulationClient } from "./BackendSimulationClient";
import {
  config,
  groundTruth,
  health,
  humanRequest,
  json,
  payouts,
  snapshot,
  terminal,
} from "../test/fixtures";

const clients: BackendSimulationClient[] = [];
function setup() {
  const fetcher = vi.fn<typeof fetch>();
  const client = new BackendSimulationClient("/api", fetcher, 10);
  clients.push(client);
  return { client, fetcher };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { resolve, promise };
}
afterEach(() => {
  clients.forEach((client) => client.dispose());
  clients.length = 0;
  vi.useRealTimers();
});

describe("backend HTTP adapter", () => {
  it("loads defaults and health only, sharing concurrent initialization", async () => {
    const { client, fetcher } = setup();
    fetcher
      .mockResolvedValueOnce(json({ ...health, geminiConfigured: false }))
      .mockResolvedValueOnce(json(config));
    await Promise.all([client.initialize(), client.initialize()]);
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
      "/api/health",
      "/api/config",
    ]);
    expect(client.getSnapshot()).toMatchObject({
      config,
      state: null,
      playing: false,
      health: { geminiConfigured: false },
    });
  });
  it("preserves current run settings when rechecking backend health", async () => {
    const { client, fetcher } = setup();
    const custom = { ...config, seed: 91, humanCost: 75 };
    fetcher.mockResolvedValueOnce(json(snapshot({ config: custom })));
    await client.create(custom);
    fetcher
      .mockResolvedValueOnce(json(health))
      .mockResolvedValueOnce(json(config));
    await client.initialize();
    expect(client.getSnapshot().config).toEqual(custom);
  });
  it("creates without a key but reports missing Gemini and never posts a step", async () => {
    const { client, fetcher } = setup();
    fetcher.mockResolvedValueOnce(json(snapshot()));
    await client.create(config);
    expect(JSON.parse(String(fetcher.mock.calls[0][1]?.body))).toEqual(config);
    fetcher.mockResolvedValueOnce(json({ ...health, geminiConfigured: false }));
    await expect(client.step()).rejects.toThrow("GEMINI_API_KEY");
    expect(
      fetcher.mock.calls.some(([url]) => String(url).endsWith("/step")),
    ).toBe(false);
    expect(client.getSnapshot()).toMatchObject({
      busy: false,
      playing: false,
      state: { round: 0 },
    });
  });
  it("gets and resets the current experiment, preserving supplied configuration", async () => {
    const { client, fetcher } = setup();
    fetcher.mockResolvedValueOnce(
      json(snapshot({ experimentId: "id with space" })),
    );
    await client.create(config);
    fetcher.mockResolvedValueOnce(
      json(
        snapshot({ experimentId: "id with space", status: "paused", round: 4 }),
      ),
    );
    await client.getExperimentState();
    expect(fetcher.mock.calls[1][0]).toBe("/api/experiments/id%20with%20space");
    const next = { ...config, seed: 91, observationNoise: 0.7 };
    fetcher.mockResolvedValueOnce(
      json(snapshot({ experimentId: "new-id", config: next })),
    );
    await client.reset(next);
    expect(fetcher.mock.calls[2]).toMatchObject([
      "/api/experiments/id%20with%20space/reset",
      { method: "POST", body: JSON.stringify(next) },
    ]);
    expect(client.getSnapshot()).toMatchObject({
      config: next,
      state: { experimentId: "new-id" },
      groundTruth: null,
    });
    fetcher.mockResolvedValueOnce(json(snapshot()));
    await client.reset();
    expect(fetcher.mock.calls[3][1]?.body).toBeUndefined();
  });
  it("shows detail and transport errors without retries or a runtime fallback", async () => {
    const { client, fetcher } = setup();
    fetcher.mockResolvedValueOnce(
      json({ detail: "Invalid grid dimensions" }, 422),
    );
    await expect(client.create(config)).rejects.toThrow(
      "Invalid grid dimensions",
    );
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(client.getSnapshot()).toMatchObject({
      state: null,
      error: "Invalid grid dimensions",
      busy: false,
    });
    fetcher.mockRejectedValueOnce(new TypeError("offline"));
    await expect(client.create(config)).rejects.toThrow(
      "Cannot reach the local backend",
    );
    fetcher.mockResolvedValueOnce(new Response("<html>Vite</html>"));
    await expect(client.create(config)).rejects.toThrow("non-JSON");
  });
  it("never overlaps steps, and pausing an in-flight step prevents scheduling another", async () => {
    vi.useFakeTimers();
    const { client, fetcher } = setup();
    fetcher.mockResolvedValueOnce(json(snapshot()));
    await client.create(config);
    const pending = deferred<Response>();
    fetcher
      .mockResolvedValueOnce(json(health))
      .mockReturnValueOnce(pending.promise);
    client.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(
      fetcher.mock.calls.filter(([url]) => String(url).endsWith("/step")),
    ).toHaveLength(1);
    client.start();
    await expect(client.step()).rejects.toThrow("already in progress");
    await expect(client.reset()).rejects.toThrow("already in progress");
    client.pause();
    await vi.advanceTimersByTimeAsync(100);
    expect(client.getSnapshot()).toMatchObject({
      playing: false,
      busy: true,
      state: { round: 0 },
    });
    pending.resolve(json(snapshot({ round: 1, status: "running" })));
    await vi.advanceTimersByTimeAsync(100);
    expect(
      fetcher.mock.calls.filter(([url]) => String(url).endsWith("/step")),
    ).toHaveLength(1);
    expect(client.getSnapshot()).toMatchObject({
      playing: false,
      busy: false,
      state: { round: 1 },
    });
  });
  it("plays sequential rounds and stops at failure with final payouts", async () => {
    vi.useFakeTimers();
    const { client, fetcher } = setup();
    fetcher.mockResolvedValueOnce(json(snapshot()));
    await client.create(config);
    fetcher
      .mockResolvedValueOnce(json(health))
      .mockResolvedValueOnce(json(snapshot({ round: 1, status: "running" })))
      .mockResolvedValueOnce(json(health))
      .mockResolvedValueOnce(json(terminal()));
    client.start();
    await vi.advanceTimersByTimeAsync(100);
    expect(client.getSnapshot()).toMatchObject({
      state: { status: "failure", results: payouts },
      busy: false,
      playing: false,
      groundTruth: null,
    });
    expect(
      fetcher.mock.calls.filter(([url]) => String(url).endsWith("/step")),
    ).toHaveLength(2);
  });
  it("publishes background step errors and stops playback", async () => {
    vi.useFakeTimers();
    const { client, fetcher } = setup();
    fetcher.mockResolvedValueOnce(json(snapshot()));
    await client.create(config);
    fetcher
      .mockResolvedValueOnce(json(health))
      .mockResolvedValueOnce(json({ detail: "Gemini quota exhausted" }, 503));
    client.start();
    await vi.advanceTimersByTimeAsync(1000);
    expect(client.getSnapshot()).toMatchObject({
      playing: false,
      busy: false,
      error: "Gemini quota exhausted",
    });
    expect(
      fetcher.mock.calls.filter(([url]) => String(url).endsWith("/step")),
    ).toHaveLength(1);
  });
  it("processes sequential human requests before resuming automatic playback", async () => {
    vi.useFakeTimers();
    const { client, fetcher } = setup();
    const awaiting = snapshot({ status: "awaiting_human" });
    fetcher.mockResolvedValueOnce(json(snapshot()));
    await client.create(config);
    fetcher
      .mockResolvedValueOnce(json(health))
      .mockResolvedValueOnce(json(awaiting))
      .mockResolvedValueOnce(
        json([humanRequest(), humanRequest("request-b", "B")]),
      );
    client.start();
    await vi.advanceTimersByTimeAsync(100);
    expect(client.getSnapshot()).toMatchObject({
      playing: true,
      state: { status: "awaiting_human" },
    });
    expect(client.getSnapshot().humanRequests).toHaveLength(2);
    fetcher
      .mockResolvedValueOnce(json(awaiting))
      .mockResolvedValueOnce(json([humanRequest("request-b", "B")]));
    await client.submitHumanResponse({
      requestId: "request-a",
      x: 6,
      y: 4,
      note: "Regional evidence",
    });
    await vi.advanceTimersByTimeAsync(100);
    expect(
      fetcher.mock.calls.filter(([url]) => String(url).endsWith("/step")),
    ).toHaveLength(1);
    expect(client.getSnapshot().humanRequests[0].id).toBe("request-b");
    fetcher
      .mockResolvedValueOnce(json(snapshot({ status: "paused", round: 1 })))
      .mockResolvedValueOnce(json(health))
      .mockResolvedValueOnce(json(terminal()));
    await client.submitHumanResponse({
      requestId: "request-b",
      x: 2,
      y: 1,
      note: "",
    });
    await vi.advanceTimersByTimeAsync(100);
    expect(client.getSnapshot()).toMatchObject({
      playing: false,
      humanRequests: [],
      state: { status: "failure" },
    });
    expect(
      fetcher.mock.calls.filter(([url]) => String(url).endsWith("/step")),
    ).toHaveLength(2);
  });
  it("retains a pending human request on submission failure and supports refresh", async () => {
    const { client, fetcher } = setup();
    fetcher
      .mockResolvedValueOnce(json(snapshot({ status: "awaiting_human" })))
      .mockResolvedValueOnce(json([humanRequest()]));
    await client.create(config);
    fetcher.mockResolvedValueOnce(json({ detail: "Response rejected" }, 422));
    await expect(
      client.submitHumanResponse({
        requestId: "request-a",
        x: 6,
        y: 4,
        note: "",
      }),
    ).rejects.toThrow("Response rejected");
    expect(client.getSnapshot().humanRequests).toHaveLength(1);
    fetcher.mockResolvedValueOnce(json([humanRequest()]));
    await client.refreshHumanRequests();
    expect(client.getSnapshot().error).toBeNull();
    fetcher.mockResolvedValueOnce(
      json(snapshot({ round: 1, status: "paused" })),
    );
    await client.submitHumanResponse({
      requestId: "request-a",
      x: 6,
      y: 4,
      note: "",
    });
    expect(client.getSnapshot().playing).toBe(false);
    expect(
      fetcher.mock.calls.some(([url]) => String(url).endsWith("/step")),
    ).toBe(false);
  });
  it("requires an explicit terminal reveal, never accepts truth in normal snapshots, and clears on reset", async () => {
    const { client, fetcher } = setup();
    fetcher.mockResolvedValueOnce(
      json({ ...snapshot({ groundTruthAvailable: true }), groundTruth }),
    );
    await client.create(config);
    await expect(client.revealGroundTruth()).rejects.toThrow(
      "only available after",
    );
    expect(client.getSnapshot().groundTruth).toBeNull();
    expect(client.getSnapshot().state).not.toHaveProperty("groundTruth");
    fetcher
      .mockResolvedValueOnce(json({ ...terminal(), results: null }))
      .mockResolvedValueOnce(json({ results: payouts }));
    await client.getExperimentState();
    expect(client.getSnapshot().state?.results).toEqual(payouts);
    expect(
      fetcher.mock.calls.some(([url]) =>
        String(url).endsWith("/reveal-ground-truth"),
      ),
    ).toBe(false);
    fetcher.mockResolvedValueOnce(json({ detail: "Reveal unavailable" }, 409));
    await expect(client.revealGroundTruth()).rejects.toThrow(
      "Reveal unavailable",
    );
    expect(client.getSnapshot().groundTruth).toBeNull();
    fetcher.mockResolvedValueOnce(json(groundTruth));
    await client.revealGroundTruth();
    expect(client.getSnapshot().groundTruth).toEqual(groundTruth);
    expect(fetcher.mock.calls.at(-1)).toMatchObject([
      "/api/experiments/test-run/reveal-ground-truth",
      { method: "POST" },
    ]);
    fetcher.mockResolvedValueOnce(json(snapshot({ experimentId: "new" })));
    await client.reset();
    expect(client.getSnapshot().groundTruth).toBeNull();
  });
  it("reconciles state when the last human response committed but its reply was lost", async () => {
    const { client, fetcher } = setup();
    fetcher
      .mockResolvedValueOnce(json(snapshot({ status: "awaiting_human" })))
      .mockResolvedValueOnce(json([humanRequest()]));
    await client.create(config);
    fetcher.mockRejectedValueOnce(new TypeError("Reply lost"));
    await expect(
      client.submitHumanResponse({
        requestId: "request-a",
        x: 6,
        y: 4,
        note: "",
      }),
    ).rejects.toThrow("Cannot reach");
    fetcher
      .mockResolvedValueOnce(json([]))
      .mockResolvedValueOnce(json(snapshot({ status: "paused", round: 1 })));
    await client.refreshHumanRequests();
    expect(client.getSnapshot()).toMatchObject({
      state: { status: "paused", round: 1 },
      humanRequests: [],
      playing: false,
      error: null,
    });
  });
  it("replays recorded rounds locally without posting steps and restores the live run", async () => {
    vi.useFakeTimers();
    const { client, fetcher } = setup();
    fetcher.mockResolvedValueOnce(json(snapshot({ round: 2, status: "paused" })));
    await client.create(config);
    const rounds = [
      snapshot({ round: 0 }),
      snapshot({ round: 1, status: "paused" }),
      snapshot({ round: 2, status: "paused" }),
    ];
    fetcher.mockResolvedValueOnce(json({ rounds }));
    await client.enterReplay();
    expect(client.getSnapshot()).toMatchObject({
      state: { round: 0 },
      replay: { index: 0 },
      busy: false,
    });
    client.replayStep(1);
    expect(client.getSnapshot()).toMatchObject({
      state: { round: 1 },
      replay: { index: 1 },
    });
    client.replayStep(-1);
    expect(client.getSnapshot()).toMatchObject({
      state: { round: 0 },
      replay: { index: 0 },
    });
    client.replayStep(-1);
    expect(client.getSnapshot().replay?.index).toBe(0);
    client.start();
    await vi.advanceTimersByTimeAsync(100);
    expect(client.getSnapshot()).toMatchObject({
      state: { round: 2 },
      replay: { index: 2 },
      playing: false,
    });
    expect(
      fetcher.mock.calls.filter(([url]) => String(url).endsWith("/step")),
    ).toHaveLength(0);
    client.exitReplay();
    expect(client.getSnapshot()).toMatchObject({
      state: { round: 2 },
      replay: null,
    });
  });
  it("rejects an empty or foreign replay without leaving the live run", async () => {
    const { client, fetcher } = setup();
    fetcher.mockResolvedValueOnce(json(snapshot({ round: 1, status: "paused" })));
    await client.create(config);
    fetcher.mockResolvedValueOnce(json({ rounds: [] }));
    await expect(client.enterReplay()).rejects.toThrow("no recorded rounds");
    fetcher.mockResolvedValueOnce(
      json({ rounds: [snapshot({ experimentId: "other" })] }),
    );
    await expect(client.enterReplay()).rejects.toThrow("no recorded rounds");
    expect(client.getSnapshot()).toMatchObject({
      state: { round: 1 },
      replay: null,
      busy: false,
    });
  });
  it("clears playback timers when disposed", async () => {
    vi.useFakeTimers();
    const { client, fetcher } = setup();
    fetcher.mockResolvedValueOnce(json(snapshot()));
    await client.create(config);
    fetcher
      .mockResolvedValueOnce(json(health))
      .mockResolvedValueOnce(json(snapshot({ status: "running", round: 1 })));
    client.start();
    await vi.advanceTimersByTimeAsync(0);
    client.dispose();
    await vi.advanceTimersByTimeAsync(1000);
    expect(fetcher).toHaveBeenCalledTimes(3);
  });
});

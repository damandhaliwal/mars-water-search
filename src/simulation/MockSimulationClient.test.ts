import { afterEach, describe, expect, it, vi } from "vitest";
import { MockSimulationClient } from "./MockSimulationClient";
import { createDemoFrames } from "./demo";
import { createBackendSimulationClient } from "./BackendSimulationClient";

afterEach(() => vi.useRealTimers());
describe("scripted experiment contract", () => {
  it("starts private with identical priors and no privileged map", () => {
    const initial = createDemoFrames()[0];
    expect(initial.groundTruth).toBeUndefined();
    expect(initial.pool.memberIds).toEqual([]);
    initial.agents.forEach((a) => {
      expect(a.collaborationStatus).toBe("private");
      expect(a.belief).toEqual(initial.agents[0].belief);
    });
  });
  it("keeps purchased advice private until joining and preserves its origin", () => {
    const frames = createDemoFrames();
    expect(frames[3].agents[2].lastAction).toBe("ask_human");
    expect(frames[3].pool.events.some((e) => e.kind === "human")).toBe(false);
    const advice = frames[4].pool.events.find((e) => e.kind === "human");
    expect(advice).toMatchObject({
      agentId: "C",
      observedRound: 3,
      sharedRound: 4,
      evidenceId: "c-r3",
    });
    expect(frames[4].pool.eligibilityRound).toBe(5);
  });
  it("retains an exhausted contributor’s eligibility and supplied payout", () => {
    const frames = createDemoFrames();
    expect(frames[8].agents[2]).toMatchObject({
      activity: "exhausted",
      budgetRemaining: 0,
    });
    expect(frames[8].pool.eligibleMemberIds).toContain("C");
    expect(frames[9].winner?.recipientIds).toEqual(
      frames[8].pool.eligibleMemberIds,
    );
    expect(
      frames[9].winner?.payouts.find((p) => p.agentId === "C")?.reward,
    ).toBeGreaterThan(0);
    expect(
      frames[9].recentEvents.some((e) => e.round === 9 && e.agentId === "C"),
    ).toBe(false);
  });
  it("has consistent authored budgets, one action per active agent, and valid maps", () => {
    const frames = createDemoFrames();
    for (const frame of frames) {
      for (const agent of frame.agents) {
        expect(agent.budgetRemaining + agent.accumulatedCost).toBe(300);
        expect(agent.belief?.values).toHaveLength(2500);
        expect(
          agent.belief?.values.every((p) => p !== null && p >= 0 && p <= 1),
        ).toBe(true);
        if (
          frame.round > 0 &&
          frames[frame.round - 1].agents.find((a) => a.id === agent.id)
            ?.activity === "active"
        ) {
          expect(
            frame.recentEvents.filter(
              (e) => e.round === frame.round && e.agentId === agent.id,
            ),
          ).toHaveLength(1);
        }
      }
      expect(new Set(frame.pool.events.map((e) => e.evidenceId)).size).toBe(
        frame.pool.events.length,
      );
      if (frame.round < 9) expect(frame.groundTruth).toBeUndefined();
    }
    for (const payout of frames[9].winner!.payouts)
      expect(payout.reward - payout.totalCost).toBeCloseTo(payout.utility);
  });
});
describe("fixture playback", () => {
  it("steps once, emits a snapshot, and protects internal state from consumers", async () => {
    const client = new MockSimulationClient();
    const listener = vi.fn();
    const off = client.subscribe(listener);
    await client.step();
    expect(listener).toHaveBeenCalledTimes(1);
    const snapshot = await client.getExperimentState();
    snapshot.agents[0].budgetRemaining = 999;
    expect((await client.getExperimentState()).agents[0].budgetRemaining).toBe(
      280,
    );
    off();
    await client.step();
    expect(listener).toHaveBeenCalledTimes(1);
    client.dispose();
  });
  it("pauses, resets and stops automatically at the terminal frame", async () => {
    vi.useFakeTimers();
    const client = new MockSimulationClient();
    await client.start();
    await client.start();
    vi.advanceTimersByTime(1800);
    expect((await client.getExperimentState()).round).toBe(1);
    await client.pause();
    vi.advanceTimersByTime(5000);
    expect((await client.getExperimentState()).round).toBe(1);
    await client.reset();
    expect((await client.getExperimentState()).status).toBe("idle");
    await client.start();
    vi.advanceTimersByTime(1800 * 15);
    expect((await client.getExperimentState()).status).toBe("success");
    expect(vi.getTimerCount()).toBe(0);
    await client.step();
    expect((await client.getExperimentState()).round).toBe(9);
    client.dispose();
  });
  it("reports an unconfigured backend instead of quietly switching to demo", () => {
    expect(createBackendSimulationClient).toThrow(
      "Backend adapter is not connected",
    );
  });
});

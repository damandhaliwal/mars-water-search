import { test, expect } from "@playwright/test";
import {
  config,
  groundTruth,
  health,
  humanRequest,
  snapshot,
  terminal,
} from "../fixtures";
import type { ExperimentState } from "../../simulation/types";

test("missing key is clear; creation, config editing, reset, and all-agent paths work", async ({
  page,
}) => {
  const requests: string[] = [];
  let createdConfig: unknown;
  let state = snapshot();
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    requests.push(`${request.method()} ${path}`);
    if (path === "/api/health")
      return route.fulfill({ json: { ...health, geminiConfigured: false } });
    if (path === "/api/config") return route.fulfill({ json: config });
    if (path === "/api/experiments" || path.endsWith("/reset")) {
      createdConfig = request.postDataJSON();
      state = snapshot({ config: request.postDataJSON() ?? config });
      return route.fulfill({ json: state });
    }
    if (request.method() === "GET") return route.fulfill({ json: state });
    return route.fulfill({
      status: 503,
      json: { detail: "GEMINI_API_KEY required" },
    });
  });
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Create experiment" }),
  ).toBeVisible();
  expect(requests).toEqual(["GET /api/health", "GET /api/config"]);
  await page.getByLabel("Seed", { exact: true }).fill("91");
  await page.getByRole("button", { name: "Create experiment" }).click();
  await expect(
    page.getByRole("region", { name: "Mars exploration map" }),
  ).toBeVisible();
  expect(createdConfig).toEqual({ ...config, seed: 91 });
  await expect(page.locator("polyline[data-agent-path]")).toHaveCount(2);
  const markerBounds = await page.locator(".map-agent").evaluateAll((markers) =>
    markers.map((marker) => {
      const { left, right, width } = marker.getBoundingClientRect();
      return { left, right, width };
    }),
  );
  expect(markerBounds[0].width).toBeLessThan(60);
  expect(markerBounds[0].right).toBeLessThan(markerBounds[1].left);

  await page
    .getByRole("group", { name: "Map view" })
    .getByRole("button", { name: "B", exact: true })
    .click();
  await expect(page.locator("polyline[data-agent-path]")).toHaveCount(2);
  await page.getByRole("button", { name: "Step one round" }).click();
  await expect(page.getByRole("alert")).toContainText("GEMINI_API_KEY");
  expect(requests.some((path) => path.endsWith("/step"))).toBe(false);
  await page.getByLabel("Human quality").fill("0.7");
  await page.getByRole("button", { name: "Apply & reset" }).click();
  await expect(page.getByLabel("Human quality")).toHaveValue("0.7");
  expect(createdConfig).toEqual({ ...config, seed: 91, humanQuality: 0.7 });
  await page.screenshot({
    path: "/tmp/mars-frontend-settings.png",
    fullPage: true,
  });
});

test("pause stops serial playback after the in-flight request", async ({
  page,
}) => {
  let steps = 0;
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/health") return route.fulfill({ json: health });
    if (path === "/api/config") return route.fulfill({ json: config });
    if (path.endsWith("/step")) {
      steps++;
      await pending;
      return route.fulfill({ json: snapshot({ round: 1, status: "paused" }) });
    }
    return route.fulfill({ json: snapshot() });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Create experiment" }).click();
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await expect.poll(() => steps).toBe(1);
  await expect(
    page.getByRole("button", { name: "Step one round" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  release();
  await expect(page.locator(".round-number")).toContainText("01");
  await expect(
    page.getByRole("button", { name: "Play", exact: true }),
  ).toBeEnabled();
  await page.waitForTimeout(500);
  expect(steps).toBe(1);
});

test("human advisor obscures presenter, handles errors and consecutive requests, then terminal reveal", async ({
  page,
}) => {
  let responses = 0;
  let revealed = false;
  const submitted: unknown[] = [];
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/health") return route.fulfill({ json: health });
    if (path === "/api/config") return route.fulfill({ json: config });
    if (path.endsWith("/human-requests"))
      return route.fulfill({
        json:
          responses < 2
            ? [humanRequest(), humanRequest("request-b", "B")]
            : [humanRequest("request-b", "B")],
      });
    if (path.endsWith("/step"))
      return route.fulfill({ json: snapshot({ status: "awaiting_human" }) });
    if (path.endsWith("/human-responses")) {
      submitted.push(route.request().postDataJSON());
      responses++;
      if (responses === 1)
        return route.fulfill({
          status: 503,
          json: { detail: "Temporary response failure" },
        });
      return route.fulfill({
        json:
          responses === 2 ? snapshot({ status: "awaiting_human" }) : terminal(),
      });
    }
    if (path.endsWith("/reveal-ground-truth")) {
      revealed = true;
      return route.fulfill({ json: groundTruth });
    }
    return route.fulfill({ json: snapshot() });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Create experiment" }).click();
  await page.getByRole("button", { name: "Step one round" }).click();
  await expect(page.getByRole("dialog")).toContainText("Agent A commits 150");
  await expect(page.locator(".app-shell")).toHaveCount(0);
  await expect(
    page.getByRole("region", { name: "Mars exploration map" }),
  ).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Reveal truth" })).toHaveCount(
    0,
  );
  await page
    .getByRole("button", { name: "Region 1, 1; confidence 0.80" })
    .click();
  await page.getByLabel("Optional note").fill("Try the selected region");
  await page
    .getByRole("button", { name: "Submit recommendation & resume" })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Temporary response failure",
  );
  await expect(page.locator(".app-shell")).toHaveCount(0);
  await expect(page.getByLabel("Optional note")).toHaveValue(
    "Try the selected region",
  );
  await page.screenshot({
    path: "/tmp/mars-human-advisor.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Submit recommendation & resume" })
    .click();
  await expect(page.getByRole("dialog")).toContainText("Agent B commits 150");
  expect(submitted[1]).toEqual({
    requestId: "request-a",
    x: 6,
    y: 4,
    note: "Try the selected region",
  });
  await expect(
    page.getByRole("button", { name: "Submit recommendation & resume" }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Region 0, 1; confidence 0.60" })
    .click();
  await page
    .getByRole("button", { name: "Submit recommendation & resume" })
    .click();
  await expect(
    page.getByRole("region", { name: "Final results" }),
  ).toContainText("-250");
  expect(revealed).toBe(false);
  await page.getByRole("button", { name: "Reveal truth" }).click();
  await expect(
    page.getByRole("heading", { name: "Ground truth" }),
  ).toBeVisible();
  expect(revealed).toBe(true);
  await expect(
    page.getByText("Successful drill threshold: 0.75"),
  ).toBeVisible();
  await page.screenshot({
    path: "/tmp/mars-final-results.png",
    fullPage: true,
  });
});

test("success shows AI pool payouts and retains inactive eligibility on a narrow screen", async ({
  page,
}) => {
  const state: ExperimentState = snapshot({
    status: "success",
    round: 5,
    groundTruthAvailable: true,
    results: [
      {
        agentId: "A",
        regime: "ai_pool",
        reward: 500,
        totalCost: 300,
        utility: 200,
      },
      {
        agentId: "B",
        regime: "ai_pool",
        reward: 500,
        totalCost: 200,
        utility: 300,
      },
    ],
  });
  state.agents = state.agents.map((a, i) => ({
    ...a,
    collaborationStatus: "ai_pool",
    activity: i === 0 ? "inactive" : "active",
    budgetRemaining: i === 0 ? 0 : 100,
    accumulatedCost: state.results![i].totalCost,
    finalReward: state.results![i].reward,
    finalUtility: state.results![i].utility,
  }));
  state.pool = {
    ...state.pool,
    memberIds: ["A", "B"],
    eligibleMemberIds: ["A", "B"],
    rewardPerMember: 500,
    belief: state.agents[0].belief,
  };
  state.winner = {
    agentId: "B",
    position: { x: 2, y: 2 },
    status: "ai_pool",
    intensity: 0.9,
    recipientIds: ["A", "B"],
    discoveryReward: 1000,
    rewardPerRecipient: 500,
    payouts: state.results!,
  };
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    return route.fulfill({
      json:
        path === "/api/health"
          ? health
          : path === "/api/config"
            ? config
            : state,
    });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Create experiment" }).click();
  await expect(
    page.getByRole("region", { name: "Final results" }),
  ).toContainText("Intensity 0.9");
  await expect(page.getByText("Prize eligibility retained")).toBeVisible();
  await page.getByRole("button", { name: "Pool", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Pool belief" }),
  ).toBeVisible();
  await expect(page.locator("polyline[data-agent-path]")).toHaveCount(2);
  const overflows = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  expect(overflows).toBe(false);
  await page.screenshot({
    path: "/tmp/mars-mobile-success.png",
    fullPage: true,
  });
});

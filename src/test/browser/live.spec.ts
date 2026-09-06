import { test, expect } from "@playwright/test";
import type {
  ExperimentConfig,
  ExperimentState,
  Health,
} from "../../simulation/types";

test("@local-backend creates and resets actual experiments without a key or agent calls", async ({
  page,
  request,
}) => {
  const healthResponse = await request.get("/api/health");
  expect(healthResponse.ok()).toBe(true);
  const health: Health = await healthResponse.json();
  test.skip(
    health.geminiConfigured,
    "Missing-key smoke check requires an unconfigured backend; it never calls Gemini.",
  );
  const defaults: ExperimentConfig = await (
    await request.get("/api/config")
  ).json();
  const calls: { method: string; path: string }[] = [];
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (request.url().includes("/api/"))
      calls.push({
        method: request.method(),
        path: new URL(request.url()).pathname,
      });
  });
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Create experiment" }),
  ).toBeVisible();
  expect(calls.some((call) => call.method === "POST")).toBe(false);
  await page.getByLabel("Seed", { exact: true }).fill("91006");
  const createdResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/experiments") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Create experiment" }).click();
  const created: ExperimentState = await (await createdResponse).json();
  await expect(
    page.getByRole("region", { name: "Mars exploration map" }),
  ).toBeVisible();
  expect(created.config).toEqual({ ...defaults, seed: 91006 });
  expect(created.source).toBe("backend");
  expect(created).not.toHaveProperty("groundTruth");
  await expect(page.locator("polyline[data-agent-path]")).toHaveCount(
    defaults.numberOfAgents,
  );
  await page.getByRole("button", { name: "Step one round" }).click();
  await expect(page.getByRole("alert")).toContainText("GEMINI_API_KEY");
  expect(calls.some((call) => call.path.endsWith("/step"))).toBe(false);
  await page.getByRole("button", { name: "Refresh state" }).click();
  await expect(
    page.getByRole("button", { name: "Step one round" }),
  ).toBeEnabled();
  await page.getByLabel("Human quality").fill("0.7");
  const resetResponse = page.waitForResponse((r) => r.url().endsWith("/reset"));
  await page.getByRole("button", { name: "Apply & reset" }).click();
  const reset: ExperimentState = await (await resetResponse).json();
  expect(reset.config).toEqual({ ...defaults, seed: 91006, humanQuality: 0.7 });
  expect(reset.experimentId).not.toBe(created.experimentId);
  await expect(
    page.getByRole("button", { name: "Reveal truth" }),
  ).toBeDisabled();
  await expect(page.getByLabel("Human quality")).toHaveValue("0.7");
  expect(errors).toEqual([]);
  await page.screenshot({ path: "/tmp/mars-live-backend.png", fullPage: true });
});

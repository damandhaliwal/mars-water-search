// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { MarsGrid } from "./MarsGrid";
import { snapshot } from "../test/fixtures";

afterEach(cleanup);

it("shows the original prior, uses labeled relative contrast, and marks a belief target", () => {
  const state = snapshot();
  state.agents[0].belief!.values[19] = .2;
  const props = { state, selected: "A", onSelect: vi.fn(), groundTruth: null, onReveal: vi.fn(), busy: false };
  render(<MarsGrid {...props} />);
  expect(screen.getByText("0.100 – 0.200")).toBeTruthy();
  expect(screen.getByText("Belief · relative scale")).toBeTruthy();
  expect(document.querySelector('[data-map-target="peak"]')?.textContent).toContain("(3, 2)");
  fireEvent.click(screen.getByRole("button", { name: "Initial prior" }));
  expect(screen.getByRole("heading", { name: "Initial prior" })).toBeTruthy();
  expect(screen.getByText("Uniform belief · 0.10 everywhere")).toBeTruthy();
  expect(document.querySelector('[data-map-target="peak"]')).toBeNull();
  fireEvent.click(screen.getByLabelText("Rover paths"));
  expect(document.querySelectorAll("[data-agent-path]")).toHaveLength(0);
});

it("renders the actual water peak and drillable zone during an allowed live presenter view", () => {
  const state = snapshot({ groundTruthAvailable: true });
  state.config.humanMode = "simulated";
  const values = Array(48).fill(0);
  values[19] = 1;
  values[20] = .8;
  render(<MarsGrid state={state} selected="A" onSelect={vi.fn()} busy={false}
    groundTruth={{ intensity: { width: 8, height: 6, values }, successThreshold: .75 }} onReveal={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Reveal truth" }));
  expect(screen.getByRole("heading", { name: "Ground truth" })).toBeTruthy();
  expect(screen.getByText("2 cells")).toBeTruthy();
  expect(document.querySelectorAll('[data-water-cell="true"]')).toHaveLength(2);
  expect(document.querySelector('[data-map-target="peak"]')?.textContent).toContain("Water peak at (3, 2)");
});

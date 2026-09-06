// @vitest-environment jsdom
import { StrictMode } from "react";
import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { BackendSimulationClient } from "./simulation/BackendSimulationClient";
import {
  config,
  groundTruth,
  health,
  humanRequest,
  json,
  snapshot,
  terminal,
} from "./test/fixtures";
import { InformationPool } from "./components/InformationPool";

const clients: BackendSimulationClient[] = [];
afterEach(() => {
  cleanup();
  clients.forEach((client) => client.dispose());
  clients.length = 0;
});
function setup() {
  const fetcher = vi
    .fn<typeof fetch>()
    .mockResolvedValueOnce(json(health))
    .mockResolvedValueOnce(json(config));
  const client = new BackendSimulationClient("/api", fetcher);
  clients.push(client);
  render(
    <StrictMode>
      <App client={client} />
    </StrictMode>,
  );
  return { client, fetcher, user: userEvent.setup() };
}
it("prefills editable defaults without running, preserves extra config, and keeps all paths", async () => {
  const { fetcher, user } = setup();
  await screen.findByRole("button", { name: "Create experiment" });
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect((screen.getByLabelText("Seed") as HTMLInputElement).value).toBe("42");
  fireEvent.change(screen.getByLabelText("Seed"), { target: { value: "123" } });
  fireEvent.change(screen.getByLabelText("Grid width"), {
    target: { value: "12" },
  });
  await user.selectOptions(screen.getByLabelText("Treatment"), "solo_only");
  fetcher.mockResolvedValueOnce(json(snapshot()));
  await user.click(screen.getByRole("button", { name: "Create experiment" }));
  await screen.findByRole("region", { name: "Mars exploration map" });
  const submitted = JSON.parse(String(fetcher.mock.calls[2][1]?.body));
  expect(submitted).toEqual({
    ...config,
    seed: 123,
    gridWidth: 12,
    treatment: "solo_only",
  });
  expect(document.querySelectorAll("polyline[data-agent-path]")).toHaveLength(
    2,
  );
  await user.click(
    within(screen.getByRole("group", { name: "Map view" })).getByRole(
      "button",
      { name: "B" },
    ),
  );
  expect(document.querySelectorAll("polyline[data-agent-path]")).toHaveLength(
    2,
  );
  expect(screen.queryByRole("button", { name: "Pool" })).toBeNull();
  expect(
    (screen.getByRole("button", { name: "Reveal truth" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
});
it("obscures the presenter during sequential human requests and submits exact bounded responses", async () => {
  const { fetcher, user } = setup();
  await screen.findByRole("button", { name: "Create experiment" });
  fetcher.mockResolvedValueOnce(json(snapshot()));
  await user.click(screen.getByRole("button", { name: "Create experiment" }));
  await screen.findByRole("region", { name: "Mars exploration map" });
  fetcher
    .mockResolvedValueOnce(json(health))
    .mockResolvedValueOnce(json(snapshot({ status: "awaiting_human" })))
    .mockResolvedValueOnce(
      json([humanRequest(), humanRequest("request-b", "B")]),
    );
  await user.click(screen.getByRole("button", { name: "Step one round" }));
  await screen.findByText(/Agent A commits 150/);
  expect(
    screen.queryByRole("region", { name: "Mars exploration map" }),
  ).toBeNull();
  expect(document.querySelector(".app-shell")).toBeNull();
  expect(screen.queryByText("Activity log")).toBeNull();
  expect(screen.queryByRole("button", { name: "Reveal truth" })).toBeNull();
  expect(
    within(
      screen.getByRole("group", { name: "Coarse human prior" }),
    ).getAllByRole("button"),
  ).toHaveLength(4);
  await user.click(
    screen.getByRole("button", { name: "Region 1, 1; confidence 0.80" }),
  );
  expect(
    screen.getByText("Recommended cell (6, 4) · Prior confidence 0.80"),
  ).toBeTruthy();
  await user.type(
    screen.getByLabelText("Optional note"),
    "Inspect this region",
  );
  fetcher
    .mockResolvedValueOnce(json(snapshot({ status: "awaiting_human" })))
    .mockResolvedValueOnce(json([humanRequest("request-b", "B")]));
  await user.click(
    screen.getByRole("button", { name: "Submit recommendation & resume" }),
  );
  await screen.findByText(/Agent B commits 150/);
  expect(
    JSON.parse(
      String(
        fetcher.mock.calls.find(([url]) =>
          String(url).endsWith("/human-responses"),
        )?.[1]?.body,
      ),
    ),
  ).toEqual({
    requestId: "request-a",
    x: 6,
    y: 4,
    note: "Inspect this region",
  });
  expect(
    (screen.getByLabelText("Optional note") as HTMLTextAreaElement).value,
  ).toBe("");
  expect(
    (
      screen.getByRole("button", {
        name: "Submit recommendation & resume",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  await user.click(
    screen.getByRole("button", { name: "Region 0, 0; confidence 0.20" }),
  );
  fetcher.mockResolvedValueOnce(json(snapshot({ status: "paused", round: 1 })));
  await user.click(
    screen.getByRole("button", { name: "Submit recommendation & resume" }),
  );
  await screen.findByRole("region", { name: "Mars exploration map" });
  expect(
    fetcher.mock.calls.filter(([url]) => String(url).endsWith("/step")),
  ).toHaveLength(1);
});
it("keeps the advisor boundary closed while request loading fails", async () => {
  const { fetcher, user } = setup();
  await screen.findByRole("button", { name: "Create experiment" });
  fetcher
    .mockResolvedValueOnce(json(snapshot({ status: "awaiting_human" })))
    .mockResolvedValueOnce(json({ detail: "Cannot load advisor packet" }, 503));
  await user.click(screen.getByRole("button", { name: "Create experiment" }));
  await screen.findByRole("alert");
  expect(screen.getByRole("dialog")).toBeTruthy();
  expect(document.querySelector(".app-shell")).toBeNull();
  fetcher.mockResolvedValueOnce(json([humanRequest()]));
  await user.click(
    screen.getByRole("button", { name: "Refresh pending requests" }),
  );
  await screen.findByRole("group", { name: "Coarse human prior" });
});
it("renders failure payouts and reveals truth only after explicit HTTP consent", async () => {
  const { fetcher, user } = setup();
  await screen.findByRole("button", { name: "Create experiment" });
  fetcher.mockResolvedValueOnce(json(terminal()));
  await user.click(screen.getByRole("button", { name: "Create experiment" }));
  await screen.findByRole("region", { name: "Final results" });
  expect(screen.getByText("-250")).toBeTruthy();
  expect(screen.getAllByText("Human assisted").length).toBeGreaterThan(0);
  expect(screen.queryByRole("heading", { name: "Ground truth" })).toBeNull();
  fetcher.mockResolvedValueOnce(json(groundTruth));
  await user.click(screen.getByRole("button", { name: "Reveal truth" }));
  await screen.findByRole("heading", { name: "Ground truth" });
  await user.click(screen.getByRole("button", { name: "Hide truth" }));
  await waitFor(() =>
    expect(screen.queryByRole("heading", { name: "Ground truth" })).toBeNull(),
  );
});
it("renders nullable pool event fields and does not put human evidence on the shared board", () => {
  const state = snapshot();
  state.pool.events = [
    {
      id: "e",
      evidenceId: "e",
      agentId: "A",
      kind: "observation",
      observedRound: 1,
      sharedRound: 2,
      position: null,
      confidence: null,
      summary: "Noisy observation",
    },
    {
      id: "private",
      evidenceId: "private",
      agentId: "B",
      kind: "human",
      observedRound: 1,
      sharedRound: 2,
      summary: "Private human advice",
    },
  ];
  render(<InformationPool pool={state.pool} />);
  expect(screen.getByText("Noisy observation")).toBeTruthy();
  expect(screen.queryByText("Private human advice")).toBeNull();
});

it("replays the recorded run from zero without posting model steps", async () => {
  const { fetcher, user } = setup();
  await screen.findByRole("button", { name: "Create experiment" });
  fetcher.mockResolvedValueOnce(json(snapshot({ round: 2, status: "paused" })));
  await user.click(screen.getByRole("button", { name: "Create experiment" }));
  await screen.findByRole("region", { name: "Mars exploration map" });
  fetcher.mockResolvedValueOnce(
    json({
      rounds: [
        snapshot({ round: 0 }),
        snapshot({ round: 1, status: "paused" }),
        snapshot({ round: 2, status: "paused" }),
      ],
    }),
  );
  await user.click(screen.getByRole("button", { name: "Replay recorded run" }));
  await screen.findByRole("region", { name: "Recorded run replay" });
  expect(
    fetcher.mock.calls.filter(([url]) => String(url).endsWith("/step")),
  ).toHaveLength(0);
  await user.click(screen.getByRole("button", { name: "Forward one round" }));
  await user.click(screen.getByRole("button", { name: "Forward one round" }));
  expect(
    fetcher.mock.calls.filter(([url]) => String(url).endsWith("/step")),
  ).toHaveLength(0);
  await user.click(screen.getByRole("button", { name: "Exit replay" }));
  expect(screen.queryByRole("region", { name: "Recorded run replay" })).toBeNull();
  expect(
    fetcher.mock.calls.filter(([url]) => String(url).endsWith("/step")),
  ).toHaveLength(0);
});
it("renders creation when the API omits every null field", async () => {
  const { fetcher, user } = setup();
  await screen.findByRole("button", { name: "Create experiment" });
  const omitted = JSON.parse(
    JSON.stringify(snapshot(), (_key, value) =>
      value === null ? undefined : value,
    ),
  );
  fetcher.mockResolvedValueOnce(json(omitted));
  await user.click(screen.getByRole("button", { name: "Create experiment" }));
  await screen.findByRole("region", { name: "Mars exploration map" });
  expect(screen.getByText("None yet")).toBeTruthy();
  expect(document.querySelectorAll("polyline[data-agent-path]")).toHaveLength(
    2,
  );
});

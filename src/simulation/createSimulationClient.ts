import { createBackendSimulationClient } from "./BackendSimulationClient";
import { MockSimulationClient } from "./MockSimulationClient";
import type { SimulationClient } from "./SimulationClient";

export function createSimulationClient(): SimulationClient {
  const mode = import.meta.env.VITE_SIMULATION_MODE ?? "demo";
  if (mode === "demo") return new MockSimulationClient();
  if (mode === "backend") return createBackendSimulationClient();
  throw new Error(`Unknown simulation mode: ${mode}`);
}

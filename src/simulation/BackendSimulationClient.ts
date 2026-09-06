import type { SimulationClient } from "./SimulationClient";

/** Implement this boundary when Eduardo's transport and payloads are agreed.
 * Map and validate backend snapshots here. Never silently fall back to demo data.
 */
export function createBackendSimulationClient(): SimulationClient {
  throw new Error(
    "Backend adapter is not connected. Use demo mode until Eduardo’s interface is configured.",
  );
}

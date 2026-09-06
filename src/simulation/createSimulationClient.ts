import { createBackendSimulationClient } from "./BackendSimulationClient";

/** Every run uses the local Gemini backend; there is no demo or fallback policy. */
export const createSimulationClient = createBackendSimulationClient;

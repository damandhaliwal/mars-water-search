import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { createSimulationClient } from "./simulation/createSimulationClient";
import "./styles.css";

const root = createRoot(document.getElementById("root")!);
try {
  const client = createSimulationClient();
  if (import.meta.hot) import.meta.hot.dispose(() => client.dispose());
  root.render(
    <StrictMode>
      <App client={client} />
    </StrictMode>,
  );
} catch (error) {
  root.render(
    <main className="loading-state">
      <h1>Connection unavailable</h1>
      <p role="alert">
        {error instanceof Error
          ? error.message
          : "Unable to initialize the simulation provider."}
      </p>
    </main>,
  );
}

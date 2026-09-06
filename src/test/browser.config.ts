import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./browser",
  outputDir: "/tmp/mars-frontend-browser-results",
  projects: [
    { name: "network-fixtures", testMatch: "frontend.spec.ts" },
    { name: "local-backend", testMatch: "live.spec.ts" },
  ],
  workers: 1,
  fullyParallel: false,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5173",
    channel: "chrome",
    headless: true,
    viewport: { width: 1440, height: 1000 },
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "npm run dev -- --port 5173 --strictPort",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: true,
    timeout: 30000,
  },
});

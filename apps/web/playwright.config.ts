import { defineConfig, devices } from "@playwright/test";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "../..");
const venvPython = resolve(
  root,
  process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python",
);
// cmd.exe treats a relative forward-slash path as `.venv` plus a switch, so pass an absolute, quoted path.
const python = existsSync(venvPython) ? `"${venvPython}"` : "python3";
const baseURL = process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3100";
const backendURL = process.env.VIVEKA_TEST_API_URL || "http://127.0.0.1:8100";
const channel = process.env.PLAYWRIGHT_CHANNEL;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 45000,
  reporter: [["list"]],
  use: { baseURL, trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1000 },
        ...(channel ? { channel } : {}),
      },
    },
  ],
  webServer: [
    {
      name: "FastAPI",
      command: `${python} -m uvicorn viveka.api:app --host 127.0.0.1 --port ${new URL(backendURL).port}`,
      cwd: root,
      url: `${backendURL}/v1/model-card`,
      env: { VIVEKA_SLM: "off" },
      timeout: 60000,
      reuseExistingServer: !process.env.CI,
    },
    {
      name: "Next.js",
      command: `npm run dev -- --port ${new URL(baseURL).port}`,
      url: baseURL,
      env: { VIVEKA_API_URL: backendURL },
      timeout: 90000,
      reuseExistingServer: !process.env.CI,
    },
  ],
});

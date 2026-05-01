import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  outputDir: "./results/test-results",
  timeout: 60_000,
  retries: 0,
  reporter: [
    ["list"],
    ["json", { outputFile: "./results/results.json" }],
  ],
  use: {
    baseURL: process.env.BASE_URL || "http://localhost:3000",
    trace: "on-first-retry",
  },
});

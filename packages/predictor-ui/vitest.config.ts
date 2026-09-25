import { defineConfig } from "vitest/config";

export default defineConfig({
  esbuild: { jsx: "automatic" },
  // Tests run outside UTC so a timestamp read in the wrong zone fails here,
  // not on a fan's phone.
  test: { environment: "jsdom", globals: true, setupFiles: "./test-setup.ts", env: { TZ: "America/Chicago" } },
});

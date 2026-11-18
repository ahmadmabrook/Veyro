import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

/**
 * Component tests. The dependency-free foundation under `tests/unit/` runs on Node's own
 * runner (`npm run test:foundation`) and is excluded here, so the two suites do not overlap
 * and neither can silently stop running.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/component/**/*.test.{ts,tsx}"],
    exclude: ["tests/unit/**", "tests/e2e/**", "node_modules/**"],
  },
});

import { resolve } from "node:path";

import { defineConfig } from "vitest/config";

// Pure-function unit tests (lib/quips.ts, lib/hallOfFame.ts) — Node env, no DOM.
// The "@/..." alias mirrors tsconfig so tests import the same paths as the app.
export default defineConfig({
  test: {
    environment: "node",
    include: ["**/*.test.ts"],
  },
  resolve: {
    alias: { "@": resolve(__dirname, ".") },
  },
});

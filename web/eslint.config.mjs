import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

/**
 * Flat config, because the linter could not run at all before this file existed.
 *
 * **`next lint` was removed in Next 16 and ESLint 10 ignores `.eslintrc.json`**, so
 * `npm run lint` answered "Invalid project directory provided, no such directory: .../lint"
 * and nothing in CI called it. A check that cannot run is a check nobody has -- the same
 * shape `CLAUDE.md` records for a test that passes vacuously -- so the config is migrated,
 * the script runs `eslint` directly, and `npm run verify` and the CI job both call it.
 */
const config = [
  ...nextCoreWebVitals,
  ...nextTypescript,
  {
    rules: {
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  },
  {
    ignores: [
      "src/design/tokens.generated.mjs",
      ".next/**",
      "node_modules/**",
      "playwright-report/**",
      "test-results/**",
    ],
  },
];

export default config;

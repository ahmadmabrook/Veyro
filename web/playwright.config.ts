import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests drive a real browser against a real Next server and a real FastAPI backend.
 *
 * **Nothing here is mocked, and that is the point.** The defects this suite exists to catch are
 * the ones only a browser finds: a form that submits natively because hydration did not happen,
 * a token that has no dark value, a focus ring that disappears, an Arabic layout that does not
 * mirror. A mocked API would have passed every one of them.
 *
 * `webServer` starts the **web** app only. The backend is started separately by
 * `tests/e2e/serve.mjs` and seeded by `tests/e2e/fixture.mjs`, deliberately: starting it here
 * would make "the API was reachable" part of the harness's own setup rather than something a
 * reader can check, and a suite that silently provisions a database is a suite whose green run
 * proves less than it looks.
 *
 * **`baseURL` is `localhost`, not `127.0.0.1`.** They are different origins to a browser, and
 * Next's dev server blocks cross-origin requests to its own dev resources -- which served a
 * page that rendered correctly and never hydrated. `next.config.mjs` now allows the loopback
 * address as well, and this stays on `localhost` so the suite exercises the ordinary path.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: /.*\.(spec|setup)\.ts$/,
  // Serial: one tenant, one saved session per role, and specs that sign out. Parallel
  // workers would race each other's cookies for no gain at this size -- and the login
  // budget is per subject, so parallel sign-ins would spend it faster rather than slower.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  timeout: 30_000,
  expect: { timeout: 7_000 },
  use: {
    baseURL: process.env.VEYRO_WEB_ORIGIN ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    // **One login per run, saved as a cookie.** MOD-011's limiter allows 30 logins per
    // minute per subject, so a suite whose every test signs in has a cap on how many tests
    // it may contain -- and it crossed that cap at 53, where the failure read as a timeout
    // rather than as a refusal. `auth.setup.ts` signs in twice (the owner and a weaker
    // reader) and the specs adopt the cookie.
    { name: "setup", testMatch: /.*\.setup\.ts/, use: { ...devices["Desktop Chrome"] } },
    {
      name: "chromium",
      // The top-level `testMatch` has to admit the setup files for the project above to
      // find them, which means this project matches them too -- and ran both sign-ins a
      // second time, spending the login budget this arrangement exists to protect.
      testIgnore: /.*\.setup\.ts/,
      use: { ...devices["Desktop Chrome"] },
      dependencies: ["setup"],
    },
  ],
  webServer: {
    // In CI the suite drives the **production** build, which is what gets deployed: a dev
    // server differs in bundling, error handling and caching, and a gate that only ever saw
    // `next dev` is a gate that has not seen the artefact. Locally it reuses whatever dev
    // server is already running, because that is the loop a developer is in.
    command: process.env.CI ? "npm run start" : "npm run dev",
    url: "http://localhost:3000/login",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      VEYRO_API_ORIGIN: process.env.VEYRO_API_ORIGIN ?? "http://127.0.0.1:8000",
    },
  },
});

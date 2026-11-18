#!/usr/bin/env node
/**
 * Start the FastAPI backend for local and E2E use, on the development database.
 *
 * Deliberately a script rather than a Playwright `webServer` entry: the backend is a different
 * language and a different dependency tree, and a test harness that silently started it would
 * make "the API was reachable" part of the test's own setup rather than something a reader can
 * check. Run it, watch it bind, then run the tests.
 *
 *   node tests/e2e/serve.mjs            # foreground, Ctrl-C to stop
 *
 * `VEYRO_DATABASE_URL` points at the local container `verify_db.sh` builds. Nothing here
 * touches a managed or production target, which rule 9 of the isolation rule requires.
 */

import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const repo = fileURLToPath(new URL("../../..", import.meta.url));
const python = `${repo}/.venv/bin/python3`;
const dsn =
  process.env.VEYRO_DATABASE_URL ??
  "postgresql://postgres:veyro_dev@127.0.0.1:55432/veyro";

const child = spawn(
  python,
  [
    "-m",
    "uvicorn",
    "--factory",
    "app.main:create_app",
    "--host",
    "127.0.0.1",
    "--port",
    process.env.VEYRO_API_PORT ?? "8000",
    "--log-level",
    "warning",
  ],
  {
    cwd: `${repo}/backend`,
    stdio: "inherit",
    env: {
      // `config.py` fails closed on an unset or unknown environment, which is the behaviour
      // this script has to satisfy rather than work around: `local` is the only value that
      // names a developer's own machine.
      VEYRO_ENV: "local",
      VEYRO_RELEASE: "e2e",
      ...process.env,
      VEYRO_DATABASE_URL: dsn,
    },
  },
);

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => child.kill(signal));
}
child.on("exit", (code) => process.exit(code ?? 0));

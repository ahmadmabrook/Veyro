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

import { execFileSync, spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

const repo = fileURLToPath(new URL("../../..", import.meta.url));

// The repository's own virtualenv when it exists (a developer's machine), otherwise whatever
// `python3` resolves to -- which is what a CI runner has after `setup-python`. Hard-coding the
// venv path made this script work locally and fail on the runner with ENOENT, which reads as
// "the backend did not start" rather than "the interpreter is somewhere else".
const venv = `${repo}/.venv/bin/python3`;
const python = existsSync(venv) ? venv : "python3";
const dsn =
  process.env.VEYRO_DATABASE_URL ??
  "postgresql://postgres:veyro_dev@127.0.0.1:55432/veyro";

/**
 * **Reload is opt-in, and it is off for a reason.** A server that restarts when a backend
 * file changes is right while somebody is writing one and wrong while a suite is running: a
 * restart mid-run fails whichever test was mid-request, for a reason that has nothing to do
 * with the product. So `VEYRO_API_RELOAD=1` turns it on deliberately and nothing turns it on
 * by accident.
 *
 * The cost of leaving it off is real and worth naming, because it was paid three times in one
 * session: a backend route added while this server was already up is invisible to it, and the
 * failure reads as a frontend defect every time -- `405` on a path that does have a POST,
 * a bare `404`, and once a `TypeError: Cannot read properties of undefined` deep inside a
 * page, because the running server was returning a row without the field the read had just
 * learned to send. The startup line below prints the commit this process was started from, so
 * the next person has something to compare against before going looking in the client.
 */
const reload = process.env.VEYRO_API_RELOAD === "1";
const head = (() => {
  try {
    return execFileSync("git", ["rev-parse", "--short", "HEAD"], { cwd: repo })
      .toString()
      .trim();
  } catch {
    return "unknown";
  }
})();
console.log(
  reload
    ? `veyro api: starting from ${head} with reload -- backend edits restart it, which will ` +
      "fail whichever request a suite has in flight"
    : `veyro api: starting from ${head} -- a route added after this line is not served ` +
      "until this process restarts",
);

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
    ...(reload ? ["--reload", "--reload-dir", `${repo}/backend/app`] : []),
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
      // **MOD-011's per-identity request budget, raised for this harness only.**
      //
      // `api.request` is 600 a minute per identity and its own comment in `ratelimit.py`
      // says why it is generous: "a limit that trips during ordinary use is a limit
      // somebody will raise to infinity rather than investigate". A browser suite is not
      // ordinary use -- three hundred tests in three minutes, every one of them a page view
      // with its gate batch and its reads -- so it tripped the limiter, and six tests came
      // back with the page saying "something went wrong" when nothing had.
      //
      // **It failed in CI and passed on every laptop**, because a laptop runs `next dev` and
      // CI drives the production build, which is faster. Lowering the number for everybody
      // would be the mistake that comment names; so the override lives in `config.py`, is
      // bounded, and is refused outside the `local` environment -- which is the only
      // environment this script starts.
      VEYRO_API_REQUEST_BUDGET: "20000",
      ...process.env,
      VEYRO_DATABASE_URL: dsn,
    },
  },
);

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => child.kill(signal));
}
child.on("exit", (code) => process.exit(code ?? 0));

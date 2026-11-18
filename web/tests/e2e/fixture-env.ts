import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

/**
 * The synthetic tenant and owner `tests/e2e/fixture.mjs` provisioned.
 *
 * Read from `web/.env.e2e.local` rather than taken from the process environment, so a developer
 * running the suite does not have to export anything and -- more importantly -- so the password
 * never appears in a shell history, a CI log or a `ps` listing. The file is mode 600 and the
 * root `.gitignore` excludes it as `.env.*`.
 *
 * **No `import.meta.url` here.** Playwright transpiles specs to CommonJS, where that is a
 * syntax error -- and the error surfaces as "No tests found", which reads as an empty suite
 * rather than a broken one. The file is found by walking up from the working directory
 * instead, which works under `npm run e2e` from `web/` and from the repository root alike.
 */
export type Fixture = {
  tenantId: string;
  identityId: string;
  email: string;
  password: string;
};

const FILENAME = ".env.e2e.local";

function locate(): string {
  const candidates: string[] = [];
  let dir = resolve(process.cwd());
  for (let i = 0; i < 6; i += 1) {
    candidates.push(join(dir, FILENAME), join(dir, "web", FILENAME));
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  const found = candidates.find((path) => existsSync(path));
  if (!found) {
    throw new Error(
      `${FILENAME} not found (looked in ${candidates.length} places from ${process.cwd()}). ` +
        "Start the backend with `node tests/e2e/serve.mjs` and provision a tenant with " +
        "`node tests/e2e/fixture.mjs`, then run the suite again.",
    );
  }
  return found;
}

export function fixture(): Fixture {
  const raw = readFileSync(locate(), "utf8");
  const env: Record<string, string> = {};
  for (const line of raw.split("\n")) {
    if (!line || line.startsWith("#")) continue;
    const at = line.indexOf("=");
    if (at > 0) env[line.slice(0, at)] = line.slice(at + 1);
  }
  const required = [
    "VEYRO_E2E_TENANT_ID",
    "VEYRO_E2E_IDENTITY_ID",
    "VEYRO_E2E_EMAIL",
    "VEYRO_E2E_PASSWORD",
  ] as const;
  for (const key of required) {
    if (!env[key]) throw new Error(`${key} missing from ${FILENAME} -- re-run fixture.mjs`);
  }
  return {
    tenantId: env.VEYRO_E2E_TENANT_ID!,
    identityId: env.VEYRO_E2E_IDENTITY_ID!,
    email: env.VEYRO_E2E_EMAIL!,
    password: env.VEYRO_E2E_PASSWORD!,
  };
}

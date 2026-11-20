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
  /** One unused code, for the device challenge a browser gets on its first sign-in. */
  recoveryCode: string;
  zoneId: string;
  pointId: string;
  /** The site MOD-019's calendar is addressed by, and whose timezone it converts in. */
  locationId: string;
  /** The first of seven generated occurrences, and the one with a substitution on it. */
  sessionId: string;
  /** Tomorrow's occurrence, which has a booking on it -- the first one's window has closed. */
  bookedSessionId: string;
  /** The seeded member: a tag, a contact point, two notes and a health custom field. */
  personId: string;
  /** The commissioned, activated turnstile the access point stands on. */
  deviceId: string;
  /** A turnstile with four of paragraph 4175's seven tests, so it cannot go live. */
  pendingDeviceId: string;
  /**
   * A second identity holding `access.zone.read` and **not**
   * `tenancy.organization.read` -- the one the gated-navigation tests need, because the
   * owner holds every permission in the catalogue and can prove only the allowed half.
   */
  readerEmail: string;
  readerPassword: string;
  /**
   * A third identity holding `people.person.read` and nothing of MOD-017. The reader proves
   * the people gate by *not* holding the person read; the membership blocks' own gates can
   * only be proved by a session that holds it and holds none of MOD-017. One identity cannot
   * be both, which is why there are three.
   */
  deskEmail: string;
  deskPassword: string;
  /** The published membership product MOD-016's board opens, with one variant and one price. */
  productId: string;
  // **The account spec takes no credential from here, deliberately.** Every one of its
  // writes is destructive -- a trust that cannot be asserted twice, a revoke that locks the
  // subject out of the product for good -- so it registers a subject per test through the
  // open registration route instead. A fixture identity would have made it green on a fresh
  // database and red on the second run, which is the failure this repository has now
  // recorded four times.
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
    "VEYRO_E2E_RECOVERY_CODE",
    "VEYRO_E2E_ZONE_ID",
    "VEYRO_E2E_POINT_ID",
    "VEYRO_E2E_PERSON_ID",
    "VEYRO_E2E_DEVICE_ID",
    "VEYRO_E2E_PENDING_DEVICE_ID",
    "VEYRO_E2E_READER_EMAIL",
    "VEYRO_E2E_READER_PASSWORD",
    "VEYRO_E2E_DESK_EMAIL",
    "VEYRO_E2E_DESK_PASSWORD",
    "VEYRO_E2E_PRODUCT_ID",
    "VEYRO_E2E_LOCATION_ID",
    "VEYRO_E2E_SESSION_ID",
    "VEYRO_E2E_BOOKED_SESSION_ID",
  ] as const;
  for (const key of required) {
    if (!env[key]) throw new Error(`${key} missing from ${FILENAME} -- re-run fixture.mjs`);
  }
  return {
    tenantId: env.VEYRO_E2E_TENANT_ID!,
    identityId: env.VEYRO_E2E_IDENTITY_ID!,
    email: env.VEYRO_E2E_EMAIL!,
    password: env.VEYRO_E2E_PASSWORD!,
    recoveryCode: env.VEYRO_E2E_RECOVERY_CODE!,
    zoneId: env.VEYRO_E2E_ZONE_ID!,
    pointId: env.VEYRO_E2E_POINT_ID!,
    locationId: env.VEYRO_E2E_LOCATION_ID!,
    sessionId: env.VEYRO_E2E_SESSION_ID!,
    bookedSessionId: env.VEYRO_E2E_BOOKED_SESSION_ID!,
    personId: env.VEYRO_E2E_PERSON_ID!,
    deviceId: env.VEYRO_E2E_DEVICE_ID!,
    pendingDeviceId: env.VEYRO_E2E_PENDING_DEVICE_ID!,
    readerEmail: env.VEYRO_E2E_READER_EMAIL!,
    readerPassword: env.VEYRO_E2E_READER_PASSWORD!,
    deskEmail: env.VEYRO_E2E_DESK_EMAIL!,
    deskPassword: env.VEYRO_E2E_DESK_PASSWORD!,
    productId: env.VEYRO_E2E_PRODUCT_ID!,
  };
}

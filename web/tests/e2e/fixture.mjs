#!/usr/bin/env node
/**
 * Provision a synthetic tenant, an owner identity and the one-time authorization bootstrap,
 * entirely over HTTP against a locally running backend.
 *
 * **Over HTTP on purpose.** `backend/tests/support.py` builds an owner through the service layer
 * because the HTTP path spends a dozen scrypt hashes per tenant and that is most of the suite's
 * wall-clock. Here the request path *is* what is under test: the web app talks to the API and
 * nothing else, so a fixture that reached past it would prove the browser works against a door
 * nobody opened. MOD-014's review says this in as many words -- no test ever called a `/people`
 * route successfully, which is why four findings passed a green suite.
 *
 * **Synthetic, local, generated.** Rule 9 of the isolation rule: generated UUIDs and synthetic
 * tenants in a local container, never real data and never a managed target. The password is
 * generated per run by `crypto.randomUUID`, written to `web/.env.e2e.local` (which the root
 * `.gitignore` already excludes as `.env.*`), and never printed.
 *
 *   node tests/e2e/fixture.mjs            # provision and write .env.e2e.local
 *   node tests/e2e/fixture.mjs --print    # also print the tenant id (not the password)
 */

import { spawnSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { existsSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { browserFingerprint } from "./device.mjs";

const api = process.env.VEYRO_API_ORIGIN ?? "http://127.0.0.1:8000";

/** A correlation id per call, so a decision here is traceable to one there. */
/**
 * The club's own timezone, and the one fact about it a seed has to know.
 *
 * Amman has been permanently UTC+3 since it abolished DST in 2022, which is why a fixed
 * offset is honest here rather than a shortcut. The *reason* it has to be stated at all is
 * the bug below.
 */
const CLUB_TZ = "Asia/Amman";
const CLUB_OFFSET_HOURS = 3;

/**
 * The UTC instant for a local hour on the local day `daysBack` days before the club's today.
 *
 * **Seeding days by subtracting 86,400,000 milliseconds counts days in UTC, and every read
 * that renders them counts days in the club's zone.** Those agree for twenty-one hours out
 * of twenty-four and disagree for the three after 21:00 UTC, when Amman has already turned
 * over: `Date.now() - 86400000` with the UTC hour pinned then lands two local days back, so
 * FD-03's "Last in 1 day ago" renders "2 days ago" and the suite goes red for a reason that
 * has nothing to do with the commit under test. It did, on a documentation-only commit
 * pushed at 21:05 UTC.
 *
 * **The old comment claimed immunity from exactly this** -- "mid-morning local, so an entry
 * never lands on a neighbouring day by accident of the hour the fixture runs". Mid-morning
 * was right and insufficient: the hour within the day was safe and the day itself was not,
 * because it was picked in the wrong frame. This repository already records the service
 * version of the same mistake twice, and a fixture is where it is hardest to see, since the
 * number it produces looks like data rather than like arithmetic.
 *
 * So the day is chosen on the club's calendar and the clock is set from it, which is stable
 * at every hour of the run.
 */
function clubLocalInstant(daysBack, localHour, localMinute = 0) {
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: CLUB_TZ }).format(new Date());
  const when = new Date(`${today}T00:00:00Z`);
  when.setUTCDate(when.getUTCDate() - daysBack);
  when.setUTCHours(localHour - CLUB_OFFSET_HOURS, localMinute, 0, 0);
  return when;
}

function cid() {
  return randomUUID();
}

/**
 * Run the real worker once over this tenant, and fail the fixture if it fails.
 *
 * **The binary, not a stand-in.** The fixture used to call `/people/timeline/project` by hand,
 * which seeded a timeline and proved nothing about the thing that is supposed to call it. This
 * runs `python -m app.worker --once`, which is the same entry point a process manager runs, so
 * the browser suite that follows is looking at rows a scheduled job actually wrote -- the
 * relay's dispatch, the timeline projection and the two sweeps.
 *
 * Scoped to this tenant with `--tenant`, because a developer's database holds every tenant any
 * earlier run ever provisioned and sweeping all of them would make the fixture's wall-clock a
 * function of how long the machine has been used.
 */
function runWorkerTick(tenantId) {
  const repo = fileURLToPath(new URL("../../..", import.meta.url));
  const venv = `${repo}/.venv/bin/python3`;
  const python = existsSync(venv) ? venv : "python3";
  const result = spawnSync(python, ["-m", "app.worker", "--once", "--tenant", tenantId], {
    cwd: `${repo}/backend`,
    encoding: "utf8",
    env: {
      VEYRO_ENV: "local",
      VEYRO_RELEASE: "e2e",
      ...process.env,
      VEYRO_DATABASE_URL:
        process.env.VEYRO_DATABASE_URL ??
        "postgresql://postgres:veyro_dev@127.0.0.1:55432/veyro",
    },
  });
  if (result.status !== 0) {
    throw new Error(
      `worker tick failed (${result.status}): ${(result.stderr ?? "").slice(-600)}`,
    );
  }
  return JSON.parse(result.stdout);
}

async function call(path, { method = "GET", body, tenant, token } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (tenant) headers["X-Veyro-Tenant"] = tenant;
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${api}${path}`, {
    method,
    headers,
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const text = await response.text();
  let parsed;
  try {
    parsed = text ? JSON.parse(text) : undefined;
  } catch {
    parsed = text;
  }
  if (!response.ok) {
    throw new Error(
      `${method} ${path} -> ${response.status} ${JSON.stringify(parsed)?.slice(0, 400)}`,
    );
  }
  return parsed;
}

/**
 * Raise a session to AAL 2 with a recovery code.
 *
 * **Most of this fixture needs it.** The hierarchy writes, every billing write, a flag or
 * configuration change, publishing a device type or an access policy and issuing a credential
 * are all `financial` in MOD-008's catalogue, which maps to assurance level 2 -- and a session
 * opened with a password alone is level 1. That is the product working: "a grant is not a
 * session" is MOD-014's finding, and a fixture that could skip the step-up would be proving
 * the opposite of what the gate does.
 *
 * A recovery code is what this build can actually verify. AAL 3 needs a hardware factor
 * MOD-007 cannot check, which is why nothing here reaches it.
 */
async function stepUp(tenantId, token, identityId, password) {
  const codes = await call(`/identities/${identityId}/recovery-codes`, {
    method: "POST", tenant: tenantId, token,
    body: { correlation_id: cid(), current_password: password },
  });
  const asked = await call("/auth/require/financial", { tenant: tenantId, token });
  const stepped = await call("/auth/step-up", {
    method: "POST", tenant: tenantId, token,
    body: { challenge: asked.challenge, recovery_code: codes.codes[0], correlation_id: cid() },
  });
  return stepped.token ?? token;
}

/**
 * Confirm the browser's device, so no test has to spend a single-use recovery code.
 *
 * **This is the fixture answering a control rather than working around one.** MOD-007
 * challenges a login from a device it has not seen and confirms that device when the
 * challenge is answered -- permanently. A browser is a different device from this script, so
 * the first sign-in through the web app was challenged and the suite answered it with the one
 * spare code in `.env.e2e.local`. That works exactly once: a second Playwright run against
 * the same fixture found the code spent, every signing-in test timed out at the recovery
 * field, and the suite's green depended on how many times it had been run. So the fixture
 * logs in *as the browser's device* -- the label comes from the same formula the app uses --
 * and answers the challenge itself.
 *
 * The challenge path is still proved, by `tests/component/login-form.test.tsx`, which is
 * where it belongs for the same reason: a once-per-fixture event cannot be asserted by a test
 * whose turn comes second.
 */
async function confirmWebDevice(tenantId, identityId, token, email, password) {
  const batch = await call(`/identities/${identityId}/recovery-codes`, {
    method: "POST", tenant: tenantId, token,
    body: { correlation_id: cid(), current_password: password },
  });
  const asked = await call("/auth/login", {
    method: "POST", tenant: tenantId,
    body: {
      identifier: email, password, correlation_id: cid(),
      device_fingerprint: browserFingerprint(tenantId, email),
      device_label: "Veyro web",
    },
  });
  if (!asked.challenge) {
    // Already confirmed, which happens when the fixture is re-run against a database that
    // still holds the device. Nothing to answer.
    return;
  }
  await call("/auth/challenge", {
    method: "POST", tenant: tenantId,
    body: {
      identifier: email, challenge: asked.challenge,
      recovery_code: batch.codes[0], correlation_id: cid(),
    },
  });
}

export async function provision() {
  const stamp = Date.now();
  const password = `e2e-${randomUUID()}`;
  const email = `owner+${stamp}@veyro.invalid`;

  // 1. A tenant. The platform plane is unauthenticated in this build and `CLAUDE.md` says so
  //    plainly -- which is exactly why nothing may be deployed where it is reachable.
  const tenant = await call("/platform/tenants", {
    method: "POST",
    body: {
      external_key: `e2e-${stamp}`,
      display_name: `E2E Fixture ${stamp}`,
      region: "eu-west-1",
      actor_id: randomUUID(),
      correlation_id: cid(),
      idempotency_key: randomUUID(),
    },
  });
  const tenantId = tenant.tenant_id ?? tenant.id;
  if (!tenantId) throw new Error(`no tenant id in ${JSON.stringify(tenant)}`);

  // 2. Move it to `active`. `provisioned` is not a state a product route serves.
  await call(`/platform/tenants/${tenantId}/activate`, {
    method: "POST",
    body: { actor_id: randomUUID(), correlation_id: cid(), idempotency_key: randomUUID() },
  }).catch((error) => {
    // Already active is not a failure; anything else is.
    if (!/already|conflict|409/i.test(String(error))) throw error;
  });

  // 3. An identity. Registration is open -- MOD-007's named gap, and the same
  //    unauthenticated-header problem as the platform plane rather than a separate one.
  const identity = await call("/identities", {
    method: "POST",
    tenant: tenantId,
    body: { display_name: "E2E Owner", correlation_id: cid(), email, password },
  });

  // 4. A session, by the same route the browser will use.
  const signedIn = await call("/auth/login", {
    method: "POST",
    tenant: tenantId,
    body: { identifier: email, password, correlation_id: cid() },
  });
  const token = signedIn.token ?? signedIn.session_token;
  if (!token) throw new Error(`login returned no token: ${JSON.stringify(Object.keys(signedIn))}`);

  // 5. The bootstrap: one tenant-wide role holding everything, refused once any assignment
  //    exists. A tenant is unusable until somebody does this, which is one call and self-closing.
  const bootstrapped = await call("/authz/bootstrap", {
    method: "POST",
    tenant: tenantId,
    token,
    body: { correlation_id: cid() },
  });

  // 6. A door, so the MOD-022 surface has something real to show. Everything here goes
  //    through the product's own routes: a zone, a MOD-021 device commissioned and
  //    activated, an access point on it, a published policy (two acts, two people) and a
  //    credential. Then one presentation, so the decision log is not empty.
  //
  //    **Publishing needs a second identity**, because `acc_policies_publisher_is_not_author`
  //    refuses the author settling their own draft -- which is the control, so the fixture
  //    has to satisfy it rather than work around it.
  const ownerIdentityId = identity.identity_id ?? identity.id;
  const ownerToken = await stepUp(tenantId, token, ownerIdentityId, password);

  await confirmWebDevice(tenantId, ownerIdentityId, ownerToken, email, password);

  // **One spare recovery code, minted last so it is unspent.** The device confirmation above
  // used the batch it minted, and issuing a batch replaces the previous one -- so this is the
  // code any test needing a step-up can spend, and nothing in the ordinary sign-in path
  // touches it. Synthetic, local and disposable like everything else here, and written to the
  // same mode-600 file.
  const spare = await call(`/identities/${ownerIdentityId}/recovery-codes`, {
    method: "POST", tenant: tenantId, token: ownerToken,
    body: { correlation_id: cid(), current_password: password },
  });
  const access = await seedAccess(tenantId, ownerToken, email, ownerIdentityId);

  return {
    tenantId,
    identityId: identity.identity_id ?? identity.id,
    email,
    password,
    role: bootstrapped.role_key ?? "tenant_admin",
    // `authz.bootstrap` answers with a count, not a list -- the first version read
    // `.length` off the number and printed `permissions null`, which reads as a
    // bootstrap that granted nothing.
    permissions: bootstrapped.permissions ?? null,
    recoveryCode: spare.codes[0],
    ...access,
  };
}

async function seedAccess(tenantId, token, ownerEmail, ownerIdentityId) {
  const as = (t) => ({ tenant: tenantId, token: t });

  const org = await call("/organizations", {
    method: "POST", ...as(token),
    body: { legal_name: "Veyro Sites Ltd", country_code: "JO", correlation_id: cid() },
  });
  const brand = await call("/brands", {
    method: "POST", ...as(token),
    body: { organization_id: org.organization_id, brand_name: "City" },
  });
  const location = await call("/locations", {
    method: "POST", ...as(token),
    body: { brand_id: brand.brand_id, location_name: "Downtown", timezone: "Asia/Amman" },
  });

  const type = await call("/fleet/types", {
    method: "POST", ...as(token),
    body: {
      type_code: `ACME-${Date.now().toString(36).toUpperCase()}`, vendor: "Acme",
      model: "Gate 3000", kind: "turnstile", display_name: "Acme Gate 3000",
      capabilities: ["access.actuate", "credential.read", "telemetry"],
      correlation_id: cid(),
    },
  });

  // The second person. Registration is open in this build, and the bootstrap has already
  // been spent -- so this identity is granted a role by the owner rather than bootstrapping.
  const secondEmail = `publisher+${Date.now()}@veyro.invalid`;
  const secondPassword = `e2e-${randomUUID()}`;
  await call("/identities", {
    method: "POST", tenant: tenantId,
    body: {
      display_name: "E2E Publisher", correlation_id: cid(), email: secondEmail,
      password: secondPassword,
    },
  });
  const secondSignIn = await call("/auth/login", {
    method: "POST", tenant: tenantId,
    body: { identifier: secondEmail, password: secondPassword, correlation_id: cid() },
  });
  const secondToken = secondSignIn.token;
  const secondSession = await call("/auth/session", { ...as(secondToken) });
  const role = await call("/authz/roles", {
    method: "POST", ...as(token),
    body: {
      role_key: `publisher_${Date.now()}`, display_name: "Publisher",
      // **`scheduling.schedule.read` without `scheduling.session.change`** is the pair that
      // makes MOD-019's masked reason provable: this session can read the board and cannot
      // record a change, so the reason on a substitution arrives withheld. The owner holds
      // both and so can only ever prove the unmasked half -- the same reason this identity
      // exists at all.
      permissions: ["devices.type.publish", "access.policy.publish", "access.zone.read",
                    "scheduling.schedule.read",
                    // **A contract version is two acts by two people, by constraint.**
                    // `mem_contract_versions_publisher_is_not_author` compares the two
                    // identities, so the owner cannot publish what the owner drafted and a
                    // fixture with one session could not write this fixture at all.
                    "membership.contract.publish",
                    // **And the template approval**, which is the same two-act shape: a
                    // template goes out under the tenant's name to everybody, so its author
                    // cannot approve it -- MOD-008's separation of duties applied to content,
                    // and a constraint rather than a convention.
                    "notifications.template.approve",
                    // **And the refund approval**, because ADM-PAY-01's whole argument is
                    // that money leaving the business takes two people: the requester is
                    // the caller's own session and `approved_by <> requested_by` compares
                    // two identities the server derived. The owner requests; this identity
                    // decides. A fixture with one session could not seed a refund at all.
                    "finance.refund.approve"],
      correlation_id: cid(),
    },
  });
  await call("/authz/assignments", {
    method: "POST", ...as(token),
    body: {
      identity_id: secondSession.identity_id, role_key: role.role_key,
      correlation_id: cid(),
    },
  });
  // Publishing is financial class, so the second identity needs a stepped-up session too.
  const publisherToken = await stepUp(
    tenantId, secondToken, secondSession.identity_id, secondPassword);

  // **A second, deliberately weaker browser session.** This identity holds
  // `access.zone.read` and not `tenancy.organization.read`, which is what lets a spec prove
  // that the navigation is filtered per item rather than all-or-nothing -- the owner holds
  // every permission in the catalogue and so can prove only the allowed half. Its device is
  // confirmed here for the same reason the owner's is: the label is per identity, so this is
  // a different device to MOD-007.
  await confirmWebDevice(
    tenantId, secondSession.identity_id, publisherToken, secondEmail, secondPassword);

  await call(`/fleet/types/${type.type_id}/publish`, {
    method: "POST", ...as(publisherToken), body: { correlation_id: cid() },
  });

  const device = await call("/fleet", {
    method: "POST", ...as(token),
    body: {
      type_id: type.type_id, location_id: location.location_id,
      serial_number: `SN-${randomUUID().slice(0, 10).toUpperCase()}`,
      display_name: "North turnstile", correlation_id: cid(),
    },
  });
  const notBefore = new Date(Date.now() - 60_000).toISOString();
  const notAfter = new Date(Date.now() + 90 * 86_400_000).toISOString();
  await call(`/fleet/${device.device_id}/provision`, {
    method: "POST", ...as(token),
    body: {
      fingerprint: (randomUUID() + randomUUID()).replace(/-/g, "").slice(0, 64),
      vault_ref: "vault:acme/gate/1", not_before: notBefore, not_after: notAfter,
      correlation_id: cid(),
    },
  });
  await call(`/fleet/${device.device_id}/commission`, {
    method: "POST", ...as(token),
    body: {
      profile: "fail_safe", on_egress_path: true, fire_release_is_independent: true,
      local_emergency_input: true, evidence_ref: "uri:certs/fire-officer-2026-11",
      door_description: "north entrance, single leaf", correlation_id: cid(),
    },
  });
  for (const testName of ["power_loss", "edge_agent_crash", "controller_disconnect",
                          "fire_alarm_input", "emergency_unlock", "recovery",
                          "manual_override"]) {
    await call(`/fleet/${device.device_id}/commissioning-tests`, {
      method: "POST", ...as(token),
      body: { test_name: testName, passed: true, correlation_id: cid() },
    });
  }
  await call(`/fleet/${device.device_id}/activate`, {
    method: "POST", ...as(token), body: { correlation_id: cid() },
  });

  // **A fleet worth looking at.** One device is not a board: the three shapes an operator
  // actually has to tell apart are a door that works, a door that cannot go live because
  // paragraph 4175's commissioning is incomplete, and a device that is not a door at all. A
  // surface built against a single healthy turnstile proves none of them.
  await call(`/fleet/${device.device_id}/health`, {
    method: "POST", ...as(token),
    body: {
      latency_ms: 42, error_count: 0, storage_free_bytes: 8 * 1024 * 1024 * 1024,
      agent_version: "1.4.2", correlation_id: cid(),
    },
  });

  // Part-commissioned: a safety profile and four of the seven tests, never activated. Its
  // `outstanding_tests` is the list paragraph 4175 blocks it on.
  const pending = await call("/fleet", {
    method: "POST", ...as(token),
    body: {
      type_id: type.type_id, location_id: location.location_id,
      serial_number: `SN-${randomUUID().slice(0, 10).toUpperCase()}`,
      display_name: "South turnstile", correlation_id: cid(),
    },
  });
  await call(`/fleet/${pending.device_id}/provision`, {
    method: "POST", ...as(token),
    body: {
      fingerprint: (randomUUID() + randomUUID()).replace(/-/g, "").slice(0, 64),
      vault_ref: "vault:acme/gate/2", not_before: notBefore, not_after: notAfter,
      correlation_id: cid(),
    },
  });
  await call(`/fleet/${pending.device_id}/commission`, {
    method: "POST", ...as(token),
    body: {
      profile: "fail_safe", on_egress_path: true, fire_release_is_independent: true,
      local_emergency_input: true, evidence_ref: "uri:certs/fire-officer-2026-11",
      door_description: "south entrance, single leaf", correlation_id: cid(),
    },
  });
  for (const testName of ["power_loss", "edge_agent_crash", "controller_disconnect",
                          "fire_alarm_input"]) {
    await call(`/fleet/${pending.device_id}/commissioning-tests`, {
      method: "POST", ...as(token),
      body: { test_name: testName, passed: true, correlation_id: cid() },
    });
  }

  // A scanner: no `access.actuate`, so it is not an access point and has no safety profile.
  // MOD-022's actuator trigger refuses a point declared over one, which is the whole reason
  // the capability set and the kind are separate facts.
  const scannerType = await call("/fleet/types", {
    method: "POST", ...as(token),
    body: {
      type_code: `SCAN-${Date.now().toString(36).toUpperCase()}`, vendor: "Acme",
      model: "Scan 100", kind: "scanner", display_name: "Acme Scan 100",
      capabilities: ["scan", "telemetry"], correlation_id: cid(),
    },
  });
  await call(`/fleet/types/${scannerType.type_id}/publish`, {
    method: "POST", ...as(publisherToken), body: { correlation_id: cid() },
  });
  await call("/fleet", {
    method: "POST", ...as(token),
    body: {
      type_id: scannerType.type_id, location_id: location.location_id,
      serial_number: `SN-${randomUUID().slice(0, 10).toUpperCase()}`,
      display_name: "Reception scanner", correlation_id: cid(),
    },
  });

  // **A fourth device: in service and not answering.** FD-08's whole requirement is that a
  // degraded row names what to do instead, and the three devices above cannot produce one --
  // two are registered and never activated, which is "out of service" rather than an
  // incident, and the third reports health a line above. So the strip's fallback branch, and
  // the fleet board's own "needs somebody" block, had no fixture between them: both had only
  // ever been seen empty.
  //
  // **A scanner rather than a turnstile**, because `activate_device` re-runs paragraph
  // 4175's commissioning gate for anything that can move a barrier and a scanner declares
  // `credential.read` instead. It is activated and never reports, which is exactly
  // `blocks_operation`: in service, unreachable, and the one shape MOD-021 says to page on.
  const silent = await call("/fleet", {
    method: "POST", ...as(token),
    body: {
      type_id: scannerType.type_id, location_id: location.location_id,
      serial_number: `SN-${randomUUID().slice(0, 10).toUpperCase()}`,
      display_name: "Studio A scanner", correlation_id: cid(),
    },
  });
  // Provisioned first: `registered` has no agent behind it, and the state machine refuses
  // the jump -- a device with no credential cannot be in service.
  await call(`/fleet/${silent.device_id}/provision`, {
    method: "POST", ...as(token),
    body: {
      fingerprint: (randomUUID() + randomUUID()).replace(/-/g, "").slice(0, 64),
      vault_ref: "vault:acme/studio-a/scanner",
      not_before: new Date(Date.now() - 60_000).toISOString(),
      not_after: new Date(Date.now() + 90 * 86_400_000).toISOString(),
      correlation_id: cid(),
    },
  });
  await call(`/fleet/${silent.device_id}/activate`, {
    method: "POST", ...as(token), body: { correlation_id: cid() },
  });

  const zone = await call("/access/zones", {
    method: "POST", ...as(token),
    body: {
      location_id: location.location_id, zone_key: "main-floor",
      display_name: "Main floor", risk_class: "standard", correlation_id: cid(),
    },
  });
  const point = await call("/access/points", {
    method: "POST", ...as(token),
    body: {
      zone_id: zone.zone_id, device_id: device.device_id, direction: "entry",
      display_name: "North turnstile", correlation_id: cid(),
    },
  });
  const policy = await call("/access/policies", {
    method: "POST", ...as(token),
    body: {
      // **The window is the whole day on purpose.** A 06:00-23:00 policy is the realistic
      // one and makes the seeded decision depend on what time the fixture ran: an evening
      // run gets `outside_opening_hours` and a morning run gets `no_entitlement`, so any
      // test asserting the decision log would pass or fail by the clock. A full-day window
      // still exercises the opening-hours rendering (00:00-23:59) and lets the presentation
      // reach the entitlement check, which is the *restricted* refusal -- the row the
      // public/private split is actually about.
      zone_id: zone.zone_id, requires_entitlement: true, opens_minute: 0,
      closes_minute: 23 * 60 + 59, anti_passback_seconds: 60, correlation_id: cid(),
    },
  });
  await call(`/access/policies/${policy.policy_id}/publish`, {
    method: "POST", ...as(publisherToken), body: { correlation_id: cid() },
  });

  // A second zone with no published policy, so a surface test can tell the two states
  // apart. A board that rendered the gap as an empty cell would read as "no restrictions",
  // which is the opposite of true -- and with only one zone, seeded with terms, no test
  // could see the difference.
  await call("/access/zones", {
    method: "POST", ...as(token),
    body: {
      location_id: location.location_id, zone_key: "plant-room",
      display_name: "Plant room", risk_class: "high_risk", correlation_id: cid(),
    },
  });

  const person = await call("/people", {
    method: "POST", ...as(token),
    body: {
      legal_name: "Jane Member", correlation_id: cid(),
      // **A birth date, because MOD-019 derives an age rather than accepting one.** The
      // schedule template below carries a `min_age` restriction and `take_hold` reads
      // `ppl_persons.date_of_birth` to answer it -- a reviewer put a fourteen-year-old in an
      // 18+ class by sending an age, which is why the column is the only source. It is an
      // `identity`-class field, so it is masked on the Member 360 at AAL 1 like the legal
      // name beside it.
      date_of_birth: "1994-05-20",
    },
  });
  // **A person with something to show, and something to withhold.** MOD-014's masking is the
  // one place in the build where `Decision.mask` reaches a read path, and a surface cannot be
  // shown to apply it against a record with nothing classified: `health` maps to AAL 3, which
  // is reached only by a passkey sign-in, so a health note and a health custom field
  // are masked for *every* caller. Both are seeded, beside an ordinary note and an ordinary
  // tag, so a test can tell "withheld" from "absent".
  await call(`/people/${person.person_id}/member-profile`, {
    method: "POST", ...as(token),
    // **A join date, because ADM-MEM-10's duplicate banner identifies a record by one.**
    // Without it the banner falls back to when the record was first known, which for a
    // fixture is "today" -- so the screen rendered "known since Nov 2026" and demonstrated
    // the fallback rather than the ordinary case the canvas draws ("joined Feb 2025").
    body: { correlation_id: cid(), lifecycle_state: "lead", member_number: "M-00042",
            joined_on: "2025-02-12" },
  });
  await call(`/people/${person.person_id}/contacts`, {
    method: "POST", ...as(token),
    body: { kind: "email", value: "jane.member@veyro.test", is_primary: true,
            correlation_id: cid() },
  });
  // **A phone, because ADM-MEM-10's duplicate check runs on one.** Nothing in the build had
  // seeded a phone contact point, so the screen whose whole subject is "this number already
  // has a record" had no number to find -- and a test against the unseeded version would
  // assert an empty state, which proves nothing about the populated one.
  //
  // **Not the canvas's own number**, deliberately: `+962 79 662 4180` is a plausible real
  // Jordanian mobile, and this repository's standard is synthetic data. The `0042` pairs with
  // the member number above so it reads as a fixture at a glance, and the detection assertion
  // is about the *answer* rather than the digits.
  await call(`/people/${person.person_id}/contacts`, {
    method: "POST", ...as(token),
    body: { kind: "phone", value: "+962 79 000 0042", is_primary: true,
            correlation_id: cid() },
  });
  const tag = await call("/people/tags", {
    method: "POST", ...as(token),
    body: { tag_key: "vip", display_name: "VIP", correlation_id: cid() },
  });
  await call(`/people/${person.person_id}/tags`, {
    method: "POST", ...as(token),
    body: { tag_id: tag.tag_id, correlation_id: cid() },
  });
  await call("/people/custom-fields", {
    method: "POST", ...as(token),
    body: { field_key: "injury_history", display_name: "Injury history",
            value_type: "text", sensitivity: "health", correlation_id: cid() },
  });
  await call(`/people/${person.person_id}/custom-fields`, {
    method: "PUT", ...as(token),
    body: { field_key: "injury_history", value: "left knee, 2025",
            correlation_id: cid() },
  });
  await call(`/people/${person.person_id}/notes`, {
    method: "POST", ...as(token),
    body: { body: "Prefers the 7am class.", note_class: "general",
            correlation_id: cid() },
  });
  await call(`/people/${person.person_id}/notes`, {
    method: "POST", ...as(token),
    body: { body: "Cleared for training by her physiotherapist.", note_class: "health",
            correlation_id: cid() },
  });

  // **A near-duplicate and a projected timeline, because both are empty until something
  // runs.** MOD-014 projects the timeline from MOD-010's outbox when somebody calls it --
  // the thirteenth module waiting on a worker runtime -- and the duplicate detector scores a
  // person against everybody sharing an exact signal. A surface built against the unseeded
  // version would be a page of empty states, which proves nothing about the populated one.
  const twin = await call("/people", {
    method: "POST", ...as(token),
    body: { legal_name: "Jane Member", correlation_id: cid(),
            contacts: [{ kind: "email", value: "jane.member@veyro.test", is_primary: true }] },
  });
  // **A second phone that is somebody's, and a different somebody's.** ADM-MEM-10 keys its
  // "different person" acknowledgement to the value it was given, and the only way to show
  // that in a browser is two numbers that each already have a record: acknowledge one, type
  // the other, and the interruption has to come back. One seeded number can only ever prove
  // that the acknowledgement sticks. A *different* number from Jane's, so it adds no matching
  // signal and the duplicate pair's score stays where the people board asserts it.
  await call(`/people/${twin.person_id}/contacts`, {
    method: "POST", ...as(token),
    body: { kind: "phone", value: "+962 79 000 0043", is_primary: true,
            correlation_id: cid() },
  });
  const candidates = await call(`/people/${twin.person_id}/duplicates`, {
    method: "POST", ...as(token), body: { correlation_id: cid() },
  });

  const credentialValue = `CARD-${randomUUID().slice(0, 12).toUpperCase()}`;
  const credential = await call("/access/credentials", {
    method: "POST", ...as(token),
    body: {
      person_id: person.person_id, kind: "nfc_card", credential_value: credentialValue,
      correlation_id: cid(),
    },
  });
  // One presentation, so the decision log has a row. The policy requires an entitlement and
  // this member has none, so it is a *restricted* refusal -- which is the row worth having,
  // because it is the one the public/private split is about.
  const decision = await call("/access/decisions", {
    method: "POST", ...as(token),
    body: {
      point_id: point.point_id, credential_value: credentialValue,
      idempotency_key: randomUUID(), correlation_id: cid(),
    },
  });

  // **A second refusal that somebody has already answered by hand**, for FD-03.
  //
  // The denial screen has two states a reader acts on differently -- a refusal nobody has
  // answered, where the override is offered, and one where somebody already let them in, so
  // offering it again would admit the same person twice in the log. **A fixture with one of
  // them renders a branch and demonstrates nothing**, which is the vacuity this repository
  // has now shipped five times, so the twin carries the answered one and Jane's stays
  // unanswered.
  //
  // **The override is seeded rather than pressed in a browser.** It is one-way: the decision
  // log is insert-only and nothing withdraws an admission, so a spec that overrode once a run
  // would consume a state nobody can restore -- the budget shape this repository records four
  // times. `freeze.spec.ts` made the same call for the same reason: the write is the backend's
  // to prove, and what a browser proves is that a reader can reach the form.
  const twinCredentialValue = `CARD-${randomUUID().slice(0, 12).toUpperCase()}`;
  await call("/access/credentials", {
    method: "POST", ...as(token),
    body: {
      person_id: twin.person_id, kind: "nfc_card", credential_value: twinCredentialValue,
      correlation_id: cid(),
    },
  });
  const twinRefusal = await call("/access/decisions", {
    method: "POST", ...as(token),
    body: {
      point_id: point.point_id, credential_value: twinCredentialValue,
      idempotency_key: randomUUID(), correlation_id: cid(),
    },
  });
  await call("/access/decisions/override", {
    method: "POST", ...as(token),
    body: {
      point_id: point.point_id, person_id: twin.person_id, reason: "manager_approved",
      // The key the screen itself composes, so a fixture re-run against the same database
      // answers from the row rather than recording a second admission.
      idempotency_key: `override-${twinRefusal.decision_id}`, correlation_id: cid(),
    },
  });

  // **Door entries across the chart's own window**, which ADM-MEM-07 is made of.
  //
  // A member with no entries renders the tab as four empty states and twelve blank rows,
  // which demonstrates nothing: this repository's own rule is that a fixture carrying one of
  // a kind renders and shows nothing, and here it carries none. So the entries are spread --
  // a run of weeks with visits, then a gap, then one recent -- because **the gap is what the
  // chart is for**. The canvas's own reading of its chart is "three weeks at zero", which
  // only means something if some weeks are not.
  //
  // An entry is a recorded event rather than a decision. MOD-022 keeps the two apart on
  // purpose: a granted decision nobody walked through is not a visit.
  //
  // **The credential's own `issued_at` is `now()` and is not settable**, so on the Access tab
  // this card reads "Issued today · 14 uses · last used yesterday". That is an artefact of
  // seeding backwards, not of the screen: a real card is issued before it is used. Adding an
  // API field so a fixture could backdate it would be inventing surface for a seed, which is
  // the wrong trade.
  for (const daysBack of [1, 9, 12, 16, 19, 23, 26, 33, 37, 44, 51, 58, 65, 72]) {
    // Mid-morning on the club's *local* calendar day, `daysBack` days before the club's
    // local today -- see `clubLocalInstant`, and the comment there for the evening this
    // was found.
    const when = clubLocalInstant(daysBack, 10, 30);
    await call("/access/events", {
      method: "POST", ...as(token),
      body: {
        point_id: point.point_id, direction: "entry",
        credential_value: credentialValue, occurred_at: when.toISOString(),
        source: "online", idempotency_key: randomUUID(), correlation_id: cid(),
      },
    });
  }

  // **A day's shape, for ADM-RPT-04.** The entries above are one a day at mid-morning,
  // which draws a single bar: a chart with one bar demonstrates nothing, which is this
  // repository's own rule about a fixture carrying one of a kind. The report's whole output
  // is a busiest window, a quietest attended hour and three heat tiers, and none of those
  // exists until a day has a shape.
  //
  // So: an evening peak at 19:00 with 18:00 just inside the peak tier beside it, which is
  // what makes the busiest window span two hours and read "18:00-20:00" the way the canvas
  // draws it; 17:00 in the middle tier; and 07:00 quiet, which is the actionable hour the
  // canvas's own conclusion names. With the 07:30 UTC entries above landing at 10:30 local,
  // the finished chart is 19:00 at ten, 18:00 at nine, 10:00 at seven, 17:00 at six and
  // 07:00 at three -- a peak, a peak-tier neighbour, two busy hours and one quiet one.
  //
  // **The hours are local and the fixture writes UTC**, which is the whole point of the
  // read: Amman is UTC+3, so 19:00 local is 16:00Z. A seed that set local hours directly
  // would agree with a chart bucketed on the instant, which is the defect.
  //
  // **Every entry is two to five days back**, not spread over the window: they then age out
  // together rather than one hour at a time, so a fixture left sitting for three weeks
  // reports a smaller chart of the same shape instead of a different peak. That is the
  // "a test that asserts a freshness has to create it" rule applied to a window.
  const SHAPE_OF_A_DAY = [[19, 10], [18, 9], [17, 6], [7, 3]];
  for (const [localHour, howMany] of SHAPE_OF_A_DAY) {
    for (let i = 0; i < howMany; i += 1) {
      const when = clubLocalInstant(2 + (i % 4), localHour);
      await call("/access/events", {
        method: "POST", ...as(token),
        body: {
          point_id: point.point_id, direction: "entry",
          credential_value: credentialValue, occurred_at: when.toISOString(),
          source: "online", idempotency_key: randomUUID(), correlation_id: cid(),
        },
      });
    }
  }

  // ---------------------------------------------------------------- MOD-005, configuration
  //
  // **Two definitions and two flags, because the board is about telling answers apart.** One
  // key is published at the tenant scope and one is left alone, so a reader can see "nobody
  // set it" beside a value somebody chose; one flag is enabled with no rule, so it reads as
  // the default, and one has its kill switch engaged, which outranks every rule and is the
  // one state worth marking on a board.
  await call("/config/definitions", {
    method: "POST", ...as(token),
    body: { config_key: "booking.window_hours", value_type: "integer",
            default_value: 48, owner_module: "MOD-020", validation: { minimum: 1 },
            description: "How far ahead a member may book" },
  });
  await call("/config/definitions", {
    method: "POST", ...as(token),
    body: { config_key: "checkin.grace_minutes", value_type: "integer",
            default_value: 15, owner_module: "MOD-020", validation: { minimum: 0 },
            description: "How late a member may still check in" },
  });
  await call("/config/values", {
    method: "POST", ...as(token),
    body: { config_key: "booking.window_hours", value: 72, scope_type: "tenant",
            published_by: ownerIdentityId, correlation_id: cid() },
  });
  await call("/flags/booking.new_flow", {
    method: "PUT", ...as(token),
    body: { enabled: true, default_variant: "off", rules: [],
            description: "The rebuilt booking path" },
  });
  await call("/flags/kiosk.offline_mode", {
    method: "PUT", ...as(token),
    body: { enabled: true, default_variant: "on", rules: [],
            description: "Let a kiosk decide alone" },
  });
  await call("/flags/kiosk.offline_mode/kill-switch", {
    method: "POST", ...as(token),
    body: { engaged: true, reason: "a reader was granting on a stale snapshot" },
  });

  // ---------------------------------------------------------------- MOD-019, a schedule
  //
  // **A class is five rows before it is a class**: the service it is, the people and the room
  // it needs, the rota those people work, the rule that says when it recurs, and the
  // occurrences generated from that rule. The board is only worth looking at once all five
  // exist, which is why the fixture builds the whole chain rather than a session row.
  const serviceResource = await call("/scheduling/resources", {
    method: "POST", ...as(token),
    body: { resource_code: "YOGA-FLOW", resource_kind: "service",
            display_name: "Yoga flow", location_id: location.location_id,
            correlation_id: cid() },
  });
  const instructor = await call("/scheduling/resources", {
    method: "POST", ...as(token),
    body: { resource_code: "COACH-1", resource_kind: "staff",
            display_name: "Dana Coach", location_id: location.location_id,
            correlation_id: cid() },
  });
  const studio = await call("/scheduling/resources", {
    method: "POST", ...as(token),
    body: { resource_code: "STUDIO-A", resource_kind: "room",
            display_name: "Studio A", location_id: location.location_id,
            correlation_id: cid() },
  });
  // **A resource with no rota is unconstrained; one with a weekly rota is bound every day.**
  // So the instructor gets every weekday, which is what makes a generation over a week
  // succeed rather than fail on availability for six of seven days.
  for (let weekday = 0; weekday < 7; weekday += 1) {
    await call("/scheduling/availability", {
      method: "POST", ...as(token),
      body: { resource_id: instructor.resource_id, window_kind: "working",
              starts_at: "06:00", ends_at: "22:00", weekday, correlation_id: cid() },
    });
  }

  const today = new Date();
  const isoDay = (offset) =>
    new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate() + offset))
      .toISOString()
      .slice(0, 10);

  const template = await call("/scheduling/templates", {
    method: "POST", ...as(token),
    body: {
      template_code: "YOGA-EVE", display_name: "Evening yoga flow",
      service_resource_id: serviceResource.resource_id,
      location_id: location.location_id,
      rule: { frequency: "daily", local_time: "18:00", duration_minutes: 60,
              starts_on: isoDay(0), until: isoDay(6) },
      policy: { capacity: 12, setup_minutes: 10, cleanup_minutes: 10, waitlist_capacity: 4 },
      requirements: [
        { kind: "staff", quantity: 1, resource_id: instructor.resource_id },
        { kind: "room", quantity: 1, resource_id: studio.resource_id },
      ],
      restrictions: [{ kind: "min_age", value: "16" }],
      correlation_id: cid(),
    },
  });
  // **Drafting and publishing are two acts**, and a draft generates nothing: `publish` is what
  // makes the rule live, and `sessions` is what turns the live rule into occurrences.
  await call(`/scheduling/templates/${template.template_id}/publish`, {
    method: "POST", ...as(token),
    body: { effective_from: isoDay(0), correlation_id: cid() },
  });
  const generated = await call(`/scheduling/templates/${template.template_id}/sessions`, {
    method: "POST", ...as(token), body: { correlation_id: cid() },
  });

  // **ADM-SCH-04's own case, and the one thing that screen exists to show.** The canvas:
  // "Thursday afternoon is an exception -- he asked for it off three weeks ago. His 17:30
  // with Hala sits inside it, so the grid shows both and the booking is flagged rather than
  // silently honoured or silently dropped ... reducing availability never deletes a booking,
  // because the member on the other end has already been told a time."
  //
  // So the exception is written *after* the sessions, which is the realistic order: a class
  // is on the calendar and somebody then asks for the evening off. The rota above is
  // 06:00-22:00 every day and the class holds 17:50-19:10 with its margins, so a time-off
  // window over the evening makes that one session conflict and leaves the other six alone.
  // A fixture with no conflict renders the grid and demonstrates nothing -- "the fixture
  // carries both members of the pair the distinction is about".
  //
  // **The reason is deliberately private**, because it is the one free-text column in a rota
  // and the one place a health fact goes in practice. The spec reads it back as masked on a
  // session holding only the schedule read, and unmasked for one that could have written it.
  const rotaExceptionDay = isoDay(1);
  await call("/scheduling/availability", {
    method: "POST", ...as(token),
    body: { resource_id: instructor.resource_id, window_kind: "time_off",
            starts_at: "12:00", ends_at: "22:00", on_date: rotaExceptionDay,
            reason: "hospital appointment", correlation_id: cid() },
  });

  // **A class with no coach, which is ADM-CC-01's STAFFING item.** The template above names
  // a staff requirement and the queue is about the ones that do not -- so without this the
  // Command Center's busiest row is unreachable and every assertion about it passes
  // vacuously. A room and a service, no staff: MOD-019 publishes it happily, because a
  // session's requirements are what the author wrote and an unstaffed class is a real thing
  // a gym schedules before it knows who is teaching.
  // Its own room. The first attempt put it in the studio and MOD-019 refused the generation
  // with three double-booking conflicts -- correctly, since the yoga class holds that room
  // from 17:50 to 19:10 with its margins. A gym with a studio and a spin room is also the
  // ordinary arrangement, so the fixture matches it rather than moving the class.
  const spinRoom = await call("/scheduling/resources", {
    method: "POST", ...as(token),
    body: { resource_code: "ROOM-SPIN", resource_kind: "room",
            display_name: "Spin room", location_id: location.location_id,
            correlation_id: cid() },
  });
  const unstaffed = await call("/scheduling/templates", {
    method: "POST", ...as(token),
    body: {
      template_code: "SPIN-THU", display_name: "Spin",
      service_resource_id: serviceResource.resource_id,
      location_id: location.location_id,
      rule: { frequency: "daily", local_time: "19:00", duration_minutes: 45,
              starts_on: isoDay(1), until: isoDay(3) },
      policy: { capacity: 18, setup_minutes: 10, cleanup_minutes: 10 },
      requirements: [{ kind: "room", quantity: 1, resource_id: spinRoom.resource_id }],
      restrictions: [],
      correlation_id: cid(),
    },
  });
  await call(`/scheduling/templates/${unstaffed.template_id}/publish`, {
    method: "POST", ...as(token),
    body: { effective_from: isoDay(1), correlation_id: cid() },
  });
  await call(`/scheduling/templates/${unstaffed.template_id}/sessions`, {
    method: "POST", ...as(token), body: { correlation_id: cid() },
  });

  // **A substitution, so a session has a change with a reason on it.** Without one the
  // session page's `What changed` block is always the empty case, and the masked reason --
  // the control MOD-019's review added after a reviewer read a health fact out of that
  // column -- has nothing to mask. The reason here is deliberately ordinary prose: the point
  // is who may read it, not what it says.
  const standIn = await call("/scheduling/resources", {
    method: "POST", ...as(token),
    body: { resource_code: "COACH-2", resource_kind: "staff",
            display_name: "Sami Stand-in", location_id: location.location_id,
            correlation_id: cid() },
  });
  for (let weekday = 0; weekday < 7; weekday += 1) {
    await call("/scheduling/availability", {
      method: "POST", ...as(token),
      body: { resource_id: standIn.resource_id, window_kind: "working",
              starts_at: "06:00", ends_at: "22:00", weekday, correlation_id: cid() },
    });
  }
  // **And a staff resource with no rota at all, because the unconstrained branch needs one.**
  // The stand-in cannot be that case: a substitution is refused unless the replacement's rota
  // covers the class, so the loop above is what makes the line below succeed. Pointing the
  // "unconstrained" spec at the stand-in proved nothing -- it has a rota, so the branch that
  // says "no rota binds" and draws no grid had never rendered. This repository's own rule is
  // that the fixture carries both members of the pair the distinction is about, and this is the
  // member that was missing. A new hire with nothing written yet is also the realistic shape:
  // on the day a gym opens, nobody has a rota.
  const noRota = await call("/scheduling/resources", {
    method: "POST", ...as(token),
    body: { resource_code: "COACH-3", resource_kind: "staff",
            display_name: "Rami New-hire", location_id: location.location_id,
            correlation_id: cid() },
  });

  const substituted = generated.sessions?.[0]?.session_id ?? null;
  if (substituted !== null) {
    await call(`/scheduling/sessions/${substituted}/substitute`, {
      method: "POST", ...as(token),
      body: { replacement_resource_id: standIn.resource_id,
              reason: "the usual instructor is away", correlation_id: cid() },
    });
  }

  // ---------------------------------------------------------------- MOD-020, a booking
  //
  // **A booking needs a policy version, and the policy is what the booking snapshots.** What a
  // member owes for cancelling late is decided months later and has to be decided on the terms
  // they agreed to, so retiring a policy stops the next sale and changes nothing about the
  // last. One version here, so a roster has something on it.
  await call("/booking/policies", {
    method: "POST", ...as(token),
    body: { policy_key: "CLASSES", display_name: "Class bookings",
            cancellation_hours: 12, max_concurrent: 5, quota: 10,
            // **The widest grace the module allows, so the suite survives being re-run
            // hours later.** FD-06's check-in window opens an hour before a class and closes
            // `checkin_grace_minutes` after it starts, so the default fifteen gave the two
            // tests that press the button a 75-minute life from seeding -- green in CI, which
            // provisions immediately before the run, and red on a local re-run for a reason
            // that looks exactly like a product regression. It took two of them.
            //
            // Four hours is the constraint's own ceiling (`0 <= grace <= 240`), it is a
            // legitimate figure for a gym that lets people drift in, and it changes nothing
            // the tests are about: the window still refuses tomorrow's class, which is what
            // the sibling test asserts. **The freshness cannot be made by the spec** -- moving
            // a session is a stepped-up scheduling write and a browser session is AAL 1 --
            // so the fixture is the only place it can come from.
            checkin_grace_minutes: 240,
            quota_period: "rolling_7_days", correlation_id: cid() },
  });
  // **The second occurrence, not the first.** The rule starts today, so the first occurrence
  // is in the past for most of the day and MOD-020 refuses it with `window_closed` -- which is
  // the correct refusal and not one a fixture should be arguing with. Tomorrow's occurrence is
  // in the future whatever time this runs at.
  const bookable = generated.sessions?.[1]?.session_id ?? null;
  const booking = bookable === null ? null : await call(
    `/booking/sessions/${bookable}/bookings`,
    { method: "POST", ...as(token),
      body: { person_id: person.person_id, policy_key: "CLASSES",
              source_kind: "front_desk", idempotency_key: randomUUID(),
              correlation_id: cid() } },
  );

  // ------------------------------------------------- a class a desk can actually check into
  //
  // **FD-06's whole control needs a session whose check-in window is open now**, and the
  // booking above is on tomorrow's class deliberately. `may_check_in` opens the window an
  // hour before the session and closes it after the policy's grace, so a desk opening a
  // class twenty-two hours out is correctly refused -- which the screen now says rather than
  // offering a button that answers 409, and which means the button itself is never exercised
  // against that session. Without this seed the one write on the Front Desk surface is
  // unreachable from a browser.
  //
  // **Forty-five minutes out, in the location's own zone**, which is why the local time is
  // computed rather than typed: MOD-019 takes a local time and the site's zone and converts
  // each occurrence separately, so a UTC time here would be the wrong hour at the site and
  // the generated occurrence would land outside the window again.
  //
  // **Forty-five rather than thirty**, because the check-in window opens an hour before the
  // class: at forty-five minutes it is already open when the fixture finishes, and with the
  // grace above it stays open for nearly five hours. At thirty it was open too, and closed
  // seventy-five minutes later.
  const soon = new Date(Date.now() + 45 * 60_000);
  const localSoon = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Amman", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).format(soon);
  const localSoonDay = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Amman", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(soon);
  const imminent = await call("/scheduling/templates", {
    method: "POST", ...as(token),
    body: {
      template_code: `DESK-${Date.now()}`, display_name: "Spin",
      service_resource_id: serviceResource.resource_id,
      location_id: location.location_id,
      rule: { frequency: "daily", local_time: localSoon, duration_minutes: 45,
              starts_on: localSoonDay, until: localSoonDay },
      // **Room for repeated runs.** Checking somebody in is one-way, so every browser run
      // books a member of its own rather than spending the fixture's -- which is the only
      // way that test is re-runnable, and it means the class fills a little each time. The
      // canvas's own 18 is on the other class, where nothing is checked in.
      policy: { capacity: 60, setup_minutes: 0, cleanup_minutes: 0, waitlist_capacity: 3 },
      // **A room and no coach, deliberately.** The instructor's rota is 06:00-22:00 and this
      // occurrence is half an hour from whenever the fixture runs, so a staffed template is
      // refused outright in the small hours -- MOD-019 doing exactly what it should, and not
      // something a fixture should argue with. A room has no rota in any meaningful sense
      // ("a resource with no working hours is unconstrained"), so it binds at any hour. A
      // template needs at least one requirement, which is why this is a room rather than
      // nothing. A class with no coach is a state the schedule board already shows ("1
      // without a coach"); the coach, the studio name and the timezone are proved on the
      // other session, which has all three.
      requirements: [{ kind: "room", quantity: 1, resource_id: studio.resource_id }],
      correlation_id: cid(),
    },
  });
  await call(`/scheduling/templates/${imminent.template_id}/publish`, {
    method: "POST", ...as(token),
    body: { effective_from: localSoonDay, correlation_id: cid() },
  });
  const imminentSessions = await call(
    `/scheduling/templates/${imminent.template_id}/sessions`,
    { method: "POST", ...as(token), body: { correlation_id: cid() } });
  const deskSessionId = imminentSessions.sessions?.[0]?.session_id ?? null;
  if (deskSessionId !== null) {
    // **Ten members on this class, and the number is the point.** Checking somebody in is
    // one-way -- there is no un-check-in, correctly -- so every browser run spends one, and
    // a roster seeded with a single booking is green on a fresh fixture and red on the
    // second run. That is the budget-consuming shape this repository records three times
    // over, and the only way to see it is to run the suite twice.
    //
    // **The test cannot provision its own**, which is why this is seeded rather than left to
    // the spec: `people.person.write` is financial class, so a browser session at AAL 1 is
    // refused -- the same permission boundary that makes ADM-MEM-10's form offer a step-up.
    // Ten is eight runs of margin over the one the suite spends, and the class carries 60
    // places so they fit.
    for (let n = 0; n < 10; n += 1) {
      const member = await call("/people", {
        method: "POST", ...as(token),
        body: { legal_name: `Spin Member ${n + 1}`, profile_kinds: ["member"],
                date_of_birth: "1991-07-14", correlation_id: cid() },
      });
      await call(`/people/${member.person_id}/member-profile`, {
        method: "POST", ...as(token),
        body: { correlation_id: cid(), lifecycle_state: "active",
                member_number: `M-SPIN${String(n + 1).padStart(2, "0")}`,
                joined_on: "2025-06-03" },
      });
      await call(`/booking/sessions/${deskSessionId}/bookings`, {
        method: "POST", ...as(token),
        body: { person_id: member.person_id, policy_key: "CLASSES",
                source_kind: "front_desk", idempotency_key: randomUUID(),
                correlation_id: cid() },
      });
    }
  }

  // ------------------------------------------------------------- a third identity: the desk
  //
  // **Three identities, because two negative proofs need contradictory permission sets.** The
  // reader proves the navigation filter and the record refusal *by not holding*
  // `people.person.read`; the membership blocks' own gates can only be proved by a session
  // that holds it and holds none of MOD-017 -- otherwise the page's gate answers first and the
  // spec proves the wrong refusal, which is the "a probe answered by a sibling" trap one layer
  // up from the schema. One identity cannot be both, and the first attempt at this made the
  // reader hold it and broke two people specs, which is how the contradiction surfaced.
  const deskEmail = `desk+${Date.now()}@veyro.invalid`;
  const deskPassword = `e2e-${randomUUID()}`;
  await call("/identities", {
    method: "POST", tenant: tenantId,
    body: { display_name: "E2E Front Desk", correlation_id: cid(), email: deskEmail,
            password: deskPassword },
  });
  const deskSignIn = await call("/auth/login", {
    method: "POST", tenant: tenantId,
    body: { identifier: deskEmail, password: deskPassword, correlation_id: cid() },
  });
  const deskSession = await call("/auth/session", { ...as(deskSignIn.token) });
  const deskRole = await call("/authz/roles", {
    method: "POST", ...as(token),
    body: {
      role_key: `desk_${Date.now()}`, display_name: "Front desk",
      // A receptionist: may look somebody up, may see none of their money.
      permissions: ["people.person.read"],
      correlation_id: cid(),
    },
  });
  await call("/authz/assignments", {
    method: "POST", ...as(token),
    body: { identity_id: deskSession.identity_id, role_key: deskRole.role_key,
            correlation_id: cid() },
  });
  // Its browser device, like the other two: the label is per identity, so this is a third
  // device to MOD-007 and an unconfirmed one would be challenged on every sign-in.
  await confirmWebDevice(
    tenantId, deskSession.identity_id, deskSignIn.token, deskEmail, deskPassword);

  // ------------------------------------------------ a second identity: a person can type it
  //
  // **Nothing in the suite uses this one.** It exists because every other credential here is
  // a UUID in a file -- the owner's email carries a timestamp and its password is
  // `e2e-<uuid>` -- which is right for a test and unusable for a person who wants to open the
  // product and look at it. A fixed email and a typeable password cost nothing in a tenant
  // that is synthetic, local and thrown away on the next run, and they are what make the
  // surface reviewable by hand rather than only by Playwright.
  //
  // **The order is the whole trick.** A brand-new identity holds no second factor, so
  // `_authenticate_in_tx` skips the risk challenge as unanswerable and confirms the device on
  // the strength of that login -- so signing in once with this app's own fingerprint *before*
  // any recovery code exists is what stops the web form asking for one afterwards. Issuing
  // the codes second gives it a step-up without taking that away.
  const EASY_EMAIL = "admin@veyro.invalid";
  const EASY_PASSWORD = "veyro-local-1";
  const easy = await call("/identities", {
    method: "POST", tenant: tenantId,
    body: { display_name: "Local Admin", correlation_id: cid(), email: EASY_EMAIL,
            password: EASY_PASSWORD },
  });
  const easyFirst = await call("/auth/login", {
    method: "POST", tenant: tenantId,
    body: { identifier: EASY_EMAIL, password: EASY_PASSWORD, correlation_id: cid(),
            device_fingerprint: browserFingerprint(tenantId, EASY_EMAIL),
            device_label: "Veyro web" },
  });
  if (easyFirst.challenge) {
    throw new Error(
      "the local admin's first login was challenged, which means a second factor existed "
      + "before the device was confirmed -- the order in this block is what prevents that",
    );
  }
  // The bootstrap's role, so this identity sees what the owner sees. `assign_role` refuses to
  // grant what the grantor does not hold, and the owner holds everything.
  // The bootstrap's role key is read back from the owner's own assignment rather than passed
  // in: `provision` holds it and this function does not, and a hard-coded "tenant_admin"
  // would be a second spelling of something the server already knows.
  const ownerRoles = await call(
    `/authz/assignments/${ownerIdentityId}?correlation_id=${cid()}`, as(token));
  const ownerRole = ownerRoles[0]?.role_key;
  if (!ownerRole) throw new Error("the owner holds no role, so there is nothing to grant");
  await call("/authz/assignments", {
    method: "POST", ...as(token),
    body: { identity_id: easy.identity_id, role_key: ownerRole, correlation_id: cid() },
  });
  const easyCodes = await call(`/identities/${easy.identity_id}/recovery-codes`, {
    method: "POST", tenant: tenantId, token: easyFirst.token,
    body: { correlation_id: cid(), current_password: EASY_PASSWORD },
  });

  // ---------------------------------------------------------------- MOD-017, a membership
  //
  // The member's agreement, what it entitles them to, and one invoice that has been paid.
  // Three blocks on the member's page read this, each through its own gate, so the fixture
  // has to carry all three -- a page with an empty entitlement table cannot show the
  // difference between "nothing granted" and "you may not see it".
  // **A second organization, deliberately without one.** The legal entity below makes the
  // first organization billable, which is what MOD-017 needs -- and it took away the empty
  // state the organization board's own disclosure exists for ("no legal entity yet, so this
  // organization cannot be invoiced"). Keeping both means both are rendered and both are
  // proved. Found by the organization spec failing the moment MOD-017 was seeded.
  await call("/organizations", {
    method: "POST", ...as(token),
    body: { legal_name: "Veyro Holdings Ltd", country_code: "JO", correlation_id: cid() },
  });
  const entity = await call("/legal-entities", {
    method: "POST", ...as(token),
    body: { organization_id: org.organization_id, registered_name: "Veyro Sites Ltd",
            tax_number: "JO-5550001", correlation_id: cid() },
  });
  // A membership is sold against a catalogue variant with a live price, and `create_agreement`
  // takes its figures from the price resolution rather than from the caller -- a reviewer
  // found an agreement citing a receipt for 45.00 and recording 4.50.
  const product = await call("/catalog/products", {
    method: "POST", ...as(token),
    body: {
      product_key: `gold${Date.now().toString(36)}`, product_type: "membership",
      texts: [{ locale: "en", display_name: "Gold membership" }],
      variants: [{ variant_key: "monthly", display_name: "Monthly", term_days: 30 }],
      correlation_id: cid(),
    },
  });
  const priceBook = await call("/catalog/price-books", {
    method: "POST", ...as(token),
    body: { price_book_key: `std${Date.now().toString(36)}`, display_name: "Standard",
            currency: "JOD", effective_from: "2026-01-01T00:00:00+00:00",
            correlation_id: cid() },
  });
  await call(`/catalog/price-books/${priceBook.price_book_id}/activate`, {
    method: "POST", ...as(token), body: { correlation_id: cid() },
  });
  await call("/catalog/prices", {
    method: "POST", ...as(token),
    body: { price_book_id: priceBook.price_book_id,
            variant_id: product.variants[0].variant_id, amount_minor: 45000,
            effective_from: "2026-01-01T00:00:00+00:00", correlation_id: cid() },
  });
  await call(`/catalog/products/${product.product_id}/publish`, {
    method: "POST", ...as(token), body: { expected_version: 1, correlation_id: cid() },
  });

  // **Two promotions, one live and one that ended while still reading as active.** Nothing
  // retires a promotion when its window closes -- the resolver reads the window -- so
  // `status: active` on a campaign that finished in February is the ordinary state of this
  // table, and a board showing the status alone says a campaign is running when it is not.
  // One of each is the only way that distinction is on the screen rather than in a comment.
  for (const [key, name, from, to] of [
    [`live${Date.now().toString(36)}`, "January sale", "2026-01-01T00:00:00+00:00", null],
    [`past${Date.now().toString(36)}`, "New year offer", "2026-01-01T00:00:00+00:00",
     "2026-02-01T00:00:00+00:00"],
  ]) {
    const promo = await call("/catalog/promotions", {
      method: "POST", ...as(token),
      body: { promotion_key: key, display_name: name, promotion_kind: "automatic",
              percent_bp: 1000, effective_from: from,
              ...(to === null ? {} : { effective_to: to }),
              correlation_id: cid() },
    });
    await call(`/catalog/promotions/${promo.promotion_id}/activate`, {
      method: "POST", ...as(token), body: { correlation_id: cid() },
    });
  }

  const contractKey = `terms${Date.now().toString(36)}`;
  const version = await call("/memberships/contract-versions", {
    method: "POST", ...as(token),
    // **Thirty freeze days a year**, because the default is nought and a contract that
    // allows no freezing makes ADM-MSH-03 undemonstrable: the panel reads "0 of 0", the
    // form never renders, and the screen's whole subject -- what a freeze costs against an
    // allowance -- has nothing to show. Thirty is the ordinary commercial term and is what
    // the canvas's "2 of 3 freeze months" implies.
    body: { contract_key: contractKey, body: "Standard membership terms.",
            freeze_days_per_year: 30, correlation_id: cid() },
  });
  // Published by the *second* identity. See the role above.
  await call(`/memberships/contract-versions/${version.contract_version_id}/publish`, {
    method: "POST", ...as(publisherToken), body: { correlation_id: cid() },
  });
  const terms = await call("/memberships/terms", {
    method: "POST", ...as(token),
    body: { product_id: product.product_id, contract_key: contractKey,
            membership_kind: "recurring", billing_period: "monthly",
            correlation_id: cid() },
  });
  // **Ninety days ago.** A freeze has to start inside the contract year it is decided in, and
  // a membership starting today leaves no room for the lifecycle history this page renders.
  const startedOn = new Date(Date.now() - 90 * 86400000).toISOString().slice(0, 10);
  const agreement = await call("/memberships/agreements", {
    method: "POST", ...as(token),
    body: { person_id: person.person_id, membership_terms_id: terms.membership_terms_id,
            variant_id: product.variants[0].variant_id, amount_minor: 45000,
            currency: "JOD", starts_on: startedOn, correlation_id: cid() },
  });
  await call(`/memberships/agreements/${agreement.agreement_id}/sign`, {
    method: "POST", ...as(token),
    body: { signature_kind: "click_through",
            signature_evidence_ref: `s3://signatures/${agreement.agreement_id}`,
            signed_by_person_id: person.person_id, correlation_id: cid() },
  });
  const membership = await call("/memberships", {
    method: "POST", ...as(token),
    body: { agreement_id: agreement.agreement_id, // **Deliberately not "M-00042".** MOD-014's member profile carries that one, and the
            // two are different human-facing numbers owned by different modules with nothing
            // relating them -- a fixture that gave both the same value would hide the fact.
            membership_number: "GOLD-00042",
            idempotency_key: randomUUID(), correlation_id: cid() },
  });

  // **ADM-MSH-07's other three commitments, and seeding them is what found the defect.**
  // `commitmentLine` says one of four sentences and this fixture produced exactly one of
  // them -- the rolling member above, who has no commitment at all. So three of the four
  // branches had never rendered in a browser, the two-fee-line block had never rendered at
  // all (it is gated on `lines.length > 1`), and `beforeYouCancel` had never rendered
  // either, because the member above last visited yesterday and is therefore not dormant.
  //
  // Building them is how the dead branch surfaced: `held_to_term` was unreachable, and the
  // member it describes was being told their commitment "has been served" nine months
  // early. A hand-written unit fixture had proved that branch with a quote the server
  // cannot emit. **Only a real membership, priced by the real lifecycle, could say so.**
  //
  // The figures are the canvas's own -- JOD 40.00 a month and a two-month buy-out, which is
  // its "two-month fee of JOD 80.00" exactly -- so a screen can be put beside its drawing
  // and the comparison is arithmetic rather than judgement.
  const commitments = {};
  for (const [label, months, buyOut, who] of [
    // The canvas's member: inside a twelve-month term, and the contract sells the way out.
    // Renders `termEarly`, both fee lines, and the committed freeze offer.
    ["buyOut", 12, 2, "Tareq Odeh"],
    // The same term with no buy-out: access runs to the term rather than to notice. This is
    // the state every contract in this build was in until the buy-out existed, and it is the
    // one that was rendering the wrong sentence.
    ["heldToTerm", 12, null, "Nadia Haddad"],
    // A term that has run out. The one member for whom "has been served" is true.
    ["served", 1, null, "Faris Qasem"],
  ]) {
    const key = `${label.toLowerCase()}${Date.now().toString(36)}`;
    const draft = await call("/memberships/contract-versions", {
      method: "POST", ...as(token),
      body: { contract_key: key, body: `Terms: ${label}.`,
              minimum_term_months: months, notice_days: 30,
              cancellation_mode: "end_of_notice", freeze_days_per_year: 30,
              // **Omitted, not zero.** `null` holds the member to the term and `0` lets them
              // leave free -- the whole reason the column is nullable, and a fixture that
              // sent 0 here would seed the wrong one of three states.
              ...(buyOut === null ? {} : { early_termination_months: buyOut }),
              correlation_id: cid() },
    });
    // Published by the second identity, because an author cannot publish their own.
    await call(`/memberships/contract-versions/${draft.contract_version_id}/publish`, {
      method: "POST", ...as(publisherToken), body: { correlation_id: cid() },
    });
    // **A product each, because `mem_membership_terms` admits one set per product** -- which
    // the seed found by being refused 409 rather than by anybody reading the migration. It
    // is also the truer shape: a twelve-month contract that sells an exit, one that does
    // not, and a one-month rolling one are three different things a gym sells, not three
    // contracts on one product.
    const theirProduct = await call("/catalog/products", {
      method: "POST", ...as(token),
      body: { product_key: `${key}p`, product_type: "membership",
              texts: [{ locale: "en", display_name: `${who}'s plan` }],
              variants: [{ variant_key: "monthly", display_name: "Monthly",
                           term_days: 30 }],
              correlation_id: cid() },
    });
    await call("/catalog/prices", {
      method: "POST", ...as(token),
      body: { price_book_id: priceBook.price_book_id,
              variant_id: theirProduct.variants[0].variant_id, amount_minor: 40000,
              effective_from: "2026-01-01T00:00:00+00:00", correlation_id: cid() },
    });
    await call(`/catalog/products/${theirProduct.product_id}/publish`, {
      method: "POST", ...as(token),
      body: { expected_version: 1, correlation_id: cid() },
    });
    const committedTerms = await call("/memberships/terms", {
      method: "POST", ...as(token),
      body: { product_id: theirProduct.product_id, contract_key: key,
              membership_kind: "recurring", billing_period: "monthly",
              correlation_id: cid() },
    });
    const member = await call("/people", {
      method: "POST", ...as(token),
      body: { legal_name: who, date_of_birth: "1990-03-14", correlation_id: cid() },
    });
    const theirAgreement = await call("/memberships/agreements", {
      method: "POST", ...as(token),
      body: { person_id: member.person_id,
              membership_terms_id: committedTerms.membership_terms_id,
              variant_id: theirProduct.variants[0].variant_id,
              // JOD 40.00 a month, so the two-month buy-out is the canvas's JOD 80.00.
              amount_minor: 40000, currency: "JOD", starts_on: startedOn,
              correlation_id: cid() },
    });
    await call(`/memberships/agreements/${theirAgreement.agreement_id}/sign`, {
      method: "POST", ...as(token),
      body: { signature_kind: "click_through",
              signature_evidence_ref: `s3://signatures/${theirAgreement.agreement_id}`,
              signed_by_person_id: member.person_id, correlation_id: cid() },
    });
    await call("/memberships", {
      method: "POST", ...as(token),
      body: { agreement_id: theirAgreement.agreement_id,
              membership_number: `${label.slice(0, 4).toUpperCase()}-00001`,
              idempotency_key: randomUUID(), correlation_id: cid() },
    });
    commitments[label] = member.person_id;
  }

  const entitlementPolicy = await call("/member-entitlements/policies", {
    method: "POST", ...as(token),
    body: { policy_key: "classes", display_name: "Group classes",
            entitlement_type: "class_credit", correlation_id: cid() },
  });
  await call("/member-entitlements/grants", {
    method: "POST", ...as(token),
    body: { person_id: person.person_id, policy_id: entitlementPolicy.policy_id,
            membership_id: membership.membership_id, source_kind: "membership",
            valid_from: "2026-01-01T00:00:00+00:00", quantity: 10,
            reason: "ten classes with the membership", correlation_id: cid() },
  });

  // **A ledger chart, before the invoice.** MOD-018's bridge runs inside MOD-017's own
  // transaction, so an invoice issued with no chart is posted nowhere -- `post_invoice`
  // returns `ledger_skipped_because` rather than refusing, precisely so a tenant mid-setup
  // does not find its till has stopped working. Seeding the chart first is what makes the
  // finance board show a trial balance with something on it rather than that honest skip.
  const chart = {};
  for (const [code, kind] of [
    ["AR", "receivable"], ["BANK", "bank"], ["CASH", "cash"],
    ["CLEARING", "provider_clearing"], ["CONTRA", "contra_revenue"],
    ["FEE", "provider_fee"], ["REV", "revenue"], ["SUSPENSE", "suspense"],
    ["TAX", "tax_payable"], ["UNEARNED", "unearned_revenue"],
    ["WCASH", "wallet_cash"], ["WPROMO", "wallet_promotional"],
  ]) {
    const account = await call("/ledger/accounts", {
      method: "POST", ...as(token),
      body: { account_code: code, account_kind: kind, display_name: code,
              currency: "JOD", correlation_id: cid() },
    });
    chart[code] = account.account_id;
  }
  // One retired account, so the chart has both states and a board cannot pass by showing
  // only the happy one.
  const retiring = await call("/ledger/accounts", {
    method: "POST", ...as(token),
    body: { account_code: "REV-OLD", account_kind: "revenue",
            display_name: "Revenue (merged)", currency: "JOD", correlation_id: cid() },
  });
  await call(`/ledger/accounts/${retiring.account_id}/retire`, {
    method: "POST", ...as(token),
    body: { reason: "merged into REV", correlation_id: cid() },
  });

  // **An open drawer and a closed one, because ADM-PAY-09 is about the pair.** A screen
  // with only an open till cannot show what a closed one reads like, and a screen with only
  // a closed one has nothing to count -- this repository's own rule that the fixture carries
  // both members of the distinction the surface is about. The closed one is short on
  // purpose: the variance posts to suspense, opens a case and carries the sentence the
  // module requires, which is the whole of COM-04-R05's discrepancy workflow in one row.
  const tillAccount = await call("/ledger/accounts", {
    method: "POST", ...as(token),
    body: { account_code: "TILL-FRONT", account_kind: "cash", display_name: "Front till",
            currency: "JOD", correlation_id: cid() },
  });
  const safeAccount = await call("/ledger/accounts", {
    method: "POST", ...as(token),
    body: { account_code: "SAFE", account_kind: "cash", display_name: "Safe",
            currency: "JOD", correlation_id: cid() },
  });
  const openDrawer = await call("/ledger/cash-sessions", {
    method: "POST", ...as(token),
    body: { location_id: location.location_id, cash_account_id: tillAccount.account_id,
            drawer_label: "Front desk", currency: "JOD", opening_float_minor: 50_000,
            float_source_account_id: safeAccount.account_id,
            legal_entity_id: entity.legal_entity_id,
            idempotency_key: `till-open-${cid()}`, correlation_id: cid() },
  });
  // Two sales in and one refund out, so the breakdown has all three lines and the expected
  // figure is a sum a reader can check rather than just the float.
  for (const [amount, what] of [[60_000, "a day pass"], [36_000, "a protein shake"]]) {
    await call("/ledger/journals", {
      method: "POST", ...as(token),
      body: { legal_entity_id: entity.legal_entity_id, currency: "JOD",
              posted_on: isoDay(0), source_kind: "manual", source_ref: what,
              description: what, idempotency_key: `till-in-${cid()}`,
              lines: [{ account_id: tillAccount.account_id, amount_minor: amount },
                      { account_id: chart.REV, amount_minor: -amount }],
              correlation_id: cid() },
    });
  }
  await call("/ledger/journals", {
    method: "POST", ...as(token),
    body: { legal_entity_id: entity.legal_entity_id, currency: "JOD",
            posted_on: isoDay(0), source_kind: "manual", source_ref: "change given back",
            description: "change given back", idempotency_key: `till-out-${cid()}`,
            lines: [{ account_id: tillAccount.account_id, amount_minor: -8_000 },
                    { account_id: chart.REV, amount_minor: 8_000 }],
            correlation_id: cid() },
  });

  // **A third till the browser suite closes and re-opens on every run.** Creating a ledger
  // account is a stepped-up financial write and a browser session is AAL 1, so a spec
  // cannot make its own -- but opening a session on one is routine, which is the whole
  // reason ADM-PAY-09 is buildable. The account is seeded here and the spec provisions the
  // *session*, which is what makes it idempotent across runs: a close is one-way, so a test
  // that closed the fixture's own drawer would pass once and fail ever after.
  const e2eTill = await call("/ledger/accounts", {
    method: "POST", ...as(token),
    body: { account_code: "TILL-E2E", account_kind: "cash", display_name: "Suite till",
            currency: "JOD", correlation_id: cid() },
  });

  const secondTill = await call("/ledger/accounts", {
    method: "POST", ...as(token),
    body: { account_code: "TILL-SHOP", account_kind: "cash", display_name: "Shop till",
            currency: "JOD", correlation_id: cid() },
  });
  const closedDrawer = await call("/ledger/cash-sessions", {
    method: "POST", ...as(token),
    body: { location_id: location.location_id, cash_account_id: secondTill.account_id,
            drawer_label: "Shop", currency: "JOD", opening_float_minor: 20_000,
            float_source_account_id: safeAccount.account_id,
            legal_entity_id: entity.legal_entity_id,
            idempotency_key: `till-shop-${cid()}`, correlation_id: cid() },
  });
  await call(`/ledger/cash-sessions/${closedDrawer.session_id}/close`, {
    method: "POST", ...as(token),
    body: { counted_minor: 17_500, legal_entity_id: entity.legal_entity_id,
            suspense_account_id: chart.SUSPENSE,
            variance_reason: "a member was given change twice", correlation_id: cid() },
  });

  const account = await call("/finance/accounts", {
    method: "POST", ...as(token),
    body: { payer_person_id: person.person_id, account_number: "A-00042",
            currency: "JOD", legal_entity_id: entity.legal_entity_id,
            correlation_id: cid() },
  });
  const series = await call("/finance/fiscal-series", {
    method: "POST", ...as(token),
    body: { legal_entity_id: entity.legal_entity_id, series_code: "INV",
            correlation_id: cid() },
  });
  const invoice = await call("/finance/invoices", {
    method: "POST", ...as(token),
    body: {
      billing_account_id: account.billing_account_id, series_id: series.series_id,
      lines: [{ description: "Gold membership, monthly", quantity: 1,
                unit_net_minor: 45000, tax_rate_bp: 1600 }],
      // **Fourteen days, not the issue date.** Both were `startedOn` at first, which rendered
      // a due date identical to the issue date right beneath it -- a payment term of zero,
      // which is a real `payment_terms_days` value and not the one anybody means.
      issued_on: startedOn,
      due_on: new Date(Date.parse(startedOn) + 14 * 86400000).toISOString().slice(0, 10),
      jurisdiction: "JO",
      // **The membership this billed for**, which ADM-PAY-10 needs: a chargeback against
      // this payment is answered with the signed agreement, and the dispute read finds it
      // through the invoice rather than by looking the payer up. Without it the evidence
      // list renders "the invoice cites no membership", which is true and is not the case
      // the canvas specifies.
      membership_id: membership.membership_id,
      idempotency_key: randomUUID(), correlation_id: cid(),
    },
  });
  // Paid in full, so the board has a settled document beside the outstanding figure. An
  // invoice nobody paid would make the "outstanding" cell the only interesting one.
  const intent = await call("/finance/payment-intents", {
    method: "POST", ...as(token),
    body: { billing_account_id: account.billing_account_id,
            invoice_id: invoice.invoice_id, amount_minor: invoice.gross_minor,
            method: "card", provider_key: "acme.payments",
            idempotency_key: randomUUID(), correlation_id: cid() },
  });
  const settled = await call(`/finance/payment-intents/${intent.intent_id}/settle`, {
    method: "POST", ...as(token),
    body: { outcome: "succeeded", correlation_id: cid() },
  });

  // ------------------------------------------------- ADM-CC-01's attention queue
  //
  // **The Command Center's quiet day and its busy morning are both real states, and a
  // fixture with only one of them demonstrates nothing.** This repository already records
  // that rule four times over -- a `closing` period beside an open one, an expired
  // promotion beside a live one, a released legal hold beside a preserving one -- and the
  // queue is the case where it matters most, because the design's own canvas 4 says an
  // empty queue "is the goal, not a gap". With nothing seeded the page renders the quiet
  // day and every assertion about a row passes vacuously.
  //
  // So: a second invoice that is overdue and in recovery (MONEY), a second membership
  // expiring inside the week (RETENTION), and a class with no coach (STAFFING). Each goes
  // through the product's own routes.
  const overdueOn = new Date(Date.now() - 45 * 86400000).toISOString().slice(0, 10);
  const inRecovery = await call("/finance/invoices", {
    method: "POST", ...as(token),
    body: {
      billing_account_id: account.billing_account_id, series_id: series.series_id,
      lines: [{ description: "Personal training, ten sessions", quantity: 1,
                unit_net_minor: 26000, tax_rate_bp: 1600 }],
      issued_on: overdueOn,
      due_on: new Date(Date.parse(overdueOn) + 14 * 86400000).toISOString().slice(0, 10),
      jurisdiction: "JO", idempotency_key: randomUUID(), correlation_id: cid(),
    },
  });
  await call("/finance/dunning-cases", {
    method: "POST", ...as(token),
    body: { invoice_id: inRecovery.invoice_id, idempotency_key: randomUUID(),
            correlation_id: cid() },
  });

  // ------------------------------------------------- ADM-PAY-01's four kinds
  //
  // **A ledger with one settled payment on it demonstrates nothing.** The screen's whole
  // argument is that a refund is a negative number on the same axis as a payment and never
  // a payment of a different colour, and that a failed charge is a row rather than an
  // absence -- neither of which a board can show without one of each. This repository
  // records the rule five times over now: the fixture carries both members of the pair the
  // distinction is about.
  //
  // A charge that failed, which is the canvas's "6 failed" and the commonest row somebody
  // has to act on.
  const failedIntent = await call("/finance/payment-intents", {
    method: "POST", ...as(token),
    body: { billing_account_id: account.billing_account_id,
            invoice_id: inRecovery.invoice_id, amount_minor: inRecovery.gross_minor,
            method: "card", provider_key: "acme.payments",
            idempotency_key: randomUUID(), correlation_id: cid() },
  });
  await call(`/finance/payment-intents/${failedIntent.intent_id}/settle`, {
    method: "POST", ...as(token),
    body: { outcome: "failed", failure_code: "card_expired", correlation_id: cid() },
  });

  // A refund, which needs two people by constraint: the owner records the request from
  // their own session and the publisher decides it. `approved_by <> requested_by` compares
  // two identities the server derived, so this cannot be written with one token.
  const refundRequest = await call("/finance/refund-requests", {
    method: "POST", ...as(token),
    body: { payment_id: settled.payment_id, amount_minor: 1000,
            reason: "Charged after she froze on the 28th", correlation_id: cid() },
  });
  await call("/finance/refunds", {
    method: "POST", ...as(publisherToken),
    body: { request_id: refundRequest.request_id,
            approval_reason: "Agreed: the charge should not have run",
            acknowledged_amount_minor: 1000,
            idempotency_key: randomUUID(), correlation_id: cid() },
  });

  // And a dispute the scheme opened, which is recorded rather than performed -- nothing
  // here speaks to a card scheme, so the row is a named actor's statement that a case
  // exists, carrying the scheme's own reference.
  await call("/finance/disputes", {
    method: "POST", ...as(token),
    body: { payment_id: settled.payment_id, provider_case_ref: "ACME-CASE-40118",
            dispute_kind: "chargeback", reason_code: "product_not_received",
            // **Ten days, which is ADM-PAY-10's unhurried branch.** The urgent one is
            // seeded below: the deadline box has two states and the canvas only draws the
            // red one, so a fixture with a single dispute renders one branch and leaves
            // the other proved by nothing -- the surface-branch vacuity this repository
            // has shipped four times.
            amount_minor: 2000, currency: invoice.currency,
            opened_on: isoDay(-2), respond_due_on: isoDay(10),
            idempotency_key: randomUUID(), correlation_id: cid() },
  });
  // The canvas's own case: "Evidence due 26 August · 7 days", in the error ink, with
  // "missing the deadline forfeits the amount automatically" under it. A scheme gives
  // whatever window it gives, so a second dispute against the same payment with a nearer
  // deadline is the ordinary way two of these sit on one board.
  await call("/finance/disputes", {
    method: "POST", ...as(token),
    body: { payment_id: settled.payment_id, provider_case_ref: "ACME-CASE-40119",
            dispute_kind: "chargeback", reason_code: "fraudulent",
            amount_minor: 1500, currency: invoice.currency,
            opened_on: isoDay(-30), respond_due_on: isoDay(4),
            idempotency_key: randomUUID(), correlation_id: cid() },
  });

  // **A wallet with both kinds in it**, which is ADM-PAY-07 and the one distinction MOD-018
  // calls a Critical Control: "a member holding 50.00 they paid in and 10.00 the tenant gave
  // away holds two different things, and the first is money the tenant owes." A fixture with
  // only a top-up renders a balance and demonstrates nothing about that, so it seeds a cash
  // top-up, a promotional credit that expires, and a spend -- which `plan_debit` takes from
  // the promotional side first, in the member's interest, because that is the kind that is
  // worth nothing lapsed.
  //
  // The counterparts are the chart's own: cash came in at the till, and value given away is
  // `contra_revenue`, which that kind's own description calls "revenue given back: a
  // discount, a credit note or a goodwill reduction".
  await call("/ledger/wallet-credits", {
    method: "POST", ...as(token),
    body: { person_id: person.person_id, value_kind: "cash", amount_minor: 10000,
            currency: "JOD", legal_entity_id: entity.legal_entity_id,
            counterpart_account_id: chart.CASH, source_kind: "purchase",
            source_ref: "desk-topup-1", reason: "Top-up at the desk",
            idempotency_key: randomUUID(), correlation_id: cid() },
  });
  await call("/ledger/wallet-credits", {
    method: "POST", ...as(token),
    body: { person_id: person.person_id, value_kind: "promotional", amount_minor: 800,
            currency: "JOD", legal_entity_id: entity.legal_entity_id,
            counterpart_account_id: chart.CONTRA, source_kind: "goodwill",
            source_ref: "class-cancelled-1",
            reason: "Class cancelled \u00b7 Tuesday spin",
            // **Expiring, because that is what makes the two kinds behave differently.**
            // A promotional credit nobody spends is worth nothing after this date, and the
            // statement marks it lapsed rather than dropping it: "where did my 10.00 go" is
            // the question a member actually asks.
            expires_on: isoDay(45),
            idempotency_key: randomUUID(), correlation_id: cid() },
  });
  await call("/ledger/wallet-debits", {
    method: "POST", ...as(token),
    body: { person_id: person.person_id, amount_minor: 250, currency: "JOD",
            legal_entity_id: entity.legal_entity_id,
            // A debit's own vocabulary is `spend | refund | expiry | correction`, not the
            // credit's: what value came *from* and what it went *to* are different questions.
            counterpart_account_id: chart.REV, source_kind: "spend",
            source_ref: "desk-sale-1", reason: "Water and a protein bar",
            idempotency_key: randomUUID(), correlation_id: cid() },
  });

  // **An invoice issued inside the current month, citing the catalogue variant it sold.**
  //
  // Two reasons, and both were found by opening ADM-RPT-02 and looking at it. The revenue
  // report reads month to date, and the two invoices above are back-dated 90 and 45 days --
  // so every figure on that screen was JOD 0.00 and the page could not be seen working at
  // all. And BY SOURCE splits revenue by the product type behind each line, which it reaches
  // through `variant_id`: a line with none is attributed to nothing and lands in the
  // "raised by hand" row. With only hand-written lines seeded, the one column that makes
  // that report a report had exactly one value, and a test asserting the split would have
  // been asserting the fallback.
  //
  // So: a line that cites the Gold membership variant, and a second with no variant at all,
  // which is the pair the distinction is about. This repository's own rule, from the
  // mutation sweeps: a fixture carrying one of a kind renders and demonstrates nothing.
  const thisMonth = await call("/finance/invoices", {
    method: "POST", ...as(token),
    body: {
      billing_account_id: account.billing_account_id, series_id: series.series_id,
      lines: [
        { description: "Gold membership, monthly", quantity: 1,
          unit_net_minor: 45000, tax_rate_bp: 1600,
          variant_id: product.variants[0].variant_id },
        { description: "Joining fee", quantity: 1, unit_net_minor: 1500, tax_rate_bp: 1600 },
      ],
      issued_on: isoDay(0),
      due_on: isoDay(14),
      jurisdiction: "JO",
      idempotency_key: randomUUID(), correlation_id: cid(),
    },
  });
  // Part paid, so OUTSTANDING carries a figure beside COLLECTED rather than a zero. An
  // invoice paid in full would make three of the report's four cells agree, which is the
  // one arrangement that cannot show they are four different facts.
  const monthIntent = await call("/finance/payment-intents", {
    method: "POST", ...as(token),
    body: { billing_account_id: account.billing_account_id,
            invoice_id: thisMonth.invoice_id, amount_minor: 20000,
            method: "card", provider_key: "acme.payments",
            idempotency_key: randomUUID(), correlation_id: cid() },
  });
  await call(`/finance/payment-intents/${monthIntent.intent_id}/settle`, {
    method: "POST", ...as(token),
    body: { outcome: "succeeded", correlation_id: cid() },
  });

  // **One invoice the tax authority rejected**, which is ADM-CC-01's COMPLIANCE row. The
  // fiscal state and the payment state move independently -- the migration says so at
  // length -- so this one is *paid* and unfiled, which is exactly the case the design's own
  // copy describes: "The sales are recorded and the money is collected -- only the e-invoice
  // submission failed." `pending -> submitted -> rejected` is the path; the machine has no
  // edge straight from `pending`, because nothing can be rejected before it is filed.
  await call(`/finance/invoices/${invoice.invoice_id}/fiscalize`, {
    method: "POST", ...as(token),
    body: { target: "submitted", correlation_id: cid() },
  });
  await call(`/finance/invoices/${invoice.invoice_id}/fiscalize`, {
    method: "POST", ...as(token),
    body: { target: "rejected", correlation_id: cid() },
  });

  // **A membership whose first monthly period ends inside the seven-day window**, which is
  // the window ADM-CC-01 states -- "14 memberships expire within 7 days". Starting today put
  // the period end a month out and the RETENTION row never appeared, so the start is
  // twenty-five days back: the first monthly period then ends in about five days, inside the
  // default window, and the row is reachable. Found by looking at the rendered queue.
  const secondPerson = await call("/people", {
    method: "POST", ...as(token),
    body: { legal_name: "Yousef Haddad", profile_kinds: ["member"], correlation_id: cid() },
  });
  const expiringAgreement = await call("/memberships/agreements", {
    method: "POST", ...as(token),
    body: { person_id: secondPerson.person_id,
            membership_terms_id: terms.membership_terms_id,
            variant_id: product.variants[0].variant_id, amount_minor: 30000,
            currency: "JOD",
            starts_on: new Date(Date.now() - 25 * 86400000).toISOString().slice(0, 10),
            correlation_id: cid() },
  });
  await call(`/memberships/agreements/${expiringAgreement.agreement_id}/sign`, {
    method: "POST", ...as(token),
    body: { signature_kind: "click_through",
            signature_evidence_ref: `s3://signatures/${expiringAgreement.agreement_id}`,
            signed_by_person_id: secondPerson.person_id, correlation_id: cid() },
  });
  const flexMembership = await call("/memberships", {
    method: "POST", ...as(token),
    body: { agreement_id: expiringAgreement.agreement_id,
            membership_number: "FLEX-00107",
            idempotency_key: randomUUID(), correlation_id: cid() },
  });

  // ------------------------------------------------- ADM-PAY-05's two halves
  //
  // **The workspace's whole argument is that the set is one decision, and one case cannot
  // show whether it is.** The debt above is personal training with no membership behind it,
  // so `recovery_treatment` reads it as `review` -- somebody has to look, because the
  // ordinary dunning notice is a sentence about a membership this debt has nothing to do
  // with. This second one cites the member's actual membership and failed on an expired
  // card, which is the canvas's `link ready`: there is nothing to retry until they act.
  //
  // With only one of them seeded the board renders one branch of the banner and the other
  // passes vacuously -- the surface-branch vacuity this repository has now shipped four
  // times. Two halves, so both the "these are one decision" and the "these are not"
  // sentences are reachable and the row-level distinction is visible beside them.
  //
  // **A different member, because the canvas's six are six people.** Putting both halves on
  // one payer would also have put a second invoice on that member's billing tab, where two
  // existing assertions locate "the settled one" by its figure -- and the membership price
  // is the same number, so the locator would have matched both. The suite's own comment
  // already records that trap for `INV-`; this is the next rung of it.
  const secondAccount = await call("/finance/accounts", {
    method: "POST", ...as(token),
    body: { payer_person_id: secondPerson.person_id, account_number: "A-00107",
            currency: "JOD", legal_entity_id: entity.legal_entity_id,
            correlation_id: cid() },
  });
  const cardExpiredOn = new Date(Date.now() - 20 * 86400000).toISOString().slice(0, 10);
  const membershipDebt = await call("/finance/invoices", {
    method: "POST", ...as(token),
    body: {
      billing_account_id: secondAccount.billing_account_id, series_id: series.series_id,
      lines: [{ description: "Flex membership, November", quantity: 1,
                unit_net_minor: 32000, tax_rate_bp: 1600 }],
      issued_on: cardExpiredOn,
      due_on: new Date(Date.parse(cardExpiredOn) + 7 * 86400000)
        .toISOString().slice(0, 10),
      // **The membership the debt is for**, which is what makes the treatment derivable:
      // the read takes the membership the *invoice* cites, never the payer's latest.
      membership_id: flexMembership.membership_id,
      jurisdiction: "JO", idempotency_key: randomUUID(), correlation_id: cid(),
    },
  });
  const expiredCard = await call("/finance/payment-intents", {
    method: "POST", ...as(token),
    body: { billing_account_id: secondAccount.billing_account_id,
            invoice_id: membershipDebt.invoice_id,
            amount_minor: membershipDebt.gross_minor,
            method: "card", provider_key: "acme.payments",
            idempotency_key: randomUUID(), correlation_id: cid() },
  });
  await call(`/finance/payment-intents/${expiredCard.intent_id}/settle`, {
    method: "POST", ...as(token),
    body: { outcome: "failed", failure_code: "card_expired", correlation_id: cid() },
  });
  await call("/finance/dunning-cases", {
    method: "POST", ...as(token),
    body: { invoice_id: membershipDebt.invoice_id, idempotency_key: randomUUID(),
            correlation_id: cid() },
  });

  // **The message the first stage would send**, so the preview block renders a template
  // rather than its own "nobody authored this" state. The key is `collections.STAGES[0]`'s
  // own notification key: the stage picks the message, not whoever is looking at the
  // screen. Approved by the second identity, because an author cannot approve their own
  // template -- it goes out under the tenant's name to everybody.
  //
  // The body keeps its placeholders and one of them is the thing this build does not have.
  // A seeded example with a working-looking URL in it would be the fabricated-evidence
  // shape, in a fixture.
  const notice = await call("/notifications/templates", {
    method: "POST", ...as(token),
    body: {
      template_key: "payment_failed", version: 1, category: "transactional",
      channel: "email", locale: "en",
      subject: "Your {{ month }} payment did not go through",
      body: "Hi {{ name }} \u2014 your {{ month }} payment of {{ amount }} didn't go"
        + " through because {{ reason }}. You can pay here: {{ link }}. You're still able"
        + " to train as normal.",
      variables: ["name", "month", "amount", "reason", "link"],
      correlation_id: cid(),
    },
  });
  await call(`/notifications/templates/${notice.template_id}/approve`, {
    method: "POST", ...as(publisherToken), body: { correlation_id: cid() },
  });
  await call(`/notifications/templates/${notice.template_id}/publish`, {
    method: "POST", ...as(token), body: { correlation_id: cid() },
  });

  // **A period in `closing`, because otherwise the state nothing writes is the state nothing
  // proves.** The finance board's "needs somebody" banner, the `Takes a posting: No` cell and
  // the caption explaining that `closing` admits the close's own entries and no trade are all
  // unreachable while every period is open -- which is MOD-020's "a declared state nothing
  // writes" finding arriving in a fixture instead of a service. The back-dated month is the
  // one to close: everything posted into it is already there, and the current month stays
  // open so the board shows both states at once.
  const backDatedKey = startedOn.slice(0, 7);
  await call("/ledger/periods/close", {
    method: "POST", ...as(token),
    body: { legal_entity_id: entity.legal_entity_id, period_key: backDatedKey,
            target: "closing", correlation_id: cid() },
  });

  // ---------------------------------------------------------------- MOD-009, privacy
  //
  // Enough of each kind that every block on the privacy board shows a real row, and two
  // pairs that exist specifically to make a distinction visible: a live legal hold beside a
  // released one, because a hold's whole meaning is whether it is still preserving; and a
  // request due in the future beside one already overdue, because the deadline is the one
  // number on that screen with a regulator attached.
  await call("/privacy/purposes", {
    method: "POST", ...as(token),
    // A dotted code, because `sec_purposes_code_shape` allows an underscore only
            // after the first segment.
            body: { purpose_code: "membership.administration",
            description: "Administering memberships and access",
            lawful_basis: "contract", controller_role: "controller",
            // **`confidential`, not `contact`.** The classes here are MOD-009's four --
            // public, internal, confidential, restricted -- and MOD-008's *kinds*
            // (identity, contact, health) map onto them. A purpose names the class.
            data_classes: ["confidential", "restricted"], correlation_id: cid() },
  });
  await call("/privacy/retention", {
    method: "POST", ...as(token),
    body: { resource_type: "access_decision", data_class: "confidential",
            retention_days: 365, legal_basis: "legitimate_interest", region: "me-south-1",
            correlation_id: cid() },
  });
  const liveHold = await call("/privacy/legal-holds", {
    method: "POST", ...as(token),
    body: { reason: "Preserved for a claim under investigation",
            reference: "CASE-2026-114", resource_type: "access_decision",
            correlation_id: cid() },
  });
  const oldHold = await call("/privacy/legal-holds", {
    method: "POST", ...as(token),
    body: { reason: "Preserved for an enquiry that has since closed",
            reference: "CASE-2025-009", resource_type: "member_note",
            correlation_id: cid() },
  });
  await call(`/privacy/legal-holds/${oldHold.hold_id}/release`, {
    method: "POST", ...as(token),
    body: { release_reason: "the enquiry closed with no action",
            correlation_id: cid() },
  });
  // **A request already past its deadline.** `received_at` is bounded so a caller cannot set
  // the regulator-facing deadline forward, but it may be in the past -- which is how a
  // genuinely overdue request exists, and the only way the board's overdue path is reachable.
  await call("/privacy/requests", {
    method: "POST", ...as(token),
    body: { subject_id: ownerIdentityId, request_type: "access", response_days: 30,
            correlation_id: cid() },
  });
  await call("/privacy/requests", {
    method: "POST", ...as(token),
    body: { subject_id: ownerIdentityId, request_type: "deletion", response_days: 1,
            received_at: new Date(Date.now() - 10 * 86400000).toISOString(),
            correlation_id: cid() },
  });
  await call("/privacy/incidents", {
    method: "POST", ...as(token),
    body: { severity: "low", category: "access_control",
            summary: "A door reader was offline for twenty minutes",
            detected_at: new Date(Date.now() - 2 * 86400000).toISOString(),
            personal_data_involved: "no", correlation_id: cid() },
  });

  // ---------------------------------------------------------------- MOD-013, messages
  //
  // **Two templates and two suppressions, because each pair is a distinction.** One template
  // is `transactional`, which a member cannot mute, and one is `marketing`, which they can --
  // the category is what decides whether a consent record is required and whether an opt-out
  // can stop the message, and a board with one of them shows neither side. One suppression is
  // an unsubscribe, which may be lifted; the other a bounce, which may not, because it is the
  // channel's judgement about deliverability rather than the tenant's choice.
  //
  // **The author is not the approver**, by constraint: a template goes out under the tenant's
  // name to everybody, which is MOD-008's separation of duties applied to content.
  await call("/notifications/channels", {
    method: "PUT", ...as(token),
    body: { channel: "email", enabled: true, fallback_channel: null,
            cost_per_message_minor: 2, currency: "JOD", correlation_id: cid() },
  });
  await call("/notifications/channels", {
    method: "PUT", ...as(token),
    body: { channel: "sms", enabled: false, fallback_channel: "email",
            cost_per_message_minor: 45, currency: "JOD", correlation_id: cid() },
  });

  const templates = {};
  for (const [key, category, subject] of [
    ["payment.failed", "transactional", "Your payment did not go through"],
    ["class.offer", "marketing", "A class you might like"],
  ]) {
    const made = await call("/notifications/templates", {
      method: "POST", ...as(token),
      body: { template_key: key, version: 1, category, channel: "email", locale: "en",
              subject, body: "Hello {{ name }}.", variables: ["name"],
              correlation_id: cid() },
    });
    await call(`/notifications/templates/${made.template_id}/approve`, {
      method: "POST", ...as(publisherToken), body: { correlation_id: cid() },
    });
    // Publishing is `template.write`, which the author holds; only the approval has to be
    // somebody else.
    await call(`/notifications/templates/${made.template_id}/publish`, {
      method: "POST", ...as(token), body: { correlation_id: cid() },
    });
    templates[key] = made.template_id;
  }

  // A digest of `channel:address`, computed exactly as `delivery.address_digest` does. The
  // address itself never reaches this build's notification tables, which is the point.
  const digestOf = (channel, address) =>
    createHash("sha256").update(`${channel}:${address}`).digest("hex");

  await call("/notifications", {
    method: "POST", ...as(token),
    body: { template_key: "payment.failed", recipient_id: person.person_id,
            address_digests: { email: digestOf("email", "jane.member@veyro.test") },
            idempotency_key: randomUUID(), variables: { name: "Jane" },
            correlation_id: cid() },
  });

  await call("/notifications/suppressions", {
    method: "POST", ...as(token),
    body: { channel: "email", address_digest: digestOf("email", "left@veyro.test"),
            reason: "unsubscribed", detail: "asked to stop at the front desk",
            correlation_id: cid() },
  });

  // ---------------------------------------------------------------- MOD-012, integrations
  //
  // **Two installs, because the written obligations only bind one of them.** A
  // `live_critical` install needs a fallback, a reconciliation procedure and an exit plan in
  // writing before it may carry traffic; a `standard` one does not. A board with only the
  // second shows a column that never says anything, and with only the first cannot show the
  // difference between "satisfied" and "not required".
  //
  // The definition lives on the platform plane, which is unauthenticated in this build and
  // worse there than the plan catalogue: a definition declares the scopes an install may
  // grant a third party, so whoever can publish one chooses what a tenant is able to hand out.
  // **The key is unique per run, because the definition catalogue is not tenant-scoped.** It
  // lives in `plt01_platform` beside the plan catalogue, so a fixed key registers once ever
  // and every later fixture run is refused with "a version must be higher than the last" --
  // which reads as a product defect and is a fixture that can only be provisioned once. The
  // suffix is what makes this suite re-runnable, and it is the same reason the tenant,
  // identity and template keys carry one.
  const partner = `acme${Date.now().toString(36)}`;
  for (const [key, criticality] of [
    [`${partner}.ledger`, "critical"],
    [`${partner}.newsletter`, "important"],
  ]) {
    await call("/platform/integrations", {
      method: "POST",
      body: {
        definition_key: key, version: 1, provider: "Acme",
        display_name: key.endsWith(".ledger") ? "Acme Ledger" : "Acme Newsletter",
        criticality, support_owner: "partners@acme.invalid",
        description: "A synthetic definition for the local fixture.",
        capabilities: ["accounting"], scopes: ["members.read"],
        required_scopes: ["members.read"],
        // `field_type`, not `type`: the name a person reaches for is the one the
        // service does not take, which is how the 500 this fixture found was found.
        config_fields: [{ name: "account", field_type: "string", required: true }],
        regions: ["me-south-1"],
      },
    });
    await call(`/platform/integrations/${key}/1/publish`, { method: "POST" });
  }

  const critical = await call("/integrations", {
    method: "POST", ...as(token),
    body: { definition_key: `${partner}.ledger`, version: 1,
            config: { account: "acct-1" }, correlation_id: cid() },
  });
  // **Only two of the three obligations**, deliberately: the board's job is to notice.
  await call(`/integrations/${critical.install_id}/configure`, {
    method: "POST", ...as(token),
    body: { fallback_plan: "Fall back to manual export while the provider is down.",
            reconciliation_plan: "Compare counts nightly against the ledger export.",
            correlation_id: cid() },
  });
  const standard = await call("/integrations", {
    method: "POST", ...as(token),
    body: { definition_key: `${partner}.newsletter`, version: 1,
            config: { account: "acct-2" }, correlation_id: cid() },
  });

  const connection = await call("/integrations/connections", {
    method: "POST", ...as(token),
    body: { install_id: standard.install_id, external_account_ref: "acme-acct-2",
            region: "me-south-1", granted_scopes: ["members.read"],
            vault_ref: "vault://veyro/local/acme-newsletter",
            expires_at: new Date(Date.now() + 90 * 86400000).toISOString(),
            correlation_id: cid() },
  });
  // **`validated` means somebody recorded a validation, not that this build performed one.**
  // There is no provider to call, so the state carries an actor and a written piece of
  // evidence and the row says what it is: a claim made by a named party at a time. A run
  // refuses an unvalidated connection, which is why this comes first.
  await call(`/integrations/connections/${connection.connection_id}/validate`, {
    method: "POST", ...as(token),
    body: { evidence: "a test call answered 200 from the partner console",
            correlation_id: cid() },
  });
  // **Install, connect, validate, activate, run -- in that order, and the order is the
  // product.** An install cannot activate without a validated connection, because activating
  // one is the act that says a third party may carry this tenant's traffic; and a run refuses
  // an install that is not active. The critical install below stays inactive on purpose: it
  // has two of its three written obligations, and activation is where that is checked.
  await call(`/integrations/${standard.install_id}/activate`, {
    method: "POST", ...as(token), body: { correlation_id: cid() },
  });

  await call("/integrations/cursors", {
    method: "POST", ...as(token),
    body: { connection_id: connection.connection_id, resource: "members",
            position: "2026-11-01T00:00:00Z", observed_at: new Date().toISOString(),
            correlation_id: cid() },
  });
  // A run that was opened and reported a result. Nothing called a provider.
  const run = await call("/integrations/runs", {
    method: "POST", ...as(token),
    body: { connection_id: connection.connection_id, resource: "members",
            max_attempts: 5, correlation_id: cid() },
  });
  await call(`/integrations/runs/${run.run_id}/finish`, {
    method: "POST", ...as(token),
    body: { records_read: 120, records_written: 118, conflicts: 2,
            correlation_id: cid() },
  });

  // **A consumer the relay can route to.** Without one the outbox is fanned out to nobody and
  // the operations board has no deliveries to show -- which hides the half of that screen
  // that is still a standing gap: a delivery is created and never handled, because no name in
  // this build has a handler behind it.
  await call("/events/subscriptions", {
    method: "POST", ...as(token),
    body: { consumer: "member_projection", event_type: "person.created",
            replay_safety: "safe", correlation_id: cid() },
  });

  // ---------------------------------------------------------------- ADM-STF-01 / ADM-STF-02
  //
  // **The team, and the finding the design says the LAST SEEN column exists for.**
  // `ppl_staff_profiles` had no reader until now, so nothing in this fixture had ever written
  // one. Four profiles, because the standing a row shows is a *pair* -- employment and access
  // -- and a fixture with one member of each pair renders a branch and demonstrates nothing,
  // which is the surface-branch vacuity this repository has shipped four times:
  //
  //   1. **Layla**, working, linked to the publisher identity, with a second narrow role, so
  //      ADM-STF-02's "beyond their role" has something in it and carries an attribution.
  //   2. **Omar**, employment ended, login still live -> `endedWithAccess`, the finding.
  //   3. **Yasmin**, employment ended and the identity suspended -> `ended`, the clean exit.
  //      Unreachable before this change: nothing in the build could set the status.
  //   4. **Dana**, working with no identity link at all -> `workingNoLogin`, which is not a
  //      fault: a cleaner on the payroll needs no account.
  const layla = await call("/people", {
    method: "POST", ...as(token),
    body: { legal_name: "Layla Mansour", correlation_id: cid() },
  });
  await call(`/people/${layla.person_id}/identity-links`, {
    method: "POST", ...as(token),
    body: { identity_id: secondSession.identity_id, correlation_id: cid() },
  });
  await call(`/people/${layla.person_id}/staff-profile`, {
    method: "POST", ...as(token),
    body: { job_title: "Reception", location_id: location.location_id,
            started_on: "2025-01-06", correlation_id: cid() },
  });
  // **A second, narrower assignment**, which is what "beyond her role" is in this build:
  // there are no per-identity grants, so an additional role assignment is the thing that
  // carries `granted_by` and `granted_at` -- the canvas's attribution line exactly. Scoped to
  // the location so `splitRole` has a real breadth difference to order on, and carrying a
  // financial-class permission so the sensitive-grants block is not empty.
  const extraRole = await call("/authz/roles", {
    method: "POST", ...as(token),
    body: {
      role_key: `till_refunds_${Date.now()}`, display_name: "Till refunds",
      // **Financial, and one the wide role does not hold.** `finance.refund.request` is
      // `routine`, so the grants block filtered it correctly and the page proved nothing
      // about scope -- I read that absence as the scope defect and it was not. And a
      // permission the tenant-wide role already carries would be visible at the default
      // scope anyway, so it has to be one only this narrow assignment grants.
      permissions: ["finance.wallet.credit"], correlation_id: cid(),
    },
  });
  await call("/authz/assignments", {
    method: "POST", ...as(token),
    body: {
      identity_id: secondSession.identity_id, role_key: extraRole.role_key,
      scope_type: "location", location_id: location.location_id, correlation_id: cid(),
    },
  });

  // Omar: the finding. A live login after employment ended.
  const omarEmail = `omar.s+${Date.now()}@veyro.invalid`;
  const omarPassword = `e2e-${randomUUID()}`;
  const omarIdentity = await call("/identities", {
    method: "POST", tenant: tenantId,
    body: { display_name: "Omar Said", email: omarEmail, password: omarPassword,
            correlation_id: cid() },
  });
  // Signing in is what gives them a live session and a last-seen instant. Without it the row
  // would still read `endedWithAccess` -- the identity's own status is enough -- but the
  // timestamp the column renders would be empty, and the two cases look different on screen.
  await call("/auth/login", {
    method: "POST", tenant: tenantId,
    body: { identifier: omarEmail, password: omarPassword, correlation_id: cid() },
  });
  const omar = await call("/people", {
    method: "POST", ...as(token),
    body: { legal_name: "Omar Said", correlation_id: cid() },
  });
  await call(`/people/${omar.person_id}/identity-links`, {
    method: "POST", ...as(token),
    body: { identity_id: omarIdentity.identity_id, correlation_id: cid() },
  });
  const omarStaff = await call(`/people/${omar.person_id}/staff-profile`, {
    method: "POST", ...as(token),
    body: { job_title: "Sales", location_id: location.location_id,
            started_on: "2024-09-02", correlation_id: cid() },
  });
  await call(`/people/${omar.person_id}/staff-profile/end`, {
    method: "POST", ...as(token),
    body: { expected_version: omarStaff.version,
            ended_on: new Date(Date.now() - 20 * 86400000).toISOString().slice(0, 10),
            correlation_id: cid() },
  });

  // Yasmin: the clean exit, which this build could not produce until `set_identity_status`
  // existed. Four controls read `iam.identities.status` and nothing wrote it, so every
  // departed employee was `endedWithAccess` and the board's good state was unreachable.
  const yasminEmail = `yasmin+${Date.now()}@veyro.invalid`;
  const yasminPassword = `e2e-${randomUUID()}`;
  const yasminIdentity = await call("/identities", {
    method: "POST", tenant: tenantId,
    body: { display_name: "Yasmin Haddad", email: yasminEmail, password: yasminPassword,
            correlation_id: cid() },
  });
  await call("/auth/login", {
    method: "POST", tenant: tenantId,
    body: { identifier: yasminEmail, password: yasminPassword, correlation_id: cid() },
  });
  const yasmin = await call("/people", {
    method: "POST", ...as(token),
    body: { legal_name: "Yasmin Haddad", correlation_id: cid() },
  });
  await call(`/people/${yasmin.person_id}/identity-links`, {
    method: "POST", ...as(token),
    body: { identity_id: yasminIdentity.identity_id, correlation_id: cid() },
  });
  const yasminStaff = await call(`/people/${yasmin.person_id}/staff-profile`, {
    method: "POST", ...as(token),
    body: { job_title: "Coach", location_id: location.location_id,
            started_on: "2023-04-17", correlation_id: cid() },
  });
  await call(`/people/${yasmin.person_id}/staff-profile/end`, {
    method: "POST", ...as(token),
    body: { expected_version: yasminStaff.version,
            ended_on: new Date(Date.now() - 60 * 86400000).toISOString().slice(0, 10),
            correlation_id: cid() },
  });
  // The offboarding the product can now do. `identity.identity.write` is financial, and
  // `token` here *is* the stepped-up owner session: `seedAccess` is called with the token
  // `stepUp` returned, which is why every financial write in this function works.
  await call(`/identities/${yasminIdentity.identity_id}/status`, {
    method: "POST", ...as(token),
    body: { status: "suspended", reason: "left the company, offboarded 60 days ago",
            correlation_id: cid() },
  });

  // **Rami: the leaver whose account still works although no session is open.** The
  // commonest real shape -- somebody left, their session expired or was signed out, and
  // nobody suspended the identity -- and the one the fixture was missing. Omar has a live
  // session, so a rule reading only `live_sessions > 0` calls him "can still sign in" too
  // and a weakening of the `status === "active"` half changes nothing about him. This row is
  // the one that falls on the other side of that weakening, which is what makes it evidence:
  // never signed in, so no session, and `active` because nothing in this build suspended it.
  const ramiEmail = `rami+${Date.now()}@veyro.invalid`;
  const ramiIdentity = await call("/identities", {
    method: "POST", tenant: tenantId,
    body: { display_name: "Rami Odeh", email: ramiEmail,
            password: `e2e-${randomUUID()}`, correlation_id: cid() },
  });
  const rami = await call("/people", {
    method: "POST", ...as(token),
    body: { legal_name: "Rami Odeh", correlation_id: cid() },
  });
  await call(`/people/${rami.person_id}/identity-links`, {
    method: "POST", ...as(token),
    body: { identity_id: ramiIdentity.identity_id, correlation_id: cid() },
  });
  const ramiStaff = await call(`/people/${rami.person_id}/staff-profile`, {
    method: "POST", ...as(token),
    body: { job_title: "Front desk", location_id: location.location_id,
            started_on: "2022-06-14", correlation_id: cid() },
  });
  await call(`/people/${rami.person_id}/staff-profile/end`, {
    method: "POST", ...as(token),
    body: { expected_version: ramiStaff.version,
            ended_on: new Date(Date.now() - 10 * 86400000).toISOString().slice(0, 10),
            correlation_id: cid() },
  });

  // Dana: on the payroll with no login, which the board must not draw as a fault.
  const dana = await call("/people", {
    method: "POST", ...as(token),
    body: { legal_name: "Dana Khalil", correlation_id: cid() },
  });
  await call(`/people/${dana.person_id}/staff-profile`, {
    method: "POST", ...as(token),
    body: { job_title: "Spin coach", location_id: location.location_id,
            started_on: "2026-02-10", correlation_id: cid() },
  });

  // ---------------------------------------------------------------------------------------
  // MOD-026: ADM-TSK-01's list, ADM-CC-06's sheet and ADM-CC-07's record.
  //
  // **An identity that is somebody, because two of the three screens depend on it.** The
  // sheet's five states include "assigned to me" and ADM-TSK-01's first chip is "Mine", and
  // both are derived from `ppl_identity_links` -- so a fixture whose only session is the
  // owner (who is nobody in this tenant, which is ordinary for staff) could render neither
  // branch. That is this repository's own "a surface branch no fixture can reach" trap, which
  // it has paid for four times, so this seeds the identity rather than leaving the state to a
  // component test. The owner then reads the same item as *somebody else's*, which is the one
  // state ADM-CC-06 is most specific about -- so both halves have a fixture.
  const taskEmail = `tasks+${Date.now()}@veyro.invalid`;
  const taskPassword = `e2e-${randomUUID()}`;
  await call("/identities", {
    method: "POST", tenant: tenantId,
    body: {
      display_name: "E2E Duty Manager", correlation_id: cid(), email: taskEmail,
      password: taskPassword,
    },
  });
  const taskSession = await call("/auth/login", {
    method: "POST", tenant: tenantId,
    body: { identifier: taskEmail, password: taskPassword, correlation_id: cid() },
  });
  const taskWho = await call("/auth/session", { tenant: tenantId, token: taskSession.token });
  const taskRole = await call("/authz/roles", {
    method: "POST", ...as(token),
    body: {
      role_key: `duty_${Date.now()}`, display_name: "Duty manager",
      // Every MOD-026 permission is routine, which is why these three screens have working
      // write forms where every other write in this app is a stepped-up financial one.
      permissions: ["tasks.task.read", "tasks.task.write", "tasks.case.read",
                    "tasks.case.write", "tasks.queue.read", "tasks.sla.read"],
      correlation_id: cid(),
    },
  });
  await call("/authz/assignments", {
    method: "POST", ...as(token),
    body: { identity_id: taskWho.identity_id, role_key: taskRole.role_key,
            correlation_id: cid() },
  });
  // **This app's device, confirmed**, so a spec signing in as this identity is not challenged.
  // A challenge would have to be answered with a recovery code, which is single-use -- the
  // trap this suite has recorded three times: a green that depends on how many times the
  // suite has been run.
  await confirmWebDevice(tenantId, taskWho.identity_id, taskSession.token, taskEmail,
                         taskPassword);

  const dutyPerson = await call("/people", {
    method: "POST", ...as(token),
    body: { legal_name: "Nadia Suleiman", correlation_id: cid() },
  });
  await call(`/people/${dutyPerson.person_id}/identity-links`, {
    method: "POST", ...as(token),
    body: { identity_id: taskWho.identity_id, correlation_id: cid() },
  });

  const deskQueue = await call("/tasks/queues", {
    method: "POST", ...as(token),
    body: { queue_key: `front_desk_${Date.now()}`, display_name: "Front desk",
            location_id: location.location_id, correlation_id: cid() },
  });
  const dutyQueue = await call("/tasks/queues", {
    method: "POST", ...as(token),
    body: { queue_key: `duty_${Date.now()}`, display_name: "Duty manager",
            location_id: location.location_id, correlation_id: cid() },
  });

  const openCase = (number, title, over = {}) => call("/tasks/cases", {
    method: "POST", ...as(token),
    body: {
      case_number: number, title, queue_id: deskQueue.queue_id, subject_kind: "tenant",
      priority: "high", source: "automation", idempotency_key: `c-${randomUUID()}`,
      correlation_id: cid(), ...over,
    },
  });

  // ADM-CC-06's own subject: "6 payments failed overnight · JOD 312.00". Unassigned as drawn.
  const moneyCase = await openCase("EXC-8841", "6 payments failed overnight");
  // **The records it is about, which is the fact a batch action is sized by.** Five that
  // resolve against a real person and one `lead`, which resolves against nothing in this
  // build -- so the sheet's "nothing here can confirm this reference" marker has a row.
  const affected = [person.person_id, twin.person_id, layla.person_id, omar.person_id,
                    dana.person_id];
  for (const who of affected) {
    await call(`/tasks/cases/${moneyCase.case_id}/affected`, {
      method: "POST", ...as(token),
      body: { affected_kind: "member", affected_id: who, correlation_id: cid() },
    });
  }
  await call(`/tasks/cases/${moneyCase.case_id}/affected`, {
    method: "POST", ...as(token),
    body: { affected_kind: "lead", affected_id: randomUUID(), correlation_id: cid() },
  });
  // **And one taken off, because a withdrawal is not a deletion.** "Was this member ever on
  // this exception" is asked exactly when somebody was contacted by mistake, so the row stays
  // and the sheet lists it separately from the count the batch is sized by.
  const mistaken = await call("/people", {
    method: "POST", ...as(token),
    body: { legal_name: "Faris Alami", correlation_id: cid() },
  });
  await call(`/tasks/cases/${moneyCase.case_id}/affected`, {
    method: "POST", ...as(token),
    body: { affected_kind: "member", affected_id: mistaken.person_id, correlation_id: cid() },
  });
  await call(`/tasks/cases/${moneyCase.case_id}/affected/withdraw`, {
    method: "POST", ...as(token),
    body: { affected_kind: "member", affected_id: mistaken.person_id,
            reason: "his card went through on the retry", correlation_id: cid() },
  });
  // The canvas's "WHAT VEYRO HAS ALREADY DONE", in its own words and at its own times.
  //
  // **`occurred_at` is the caller's and `recorded_at` is not**, which is what makes a
  // timeline readable here: the three lines are 06:12 and 06:13 on the canvas, and a fixture
  // writing them all at `now()` would render three identical clocks in a 66px gutter whose
  // whole purpose is a vertical scan.
  for (const [kind, summary, minutes] of [
    ["status_change", "Billing run \u00b7 6 of 214 charges declined", 0],
    ["communication", "6 reminder messages drafted, held for approval", 1],
    ["escalation", "Exception raised to the Command Center", 1],
  ]) {
    await call(`/tasks/cases/${moneyCase.case_id}/entries`, {
      method: "POST", ...as(token),
      body: {
        entry_kind: kind, summary, correlation_id: cid(),
        occurred_at: clubLocalInstant(1, 6, 12 + minutes),
      },
    });
  }
  // A running target, so the header's "a target is running on this item" has a row behind it.
  await call("/tasks/clocks", {
    method: "POST", ...as(token),
    body: { case_id: moneyCase.case_id, target_seconds: 4 * 3600,
            escalate_to_queue_id: dutyQueue.queue_id, warn_at_basis_points: 8000,
            correlation_id: cid() },
  });

  // Assigned to the duty manager, which is "mine" for that session and "someone else's" for
  // the owner -- the one state whose rule is that every action stays visible and inert.
  const assignedCase = await openCase(
    "EXC-8842", "Lead not contacted \u00b7 3 from Friday", { priority: "normal" });
  await call(`/tasks/cases/${assignedCase.case_id}/assign`, {
    method: "POST", ...as(token),
    body: { assignee_person_id: dutyPerson.person_id, correlation_id: cid() },
  });

  // Deferred, with the reason and the return date the canvas requires.
  const snoozedCase = await openCase("EXC-8843", "Document expiring \u00b7 2 waivers");
  const returnOn = new Date(Date.now() + 9 * 86400000).toISOString().slice(0, 10);
  await call(`/tasks/cases/${snoozedCase.case_id}/snooze`, {
    method: "POST", ...as(token),
    body: { snoozed_until: `${returnOn}T00:00:00Z`,
            reason: "the member is away until the ninth", correlation_id: cid() },
  });

  // **Two resolved, so ADM-CC-07's median is a median of something.** The elapsed times are
  // all under a minute here and that is a property of the fixture rather than of the screen:
  // `tsk_cases.opened_at` is `now()` and no route backdates it, which is right for the product
  // -- a case is opened when it is opened. The *format* of the figure is proven against the
  // canvas's own `12m` / `1h 20m` / `2h 04m` in `tests/component/tasks.test.ts`.
  for (const [number, title, outcome] of [
    ["EXC-8839", "Low stock \u00b7 protein bars, Khalda", "Ordered"],
    ["EXC-8840", "Access denial \u00b7 Sweifieh card reader", "Manual entry"],
  ]) {
    const done = await openCase(number, title);
    await call(`/tasks/cases/${done.case_id}/settle`, {
      method: "POST", ...as(token),
      body: { target: "resolved", resolution_reason: outcome, correlation_id: cid() },
    });
  }

  // ADM-TSK-01's rows, one per shape its meta line has to render.
  const raise = (title, over = {}) => call("/tasks", {
    method: "POST", ...as(token),
    body: {
      queue_id: deskQueue.queue_id, title, subject_kind: "tenant", priority: "normal",
      source: "manual", idempotency_key: `t-${randomUUID()}`, correlation_id: cid(), ...over,
    },
  });
  const day = (offset) => new Date(Date.now() + offset * 86400000).toISOString();
  const overdueTask = await raise("Call Tareq Odeh about his lapsed membership", {
    case_id: moneyCase.case_id, due_at: day(-2), priority: "high",
    subject_kind: "member", subject_id: person.person_id,
  });
  await raise("Chase Omar for 22 unverified sessions", { due_at: day(0) });
  await raise("Renew Dana\u2019s spin certification", {
    source: "automation", due_at: day(18),
  });
  await raise("Review the Sweifieh reader replacement quote", { due_at: day(3) });
  // Assigned to the duty manager, so that session's `Mine` chip is not zero.
  const mineTask = await raise("Confirm September class timetable", {
    assignee_person_id: dutyPerson.person_id, due_at: day(6),
  });
  // **And one blocked by another, which is the row the bulk selection must not offer.**
  // `blocked -> done` is not an edge, in the Python table and in the trigger -- a blocked task
  // is unblocked before it is finished -- so the screen draws no checkbox on it, and without
  // this seed that branch would be a branch no fixture reaches. It also gives R07's
  // bottleneck a blocker to name, which is the figure a count of blocked work cannot answer.
  const blocker = await raise("Get the landlord's sign-off on the riser", { due_at: day(4) });
  const blockedTask = await raise("Install the second turnstile", { due_at: day(5) });
  await call(`/tasks/${blockedTask.task_id}/dependencies`, {
    method: "POST", ...as(token),
    body: { depends_on_task_id: blocker.task_id, correlation_id: cid() },
  });
  await call(`/tasks/${blockedTask.task_id}/status`, {
    method: "POST", ...as(token),
    body: { target: "blocked", reason: "waiting on the riser", correlation_id: cid() },
  });

  // And one already settled, so the overdue filter has a row it must *not* return -- a task
  // finished late is not overdue work -- and the in-hand list has one it must not show.
  const settledTask = await raise("Order the replacement turnstile board", { due_at: day(-5) });
  await call(`/tasks/${settledTask.task_id}/status`, {
    method: "POST", ...as(token),
    body: { target: "done", reason: "ordered on the fourteenth", correlation_id: cid() },
  });

  // ---- MOD-027's pipeline (ADM-CRM-01, ADM-CRM-02) ----------------------------------
  //
  // **Four leads, because a board with one card demonstrates nothing.** One in each stored
  // stage plus an unattributed one, so the board draws three non-empty columns and the table
  // has a row for each -- and one of them is cold, which is the single row state either view
  // has. A lead cannot be *aged* from here (`crm_leads.created_at` is outside every runtime
  // role's UPDATE grant, deliberately: a lead whose age could be reset is a lead that never
  // goes cold), so the cold one is the lead nobody has touched and the warm ones carry a
  // touchpoint written just now.
  const leadSource = await call("/crm/sources", {
    method: "POST", ...as(token),
    body: {
      source_key: "sweifieh_open_day", display_name: "Sweifieh open day",
      correlation_id: cid(),
    },
  });
  const leadFor = async (name, over = {}) => {
    const who = await call("/people", {
      method: "POST", ...as(token),
      body: { legal_name: name, profile_kinds: ["lead"], correlation_id: cid() },
    });
    // **A phone on the lead, because ADM-CRM-04's whole subject is finding one.** Without it
    // the add-lead form's duplicate check has no lead to find, and its deterministic case --
    // a person who *already has a lead*, where the server returns theirs rather than opening
    // a second -- is the one state no `fresh()` number can reach. The `01NN` block pairs with
    // the member's `0042` so both read as fixture data at a glance.
    const body = { ...over };
    if (body.phone !== undefined) {
      await call(`/people/${who.person_id}/contacts`, {
        method: "POST", ...as(token),
        body: { kind: "phone", value: body.phone, is_primary: true,
                correlation_id: cid() },
      });
      delete body.phone;
    }
    return call("/crm/leads", {
      method: "POST", ...as(token),
      body: {
        person_id: who.person_id, source_id: leadSource.source_id,
        correlation_id: cid(), ...body,
      },
    });
  };
  // Cold: no touchpoint at all, so the clock runs from its creation -- which is the canvas's
  // own case, "Rana Sabbagh NO CONTACT · 2 DAYS" beside "open day · 2d". It reads warm here
  // because it was made a moment ago; what the fixture proves is that the row is drawn and
  // that the chip filters, and the forty-eight-hour boundary is the component test's.
  const coldLead = await leadFor("Rana Sabbagh", {
    interests: ["classes", "pt"], phone: "+962 79 000 0101",
  });
  const contactedLead = await leadFor("Omar Zaid");
  await call(`/crm/leads/${contactedLead.lead_id}/touchpoints`, {
    method: "POST", ...as(token),
    body: {
      kind: "call", summary: "asked twice about the 19:00 spin class",
      correlation_id: cid(),
    },
  });
  const touredLead = await leadFor("Lina Haddad");
  await call(`/crm/leads/${touredLead.lead_id}/touchpoints`, {
    method: "POST", ...as(token),
    body: { kind: "tour", summary: "walked the floor with Yasmin", correlation_id: cid() },
  });
  // An owned lead with a next action, which is the one row where ADM-CRM-02's OWNER and NEXT
  // ACTION columns have anything in them. The owner is the seeded member, because this
  // fixture's staff are sign-ins rather than people -- which is the asymmetry the board's
  // own "mine" branch is about.
  const ownedLead = await leadFor("Faris Alami", { owner_person_id: person.person_id });
  await call(`/crm/leads/${ownedLead.lead_id}/next-action`, {
    method: "POST", ...as(token),
    body: {
      next_action: "call back about the 17:00 tour", next_action_on: day(2).slice(0, 10),
      correlation_id: cid(),
    },
  });

  // Last, so it sees everything above. The timeline, the dispatched outbox and the sweeps on
  // the operations board are all these ticks' work.
  //
  // **Ticks until the outbox is empty, not once.** `dispatch_pending` claims a batch, so one
  // tick drains a batch -- and the moment this fixture seeded more events than that, the
  // operations board showed a pending backlog and its "the relay drained it" assertion
  // failed. That is a property of the batch size rather than of the relay, which is exactly
  // what the board exists *not* to report: a pending event that persists is supposed to mean
  // a worker that is down. Every job is idempotent, so a second pass is free by construction.
  let tick = runWorkerTick(tenantId);
  for (let pass = 0; pass < 5; pass += 1) {
    const pending = await call("/events/health", { ...as(token) });
    if ((pending.pending_events ?? 0) === 0) break;
    tick = runWorkerTick(tenantId);
  }

  return {
    templateId: template.template_id,
    sessionsGenerated: generated.created,
    firstSessionId: substituted,
    standInResourceId: standIn.resource_id,
    openDrawerId: openDrawer.session_id,
    safeAccountId: safeAccount.account_id,
    suiteTillAccountId: e2eTill.account_id,
    legalEntityId: entity.legal_entity_id,
    closedDrawerId: closedDrawer.session_id,
    noRotaResourceId: noRota.resource_id,
    bookingId: booking?.booking_id ?? null,
    bookedSessionId: bookable,
    deskSessionId,
    instructorResourceId: instructor.resource_id,
    rotaExceptionDay,
    workerRuns: tick.runs,
    workerFailed: tick.failed,
    deviceId: device.device_id,
    pendingDeviceId: pending.device_id,
    duplicateCandidates: candidates.length,
    twinPersonId: twin.person_id,
    overriddenPersonId: twin.person_id,
    deskEmail,
    deskPassword,
    easyEmail: EASY_EMAIL,
    easyPassword: EASY_PASSWORD,
    easyRecoveryCode: easyCodes.codes[0],
    publisherEmail: secondEmail,
    publisherPassword: secondPassword,
    // ADM-STF-01's four standings, named so a spec asserts the row it means rather than
    // whichever row happens to sort first.
    staffWorkingPersonId: layla.person_id,
    staffEndedWithAccessPersonId: omar.person_id,
    staffOffboardedPersonId: yasmin.person_id,
    staffNoLoginPersonId: dana.person_id,
    staffNeverSignedInPersonId: rami.person_id,
    locationId: location.location_id,
    // MOD-026's three screens. `taskEmail` is the only session in this fixture whose identity
    // is a person, which is what makes "assigned to me" and the `Mine` chip renderable.
    taskEmail,
    taskPassword,
    dutyPersonId: dutyPerson.person_id,
    deskQueueId: deskQueue.queue_id,
    moneyCaseId: moneyCase.case_id,
    moneyCaseNumber: "EXC-8841",
    assignedCaseId: assignedCase.case_id,
    snoozedCaseId: snoozedCase.case_id,
    snoozedReturnOn: returnOn,
    // MOD-027's pipeline.
    leadSourceId: leadSource.source_id,
    coldLeadId: coldLead.lead_id,
    contactedLeadId: contactedLead.lead_id,
    touredLeadId: touredLead.lead_id,
    ownedLeadId: ownedLead.lead_id,
    overdueTaskId: overdueTask.task_id,
    mineTaskId: mineTask.task_id,
    settledTaskId: settledTask.task_id,
    blockedTaskId: blockedTask.task_id,
    zoneId: zone.zone_id,
    pointId: point.point_id,
    personId: person.person_id,
    // ADM-MSH-07's four commitment sentences, one member each, named so a spec asserts the
    // case it means rather than whichever membership sorts first. `person` above is the
    // fourth -- a rolling contract with no commitment at all.
    buyOutPersonId: commitments.buyOut,
    heldToTermPersonId: commitments.heldToTerm,
    servedTermPersonId: commitments.served,
    membershipId: membership.membership_id,
    retiredAccountId: retiring.account_id,
    productId: product.product_id,
    // ADM-PAY-03's subject: the invoice that was paid, has a fiscal rejection on it and
    // carries a dispute and a refund -- which is every state the screen draws except a
    // credit note, in one document.
    invoiceId: invoice.invoice_id,
    closingPeriodKey: backDatedKey,
    liveHoldId: liveHold.hold_id,
    membershipNumber: "GOLD-00042",
    invoiceNumber: invoice.document_number,
    invoiceGrossMinor: invoice.gross_minor,
    credentialId: credential.credential_id,
    decisionCode: decision.code,
    ownerEmail,
  };
}

const invokedDirectly =
  process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];

if (invokedDirectly) {
  const fixture = await provision();
  const target = fileURLToPath(new URL("../../.env.e2e.local", import.meta.url));
  writeFileSync(
    target,
    [
      "# Generated by tests/e2e/fixture.mjs. Synthetic, local, disposable.",
      "# Gitignored by the root .gitignore's `.env.*` rule. Re-run the fixture for a fresh one.",
      `VEYRO_E2E_TENANT_ID=${fixture.tenantId}`,
      `VEYRO_E2E_IDENTITY_ID=${fixture.identityId}`,
      `VEYRO_E2E_EMAIL=${fixture.email}`,
      `VEYRO_E2E_PASSWORD=${fixture.password}`,
      `VEYRO_E2E_RECOVERY_CODE=${fixture.recoveryCode}`,
      `VEYRO_E2E_ZONE_ID=${fixture.zoneId}`,
      `VEYRO_E2E_COACH_RESOURCE_ID=${fixture.instructorResourceId}`,
      `VEYRO_E2E_STANDIN_RESOURCE_ID=${fixture.standInResourceId}`,
      `VEYRO_E2E_OPEN_DRAWER_ID=${fixture.openDrawerId}`,
      `VEYRO_E2E_SAFE_ACCOUNT_ID=${fixture.safeAccountId}`,
      `VEYRO_E2E_SUITE_TILL_ACCOUNT_ID=${fixture.suiteTillAccountId}`,
      `VEYRO_E2E_LEGAL_ENTITY_ID=${fixture.legalEntityId}`,
      `VEYRO_E2E_CLOSED_DRAWER_ID=${fixture.closedDrawerId}`,
      `VEYRO_E2E_NO_ROTA_RESOURCE_ID=${fixture.noRotaResourceId}`,
      `VEYRO_E2E_ROTA_EXCEPTION_DAY=${fixture.rotaExceptionDay}`,
      `VEYRO_E2E_POINT_ID=${fixture.pointId}`,
      `VEYRO_E2E_PERSON_ID=${fixture.personId}`,
      `VEYRO_E2E_BUY_OUT_PERSON_ID=${fixture.buyOutPersonId}`,
      `VEYRO_E2E_HELD_TO_TERM_PERSON_ID=${fixture.heldToTermPersonId}`,
      `VEYRO_E2E_SERVED_TERM_PERSON_ID=${fixture.servedTermPersonId}`,
      `VEYRO_E2E_OVERRIDDEN_PERSON_ID=${fixture.overriddenPersonId}`,
      `VEYRO_E2E_DEVICE_ID=${fixture.deviceId}`,
      `VEYRO_E2E_PENDING_DEVICE_ID=${fixture.pendingDeviceId}`,
      `VEYRO_E2E_READER_EMAIL=${fixture.publisherEmail}`,
      `VEYRO_E2E_READER_PASSWORD=${fixture.publisherPassword}`,
      `VEYRO_E2E_DESK_EMAIL=${fixture.deskEmail}`,
      `VEYRO_E2E_DESK_PASSWORD=${fixture.deskPassword}`,
      `VEYRO_E2E_LOCATION_ID=${fixture.locationId}`,
      `VEYRO_E2E_SESSION_ID=${fixture.firstSessionId}`,
      `VEYRO_E2E_BOOKED_SESSION_ID=${fixture.bookedSessionId}`,
      `VEYRO_E2E_DESK_SESSION_ID=${fixture.deskSessionId}`,
      `VEYRO_E2E_PRODUCT_ID=${fixture.productId}`,
      `VEYRO_E2E_INVOICE_ID=${fixture.invoiceId}`,
      `VEYRO_E2E_STAFF_WORKING_PERSON_ID=${fixture.staffWorkingPersonId}`,
      `VEYRO_E2E_STAFF_ENDED_ACCESS_PERSON_ID=${fixture.staffEndedWithAccessPersonId}`,
      `VEYRO_E2E_STAFF_OFFBOARDED_PERSON_ID=${fixture.staffOffboardedPersonId}`,
      `VEYRO_E2E_STAFF_NO_LOGIN_PERSON_ID=${fixture.staffNoLoginPersonId}`,
      `VEYRO_E2E_STAFF_NEVER_SIGNED_IN_PERSON_ID=${fixture.staffNeverSignedInPersonId}`,
      "# MOD-026's three screens. `TASK_EMAIL` is the only session here whose identity is a",
      "# person, which is what makes `Mine` and `assigned to me` renderable at all.",
      `VEYRO_E2E_TASK_EMAIL=${fixture.taskEmail}`,
      `VEYRO_E2E_TASK_PASSWORD=${fixture.taskPassword}`,
      `VEYRO_E2E_DUTY_PERSON_ID=${fixture.dutyPersonId}`,
      `VEYRO_E2E_DESK_QUEUE_ID=${fixture.deskQueueId}`,
      `VEYRO_E2E_COLD_LEAD_ID=${fixture.coldLeadId}`,
      `VEYRO_E2E_OWNED_LEAD_ID=${fixture.ownedLeadId}`,
      `VEYRO_E2E_TOURED_LEAD_ID=${fixture.touredLeadId}`,
      `VEYRO_E2E_MONEY_CASE_ID=${fixture.moneyCaseId}`,
      `VEYRO_E2E_MONEY_CASE_NUMBER=${fixture.moneyCaseNumber}`,
      `VEYRO_E2E_ASSIGNED_CASE_ID=${fixture.assignedCaseId}`,
      `VEYRO_E2E_SNOOZED_CASE_ID=${fixture.snoozedCaseId}`,
      `VEYRO_E2E_SNOOZED_RETURN_ON=${fixture.snoozedReturnOn}`,
      `VEYRO_E2E_OVERDUE_TASK_ID=${fixture.overdueTaskId}`,
      `VEYRO_E2E_MINE_TASK_ID=${fixture.mineTaskId}`,
      `VEYRO_E2E_SETTLED_TASK_ID=${fixture.settledTaskId}`,
      `VEYRO_E2E_BLOCKED_TASK_ID=${fixture.blockedTaskId}`,
      "# A person can type these. Nothing in the suite uses them; they exist so the product",
      "# can be opened and looked at, which is how four of this surface's defects were found.",
      `VEYRO_E2E_EASY_EMAIL=${fixture.easyEmail}`,
      `VEYRO_E2E_EASY_PASSWORD=${fixture.easyPassword}`,
      `VEYRO_E2E_EASY_RECOVERY_CODE=${fixture.easyRecoveryCode}`,
      "",
    ].join("\n"),
    { mode: 0o600 },
  );
  // Never the password, and never the token: a fixture that printed either would put it in a
  // terminal scrollback and in whatever CI collects.
  console.log(`tenant      ${fixture.tenantId}`);
  console.log(`identity    ${fixture.identityId}`);
  console.log(`role        ${fixture.role}`);
  console.log(`permissions ${fixture.permissions}`);
  console.log(`zone        ${fixture.zoneId}`);
  console.log(`decision    ${fixture.decisionCode}`);
  console.log(`schedule    ${fixture.sessionsGenerated} sessions from one template`);
  console.log(`booking     ${fixture.bookingId === null ? "none" : "one on tomorrow's class"}`);
  // The password is printed here on purpose and the others deliberately are not: this one is
  // a constant in this file, so a terminal scrollback learns nothing it could not read.
  console.log(`sign in as  ${fixture.easyEmail} / ${fixture.easyPassword}`);
  console.log(`worker      ${fixture.workerRuns} runs, ${fixture.workerFailed} failed`);
  console.log(`credentials written to web/.env.e2e.local (mode 600)`);
}

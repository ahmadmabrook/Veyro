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
import { randomUUID } from "node:crypto";
import { existsSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { browserFingerprint } from "./device.mjs";

const api = process.env.VEYRO_API_ORIGIN ?? "http://127.0.0.1:8000";

/** A correlation id per call, so a decision here is traceable to one there. */
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
                    "scheduling.schedule.read"],
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
  // needs a hardware factor MOD-007 cannot verify, so a health note and a health custom field
  // are masked for *every* caller. Both are seeded, beside an ordinary note and an ordinary
  // tag, so a test can tell "withheld" from "absent".
  await call(`/people/${person.person_id}/member-profile`, {
    method: "POST", ...as(token),
    body: { correlation_id: cid(), lifecycle_state: "lead", member_number: "M-00042" },
  });
  await call(`/people/${person.person_id}/contacts`, {
    method: "POST", ...as(token),
    body: { kind: "email", value: "jane.member@veyro.test", is_primary: true,
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

  // **A consumer the relay can route to.** Without one the outbox is fanned out to nobody and
  // the operations board has no deliveries to show -- which hides the half of that screen
  // that is still a standing gap: a delivery is created and never handled, because no name in
  // this build has a handler behind it.
  await call("/events/subscriptions", {
    method: "POST", ...as(token),
    body: { consumer: "member_projection", event_type: "person.created",
            replay_safety: "safe", correlation_id: cid() },
  });

  // Last, so it sees everything above. The timeline, the dispatched outbox and the sweeps on
  // the operations board are all this tick's work.
  const tick = runWorkerTick(tenantId);

  return {
    templateId: template.template_id,
    sessionsGenerated: generated.created,
    firstSessionId: substituted,
    standInResourceId: standIn.resource_id,
    bookingId: booking?.booking_id ?? null,
    bookedSessionId: bookable,
    instructorResourceId: instructor.resource_id,
    workerRuns: tick.runs,
    workerFailed: tick.failed,
    deviceId: device.device_id,
    pendingDeviceId: pending.device_id,
    duplicateCandidates: candidates.length,
    twinPersonId: twin.person_id,
    publisherEmail: secondEmail,
    publisherPassword: secondPassword,
    locationId: location.location_id,
    zoneId: zone.zone_id,
    pointId: point.point_id,
    personId: person.person_id,
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
      `VEYRO_E2E_POINT_ID=${fixture.pointId}`,
      `VEYRO_E2E_PERSON_ID=${fixture.personId}`,
      `VEYRO_E2E_DEVICE_ID=${fixture.deviceId}`,
      `VEYRO_E2E_PENDING_DEVICE_ID=${fixture.pendingDeviceId}`,
      `VEYRO_E2E_READER_EMAIL=${fixture.publisherEmail}`,
      `VEYRO_E2E_READER_PASSWORD=${fixture.publisherPassword}`,
      `VEYRO_E2E_LOCATION_ID=${fixture.locationId}`,
      `VEYRO_E2E_SESSION_ID=${fixture.firstSessionId}`,
      `VEYRO_E2E_BOOKED_SESSION_ID=${fixture.bookedSessionId}`,
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
  console.log(`worker      ${fixture.workerRuns} runs, ${fixture.workerFailed} failed`);
  console.log(`credentials written to web/.env.e2e.local (mode 600)`);
}

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
                    "notifications.template.approve"],
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
    body: { contract_key: contractKey, body: "Standard membership terms.",
            correlation_id: cid() },
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
  for (const [code, kind] of [
    ["AR", "receivable"], ["BANK", "bank"], ["CASH", "cash"],
    ["CLEARING", "provider_clearing"], ["CONTRA", "contra_revenue"],
    ["FEE", "provider_fee"], ["REV", "revenue"], ["SUSPENSE", "suspense"],
    ["TAX", "tax_payable"], ["UNEARNED", "unearned_revenue"],
    ["WCASH", "wallet_cash"], ["WPROMO", "wallet_promotional"],
  ]) {
    await call("/ledger/accounts", {
      method: "POST", ...as(token),
      body: { account_code: code, account_kind: kind, display_name: code,
              currency: "JOD", correlation_id: cid() },
    });
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
  await call(`/finance/payment-intents/${intent.intent_id}/settle`, {
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
  await call("/memberships", {
    method: "POST", ...as(token),
    body: { agreement_id: expiringAgreement.agreement_id,
            membership_number: "FLEX-00107",
            idempotency_key: randomUUID(), correlation_id: cid() },
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
    deskEmail,
    deskPassword,
    easyEmail: EASY_EMAIL,
    easyPassword: EASY_PASSWORD,
    easyRecoveryCode: easyCodes.codes[0],
    publisherEmail: secondEmail,
    publisherPassword: secondPassword,
    locationId: location.location_id,
    zoneId: zone.zone_id,
    pointId: point.point_id,
    personId: person.person_id,
    membershipId: membership.membership_id,
    retiredAccountId: retiring.account_id,
    productId: product.product_id,
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
      `VEYRO_E2E_POINT_ID=${fixture.pointId}`,
      `VEYRO_E2E_PERSON_ID=${fixture.personId}`,
      `VEYRO_E2E_DEVICE_ID=${fixture.deviceId}`,
      `VEYRO_E2E_PENDING_DEVICE_ID=${fixture.pendingDeviceId}`,
      `VEYRO_E2E_READER_EMAIL=${fixture.publisherEmail}`,
      `VEYRO_E2E_READER_PASSWORD=${fixture.publisherPassword}`,
      `VEYRO_E2E_DESK_EMAIL=${fixture.deskEmail}`,
      `VEYRO_E2E_DESK_PASSWORD=${fixture.deskPassword}`,
      `VEYRO_E2E_LOCATION_ID=${fixture.locationId}`,
      `VEYRO_E2E_SESSION_ID=${fixture.firstSessionId}`,
      `VEYRO_E2E_BOOKED_SESSION_ID=${fixture.bookedSessionId}`,
      `VEYRO_E2E_PRODUCT_ID=${fixture.productId}`,
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

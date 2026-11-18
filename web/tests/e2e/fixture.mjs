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

import { randomUUID } from "node:crypto";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const api = process.env.VEYRO_API_ORIGIN ?? "http://127.0.0.1:8000";

/** A correlation id per call, so a decision here is traceable to one there. */
function cid() {
  return randomUUID();
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

  return {
    tenantId,
    identityId: identity.identity_id ?? identity.id,
    email,
    password,
    role: bootstrapped.role_key ?? "tenant_admin",
    permissions: bootstrapped.permissions?.length ?? null,
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
  console.log(`credentials written to web/.env.e2e.local (mode 600)`);
}

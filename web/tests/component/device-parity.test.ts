import { describe, expect, it } from "vitest";

import { browserFingerprint } from "@/lib/device";
// A plain-JavaScript module with no type declarations, which is the point: the fixture runs
// on bare Node with no build step, so its copy of the formula has to be ordinary JavaScript.
import { browserFingerprint as fixtureFingerprint } from "../e2e/device.mjs";

/**
 * The app's device label and the fixture's are one formula, and this is what says so.
 *
 * **Why it matters more than it looks.** MOD-007 confirms a device the first time a login
 * from it is challenged and answered, so the fixture confirms the browser's device by
 * logging in *as that device* -- which it can only do by computing the same label the app
 * sends. If the two drift, the fixture confirms a device nothing uses, every browser sign-in
 * is challenged, and the suite spends a single-use recovery code per run: green on the first
 * run against a fresh fixture and red on every one after it. That is exactly the failure
 * this test was written after.
 */
describe("the web app's device label", () => {
  const vectors: [string, string][] = [
    ["11111111-1111-4111-8111-111111111111", "jane@example.test"],
    ["7b6f7262-391f-4773-9039-45d81fe988aa", "owner+e2e@veyro.test"],
    ["00000000-0000-4000-8000-000000000000", "+962790000000"],
    ["11111111-1111-4111-8111-111111111111", "JANE@EXAMPLE.TEST"],
  ];

  it("is the same in the app and in the browser fixture", () => {
    for (const [tenant, identifier] of vectors) {
      expect(fixtureFingerprint(tenant, identifier)).toBe(
        browserFingerprint(tenant, identifier),
      );
    }
  });

  it("is stable, scoped to the tenant and the identifier, and says what it is", () => {
    const [tenant, identifier] = vectors[0]!;
    const [otherTenant, otherIdentifier] = vectors[1]!;
    const first = browserFingerprint(tenant, identifier);
    expect(browserFingerprint(tenant, identifier)).toBe(first);
    expect(first).toMatch(/^web:[0-9a-f]{32}$/);
    // A different tenant is a different device, which is what stops one tenant's confirmed
    // device vouching for a sign-in in another.
    expect(browserFingerprint(otherTenant, identifier)).not.toBe(first);
    expect(browserFingerprint(tenant, otherIdentifier)).not.toBe(first);
  });
});

import { createHash } from "node:crypto";

/**
 * A stable per-(tenant, identifier) label for this app, for MOD-007's device inventory.
 *
 * **Not a measurement, and not a browser fingerprint in the tracking sense.** This app reads
 * nothing about the reader's machine: it derives a value from what the sign-in already
 * carries, so the same person signing in from this app twice is one device to MOD-007 and
 * somebody signing in from the mobile app is another. A random value per attempt -- which is
 * what the first version sent -- makes every sign-in a new device and challenges every one.
 *
 * **It lives here rather than beside the sign-in action because the browser test fixture has
 * to produce the same value.** MOD-007 confirms a device the first time a login from it is
 * challenged and answered, and a recovery code is single-use -- so a suite that spends one
 * per run passes only on the run that happens to find an unspent code, which is what it did:
 * a second Playwright run against one fixture failed every signing-in test. The fixture now
 * confirms this device itself, which needs this formula, and
 * `tests/component/device-parity.test.ts` is what keeps the two spellings identical.
 */
export function browserFingerprint(tenantId: string, identifier: string): string {
  return `web:${createHash("sha256").update(`${tenantId}:${identifier}`).digest("hex").slice(0, 32)}`;
}

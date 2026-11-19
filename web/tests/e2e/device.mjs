import { createHash } from "node:crypto";

/**
 * The web app's device label, in plain JavaScript so the fixture can produce it.
 *
 * `src/lib/device.ts` is the one the app uses and the comment there says why this exists.
 * Two spellings of one formula drift, so `tests/component/device-parity.test.ts` runs both
 * over a vector set and compares -- the same trade as `conventions-parity.test.mjs`, which
 * spawns Python to compare this app's formatting against the backend's.
 */
export function browserFingerprint(tenantId, identifier) {
  return `web:${createHash("sha256").update(`${tenantId}:${identifier}`).digest("hex").slice(0, 32)}`;
}

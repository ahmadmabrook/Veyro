import { expect, type Page } from "@playwright/test";

import { fixture } from "./fixture-env";

/**
 * Stepping up, for the specs that need a level-2 session rather than a step-up to test.
 *
 * **Extracted when ADM-MSH-03 needed it**, because a second copy of this is a second
 * definition of how a step-up works, and the day they disagree nobody can say which is the
 * flow. `step-up.spec.ts` tests the screen; this is for every other spec that has to get
 * past it.
 */

/**
 * A recovery code nobody has spent.
 *
 * **A step-up spends one**, and a spec that used a code from the fixture would pass on the
 * first run against a fresh fixture and fail on every one after it -- the exact trap
 * `auth.setup.ts` closes one layer up. Minting is what an operator does, it needs only the
 * password this session already proved, and it makes the spec re-runnable.
 */
export async function freshRecoveryCode(page: Page): Promise<string> {
  const creds = fixture();
  const cookies = await page.context().cookies();
  const token = cookies.find((cookie) => cookie.name === "veyro_session")?.value;
  expect(token, "signed in, so there is a session cookie to use as a bearer token").toBeTruthy();

  const api = process.env.VEYRO_API_ORIGIN ?? "http://127.0.0.1:8000";
  const response = await page.request.post(
    `${api}/identities/${creds.identityId}/recovery-codes`,
    {
      headers: {
        "X-Veyro-Tenant": creds.tenantId,
        Authorization: `Bearer ${token}`,
        "content-type": "application/json",
      },
      data: { correlation_id: crypto.randomUUID(), current_password: creds.password },
    },
  );
  expect(response.status(), await response.text()).toBe(201);
  const body = (await response.json()) as { codes: string[] };
  return body.codes[0]!;
}

/**
 * Complete a step-up that is already on screen, and return to where it came from.
 *
 * The caller has followed a page's own offer, so the `next` is already set; this fills the
 * one credential a password session can present and confirms. A password cannot raise a
 * password session -- two passwords are one kind -- which is why it is a recovery code.
 */
export async function stepUp(page: Page): Promise<void> {
  const code = await freshRecoveryCode(page);
  await page.getByLabel("Recovery code").fill(code);
  await page.getByRole("button", { name: "Confirm" }).click();
  await page.waitForLoadState("networkidle");
}

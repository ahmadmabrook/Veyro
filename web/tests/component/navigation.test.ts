import { describe, expect, it } from "vitest";

import { HOME, safeNext } from "@/lib/navigation";

/**
 * The open-redirect guard, tested where the decision is made.
 *
 * **`next` arrives in a link, which is the one thing a reader can be handed**, and the two
 * places this product reads it are sign-in and step-up -- the two pages where somebody has
 * just typed a credential, which is exactly where a redirect to a lookalike host is worth the
 * most. Each refusal below is a real bypass of a naive `startsWith("/")` check rather than a
 * hypothetical one.
 */
describe("where a flow may send the reader back to", () => {
  it("keeps an ordinary same-origin path, with its query and fragment", () => {
    expect(safeNext("/people/abc")).toBe("/people/abc");
    expect(safeNext("/access?zone=1")).toBe("/access?zone=1");
    expect(safeNext("/organization#brands")).toBe("/organization#brands");
    expect(safeNext("/")).toBe("/");
  });

  it("refuses the four shapes that leave this origin", () => {
    // Protocol-relative: a browser reads this as another host, and it starts with a slash.
    expect(safeNext("//evil.test")).toBe(HOME);
    expect(safeNext("//evil.test/people")).toBe(HOME);
    // The same trick with a backslash, which browsers normalise to a slash.
    expect(safeNext("/\\evil.test")).toBe(HOME);
    expect(safeNext("/\\\\evil.test")).toBe(HOME);
    // An absolute URL, with and without a leading slash to sneak past the first rule.
    expect(safeNext("https://evil.test")).toBe(HOME);
    expect(safeNext("/https://evil.test")).toBe(HOME);
    expect(safeNext("javascript:alert(1)")).toBe(HOME);
  });

  it("refuses a control character, which is how a second location gets smuggled", () => {
    expect(safeNext("/people\nLocation: https://evil.test")).toBe(HOME);
    expect(safeNext("/people\r\nSet-Cookie: a=b")).toBe(HOME);
    expect(safeNext("/people\u0000")).toBe(HOME);
  });

  it("falls back rather than failing, for everything that is not a path", () => {
    expect(safeNext(null)).toBe(HOME);
    expect(safeNext(undefined)).toBe(HOME);
    expect(safeNext("")).toBe(HOME);
    expect(safeNext("   ")).toBe(HOME);
    expect(safeNext("people")).toBe(HOME);
    // Long enough to be a payload rather than a path.
    expect(safeNext(`/${"a".repeat(600)}`)).toBe(HOME);
  });
});

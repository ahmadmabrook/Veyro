import { describe, expect, it } from "vitest";

import {
  assuranceMeans,
  currentDeviceId,
  mayIssueRecoveryCodes,
  needsAttention,
  sessionIsLive,
  type DeviceFact,
  type SessionFact,
} from "@/lib/account";

/**
 * MOD-007's account decisions, tested where they are made.
 *
 * **`mayIssueRecoveryCodes` is the one with teeth.** Minting codes takes the current password
 * or a stepped-up session and nothing else -- deliberately *not* the recovery allowance that
 * `set_password` has, because MOD-007's second review found a stolen recovery session minting
 * ten fresh codes with no password, and those codes surviving the owner's own password reset.
 * A page offering the button to a level-1 session would be offering an action the server
 * refuses.
 *
 * **These functions live apart from the fetchers**, which is not tidiness: the account page is
 * the first client component in this app, and a client component importing a module that
 * reaches `next/headers` fails the build outright. The split is the one the backend makes
 * between `domain` and `service`.
 */

function session(over: Partial<SessionFact>): SessionFact {
  return {
    session_id: "s1",
    device_id: "d1",
    aal: 1,
    factors: ["password"],
    issued_at: "2026-11-20T00:00:00+00:00",
    expires_at: "2026-12-04T00:00:00+00:00",
    last_seen_at: "2026-11-20T01:00:00+00:00",
    revoked_at: null,
    revoke_reason: null,
    ...over,
  };
}

function device(over: Partial<DeviceFact>): DeviceFact {
  return {
    device_id: "d1",
    label: "Veyro web",
    platform: null,
    trusted: false,
    confirmed: true,
    first_seen_at: "2026-11-01T00:00:00+00:00",
    last_seen_at: "2026-11-20T00:00:00+00:00",
    revoked_at: null,
    revoked_reason: null,
    ...over,
  };
}

describe("mayIssueRecoveryCodes", () => {
  it("needs a stepped-up session, not a signed-in one", () => {
    expect(mayIssueRecoveryCodes(1)).toBe(false);
    expect(mayIssueRecoveryCodes(2)).toBe(true);
    expect(mayIssueRecoveryCodes(3)).toBe(true);
  });
});

describe("assuranceMeans", () => {
  it("says what a level lets you do, not what number it is", () => {
    expect(assuranceMeans(1)).toBe("password");
    expect(assuranceMeans(2)).toBe("stepped_up");
  });

  it("calls level three unreachable, because nothing here reaches it", () => {
    // It needs a hardware authenticator MOD-007 cannot verify. Rendering it as a level a
    // reader might aim for would send them looking for a key the product cannot check.
    expect(assuranceMeans(3)).toBe("unreachable");
  });
});

describe("sessionIsLive", () => {
  it("needs both: not revoked, and not expired", () => {
    const now = "2026-11-20T12:00:00+00:00";
    expect(sessionIsLive(session({}), now)).toBe(true);
    expect(sessionIsLive(session({ revoked_at: "2026-11-20T06:00:00+00:00" }), now))
      .toBe(false);
    // A board showing only the revoked flag would list a fortnight-old session as live.
    expect(sessionIsLive(session({ expires_at: "2026-11-19T00:00:00+00:00" }), now))
      .toBe(false);
  });

  it("compares ISO strings, which is chronological for UTC instants", () => {
    // Both sides are ISO-8601 in UTC, so lexical order is chronological -- which avoids the
    // browser answering a timezone question differently from the server that issued it.
    expect(
      sessionIsLive(
        session({ expires_at: "2026-12-04T00:00:00+00:00" }),
        "2026-12-03T23:59:59+00:00",
      ),
    ).toBe(true);
  });
});

describe("needsAttention", () => {
  it("is an unconfirmed device that is still live", () => {
    expect(needsAttention(device({ confirmed: false }))).toBe(true);
    expect(needsAttention(device({ confirmed: true }))).toBe(false);
    // A revoked device needs nothing: it was already dealt with.
    expect(
      needsAttention(device({ confirmed: false, revoked_at: "2026-11-19T00:00:00+00:00" })),
    ).toBe(false);
  });
});

describe("the device this session came from", () => {
  const session = (id: string, deviceId: string | null) => ({
    session_id: id, device_id: deviceId, aal: 1, factors: ["password"],
    issued_at: "2026-11-20T08:00:00Z", expires_at: "2026-12-04T08:00:00Z",
    last_seen_at: null, revoked_at: null, revoke_reason: null,
  });

  it("is found by the session id, not by being the newest row", () => {
    const sessions = [session("s-new", "d-other"), session("s-mine", "d-mine")];
    expect(currentDeviceId(sessions, "s-mine")).toBe("d-mine");
  });

  it("is null when the session is not on the bounded, live-only list", () => {
    expect(currentDeviceId([session("s-other", "d-other")], "s-mine")).toBeNull();
  });

  it("is null when the session carries no device, rather than guessing one", () => {
    expect(currentDeviceId([session("s-mine", null)], "s-mine")).toBeNull();
  });
});

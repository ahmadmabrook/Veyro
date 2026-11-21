import { describe, expect, it } from "vitest";

import { MESSAGES } from "@/i18n/locale";
import type { Assignment, CatalogPermission, Role } from "@/lib/authz";
import {
  grantReach,
  keysInPlay,
  reachOf,
  scopesToSimulate,
  sensitiveGrants,
  splitRole,
  standingName,
  standingOf,
  standingSeverity,
  stateName,
  type LastSeen,
} from "@/lib/staff";

/**
 * ADM-STF-01 and ADM-STF-02's judgements, tested where they are made.
 *
 * **`standingOf` has six answers and a fixture renders two of them.** That is the
 * surface-branch vacuity this repository has shipped four times — a branch with an assertion
 * written for it that never runs, because the data to reach it does not exist. So the
 * classification is a function, and the two that matter most are provable here: `unknown`,
 * which must not read as "no access", and `endedWithAccess`, which is the finding the whole
 * screen leads with.
 */

function row(over: Partial<{ employment_state: string; identity_id: string | null }> = {}) {
  return { employment_state: "active", identity_id: "id-1", ...over };
}

function seen(over: Partial<LastSeen> = {}): LastSeen {
  return {
    identity_id: "id-1", status: "active", last_seen_at: "2026-11-20T08:00:00+00:00",
    live_sessions: 1, no_device_or_address_is_returned: "", ...over,
  };
}

function assignment(over: Partial<Assignment> = {}): Assignment {
  return {
    assignment_id: "a-1", role_key: "reception", display_name: "Reception",
    scope_type: "tenant", brand_id: null, location_id: null,
    granted_at: "2026-01-02T00:00:00+00:00", expires_at: null,
    revoked_at: null, revoked_reason: null, granted_by: "granter-1", live: true, ...over,
  };
}

const TENANT = { key: "tenant", kind: "tenant", id: null } as const;
const SITE = { key: "location:loc-1", kind: "location", id: "loc-1" } as const;

function permission(over: Partial<CatalogPermission> = {}): CatalogPermission {
  return {
    name: "finance.refund.approve", description: "Approve a member refund",
    category: "financial", action_class: "financial", required_aal: 2, ...over,
  };
}

describe("where a staff member stands", () => {
  it("is working when they are employed, have a login and have used it", () => {
    expect(standingOf(row(), seen())).toBe("working");
  });

  it("tells a stalled onboarding from a working account", () => {
    // A column showing only a date cannot: both are blank-ish, and one of them is somebody
    // who cannot do their job.
    expect(standingOf(row(), seen({ last_seen_at: null })))
      .toBe("workingNeverUsed");
    expect(standingSeverity("workingNeverUsed")).toBe("attention");
  });

  it("does not call an employee with no login a fault", () => {
    // A cleaner on the payroll needs no account, and `ppl_identity_links` is the only thing
    // relating the two planes. This is knowable without the identity permission.
    expect(standingOf(row({ identity_id: null }), null)).toBe("workingNoLogin");
    expect(standingSeverity("workingNoLogin")).toBeNull();
  });

  it("finds the departed employee who can still sign in, which is the point", () => {
    // The design's own sentence: "Last seen exists so a departed employee with a live login
    // is visible rather than discovered."
    expect(standingOf(row({ employment_state: "ended" }), seen()))
      .toBe("endedWithAccess");
    expect(standingSeverity("endedWithAccess")).toBe("critical");
  });

  it("counts an active identity as access even with no live session", () => {
    // A revoked session is not a revoked account: the password still works, so the next sign
    // in opens the product. Reading only `live_sessions` would call that clean.
    expect(standingOf(row({ employment_state: "ended" }),
                      seen({ live_sessions: 0, status: "active" })))
      .toBe("endedWithAccess");
  });

  it("calls a properly offboarded leaver ended, and that is the only clean exit", () => {
    expect(standingOf(row({ employment_state: "ended" }),
                      seen({ live_sessions: 0, status: "suspended" })))
      .toBe("ended");
    expect(standingSeverity("ended")).toBeNull();
  });

  it("says nobody has checked rather than saying there is no access", () => {
    // **The important one, and it is one guard rather than two.** A reader holding
    // `people.person.read` and not `identity.identity.read` passes no `seen` at all, and so
    // does a permitted read that came back with nothing -- `ppl_identity_links` carries no
    // foreign key into `iam`, so a stale link answers nothing. Both are "nobody looked",
    // which is what must not be rendered as "checked and clean".
    //
    // The first version took a `mayReadLogins` flag as well and the mutation sweep showed
    // its branch was unreachable: deleting it left the suite green, because the `seen ===
    // null` line below already answered. Subsumed, so deleted.
    expect(standingOf(row({ employment_state: "ended" }), null)).toBe("unknown");
    expect(standingOf(row(), null)).toBe("unknown");
  });

  it("treats suspended employment as still employed, because access is the question", () => {
    expect(standingOf(row({ employment_state: "suspended" }), seen())).toBe("working");
  });
});

describe("which assignment is the job", () => {
  it("is the broadest scope, because the job is the widest thing somebody was hired for", () => {
    const { primary, beyond } = splitRole([
      assignment({ assignment_id: "a-narrow", role_key: "till", scope_type: "location",
                   location_id: "loc-1" }),
      assignment({ assignment_id: "a-wide", role_key: "reception", scope_type: "tenant" }),
    ]);
    expect(primary?.role_key).toBe("reception");
    expect(beyond.map((one) => one.role_key)).toEqual(["till"]);
  });

  it("breaks a tie on when it was granted, then on the id, so the order is total", () => {
    // An unordered answer makes the planner the author and the screen's two halves change
    // between reads, which is MOD-018's `chart_for` finding in a surface.
    const first = assignment({
      assignment_id: "bbb", role_key: "early", granted_at: "2026-01-01T00:00:00+00:00" });
    const second = assignment({
      assignment_id: "aaa", role_key: "late", granted_at: "2026-02-01T00:00:00+00:00" });
    expect(splitRole([second, first]).primary?.role_key).toBe("early");
    const sameInstant = [
      assignment({ assignment_id: "zzz", role_key: "zed" }),
      assignment({ assignment_id: "aaa", role_key: "alpha" }),
    ];
    expect(splitRole(sameInstant).primary?.role_key).toBe("alpha");
    expect(splitRole([...sameInstant].reverse()).primary?.role_key).toBe("alpha");
  });

  it("puts a revoked or expired assignment in neither half", () => {
    const { primary, beyond, lapsed } = splitRole([
      assignment({ assignment_id: "gone", role_key: "old", live: false,
                   revoked_at: "2026-05-05T00:00:00+00:00" }),
      assignment({ assignment_id: "now", role_key: "current" }),
    ]);
    expect(primary?.role_key).toBe("current");
    expect(beyond).toEqual([]);
    expect(lapsed.map((one) => one.role_key)).toEqual(["old"]);
  });

  it("has no primary when nothing is live, which is a real state", () => {
    const { primary, lapsed } = splitRole([assignment({ live: false })]);
    expect(primary).toBeNull();
    expect(lapsed).toHaveLength(1);
  });
});

describe("where a role reaches", () => {
  it("is every club when any live assignment is tenant-scoped", () => {
    // A chip list beside a tenant-wide grant would understate it: the wide one already
    // covers the named ones.
    expect(reachOf([
      assignment({ scope_type: "location", location_id: "loc-1" }),
      assignment({ assignment_id: "a-2", scope_type: "tenant" }),
    ])).toEqual({ kind: "tenant" });
  });

  it("is the named scopes otherwise, deduplicated and ordered", () => {
    expect(reachOf([
      assignment({ assignment_id: "a-1", scope_type: "location", location_id: "loc-b" }),
      assignment({ assignment_id: "a-2", scope_type: "location", location_id: "loc-a" }),
      assignment({ assignment_id: "a-3", scope_type: "location", location_id: "loc-a" }),
      assignment({ assignment_id: "a-4", scope_type: "brand", brand_id: "br-1" }),
    ])).toEqual({ kind: "named", brands: ["br-1"], locations: ["loc-a", "loc-b"] });
  });

  it("is nothing when every assignment has lapsed", () => {
    expect(reachOf([assignment({ live: false })])).toEqual({ kind: "none" });
    expect(reachOf([])).toEqual({ kind: "none" });
  });
});

describe("which scopes the simulator has to be asked about", () => {
  it("is every distinct live scope, tenant first", () => {
    // **Asking only about the default scope hides every narrow grant**, because a broad
    // assignment covers a narrow scope and never the reverse -- and a narrow grant is what
    // "beyond their role" usually is. Found by reading the rendered page: the fixture's own
    // location-scoped refund grant was missing from the block that exists to show it.
    expect(scopesToSimulate([
      assignment({ assignment_id: "a-1", scope_type: "location", location_id: "loc-b" }),
      assignment({ assignment_id: "a-2", scope_type: "tenant" }),
      assignment({ assignment_id: "a-3", scope_type: "location", location_id: "loc-a" }),
      assignment({ assignment_id: "a-4", scope_type: "brand", brand_id: "br-1" }),
    ]).map((one) => one.key))
      .toEqual(["tenant", "brand:br-1", "location:loc-a", "location:loc-b"]);
  });

  it("deduplicates, so two roles at one site are asked once", () => {
    expect(scopesToSimulate([
      assignment({ assignment_id: "a-1", scope_type: "location", location_id: "loc-a" }),
      assignment({ assignment_id: "a-2", scope_type: "location", location_id: "loc-a" }),
    ])).toHaveLength(1);
  });

  it("asks about nothing when every assignment has lapsed", () => {
    expect(scopesToSimulate([assignment({ live: false })])).toEqual([]);
  });
});

describe("what somebody can do that is dangerous", () => {
  const catalog = [
    permission(),
    permission({ name: "people.person.read", description: "See a person",
                 action_class: "routine", required_aal: 1 }),
    permission({ name: "support.breakglass.use", description: "Break-glass support access",
                 action_class: "privileged", required_aal: 3 }),
  ];
  const roles: Role[] = [
    { role_id: "r-1", role_key: "reception", display_name: "Reception", description: null,
      builtin: false, version: 1,
      permissions: ["people.person.read", "finance.refund.approve"] },
    { role_id: "r-2", role_key: "support", display_name: "Support", description: null,
      builtin: false, version: 1, permissions: ["support.breakglass.use"] },
  ];

  it("is the financial and privileged classes, which is the catalogue's own judgement", () => {
    const grants = sensitiveGrants(
      [{ scope: TENANT, permissions: ["people.person.read", "finance.refund.approve"] }],
      catalog, 2, [assignment()], roles);
    expect(grants.map((one) => one.permission.name)).toEqual(["finance.refund.approve"]);
    expect(grants[0]!.reach).toBe("needsStepUp");
  });

  it("names the role that carries it, which is the design's attribution line", () => {
    const grants = sensitiveGrants(
      [{ scope: TENANT, permissions: ["finance.refund.approve"] }],
      catalog, 2, [assignment()], roles);
    expect(grants[0]!.carriers.map((one) => one.role_key)).toEqual(["reception"]);
  });

  it("does not credit a lapsed assignment with carrying anything", () => {
    const grants = sensitiveGrants(
      [{ scope: TENANT, permissions: ["finance.refund.approve"] }], catalog, 2,
      [assignment({ live: false, revoked_at: "2026-05-05T00:00:00+00:00" })], roles);
    expect(grants[0]!.carriers).toEqual([]);
  });

  it("marks a permission nobody in this build can use, rather than drawing it as held", () => {
    // AAL 3 needs a hardware authenticator MOD-007 cannot verify, so break-glass support
    // access is granted, recorded and exercisable by nobody. Drawing it as held would say
    // somebody can do something no session can.
    const grants = sensitiveGrants(
      [{ scope: TENANT, permissions: ["support.breakglass.use"] }], catalog, 2,
      [assignment({ role_key: "support", display_name: "Support" })], roles);
    expect(grants[0]!.reach).toBe("unreachable");
    expect(grantReach(permission({ required_aal: 3 }), 3)).toBe("needsStepUp");
    expect(grantReach(permission({ required_aal: 1 }), 2)).toBe("usable");
  });

  it("sees a grant held only at one site, which asking once could not", () => {
    // The defect this signature exists for. A location-scoped assignment contributes nothing
    // at the tenant-wide default scope, so the permission it carries was simply absent.
    const grants = sensitiveGrants(
      [
        { scope: TENANT, permissions: ["people.person.read"] },
        { scope: SITE, permissions: ["people.person.read", "finance.refund.approve"] },
      ],
      catalog, 2, [assignment({ scope_type: "location", location_id: "loc-1" })], roles);
    expect(grants.map((one) => one.permission.name)).toEqual(["finance.refund.approve"]);
    expect(grants[0]!.scopes.map((one) => one.key)).toEqual(["location:loc-1"]);
  });

  it("says a tenant-wide grant applies everywhere rather than listing sites", () => {
    const grants = sensitiveGrants(
      [
        { scope: TENANT, permissions: ["finance.refund.approve"] },
        { scope: SITE, permissions: ["finance.refund.approve"] },
      ],
      catalog, 2, [assignment()], roles);
    expect(grants[0]!.scopes.map((one) => one.kind)).toContain("tenant");
  });

  it("is ordered by name, so two reads of one record agree", () => {
    const grants = sensitiveGrants(
      [{ scope: TENANT, permissions: ["support.breakglass.use", "finance.refund.approve"] }],
      catalog, 3, [assignment()], roles);
    expect(grants.map((one) => one.permission.name))
      .toEqual(["finance.refund.approve", "support.breakglass.use"]);
  });
});

describe("the vocabularies, from the side the parity check cannot see", () => {
  it("maps every employment state rather than leaking the column value", () => {
    for (const state of ["active", "suspended", "ended"]) {
      expect(stateName(state)).not.toBeNull();
    }
    // An unknown value falls through to its raw form rather than to "other": the set is the
    // schema's and this is a screen somebody filters and acts on.
    expect(stateName("invited")).toBeNull();
  });

  it("has every key this module maps to in both locales", () => {
    for (const key of keysInPlay()) {
      expect(MESSAGES.en, `en is missing ${key}`).toHaveProperty(key);
      expect(MESSAGES.ar, `ar is missing ${key}`).toHaveProperty(key);
    }
  });

  it("names a standing for each of the six, with no gaps", () => {
    const names = new Set([
      "working", "workingNeverUsed", "workingNoLogin", "endedWithAccess", "ended", "unknown",
    ].map((one) => standingName(one as never)));
    expect(names.size).toBe(6);
  });
});

import { describe, expect, it } from "vitest";

import {
  flagReason,
  isUnset,
  type FlagDecision,
  type ResolvedValue,
} from "@/lib/configuration";

/**
 * The two distinctions MOD-005's board rests on, tested where they are decided.
 *
 * **`off` is four different facts** and the variant carries none of them. A kill switch
 * somebody engaged, a flag nobody enabled, a targeting rule that sent this subject to the
 * control arm, and no rule matching at all have four different next actions.
 *
 * **A default is not a setting.** An unset key reads back as its own default, which is
 * indistinguishable from a tenant that published the same value on purpose unless the scope
 * is read -- so the scope is the fact, not the value.
 */

function decision(reason: string): FlagDecision {
  return { variant: "off", reason, version: 3 };
}

describe("why a flag resolved as it did", () => {
  it("tells a kill switch from a flag nobody enabled", () => {
    // A kill switch outranks every rule and is somebody's deliberate stop; `disabled` is a
    // flag that was never turned on. The same variant, two different next actions.
    expect(flagReason(decision("kill_switch"))).toBe("kill_switch");
    expect(flagReason(decision("disabled"))).toBe("disabled");
  });

  it("reduces a rule to the fact that a rule matched", () => {
    // `rule:0f3a…` tells a reader nothing. The id stays in the data for whoever is debugging.
    expect(flagReason(decision("rule:0f3ac6b2-1111-4111-8111-111111111111"))).toBe("rule");
    expect(flagReason(decision("rule:anything"))).toBe("rule");
  });

  it("treats a reason it does not recognise as the default", () => {
    // The evaluator's four reasons are the whole set today. A fifth would land here rather
    // than rendering an empty cell, which is the failure a reader cannot interpret at all.
    expect(flagReason(decision("default"))).toBe("default");
    expect(flagReason(decision("something_new"))).toBe("default");
  });
});

describe("a configured value", () => {
  const resolved = (scope: string, version: number | null): ResolvedValue => ({
    value: 72,
    scope_type: scope,
    version,
  });

  it("is unset only when nothing was published for it", () => {
    expect(isUnset(resolved("default", null))).toBe(true);
    expect(isUnset(resolved("tenant", 1))).toBe(false);
    expect(isUnset(resolved("brand", 4))).toBe(false);
    expect(isUnset(resolved("location", 2))).toBe(false);
  });
});

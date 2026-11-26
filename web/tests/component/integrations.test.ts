import { describe, expect, it } from "vitest";

import { t } from "@/i18n/locale";

import {
  OBLIGED_CRITICALITY,
  credentialIsCurrent,
  missingObligations,
  needsSomebody,
  obligationsApply,
  obligationsMet,
  reportedNotObserved,
  type ConnectorRun,
  type CredentialRef,
  type Install,
} from "@/lib/integrations";

/**
 * MOD-012's judgements, tested where they are made -- and two of these exist because the
 * board shipped them wrong and looking at it found them.
 *
 * **The obligations were keyed on a value the column never holds.** `live_critical` is how
 * the prose names it; `int_installs.criticality` is one of `convenience`, `important`,
 * `critical`, and `lifecycle.py` compares against the last. So the check matched nothing and
 * every install reported "not required at this criticality" -- a control keyed on a value
 * that never occurs, which is the shape `CLAUDE.md` records across five modules.
 *
 * **And the comparison was written twice.** The page re-derived it inline for its own cell
 * while the library answered the banner, so fixing one left the other wrong: the banner
 * correctly named an install carrying traffic without its obligations while the row beside it
 * said they did not apply. `obligationsApply` is exported so there is one definition.
 */

function install(over: Partial<Install>): Install {
  return {
    install_id: "i1",
    definition_key: "acme.ledger",
    definition_version: 1,
    criticality: "critical",
    state: "active",
    config: {},
    has_fallback: true,
    has_reconciliation: true,
    has_exit_plan: true,
    installed_at: "2026-11-01T00:00:00+00:00",
    uninstalled_at: null,
    ...over,
  };
}

function run(over: Partial<ConnectorRun>): ConnectorRun {
  return {
    run_id: "r1",
    connection_id: "c1",
    resource: "members",
    status: "succeeded",
    attempts: 1,
    max_attempts: 5,
    records_read: 0,
    records_written: 0,
    conflicts: 0,
    last_error: null,
    next_attempt_at: null,
    started_at: "2026-11-20T00:00:00+00:00",
    finished_at: "2026-11-20T00:01:00+00:00",
    ...over,
  };
}

function credential(over: Partial<CredentialRef>): CredentialRef {
  return {
    credential_ref_id: "k1",
    connection_id: "c1",
    vault_ref: "vault://veyro/local/acme",
    scopes: ["members.read"],
    issued_at: "2026-11-01T00:00:00+00:00",
    expires_at: null,
    retired_at: null,
    supersedes: null,
    ...over,
  };
}

describe("obligationsApply", () => {
  it("is the value the column actually holds, not the one the prose uses", () => {
    // The regression this test exists for: `live_critical` matched nothing.
    expect(OBLIGED_CRITICALITY).toBe("critical");
    expect(obligationsApply(install({ criticality: "critical" }))).toBe(true);
    expect(obligationsApply(install({ criticality: "important" }))).toBe(false);
    expect(obligationsApply(install({ criticality: "convenience" }))).toBe(false);
    // And the value that caused the defect binds nothing, which is the point.
    expect(obligationsApply(install({ criticality: "live_critical" }))).toBe(false);
  });
});

describe("obligationsMet", () => {
  it("needs all three on a critical install", () => {
    expect(obligationsMet(install({}))).toBe(true);
    expect(obligationsMet(install({ has_exit_plan: false }))).toBe(false);
    expect(obligationsMet(install({ has_fallback: false }))).toBe(false);
    expect(obligationsMet(install({ has_reconciliation: false }))).toBe(false);
  });

  it("asks nothing of an install the obligations do not bind", () => {
    expect(
      obligationsMet(install({
        criticality: "important", has_fallback: false,
        has_reconciliation: false, has_exit_plan: false,
      })),
    ).toBe(true);
  });

  it("names which obligation is missing, not merely that one is", () => {
    // "A written obligation is missing" in a list of three sends somebody reading all three.
    // **The list returns message keys now**, because the three names are this app's own and
    // `exit_plan` reaching a screen was it naming its own field at a reader. The property is
    // unchanged -- which obligation, in order -- and the keys are asserted to exist, so a
    // renamed key fails here rather than rendering as a blank.
    expect(missingObligations(install({ has_exit_plan: false })))
      .toEqual(["integrations.obligationExitPlan"]);
    expect(
      missingObligations(install({ has_fallback: false, has_exit_plan: false })),
    ).toEqual(["integrations.obligationFallback", "integrations.obligationExitPlan"]);
    expect(missingObligations(install({ criticality: "important", has_fallback: false })))
      .toEqual([]);
    for (const key of missingObligations(install({
      has_fallback: false, has_reconciliation: false, has_exit_plan: false,
    }))) {
      expect(t("en", key).length).toBeGreaterThan(3);
      expect(t("ar", key).length).toBeGreaterThan(3);
    }
  });
});

describe("credentialIsCurrent", () => {
  it("is the retirement and nothing else", () => {
    // A rotation is a new row superseding the old one, so a board showing every row without
    // saying which is current shows a history as though it were a state.
    expect(credentialIsCurrent(credential({}))).toBe(true);
    expect(
      credentialIsCurrent(credential({ retired_at: "2026-11-10T00:00:00+00:00" })),
    ).toBe(false);
  });
});

describe("needsSomebody", () => {
  it("is dead and not merely failed", () => {
    // A failed run retries itself; a dead one burned its budget and needs an attributed
    // release before it goes back in front of a provider.
    expect(needsSomebody(run({ status: "dead" }))).toBe(true);
    expect(needsSomebody(run({ status: "failed" }))).toBe(false);
    expect(needsSomebody(run({ status: "running" }))).toBe(false);
  });
});

describe("reportedNotObserved", () => {
  it("is true as soon as a run claims it moved anything", () => {
    // Nothing in this build calls a provider, so these counts are a caller's word. The
    // caveat renders exactly where a number would otherwise read as data that moved.
    expect(reportedNotObserved(run({ records_read: 120 }))).toBe(true);
    expect(reportedNotObserved(run({ records_written: 1 }))).toBe(true);
    expect(reportedNotObserved(run({}))).toBe(false);
  });
});

import { describe, expect, it } from "vitest";

import { MESSAGES } from "@/i18n/locale";
import {
  headlineDays, planChoice, startedNow, type TrialPlan, type TrialSteps,
} from "@/lib/walk-in-trial";

/**
 * FD-05's own decisions. The duplicate check is `@/lib/walk-in`'s and tested there; what is
 * here is the trial plan and what to say about a press.
 *
 * **Decisions rather than a rendered branch**, which this repository has a rule for: a
 * surface branch no fixture can reach is vacuity one layer up, and it has happened four times
 * in four modules. The `none` and `several` plan states are two of those -- a browser fixture
 * publishes one trial, so neither renders there without a second tenant.
 */

const plan = (over: Partial<TrialPlan> = {}): TrialPlan => ({
  variant_id: "v1", display_name: "Seven-day trial", trial_days: 7, ...over,
});

describe("which trial a walk-in is started on", () => {
  it("has three states, because a tenant can publish none, one or several", () => {
    expect(planChoice([]).kind).toBe("none");
    expect(planChoice([plan()]).kind).toBe("one");
    expect(planChoice([plan(), plan({ variant_id: "v2" })]).kind).toBe("several");
  });

  it("carries the plan itself where there is one, so the page needs no second read", () => {
    const choice = planChoice([plan({ display_name: "Trial week" })]);
    expect(choice.kind === "one" && choice.plan.display_name).toBe("Trial week");
  });

  it("names the trial's length in the heading only where there is one answer", () => {
    expect(headlineDays(planChoice([plan({ trial_days: 7 })]))).toBe(7);
    // **Two plans of different lengths have no single answer until one is chosen**, and a
    // heading naming one of them would be naming whichever sorted first -- MOD-018's
    // unordered lookup in a title. The page falls back to the lengthless heading.
    expect(headlineDays(planChoice([
      plan({ trial_days: 7 }), plan({ variant_id: "v2", trial_days: 14 }),
    ]))).toBeNull();
    expect(headlineDays(planChoice([]))).toBeNull();
  });

  it("names no length for a plan whose terms state none, which cannot be a trial", () => {
    // `trial_days` is the one thing that marks a product as a trial (ADR-0010 D7), so a null
    // here is a row the trials-only filter should never have returned -- and the heading
    // falls back rather than rendering "Start a null-day trial".
    expect(headlineDays(planChoice([plan({ trial_days: null })]))).toBeNull();
  });
});

describe("what a press did", () => {
  it("reads the server's own step rather than assuming the trial is new", () => {
    const started: TrialSteps = {
      person: "created", lead: "created", agreement: "created",
      signature: "recorded", trial: "created",
    };
    expect(startedNow(started)).toBe(true);
    expect(startedNow({ ...started, trial: "existing" })).toBe(false);
  });

  it("treats a missing step as a start, because the four writes are resumable", () => {
    // ADR-0010 D12: a press that resumes reports `existing` for the steps it found and
    // `created` for the ones it made. Only `trial: "existing"` means nothing began now, and
    // an absent key is a response shape older than this field -- the fail-safe reading is
    // that something happened, because the confirmation then links to the lead either way.
    expect(startedNow({ person: "named", lead: "existing" })).toBe(true);
  });
});

describe("the confirmation's wording", () => {
  it("states day one as a fact about the write and has no arithmetic to do it", () => {
    // A press that started a trial started it today, so "day 1 of 7" needs no clock -- and
    // the already-running branch deliberately quotes only the end date, because which day
    // somebody is on needs a *today* that is on no response. ADM-CRM-05's card answers that
    // on the server, which is where the link goes.
    const en = MESSAGES.en["deskTrial.dayOne"];
    expect(typeof en === "object" && en.other).toContain("Day 1");
    expect(MESSAGES.en["deskTrial.endsOn"]).not.toContain("Day");
  });

  it("names the two promises this build does not keep", () => {
    expect(MESSAGES.en["deskTrial.notSent"]).toContain("No credential");
    expect(MESSAGES.en["deskTrial.gapInvitationWhy"]).toContain("sends a message");
  });

  it("keeps the plan-refused and no-plan states apart, because they are different facts", () => {
    expect(MESSAGES.en["deskTrial.noPlan"]).not.toBe(MESSAGES.en["deskTrial.plansRefused"]);
    expect(MESSAGES.en["deskTrial.plansRefusedWhat"]).toContain("different fact");
  });
});

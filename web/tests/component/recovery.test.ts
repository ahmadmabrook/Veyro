import { describe, expect, it } from "vitest";

import { MESSAGES } from "@/i18n/locale";
import {
  batchVerdict,
  failureName,
  keysInPlay,
  reasonName,
  treatmentName,
  treatmentSeverity,
  type RecoveryCase,
  type RecoveryWorkspace,
} from "@/lib/recovery";

/**
 * ADM-PAY-05's mappings, tested where they are made.
 *
 * **A stored value is never a label.** Four of these shipped in one pass elsewhere in this
 * app — a lifecycle state, two plan words, a credential kind — each rendering Latin letters
 * in the middle of an Arabic line, and `MESSAGE_KEYS` is structurally blind to every one of
 * them because it compares the two catalogues against each other and cannot see a string
 * that never became a key. So the parity check that matters here is the one run from the
 * side the catalogue cannot see: **every key this module maps to exists in both locales.**
 *
 * **An unknown value falls through to its raw form, not to "other".** The treatment set is
 * the server's and may grow; showing an ugly word is better than hiding a decision somebody
 * has to act on — which is MOD-013's board's rule, one module over.
 */

function one(over: Partial<RecoveryCase> = {}): RecoveryCase {
  return {
    case_id: "c1",
    invoice_id: "i1",
    stage: 1,
    dunning_attempts: 0,
    access_recommendation: "none",
    next_action_on: null,
    opened_on: "2026-11-01",
    document_number: "INV-0001",
    currency: "JOD",
    outstanding_minor: 55000,
    due_on: "2026-10-01",
    payer_person_id: "p1",
    failure_code: "card_expired",
    failure_class: "needs_member_action",
    method: "card",
    charges_presented: 1,
    failed_at: "2026-11-01T00:00:00+00:00",
    membership_id: "m1",
    membership_status: "active",
    membership_number: "M1",
    treatment: "link",
    treatment_reason: "member_action_needed",
    may_retry: false,
    notification_key: "payment_failed",
    ...over,
  };
}

function workspace(cases: RecoveryCase[]): RecoveryWorkspace {
  return {
    cases,
    count: cases.length,
    limit: 50,
    truncated: false,
    at_risk: [{ currency: "JOD", amount_minor: 312000 }],
    by_treatment: {
      link: cases.filter((c) => c.treatment === "link").length,
      review: cases.filter((c) => c.treatment === "review").length,
      retry: cases.filter((c) => c.treatment === "retry").length,
    },
    all_retries_exhausted: cases.every((c) => c.treatment !== "retry"),
    access_recommendations: ["none"],
    no_access_blocked: true,
    at_risk_is_outstanding: "",
    nothing_here_sends: "",
    no_card_detail_exists: "",
  };
}

describe("the treatment a case wants", () => {
  it("names all three, and marks only the one a person has to look at", () => {
    // `review` is the canvas's amber "review first"; `link` is its neutral "link ready".
    // `retry` is neither — the system is still working on it, and marking it would put a
    // row in front of somebody who has nothing to do about it.
    expect(treatmentName("link")).toBe("recovery.treatment.link");
    expect(treatmentName("review")).toBe("recovery.treatment.review");
    expect(treatmentName("retry")).toBe("recovery.treatment.retry");
    expect(treatmentSeverity("review")).toBe("attention");
    expect(treatmentSeverity("link")).toBeNull();
    expect(treatmentSeverity("retry")).toBeNull();
  });

  it("returns null for a value the server grew, so the page shows the value itself", () => {
    expect(treatmentName("escalate")).toBeNull();
    expect(reasonName("something_new")).toBeNull();
    expect(failureName("a_code_no_provider_here_has_sent")).toBeNull();
  });

  it("maps no reason at all to a sentence rather than an empty cell", () => {
    // `null` is the `unknown` payment state paragraph 1609 requires to be representable,
    // and it is a different fact from a code nobody recognises.
    expect(failureName(null)).toBe("recovery.failure.none");
  });
});

describe("the messages the set would send", () => {
  it("is one entry per distinct stage, sorted", () => {
    // The canvas previews one message because its six cases are all at stage 1. A set
    // spanning two stages sends two different messages, and a preview showing only the
    // first would be a claim about what the other members receive.
    const got = keysInPlay(workspace([
      one(),
      one({ case_id: "c2", notification_key: "payment_overdue_warning" }),
      one({ case_id: "c3" }),
    ]));
    expect(got).toEqual(["payment_failed", "payment_overdue_warning"]);
  });

  it("is empty when nothing is in recovery", () => {
    expect(keysInPlay(workspace([]))).toEqual([]);
  });
});

describe("the catalogue, from the side the parity check cannot see", () => {
  // Every key this module can return, driven over the vocabularies the server declares.
  const treatments = ["link", "review", "retry"];
  const reasons = [
    "member_action_needed", "retries_exhausted", "retries_remain",
    "failure_is_permanent", "membership_ended", "membership_frozen",
    "no_membership_cited", "cause_unknown",
  ];
  const codes = [
    "card_expired", "insufficient_funds", "authentication_required",
    "incorrect_details", "limit_exceeded", "issuer_unavailable", "processing_error",
    "rate_limited", "card_stolen", "card_lost", "do_not_honour_final",
    "mandate_revoked", "account_closed", null,
  ];

  const mapped = [
    ...treatments.map(treatmentName),
    ...reasons.map(reasonName),
    ...codes.map(failureName),
  ];

  it("maps every declared value to a key rather than leaking it to the page", () => {
    // **A declared value with no mapping is a stored value rendered as a label**, which in
    // Arabic is Latin letters mid-sentence. The fall-through exists for codes the *server*
    // grows, not for the ones it already declares.
    expect(mapped.filter((key) => key === null)).toEqual([]);
  });

  it("has every one of those keys in both locales", () => {
    for (const key of mapped) {
      expect(MESSAGES.en, `en is missing ${key}`).toHaveProperty(key as string);
      expect(MESSAGES.ar, `ar is missing ${key}`).toHaveProperty(key as string);
    }
  });
});

describe("whether the set really is one decision", () => {
  // **The canvas's closing note is a claim, not a caption.** "The batch action is the
  // default because the recommended treatment is identical for all six" is true only when
  // the treatments agree, and a page that printed it unconditionally would be inviting one
  // action over a set where it does the wrong thing to some rows. Both branches are tested
  // here because no single fixture can render both, which is the surface-branch vacuity
  // this repository has shipped four times.

  it("is one decision when every case wants the same thing", () => {
    const got = batchVerdict(workspace([one(), one({ case_id: "c2" })]));
    expect(got).toEqual({ kind: "one_decision", treatment: "link", count: 2 });
  });

  it("is one decision for a set that all wants reviewing, which is a different sentence", () => {
    const got = batchVerdict(workspace([
      one({ treatment: "review", treatment_reason: "membership_frozen" }),
    ]));
    expect(got).toEqual({ kind: "one_decision", treatment: "review", count: 1 });
  });

  it("is mixed the moment two treatments are present", () => {
    const got = batchVerdict(workspace([
      one(),
      one({ case_id: "c2", treatment: "review", treatment_reason: "membership_ended" }),
    ]));
    expect(got).toEqual({ kind: "mixed", link: 1, review: 1, retry: 0 });
  });

  it("is empty rather than a decision about nothing", () => {
    expect(batchVerdict(workspace([]))).toEqual({ kind: "empty" });
  });
});

import { describe, expect, it } from "vitest";

import {
  LIVE_BOOK, confirms, direction, livePrices, planName, repriceable, riseState,
  type Impact, type Plan, type PriceRow,
} from "@/lib/plans";

/**
 * ADM-MSH-09's three states and seven refusals.
 *
 * **A builder that refuses what the server cannot answer with**, which is the lesson
 * ADM-MSH-07 paid for: its `commitmentLine` reached a branch with a hand-written quote the
 * lifecycle cannot emit, so the branch passed its assertion and was dead in the product. Three
 * invariants hold here and all three come from `list_prices` and `price_change_impact`:
 *
 * - `in_window` is derived from the row's own dates, so a row with no supersession and a start
 *   in the past is in its window and a superseded one never is.
 * - `price_book_id` is a NOT NULL uuid, so no row carries an empty one. The first version of
 *   `repriceable` had a `noBook` branch keyed on exactly that -- a state the schema forbids --
 *   while the fact that *is* reachable, a live price in a book nobody activated, was dropped by
 *   this file's own hand-written type. Both halves of this build's recurring finding at once.
 * - `move_at_renewal` is `on_this_plan - inside_a_commitment` on the server, so a triple that
 *   does not add up is a response no caller can receive.
 */

function price(over: Partial<PriceRow> = {}): PriceRow {
  const one: PriceRow = {
    price_id: "price-1",
    price_book_id: "book-1",
    price_book_key: "standard",
    price_book_status: LIVE_BOOK,
    price_book_priority: 100,
    variant_id: "variant-1",
    amount_minor: 55_000,
    currency: "JOD",
    effective_from: "2026-01-01",
    in_window: true,
    ...over,
  };
  if (one.price_book_id === "") {
    throw new Error(
      "cat_prices.price_book_id is a NOT NULL uuid: list_prices cannot return an empty book");
  }
  if (!["draft", "active", "retired"].includes(one.price_book_status)) {
    throw new Error("cat_price_books_status admits draft, active or retired");
  }
  return one;
}

function impact(over: Partial<Impact> = {}): Impact {
  const one: Impact = {
    variant_id: "variant-1",
    as_of: "2026-11-25",
    on_this_plan: 2_140,
    inside_a_commitment: 890,
    move_at_renewal: 1_250,
    earliest_move_on: "2026-08-22",
    earliest_commitment_ends_on: "2027-03-01",
    ...over,
  };
  if (one.on_this_plan - one.inside_a_commitment !== one.move_at_renewal) {
    throw new Error(
      "price_change_impact derives move_at_renewal as on_this_plan - inside_a_commitment, "
      + "so the three cannot disagree");
  }
  if (one.move_at_renewal === 0 && one.earliest_move_on !== null) {
    throw new Error("nobody moving means there is no earliest move date");
  }
  return one;
}

function plan(over: Partial<Plan> = {}): Plan {
  return {
    product_id: "product-1",
    variant_id: "variant-1",
    display_name: "Monthly",
    product_name: "Club",
    product_key: "club",
    billing_period: "monthly",
    is_a_trial_product: false,
    price: price(),
    impact: impact(),
    ...over,
  };
}

describe("the builders refuse a state the server cannot produce", () => {
  it("refuses an empty price book, which the first repriceable branched on", () => {
    expect(() => price({ price_book_id: "" })).toThrow(/NOT NULL uuid/);
  });

  it("refuses a book status outside the schema's three", () => {
    expect(() => price({ price_book_status: "published" })).toThrow(/draft, active or retired/);
  });

  it("refuses an impact whose three counts do not add up", () => {
    expect(() => impact({ inside_a_commitment: 100 })).toThrow(/cannot disagree/);
  });

  it("refuses an earliest-move date for a change nobody moves on", () => {
    expect(() => impact({
      on_this_plan: 4, inside_a_commitment: 4, move_at_renewal: 0,
    })).toThrow(/no earliest move date/);
  });
});

describe("what a plan is called", () => {
  // **A variant is a term length and a product is the thing a member buys.** Rendering the
  // variant's name alone put "Monthly" on six of eight rows, and the fix needed a server
  // change: `sellable_plans` carried only `v.display_name`.
  it("is the product, qualified by the variant", () => {
    const named = planName(plan());
    expect(named.name).toBe("Club");
    expect(named.qualifier).toBe("Monthly");
    expect(named.isKey).toBe(false);
  });

  // `list_products`' own rule, copied by the plan read: a name in a language nobody asked for
  // is worse than none, and the key is always there.
  it("falls back to the product key when the name is not translated", () => {
    const named = planName(plan({ product_name: null }));
    expect(named.name).toBe("club");
    expect(named.isKey).toBe(true);
  });

  it("treats a blank name as untranslated rather than printing nothing", () => {
    expect(planName(plan({ product_name: "   " })).isKey).toBe(true);
  });
});

describe("which price a variant priced in two books reads as", () => {
  // **A variant in two books is a legitimate chart**, which is MOD-016's own `REV` beside
  // `REV-RETAIL`. `list_prices` orders by book key, so the alphabet is what the first version
  // of this selection used.
  const std = price({
    price_id: "p-std", price_book_key: "aaa-standard", price_book_priority: 100,
  });
  // **The keys point the other way from the priorities, deliberately.** With both rules
  // agreeing, disabling the priority comparison leaves the same answer and the mutation comes
  // back uncaught -- which is what happened, and is this repository's "a case catches a
  // weakening only if the weakened rule admits the row" one level out: the case has to be one
  // the two rules disagree about.
  const corporate = price({
    price_id: "p-corp", price_book_key: "zzz-corporate", price_book_priority: 500,
    amount_minor: 40_000,
  });
  const draft = price({
    price_id: "p-draft", price_book_key: "aaa-draft", price_book_status: "draft",
    price_book_priority: 900, amount_minor: 1_000,
  });

  it("takes the higher priority, not the earlier book key", () => {
    expect(livePrices([std, corporate]).get("variant-1")?.price_id).toBe("p-corp");
    expect(livePrices([corporate, std]).get("variant-1")?.price_id).toBe("p-corp");
  });

  // A book nobody activated matches no sale whatever its priority, so it loses to an active
  // one -- otherwise the highest-priority draft book would decide every figure on the screen.
  it("prefers an active book over a draft one however high its priority", () => {
    expect(livePrices([draft, std]).get("variant-1")?.price_id).toBe("p-std");
    expect(livePrices([std, draft]).get("variant-1")?.price_id).toBe("p-std");
  });

  it("falls back to the draft book when nothing active is in window", () => {
    expect(livePrices([draft]).get("variant-1")?.price_id).toBe("p-draft");
  });

  // **`choose_book`'s own third key**, and its docstring says why: the book key "is unique, so
  // there is never a tie the planner gets to break. A resolver whose answer depended on row
  // order would fail the requirement in the way nobody notices until two tills disagree." Two
  // books at the same priority priced from the same date is the ordinary result of adding a
  // seasonal book beside a standing one -- the fixture has exactly that -- and the first
  // version of this ordering ended on the date, so it came back to iteration order.
  it("breaks a priority tie on the book key, in both orders", () => {
    const a = price({ price_id: "p-a", price_book_key: "autumn" });
    const z = price({ price_id: "p-z", price_book_key: "zzz-sale" });
    expect(livePrices([z, a]).get("variant-1")?.price_id).toBe("p-a");
    expect(livePrices([a, z]).get("variant-1")?.price_id).toBe("p-a");
  });

  it("takes the later start for two prices in the same book", () => {
    const older = price({ price_id: "p-old", effective_from: "2025-01-01" });
    const newer = price({ price_id: "p-new", effective_from: "2026-06-01" });
    expect(livePrices([newer, older]).get("variant-1")?.price_id).toBe("p-new");
    expect(livePrices([older, newer]).get("variant-1")?.price_id).toBe("p-new");
  });

  it("skips a row outside its window whatever its book", () => {
    expect(livePrices([price({ in_window: false })].concat()).size).toBe(0);
  });

  it("answers per variant", () => {
    const other = price({ price_id: "p-other", variant_id: "variant-2" });
    const found = livePrices([std, other]);
    expect(found.get("variant-1")?.price_id).toBe("p-std");
    expect(found.get("variant-2")?.price_id).toBe("p-other");
  });
});

describe("whether a plan can be re-priced at all", () => {
  it("is ready when a live price sits in an active book", () => {
    expect(repriceable(plan()).kind).toBe("ready");
  });

  it("has no price when the plan has none at all", () => {
    expect(repriceable(plan({ price: null })).kind).toBe("noPrice");
  });

  it("has no price when the only row is outside its window", () => {
    expect(repriceable(plan({ price: price({ in_window: false }) })).kind).toBe("noPrice");
  });

  // **The state the first version could not express.** `create_price` never reads the book's
  // status, so a version written into a retired book is accepted by the server and resolved by
  // no sale: a price change reporting success and charging nobody.
  it("refuses a live price whose book was retired, and says which book", () => {
    const state = repriceable(plan({
      price: price({ price_book_status: "retired", price_book_key: "summer" }),
    }));
    expect(state.kind).toBe("deadBook");
    if (state.kind !== "deadBook") throw new Error("unreachable");
    expect(state.status).toBe("retired");
    expect(state.price.price_book_key).toBe("summer");
  });

  it("refuses a live price in a draft book for the same reason", () => {
    expect(repriceable(plan({
      price: price({ price_book_status: "draft" }),
    })).kind).toBe("deadBook");
  });

  // A dead book keeps its figure, because the amount was really written -- what is untrue of
  // it is that a sale resolves to it.
  it("keeps the figure on a dead book rather than hiding it", () => {
    const state = repriceable(plan({ price: price({ price_book_status: "draft" }) }));
    if (state.kind !== "deadBook") throw new Error("unreachable");
    expect(state.price.amount_minor).toBe(55_000);
  });
});

describe("the typed confirmation the canvas requires", () => {
  const club = { amountMinor: 58_000, currency: "JOD" };

  it("accepts the figure as drawn", () => {
    expect(confirms("58.00", club)).toBe(true);
  });

  // **An amount, not a string.** The point of a tier-3 typed confirmation is to make somebody
  // read the figure, not reproduce its trailing zero -- and a control about typography teaches
  // people to copy and paste.
  it("accepts the same amount written shorter", () => {
    expect(confirms("58", club)).toBe(true);
    expect(confirms("58.0", club)).toBe(true);
    expect(confirms(" 58.00 ", club)).toBe(true);
  });

  it("refuses the old figure, a near miss and a word", () => {
    expect(confirms("55.00", club)).toBe(false);
    expect(confirms("58.01", club)).toBe(false);
    expect(confirms("yes", club)).toBe(false);
    expect(confirms("", club)).toBe(false);
  });

  // JOD is stored in fils and shown with two decimals, which is the one conflation
  // `@/lib/cash` exists to prevent: 58.00 is 58,000 minor units and not 5,800.
  it("compares in the currency's own storage precision", () => {
    expect(confirms("58.00", { amountMinor: 5_800, currency: "JOD" })).toBe(false);
  });

  it("fails closed on a currency this build cannot render", () => {
    expect(confirms("58.00", { amountMinor: 58_000, currency: "ZZZ" })).toBe(false);
  });
});

describe("which of seven states the sheet is in", () => {
  const current = price();
  const today = "2026-11-25";
  const ask = (over: Partial<Parameters<typeof riseState>[0]> = {}) => riseState({
    typedAmount: "58.00", effectiveFrom: "2026-12-01", typedConfirmation: "58.00",
    current, today, ...over,
  });

  it("rests on an empty field", () => {
    expect(ask({ typedAmount: "" }).kind).toBe("resting");
    expect(ask({ typedAmount: "   " }).kind).toBe("resting");
  });

  it("names a figure it cannot parse", () => {
    expect(ask({ typedAmount: "fifty-eight" }).kind).toBe("notAnAmount");
  });

  // **A version charging the same still supersedes the row in force**, so a reader who
  // mistyped and got the old figure back would have moved the price's history for nothing.
  it("refuses the price it already is", () => {
    expect(ask({ typedAmount: "55.00" }).kind).toBe("unchanged");
    expect(ask({ typedAmount: "55" }).kind).toBe("unchanged");
  });

  it("asks for a date before anything else", () => {
    expect(ask({ effectiveFrom: "" }).kind).toBe("needsDate");
  });

  // MOD-016's own stated gap: a stored resolution is immutable so a receipt stands, but a
  // re-derivation of a historical order reads the price rows.
  it("refuses a date in the past and accepts today", () => {
    expect(ask({ effectiveFrom: "2026-11-24" }).kind).toBe("dateInThePast");
    expect(ask({ effectiveFrom: today }).kind).toBe("ready");
  });

  it("waits for the typed figure, and carries the amount while it waits", () => {
    const state = ask({ typedConfirmation: "" });
    expect(state.kind).toBe("needsConfirmation");
    if (state.kind !== "needsConfirmation") throw new Error("unreachable");
    expect(state.amountMinor).toBe(58_000);
  });

  it("waits when the typed figure is the old one", () => {
    expect(ask({ typedConfirmation: "55.00" }).kind).toBe("needsConfirmation");
  });

  it("is ready only with all three, and returns both", () => {
    const state = ask();
    expect(state.kind).toBe("ready");
    if (state.kind !== "ready") throw new Error("unreachable");
    expect(state.amountMinor).toBe(58_000);
    expect(state.effectiveFrom).toBe("2026-12-01");
  });

  // **The order is the point, not an accident.** A figure that cannot be parsed is named
  // before a missing date, so a reader fixing one thing at a time is told about the field they
  // are in rather than the one below it.
  it("names the amount before the date when both are wrong", () => {
    expect(ask({ typedAmount: "oops", effectiveFrom: "" }).kind).toBe("notAnAmount");
  });
});

describe("whether it is a rise or a cut", () => {
  const current = price();

  it("is a rise above the figure in force", () => {
    expect(direction(58_000, current)).toBe("rise");
  });

  // A cut reaches the same members and the same split applies -- a member inside a term keeps
  // the old, *higher* figure until it ends, which is the surprising direction.
  it("is a cut below it", () => {
    expect(direction(45_000, current)).toBe("cut");
  });
});

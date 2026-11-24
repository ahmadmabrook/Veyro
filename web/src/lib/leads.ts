import { fill, formatInteger, type Locale, type MessageKey } from "@/i18n/locale";

/**
 * ADM-CRM-01 and ADM-CRM-02's decisions, with no I/O in the module.
 *
 * **Nothing here composes a name.** A lead is a `ppl_persons` row -- "a lead, a trialist and
 * a member are one record at three stages, never three records" -- so the name arrives from
 * MOD-014 already masked by its own rules, and this module never builds one from parts.
 *
 * **The two views are two components over one list.** The canvas draws a board of five
 * columns and a "Board view" toggle beside a table; ADM-CRM-02's own note says the table is
 * "the same grid component as the members list at the same 34px". So the view is a parameter
 * and the rows are the same rows.
 */

/** The five columns ADM-CRM-01 draws, in its own order. The last two are MOD-017's answer. */
export const BOARD_COLUMNS = ["new", "contacted", "toured", "on_trial", "joined"] as const;

export type BoardColumn = (typeof BOARD_COLUMNS)[number];

export const LEAD_VIEWS = ["board", "table"] as const;

export type LeadView = (typeof LEAD_VIEWS)[number];

export function isLeadView(value: string | undefined): value is LeadView {
  return value !== undefined && (LEAD_VIEWS as readonly string[]).includes(value);
}

/** ADM-CRM-02's three chips. The third is slice 2's and is not offered. */
export const LEAD_FILTERS = ["all", "going_cold", "mine"] as const;

export type LeadFilter = (typeof LEAD_FILTERS)[number];

export function isLeadFilter(value: string | undefined): value is LeadFilter {
  return value !== undefined && (LEAD_FILTERS as readonly string[]).includes(value);
}

/** One row of `GET /crm/leads`. No name, no number: those are MOD-014's. */
export type LeadRow = {
  lead_id: string;
  person_id: string;
  /** The stored sales stage, which is what the route's filter takes. */
  stage: string;
  /**
   * Which of the five board columns this person is in.
   *
   * **Both, because they answer different questions.** The board derives its last two columns
   * from MOD-017 and the table showed `stage`, so ADM-CRM-02 read "New" for somebody
   * ADM-CRM-01 put in "On trial" -- two views of one list disagreeing about where a person
   * is. The server derives this one; a client cannot, because whether a membership is live is
   * a date comparison in the tenant's own frame.
   */
  board_stage: string;
  source_id: string | null;
  source: string | null;
  owner_person_id: string | null;
  next_action: string | null;
  next_action_on: string | null;
  created_at: string;
  version: number;
  last_touch_at: string | null;
  hours_since_contact: number;
  going_cold: boolean;
  /**
   * ADM-CRM-07's state, which is a fact beside the stage rather than a sixth value in it.
   *
   * `stage` is unchanged while a lead is lost, so a board or a table reading only `stage`
   * would still place them -- which is why both reads exclude them and this flag is on the
   * row for the one screen that draws a refusal.
   */
  lost: boolean;
  lost_at: string | null;
  lost_reason: string | null;
  lost_detail: string | null;
  /** Advisory: lost more than ninety days ago. Reopening is allowed either way. */
  recontactable: boolean;
};

export type LeadList = {
  leads: LeadRow[];
  count: number;
  limit: number;
  truncated: boolean;
  going_cold_after_hours: number;
};

export type Board = {
  columns: { stage: string; count: number }[];
  open_leads: number;
  going_cold: number;
  /** Present when the reader is not linked to a person, in which case every count is zero. */
  mine_is_zero_without_a_person_record?: string;
  on_trial_is_empty_in_this_slice?: string;
};

export type Touchpoint = {
  touchpoint_id: string;
  kind: string;
  occurred_at: string;
  summary: string;
  summary_withheld: boolean;
  recorded_at: string;
  recorded_by: string;
};

export type LeadDetail = LeadRow & {
  stage_changed_at: string;
  interests: string[];
  board_stage: string;
  touchpoints: Touchpoint[];
  touchpoint_count: number;
  touchpoints_truncated: boolean;
};

/**
 * What `GET /crm/leads/{id}/trial` answers.
 *
 * **A discriminated union on `on_trial`**, because a lead with no trial is the ordinary case
 * -- three of the five board columns -- and a shape that carried four optional zeros would let
 * a screen render `0 VISITS` for somebody who is not on a trial at all. That is MOD-014's "a
 * confident wrong answer where a missing one would have been honest", which its own 360 was
 * bitten by.
 */
/**
 * One row of ADM-CRM-06's plan pick.
 *
 * **No amount, by design.** A price needs `catalog.price.read` and only a quote may name it,
 * so a picker that carried figures would make "see the catalog" buy "see what every sale
 * costs". The billing period and anchor are here because a screen can derive neither and
 * together they decide which boundary the first charge is prorated to.
 */
export type SellablePlan = {
  product_id: string;
  variant_id: string;
  display_name: string;
  product_key: string;
  billing_period: string;
  billing_anchor: string;
  membership_kind: string;
  trial_days: number | null;
  is_a_trial_product: boolean;
};

/**
 * ADM-CRM-06's answer: what it costs this person to become a member on this plan, today.
 *
 * **`recurring_minor` and `first_charge_minor` are different numbers and neither is derivable
 * from the other.** The design's own note on the sale sheet says confusing them is "the most
 * common membership-sale complaint in the industry", which is why both are on the wire and
 * why `prorated` is a field rather than a comparison a client makes.
 */
export type ConversionQuote = {
  lead_id: string;
  person_id: string;
  stage: string;
  /** The server's day, so the screen never consults its own clock. */
  today: string;
  plan: {
    variant_id: string;
    display_name: string;
    product_key: string;
    billing_period: string;
    billing_anchor: string;
  };
  currency: string;
  price_book_id: string;
  price_id: string;
  recurring_minor: number;
  list_amount_minor: number;
  discount_minor: number;
  first_charge_minor: number;
  first_period_ends_on: string;
  recurring_starts_on: string;
  prorated: boolean;
  explanation: string[];
  converting_from_a_trial: boolean;
  trial: {
    membership_id: string;
    starts_on: string;
    ends_on: string;
    trial_days: number;
  } | null;
  carries_over: {
    classes: number;
    visits: number;
    touchpoints: number;
    the_record_does_not_change: string;
    no_credential_count_here: string;
  };
  nothing_is_charged_here: string;
};

export type TrialCard =
  | {
      on_trial: false;
      lead_id: string;
      person_id: string;
      stage: string;
      not_on_a_trial: string;
    }
  | {
      on_trial: true;
      lead_id: string;
      person_id: string;
      stage: string;
      membership_id: string;
      starts_on: string;
      ends_on: string;
      trial_days: number;
      visits: number;
      classes: number;
      day_of: number;
      of_days: number;
      days_left: number;
      ends_tomorrow: boolean;
      /** One of ENGAGEMENT, which is how much of the trial has been used. */
      engagement: string;
    };

/**
 * The reader's word for an engagement band, or `null` where this build has none.
 *
 * **Use, not likelihood.** The drawn canvas's cell is `ENGAGEMENT` and the prototype calls the
 * same cell conversion likelihood -- a prediction about a person, which MOD-020 refuses
 * outright for the no-show score because "paragraph 1889's 'must not discriminate unlawfully'
 * is a property of a population under a model rather than of an expression". So these four
 * words describe what happened.
 */
export function engagementWord(band: string): MessageKey | null {
  return ENGAGEMENT_WORDS[band] ?? null;
}

const ENGAGEMENT_WORDS: Record<string, MessageKey> = {
  none: "trial.engagementNone",
  light: "trial.engagementLight",
  steady: "trial.engagementSteady",
  high: "trial.engagementHigh",
};

export type SourceRow = {
  source_id: string;
  source_key: string;
  display_name: string;
  location_id: string | null;
  status: string;
  created_at: string;
};

const STAGE_WORDS: Record<string, MessageKey> = {
  new: "leads.stage.new",
  contacted: "leads.stage.contacted",
  toured: "leads.stage.toured",
  on_trial: "leads.stage.onTrial",
  joined: "leads.stage.joined",
};

const KIND_WORDS: Record<string, MessageKey> = {
  call: "leads.kind.call",
  message: "leads.kind.message",
  email: "leads.kind.email",
  visit: "leads.kind.visit",
  tour: "leads.kind.tour",
  note: "leads.kind.note",
};

/** ADM-CRM-04's three, in the vocabulary's own order -- which is the server's. */
export const INTERESTS = ["classes", "pt", "gym_only"] as const;

/**
 * The one stage the pipeline admits from here, or `null` at the end of it.
 *
 * **Forward only, and the table is the server's `EDGES` read from the client side.** A screen
 * that offered a backwards move would offer one the service refuses, which is FD-06's "a
 * button the module will refuse is worse than no button" -- and `toured` is the last sales
 * stage, because the two columns after it are what a membership answers.
 */
export function nextStage(stage: string): string | null {
  if (stage === "new") return "contacted";
  if (stage === "contacted") return "toured";
  return null;
}

const INTEREST_WORDS: Record<string, MessageKey> = {
  classes: "leads.interest.classes",
  pt: "leads.interest.pt",
  gym_only: "leads.interest.gymOnly",
};

/**
 * The reader's word for a stored value, or `null` where this build has none.
 *
 * **A vocabulary the backend stores is never a label**, which this app has four recorded
 * defects from -- a `lifecycle_state` rendered as `lead`, a plan rendered as `recurring`, a
 * wallet kind and a credential kind, each Latin letters in the middle of an Arabic line. And
 * `null` rather than a fallback word: the set is the server's and may grow, so showing an
 * ugly value is better than hiding a stage somebody needs to see.
 */
export function stageWord(stage: string): MessageKey | null {
  return STAGE_WORDS[stage] ?? null;
}

export function kindWord(kind: string): MessageKey | null {
  return KIND_WORDS[kind] ?? null;
}

export function interestWord(interest: string): MessageKey | null {
  return INTEREST_WORDS[interest] ?? null;
}

/**
 * How long since this lead was last contacted, in the canvas's own two forms.
 *
 * "open day · 2d" and "instagram · 4h": hours below a day and whole days above it. Both are
 * whole numbers, because this app has one number path and `formatInteger` throws for a
 * fraction -- which cost a 500 on a rendered page once.
 *
 * **The server computed the hours.** A browser comparing a timestamp against its own clock
 * counts in the wrong frame, which this build has three recorded defects from, so the figure
 * comes down on the row and this only chooses the unit.
 */
export function sinceLabel(locale: Locale, hours: number): string {
  if (hours < 1) return fill(locale, "leads.sinceNow", {});
  if (hours < 24) return fill(locale, "leads.sinceHours", { count: hours });
  return fill(locale, "leads.sinceDays", { count: Math.floor(hours / 24) });
}

/**
 * ADM-CRM-02's meta line under a name: the source and the age.
 *
 * A lead with no source says so rather than leaving the line half-empty: "where did this come
 * from" is the question ADM-RPT-03 is built on, and an unattributed lead is the answer that
 * matters most.
 */
export function metaLine(locale: Locale, lead: LeadRow): string {
  const source = lead.source ?? fill(locale, "leads.noSource", {});
  return `${source} · ${sinceLabel(locale, lead.hours_since_contact)}`;
}

/**
 * The count beside a column title, as the canvas draws it.
 *
 * Rendered through `formatInteger` rather than interpolated, because this app has one
 * number path and a cross-runtime parity test behind it -- a bare `String(n)` is a second
 * one. `latn` because the numeral system is a tenant setting this build does not carry,
 * which is the same choice `money()` records.
 */
export function columnCount(count: number): string {
  return formatInteger(count, "latn");
}

/**
 * How many cards a column draws before it says "+N more".
 *
 * Two, which is what the canvas draws -- and the overflow line is a link rather than a
 * truncation, because a column that silently stopped would be a count the reader cannot
 * reconcile with the rows under it.
 */
export const CARDS_PER_COLUMN = 2;

/**
 * What a board column is missing, where it is missing something.
 *
 * **Nothing, now that a trial is expressible.** `on_trial` carried a note saying nothing in
 * this build marked a product as a trial; ADR-0010 D7 settled that -- `trial_days` on the
 * membership terms is the marker, and the server derives the column from MOD-017's
 * supersession chain. So the note is gone rather than reworded: a gap list is a claim about
 * the product, and the one direction it goes stale in is the hour the gap closes.
 *
 * The function stays because the next column to need a reason will need the same slot, and
 * `null` for every stage is a cheaper statement than deleting it and re-deriving it later.
 */
export function columnNote(_stage: string): MessageKey | null {
  return null;
}

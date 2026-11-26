import type { ReactNode } from "react";

import type { MessageKey } from "@/i18n/locale";
import type { Severity } from "@/components/ds/status-badge";

/**
 * ADM-CC-01's decisions, with no I/O — what the Command Center says and in what order.
 *
 * The specification is in `screens.generated.json`, five canvases of it, and the parts that
 * are decisions rather than markup are here so they can be tested without a database or a
 * browser. `command-centre-reads.ts` does the I/O and `app/page.tsx` renders.
 *
 * ## What the design is, in one paragraph
 *
 * A metric row of four figures; an attention queue that is "the reason the page exists" and
 * never collapses at any viewport; an AI interpretation panel; and two charts. The heading
 * counts the queue — "Three things need you this morning" — and the queue carries a category
 * eyebrow, a timing, an optional money figure, a title, a paragraph of explanation, actions,
 * and who owns it.
 *
 * ## The four rules worth stating before the code
 *
 * **A metric carries its own freshness.** `DS-CL-01` in the design's own change log: a page
 * banner is the right container for "the pipeline is behind" and the wrong granularity for
 * the data, because "mixing fresh and stale numbers in one grid with a single caveat above
 * them invites exactly the misreading the money rules exist to prevent — a manager quoting a
 * stale collections figure as current". So `freshness` is `live | stale | unavailable`, and
 * the third value is what this build needs most: **there is no CRM module**, so the design's
 * fourth metric has no source and renders as unavailable with its reason rather than as a
 * number somebody could act on.
 *
 * **An empty queue is the goal, not a gap.** Canvas 4: "No illustration, no 'all caught up!'
 * — it reports the day and offers the next useful thing. A manager who sees this should feel
 * informed, not congratulated."
 *
 * **The metrics do not turn red.** Canvas 3, during an outage: "48 people in the building is
 * a fact, not a problem, and colouring it red during an unrelated outage teaches staff to
 * distrust the colour. Only the outage and its direct consequence carry severity."
 *
 * **The AI panel withholds rather than reasoning from what it does not have.** Canvas 5 does
 * this for stale inputs — "an interpretation built on stale inputs is the one thing worse
 * than no interpretation". Here the reason is different and stronger: there is no
 * interpretation engine in this build at all. Writing a plausible one would be the
 * fabricated-evidence shape this codebase has been bitten by six times, so the panel renders
 * its withheld state with the true reason.
 */

/** The five categories the design's queue uses, as its eyebrows. */
export const CATEGORIES = [
  "money",
  "compliance",
  "retention",
  "staffing",
  "leads",
] as const;

export type Category = (typeof CATEGORIES)[number];

/**
 * §30's severity scale is the design system's, imported rather than redeclared.
 *
 * Four steps -- `neutral`, `info`, `attention`, `critical` -- and the foundation audit's note
 * on them is worth keeping: "Four steps carried nine distinct conditions across both screens
 * without a fifth being wanted." A second scale local to this screen is the duplicate the
 * directive forbids by name, and the edge-mark and the badge are "the same scale expressed at
 * two granularities", which only holds while there is one scale.
 */
export type { Severity };

/** `DS-CL-01`'s variant, filed in the design's own change log rather than invented here. */
export type Freshness = "live" | "stale" | "unavailable";

export type Metric = {
  /** The label, e.g. "COLLECTED · MONTH TO DATE". */
  label: MessageKey;
  freshness: Freshness;
  /** The figure, already formatted, or null when `freshness` is not `live`. */
  value: string | null;
  /** The comparison line under the value: "↓ 7.8% vs July · pace to 63.1k". */
  comparison?: string;
  /** Why there is no figure. Required when `freshness` is `unavailable`. */
  unavailableBecause?: MessageKey;
  /** The change, in basis points, when there is a baseline. `null` is not zero. */
  changeBp?: number | null;
};

export type Action = {
  label: MessageKey;
  /** Where it goes. A queue action with nowhere to go is not rendered — see `withRoutes`. */
  href?: string;
};

export type AttentionItem = {
  key: string;
  category: Category;
  severity: Severity;
  /** The eyebrow's right half: "2h ago · Khalda, Abdoun". */
  when: string;
  /**
   * A money figure and what it means: "JOD 312.00 at risk".
   *
   * A node rather than a string, because §39 forbids a bare number: the amount is a
   * `MoneyValue` of a declared kind, and `owed` is set in the critical ink while a renewal
   * value is neutral. A string here would make the kind unexpressible.
   */
  money?: { amount: ReactNode; meaning: MessageKey };
  title: string;
  /** The paragraph that explains what happened and what is already handled. */
  body: string;
  actions: Action[];
  /** "unassigned", or who owns it. The design renders both. */
  owner?: string;
  /**
   * `full` or `condensed` — ADM-CC-01's component list is "AttentionRow ×5 (2 full,
   * 2 condensed, 1 collapsed group)", and the canvas draws STAFFING and LEADS on one line.
   * Absent means full, because a row that needs explaining is the default and the short
   * form is the exception somebody opts into.
   */
  density?: "full" | "condensed";
};

/**
 * The queue, ordered. Critical first, then by category in the design's own order.
 *
 * **The order is the design's, not a sort by recency.** Canvas 1 runs MONEY, COMPLIANCE,
 * RETENTION, STAFFING, LEADS, and canvas 2 — the same morning, a different role — leads with
 * COACHING because that is the job that manager has. So the order is a declared sequence
 * rather than a timestamp comparison, which would reshuffle the page every few minutes and
 * make it un-learnable.
 */
export function orderQueue(items: AttentionItem[]): AttentionItem[] {
  const rank = (item: AttentionItem) =>
    (item.severity === "critical" ? 0 : 1) * 100 + CATEGORIES.indexOf(item.category);
  return [...items].sort((a, b) => rank(a) - rank(b) || a.key.localeCompare(b.key));
}

/** How the queue's own header counts itself: "9 open · 2 critical · 4 assigned to others". */
export function queueCounts(items: AttentionItem[]): {
  open: number;
  critical: number;
  assigned: number;
} {
  return {
    open: items.length,
    critical: items.filter((item) => item.severity === "critical").length,
    assigned: items.filter((item) => item.owner !== undefined).length,
  };
}

/**
 * The heading, which counts the queue: "Three things need you this morning".
 *
 * **Returns a key and a count, never a built sentence.** The number is inside the phrase in
 * both languages and the grammar differs, so composing it here would put English word order
 * into an Arabic heading — which is the finding this repository already records for MOD-013's
 * decision reasons, where eight English sentences reached an otherwise-correct Arabic page.
 *
 * **`complete` is what makes the empty heading honest, and it was a defect without it.**
 * Canvas 4's "Nothing needs you at Abdoun" is a statement about the business, and the page
 * can only make it when it could see everything that would have contributed. A reader
 * holding three of the four grants was shown the same sentence -- so a club manager without
 * `finance.dunning.read` read "nothing needs you" over six payments in recovery. Found by
 * signing in and looking at the page, which is how this build has found its last four
 * surface defects.
 */
export function heading(
  items: AttentionItem[],
  complete = true,
): { key: MessageKey; count: number } {
  if (items.length > 0) return { key: "cc.heading", count: items.length };
  return { key: complete ? "cc.headingClear" : "cc.headingPartial", count: 0 };
}

/**
 * An action is rendered only when it has somewhere to go.
 *
 * The design's queue rows carry primary actions — "Send 6 payment links", "Fix the 3
 * invoices", "Offer to Dana or Yousef" — and **none of those writes exists in this build**:
 * every one is a stepped-up financial permission with no form behind it, which is the same
 * gap the hierarchy surface has. A button that does nothing is worse than one that is absent
 * (ADM-MEM-05's own rule, applied to its bulk bar), so an action with no `href` is dropped
 * and the row says what it cannot do instead.
 */
export function withRoutes(actions: Action[]): Action[] {
  return actions.filter((action) => action.href !== undefined);
}

/**
 * Whether the page is in its degraded state, and which panels are behind.
 *
 * Canvas 5: "Per-panel provenance, not a page-level spinner. Stale numbers de-emphasise to
 * secondary and carry a timestamp; live ones stay primary." A read that failed is not the
 * same as a read that is late, and neither is the same as a module that does not exist — so
 * the three are different `Freshness` values rather than one boolean.
 */
export function degraded(metrics: Metric[]): boolean {
  return metrics.some((metric) => metric.freshness === "stale");
}

/**
 * The AI panel's state. Always `withheld` in this build, and the reason is the true one.
 *
 * The design's withheld state exists for stale inputs. This build's reason is stronger: no
 * module produces an interpretation at all. The panel is still rendered, because the design
 * puts a titled, bordered block there and an absent one would make the page look like a
 * different screen — and because the honest sentence is worth reading.
 */
export const AI_PANEL = {
  state: "withheld" as const,
  /** The eyebrow the design requires above any interpretation, verbatim. */
  eyebrow: "cc.aiEyebrow" as MessageKey,
  reason: "cc.aiWithheld" as MessageKey,
};

/**
 * What ADM-CC-01 specifies that this build cannot answer, named in one place.
 *
 * The same device ADM-MEM-05 uses for its three unanswerable columns: a screen states its
 * own gaps rather than rendering an empty panel that reads as a fact about the business.
 * Every entry here is a module that does not exist or a write with no form, and each is
 * quoted from the design so a reader can see what is missing rather than inferring it.
 */
export const UNANSWERABLE = {
  /** The scope switcher the heading's "all locations" comes from. */
  scope: "cc.gapScope" as MessageKey,
} as const;

import type { CSSProperties } from "react";

import { SEVERITY, VOCABULARY } from "@/design/contracts.generated";

/**
 * StatusBadge and the row edge-mark — §30. One four-step scale at two granularities.
 *
 * **The component takes an enum, not a string.** The source is explicit about why: "A status
 * the vocabulary does not contain cannot be rendered — the component takes an enum, not a
 * string, so an engineer cannot invent 'Semi-active'." Every status this product can render
 * is one of the twenty below, and TypeScript refuses the rest at the call site rather than at
 * a design review three months later.
 *
 * **Four severities, not five.** "'success' is not a severity, it is the neutral case. A green
 * badge on every paid invoice makes a table of paid invoices look like a celebration and makes
 * the one unpaid row harder to find." So `Paid`, `Active` and `Confirmed` are `neutral`, and
 * there is no green.
 *
 * **Never colour alone.** Every badge carries its label; icon-only status is a defect at any
 * density. At Compact the label may abbreviate but never disappear, and the full text stays in
 * the accessible name regardless.
 *
 * **The enum is the state; `label` is the word.** The status is a closed English vocabulary
 * from the design source and that is what makes it type-safe -- and rendering it is what put
 * a Latin word in the middle of an Arabic line the first time a screen used this component.
 * That is this repository's own recurring finding ("a vocabulary the backend stores is never
 * a label"), and the catalogue's parity check is structurally blind to it: a string that
 * never became a message key cannot be compared between two catalogues. So a caller passes
 * the localized word and `tests/unit/ds-usage.test.mjs` requires it, because an English badge
 * on an Arabic page is invisible to every assertion about structure.
 *
 * The edge-mark is the same scale expressed at row granularity: it carries the roll-up while
 * the badge names the specific state, which is what stopped them reading as two independent
 * signals. In RTL the edge-mark moves to the logical start edge, which `border-inline-start`
 * does without a direction check.
 */

export type Severity = "neutral" | "info" | "attention" | "critical";

/**
 * The fixed vocabularies and their severities — **generated, not transcribed**.
 *
 * The first version of this file wrote both out by hand from §30 and was wrong: §30's
 * "Payment" line names five states, and Step 4's domain-component file names *ten*, each with
 * its own severity column — Retrying, Overdue, Disputed, Cash pending and Wallet applied are
 * only in the second. A payment row could not be marked overdue at all, which is the one
 * payment state a members table exists to surface. Found by a test comparing the map against
 * the extraction rather than against the prose I had read.
 *
 * So `src/design/extract.mjs` builds both from the source and the generator fails if §30's
 * list stops being a subset of PAY_STATES, or if any vocabulary entry has no severity.
 */
export { VOCABULARY, SEVERITY } from "@/design/contracts.generated";

export type Domain = keyof typeof VOCABULARY;
export type Status = (typeof VOCABULARY)[Domain][number];

/**
 * **The tone lives in the stylesheet now, and `ds-badge` used to style nothing.**
 *
 * The class was applied from the first commit and defined nowhere; every badge in the
 * product was painted by a `style` object instead. Two things were wrong with that and the
 * undefined-class sweep found the first:
 *
 * A design-system class that styles nothing is a promise the component exists, and it hides
 * the component from the stylesheet entirely -- a theme, a density mode or a media query
 * cannot reach an inline style, so this badge could not have responded to any of them.
 *
 * And the tone it painted was `borderInlineStart: 2px solid <severity>` on a box with
 * `borderRadius`, which is a bar down one side of a rounded box: the craft floor bans that
 * outright "any colour or state" and answers it with "a full border, a tint, or a leading
 * icon or label". The badge already has the label -- it names the state in words, which is
 * what makes it more than a colour -- so the severity is a solid field, matching the
 * attention queue's category chips so the two read as one system rather than two.
 */

export function StatusBadge({
  status,
  label,
  abbreviated,
  style,
}: {
  status: Status;
  /**
   * The status in the reader's own language. Required by the usage sweep: the enum is the
   * state and this is the word for it, and the two must mean the same thing.
   */
  label?: string;
  /** Compact only. The label shortens; the accessible name does not. */
  abbreviated?: string;
  style?: CSSProperties;
}) {
  const severity = SEVERITY[status] ?? "neutral";
  return (
    <span
      // Not a button: the source says a badge is "not a button unless it opens something",
      // and nothing here opens anything.
      className={`ds-badge ds-badge-${severity}`}
      // The full text stays in the accessible name whatever the visible label does -- and
      // it is the localized one where there is one, because an abbreviation whose accessible
      // name is in another language is worse than no abbreviation.
      aria-label={abbreviated ? (label ?? status) : undefined}
      {...(style ? { style } : {})}
    >
      {abbreviated ?? label ?? status}
    </span>
  );
}

/**
 * The row-level roll-up, as a style to spread onto a row container.
 *
 * Same scale, coarser granularity: a row carries the worst severity among its cells and the
 * badge still names the specific state. A row with no severity gets no mark at all rather than
 * a neutral one, because a mark on every row is not a signal.
 */
export function edgeMark(severity: Severity | null): CSSProperties {
  if (severity === null || severity === "neutral") return {};
  // **A table row, not a rounded box.** The craft floor's ban is on a bar down one side of a
  // rounded box, which is the card cliché; a severity mark on the leading edge of a dense
  // grid row is a standard affordance the reader already knows, and the rows here carry no
  // radius. The attention queue's rows lost theirs because they *were* boxes and because the
  // category chip was already carrying the signal in words.
  const edge = {
    info: "var(--color-semantic-info)",
    attention: "var(--color-semantic-warning)",
    critical: "var(--color-semantic-error)",
  }[severity];
  return { borderInlineStart: `var(--shell-rule) solid ${edge}` };
}

/** The worst severity in a set, for a row roll-up. */
export function rollUp(statuses: readonly Status[]): Severity | null {
  const order: Severity[] = ["neutral", "info", "attention", "critical"];
  let worst = -1;
  for (const s of statuses) {
    const at = order.indexOf(SEVERITY[s] ?? "neutral");
    if (at > worst) worst = at;
  }
  return worst < 0 ? null : (order[worst] ?? null);
}

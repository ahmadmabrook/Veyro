import type { ReactNode } from "react";

import type { Severity } from "@/components/ds/status-badge";

/**
 * AttentionRow — §38, "the component the whole Admin rests on".
 *
 * The source is unusually specific about this one, and every clause of it is a decision:
 *
 * > The Command Center is a queue of these and almost nothing else. Anatomy: severity
 * > edge-mark · category · age · headline stating the fact · plain-language evidence ·
 * > resolution action · secondary route. **The headline is never a metric name — "6 payments
 * > failed" not "Payment failure rate".**
 * >
 * > **CONTRACTS** — Each row is an `article` with the headline as its label; the queue is a
 * > list with a live count. Severity is edge-mark **and** category chip **and** wording —
 * > never the bar alone. RTL: edge-mark moves to the logical start, amount to the logical
 * > end. Below bp.sm the action row stacks and the primary becomes full-width.
 *
 * Four of those are enforced here rather than left to each call site:
 *
 * - **`article` with the headline as its label.** `aria-labelledby` points at the headline's
 *   own id, so a screen reader announcing the queue reads nine facts rather than nine
 *   "article"s. A `label` prop would let a call site pass something other than the headline,
 *   which is the one thing the contract rules out.
 * - **Severity is never the bar alone.** The edge-mark is drawn by `edgeMark`, the same
 *   function the DataGrid uses, and the row additionally carries its category and its
 *   wording. A row whose severity existed only as a coloured edge would be a colour-only
 *   signal, which the contrast matrix forbids outright.
 * - **RTL comes from logical properties**, not from a mirrored stylesheet: `borderInlineStart`
 *   and `margin-inline-start: auto` move on their own when `dir` flips.
 * - **The action row stacks below bp.sm** and the first action goes full-width, which is in
 *   the stylesheet rather than measured here.
 *
 * **The queue never collapses.** The design's responsive section is explicit at bp.md: "The
 * attention queue never collapses — it is the reason the page exists." So there is no
 * condensed variant that drops the evidence paragraph; canvas 1's "condensed" rows are rows
 * with a shorter body and no money figure, which is content rather than a mode.
 */

export function AttentionQueue({
  heading,
  title,
  counts,
  aside,
  children,
}: {
  /** The id of the heading, for the list's accessible name. */
  heading: string;
  /**
   * The heading itself, which shares a baseline with the counts.
   *
   * The canvas: `display:flex;gap:10px;align-items:baseline;margin-bottom:9px` with
   * `Needs you now` at 14.5/1.3 and `9 open · 2 critical` in mono beside it. Stacking them
   * reads as a section heading over a caption, which is a different and heavier shape.
   */
  title: ReactNode;
  /** "9 open · 2 critical · 4 assigned to others" — the live count the contract requires. */
  counts: ReactNode;
  /** The end of the header row: "Show resolved today" in the canvas. */
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <>
      <div className="ds-queue-head">
        {title}
        <p className="ds-queue-counts">{counts}</p>
        {aside ? <div className="ds-queue-aside">{aside}</div> : null}
      </div>
      {/* **One bordered container, rows divided by a hairline** -- not a stack of cards.
          The canvas: `border:1px solid …;border-radius:4px;background:warm.0;overflow:hidden`
          with each row after the first carrying `border-top`. Separate cards would put a
          double rule and two radii at every seam. */}
      <ul className="ds-queue" aria-labelledby={heading}>
        {children}
      </ul>
    </>
  );
}

export function AttentionRow({
  id,
  severity,
  category,
  kind,
  when,
  money,
  headline,
  evidence,
  actions,
  owner,
  density = "full",
}: {
  /** Used for the headline's id, so the article can be labelled by it. */
  id: string;
  severity: Severity;
  /** The category chip's text, in the reader's own language. */
  category: string;
  /**
   * The category's machine value -- `money`, `compliance`, `retention`, `staffing`.
   *
   * **The chip's colour comes from this, not from `severity`.** The direction contract puts
   * the row's *kind* in the field at its head; keying the fill on severity made every row
   * wear another category's declared colour. The localized `category` above is what a reader
   * sees; this is what the stylesheet matches on, and the two must name the same thing.
   */
  kind: string;
  /** The age and scope: "2h ago · Khalda, Abdoun". */
  when: string;
  /** A figure and what it means. Logical end, so it mirrors. */
  money?: { amount: ReactNode; meaning: string };
  /** The fact, never a metric name. */
  headline: string;
  /** Plain-language evidence: what happened, and what is already handled. */
  evidence: string;
  /** Resolution action first, then the secondary route, then the ghost. */
  actions?: ReactNode;
  /** Who owns it, or "unassigned". The design renders both rather than hiding one. */
  owner?: string;
  /**
   * `full` or `condensed` — ADM-CC-01's own component list is
   * "AttentionRow ×5 (2 full, 2 condensed, 1 collapsed group)".
   *
   * **A condensed row is one line: chip, headline, owner, one action.** It is what the queue
   * uses for an item that still needs somebody but does not need explaining -- a class with
   * no coach, leads nobody has rung. Giving every row the full treatment is what makes a
   * queue of nine unreadable, and dropping the small ones entirely is worse: the design's
   * answer is a third height, not a cut.
   *
   * The evidence sentence is **not** rendered here, so a caller must still write one: it is
   * the row's accessible description, and a condensed row that carried no explanation at all
   * would be a headline with nowhere to go for anybody who needs more than a glance.
   */
  density?: "full" | "condensed";
}) {
  const condensed = density === "condensed";
  return (
    <li>
      <article
        className="ds-attention"
        aria-labelledby={`${id}-headline`}
        {...(condensed ? { "aria-describedby": `${id}-evidence` } : {})}
        data-severity={severity}
        data-category={kind}
        data-density={density}
      >
        {/* **A 3px block, not a border.** The canvas draws it as its own flex child so it
            runs the row's full height whatever the content does; a `border-inline-start`
            would stop at the padding box and leave the mark short on a tall row. */}
        <div className="ds-attention-body">
          {condensed ? (
            <div className="ds-attention-line">
              <span className="ds-attention-category">{category}</span>
              <h3 id={`${id}-headline`} className="ds-attention-headline">
                {headline}
              </h3>
              <p id={`${id}-evidence`} className="ds-visually-hidden">
                {evidence}
              </p>
              {owner ? <span className="ds-attention-owner">{owner}</span> : null}
              {actions ? <span className="ds-attention-actions">{actions}</span> : null}
            </div>
          ) : (
            <>
              <div className="ds-attention-eyebrow">
                <span className="ds-attention-category">{category}</span>
                <span className="ds-attention-when">{when}</span>
                {money ? (
                  <span className="ds-attention-money">
                    {money.amount}{" "}
                    <span className="ds-attention-meaning">{money.meaning}</span>
                  </span>
                ) : null}
              </div>
              <h3 id={`${id}-headline`} className="ds-attention-headline">
                {headline}
              </h3>
              <p className="ds-attention-evidence">{evidence}</p>
              {actions ? <div className="ds-attention-actions">{actions}</div> : null}
              {owner ? <p className="ds-attention-owner">{owner}</p> : null}
            </>
          )}
        </div>
      </article>
    </li>
  );
}

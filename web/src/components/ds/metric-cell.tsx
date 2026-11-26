import type { ReactNode } from "react";

/**
 * MetricCell — and its `freshness` variant, which is `DS-CL-01` in the design's own change log.
 *
 * The Command Center's component list names `MetricCell ×4`, and canvas 5 needed something
 * the system did not have. The change log states the gap, the reasoning and the remedy, and
 * all three are worth quoting because they are the whole of this component:
 *
 * > **ISSUE** — Canvas 5 needs individual metrics to show their own freshness. The system
 * > specified partial data at page level (a banner naming what is stale) but gave MetricCell
 * > no way to carry provenance, so a stale figure and a live one were visually identical
 * > below the banner.
 * >
 * > **WHY THE SYSTEM COULD NOT EXPRESS IT** — A page banner is the right container for the
 * > explanation but the wrong granularity for the data. Mixing fresh and stale numbers in one
 * > grid with a single caveat above them invites exactly the misreading the money rules exist
 * > to prevent — a manager quoting a stale collections figure as current.
 * >
 * > **CLASSIFICATION & SOLUTION** — Missing variant, not a defect. Smallest reusable
 * > extension: MetricCell gains `freshness: live | stale | unavailable`. Stale demotes the
 * > value from text.primary to text.secondary and replaces the comparison line with a
 * > timestamp in warning. No new token, no new colour — existing semantic tokens in a new
 * > arrangement.
 * >
 * > **ACCESSIBILITY IMPACT** — Positive and required: freshness must be in the accessible
 * > name — "collected month to date, 41,280 dinars, as of 08:00" — because the visual
 * > demotion alone is a colour-and-weight signal.
 *
 * So `provenance` is rendered as text inside the cell rather than as a title attribute or a
 * colour: the accessibility requirement is explicit and it is the reason the variant was
 * filed rather than solved with a shade of grey.
 *
 * **`unavailable` is the third value and this build needs it most.** The design uses it for a
 * figure the pipeline cannot supply; here it is the honest state for ADM-CC-01's fourth
 * metric, lead conversion, which has no module behind it at all. A cell rendering `0%` or an
 * em-dash would both read as a measurement.
 *
 * **The value does not carry severity.** Canvas 3's note, during an outage: "Why the metrics
 * stay neutral: 48 people in the building is a fact, not a problem, and colouring it red
 * during an unrelated outage teaches staff to distrust the colour. Only the outage and its
 * direct consequence carry severity." There is no `severity` prop, deliberately.
 *
 * ## What the redesign changed, and why the product reasoning above is untouched
 *
 * Every decision in this docstring is a *product* decision and all of them stand. What moved
 * is the arrangement, on two counts the craft floor names by hand:
 *
 * **The label is beneath the figure, not above it.** A small tracked label above a heading is
 * a kicker, which is banned outright -- "the heading carries its own weight; delete the label
 * and let the heading speak". Here the figure *is* the heading, so the label becomes what it
 * actually is: the unit and the period the figure is in, read after the number rather than
 * before it. A screen reader gets "JOD 72.20, collected month to date", which is the sentence
 * a person would say.
 *
 * **There is no tile.** The retired row was "a bordered grid whose 1px gaps are the
 * dividers", which is the hero-metric template -- big number, small label, supporting stats,
 * a box -- and a border around a number is a substitute for having decided it matters. The
 * figures sit on a shared baseline in the open, separated by space, and the one rule on the
 * row is the 2px line under it that closes the group.
 */

export type Freshness = "live" | "stale" | "unavailable";

export function MetricCell({
  label,
  value,
  comparison,
  /** The delta's own tone: `up`, `down` or none. Semantic colour, never the value's. */
  delta,
  freshness = "live",
  provenance,
  unavailableBecause,
}: {
  /** The eyebrow: "COLLECTED · MONTH TO DATE". Mono, tracked, uppercase. */
  label: string;
  /** The figure. Mono at 21px — `MoneyValue(aggregate)` where it is money. */
  value?: ReactNode;
  /** The line under the value: "vs July · pace to 63.1k". */
  comparison?: ReactNode;
  /** "↓ 7.8%" — set in the semantic tone its direction earns. */
  delta?: { text: string; tone: "up" | "down" };
  freshness?: Freshness;
  /** When stale: what the figure is as of. Rendered as text, per the accessibility note. */
  provenance?: string;
  /** When unavailable: why. Rendered in place of the figure, never beside a zero. */
  unavailableBecause?: string;
}) {
  const stale = freshness === "stale";
  const missing = freshness === "unavailable";
  return (
    <div className="ds-metric" data-freshness={freshness}>
      {missing ? (
        // Not a zero and not an em-dash. `MoneyValue`'s own rule for a figure nobody may see
        // -- "never blank, never zero" -- generalised to a figure nobody can compute. The
        // label still leads here, because there is no figure for it to follow.
        <>
          <div className="ds-metric-label">{label}</div>
          <p className="ds-metric-unavailable">{unavailableBecause}</p>
        </>
      ) : (
        <>
          <div className="ds-metric-value ds-figure">{value}</div>
          <div className="ds-metric-label">{label}</div>
          {stale ? (
            // "Replaces the comparison line with a timestamp in warning." The comparison is
            // not shown beside a stale figure at all: a change computed from a figure that is
            // forty minutes old is a change nobody can act on.
            <div className="ds-metric-provenance">{provenance}</div>
          ) : (
            delta !== undefined || comparison !== undefined ? (
              // The canvas: `display:flex;gap:7px;align-items:baseline;margin-top:5px`, the
              // delta in mono and the sentence beside it in sans.
              <div className="ds-metric-comparison">
                {delta ? (
                  <span className="ds-metric-delta data" data-tone={delta.tone}>
                    {delta.text}
                  </span>
                ) : null}
                {comparison !== undefined ? <span>{comparison}</span> : null}
              </div>
            ) : null
          )}
        </>
      )}
    </div>
  );
}

/**
 * The metric row. Four figures at bp.lg, 2×2 at bp.md, stacked at bp.xs.
 *
 * **Space separates them, not rules.** The figures share a baseline and sit in the open; the
 * group is closed by one 2px line beneath it. The retired row drew a bordered grid whose 1px
 * gaps were the dividers, which boxed each figure -- see the note on `MetricCell`.
 *
 * **It does not scroll sideways at any width.** The design made its one exception to its own
 * rule here, on the grounds that the cells "are peers with no comparison axis", and that
 * exception was for cells in a scrolling grid. A figure at this scale does not need one: at
 * phone width the row stacks and each figure drops to `type.figureSm`, which is the same
 * reading in a column. The sideways-scroll sweep covers every surface in this app and a
 * deliberate exception is the kind of thing that stops being deliberate.
 */
export function MetricRow({
  children,
  label,
}: {
  children: ReactNode;
  label: string;
}) {
  // **No `columns` prop.** It set `--metric-columns` on a four-track grid, and a cell count
  // is the wrong instrument: the figures differ in width because their *content* does, and an
  // equal track forced the widest -- money, which carries a currency code -- to the same
  // width as "8". The row is a flex line now, so each figure takes what it needs and the cell
  // with no figure absorbs the rest. Callers that passed 3, 4 or 5 were describing how many
  // cells they had, which the row can see for itself.
  return (
    <div className="ds-metric-row" role="group" aria-label={label}>
      {children}
    </div>
  );
}

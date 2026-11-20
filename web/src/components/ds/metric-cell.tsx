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
 */

export type Freshness = "live" | "stale" | "unavailable";

export function MetricCell({
  label,
  value,
  comparison,
  freshness = "live",
  provenance,
  unavailableBecause,
}: {
  /** The eyebrow: "COLLECTED · MONTH TO DATE". */
  label: string;
  /** The figure, already formatted in the locale's own numerals. */
  value?: ReactNode;
  /** The line under the value: "↓ 7.8% vs July · pace to 63.1k". */
  comparison?: ReactNode;
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
      <div className="ds-metric-label">{label}</div>
      {missing ? (
        // Not a zero and not an em-dash. `MoneyValue`'s own rule for a figure nobody may see
        // -- "never blank, never zero" -- generalised to a figure nobody can compute.
        <p className="ds-metric-unavailable">{unavailableBecause}</p>
      ) : (
        <>
          {/* `.data` is tabular and mono, which is what makes four of these align. */}
          <div className="ds-metric-value data">{value}</div>
          {stale ? (
            // "Replaces the comparison line with a timestamp in warning." The comparison is
            // not shown beside a stale figure at all: a change computed from a figure that is
            // forty minutes old is a change nobody can act on.
            <div className="ds-metric-provenance">{provenance}</div>
          ) : (
            comparison !== undefined ? (
              <div className="ds-metric-comparison">{comparison}</div>
            ) : null
          )}
        </>
      )}
    </div>
  );
}

/**
 * The metric row. Four cells at bp.lg, 2×2 at bp.md, one horizontally scrolling row at bp.sm.
 *
 * That last one is the design's single exception to its own rule, and it says why: "Metrics
 * scroll horizontally as a single row of cards — the one place horizontal scroll is right,
 * because they are peers with no comparison axis." Everywhere else in this build a horizontal
 * scrollbar on data is the defect the DataGrid's column priority exists to remove.
 */
export function MetricRow({
  children,
  label,
}: {
  children: ReactNode;
  label: string;
}) {
  return (
    <div className="ds-metric-row" role="group" aria-label={label}>
      {children}
    </div>
  );
}

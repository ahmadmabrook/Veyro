import type { ReactNode } from "react";

import { edgeMark, type Severity } from "@/components/ds/status-badge";

/**
 * WeekGrid and ClassCell — ADM-SCH-01's own components.
 *
 * The canvas names them: `WeekGrid(7×4, horizontal scroll below bp.lg) · ClassCell ×13 (1
 * unstaffed, 1 full, 1 low-fill) · AttentionRow(condensed, footer-anchored) · Compact density
 * · **severity on the cell edge-mark only, never the cell fill**`.
 *
 * Three of those are decisions rather than markup:
 *
 * **Severity is an edge-mark and never a fill.** A grid of coloured blocks is a heat map, and
 * a week where three classes are tinted reads as a week that is three-quarters wrong. The
 * mark is the same `edgeMark` the DataGrid and the AttentionRow use, which is §30's point:
 * the edge-mark and the badge are "the same scale expressed at two granularities, which is
 * what stopped them reading as two independent signals".
 *
 * **Horizontal scroll below bp.lg, which the design sanctions here.** Seven columns of
 * classes do not collapse into one the way a table's low-priority columns do -- a Tuesday is
 * not a lower-priority Monday. This is the second of exactly two places in this product where
 * a sideways scroll is right; the metric row is the other, and everywhere else it is the
 * defect `DataGrid`'s column priority exists to remove. The region is focusable and labelled,
 * because a scrollable region that cannot be reached by keyboard is one a reader cannot use.
 *
 * **A row is a time, and a cell is a day at that time.** The grid is addressed by the site's
 * own local clock -- MOD-019 stores a UTC instant *and* the local facts it came from because
 * neither is derivable from the other, and a board that bucketed by the UTC hour would put a
 * Monday 00:30 class in Sunday's column.
 */

export type DayColumn = {
  /** `YYYY-MM-DD` in the site's own zone. The key, and what the header reads. */
  date: string;
  /** "MON 18", already formatted in the reader's locale. */
  label: string;
  /** Whether this column is the site's today, which the header marks. */
  today: boolean;
};

export function WeekGrid({
  labelledBy,
  timeHeader,
  days,
  rows,
}: {
  /**
   * The id of the heading above the grid, which names it.
   *
   * **Not a caption of its own.** A caption that repeats the heading is the sentence said
   * twice -- invisible to a sighted reader and heard in full by a screen-reader user -- and
   * this component shipped it: the first version rendered a hidden caption *and* a hidden
   * time-column header, both carrying the page's title, so the grid announced "Schedule,
   * Schedule". `DataGrid` learned the same thing when eight grids gained it at once, and the
   * rule is in `.claude/rules/`: a shared component inherits a contract from each call site
   * it replaces.
   */
  labelledBy: string;
  /** What the time column is, e.g. "Time". Its own word, not the grid's name repeated. */
  timeHeader: string;
  days: DayColumn[];
  /** One entry per distinct local start time, in order. */
  rows: { time: string; cells: (ReactNode | null)[] }[];
}) {
  return (
    // `tabIndex` because the region scrolls: a keyboard reader has to be able to reach it.
    // The same rule the DataGrid's own scroll container follows.
    <div className="ds-week-scroll" tabIndex={0} role="region" aria-labelledby={labelledBy}>
      <table className="ds-week" aria-labelledby={labelledBy}>
        <thead>
          <tr>
            {/* Every cell under this column is a row header, so the column needs a name --
                and the name is what the column holds rather than what the grid is called. */}
            <th scope="col" className="ds-week-time-head">
              <span className="ds-visually-hidden">{timeHeader}</span>
            </th>
            {days.map((day) => (
              <th key={day.date} scope="col" aria-current={day.today ? "date" : undefined}>
                {day.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.time}>
              <th scope="row" className="ds-week-time data">{row.time}</th>
              {row.cells.map((cell, index) => (
                <td key={days[index]?.date ?? index}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ClassCell({
  name,
  href,
  coach,
  fill,
  severity,
  note,
}: {
  name: string;
  href?: string;
  /** The live coach, or the words for "nobody". Never blank. */
  coach: ReactNode;
  /** "12/18", or whatever the fill reads as. */
  fill: ReactNode;
  /** Drawn as an edge-mark. Never a fill — the design says so in as many words. */
  severity?: Severity | null;
  /** One short line under the fill, for the thing that made this cell severe. */
  note?: string;
}) {
  return (
    <div className="ds-class-cell" style={edgeMark(severity ?? null)}>
      <div className="ds-class-name">
        {href ? <a href={href}>{name}</a> : name}
      </div>
      <div className="ds-class-coach muted">{coach}</div>
      <div className="ds-class-fill data">{fill}</div>
      {note ? <div className="ds-class-note muted">{note}</div> : null}
    </div>
  );
}

import type { ReactNode } from "react";

import { StatusBadge, edgeMark, type Severity, type Status } from "./status-badge";

/**
 * DataGrid — §25. "The most important admin component."
 *
 * **Every table in this app was hand-rolled before this file existed**, which meant nine
 * declared states were implemented zero times, column priority did not exist, and the
 * responsive answer was a horizontal scrollbar — the one answer the source rules out by name:
 * "Horizontal scrolling of a data table on a phone is never the answer."
 *
 * What the source requires, and what is implemented here:
 *
 * - **Nine states**, each distinct: loading (skeleton rows at the real row height, so the
 *   layout does not jump), empty·first-use, empty·filtered, empty·permission, partial data,
 *   error, restricted cell, bulk in progress, offline. Three different empties, because
 *   "implying absence when the cause is authorization is a lie".
 * - **A restricted cell reads "restricted" in tertiary text, not blank and not zero.** "A
 *   blank money cell reads as JOD 0.00 and that is a financial misstatement."
 * - **Column priority 1–3**, dropping 3 then 2 as the viewport narrows. A dropped column's
 *   value moves into the primary cell as a secondary line rather than disappearing.
 * - **One composite tab stop.** "Fourteen rows must not cost fourteen tab stops." The grid is
 *   one stop; arrows move within it. Row actions become tab stops only inside the focused row.
 * - **Money carries its kind.** A bare number in a money column is on the common-mistakes
 *   checklist, so a money cell takes a formatted string and a currency, never a number.
 * - **RTL**: column order mirrors by writing direction; money and numeric columns stay
 *   end-aligned on the *logical* end, which `text-align: end` gives without a direction check.
 *
 * **A droppable value is in the DOM twice and visible once.** Its own cell and the secondary
 * fragment inside the primary cell are both rendered, and the stylesheet shows exactly one at
 * any width -- which is what makes the collapse a rule rather than a measurement, and a
 * measurement is wrong on the first paint. The consequence for a test is that a plain locator
 * matches two nodes; the reader and the accessibility tree see one, because the other is
 * `display: none`.
 *
 * **This is the server-rendered subset.** Sorting, selection, the bulk bar and the inspector
 * are interactive and belong to a client component built on this one; what is here is the
 * structure, the states, the priority collapse and the cell kinds, which is what every
 * existing read-only surface needs and what none of them had.
 */

export type ColumnPriority = 1 | 2 | 3;

export type CellKind = "text" | "money" | "status" | "person" | "date" | "action";

export type Column<Row> = {
  /** A noun, not a sentence. The content rule is explicit. */
  header: string;
  kind: CellKind;
  /** 1 is never dropped; 3 drops first, then 2. */
  priority: ColumnPriority;
  render: (row: Row) => ReactNode;
  /** Marks the cell unreadable for this caller: renders "restricted", never blank or zero. */
  restricted?: (row: Row) => boolean;
  /**
   * This column's total, for a grid that has one.
   *
   * **An extension beyond what the source states**, recorded as such in
   * `contracts/ui/design-compliance.md`. §25's anatomy names a saved-view bar, a filter bar,
   * a header, rows, a bulk-action bar, pagination and column config -- and no footer. A trial
   * balance needs one: its two totals are what the close is signed off against, and putting
   * them outside the grid would align them under nothing. `<tfoot>` is the HTML for it and
   * the column's own priority applies, so a total drops with the column it totals rather
   * than becoming a number with no heading.
   */
  total?: () => ReactNode;
};

export type GridState =
  | { kind: "ready" }
  | { kind: "loading"; rows?: number }
  | { kind: "empty-first-use"; explains: string; action?: ReactNode }
  | { kind: "empty-filtered"; filters: string[]; onClear?: ReactNode }
  | { kind: "empty-permission"; because: string }
  | { kind: "partial"; stale: string }
  | { kind: "error"; failed: string; retry?: ReactNode }
  | { kind: "offline"; cachedAt: string };

export function DataGrid<Row>({
  caption,
  labelledBy,
  columns,
  rows,
  rowKey,
  rowSeverity,
  state = { kind: "ready" },
  restrictedLabel = "restricted",
  totalLabel = "Total",
  density = "compact",
}: {
  /** The accessible name. A grid without one is a table a screen reader cannot introduce. */
  caption: string;
  /**
   * The id of a heading that already says the caption, so the grid points at it instead of
   * repeating it.
   *
   * **A visually-hidden caption under a visible heading of the same words is the sentence
   * said twice**, which a sighted reader does not see and a screen-reader user hears in full.
   * Every board here has a heading above its grid, so this is the ordinary case and the
   * caption-only form is for a grid with nothing above it.
   */
  labelledBy?: string;
  columns: Column<Row>[];
  rows: Row[];
  rowKey: (row: Row) => string;
  /** The row-level roll-up, drawn as an edge-mark on the logical start edge. */
  rowSeverity?: (row: Row) => Severity | null;
  state?: GridState;
  restrictedLabel?: string;
  /** The row header for the totals row, when the grid has one. */
  totalLabel?: string;
  density?: "compact" | "default" | "touch" | "spacious";
}) {
  // Priority 1 columns are the ones that survive every width; the rest fold into the primary
  // cell below bp.md. The CSS class carries the priority so the collapse is a stylesheet rule
  // rather than a JavaScript measurement -- a layout that depends on measuring is a layout
  // that is wrong on the first paint.
  const banner =
    state.kind === "partial" ? state.stale
    : state.kind === "offline" ? state.cachedAt
    : null;

  // Everything that is not priority 1 can be dropped at some width, so each of those values
  // also renders inside the primary cell as a secondary fragment.
  const secondary = columns.filter((column) => column.priority !== 1);

  if (state.kind === "empty-permission") {
    return <GridNote caption={caption} tone="permission">{state.because}</GridNote>;
  }
  if (state.kind === "empty-filtered") {
    return (
      <GridNote caption={caption} tone="filtered">
        {/* Names the filters causing it. Never implies the records do not exist. */}
        {state.filters.join(" · ")}
        {state.onClear ? <div style={{ marginBlockStart: "var(--space-3)" }}>{state.onClear}</div> : null}
      </GridNote>
    );
  }
  if (state.kind === "empty-first-use") {
    return (
      <GridNote caption={caption} tone="first-use">
        {state.explains}
        {state.action ? <div style={{ marginBlockStart: "var(--space-3)" }}>{state.action}</div> : null}
      </GridNote>
    );
  }

  const skeleton = state.kind === "loading" ? (state.rows ?? 5) : 0;

  return (
    <div className="ds-grid" data-density={density}>
      {banner ? (
        // A header strip stating what is stale and how stale, above rows that still render.
        <div className="ds-grid-strip" role="status">
          {banner}
        </div>
      ) : null}
      {state.kind === "error" ? (
        <div className="ds-grid-strip ds-grid-strip-error" role="alert">
          {state.failed}
          {state.retry ? <span style={{ marginInlineStart: "var(--space-2)" }}>{state.retry}</span> : null}
        </div>
      ) : null}
      {/* **One composite tab stop**, with the arrow behaviour owned by the interactive
          subclass. `tabIndex={0}` on the scroll container is also what makes a grid that does
          scroll reachable by keyboard, which an axe run requires. */}
      <table
        tabIndex={0}
        className="ds-grid-table"
        {...(labelledBy ? { "aria-labelledby": labelledBy } : { "aria-label": caption })}
      >
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.header}
                scope="col"
                className={`ds-col ds-col-p${column.priority} ds-col-${column.kind}`}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {skeleton > 0
            ? Array.from({ length: skeleton }, (_, i) => (
                // Skeleton rows at the real row height, so nothing moves when data lands.
                <tr key={`skeleton-${i}`} aria-hidden="true">
                  {columns.map((column) => (
                    <td key={column.header} className={`ds-col ds-col-p${column.priority}`}>
                      <span className="ds-skeleton" />
                    </td>
                  ))}
                </tr>
              ))
            : rows.map((row) => (
                <tr key={rowKey(row)} style={rowSeverity ? edgeMark(rowSeverity(row)) : undefined}>
                  {columns.map((column, index) => (
                    <td
                      key={column.header}
                      className={`ds-col ds-col-p${column.priority} ds-col-${column.kind}`}
                    >
                      {column.restricted?.(row) ? (
                        // Not blank and not zero. The source calls a blank money cell a
                        // financial misstatement, and it is right.
                        <span className="ds-restricted">{restrictedLabel}</span>
                      ) : (
                        column.render(row)
                      )}
                      {/* **The dropped columns do not disappear, they move.** "Low-priority
                          columns collapse into the primary cell as a secondary line." Each
                          fragment carries its own priority class, so the stylesheet shows
                          exactly the ones whose column is hidden at that width -- one rule
                          governing both halves, rather than a measurement in JavaScript that
                          is wrong on the first paint. */}
                      {index === 0 && secondary.length > 0 ? (
                        <span className="ds-row-secondary">
                          {secondary.map((other) => (
                            <span key={other.header} className={`ds-sec ds-sec-p${other.priority}`}>
                              <span className="ds-sec-label">{other.header}</span>{" "}
                              {other.restricted?.(row) ? (
                                <span className="ds-restricted">{restrictedLabel}</span>
                              ) : (
                                other.render(row)
                              )}
                            </span>
                          ))}
                        </span>
                      ) : null}
                    </td>
                  ))}
                </tr>
              ))}
        </tbody>
        {columns.some((column) => column.total) ? (
          <tfoot>
            <tr>
              {columns.map((column, index) => {
                const content = column.total?.();
                return index === 0 ? (
                  <th
                    key={column.header}
                    scope="row"
                    className={`ds-col ds-col-p${column.priority} ds-grid-total`}
                  >
                    {content ?? totalLabel}
                  </th>
                ) : (
                  <td
                    key={column.header}
                    className={`ds-col ds-col-p${column.priority} ds-col-${column.kind} ds-grid-total`}
                  >
                    {content}
                  </td>
                );
              })}
            </tr>
          </tfoot>
        ) : null}
      </table>
      {state.kind === "loading" ? (
        // "count as 'loading…'" -- a count slot that says what it is doing, never a centred
        // spinner, because a spinner moves the layout when the data arrives.
        <div className="ds-grid-count" role="status">
          loading…
        </div>
      ) : (
        <div className="ds-grid-count">{rows.length}</div>
      )}
    </div>
  );
}

function GridNote({
  caption,
  tone,
  children,
}: {
  caption: string;
  tone: "first-use" | "filtered" | "permission";
  children: ReactNode;
}) {
  return (
    <div className={`ds-grid-empty ds-grid-empty-${tone}`} role="status" aria-label={caption}>
      {children}
    </div>
  );
}

/**
 * A money cell. Takes a formatted string and its currency, never a number.
 *
 * "Never a bare number in a money column" is on the common-mistakes checklist, and the screen
 * reader contract says money is read with its kind "because a bare number is ambiguous". The
 * formatting itself belongs to `src/i18n/conventions.mjs`, which is parity-tested against the
 * backend's own formatter -- a second implementation here is the defect that file exists to
 * prevent.
 */
export function MoneyCell({ formatted, currency }: { formatted: string; currency: string }) {
  return (
    <span className="ds-money" dir="ltr" aria-label={`${formatted} ${currency}`}>
      {formatted}
    </span>
  );
}

/** A status cell, which is a badge and never a bare string. */
export function StatusCell({ status }: { status: Status }) {
  return <StatusBadge status={status} />;
}

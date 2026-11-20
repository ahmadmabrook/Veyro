import type { ReactNode } from "react";

/**
 * ADM-STF-04's permission matrix — "Nine roles, and what each may actually do".
 *
 * The canvas:
 *
 * > CAPABILITY · {{ r.short }} · {{ x.mark }}
 * > LEGEND — ● can do · ◐ can request approval · — not available, and absent from their UI
 * > entirely
 * >
 * > The ◐ column is the one this product argued for: a receptionist who can *ask* for a
 * > refund is faster than one who phones a manager, and safer than one who can issue it.
 *
 * **What this app rendered instead was every role's raw permission list**, comma-separated
 * and grouped by module — 4,300 pixels of identifier on one page, with no way to compare two
 * roles at all, which is the entire question the screen exists to answer. The matrix is the
 * screen; the lists were the data under it.
 *
 * **The middle mark means something different here, and the legend says so.** The design's ◐
 * is "can request approval", which MOD-008 has as a workflow but not as a per-role fact: an
 * approval request needs the requester to hold the action's own permission, so no role is
 * "request-only". What this build does have in that middle position is a permission a role
 * holds that it cannot exercise on an ordinary sign-in — `catalog.action_class` is
 * `financial` or `privileged`, which needs assurance level 2 or 3 — and that is a real and
 * frequently surprising third state: holding the permission is not enough. The caller passes
 * the legend text, so the adaptation is stated on the page rather than hidden in a glyph.
 *
 * **Every mark carries a word.** A cell is a glyph *and* a visually-hidden label, because a
 * matrix read by a screen reader as "● ● — ●" is a matrix nobody can read. The design's own
 * rule, stated for icons: they never carry meaning alone.
 */

export type Mark = "yes" | "partial" | "stepUp" | "no" | "unreachable";

const GLYPH: Record<Mark, string> = {
  yes: "●",
  // Holds some of what the row covers. Only a module row can be this: a single permission is
  // held or it is not, and rendering "some" as either of the other two would be a lie about
  // a role -- in a matrix of modules it is also the commonest case.
  partial: "◑",
  stepUp: "◐",
  no: "—",
  // A permission nobody in this build can exercise at any assurance. Distinct from "not
  // held", because the remedy is different: there is none.
  unreachable: "⊘",
};

export function CapabilityMatrix<R extends { key: string; display: string }>({
  caption,
  labelledBy,
  columns,
  rows,
  mark,
  markLabel,
  legend,
}: {
  caption: string;
  labelledBy: string;
  /** The roles. Short names, because every one is a column heading. */
  columns: R[];
  /** The capabilities: a name, a description and a stable key. */
  rows: { key: string; name: ReactNode; detail?: ReactNode }[];
  mark: (rowKey: string, column: R) => Mark;
  /** The word for a mark, which is what a screen reader hears. */
  markLabel: (value: Mark) => string;
  legend: ReactNode;
}) {
  return (
    <>
      {/* The table scrolls rather than the page: a matrix is the one shape whose columns
          cannot be dropped at a narrow width, because dropping a role is dropping the
          comparison. `tabindex` makes the scroll region keyboard-reachable, which is what
          the phone suite's axe run requires of any scrollable element. */}
      <div className="ds-matrix-scroll" tabIndex={0} role="group" aria-labelledby={labelledBy}>
        <table className="ds-matrix">
          <caption className="ds-visually-hidden">{caption}</caption>
          <thead>
            <tr>
              <th scope="col" className="ds-matrix-rowhead">
                {/* The canvas's own heading for the first column. */}
                <span className="ds-matrix-eyebrow">CAPABILITY</span>
              </th>
              {columns.map((column) => (
                <th key={column.key} scope="col" className="ds-matrix-colhead">
                  {column.display}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key}>
                <th scope="row" className="ds-matrix-rowhead">
                  <span className="ds-matrix-name">{row.name}</span>
                  {row.detail === undefined ? null : (
                    <span className="ds-matrix-detail">{row.detail}</span>
                  )}
                </th>
                {columns.map((column) => {
                  const value = mark(row.key, column);
                  return (
                    <td key={column.key} className="ds-matrix-cell" data-mark={value}>
                      <span aria-hidden="true">{GLYPH[value]}</span>
                      <span className="ds-visually-hidden">{markLabel(value)}</span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="ds-matrix-legend">{legend}</p>
    </>
  );
}

export { GLYPH as MATRIX_GLYPH };

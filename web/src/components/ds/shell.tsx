import type { ReactNode } from "react";

/**
 * The Veyro Admin shell — `LAYOUTS` in Foundations, quoted exactly:
 *
 * > 12-column, 24px gutter. Rail 240 expanded / 56 collapsed. Content max 1440. Inspector 380
 * > at bp.lg, 480 at bp.xl. Split view is list + inspector, never three columns — the Member
 * > 360 decision from Phase 6 generalised.
 *
 * **None of that existed.** Every page in this app rendered a horizontal strip of links over a
 * single column capped at 960px — a shell nobody specified, on fifteen screens, while those
 * numbers sat in `ds.json` extracted and unused. The rail, the inspector and the content cap
 * are the three that change what a screen can be: a list-and-inspector surface is not
 * expressible in a 960px column, so every screen that wanted one became a page of stacked
 * panels instead.
 *
 * The breakpoint behaviour is the source's, per `BREAKPOINTS`:
 *
 * - **bp.xl (1600+)** — content caps at 1440 and centres; the inspector widens to 480 "rather
 *   than the table stretching indefinitely".
 * - **bp.lg (1200–1599)** — the Admin target. Rail expanded at 240, content and inspector side
 *   by side.
 * - **bp.md (900–1199)** — "Admin usable: rail collapsed, inspector becomes an overlay rather
 *   than a column."
 * - **bp.sm (600–899)** — rail collapses to icons.
 * - **bp.xs (0–599)** — single column; the rail becomes a bottom nav of five and sheets
 *   replace modals.
 *
 * Every length is a generated token, so the numbers are the design source's parsed values
 * rather than literals retyped here. The media-query breakpoints are literal because a media
 * query cannot read a custom property; `tests/unit/shell-tokens.test.mjs` compares those
 * literals against `--bp-*` so the two cannot drift.
 *
 * **Never three columns.** The inspector slot exists and there is no second one; a screen that
 * wants a third pane has an information-architecture problem, which is what the Member 360
 * decision settled.
 */
export function AdminShell({
  rail,
  children,
  inspector,
  banner,
}: {
  /** The rail of eight, generated from role and scope. Not a static tree with disabled rows. */
  rail: ReactNode;
  children: ReactNode;
  /** The list-and-inspector second pane. Absent on a single-pane screen. */
  inspector?: ReactNode;
  /** The global banner slot: fixed, above the rail, and it does not scroll away. */
  banner?: ReactNode;
}) {
  return (
    <div className="ds-shell" data-has-inspector={inspector ? "true" : "false"}>
      {banner ? <div className="ds-shell-banner">{banner}</div> : null}
      <div className="ds-shell-body">
        <nav className="ds-shell-rail" aria-label="Sections">
          {rail}
        </nav>
        <div className="ds-shell-content">
          <div className="ds-shell-main">{children}</div>
          {inspector ? (
            <aside className="ds-shell-inspector" aria-label="Details">
              {inspector}
            </aside>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/**
 * The 12-column grid, for screens that lay out across it.
 *
 * The gutter is `--shell-gutter`, parsed from the layout line rather than chosen. A child
 * spans columns with `gridColumn: "span N"`; nothing here invents a second grid system.
 */
export function GridRow({ children }: { children: ReactNode }) {
  return <div className="ds-grid-12">{children}</div>;
}

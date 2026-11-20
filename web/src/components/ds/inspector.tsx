import Link from "next/link";
import type { ReactNode } from "react";

/**
 * Pattern 02 — list → inspector, which the design's own pattern table defines and names four
 * screens for:
 *
 * > **Components** — DataGrid or PersonRow list · Drawer inspector · timeline spine inside.
 * > **Rule** — Two panes, never three. The list keeps its scroll and selection when the
 * > inspector closes. Member 360, lead detail, invoice detail and staff detail are all this —
 * > the Phase 6 decision, generalised.
 *
 * This app had one pane: opening a member replaced the list with the record, so going back to
 * the queue meant a navigation and the position was whatever the list route's default order
 * gave. ADM-MEM-01 is drawn as the queue it was opened from, pinned, with the member beside
 * it and the selected row marked -- which is what makes "6 of 4,812 · sorted by amount" and
 * the footer's "list keeps position" true.
 *
 * **The keyboard line the canvas prints is `↑↓ moves · ⏎ opens · list keeps position`, and
 * two of those three are what a list of links already does.** `⏎` opens the focused link and
 * `Tab` moves between them; `↑↓` is a listbox behaviour that would need client JavaScript and
 * would then have to re-implement focus, selection and announcement correctly. So the footer
 * here names what the pane actually does rather than quoting a key that does nothing -- a
 * printed shortcut that is not bound is the same defect as a button that answers 403.
 *
 * The canvas's measurements: the list pane is 300px with a `warm.0` ground and a 1px end
 * border, the inspector `flex:1;min-width:0` on the `warm.100` canvas, and the whole thing
 * collapses to one column below `bp.md` -- where the list becomes a link back to the queue
 * rather than a 300px column squeezed into 375.
 */

export function Inspector({
  list,
  children,
}: {
  /** The pinned pane. Absent is not an option: pattern 02 is two panes. */
  list: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="ds-inspector">
      {list}
      <div className="ds-inspector-pane">{children}</div>
    </div>
  );
}

export function InspectorList({
  title,
  counts,
  footer,
  children,
  label,
}: {
  title: ReactNode;
  /** "6 of 4,812 · sorted by amount" — mono, under the title. */
  counts?: ReactNode;
  footer?: ReactNode;
  label: string;
  children: ReactNode;
}) {
  return (
    <aside className="ds-inspector-list" aria-label={label}>
      <div className="ds-inspector-list-head">
        <span className="ds-inspector-list-title">{title}</span>
        {counts === undefined ? null : (
          <p className="ds-inspector-list-counts data">{counts}</p>
        )}
      </div>
      <ul className="ds-person-list">{children}</ul>
      {footer === undefined ? null : (
        <p className="ds-inspector-list-foot">{footer}</p>
      )}
    </aside>
  );
}

/**
 * `PersonRow` — the design's own component, 52px tall with a 28px avatar ground, the name at
 * 450 12.5 and a mono sub-line under it, and a figure at the end.
 *
 * **The figure is end-aligned and logical**, so it mirrors in Arabic rather than staying on
 * the right of a right-to-left row.
 */
export function PersonRow({
  href,
  name,
  detail,
  figure,
  current,
}: {
  href: string;
  name: ReactNode;
  /** "Club · expired card" — mono, tertiary. */
  detail?: ReactNode;
  /** The amount, the date, whatever the list is sorted by. */
  figure?: ReactNode;
  current?: boolean;
}) {
  return (
    <li>
      <Link
        className="ds-person-row"
        href={href}
        {...(current ? { "aria-current": "page" as const } : {})}
      >
        <span className="ds-person-avatar" aria-hidden="true" />
        <span className="ds-person-text">
          <span className="ds-person-name">{name}</span>
          {detail === undefined ? null : (
            <span className="ds-person-detail data">{detail}</span>
          )}
        </span>
        {figure === undefined ? null : (
          <span className="ds-person-figure">{figure}</span>
        )}
      </Link>
    </li>
  );
}

import type { ReactNode } from "react";

import { Icon } from "@/components/ds/icon";

/**
 * The global chrome — §21's first layer, and the bar the Command Center canvas is drawn under.
 *
 * > Global chrome: scope switcher, ⌘K, tasks, alerts, account.
 *
 * The canvas gives it exact dimensions, and they are the ones here:
 *
 *     height:48px · padding:0 16px · gap:14px · background: warm.0
 *     logo tile   22×22, radius 4, warm.900 ground, 12/22 500, tracking -.02em
 *     org name    13.5/1.2 500, tracking -.012em
 *     divider     1×20, rgba(23,23,26,.14)
 *     scope       12/1, 1px border, 7px 10px, radius 6, gap 7
 *     search      392 wide, centred, 12/1, warm.50 ground, 8px 12px, radius 6
 *     ⌘K chip     10px mono, 1px border, 2px 5px, radius 3
 *     tasks       11.5/1 with a warm.900 count chip, 10px mono
 *     avatar      26×26 circle, warm.300 ground
 *
 * **Three of the five are not rendered, and that is the rule rather than an omission.** A
 * control that does nothing is worse than one that is absent -- ADM-MEM-05's own finding,
 * applied to the chrome:
 *
 * - **Search and ⌘K** need ENG-01's permission-aware index with a mandatory query pre-filter.
 *   MOD-014 refuses to ship a `LIKE` scan presented as search, and a box that swallowed a
 *   query and returned nothing would be worse than the gap it hides.
 * - **Tasks and Alerts** have no module. There is no task in this product.
 * - **The scope switcher is rendered as a statement, not a control.** Every `permit` call in
 *   this build is tenant-wide -- MOD-014 records it as its own gap -- so "All locations" is
 *   true and a menu offering to narrow it would be offering something the gate cannot do.
 *   The caret is absent for the same reason: it is the affordance that makes it a control.
 *
 * What is here is the half that works: the mark, the tenant, the scope as a fact, and the
 * account. Each absent piece is named on the Command Center's own gaps list.
 */

export function Chrome({
  mark,
  organization,
  scope,
  children,
}: {
  /** One or two letters on the logo tile. The tenant's initial, not a brand asset. */
  mark: string;
  organization: string;
  /** "All locations" — a statement in this build, which the gaps list explains. */
  scope: string;
  /** The account end of the bar: language, theme, the avatar. */
  children: ReactNode;
}) {
  return (
    <div className="ds-chrome">
      <div className="ds-chrome-brand">
        <span className="ds-chrome-mark" aria-hidden="true">{mark}</span>
        <span className="ds-chrome-org">{organization}</span>
      </div>
      <span className="ds-chrome-divider" aria-hidden="true" />
      {/* Not a button and not a menu: there is nothing to switch to. */}
      <span className="ds-chrome-scope">{scope}</span>
      <div className="ds-chrome-end">{children}</div>
    </div>
  );
}

/**
 * A rail group — `OPERATE`, `PEOPLE`, `MONEY`, `DELIVER`.
 *
 * The canvas groups thirteen items under four headings, which is what makes a rail of that
 * length readable: a flat list of thirteen is a list, and four groups of three is a shape.
 */
export function RailGroup({
  id,
  label,
  groupIcon,
  children,
}: {
  id: string;
  label: string;
  /** One conventional mark for the group. Items below it carry none. */
  groupIcon?: Parameters<typeof Icon>[0]["name"];
  children: ReactNode;
}) {
  return (
    // **A nested list, not a heading between siblings.** The first version put each group
    // label in an `<li role="presentation">`, which makes it a child of the `<ul>` that is
    // not a list item -- axe's `only-listitems`, and a screen reader then reads a list whose
    // length counts the headings. A group is a list item that contains a list, which is the
    // structure a grouped navigation actually has.
    <li className="ds-rail-section">
      {/* **The icon moved here from the items, and the research is why.** Twenty-six
          destinations carried twenty-six glyphs, of which three pairs were identical --
          the whole Money group drew one payments mark, so the icon distinguished nothing
          and competed with the label that did. NN/g: a navigation icon needs a permanent
          text label, and an icon nobody can name in five seconds will not communicate; a
          glyph per destination is decoration at this count. Six group marks are
          conventional, scannable, and leave the labels to carry the destinations. */}
      <span className="ds-rail-group" id={id}>
        {groupIcon === undefined ? null : <Icon name={groupIcon} size={16} />}
        {label}
      </span>
      <ul className="ds-rail-items" aria-labelledby={id}>
        {children}
      </ul>
    </li>
  );
}

/** A rail item's label and its count. The group above it carries the only icon. */
export function RailItem({
  label,
  count,
}: {
  label: string;
  /** "4,812" beside Members, "6" beside Payments. Absent where there is nothing to count. */
  count?: string;
}) {
  return (
    <>
      <span className="ds-rail-label">{label}</span>
      {count === undefined ? null : (
        // Mono and tabular, like every other figure in the product.
        <span className="ds-rail-count data">{count}</span>
      )}
    </>
  );
}

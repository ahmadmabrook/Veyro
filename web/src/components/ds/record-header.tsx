import Link from "next/link";
import type { ReactNode } from "react";

/**
 * `Member360Header` and `Tabs` — the two pieces every record inspector in the design opens
 * with, and the two this app's member page did not have.
 *
 * ADM-MEM-01's own component list names both: `Member360Header · PersonRow ×6 ·
 * AttentionRow(inline) · MetricCell ×5 · TimelineItem ×7 · MembershipCard · AccessPass ·
 * MoneyValue · ConsentBlock reference · Tabs`. What this page rendered instead was an `<h1>`
 * and nine stacked `<dl>` blocks -- every fact present, the whole anatomy absent.
 *
 * The canvas's measurements, which are the ones here:
 *
 *     container  background warm.0, border-bottom 1px, padding 16px 20px 0
 *     row        display:flex; gap:14px; align-items:flex-start; flex-wrap:wrap
 *     avatar     52×52 circle, warm.200 ground, 1px border
 *     name       500 22/1.2, tracking -.016em
 *     band       500 9.5/1.4 mono, 1px border in its own ink, 2px 6px, radius 3
 *     sub-line   400 12/1.55, text.secondary, margin-top 4px, ids in mono
 *     actions    primary 11px 14px radius 6 · secondary 1px border 10px 13px
 *     tabs       500/400 11.5/1.4, 1.5px bottom border on the current one, 16px apart
 *
 * **The band is a word, not a colour.** `PAYMENT OVERDUE` is set in the error ink with a
 * border in the same ink and no fill -- which is the design's rule for a status that must
 * survive monochrome and colour-blindness, and the reason the canvas's note says "No green
 * badges": paid, active and granted are the expected cases, and decorating them makes a
 * genuinely overdue row harder to spot. So there is no `tone: "success"`.
 */

export type BandTone = "critical" | "warning" | "neutral";

export function RecordHeader({
  name,
  band,
  subline,
  actions,
  tabs,
  avatar = false,
  id,
}: {
  name: ReactNode;
  /** `PAYMENT OVERDUE` — absent where nothing is wrong, which is the signal. */
  band?: { text: string; tone: BandTone };
  /** "Club · Khalda · member since March 2024 · +962 79 555 0134 · M-04188". */
  subline?: ReactNode;
  /**
   * The end of the row. **Absent where the write does not exist**: every member-facing write
   * in this build is a stepped-up financial permission with no form behind it, and a
   * "Take payment" button that answered 403 would be worse than the gap, which is
   * ADM-MEM-05's own finding.
   */
  actions?: ReactNode;
  tabs?: ReactNode;
  /**
   * Whether to draw the 52px circle.
   *
   * **Off by default, because most records are not people.** The canvas draws it for a
   * member and draws none for a class: a circle beside "Spin · Thursday 19:00" reads as an
   * avatar for a thing that has no face, and an empty one reads as a photograph that failed
   * to load. There is no photograph in this build either -- MOD-014 has no progress media
   * and no object store -- so even for a person it is the shape with nothing in it.
   */
  avatar?: boolean;
  id?: string;
}) {
  return (
    <header className="ds-record-head">
      <div className="ds-record-head-row">
        {/* A ground, not a photograph, and only where the record is a person. */}
        {avatar ? <span className="ds-record-avatar" aria-hidden="true" /> : null}
        <div className="ds-record-head-text">
          <div className="ds-record-title">
            <h1 id={id} className="ds-record-name">{name}</h1>
            {band ? (
              <span className="ds-record-band data" data-tone={band.tone}>
                {band.text}
              </span>
            ) : null}
          </div>
          {subline === undefined ? null : (
            <p className="ds-record-subline">{subline}</p>
          )}
        </div>
        {actions === undefined ? null : (
          <div className="ds-record-actions">{actions}</div>
        )}
      </div>
      {tabs === undefined ? null : tabs}
    </header>
  );
}

/**
 * The tab strip.
 *
 * **Real navigation, not a client-side toggle.** Each tab is a link carrying the tab in the
 * query string, so a deep link lands on the tab it names, the browser's back button works,
 * and the page renders with JavaScript off -- which is the same reason the sign-in form is a
 * Server Action rather than a fetch.
 *
 * **A tab this build cannot fill is not drawn.** The canvas has nine, five of which would be
 * empty here: attendance per person, coaching, bookings per person, purchases and documents
 * each need a module or a read that does not exist. A tab that opened an empty panel would
 * say the member has no bookings rather than that nothing here knows, which is the one
 * reading that is always wrong -- so those five are named at the foot of the page instead,
 * with the reason each is absent.
 */
export function Tabs({
  label,
  tabs,
  current,
  href,
}: {
  label: string;
  tabs: { key: string; label: string }[];
  current: string;
  /** Builds the link for a tab key, so the caller owns the rest of the query string. */
  href: (key: string) => string;
}) {
  return (
    <nav className="ds-tabs" aria-label={label}>
      <ul className="ds-tab-list">
        {tabs.map((tab) => (
          <li key={tab.key}>
            <Link
              className="ds-tab"
              href={href(tab.key)}
              // `aria-current="page"` rather than `aria-selected`: these are links in a
              // navigation, not options in a tablist, and claiming the tablist role would
              // promise arrow-key traversal that links do not have.
              {...(tab.key === current ? { "aria-current": "page" as const } : {})}
            >
              {tab.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

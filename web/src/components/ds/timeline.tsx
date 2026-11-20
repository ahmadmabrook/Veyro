import Link from "next/link";
import type { ReactNode } from "react";

/**
 * `Timeline` and `TimelineItem` — ADM-MEM-01's spine, which the design counts as seven items
 * in five event classes and this app rendered as a bulleted list with an ISO timestamp under
 * each line.
 *
 * The canvas's measurements:
 *
 *     container  1px border, radius 4, warm.0, overflow hidden
 *     header     10px 14px, border-bottom, "Timeline" at 500 12.5/1.3 with the filters after
 *     filter     400 10.5/1, 5px 8px, radius 4 — the current one on a warm.100 ground
 *     row        display:flex; gap:11px; padding:11px 14px; border-bottom 1px subtle
 *     gutter     66px: the time at 500 10.5 mono, the day under it at 400 9.5 mono tertiary
 *     spine      2px wide, full height, radius 1, in the row's own tone
 *     title      500 12.5/1.45, the money end-aligned beside it at 500 12 mono
 *     meta       400 11.5/1.55 text.secondary, margin-top 2px
 *
 * **The spine is the event class and it is 2px of colour with a word beside it.** The five
 * classes in the canvas are money (error ink where it failed), system (warm.400), coaching,
 * visit and consent. A tone alone would be colour-only signalling, which is why every row's
 * meta line names what it is -- the colour is the scan and the words are the content.
 *
 * **The time gutter is split: the clock above, the day below.** That is what makes a vertical
 * scan of a timeline readable -- the eye reads `06:12 / today` as one unit and `31 Jul` as
 * another, where one combined string of eleven characters reads as neither.
 */

export type TimelineTone = "money" | "system" | "visit" | "coaching" | "consent";

export function Timeline({
  label,
  filters,
  footer,
  children,
}: {
  /** "Timeline" — the heading inside the container's own header row. */
  label: ReactNode;
  /** The filter chips. Links, for the same reason the tabs are. */
  filters?: ReactNode;
  /** "Load earlier activity · 214 events since March 2024". */
  footer?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="ds-timeline">
      <div className="ds-timeline-head">
        <h2 className="ds-timeline-title">{label}</h2>
        {filters === undefined ? null : (
          <div className="ds-timeline-filters">{filters}</div>
        )}
      </div>
      <ol className="ds-timeline-items">{children}</ol>
      {footer === undefined ? null : (
        <div className="ds-timeline-foot">{footer}</div>
      )}
    </section>
  );
}

/** One filter chip. A link, so the filter is in the URL and survives a reload. */
export function TimelineFilter({
  href,
  current,
  children,
}: {
  href: string;
  current: boolean;
  children: ReactNode;
}) {
  return (
    <Link
      className="ds-timeline-filter"
      href={href}
      {...(current ? { "aria-current": "page" as const } : {})}
    >
      {children}
    </Link>
  );
}

export function TimelineItem({
  time,
  day,
  tone,
  title,
  money,
  meta,
}: {
  /**
   * "06:12" — mono, and the caller decides which zone it is in and says so.
   *
   * Empty where the instant is a date with no time of day, in which case `day` takes the
   * clock's place rather than sitting under a blank line.
   */
  time: string;
  /** "today", "31 Jul" — the bucket, under the clock. */
  day: string;
  tone: TimelineTone;
  title: ReactNode;
  /** `MoneyValue` where the event moved money. End-aligned, so it mirrors in RTL. */
  money?: ReactNode;
  meta?: ReactNode;
}) {
  return (
    <li className="ds-timeline-item">
      <div className="ds-timeline-when">
        {/* **An empty clock is not a blank line.** Some instants are dates: an invoice's
            issue date is a `date` column, so there is no time of day to show, and the
            gutter rendered an empty row above the day. Where there is no clock the day
            takes its place, which is what a reader expects of a date-only row. */}
        {time === "" ? (
          <span className="ds-timeline-clock data" dir="ltr">{day}</span>
        ) : (
          <>
            <span className="ds-timeline-clock data" dir="ltr">{time}</span>
            <span className="ds-timeline-day data" dir="ltr">{day}</span>
          </>
        )}
      </div>
      <span className="ds-timeline-spine" data-tone={tone} aria-hidden="true" />
      <div className="ds-timeline-body">
        <div className="ds-timeline-headline">
          <span className="ds-timeline-what">{title}</span>
          {money === undefined ? null : money}
        </div>
        {meta === undefined ? null : <p className="ds-timeline-meta">{meta}</p>}
      </div>
    </li>
  );
}

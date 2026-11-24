/**
 * Reading an instant, which this app does in two different ways on purpose.
 *
 * **A scheduled session is read in its site's timezone**, because MOD-019 stores a UTC instant
 * and the local facts it came from and neither is derivable from the other. **Everything else
 * is read in UTC and says so**, because nothing else in the build carries a zone to convert
 * into: a device's last report, an audit entry and a note belong to a tenant rather than to a
 * site. The two live together so the difference is a choice somebody made rather than one
 * page's habit -- and an instant rendered with no zone at all is the thing both exist to
 * prevent, now that one screen shows local time and a reader will assume the rest do too.
 */

/**
 * An instant as the site reads it, which is the only way it should ever be read.
 *
 * **MOD-019 stores a UTC instant and the local facts it came from, because neither is
 * derivable from the other** -- a rule carries a local time plus the location's zone and every
 * occurrence is converted separately, so a clock change moves one and not the other. A surface
 * that slices the ISO string renders the UTC wall time instead, and the first version of this
 * board did exactly that: a class at 18:00 in Amman read as `15:00` under a heading promising
 * the site's own timezone. Nothing in 140 passing tests noticed, because every one of them
 * asserted the timezone's *name* was on the page rather than what the times said.
 *
 * **A bad zone falls back to UTC and says UTC**, rather than to a local time that would be
 * wrong. MOD-004 validates a location's timezone when it is created, so this is the shape of a
 * failure nobody should see -- and rendering a plausible wrong time is the one outcome worse
 * than rendering an obviously foreign one.
 */
export function inZone(
  instant: string,
  timezone: string,
): { date: string; time: string; zone: string } {
  const at = new Date(instant);
  try {
    return {
      date: new Intl.DateTimeFormat("en-CA", {
        timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit",
      }).format(at),
      time: new Intl.DateTimeFormat("en-GB", {
        timeZone: timezone, hour: "2-digit", minute: "2-digit", hourCycle: "h23",
      }).format(at),
      zone: timezone,
    };
  } catch {
    return {
      date: at.toISOString().slice(0, 10),
      time: at.toISOString().slice(11, 16),
      zone: "UTC",
    };
  }
}

/**
 * An instant in UTC, labelled.
 *
 * Ten sites rendered `instant.slice(0, 16).replace("T", " ")` and showed a bare wall time with
 * no zone on it. That was merely ambiguous while every screen did it; it became misleading the
 * day the schedule board started converting, because a reader with one local-time screen reads
 * the next one as local too.
 */
export function utcStamp(instant: string): string {
  return `${instant.slice(0, 10)} ${instant.slice(11, 16)} UTC`;
}

/**
 * The timeline gutter's two halves: the clock above, the day under it.
 *
 * ADM-MEM-01 draws a 66px column carrying `06:12` over `today`, and that split is what makes a
 * vertical scan of a timeline readable -- the eye reads the pair as one unit where a single
 * eleven-character string reads as neither. So they are two functions and the component takes
 * both, rather than one that returns a sentence.
 *
 * **Both are UTC and the row's meta line says so**, which is the rule one function up: nothing
 * on a member's record carries a zone to convert into. A timeline entry belongs to the tenant,
 * not to a site -- MOD-014 projects it from the event outbox, where the only instant is the
 * one the producer recorded.
 */
export function timeOfDay(instant: string): string {
  return instant.slice(11, 16);
}

/**
 * `today`, `yesterday` or `31 Jul` — the bucket the entry falls in.
 *
 * **Relative to the reader's own UTC day, which is the only "today" this build has.** A
 * tenant with clubs in two zones has two local todays and a timeline carrying neither, so
 * labelling the day in any one site's zone would be wrong for the other; UTC is at least
 * consistently stated. The `now` argument exists because a test that asserts "today" has to
 * be able to say when today is -- otherwise its green depends on when it runs, which this
 * repository has already paid for four times.
 */
export function dayLabel(instant: string, now: Date = new Date()): string {
  const day = instant.slice(0, 10);
  const today = now.toISOString().slice(0, 10);
  if (day === today) return "today";
  const before = new Date(now.getTime() - 86_400_000).toISOString().slice(0, 10);
  if (day === before) return "yesterday";
  // `15 Mar` in Latin numerals and English month names, because this is a mono gutter sitting
  // beside a mono clock: a localised month name in a 66px column wraps, and the one place
  // this app localises a date is where it is prose rather than data.
  const at = new Date(instant);
  return `${at.getUTCDate()} ${
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][at.getUTCMonth()]}`;
}

/**
 * A calendar date as a day and a month -- "to 31 August", which is the boundary ADM-CRM-06
 * prorates a first charge to and the week heading `/rota` draws.
 *
 * **Moved here from `src/lib/scheduling.ts`, where it was beside `weekDays`.** It shares that
 * function's UTC-parse subtlety -- a bare `YYYY-MM-DD` is UTC midnight, so the formatter is
 * pinned to UTC and reads back the calendar date it was given, where the host's own zone
 * renders a date west of UTC as the day before for part of every day -- but it is a *date
 * formatter*, and its sibling `monthYearLabel` has lived in this module all along with a
 * docstring that cites this function by name. A CRM screen importing a scheduling helper to
 * render a date is the smell; two copies of the same formatter would be the defect.
 *
 * No year, because every caller's heading carries the range and a date that needs a year to
 * disambiguate is one nobody is looking at.
 */
export function monthDayLabel(date: string, locale: "en" | "ar"): string {
  return new Intl.DateTimeFormat(locale === "ar" ? "ar" : "en-GB", {
    timeZone: "UTC", day: "numeric", month: "long",
  }).format(new Date(`${date}T00:00:00Z`));
}

/**
 * A calendar date as a month and a year — "joined Feb 2025", which is how ADM-MEM-10's
 * duplicate banner identifies the record it found.
 *
 * **Here rather than beside the screen, and UTC-pinned for `monthDayLabel`'s reason**: a bare
 * `YYYY-MM-DD` parses as UTC midnight, so the formatter has to be pinned to UTC to read back
 * the calendar date it was given. Formatted in the host's zone instead, a date west of UTC
 * renders as the previous month for part of every first-of-the-month. A second copy of that
 * reasoning next to the screen that needed it is how two date formatters start to disagree.
 *
 * **A month and no day, because the day is not what identifies a record.** A desk recognising
 * somebody by when they joined thinks in months; a precise date would also be a slightly
 * sharper way to confirm facts about a person whose name this session may not be allowed to
 * see, which is the direction to err away from.
 */
export function monthYearLabel(date: string, locale: "en" | "ar"): string {
  const parsed = new Date(`${date}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return date;
  return new Intl.DateTimeFormat(locale === "ar" ? "ar" : "en-GB", {
    timeZone: "UTC", month: "short", year: "numeric",
  }).format(parsed);
}

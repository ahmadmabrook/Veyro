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

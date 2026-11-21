/**
 * ADM-MSH-03 · FREEZE — "Freeze Ahmad's membership".
 *
 * **Decisions only, and no imports that reach `next/headers`.** The form is a client
 * component, and the cash board paid for this lesson a screen ago: a client component
 * importing `@/lib/api` fails the whole app's build, with an error naming a chain of
 * `[Client Component Browser]` imports and never mentioning `next/headers`.
 *
 * The canvas takes FROM and UNTIL; `freeze_membership` takes a start and a number of days,
 * and stores `planned_ends_on = starts_on + days - 1`. So the two dates are **inclusive** —
 * a freeze from the 1st to the 1st is one day, not nought — and converting them wrongly is
 * the kind of off-by-one that spends somebody's allowance a day at a time.
 */

export type FreezeAllowance = {
  membership_id: string;
  status: string;
  counting_an_open_freeze: boolean;
  contract_year: { from: string; to: string };
  allowance_days: number;
  days_used: number;
  days_remaining: number;
  may_start_between: { from: string; to: string };
  allows_freezing: boolean;
  an_open_freeze_counts_to_the_year_end: string;
  the_figure_is_the_writes_own: string;
};

/** A calendar date, in the one format every date on these surfaces uses. */
export function isDay(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value)
    && !Number.isNaN(Date.parse(`${value}T00:00:00Z`));
}

const at = (day: string): number => Date.parse(`${day}T00:00:00Z`);

/**
 * How many days a freeze from `from` to `until` lasts, counting both ends.
 *
 * **UTC, on a date-only string**, which is `weekDays`' own reasoning one module over: a bare
 * `YYYY-MM-DD` parses as UTC midnight and a difference in UTC never crosses a clock change,
 * where the host's zone gives a day too few or too many on the two nights a year it shifts.
 */
export function freezeDays(from: string, until: string): number | null {
  if (!isDay(from) || !isDay(until)) return null;
  const span = (at(until) - at(from)) / 86_400_000;
  if (!Number.isInteger(span) || span < 0) return null;
  return span + 1;
}

/** Whether a start date is one `freeze_membership` will accept. */
export function startIsAllowed(
  from: string, window: { from: string; to: string },
): boolean {
  if (!isDay(from) || !isDay(window.from) || !isDay(window.to)) return false;
  return at(from) >= at(window.from) && at(from) <= at(window.to);
}

/** What a freeze of this length would leave, or `null` when the dates are not a span. */
export function wouldRemain(
  allowance: FreezeAllowance, from: string, until: string,
): number | null {
  const days = freezeDays(from, until);
  if (days === null) return null;
  return allowance.days_remaining - days;
}

/**
 * Why this freeze cannot be taken, or `null` when it can.
 *
 * **The order is the server's**, so a form never reports a reason the module would not: the
 * contract first, then the start window, then the length, then the allowance. A screen that
 * checked the allowance before the window would tell somebody to shorten a freeze whose date
 * the server was going to refuse anyway.
 */
export type FreezeRefusal =
  | "freeze.noAllowance"
  | "freeze.badDates"
  | "freeze.startOutsideWindow"
  | "freeze.tooLong"
  | "freeze.overAllowance";

export function refusalFor(
  allowance: FreezeAllowance, from: string, until: string,
): FreezeRefusal | null {
  if (!allowance.allows_freezing) return "freeze.noAllowance";
  const days = freezeDays(from, until);
  if (days === null) return "freeze.badDates";
  if (!startIsAllowed(from, allowance.may_start_between)) {
    return "freeze.startOutsideWindow";
  }
  // `check_freeze` refuses anything over a year before it looks at the allowance.
  if (days > 365) return "freeze.tooLong";
  if (days > allowance.days_remaining) return "freeze.overAllowance";
  return null;
}


/**
 * What this reader is offered, which is four answers rather than two.
 *
 * **A branch no fixture can reach is a branch nobody tested**, and this one was: the
 * fixture's contract allows thirty freeze days, so the "this contract allows no freezing"
 * path never rendered and a mutation deleting it passed a green suite. That is the shape
 * this repository records for four modules, caught here by the browser sweep. The remedy is
 * the one the rules file states: make the decision a function and test every branch of it,
 * rather than seeding a second membership so a surface can be looked at.
 *
 * The order matters as much as the answers. A contract that allows no freezing is refused by
 * `check_freeze` whatever the session holds, so offering a step-up there would send somebody
 * to find a second factor that changes nothing -- the member record's own rule about a health
 * field nobody in this build can read, applied to a write.
 */
export type FreezeAffordance = "form" | "step_up" | "no_allowance" | "refused";

export function affordanceFor(
  allowance: Pick<FreezeAllowance, "allows_freezing">,
  gate: { allowed: boolean; verdict: "needs_step_up" | "denied" | string },
): FreezeAffordance {
  if (!allowance.allows_freezing) return "no_allowance";
  if (gate.allowed) return "form";
  if (gate.verdict === "needs_step_up") return "step_up";
  return "refused";
}

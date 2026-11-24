import type { MessageKey } from "@/i18n/locale";

/**
 * ADM-CRM-07's decisions — "Why did Omar Zaid not join?"
 *
 * The canvas is a reason picker over four values, one free-text follow-up, a `Mark lost`
 * button and a footnote: "Not deleted. Reopenable, and re-contact after 90 days is a supported
 * flow rather than a fresh record. The reason feeds source effectiveness in ADM-RPT-03."
 *
 * **Nothing here decides whether a lead is lost or re-contactable.** `lost`, `lost_at` and
 * `recontactable` all come off the read, because the ninety days is arithmetic over the
 * server's clock and a browser comparing a timestamp against its own counts in the wrong
 * frame -- which this app has three recorded defects from.
 */

/** The four, in the canvas's own order, each with the word it is drawn as. */
export const LOST_REASONS: readonly { value: string; label: MessageKey }[] = [
  { value: "too_expensive", label: "lost.reasonTooExpensive" },
  { value: "joined_elsewhere", label: "lost.reasonJoinedElsewhere" },
  { value: "location_or_hours", label: "lost.reasonLocationOrHours" },
  { value: "no_longer_responding", label: "lost.reasonNoLongerResponding" },
] as const;

/**
 * The word a stored reason is drawn as, or `null` where this build has none.
 *
 * **A vocabulary the backend stores is never a label.** The set is closed on the server and a
 * fifth value is a product decision rather than a migration, so an unknown one falls through
 * to its stored form rather than to "other" -- the members list's rule, because the screens
 * that show these are the screens somebody acts on.
 */
export function reasonWord(stored: string): MessageKey | null {
  return LOST_REASONS.find((one) => one.value === stored)?.label ?? null;
}

/**
 * Which sentence a lost lead's re-contact state gets.
 *
 * **Both say reopening is allowed**, which is the point: ADR-0010 D10 makes the ninety days
 * advisory rather than a lock, because locking it would leave a lead marked lost by mistake
 * uncorrectable for a quarter on a routine permission. So the difference is whether it is
 * usually worth another try, not whether the button works.
 */
export function recontactSentence(recontactable: boolean): MessageKey {
  return recontactable ? "lost.reopenable" : "lost.notYetReopenable";
}

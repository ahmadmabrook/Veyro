import type { MessageKey } from "@/i18n/locale";

/**
 * FD-03 · ACCESS DENIED · WHAT TO SAY AND DO.
 *
 * > "**His membership ended on 7 August** and the 14-day grace ran out five days ago. He was
 * > here three times a week for two years — worth asking whether something changed before you
 * > lead with the renewal." … "YOU CAN OVERRIDE THIS. Ziad granted you override authority in
 * > March. Letting him in records your name, the reason, and appears in the access log."
 * > … "Without override authority the last button is absent and the panel names Ziad as the
 * > person to call. Never a locked control with no route."
 *
 * **Decisions only**, no import reaching `next/headers`.
 *
 * **This is the one screen in the product where what a receptionist may say is governed by a
 * permission.** MOD-022 splits a refusal into a public line a door may display and a private
 * reason only `access.decision.read_reason` returns -- financial class, so a password-only
 * desk does not hold it -- and the split is over the *code* as well as the prose, because
 * "both reviewers found that the split gated the sentence and not the fact". So a desk at an
 * ordinary sign-in is told to see the front desk, which is what the member was told, and the
 * sentence the canvas prints is behind a step-up. That is the module working, not a gap.
 */

/** Every refusal MOD-022 can give. The public ones are the codes a door may display. */
export type DenialCode = string;

/**
 * What a receptionist can say out loud, per code.
 *
 * **Only codes this module actually writes.** A reviewer grepped the writers of all twenty
 * and found nineteen -- `wrong_zone` was declared and produced by nothing, and is gone -- so
 * a map with an entry for it would be a sentence nobody could ever read.
 *
 * **`see_front_desk` is in here too**, and it is the one a desk sees most: it is the stable
 * code a restricted refusal carries outward, so a session without the private read lands on
 * it for every one of the five restricted reasons. Its sentence says that rather than
 * pretending to explain.
 */
export const SAY: Record<string, MessageKey> = {
  see_front_desk: "denial.say.seeFrontDesk",
  credential_unknown: "denial.say.credentialUnknown",
  credential_revoked: "denial.say.credentialRevoked",
  credential_expired: "denial.say.credentialExpired",
  credential_replayed: "denial.say.credentialReplayed",
  credential_window: "denial.say.credentialWindow",
  reader_clock_unreliable: "denial.say.readerClock",
  outside_opening_hours: "denial.say.outsideHours",
  zone_closed: "denial.say.zoneClosed",
  membership_inactive: "denial.say.membershipInactive",
  no_entitlement: "denial.say.noEntitlement",
  outstanding_balance: "denial.say.outstandingBalance",
  age_restricted: "denial.say.ageRestricted",
  safety_hold: "denial.say.safetyHold",
  anti_passback: "denial.say.antiPassback",
  zone_at_capacity: "denial.say.atCapacity",
  device_untrusted: "denial.say.deviceUntrusted",
  point_not_an_entry: "denial.say.notAnEntry",
};

export function sayFor(code: string): MessageKey | null {
  return SAY[code] ?? null;
}

/**
 * The two grants, worded.
 *
 * `granted` gets no sentence on purpose: the verdict beside it already reads "Admitted", and
 * a caption repeating it is the one message said twice that the field shell's own rule
 * exists to prevent. `granted_by_override` is the other half and is the fact that matters --
 * somebody let this person in against the policy, which is "a decision in its own right
 * rather than a flag on one" and the thing a reader of the log is looking for.
 */
const GRANT_WORD: Record<string, MessageKey> = {
  granted_by_override: "access.byOverride",
};

/**
 * What to say under a decision's verdict, or nothing.
 *
 * **The code is the module's closed vocabulary and was being rendered raw.** The door board
 * printed `granted_by_override` and `see_front_desk` in a caption under every row -- a
 * stored enumeration where a word belongs, which is this repository's most-repeated surface
 * finding and the fifth place it has been found. FD-03 already had the sentences; this is
 * the same map read by the board, so the two screens cannot word one refusal two ways.
 *
 * **An unmapped code falls through to its stored form rather than to "other".** The set is
 * MOD-022's and may grow, and hiding a decision somebody needs to see is worse than showing
 * an ugly one -- MOD-013's own judgement about its eight delivery reasons.
 */
export function codeWord(code: string, granted: boolean): MessageKey | null {
  if (granted) return GRANT_WORD[code] ?? null;
  return sayFor(code);
}

/**
 * Whether this refusal is one the hardware caused rather than the member.
 *
 * **It changes who the next sentence is about.** A revoked card and a reader whose clock is
 * wrong are both "denied" at the door and nothing else about them is alike: one is a
 * conversation with the member and the other is a conversation with whoever maintains the
 * device. A screen that led with "renew your membership" for a clock fault would be the
 * canvas's own warning -- leading with the renewal before asking what changed -- in its
 * worst form.
 */
const DEVICE_FAULTS = new Set([
  "credential_replayed", "reader_clock_unreliable", "device_untrusted",
  "point_not_an_entry",
]);

export function isDeviceFault(code: string): boolean {
  return DEVICE_FAULTS.has(code);
}

/** A decision as `GET /access/decisions` returns it. */
export type AccessDecision = {
  decision_id: string;
  point_id: string;
  zone_id: string;
  person_id: string | null;
  granted: boolean;
  code: string;
  public_reason: string;
  private_reason: string | null;
  /**
   * There is more to read and this session may not.
   *
   * **It was declared `masked` and the server has never sent that**, which no typecheck can
   * see: the type is a hand-written declaration of an untyped JSON response, so the field
   * read `undefined`, the branch behind it never rendered, and the screen's offer to read
   * why a member was refused was dead on arrival. That is this repository's "a declared
   * value nothing writes", on the client side of the wire -- and the only thing that found
   * it was a browser test asking for the link.
   *
   * The server's own name is better than the one invented here, too: it is already
   * `withheld AND NOT may_read_private`, so a caller holding the permission sees `false`
   * rather than having to re-derive it.
   */
  reason_withheld: boolean;
  /** ADM-ACC-02's classification, derived by MOD-022 from the code rather than here. */
  bucket: "granted" | "policy" | "fault";
  decided_at: string;
};

/**
 * The refusal this screen is about.
 *
 * **The most recent one, and only a refusal.** A member whose card worked an hour after it
 * failed is not somebody a desk needs to talk to, and a screen that showed the newest
 * *decision* would open on a grant and explain nothing. `granted_by_override` is a grant,
 * so a refusal already resolved by somebody is not re-offered either.
 */
export function latestRefusal(decisions: AccessDecision[]): AccessDecision | null {
  const refusals = decisions.filter((d) => !d.granted);
  if (refusals.length === 0) return null;
  return [...refusals].sort(
    (a, b) => b.decided_at.localeCompare(a.decided_at))[0] ?? null;
}

/**
 * Whether somebody already let this person in after the refusal.
 *
 * The canvas's own "Let in, flag it" leaves a grant in the log beside the refusal -- the
 * override is "a decision in its own right rather than a flag on one" -- so the screen has
 * to notice when that has happened rather than offering the button twice.
 */
export function overriddenSince(
  decisions: AccessDecision[], refusal: AccessDecision,
): AccessDecision | null {
  return decisions.find(
    (d) => d.code === "granted_by_override"
      && d.decided_at.localeCompare(refusal.decided_at) > 0) ?? null;
}

/**
 * The three reasons the canvas offers for an override.
 *
 * **The module takes free text and this screen offers three**, which is the design's own
 * "Choose a reason: renewing today · manager approved · resolving a dispute". A written
 * reason that is one of three is a reason somebody can count later; free text at a busy desk
 * is "ok" nineteen times. The module's own constraint is only that it is not blank, so the
 * narrowing is this screen's and is said on it.
 */
export const OVERRIDE_REASONS = [
  "renewing_today", "manager_approved", "resolving_a_dispute",
] as const;

export type OverrideReason = (typeof OVERRIDE_REASONS)[number];

export function isOverrideReason(value: string): value is OverrideReason {
  return (OVERRIDE_REASONS as readonly string[]).includes(value);
}

/**
 * What this reader is offered about the override.
 *
 * **The canvas's own footnote is the requirement**: "Without override authority the last
 * button is absent and the panel names Ziad as the person to call. Never a locked control
 * with no route." Two of those three are buildable -- the button is absent, and a reader who
 * could step up is offered one. Naming the person to call is not: MOD-008 answers what one
 * identity may do and nothing answers who holds a permission, so the panel says that rather
 * than inventing a name.
 */
export type OverrideOffer = "form" | "step_up" | "denied" | "already";

export function overrideOffer(
  gate: { allowed: boolean; verdict: string },
  alreadyOverridden: boolean,
): OverrideOffer {
  if (alreadyOverridden) return "already";
  if (gate.allowed) return "form";
  return gate.verdict === "needs_step_up" ? "step_up" : "denied";
}

/**
 * The idempotency key for admitting somebody against the policy.
 *
 * **It is the refusal being answered, and nothing else.** That is the only stable handle for
 * "this press answers this": a desk that pressed the button twice, or whose request timed out
 * after the commit, must not admit the same person twice in an insert-only log.
 *
 * **It was `(point, person, reason)` and that was a defect**, found by working out how a
 * browser test would re-run rather than by reading it. `override_access` answers a repeated
 * key from the row it already wrote, so a member refused today and admitted by hand, then
 * refused again tomorrow and admitted for the same reason, produced **no second row**: the
 * desk was told it had worked, nothing was recorded for the second admission, and the access
 * log showed one override for two. This repository's "an idempotency key compared on fewer
 * fields than the command takes", from the caller's side.
 *
 * **The reason is deliberately out of it.** One override per refusal, whatever was chosen:
 * two presses with two reasons would otherwise write two rows saying somebody was let in
 * once, and a correction that doubles the record is worse than a first answer that stands.
 *
 * It is a function here rather than a template in the action because the action reaches
 * `next/headers` and cannot be imported by a test -- the same split the backend makes between
 * a decision and the I/O that carries it out.
 */
export function overrideKey(decisionId: string): string {
  return `override-${decisionId}`;
}

/**
 * Which door this happened at, from the zone the refusal already names.
 *
 * **The canvas puts it under the member's name** -- "Flex · Khalda · turnstile 18:39" -- and
 * it is the half of that line this module owns: a desk with two lanes needs to know which
 * one turned somebody away, and a decision carries a `point_id` rather than a name.
 *
 * It is `null` where the zone read was refused or the point is not in it, because a door
 * named wrongly is worse than a door not named: a receptionist sent to the wrong lane walks
 * away from the person who is standing in front of them.
 */
export function doorOf(
  zone: { display_name: string; points: { point_id: string; display_name: string }[] } | null,
  pointId: string,
): { zone: string; point: string } | null {
  if (zone === null) return null;
  const point = zone.points.find((p) => p.point_id === pointId);
  return point === undefined ? null : { zone: zone.display_name, point: point.display_name };
}

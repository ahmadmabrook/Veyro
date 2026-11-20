import type { MessageKey } from "@/i18n/locale";
import { api } from "@/lib/api";

/**
 * MOD-013's reads, typed: what this tenant can say, what it decided to say, and to whom it
 * may not say anything at all.
 *
 * **No message text passes through here, and that is the server's decision rather than this
 * module's restraint.** `GET /notifications` deliberately carries no rendered body: a list
 * route that did would be a read path to everything a tenant has ever said to anybody under
 * one permission, which is MOD-010's `events.event.read` finding. The text is on the detail
 * route behind `notifications.notification.read_content`, and this board never asks for it.
 *
 * **Nothing sends.** There is no provider, no SMTP and no outbound HTTP in this build:
 * `dispatch_notification` claims a delivery for whatever does the sending and `record_outcome`
 * is written by it. So a notification here sits at `requested` or `deferred` for ever, and a
 * board that rendered that as a queue making progress would be the fabricated-evidence shape
 * this codebase has been bitten by. The page says it instead.
 *
 * **An address never appears either.** `ntf_notifications`, `ntf_suppressions` and
 * `ntf_recipient_channels` carry a SHA-256 of `channel:address` and never the address, so a
 * bounce is remembered and a recipient matched without a second copy of everyone's email
 * beside the one MOD-007 and MOD-014 own.
 */

export type NotificationTemplate = {
  template_id: string;
  template_key: string;
  version: number;
  category: string;
  channel: string;
  locale: string;
  subject: string | null;
  variables: string[];
  status: string;
  approved_at: string | null;
  published_at: string | null;
  retired_at: string | null;
};

export type ChannelPolicy = {
  policy_id: string;
  channel: string;
  enabled: boolean;
  fallback_channel: string | null;
  cost_per_message_minor: number | null;
  currency: string | null;
  updated_at: string;
};

export type NotificationRow = {
  notification_id: string;
  template_key: string;
  template_version: number;
  category: string;
  channel: string;
  locale: string;
  recipient_id: string;
  priority: string;
  status: string;
  /** Why it was sent, deferred or suppressed. The field a board exists to render. */
  decision_reason: string | null;
  requested_at: string;
};

export type Suppression = {
  suppression_id: string;
  channel: string;
  /** A digest of `channel:address`, never the address. Pseudonymous, not anonymous. */
  address_digest: string;
  reason: string;
  detail: string | null;
  recorded_at: string;
  released_at: string | null;
};

export type Digest = {
  digest_id: string;
  recipient_id: string;
  category: string;
  channel: string;
  window_start: string;
  window_end: string;
  state: string;
  notification_count: number;
};

export function listTemplates(): Promise<NotificationTemplate[]> {
  return api("/notifications/templates");
}

export function listChannels(): Promise<ChannelPolicy[]> {
  return api("/notifications/channels");
}

export function listNotifications(): Promise<NotificationRow[]> {
  return api("/notifications?limit=50");
}

export function listSuppressions(): Promise<Suppression[]> {
  return api("/notifications/suppressions/all");
}

export function listDigests(): Promise<Digest[]> {
  return api("/notifications/digests/all");
}

/**
 * Whether a suppression is still blocking messages.
 *
 * Only an unsubscribe may be released, and `reason` carries no UPDATE grant so a bounce
 * cannot be relabelled an unsubscribe and then lifted. A board that showed released and live
 * suppressions alike would be showing an address that is blocked beside one that is not, under
 * one heading.
 */
export function suppressionIsLive(suppression: Suppression): boolean {
  return suppression.released_at === null;
}

/**
 * Whether a suppression can ever be lifted.
 *
 * A bounce or a complaint is the channel's judgement about deliverability, and a tenant that
 * could clear those would be choosing to keep sending to an address that rejected them --
 * which damages the chance of every other message arriving, including the transactional ones
 * nobody opted out of. So the board says which of the two a row is, rather than offering a
 * release control that would be refused.
 */
export function releasable(suppression: Suppression): boolean {
  return suppression.reason === "unsubscribed";
}

/**
 * What a notification is waiting on, as a sentence rather than a status.
 *
 * Four states and only one of them is about the member. `requested` and `deferred` are both
 * waiting for a dispatcher that does not exist in this build, which is the fact worth saying;
 * `suppressed` is a decision the module made and recorded a reason for; `sent` cannot happen
 * here, so a board claiming it would be claiming an outbound path there is none of.
 */
export function waitingOn(
  notification: NotificationRow,
): "no_dispatcher" | "decided" | "settled" {
  if (notification.status === "requested" || notification.status === "deferred") {
    return "no_dispatcher";
  }
  if (notification.status === "suppressed") return "decided";
  return "settled";
}

/**
 * A decision reason as a message key, not as the enum the column stores.
 *
 * **"A rule id is not a reason", which MOD-005's board learned about flags**, applies here
 * word for word: `no_preference_stops_it` tells a reader nothing they can act on, and
 * `address_is_suppressed_on_this_channel` is a sentence written for a log. Each of these is a
 * different next action -- one means somebody asked not to be contacted, one means a cap
 * digested the message rather than dropping it, and one means the message went out under an
 * override that costs a stepped-up financial permission.
 *
 * **It returns a key rather than a sentence, and that was a defect for one commit.** The first
 * version held English sentences in this map, so the most explanatory field on the page
 * stayed in English on the Arabic one -- found by opening the board in Arabic, which no
 * assertion about structure could see. Every other string on these surfaces goes through the
 * catalogue; this one now does too.
 *
 * **An unknown value returns null and the caller renders it raw.** The set is the module's
 * and may grow; a new reason showing as its stored value is ugly and true, while rendering it
 * as "unknown" would hide a decision somebody needs to see -- the same judgement the
 * configuration board makes about a targeting rule it cannot name.
 */
const REASON_KEYS: Record<string, MessageKey> = {
  no_preference_stops_it: "notify.reason.noPreferenceStops",
  recipient_opted_out: "notify.reason.optedOut",
  address_is_suppressed_on_this_channel: "notify.reason.suppressed",
  quiet_hours: "notify.reason.quietHours",
  daily_cap_reached: "notify.reason.capReached",
  critical_bypass: "notify.reason.criticalBypass",
  channel_disabled_and_no_fallback: "notify.reason.channelOff",
  no_template_for_the_fallback_channel: "notify.reason.noFallbackTemplate",
};

export function reasonKey(reason: string): MessageKey | null {
  return REASON_KEYS[reason] ?? null;
}

/**
 * The channels a message could actually leave by, and what each would cost.
 *
 * A disabled channel with a fallback is the arrangement that matters: MOD-013's review found
 * that falling back resolved the channel *after* the preference, the suppression and the
 * address digest had been read for the channel the message was no longer going to -- so a
 * tenant falling back from email to SMS texted somebody who had said "don't text me", over a
 * channel that was itself disabled, to a number that had reported them as spam.
 */
export function usableChannels(policies: ChannelPolicy[]): ChannelPolicy[] {
  return policies.filter((p) => p.enabled);
}

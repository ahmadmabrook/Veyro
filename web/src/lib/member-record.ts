import type { MessageKey } from "@/i18n/locale";
import { api } from "@/lib/api";

/**
 * The three person-scoped access reads ADM-MEM-01's metric row and Access block need, and the
 * arithmetic that turns them into the canvas's four sentences.
 *
 * The canvas's five metric cells are `OUTSTANDING · MEMBERSHIP · LAST VISIT · PT CREDITS ·
 * ACCESS`. Four of the five had a read in this build already — MOD-017 answers the money, the
 * renewal and the credits — and `LAST VISIT` and `ACCESS` had none at all: MOD-022 could list
 * decisions by zone or by credential and nothing by person, so the one question a receptionist
 * asks about a member standing in front of them ("when did they last come in?") was
 * unanswerable from any route. `GET /access/attendance` and `GET /access/credentials` are
 * those two, and they were added for this screen.
 */

export type Attendance = {
  person_id: string;
  as_of: string;
  last_entry_on: string | null;
  last_entry_at: string | null;
  last_location: string | null;
  days_since: number | null;
  entries_in_window: number;
  weeks: number;
  /** Null where nothing has ever been recorded — which is not a rate of zero. */
  entries_per_week: number | null;
  /**
   * Every entry ever, which is a different question from the window beside it.
   *
   * ADM-MEM-07 draws `19d SINCE LAST · 2.8 WEEKLY AVG · 214 LIFETIME`, and the third is what
   * makes the first two mean something: a gap of nineteen days reads differently against two
   * hundred visits than against six.
   */
  lifetime_entries: number;
  chart_weeks: number;
  /**
   * One bucket per week, **including the empty ones**.
   *
   * The canvas's own reading of this chart is "three weeks at zero", which only means
   * anything if the zeros are drawn. A series that omitted them -- which is what a `GROUP BY`
   * returns if nobody fills the gaps -- draws a member who trained steadily.
   */
  by_week: { starts_on: string; ends_on: string; entries: number }[];
  recent: {
    on: string;
    /** Local to the club whose door they used, as `HH:MM`. */
    at: string;
    location_name: string;
    /** How they got in. Never the credential itself: the stored value is a SHA-256. */
    credential_kind: string | null;
    source: string;
  }[];
  recent_limit: number;
  no_reading_of_the_chart_is_offered?: string;
};

export type Credential = {
  credential_id: string;
  kind: string;
  state: string;
  issued_at: string;
  expires_at: string | null;
  revoked_at: string | null;
  revocation_epoch: number;
};

export type CredentialSet = {
  person_id: string;
  credentials: Credential[];
  live: number;
};

/**
 * The message key naming a credential kind.
 *
 * **The third stored value rendered as a label in one pass.** The canvas's recent-visits
 * list reads "Khalda · 18:40 · card"; this rendered `nfc_card`, which is the column's value
 * and not a word anybody says -- and in the Arabic build it is Latin letters in the middle
 * of an Arabic line, which the catalogue parity check is structurally blind to.
 *
 * Unknown kinds fall through to the stored value, as everywhere else: MOD-022's vocabulary
 * may grow, and "other" on a line that is telling somebody how a member got through a door
 * hides the part they would act on.
 */
export function credentialKindName(kind: string): MessageKey | null {
  const known: Record<string, MessageKey> = {
    qr_rotating: "credential.qrRotating",
    nfc_card: "credential.nfcCard",
    wallet_pass: "credential.walletPass",
    physical_card: "credential.physicalCard",
    pin: "credential.pin",
    staff_assisted: "credential.staffAssisted",
  };
  return known[kind] ?? null;
}

export function readAttendance(personId: string, weeks = 8): Promise<Attendance> {
  return api(
    `/access/attendance?person_id=${encodeURIComponent(personId)}&weeks=${weeks}`);
}

export function readCredentials(personId: string): Promise<CredentialSet> {
  return api(`/access/credentials?person_id=${encodeURIComponent(personId)}`);
}

/**
 * The timeline's five filters, as the canvas names them: `All · Money · Visits · Coaching ·
 * Messages`.
 *
 * **The mapping is by event type, and three of the five are empty in this build.** MOD-014
 * projects nine event types and `CLAUDE.md` records that none of MOD-017's nineteen, MOD-018's,
 * MOD-019's five, MOD-020's seven, MOD-021's six or MOD-022's six is among them — so a
 * member's timeline carries consent, membership, person and merge events and nothing about a
 * class they attended, a door they walked through or a message they were sent.
 *
 * That is why `visits`, `coaching` and `messages` are not offered as filters here. A filter
 * that is always empty tells a reader this member has never attended anything, which is a
 * statement about the projection rather than about the member — ADM-MEM-05's rule, applied to
 * a chip instead of a column. The projection's own gap is named at the foot of the page.
 */
export const TIMELINE_FILTERS = ["all", "money", "membership", "consent"] as const;

export type TimelineFilterKey = (typeof TIMELINE_FILTERS)[number];

export function isTimelineFilter(value: string | undefined): value is TimelineFilterKey {
  return value !== undefined && (TIMELINE_FILTERS as readonly string[]).includes(value);
}

/** Which filter an event type falls under, and which spine tone it draws. */
export function classifyEvent(eventType: string): {
  filter: Exclude<TimelineFilterKey, "all">;
  tone: "money" | "system" | "visit" | "coaching" | "consent";
} {
  if (eventType.startsWith("consent.") || eventType.startsWith("data_subject_request.")) {
    return { filter: "consent", tone: "consent" };
  }
  if (
    eventType.startsWith("invoice.")
    || eventType.startsWith("payment.")
    || eventType.startsWith("refund.")
  ) {
    return { filter: "money", tone: "money" };
  }
  if (eventType.startsWith("membership.") || eventType.startsWith("agreement.")) {
    return { filter: "membership", tone: "system" };
  }
  // Everything MOD-014 projects that is not one of the three above: a person created, a
  // profile changed, a duplicate merged. The canvas has no chip for these, so they appear
  // under `All` only — which is correct, since "Veyro changed this record" is not a life event
  // anybody filters for.
  return { filter: "membership", tone: "system" };
}

/**
 * The band in the record header: the one thing wrong with this member, or nothing.
 *
 * **Nothing is the signal.** The canvas's own note, over the healthy member: "No green
 * badges. Paid, active and granted are the expected cases — decorating them makes a genuinely
 * overdue row harder to spot. The absence of an alert band *is* the signal." So this returns
 * `null` for a member in good standing rather than a reassuring chip.
 */
export function recordBand(input: {
  outstandingMinor: number;
  membershipStatus: string | null;
}): { key: "member.bandOverdue" | "member.bandFrozen" | "member.bandLapsed";
      tone: "critical" | "warning" } | null {
  if (input.outstandingMinor > 0) {
    return { key: "member.bandOverdue", tone: "critical" };
  }
  if (input.membershipStatus === "frozen" || input.membershipStatus === "paused") {
    return { key: "member.bandFrozen", tone: "warning" };
  }
  if (input.membershipStatus === "lapsed" || input.membershipStatus === "cancelled") {
    return { key: "member.bandLapsed", tone: "warning" };
  }
  return null;
}

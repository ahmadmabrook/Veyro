import { describe, expect, it } from "vitest";

import { MESSAGES } from "@/i18n/locale";
import {
  reasonKey,
  releasable,
  suppressionIsLive,
  usableChannels,
  waitingOn,
  type ChannelPolicy,
  type NotificationRow,
  type Suppression,
} from "@/lib/notifications";

/**
 * The four judgements MOD-013's board makes, tested where they are made.
 *
 * **A decision reason is a next action, not a label.** `no_preference_stops_it` and
 * `recipient_opted_out` are two different things to do about a member; rendering the column
 * raw is "a rule id is not a reason", which MOD-005's board learned about flags.
 *
 * **Only an unsubscribe may be lifted.** A bounce or a complaint is the channel's judgement
 * about deliverability, and a tenant that could clear those would be choosing to keep sending
 * to an address that rejected them.
 *
 * **`requested` and `deferred` are both waiting for a dispatcher that does not exist**, which
 * is a different sentence from a queue making progress.
 */

function suppression(over: Partial<Suppression>): Suppression {
  return {
    suppression_id: "s1",
    channel: "email",
    address_digest: "a".repeat(64),
    reason: "unsubscribed",
    detail: null,
    recorded_at: "2026-11-01T00:00:00+00:00",
    released_at: null,
    ...over,
  };
}

function notification(over: Partial<NotificationRow>): NotificationRow {
  return {
    notification_id: "n1",
    template_key: "payment.failed",
    template_version: 1,
    category: "transactional",
    channel: "email",
    locale: "en",
    recipient_id: "p1",
    priority: "normal",
    status: "requested",
    decision_reason: "no_preference_stops_it",
    requested_at: "2026-11-20T00:00:00+00:00",
    ...over,
  };
}

function channel(over: Partial<ChannelPolicy>): ChannelPolicy {
  return {
    policy_id: "c1",
    channel: "email",
    enabled: true,
    fallback_channel: null,
    cost_per_message_minor: 2,
    currency: "JOD",
    updated_at: "2026-11-01T00:00:00+00:00",
    ...over,
  };
}

describe("reasonKey", () => {
  it("maps the stored enum to a catalogue key, not to an English sentence", () => {
    // **It returned sentences for one commit**, so the most explanatory field on the page
    // stayed in English on the Arabic one -- found by opening the board in Arabic, which no
    // assertion about structure could see. Every other string on these surfaces goes through
    // the catalogue and this one now does too.
    expect(reasonKey("recipient_opted_out")).toBe("notify.reason.optedOut");
    expect(reasonKey("daily_cap_reached")).toBe("notify.reason.capReached");
    // Two reasons a message did not go out, two different next actions.
    expect(reasonKey("recipient_opted_out")).not.toBe(
      reasonKey("address_is_suppressed_on_this_channel"),
    );
  });

  it("returns null for a reason it has no sentence for", () => {
    // The caller then renders the stored value raw. Ugly and true beats a friendly lie
    // about a decision somebody needs to see.
    expect(reasonKey("some_reason_added_later")).toBeNull();
  });

  it("names a key that exists in both catalogues", () => {
    // A key with no translation is the defect this change exists to fix, arriving from the
    // other side -- so every mapped key is asserted present in English and in Arabic.
    for (const stored of [
      "no_preference_stops_it", "recipient_opted_out",
      "address_is_suppressed_on_this_channel", "quiet_hours", "daily_cap_reached",
      "critical_bypass", "channel_disabled_and_no_fallback",
      "no_template_for_the_fallback_channel",
    ]) {
      const key = reasonKey(stored);
      expect(key).not.toBeNull();
      expect(MESSAGES.en[key!]).toBeTruthy();
      expect(MESSAGES.ar[key!]).toBeTruthy();
    }
  });
});

describe("releasable", () => {
  it("is true only for an unsubscribe", () => {
    expect(releasable(suppression({ reason: "unsubscribed" }))).toBe(true);
    expect(releasable(suppression({ reason: "bounced" }))).toBe(false);
    expect(releasable(suppression({ reason: "complained" }))).toBe(false);
  });
});

describe("suppressionIsLive", () => {
  it("is the released timestamp and nothing else", () => {
    expect(suppressionIsLive(suppression({}))).toBe(true);
    expect(
      suppressionIsLive(suppression({ released_at: "2026-11-10T00:00:00+00:00" })),
    ).toBe(false);
  });
});

describe("waitingOn", () => {
  it("treats requested and deferred alike, because both wait on a dispatcher", () => {
    expect(waitingOn(notification({ status: "requested" }))).toBe("no_dispatcher");
    expect(waitingOn(notification({ status: "deferred" }))).toBe("no_dispatcher");
  });

  it("calls a suppressed message decided, not waiting", () => {
    // A suppression is a decision the module made and recorded a reason for. Counting it as
    // waiting would inflate the one number on the page that means "nothing sends".
    expect(waitingOn(notification({ status: "suppressed" }))).toBe("decided");
  });

  it("calls anything else settled", () => {
    expect(waitingOn(notification({ status: "sent" }))).toBe("settled");
  });
});

describe("usableChannels", () => {
  it("drops a disabled channel even when it has a fallback", () => {
    // The fallback is where a message goes *from* this channel, not evidence that this one
    // works. MOD-013's review found a tenant texting somebody over a channel that was itself
    // disabled, because the fallback was resolved after everything was evaluated.
    const usable = usableChannels([
      channel({ policy_id: "a", channel: "email", enabled: true }),
      channel({ policy_id: "b", channel: "sms", enabled: false, fallback_channel: "email" }),
    ]);
    expect(usable.map((c) => c.channel)).toEqual(["email"]);
  });

  it("is empty when every channel is off, which is a state worth naming", () => {
    expect(usableChannels([channel({ enabled: false })])).toEqual([]);
  });
});

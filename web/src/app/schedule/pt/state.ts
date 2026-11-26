/**
 * What ADM-SCH-05's booking can say back.
 *
 * **Types only, so the client component can import it.** `@/lib/api` reaches `next/headers`,
 * and a pure name in an impure module is still impure to a bundler — which has broken this
 * app's build three times, once taking the sign-in page down with it.
 *
 * **One write, so there is one window and no partial state to report.** The session, the
 * coach's hold, the member's place and the credit all commit together (ADR-0019 D5), so
 * unlike ADM-SCH-03 there is nothing between "refused" and "done" for a reader to carry on
 * from.
 */
export type SessionBooked = {
  sessionId: string;
  coachName: string;
  startsAt: string;
  endsAt: string;
  minutes: number;
  timezone: string;
  /** `null` for an uncounted grant, which this build can sell: the draw succeeded either way. */
  creditsRemaining: number | null;
  /** True where the command answered a retry from what was already recorded. */
  repeated: boolean;
};

export type BookPtState = {
  booked: SessionBooked | null;
  error:
    | "pt.refusedBusy"
    | "pt.refusedNoCredit"
    | "pt.refused"
    | "pt.needsPermission"
    | "error.network"
    | "error.tooMany"
    | null;
};

export const IDLE: BookPtState = { booked: null, error: null };

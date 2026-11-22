/**
 * What FD-06's one write can say back.
 *
 * Types only, so the client component can import it — the split every screen here makes.
 */
export type CheckInState = {
  /** The booking that was just marked present, so the row can say so without a reload. */
  checkedIn: string | null;
  error:
    | "desk.checkInRefused"
    | "desk.checkInNotPermitted"
    | "desk.checkInTooLate"
    | "error.network"
    | "error.tooMany"
    | null;
};

export const IDLE: CheckInState = { checkedIn: null, error: null };

/** What FD-03's one write can say back. Types only, so the client component can import it. */
export type OverrideState = {
  done: boolean;
  error:
    | "denial.overrideRefused"
    | "denial.overrideNeedsStepUp"
    | "denial.overrideDenied"
    | "error.network"
    | "error.tooMany"
    | null;
};

export const IDLE: OverrideState = { done: false, error: null };

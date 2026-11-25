/**
 * What ADM-MSH-06's one write can say back.
 *
 * **Types only, so the client component can import it.** `@/lib/api` reaches `next/headers`
 * and a client component that imports a module touching it fails the build — the account
 * page's first version made the *login* page answer 500 that way, and FD-07 hit the same
 * thing through a module that merely held a pure predicate beside an impure import.
 */
export type PlanMoveError =
  | "downgrade.refused"
  | "downgrade.needsWrite"
  | "downgrade.confirmMismatch"
  | "error.network"
  | "error.tooMany";

export type Moved = {
  changeId: string;
  kind: string;
  effectiveOn: string;
  planName: string;
};

export type PlanMoveState = {
  moved: Moved | null;
  error: PlanMoveError | null;
  /** What they typed, so a refusal does not empty a field somebody is holding. */
  echo: { confirm?: string };
};

export const IDLE: PlanMoveState = { moved: null, error: null, echo: {} };

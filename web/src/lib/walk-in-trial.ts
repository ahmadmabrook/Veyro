/**
 * FD-05 · WALK-IN TRIAL — "Two fields. Sales will get the rest later."
 *
 * **Decisions only, and no import that reaches `next/headers`.** The form is a client
 * component, and this repository has paid for that lesson three times: the account page's
 * first version put its decisions beside its fetchers and made the *login* page answer 500,
 * the cash board's parse did it again, and the tell is a build error naming a chain of
 * `[Client Component Browser]` imports without ever mentioning `next/headers`.
 *
 * **The duplicate check is `@/lib/walk-in`'s, imported rather than re-decided.** A lead is a
 * person, so a number already on a record is already on a record -- the argument
 * `@/lib/contact-check` makes for ADM-MEM-10 and ADM-CRM-04 sharing one read, and this is the
 * third screen asking the same question. What is here is only what those two do not have: the
 * trial plan, and what to say about a trial that has started.
 */

/** One trial plan, as `GET /memberships/plans?trials=only` returns it. */
export type TrialPlan = {
  variant_id: string;
  display_name: string;
  trial_days: number | null;
};

/**
 * Which trial a walk-in is started on.
 *
 * **Three states, because a tenant can publish none, one or several**, and only the middle
 * one is the screen the canvas draws. The command derives the plan where there is one and
 * refuses with both named where there are two -- MOD-018's unordered lookup applied to what
 * somebody is sold -- so the picker exists for the case the drawing does not have, which is
 * `/rota`'s "no rota binds" judgement rather than a deviation.
 *
 * **`none` is a real state and not an error**: a gym that sells no trial cannot use this
 * screen at all, and saying so is better than a button whose own contract refuses it.
 */
export type PlanChoice =
  | { kind: "none" }
  | { kind: "one"; plan: TrialPlan }
  | { kind: "several"; plans: readonly TrialPlan[] };

export function planChoice(plans: readonly TrialPlan[]): PlanChoice {
  // `noUncheckedIndexedAccess` is on, so the first element is read rather than indexed --
  // which is the right strictness here: the three states are about the *count*, and an index
  // that the type system cannot see is bounded is how a one-plan branch comes to render
  // `undefined.display_name`.
  const [first] = plans;
  if (first === undefined) return { kind: "none" };
  if (plans.length === 1) return { kind: "one", plan: first };
  return { kind: "several", plans };
}

/**
 * The trial length the heading names, or `null` where it cannot be named.
 *
 * The canvas's title is "Start a 7-day trial" -- a figure, so it comes from the plan rather
 * than being written into the heading. With two plans of different lengths there is no single
 * answer until one is chosen, and a heading that named one of them would be naming whichever
 * sorted first.
 */
export function headlineDays(choice: PlanChoice): number | null {
  if (choice.kind !== "one") return null;
  return choice.plan.trial_days;
}

/** What the command did, as the route reports it step by step. */
export type TrialSteps = {
  person?: "created" | "named";
  lead?: "created" | "existing";
  agreement?: "created" | "existing";
  signature?: "recorded" | "existing";
  trial?: "created" | "existing";
};

/**
 * Whether this press started the trial or found one already running.
 *
 * **The server says which, so the screen does not infer it.** A press that found a live trial
 * returns that window and creates nothing -- which is the right answer for a member who
 * already walked in this morning, and the wrong thing to report as "started". The command's
 * four writes are resumable rather than atomic (ADR-0010 D12), so every step carries
 * `created` or `existing` and this reads the one a reader cares about.
 */
export function startedNow(steps: TrialSteps): boolean {
  return steps.trial !== "existing";
}

/**
 * **There is no day-of-trial arithmetic here, and that is deliberate.**
 *
 * A press that started a trial started it today, so the confirmation's "day 1 of 7" is a fact
 * about the write rather than a figure anybody computes -- and a press that found one already
 * running cannot be told which day it is on without a *today*, which is on no response. A
 * browser comparing dates against its own clock counts in the wrong frame, which this app has
 * three recorded defects from. ADM-CRM-05's card answers that question on the server, so the
 * confirmation links to the lead rather than deriving a second answer here.
 */

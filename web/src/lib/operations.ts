import { api } from "@/lib/api";

/**
 * MOD-010's and MOD-011's reads: what the system is doing to itself.
 *
 * **A backlog here is usually not a fault, and that is the whole difficulty of the screen.**
 * `evt_outbox` fills whenever any module writes a business row, and nothing in this build
 * drains it: there is no transport, no consumer has a handler behind it, and no worker loops
 * on the relay. So `pending_events` climbing is the missing worker runtime rather than a
 * failing one -- and the table has no DELETE grant for any runtime role, which is right for
 * evidence and means it grows without bound until an archive exists to move rows out.
 *
 * A surface that rendered the number alone would read as an incident every time somebody used
 * the product. The disclosure is the feature.
 */

export type OutboxHealth = {
  pending_events: number;
  oldest_pending_at: string | null;
  pending_deliveries: number;
  oldest_undelivered_at: string | null;
  dead_letters: number;
};

export type DeadLetter = {
  dead_letter_id: string;
  event_id: string;
  consumer: string;
  reason: string;
  attempts: number;
  quarantined_at: string;
  released_at: string | null;
  released_by: string | null;
  release_reason: string | null;
};

export type Subscription = {
  subscription_id: string;
  consumer: string;
  event_type: string;
  /** `safe` is delivered even under the default replay policy; `suppress` is not. */
  replay_safety: string;
  max_attempts: number;
  active: boolean;
  registered_at: string;
  deactivated_at: string | null;
};

export type Objective = {
  objective_id: string;
  objective_key: string;
  kind: string;
  metric_key: string;
  comparison: string;
  threshold: number;
  window_hours: number;
  aggregate_as: string;
  owner: string;
  runbook_ref: string | null;
  set_at: string;
  retired_at: string | null;
  dimensions: Record<string, string> | null;
};

export function readOutboxHealth(): Promise<OutboxHealth> {
  return api<OutboxHealth>("/events/health");
}

export function listDeadLetters(): Promise<DeadLetter[]> {
  return api<DeadLetter[]>("/events/dead-letters/all");
}

export function listSubscriptions(): Promise<Subscription[]> {
  return api<Subscription[]>("/events/subscriptions/all");
}

export function listObjectives(): Promise<Objective[]> {
  return api<Objective[]>("/ops/objectives");
}

/**
 * Whether a backlog is somebody's problem, which in this build it is not.
 *
 * **There is no consumer with a handler and no worker driving the relay**, so events accumulate
 * by design rather than by failure. The one number that *is* a fault whatever else is true is
 * a dead letter: something was delivered, failed its whole retry budget and is now quarantined
 * waiting for a person. Keeping the two apart is what stops this page crying wolf.
 */
export function backlogIsExpected(subscriptions: Subscription[]): boolean {
  return subscriptions.filter((subscription) => subscription.active).length === 0;
}

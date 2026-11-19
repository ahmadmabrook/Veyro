import { api } from "@/lib/api";

/**
 * MOD-010's, MOD-011's and the worker's reads: what the system is doing to itself.
 *
 * **A backlog here used to be expected and now it is a signal, which is a change worth
 * stating.** `evt_outbox` fills whenever any module writes a business row, and until the
 * worker runtime existed nothing drained it: the number climbing was the missing scheduler
 * rather than a failing one, and this page's job was to stop that reading as an incident.
 *
 * The relay now runs every fifteen seconds for every schedulable tenant, so a *pending event*
 * that persists means the worker is not running -- which is a fault, and the first one this
 * page can actually diagnose. A *pending delivery* is still expected whatever happens: no
 * consumer in this build has a handler behind it, there is no transport, and `evt_outbox` has
 * no DELETE grant for any runtime role, so the table still grows without bound until an
 * archive exists to move rows out.
 *
 * Telling those two apart needs evidence that the worker ran, which is what `/ops/worker`
 * carries. `relayVerdict` is that distinction and `backlogNote` is what the reader is told.
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

/** One scheduled job's record over the window, as `/ops/worker` reports it. */
export type WorkerJob = {
  job: string;
  summary: string;
  /** `app` is `veyro_cp_app`; `worker` is `veyro_cp_worker`, which holds the DELETE grants. */
  role: string;
  every_seconds: number;
  runs: number;
  failed: number;
  mean_duration_ms: number | null;
};

export type WorkerJobs = {
  window_hours: number;
  jobs: WorkerJob[];
  worker_gaps: string[];
};

export function readWorkerJobs(): Promise<WorkerJobs> {
  return api<WorkerJobs>("/ops/worker");
}

/**
 * Whether a backlog is somebody's problem.
 *
 * **There is no consumer with a handler**, so deliveries accumulate by design: that half has
 * not changed and `backlogIsExpected` is still the question for it. The one number that *is*
 * a fault whatever else is true is a dead letter -- something was delivered, failed its whole
 * retry budget and is now quarantined waiting for a person.
 */
export function backlogIsExpected(subscriptions: Subscription[]): boolean {
  return subscriptions.filter((subscription) => subscription.active).length === 0;
}

/**
 * Whether the relay is running, from what the worker recorded rather than from a heartbeat.
 *
 * **A zero is a real answer here, which is unusual for a count.** The relay runs every fifteen
 * seconds for every schedulable tenant, so no recorded run over a window of hours is a worker
 * that is not running -- the same reasoning MOD-011 refuses for an empty metric window, and it
 * holds here only because the denominator is known: the runner attempts every due job for
 * every tenant, so it knows the trials.
 *
 * `no_evidence` is kept apart from `stopped` on purpose. A reader without `ops.metric.read`,
 * or a request that failed, has learned nothing -- and rendering that as "stopped" would be
 * the page inventing an incident out of its own permissions.
 */
export type RelayVerdict = "running" | "stopped" | "no_evidence";

export function relayVerdict(worker: WorkerJobs | null): RelayVerdict {
  if (worker === null) return "no_evidence";
  const relay = worker.jobs.find((job) => job.job === "events.relay");
  if (relay === undefined) return "no_evidence";
  return relay.runs > 0 ? "running" : "stopped";
}

/** Every job that recorded a failure in the window. A failure is always worth a person. */
export function failingJobs(worker: WorkerJobs | null): WorkerJob[] {
  return (worker?.jobs ?? []).filter((job) => job.failed > 0);
}

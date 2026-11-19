import { describe, expect, it } from "vitest";

import {
  backlogIsExpected,
  failingJobs,
  relayVerdict,
  type Subscription,
  type WorkerJob,
  type WorkerJobs,
} from "@/lib/operations";

/**
 * The distinction the operations board now rests on: a backlog that is expected, and one that
 * is a stopped worker.
 *
 * **`no_evidence` is the case worth testing hardest.** A reader without `ops.metric.read` has
 * learned nothing about the worker, and rendering that as "stopped" would be the page
 * inventing an incident out of its own permissions -- the same mistake as showing an empty
 * dead-letter table to somebody who may not read it.
 */

function job(over: Partial<WorkerJob> = {}): WorkerJob {
  return {
    job: "events.relay",
    summary: "Fan pending outbox events out to their subscribers",
    role: "app",
    every_seconds: 15,
    runs: 240,
    failed: 0,
    mean_duration_ms: 3.2,
    ...over,
  };
}

function worker(...jobs: WorkerJob[]): WorkerJobs {
  return { window_hours: 24, jobs, worker_gaps: [] };
}

describe("the relay verdict", () => {
  it("is running when the worker recorded a run", () => {
    expect(relayVerdict(worker(job()))).toBe("running");
  });

  it("is stopped when the relay is declared and ran nothing", () => {
    // A zero is a real answer here, which is unusual for a count: the relay runs every fifteen
    // seconds for every schedulable tenant, so none over a window of hours is a worker that is
    // not running.
    expect(relayVerdict(worker(job({ runs: 0 })))).toBe("stopped");
  });

  it("is no evidence when the reader could not see the worker at all", () => {
    expect(relayVerdict(null)).toBe("no_evidence");
  });

  it("is no evidence when the relay is not among the jobs reported", () => {
    // A build that dropped the relay from the registry would otherwise read as "stopped",
    // which is a different and wrong sentence: nothing is failing, the job is gone.
    expect(relayVerdict(worker(job({ job: "access.replay_sweep" })))).toBe("no_evidence");
  });
});

describe("a failing job", () => {
  it("is every job with a failure in the window, and no others", () => {
    const failing = failingJobs(
      worker(job(), job({ job: "people.project_timeline", failed: 2 })),
    );
    expect(failing.map((entry) => entry.job)).toEqual(["people.project_timeline"]);
  });

  it("is none of them when the reader saw nothing", () => {
    expect(failingJobs(null)).toEqual([]);
  });
});

describe("a delivery backlog", () => {
  // This half did not change when the worker arrived: no consumer in this build has a handler,
  // so deliveries accumulate whatever the relay does.
  const subscription = (active: boolean): Subscription => ({
    subscription_id: "s",
    consumer: "a_consumer",
    event_type: "person.created",
    replay_safety: "safe",
    max_attempts: 5,
    active,
    registered_at: "2026-11-20T09:00:00Z",
    deactivated_at: null,
  });

  it("is expected while nothing is subscribed", () => {
    expect(backlogIsExpected([])).toBe(true);
    expect(backlogIsExpected([subscription(false)])).toBe(true);
  });

  it("is worth looking at once a consumer is routed to", () => {
    expect(backlogIsExpected([subscription(true)])).toBe(false);
  });
});

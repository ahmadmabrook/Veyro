import { redirect } from "next/navigation";

import { Alert } from "@/components/controls";
import { formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate } from "@/lib/api";
import {
  backlogIsExpected,
  failingJobs,
  listDeadLetters,
  listObjectives,
  listSubscriptions,
  readOutboxHealth,
  readWorkerJobs,
  relayVerdict,
  type DeadLetter,
  type Objective,
  type OutboxHealth,
  type Subscription,
  type WorkerJobs,
} from "@/lib/operations";
import { presentation } from "@/lib/preferences";
import { utcStamp } from "@/lib/time";

/**
 * The system watching itself: the event outbox, what failed delivery, and what is measured.
 *
 * **This page was built to make the repository's most-repeated gap visible in the product.**
 * "Nothing drives this on a schedule" appeared in fourteen module entries in `CLAUDE.md`, and
 * the event outbox was where it became countable: every module writes to it, the table has no
 * DELETE grant, and nothing drained it -- so the number climbed whenever somebody used the
 * product.
 *
 * **The worker runtime changed what a backlog means, and the page is where that shows.**
 * Until there was one, a growing `pending_events` was the missing scheduler and the screen's
 * job was to stop it reading as an incident. The relay now runs every fifteen seconds, so a
 * persistent pending event means the worker is down -- which is a fault, and the first one
 * this page can actually diagnose rather than excuse. Pending *deliveries* are unchanged: no
 * consumer here has a handler, so that half is still expected whatever happens.
 *
 * Telling the two apart needs evidence that the worker ran, which is what the scheduled-jobs
 * block carries. A zero there is a real answer -- every job runs for every tenant at least
 * every five minutes, so no recorded run over hours is a stopped worker -- and `no_evidence`
 * is kept apart from `stopped`, because a reader without `ops.metric.read` has learned
 * nothing and a page that called that an incident would be inventing one out of its own
 * permissions.
 *
 * Five blocks, five permissions, each gated on its own. A reader may hold the event read and
 * not the dead-letter read, and an empty table they are not allowed to see must not read as
 * "nothing is quarantined".
 */
export default async function OperationsPage() {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  const [mayEvents, mayDeadLetters, maySubscriptions, mayObjectives, mayMetrics] =
    await Promise.all([
      gate("events.event.read"),
      gate("events.dead_letter.read"),
      gate("events.subscription.read"),
      gate("ops.objective.read"),
      gate("ops.metric.read"),
    ]);

  const [health, deadLetters, subscriptions, objectives, worker] = await Promise.all([
    mayEvents.allowed ? readOutboxHealth().catch(toNull) : null,
    mayDeadLetters.allowed ? listDeadLetters().catch(toNull) : null,
    maySubscriptions.allowed ? listSubscriptions().catch(toNull) : null,
    mayObjectives.allowed ? listObjectives().catch(toNull) : null,
    mayMetrics.allowed ? readWorkerJobs().catch(toNull) : null,
  ]);

  const relay = relayVerdict(worker);

  return (
    <div className="stack" style={{ padding: "var(--space-6)", maxWidth: "960px" }}>
      <h1 style={{ margin: 0 }}>{text("ops.title")}</h1>
      <p className="muted" style={{ margin: 0 }}>
        {text("ops.lead")}
      </p>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("ops.outbox")}</h2>
        <Gated gate={mayEvents} value={health} locale={locale}>
          {(outbox: OutboxHealth) => (
            <>
              <dl className="facts">
                <dt className="muted">{text("ops.pendingEvents")}</dt>
                <dd style={{ margin: 0 }}>
                  <span className="data">
                    {formatInteger(outbox.pending_events, "latn")}
                  </span>
                  {outbox.oldest_pending_at ? (
                    <span className="muted">
                      {" · "}
                      {text("ops.oldest")}{" "}
                      <span className="data" dir="ltr">
                        {utcStamp(outbox.oldest_pending_at)}
                      </span>
                    </span>
                  ) : null}
                </dd>
                <dt className="muted">{text("ops.pendingDeliveries")}</dt>
                <dd style={{ margin: 0 }}>
                  <span className="data">
                    {formatInteger(outbox.pending_deliveries, "latn")}
                  </span>
                </dd>
                <dt className="muted">{text("ops.deadLetters")}</dt>
                <dd style={{ margin: 0 }}>
                  <span className="data">{formatInteger(outbox.dead_letters, "latn")}</span>
                </dd>
              </dl>
              {/* **Which kind of number this is.** Without these lines a backlog reads as an
                  incident, and with an alarm beside it this page would cry wolf on every
                  ordinary use of the product. The relay line comes first because it is the
                  one that can now be a fault; the delivery line is the standing disclosure. */}
              {relay === "stopped" ? (
                <Alert tone="error">{text("ops.backlogRelayStopped")}</Alert>
              ) : relay === "running" ? (
                <Alert tone="info">{text("ops.backlogRelayRunning")}</Alert>
              ) : null}
              <Alert tone="info">
                {subscriptions === null || backlogIsExpected(subscriptions)
                  ? text("ops.backlogExpected")
                  : text("ops.backlogUnexpected")}
              </Alert>
            </>
          )}
        </Gated>
      </section>

      <section className="panel stack">
        <h2 id="worker-heading" style={{ margin: 0 }}>
          {text("ops.worker")}
        </h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("ops.workerLead")}
        </p>
        <Gated gate={mayMetrics} value={worker} locale={locale}>
          {(jobs: WorkerJobs) => (
            <>
              {relay === "stopped" ? (
                <Alert tone="error">{text("ops.workerStopped")}</Alert>
              ) : null}
              {failingJobs(jobs).length > 0 ? (
                <Alert tone="error">{text("ops.workerFailing")}</Alert>
              ) : null}
              <table
                tabIndex={0}
                aria-labelledby="worker-heading"
                style={{ width: "100%", borderCollapse: "collapse" }}
              >
                <thead>
                  <tr>
                    <th scope="col" style={headCell}>{text("ops.job")}</th>
                    <th scope="col" style={headCell}>{text("ops.every")}</th>
                    <th scope="col" style={headCell}>{text("ops.runs")}</th>
                    <th scope="col" style={headCell}>{text("ops.failed")}</th>
                    <th scope="col" style={headCell}>{text("ops.mean")}</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.jobs.map((job) => (
                    <tr key={job.job}>
                      <td style={cell}>
                        <span className="data" dir="ltr">
                          {job.job}
                        </span>
                        <div className="muted" style={{ fontSize: "var(--type-label-size)" }}>
                          {job.summary}
                        </div>
                      </td>
                      <td style={cell}>
                        <span className="data" dir="ltr">
                          {formatInteger(job.every_seconds, "latn")}s
                        </span>
                      </td>
                      {/* A zero is the answer rather than an absence, so it is rendered as
                          words: "0" in a column of counts reads as "nothing happened to
                          count", and here it means the worker never ran. */}
                      <td style={cell}>
                        {job.runs === 0 ? (
                          <span className="muted">{text("ops.noRuns")}</span>
                        ) : (
                          <span className="data">{formatInteger(job.runs, "latn")}</span>
                        )}
                      </td>
                      <td style={cell}>
                        <span className="data">{formatInteger(job.failed, "latn")}</span>
                      </td>
                      <td style={cell}>
                        {job.mean_duration_ms === null ? (
                          <span className="muted">{"\u2014"}</span>
                        ) : (
                          <span className="data" dir="ltr">
                            {job.mean_duration_ms}ms
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <ul className="muted" style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
                {jobs.worker_gaps.map((gap) => (
                  <li key={gap}>{gap}</li>
                ))}
              </ul>
            </>
          )}
        </Gated>
      </section>

      <section className="panel stack">
        <h2 id="dead-letters-heading" style={{ margin: 0 }}>
          {text("ops.deadLetters")}
        </h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("ops.deadLetterAlert")}
        </p>
        <Gated gate={mayDeadLetters} value={deadLetters} locale={locale}>
          {(letters: DeadLetter[]) =>
            letters.length === 0 ? (
              <Alert tone="info">{text("ops.noDeadLetters")}</Alert>
            ) : (
              <table
                tabIndex={0}
                aria-labelledby="dead-letters-heading"
                style={{ width: "100%", borderCollapse: "collapse" }}
              >
                <thead>
                  <tr>
                    <th scope="col" style={headCell}>{text("ops.consumer")}</th>
                    <th scope="col" style={headCell}>{text("ops.attempts")}</th>
                    <th scope="col" style={headCell}>{text("ops.reason")}</th>
                    <th scope="col" style={headCell}>{text("ops.quarantined")}</th>
                  </tr>
                </thead>
                <tbody>
                  {letters.map((letter) => (
                    <tr key={letter.dead_letter_id}>
                      <td style={cell}>
                        <span className="data" dir="ltr">
                          {letter.consumer}
                        </span>
                      </td>
                      <td style={cell}>
                        <span className="data">{formatInteger(letter.attempts, "latn")}</span>
                      </td>
                      <td style={cell}>{letter.reason}</td>
                      <td style={cell}>
                        <span className="data" dir="ltr">
                          {utcStamp(letter.quarantined_at)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          }
        </Gated>
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("ops.subscriptions")}</h2>
        {/* **The standing disclosure is above the table, not inside the empty case.** It used
            to live in the "nothing is subscribed" message, so the day a subscription existed
            the page stopped saying that no name in this build has a handler -- which is the
            fact a reader needs most once there is routing to look at. */}
        <p className="muted" style={{ margin: 0 }}>
          {text("ops.routingLead")}
        </p>
        <Gated gate={maySubscriptions} value={subscriptions} locale={locale}>
          {(rows: Subscription[]) =>
            rows.length === 0 ? (
              <Alert tone="info">{text("ops.noSubscriptions")}</Alert>
            ) : (
              <ul style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
                {rows.map((row) => (
                  <li key={row.subscription_id}>
                    <span className="data" dir="ltr">
                      {row.consumer} ← {row.event_type}
                    </span>
                    {" · "}
                    {text("ops.replaySafety")}: {row.replay_safety}
                    {" · "}
                    {row.active ? text("ops.active") : text("ops.inactive")}
                  </li>
                ))}
              </ul>
            )
          }
        </Gated>
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("ops.objectives")}</h2>
        <Gated gate={mayObjectives} value={objectives} locale={locale}>
          {(rows: Objective[]) =>
            rows.length === 0 ? (
              <Alert tone="info">{text("ops.noObjectives")}</Alert>
            ) : (
              <ul style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
                {rows.map((row) => (
                  <li key={row.objective_id}>
                    <span className="data" dir="ltr">
                      {row.objective_key}
                    </span>
                    {" · "}
                    <span className="data" dir="ltr">
                      {row.metric_key} {row.comparison} {row.threshold}
                    </span>
                    {" · "}
                    <span className="data">{formatInteger(row.window_hours, "latn")}</span>{" "}
                    {text("ops.hours")}
                    {" · "}
                    {text("ops.owner")}: {row.owner}
                  </li>
                ))}
              </ul>
            )
          }
        </Gated>
      </section>
    </div>
  );
}

/**
 * One block's three outcomes: refused, failed, or rendered.
 *
 * **A refusal and an empty list must not look alike.** An operator who cannot read the
 * dead-letter table and is shown an empty one concludes nothing is quarantined, which is a
 * different fact from "you may not see what is".
 */
function Gated<T>({
  gate,
  value,
  locale,
  children,
}: {
  gate: { allowed: boolean; reachable: boolean };
  value: T | null;
  locale: Locale;
  children: (value: T) => React.ReactNode;
}) {
  const text = (key: MessageKey) => t(locale, key);
  if (!gate.allowed) {
    return (
      <Alert tone="info">
        {gate.reachable ? text("gate.denied") : text("gate.unreachable")}
      </Alert>
    );
  }
  if (value === null) return <Alert tone="error">{text("error.unexpected")}</Alert>;
  return <>{children(value)}</>;
}

function toNull(error: unknown): null {
  if (error instanceof ApiError) return null;
  throw error;
}

const headCell: React.CSSProperties = {
  textAlign: "start",
  padding: "var(--space-2) var(--space-3)",
  borderBottom: "1px solid var(--color-border-default)",
  background: "var(--color-surface-sunken)",
  fontSize: "var(--type-label-size)",
  fontWeight: "var(--type-label-weight)",
};

const cell: React.CSSProperties = {
  textAlign: "start",
  verticalAlign: "top",
  padding: "var(--space-2) var(--space-3)",
  borderBottom: "1px solid var(--color-border-subtle)",
};


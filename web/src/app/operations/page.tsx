import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { MetricCell, MetricRow } from "@/components/ds/metric-cell";
import { PageHeader } from "@/components/ds/page-header";
import { DataGrid } from "@/components/ds/data-grid";
import {
  fill,
  formatInteger,
  t,
  type Locale,
  type MessageKey,
  type Numbering,
} from "@/i18n/locale";
import {
  ApiError,
  currentSession,
  gateAll,
  gateMessage,
  type GateAnswer,
} from "@/lib/api";
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
import { numerals } from "@/lib/display";
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
  // **The tenant's numerals** -- ADR-0015. Every quantity on this page follows
  // `localization.numerals`; an identifier does not, and neither does money. One read for the
  // whole render: `conventions()` is React's per-request memo and the layout starts it.
  const numbering = await numerals();
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  // One round trip rather than several: `/authz/checks` asks the same question about
  // every action at once, with the same scope resolution and the same assurance weighing.
  // The semantics are identical -- it is not a permission list, which would be MOD-014's
  // "a grant is not a session" finding.
  const [mayEvents, mayDeadLetters, maySubscriptions, mayObjectives, mayMetrics] = await gateAll([
    "events.event.read",
    "events.dead_letter.read",
    "events.subscription.read",
    "ops.objective.read",
    "ops.metric.read",
  ] as const);

  const [health, deadLetters, subscriptions, objectives, worker] = await Promise.all([
    mayEvents.allowed ? readOutboxHealth().catch(toNull) : null,
    mayDeadLetters.allowed ? listDeadLetters().catch(toNull) : null,
    maySubscriptions.allowed ? listSubscriptions().catch(toNull) : null,
    mayObjectives.allowed ? listObjectives().catch(toNull) : null,
    mayMetrics.allowed ? readWorkerJobs().catch(toNull) : null,
  ]);

  const relay = relayVerdict(worker);

  return (
    <div className="stack">
      <PageHeader title={text("ops.title")}
        figures={fill(locale, "ops.deliveriesCounted",
          { count: health?.pending_deliveries ?? 0 }, numbering)}
       />

      {/* **The two figures that are faults, out of a line of three.** A pending delivery is
          expected here -- no name in this build has a handler -- so it stays on the figures
          line; a pending *event* that persists is a relay that is down, and a dead letter is
          a fault whatever else is true. Both were rendered at `type.bodySm` beside the one
          clause that means nothing is wrong.

          **A refused read is not a zero**, which matters more here than anywhere: the
          figures line coalesces an absent health read to `0`, and a *large* zero over
          "events waiting to be dispatched" would read as an empty outbox -- the one reading
          that is always wrong. The cells make the same distinction `Gated` makes below, from
          the same gate answer and the same two keys. */}
      <MetricRow label={text("ops.outbox")}>
        <MetricCell
          label={text("ops.pendingEvents")}
          {...outboxFigure(mayEvents, health?.pending_events, locale, numbering)}
        />
        <MetricCell
          label={text("ops.deadLetters")}
          {...outboxFigure(mayEvents, health?.dead_letters, locale, numbering)}
        />
      </MetricRow>

      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("ops.outbox")}</h2>
        <Gated gate={mayEvents} value={health} locale={locale}>
          {(outbox: OutboxHealth) => (
            <>
              <dl className="facts">
                <dt className="muted">{text("ops.pendingEvents")}</dt>
                <dd style={{ margin: 0 }}>
                  <span className="data">
                    {formatInteger(outbox.pending_events, numbering)}
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
                    {formatInteger(outbox.pending_deliveries, numbering)}
                  </span>
                </dd>
                <dt className="muted">{text("ops.deadLetters")}</dt>
                <dd style={{ margin: 0 }}>
                  <span className="data">{formatInteger(outbox.dead_letters, numbering)}</span>
                </dd>
              </dl>
              {/* **Which kind of number this is.** Without these lines a backlog reads as an
                  incident, and with an alarm beside it this page would cry wolf on every
                  ordinary use of the product. The relay line comes first because it is the
                  one that can now be a fault; the delivery line is the standing disclosure. */}
              {relay === "stopped" ? (
                <Banner severity="critical">{text("ops.backlogRelayStopped")}</Banner>
              ) : relay === "running" ? (
                <Banner severity="info">{text("ops.backlogRelayRunning")}</Banner>
              ) : null}
              <Banner severity="info">
                {subscriptions === null || backlogIsExpected(subscriptions)
                  ? text("ops.backlogExpected")
                  : text("ops.backlogUnexpected")}
              </Banner>
            </>
          )}
        </Gated>
      </section>

      <section className="page-section">
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
                <Banner severity="critical">{text("ops.workerStopped")}</Banner>
              ) : null}
              {failingJobs(jobs).length > 0 ? (
                <Banner severity="critical">{text("ops.workerFailing")}</Banner>
              ) : null}
              <DataGrid
                caption={text("ops.worker")}
                countLabel={fill(locale, "grid.count.jobs", { count: jobs.jobs.length }, numbering)}
                labelledBy="worker-heading"
                rows={jobs.jobs}
                rowKey={(job) => job.job}
                // A job with no recorded run over the window is a stopped worker, which is
                // the first fault this page can diagnose rather than excuse.
                rowSeverity={(job) => (job.failed > 0 ? "critical" : job.runs === 0 ? "attention" : null)}
                columns={[
                  {
                    header: text("ops.job"),
                    kind: "text",
                    priority: 1,
                    render: (job) => (
                      <>
                        <span className="data" dir="ltr">{job.job}</span>
                        <div className="muted" style={{ fontSize: "var(--type-label-size)" }}>
                          {job.summary}
                        </div>
                      </>
                    ),
                  },
                  {
                    header: text("ops.runs"),
                    kind: "text",
                    priority: 1,
                    // A zero is the answer rather than an absence, so it is rendered as
                    // words: "0" in a column of counts reads as "nothing happened to count",
                    // and here it means the worker never ran.
                    render: (job) =>
                      job.runs === 0 ? (
                        <span className="muted">{text("ops.noRuns")}</span>
                      ) : (
                        <span className="data">{formatInteger(job.runs, numbering)}</span>
                      ),
                  },
                  {
                    header: text("ops.failed"),
                    kind: "text",
                    priority: 1,
                    render: (job) => (
                      <span className="data">{formatInteger(job.failed, numbering)}</span>
                    ),
                  },
                  {
                    header: text("ops.every"),
                    kind: "text",
                    priority: 3,
                    render: (job) => (
                      <span className="data" dir="ltr">
                        {formatInteger(job.every_seconds, numbering)}s
                      </span>
                    ),
                  },
                  {
                    header: text("ops.mean"),
                    kind: "text",
                    priority: 2,
                    render: (job) =>
                      job.mean_duration_ms === null ? (
                        <span className="muted">{"\u2014"}</span>
                      ) : (
                        <span className="data" dir="ltr">{job.mean_duration_ms}ms</span>
                      ),
                  },
                ]}
              />
              <ul className="muted" style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
                {jobs.worker_gaps.map((gap) => (
                  <li key={gap}>{gap}</li>
                ))}
              </ul>
            </>
          )}
        </Gated>
      </section>

      <section className="page-section">
        <h2 id="dead-letters-heading" style={{ margin: 0 }}>
          {text("ops.deadLetters")}
        </h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("ops.deadLetterAlert")}
        </p>
        <Gated gate={mayDeadLetters} value={deadLetters} locale={locale}>
          {(letters: DeadLetter[]) =>
            letters.length === 0 ? (
              <Banner severity="info">{text("ops.noDeadLetters")}</Banner>
            ) : (
              <DataGrid
                caption={text("ops.deadLetters")}
                countLabel={fill(locale, "grid.count.deadLetters", { count: letters.length }, numbering)}
                labelledBy="dead-letters-heading"
                rows={letters}
                rowKey={(letter) => letter.dead_letter_id}
                // A dead letter is a fault whatever else is true, so every row carries it.
                rowSeverity={() => "critical"}
                columns={[
                  {
                    header: text("ops.consumer"),
                    kind: "text",
                    priority: 1,
                    render: (letter) => (
                      <span className="data" dir="ltr">{letter.consumer}</span>
                    ),
                  },
                  {
                    header: text("ops.reason"),
                    kind: "text",
                    priority: 1,
                    render: (letter) => letter.reason,
                  },
                  {
                    header: text("ops.attempts"),
                    kind: "text",
                    priority: 2,
                    render: (letter) => (
                      <span className="data">{formatInteger(letter.attempts, numbering)}</span>
                    ),
                  },
                  {
                    header: text("ops.quarantined"),
                    kind: "date",
                    priority: 2,
                    render: (letter) => (
                      <span className="data" dir="ltr">{utcStamp(letter.quarantined_at)}</span>
                    ),
                  },
                ]}
              />
            )
          }
        </Gated>
      </section>

      <section className="page-section">
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
              <Banner severity="info">{text("ops.noSubscriptions")}</Banner>
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

      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("ops.objectives")}</h2>
        <Gated gate={mayObjectives} value={objectives} locale={locale}>
          {(rows: Objective[]) =>
            rows.length === 0 ? (
              <Banner severity="info">{text("ops.noObjectives")}</Banner>
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
                    <span className="data">{formatInteger(row.window_hours, numbering)}</span>{" "}
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
/**
 * One outbox figure for the metric row, and the distinction it carries.
 *
 * The figures line reads `health?.pending_events ?? 0`, which is honest enough at
 * `type.bodySm` beside two other clauses and is not at figure size: a large zero over "events
 * waiting to be dispatched" says the outbox is clear, which is the one reading that is always
 * wrong. So the three states stay apart, using the same gate answer and the same two message
 * keys `Gated` uses for the sections below -- a refusal names what the session may not see,
 * and a failed read says so rather than reporting a measurement nobody made.
 */
function outboxFigure(
  gate: GateAnswer,
  value: number | undefined,
  locale: Locale,
  numbering: Numbering,
) {
  if (!gate.allowed) {
    return {
      freshness: "unavailable" as const,
      unavailableBecause: t(locale, gateMessage(gate)),
    };
  }
  if (value === undefined) {
    return {
      freshness: "unavailable" as const,
      unavailableBecause: t(locale, "error.unexpected"),
    };
  }
  return {
    value: (
      <span className="data" dir="ltr">{formatInteger(value, numbering)}</span>
    ),
  };
}

function Gated<T>({
  gate,
  value,
  locale,
  children,
}: {
  // **The whole answer, not two booleans of it.** A refusal has four meanings and only the
  // full answer can tell them apart: a narrowed shape here reported a failed request as
  // "Not permitted", which is the defect `gateMessage` exists for.
  gate: GateAnswer;
  value: T | null;
  locale: Locale;
  children: (value: T) => React.ReactNode;
}) {
  const text = (key: MessageKey) => t(locale, key);
  if (!gate.allowed) {
    return (
      <Banner severity="info">
        {text(gateMessage(gate))}
      </Banner>
    );
  }
  if (value === null) return <Banner severity="critical">{text("error.unexpected")}</Banner>;
  return <>{children(value)}</>;
}

function toNull(error: unknown): null {
  if (error instanceof ApiError) return null;
  throw error;
}




import { redirect } from "next/navigation";

import { Alert } from "@/components/controls";
import { formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate } from "@/lib/api";
import {
  backlogIsExpected,
  listDeadLetters,
  listObjectives,
  listSubscriptions,
  readOutboxHealth,
  type DeadLetter,
  type Objective,
  type OutboxHealth,
  type Subscription,
} from "@/lib/operations";
import { presentation } from "@/lib/preferences";

/**
 * The system watching itself: the event outbox, what failed delivery, and what is measured.
 *
 * **This page exists to make the repository's most-repeated gap visible in the product.**
 * Fourteen modules in `CLAUDE.md` end with some version of "nothing drives this on a
 * schedule", and the event outbox is where that is countable: every module writes to it, no
 * consumer in this build has a handler, no worker loops on the relay, and the table has no
 * DELETE grant -- so the number climbs whenever somebody uses the product.
 *
 * **A backlog is therefore not an incident here, and the page has to say which kind of number
 * it is showing.** Rendering "12 events pending" with an alarm beside it would cry wolf every
 * time; rendering it with no explanation would let somebody conclude the relay is working.
 * `backlogIsExpected` is the distinction -- no active subscription means nothing was ever
 * going to drain it -- and a dead letter is kept separate because that one *is* a fault
 * whatever else is true: a delivery used its entire retry budget and is waiting for a person.
 *
 * Four blocks, four permissions, each gated on its own. A reader may hold the event read and
 * not the dead-letter read, and an empty table they are not allowed to see must not read as
 * "nothing is quarantined".
 */
export default async function OperationsPage() {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  const [mayEvents, mayDeadLetters, maySubscriptions, mayObjectives] = await Promise.all([
    gate("events.event.read"),
    gate("events.dead_letter.read"),
    gate("events.subscription.read"),
    gate("ops.objective.read"),
  ]);

  const [health, deadLetters, subscriptions, objectives] = await Promise.all([
    mayEvents.allowed ? readOutboxHealth().catch(toNull) : null,
    mayDeadLetters.allowed ? listDeadLetters().catch(toNull) : null,
    maySubscriptions.allowed ? listSubscriptions().catch(toNull) : null,
    mayObjectives.allowed ? listObjectives().catch(toNull) : null,
  ]);

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
              <dl style={listStyle}>
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
                        {outbox.oldest_pending_at.slice(0, 16).replace("T", " ")}
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
              {/* **Which kind of number this is.** Without this line a backlog reads as an
                  incident, and with an alarm beside it this page would cry wolf on every
                  ordinary use of the product. */}
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
                          {letter.quarantined_at.slice(0, 16).replace("T", " ")}
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

const listStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "minmax(16rem, auto) 1fr",
  gap: "var(--space-2) var(--space-4)",
  margin: 0,
};

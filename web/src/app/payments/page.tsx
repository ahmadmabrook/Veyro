import { redirect } from "next/navigation";
import Link from "next/link";

import { Banner } from "@/components/ds/banner";
import { DataGrid } from "@/components/ds/data-grid";
import { MoneyValue } from "@/components/ds/money-value";
import { PageHeader } from "@/components/ds/page-header";
import { Prose } from "@/components/prose";
import { Withheld } from "@/components/withheld";
import { fill, formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { currentSession, gateAll, failureMessage } from "@/lib/api";
import { readCollections, type Collections } from "@/lib/command-centre-reads";
import { listMembers } from "@/lib/members-reads";
import { exceptions, moneyKind, readPayments, type PaymentsLedger } from "@/lib/payments";
import { isWithheld } from "@/lib/people";
import { presentation } from "@/lib/preferences";
import { utcStamp } from "@/lib/time";

/**
 * ADM-PAY-01 · PAYMENTS LEDGER — "Money, and the one place friction is correct".
 *
 * **This screen did not exist, and `/finance` was being counted as it.** That route is
 * MOD-018's general ledger: the chart of accounts, the period lock and the trial balance,
 * which is what an accountant closes a month with. The payments ledger is what a manager
 * opens every morning, and the compliance record has carried the mismatch as a named
 * deviation since the audit. The read behind it is new as well -- MOD-017 could answer "what
 * does this member owe" and had nothing that put a tenant's payments, failed attempts,
 * refunds and disputes in one list.
 *
 * The canvas's measurements and its rules:
 *
 * > JOD 41,280.00 collected · 1–19 August · all locations · 6 failed, 3 refunded, 2 disputed
 * > Needs action · 8 | All | Export
 * > DATE · MEMBER · METHOD · AMOUNT · STATE · NEXT
 * >
 * > Refunds carry a negative sign and the parenthetical original. **A refund is never shown
 * > as a payment of a different colour — it is a different sign on the same axis.**
 * >
 * > COMPONENTS · DataGrid(Compact, 34px) ×7 rows
 *
 * Three things the build decides rather than copies:
 *
 * - **The MEMBER column is composed, not returned.** `finance.payment.read` is tenant-wide
 *   and its rows carry a `payer_person_id` and nothing else about anybody; a money permission
 *   that returned names would be a lateral read path around `people.person.read`, which is
 *   MOD-010's `events.event.read` finding. So the page asks MOD-014 for the page's payers
 *   through MOD-014's own gate, exactly as the members list composes MOD-017's plans -- and a
 *   reader without that permission gets the ledger with ids rather than a refusal.
 * - **There is no refund form and no Export.** Requesting a refund is tier 3 *and* tier 4 in
 *   the design's own scale -- a typed confirmation and a second person -- and
 *   `finance.refund.request` is a stepped-up financial permission with no form in this build.
 *   A button that answered 403 would be worse than the gap, which is ADM-MEM-05's rule.
 * - **"Needs action" is a link, not client state**, so the filtered view is in the URL and
 *   somebody can send a colleague the one they are looking at.
 */
export default async function PaymentsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);
  const query = await searchParams;
  const needsAction = query.filter === "needs_action";

  if (!(await currentSession())) redirect("/login");

  // One round trip rather than several: `/authz/checks` asks the same question about
  // every action at once, with the same scope resolution and the same assurance weighing.
  // The semantics are identical -- it is not a permission list, which would be MOD-014's
  // "a grant is not a session" finding.
  const [mayPayments, mayRevenue, mayPeople] = await gateAll([
    "finance.payment.read",
    "finance.revenue.read",
    "people.person.read",
  ] as const);

  if (!mayPayments.allowed) {
    return (
      <Shell locale={locale}>
        <Banner severity="info">
          {mayPayments.reachable ? text("gate.denied") : text("gate.unreachable")}
        </Banner>
      </Shell>
    );
  }

  let ledger: PaymentsLedger;
  try {
    ledger = await readPayments({ needsAction });
  } catch (error) {
    return (
      <Shell locale={locale}>
        <Banner severity="critical">
          {text(failureMessage(error))}
        </Banner>
      </Shell>
    );
  }

  // The header's figure. Collected month to date is MOD-017's own arithmetic, already built
  // for the Command Center's first metric -- rendering a second sum over the rows on screen
  // would be a figure that disagrees with it the moment the page is bounded, which it is.
  const collections: Collections | null = mayRevenue.allowed
    ? await readCollections().catch(() => null)
    : null;
  const collected = collections?.collected[0] ?? null;

  // **The MEMBER column, composed.** One extra request for the page rather than one per row.
  const names = mayPeople.allowed
    ? await listMembers({ limit: 200 }).then(
      (page) => new Map(page.people.map((person) => [person.person_id, person.legal_name])),
    ).catch(() => null)
    : null;

  const shown = exceptions(ledger);

  return (
    <Shell
      locale={locale}
      // "JOD 41,280.00 collected · 1–19 August · all locations · 6 failed, 3 refunded,
      // 2 disputed" -- and the last clause is only the non-zero parts, because a clean
      // period says nothing here.
      figures={
        <>
          {collected === null ? (
            text("payments.collectedUnavailable")
          ) : (
            <>
              <MoneyValue
                kind="aggregate"
                amountMinor={collected.collected_minor}
                currency={collected.currency}
              />{" "}
              {text("payments.collected")}
            </>
          )}
          {" · "}
          <span className="data" dir="ltr">{ledger.since} — {ledger.until}</span>
          {" · "}
          {text("payments.allLocations")}
          {shown.length === 0 ? null : (
            <> {"· "}{shown.map((one, index) => (
              <span key={one.key}>
                {index === 0 ? null : ", "}
                {fill(locale, one.key, { count: one.count })}
              </span>
            ))}</>
          )}
        </>
      }
    >
      {/* The canvas's two chips. Links rather than client state, so the view is in the URL. */}
      <nav className="ds-segmented" aria-label={text("payments.views")}>
        <Link
          href="/payments?filter=needs_action"
          {...(needsAction ? { "aria-current": "page" as const } : {})}
        >
          {fill(locale, "payments.needsAction", { count: ledger.needs_action })}
        </Link>
        <Link href="/payments" {...(needsAction ? {} : { "aria-current": "page" as const })}>
          {text("payments.all")}
        </Link>
      </nav>

      <section className="page-section" aria-labelledby="ledger-heading">
        <h2 id="ledger-heading" className="ds-visually-hidden">{text("payments.title")}</h2>
        {ledger.entries.length === 0 ? (
          <Banner severity="info">
            {text(needsAction ? "payments.nothingNeedsAction" : "payments.empty")}
          </Banner>
        ) : (
          <DataGrid
            caption={text("payments.title")}
            labelledBy="ledger-heading"
            density="compact"
            rows={ledger.entries}
            rowKey={(entry) => `${entry.kind}:${entry.row_id}`}
            // A row somebody has to act on: a failed charge, a refund nobody has settled, an
            // open dispute. The canvas's own count chip is the same set.
            rowSeverity={(entry) => (entry.needs_action ? "attention" : null)}
            columns={[
              {
                header: text("payments.date"),
                kind: "date",
                priority: 1,
                render: (entry) => (
                  <span className="data" dir="ltr">{utcStamp(entry.at)}</span>
                ),
              },
              {
                header: text("payments.member"),
                kind: "person",
                priority: 1,
                render: (entry) => {
                  if (entry.payer_person_id === null) {
                    return <span className="muted">{text("payments.noPayer")}</span>;
                  }
                  const name = names?.get(entry.payer_person_id);
                  // **Three answers, and they are different facts.** No permission to read
                  // people at all; a name this page's own read did not cover; and a name the
                  // gate masked. Rendering any of them as a blank would say the payment has
                  // no payer.
                  if (names === null) {
                    return (
                      <span className="data" dir="ltr">
                        {entry.payer_person_id.slice(0, 8)}
                      </span>
                    );
                  }
                  if (name === undefined) {
                    return <span className="muted">{text("payments.notOnThisPage")}</span>;
                  }
                  return isWithheld(name) ? (
                    <Withheld locale={locale} reason="member.withheldIdentity" />
                  ) : (
                    <Link href={`/people/${entry.payer_person_id}`}>{name}</Link>
                  );
                },
              },
              {
                header: text("payments.method"),
                kind: "text",
                priority: 3,
                render: (entry) => <span className="data" dir="ltr">{entry.method}</span>,
              },
              {
                header: text("payments.amount"),
                kind: "money",
                priority: 1,
                // **One axis, one sign.** A refund is a negative number beside a payment and
                // never a payment of another colour -- which is also what makes the column
                // add up to something a reader can check.
                render: (entry) => (
                  <MoneyValue
                    kind={moneyKind(entry)}
                    amountMinor={entry.amount_minor}
                    currency={entry.currency}
                  />
                ),
              },
              {
                header: text("payments.state"),
                kind: "status",
                priority: 2,
                render: (entry) => (
                  <>
                    {entry.state}
                    <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
                      {text(`payments.kind.${entry.kind}` as MessageKey)}
                      {entry.about_payment_id === null
                        || entry.about_payment_id === entry.row_id
                        ? null
                        : (
                          // The canvas's "parenthetical original": a negative figure with no
                          // story is a figure nobody can check.
                          <>
                            {" ("}
                            <span className="data" dir="ltr">
                              {entry.about_payment_id.slice(0, 8)}
                            </span>
                            {")"}
                          </>
                        )}
                    </div>
                  </>
                ),
              },
              {
                header: text("payments.next"),
                kind: "text",
                priority: 2,
                // **What has to happen, not a button that would answer 403.** Settling a
                // refund, responding to a dispute and retrying a charge are all stepped-up
                // financial permissions with no form in this build.
                // **Only the three kinds that can need action have a key.** A received
                // payment is never `needs_action`, so a `payments.next.payment` message
                // was a declared value nothing could ever write -- which is the defect
                // this repository names in four modules, in a message catalogue. The
                // parity check caught it: the em-dash was identical in both locales
                // because nothing was ever going to render it.
                render: (entry) =>
                  entry.needs_action && entry.kind !== "payment" ? (
                    text(`payments.next.${entry.kind}` as MessageKey)
                  ) : (
                    <span className="muted">—</span>
                  ),
              },
            ]}
          />
        )}
        <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
          <span className="data">{formatInteger(ledger.count, "latn")}</span>{" "}
          {text("payments.rows")}
          {ledger.truncated ? <> {"· "}{text("payments.truncated")}</> : null}
        </p>
      </section>

      {/* What this screen cannot do, at the foot. Both are the design's own tier 3 and tier
          4 and both are real: a refund needs a typed amount *and* a second person, and
          nothing in this build has a form for either. */}
      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("payments.notYet")}</h2>
        <dl className="facts">
          <dt className="muted">{text("payments.refundTitle")}</dt>
          {/* **Rendered, not printed.** The reason names a permission in backticks, which
              is how every such note in this repository is written -- and `/privacy`'s board
              already learned that printing the delimiters puts punctuation nobody wrote in
              front of a reader. */}
          <dd style={{ margin: 0 }}><Prose>{text("payments.refundWhy")}</Prose></dd>
          <dt className="muted">{text("payments.exportTitle")}</dt>
          <dd style={{ margin: 0 }}>{text("payments.exportWhy")}</dd>
          <dt className="muted">{text("payments.locationTitle")}</dt>
          <dd style={{ margin: 0 }}>{text("payments.locationWhy")}</dd>
        </dl>
      </section>
    </Shell>
  );
}

function Shell({
  locale,
  children,
  figures,
}: {
  locale: Locale;
  children: React.ReactNode;
  figures?: React.ReactNode;
}) {
  return (
    <div className="stack">
      {/* The canvas's own title. It is the screen's argument rather than its noun: friction
          on money leaving the business is deliberate, and the heading says so before the
          table does. */}
      <PageHeader
        title={t(locale, "payments.heading")}
        {...(figures ? { figures } : {})}
      />
      {children}
    </div>
  );
}

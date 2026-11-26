import { redirect } from "next/navigation";
import Link from "next/link";

import { Banner } from "@/components/ds/banner";
import { NotYet } from "@/components/not-yet";
import { DataGrid } from "@/components/ds/data-grid";
import { MetricCell, MetricRow } from "@/components/ds/metric-cell";
import { MoneyValue } from "@/components/ds/money-value";
import { PageHeader } from "@/components/ds/page-header";
import { Withheld } from "@/components/withheld";
import { fill, formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { currentSession, failureMessage, gateAll, gateMessage, gateVerdict } from "@/lib/api";
import { readCollections, type Collections } from "@/lib/command-centre-reads";
import { listMembers } from "@/lib/members-reads";
import { exceptions, moneyKind, readPayments, type PaymentsLedger } from "@/lib/payments";
import { isWithheld, withheldRemedy } from "@/lib/people";
import { numerals } from "@/lib/display";
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
  // **The tenant's numerals** -- ADR-0015. Every quantity on this page follows
  // `localization.numerals`; an identifier does not, and neither does money. One read for the
  // whole render: `conventions()` is React's per-request memo and the layout starts it.
  const numbering = await numerals();
  const text = (key: MessageKey) => t(locale, key);
  const query = await searchParams;
  const needsAction = query.filter === "needs_action";

  if (!(await currentSession())) redirect("/login");

  // One round trip rather than several: `/authz/checks` asks the same question about
  // every action at once, with the same scope resolution and the same assurance weighing.
  // The semantics are identical -- it is not a permission list, which would be MOD-014's
  // "a grant is not a session" finding.
  const [mayPayments, mayRevenue, mayPeople, mayNames] = await gateAll([
    "finance.payment.read",
    "finance.revenue.read",
    "people.person.read",
    // For the withheld marker's remedy, not for any read. See `@/lib/mask`.
    "member.identity.read",
  ] as const);
  // **The remedy has to match the cause.** A legal name is MOD-014's `identity` class and
  // `member.identity.read` opens it; that permission is `financial`, so a step-up lifts the
  // mask for a session holding the grant at too low an assurance and does nothing for a role
  // that does not hold it. The row said "step up" to both until now. See `@/lib/mask`.
  const remedy = withheldRemedy(gateVerdict(mayNames));
  const nameWithheld: MessageKey = remedy === "step_up"
    ? "member.withheldIdentity"
    : "member.withheldIdentityNoRemedy";

  if (!mayPayments.allowed) {
    return (
      <Shell locale={locale}>
        <Banner severity="info">
          {text(gateMessage(mayPayments))}
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
      // **The money is the figure, and it is no longer the size of a footnote.** The canvas's
      // header line is "JOD 41,280.00 collected · 1–19 August · all locations · 6 failed,
      // 3 refunded, 2 disputed", and rendering all four clauses at `type.bodySm` made the
      // number a manager opens this page for the same size as the scope beside it. Collected
      // is promoted to a `MetricCell`; the window, the scope and the exceptions stay on the
      // figures line, which is what they are. The last clause is still only the non-zero
      // parts, because a clean period says nothing here.
      metrics={
        <MetricRow label={text("payments.heading")}>
          <MetricCell
            label={text("payments.collected")}
            // **Not a zero and not an em-dash.** The figure needs its own permission, so a
            // session without it is told which fact is missing rather than shown a total
            // that reads as nothing collected.
            {...(collected === null
              ? {
                  freshness: "unavailable" as const,
                  unavailableBecause: text("payments.collectedUnavailable"),
                }
              : {
                  value: (
                    <MoneyValue
                      kind="aggregate"
                      amountMinor={collected.collected_minor}
                      currency={collected.currency}
                    />
                  ),
                })}
          />
        </MetricRow>
      }
      figures={
        <>
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
      <nav className="ds-filter-bar" aria-label={text("payments.views")}>
        <Link
          href="/payments?filter=needs_action"
          {...(needsAction ? { "aria-current": "page" as const } : {})}
         className="ds-filter-chip">
          {fill(locale, "payments.needsAction", { count: ledger.needs_action }, numbering)}
        </Link>
        <Link href="/payments" {...(needsAction ? {} : { "aria-current": "page" as const })} className="ds-filter-chip">
          {text("payments.all")}
        </Link>
      </nav>

      {/* **The drawer is a board of its own, and it had no way in.** ADM-PAY-09 is the
          shift close; this ledger is what was taken, not what is in the till. A link rather
          than a tab, because the two answer different questions and a reader arrives at
          each from a different place in the day. */}
      <p style={{ margin: 0 }}>
        <Link href="/payments/cash">{text("cash.heading")}</Link>
      </p>

      <section className="page-section" aria-labelledby="ledger-heading">
        <h2 id="ledger-heading" className="ds-visually-hidden">{text("payments.title")}</h2>
        {ledger.entries.length === 0 ? (
          <Banner severity="info">
            {text(needsAction ? "payments.nothingNeedsAction" : "payments.empty")}
          </Banner>
        ) : (
          <DataGrid
            caption={text("payments.title")}
            countLabel={null}
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
                    // **The reader holds no people permission, so there is no name to show
                    // and an id fragment is not a substitute.** Eight hex characters tell an
                    // operator nothing they can act on, and the directive bars an identifier
                    // from ordinary product UI. The sentence says which of the three cases
                    // this is, which is what the branch exists for.
                    return <span className="muted">{text("payer.nameNeedsPermission")}</span>;
                  }
                  if (name === undefined) {
                    return <span className="muted">{text("payments.notOnThisPage")}</span>;
                  }
                  return isWithheld(name) ? (
                    <Withheld locale={locale} reason={nameWithheld} />
                  ) : (
                    <Link href={`/people/${entry.payer_person_id}`}>{name}</Link>
                  );
                },
              },
              {
                header: text("payments.method"),
                kind: "text",
                priority: 3,
                // Worded, for the state column's reason: `direct_debit` and `gift_card`
                // are stored values, and the underscore alone says they were never meant for
                // a reader. An unmapped method still shows as data.
                render: (entry) => (methodWord(entry.method) === null
                  ? <span className="data" dir="ltr">{entry.method}</span>
                  : text(methodWord(entry.method) as MessageKey)),
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
                    {/* **The state, worded.** Four kinds of row carry four state
                        vocabularies -- an intent is `requires_authentication`, a dispute is
                        `responded` -- and this rendered all of them raw, which is a stored
                        enumeration where a word belongs. An unmapped value still shows, as
                        data, because each set is a module's and may grow. */}
                    {stateWord(entry.state) === null
                      ? <span className="data" dir="ltr">{entry.state}</span>
                      : text(stateWord(entry.state) as MessageKey)}
                    <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
                      {text(`payments.kind.${entry.kind}` as MessageKey)}
                      {/* **The canvas's "parenthetical original" is not drawn, and the
                          reason is that nothing here can name the payment it points at.**
                          It held eight characters of the original's uuid -- a handle for
                          matching two rows by eye, and an identifier in ordinary product UI
                          either way. A payment has no human-facing number in this build the
                          way an invoice has a document number, so the honest options were a
                          fragment or a gap, and the gap is named in "What this screen cannot
                          do yet" rather than papered over with hex. */}
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
                // **A failed charge has somewhere to go.** ADM-PAY-05 is the workspace for
                // exactly these rows -- it pairs each with the failure that opened it and
                // the membership its invoice cites, and says which want a message and which
                // want a person. The cell said "Retry or ask for a new card" and offered no
                // way to do either, which is the shape an independent tester found on the
                // members list: a marker somebody clicks looking for the remedy.
                render: (entry) =>
                  entry.needs_action && entry.kind !== "payment" ? (
                    entry.kind === "attempt" ? (
                      <Link href="/payments/recovery">
                        {text("payments.next.attempt")}
                      </Link>
                    ) : entry.kind === "dispute" ? (
                      // ADM-PAY-10 is where a chargeback is answered, and the deadline is
                      // the one thing on this ledger that expires.
                      <Link href="/payments/disputes">
                        {text("payments.next.dispute")}
                      </Link>
                    ) : (
                      text(`payments.next.${entry.kind}` as MessageKey)
                    )
                  ) : (
                    <span className="muted">—</span>
                  ),
              },
            ]}
          />
        )}
        <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
          <span className="data">{formatInteger(ledger.count, numbering)}</span>{" "}
          {text("payments.rows")}
          {ledger.truncated ? <> {"· "}{text("payments.truncated")}</> : null}
        </p>
      </section>

      {/* What this screen cannot do, at the foot. Both are the design's own tier 3 and tier
          4 and both are real: a refund needs a typed amount *and* a second person, and
          nothing in this build has a form for either. */}
      <NotYet locale={locale} items={["payments.refundTitle", "payments.exportTitle", "payments.locationTitle"]} />
    </Shell>
  );
}

function Shell({
  locale,
  children,
  figures,
  metrics,
}: {
  locale: Locale;
  children: React.ReactNode;
  figures?: React.ReactNode;
  /**
   * The metric row, immediately under the header. A separate slot rather than the first
   * child, because the three early returns on this page — refused, no session, read failed
   * — have a header and no figure to show, and a row of one `unavailable` cell above a
   * refusal banner would say the same thing twice.
   */
  metrics?: React.ReactNode;
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
      {metrics}
      {children}
    </div>
  );
}

/**
 * A payment row's state and method, worded.
 *
 * **Four kinds of row carry four state vocabularies**, which is why this is a flat map rather
 * than a lookup keyed on the kind: an attempt is one of MOD-017's intent statuses, a dispute
 * one of its dispute statuses, and the two sets do not overlap. A value outside all of them
 * still renders, as data -- each set is the module's and may grow, and hiding a state
 * somebody needs to see is worse than showing an ugly one.
 */
function stateWord(state: string): MessageKey | null {
  return (PAYMENT_STATE as Record<string, MessageKey>)[state] ?? null;
}

function methodWord(method: string): MessageKey | null {
  return (PAYMENT_METHOD as Record<string, MessageKey>)[method] ?? null;
}

const PAYMENT_STATE = {
  pending: "payments.state.pending",
  requires_authentication: "payments.state.requires_authentication",
  succeeded: "payments.state.succeeded",
  failed: "payments.state.failed",
  cancelled: "payments.state.cancelled",
  unknown: "payments.state.unknown",
  received: "payments.state.received",
  open: "payments.state.open",
  responded: "payments.state.responded",
  won: "payments.state.won",
  lost: "payments.state.lost",
  withdrawn: "payments.state.withdrawn",
} as const satisfies Record<string, MessageKey>;

const PAYMENT_METHOD = {
  card: "payments.method.card",
  direct_debit: "payments.method.direct_debit",
  bank_transfer: "payments.method.bank_transfer",
  cash: "payments.method.cash",
  wallet: "payments.method.wallet",
  gift_card: "payments.method.gift_card",
  other: "payments.method.other",
  refund: "payments.method.refund",
  chargeback: "payments.method.chargeback",
} as const satisfies Record<string, MessageKey>;

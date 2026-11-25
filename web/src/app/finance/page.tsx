import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { PageHeader } from "@/components/ds/page-header";
import { DataGrid } from "@/components/ds/data-grid";
import { fill, formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { currentSession, gate, failureMessage, gateMessage } from "@/lib/api";
import {
  balanceVerdict,
  hasPostings,
  listAccounts,
  listPeriods,
  listReconciliationCases,
  listRecognitionDue,
  periodsNeedingAttention,
  readTrialBalance,
  type LedgerAccount,
  type LedgerPeriod,
  type ReconciliationCase,
  type RecognitionDue,
  type TrialBalance,
} from "@/lib/ledger";
import { money } from "@/lib/membership";
import { listLegalEntities, type LegalEntity } from "@/lib/organization";
import { numerals } from "@/lib/display";
import { presentation } from "@/lib/preferences";
import { utcStamp } from "@/lib/time";

/**
 * MOD-018's board: the lock, the balances, and the questions nobody has answered.
 *
 * **The period lock is the thing this page exists for.** A closed period refuses a posting and
 * `closing` admits the close's own entries and no trade at all, so "which months are shut"
 * decides whether a till can take money -- and until the route behind this block existed, the
 * only way to find out was to attempt a posting and read the refusal. An accountant beginning
 * a month-end close is deliberately stopping the product for that entity, and nothing told
 * anybody.
 *
 * **A month with no row has never been opened, which is not the same as being open.** The lock
 * is enforced per period row, so a tenant whose 2026 books are filed has every earlier month
 * with no row at all. The page says that rather than listing twelve months and implying the
 * absent ones are available.
 *
 * **There is no journal on this page and no way to list one.** `finance.ledger.read` returns
 * an invoice's figures and the payer's `person_id` out of `GET /ledger/journals/{id}`, which
 * the module discloses as a lateral read around `finance.invoice.read` -- safe only while
 * journal ids are not enumerable. A board that listed them would close that gap in the wrong
 * direction, so this one shows aggregates and states.
 *
 * **Both the entity and the currency are derived, not asked for.** A trial balance is per
 * legal entity and per currency -- COM-03-R07 numbers an invoice per entity and MOD-018 refuses
 * a cross-currency journal -- so a board that showed one without saying which would be showing
 * a figure that belongs to a question nobody asked. The entity comes from the newest period
 * and the currency from the chart, both of which are this module's own reads, so the page needs
 * no hierarchy permission to name them.
 */
export default async function FinancePage({
  searchParams,
}: {
  searchParams: Promise<{ entity?: string; currency?: string }>;
}) {
  const { locale } = await presentation();
  // **The tenant's numerals** -- ADR-0015. Every quantity on this page follows
  // `localization.numerals`; an identifier does not, and neither does money. One read for the
  // whole render: `conventions()` is React's per-request memo and the layout starts it.
  const numbering = await numerals();
  const text = (key: MessageKey) => t(locale, key);
  const chosen = await searchParams;

  if (!(await currentSession())) redirect("/login");

  const may = await gate("finance.ledger.read");
  if (!may.allowed) {
    return (
      <Shell locale={locale}>
        <Banner severity="info">
          {text(gateMessage(may))}
        </Banner>
      </Shell>
    );
  }

  let accounts: LedgerAccount[];
  let periods: LedgerPeriod[];
  let absenceMeansNeverOpened: boolean;
  let cases: ReconciliationCase[];
  let due: RecognitionDue[];
  try {
    const [chart, lock, reconciliation, recognition] = await Promise.all([
      listAccounts(),
      listPeriods(),
      listReconciliationCases(),
      listRecognitionDue(),
    ]);
    accounts = chart.accounts;
    periods = lock.periods;
    absenceMeansNeverOpened = lock.absence_means_never_opened;
    cases = reconciliation.cases;
    due = recognition.due;
  } catch (error) {
    return (
      <Shell locale={locale}>
        <Banner severity="critical">
          {text(failureMessage(error))}
        </Banner>
      </Shell>
    );
  }

  // Derived, in this order: an explicit link wins, then the newest period's entity, then the
  // first account that names one. A tenant with neither has nothing to show a balance for.
  const entityId =
    chosen.entity ??
    periods[0]?.legal_entity_id ??
    accounts.find((a) => a.legal_entity_id !== null)?.legal_entity_id ??
    null;
  const currency =
    chosen.currency ??
    accounts.find((a) => a.status === "active")?.currency ??
    accounts[0]?.currency ??
    null;

  // **Naming the entity needs a different permission from reading the balance.**
  // `tenancy.organization.read` is MOD-004's and `finance.ledger.read` is MOD-018's, and an
  // accountant may hold the second without the first. So the name is looked up when it can be
  // and the id is shown when it cannot -- the same arrangement the schedule board makes for
  // its site picker. Rendering neither is what the block's own sentence warns against.
  let entities: LegalEntity[] = [];
  const mayName = await gate("tenancy.organization.read");
  if (mayName.allowed) {
    try {
      entities = await listLegalEntities();
    } catch {
      entities = [];
    }
  }

  let balance: TrialBalance | null = null;
  let balanceFailed = false;
  if (entityId !== null && currency !== null) {
    try {
      balance = await readTrialBalance(entityId, currency);
    } catch {
      // A bad entity or currency in a link is not a broken product. The block says it could
      // not read that pair rather than failing the whole page, because the lock above it is
      // the part somebody came here for.
      balanceFailed = true;
    }
  }

  const attention = periodsNeedingAttention(periods);

  return (
    <Shell
      locale={locale}
      figures={
        <>
          {fill(locale, "finance.accountsCounted", { count: accounts.length }, numbering)}
          {" \u00b7 "}
          {fill(locale, "finance.periodsCounted", { count: periods.length }, numbering)}
          {" \u00b7 "}
          {fill(locale, "finance.attentionCounted", { count: attention.length }, numbering)}
        </>
      }
    >
      <section className="page-section">
        <h2 id="lock-heading" style={{ margin: 0 }}>{text("finance.lock")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("finance.lockLead")}
        </p>
        {attention.length > 0 ? (
          <Banner severity="attention">
            {text("finance.lockAttention")}{" "}
            {attention.map((p) => p.period_key).join(", ")}
          </Banner>
        ) : null}
        {periods.length === 0 ? (
          <Banner severity="info">{text("finance.noPeriods")}</Banner>
        ) : (
          <DataGrid
            caption={text("finance.lock")}
            labelledBy="lock-heading"
            rows={periods}
            rowKey={(period) => period.period_id}
            // A period in `closing` is the one that surprises: an accountant beginning the
            // month-end close is deliberately stopping that entity's till, and a reader
            // reasoning from `status` alone gets exactly that case wrong.
            rowSeverity={(period) => (period.admits_trade ? null : "attention")}
            columns={[
              {
                header: text("finance.period"),
                kind: "text",
                priority: 1,
                render: (period) => (
                  <span className="data" dir="ltr">{period.period_key}</span>
                ),
              },
              {
                header: text("finance.admitsTrade"),
                kind: "status",
                priority: 1,
                render: (period) => (
                  <>
                    {period.admits_trade ? text("finance.yes") : text("finance.no")}
                    {period.status === "closing" ? (
                      <div className="muted" style={caption}>
                        {text("finance.closingTakesOnlyTheClose")}
                      </div>
                    ) : null}
                  </>
                ),
              },
              {
                header: text("finance.status"),
                kind: "status",
                priority: 2,
                render: (period) => (
                  <>
                    {period.status}
                    {period.reopen_reason === null ? null : (
                      <div className="muted" style={caption}>
                        {text("finance.reopenedBecause")} {period.reopen_reason}
                      </div>
                    )}
                  </>
                ),
              },
              {
                header: text("finance.span"),
                kind: "date",
                priority: 3,
                render: (period) => (
                  <span className="data" dir="ltr">
                    {period.starts_on} → {period.ends_on}
                  </span>
                ),
              },
            ]}
          />
        )}
        {absenceMeansNeverOpened ? (
          <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
            {text("finance.absenceMeansNeverOpened")}
          </p>
        ) : null}
      </section>

      <section className="page-section">
        <h2 id="trial-balance-heading" style={{ margin: 0 }}>{text("finance.trialBalance")}</h2>
        {balance === null ? (
          <Banner severity="info">
            {balanceFailed ? text("finance.balanceUnreadable") : text("finance.noEntity")}
          </Banner>
        ) : (
          <>
            <p className="muted" style={{ margin: 0 }}>
              {text("finance.perEntityPerCurrency")}{" "}
              <strong>
                {entities.find((e) => e.legal_entity_id === balance.legal_entity_id)
                  ?.registered_name ?? (
                  <span className="data" dir="ltr">{balance.legal_entity_id}</span>
                )}
              </strong>
              {" · "}
              <span className="data" dir="ltr">{balance.currency}</span>
              {" · "}
              <span className="data" dir="ltr">{balance.as_of}</span>
              {mayName.allowed ? null : ` · ${text("finance.entityUnnamed")}`}
            </p>
            {balanceVerdict(balance).kind === "balanced" ? (
              <Banner severity="neutral">{text("finance.balanced")}</Banner>
            ) : (
              <Banner severity="critical">
                {text("finance.lostRows")}{" "}
                <span className="data" dir="ltr">
                  {money(balance.difference_minor, balance.currency)}
                </span>
              </Banner>
            )}
            {!hasPostings(balance) ? (
              <Banner severity="info">{text("finance.nothingPosted")}</Banner>
            ) : (
              <DataGrid
                caption={text("finance.trialBalance")}
                labelledBy="trial-balance-heading"
                rows={balance.lines}
                rowKey={(line) => line.account_id}
                totalLabel={text("finance.total")}
                columns={[
                  {
                    header: text("finance.account"),
                    kind: "text",
                    priority: 1,
                    render: (line) => (
                      <>
                        <span className="data" dir="ltr">{line.account_code}</span>
                        <div className="muted" style={caption}>
                          {line.account_kind}
                          {/* A retired account with a balance is exactly the row somebody
                              needs to notice; unmarked it reads as a live one. */}
                          {line.status === "active" ? "" : ` · ${text("finance.retired")}`}
                        </div>
                      </>
                    ),
                    total: () => text("finance.total"),
                  },
                  {
                    header: text("finance.debit"),
                    kind: "money",
                    priority: 1,
                    render: (line) => (
                      <span className="data" dir="ltr">
                        {money(line.debit_minor, balance.currency)}
                      </span>
                    ),
                    total: () => (
                      <span className="data" dir="ltr">
                        {money(balance.debit_total_minor, balance.currency)}
                      </span>
                    ),
                  },
                  {
                    header: text("finance.credit"),
                    kind: "money",
                    priority: 1,
                    render: (line) => (
                      <span className="data" dir="ltr">
                        {money(line.credit_minor, balance.currency)}
                      </span>
                    ),
                    total: () => (
                      <span className="data" dir="ltr">
                        {money(balance.credit_total_minor, balance.currency)}
                      </span>
                    ),
                  },
                  {
                    header: text("finance.class"),
                    kind: "text",
                    priority: 3,
                    render: (line) => line.account_class,
                  },
                ]}
              />
            )}
            <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
              {text("finance.balancedByConstruction")}
            </p>
          </>
        )}
      </section>

      <section className="page-section">
        <h2 id="cases-heading" style={{ margin: 0 }}>{text("finance.cases")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("finance.casesLead")}
        </p>
        {cases.length === 0 ? (
          <Banner severity="info">{text("finance.noCases")}</Banner>
        ) : (
          <DataGrid
            caption={text("finance.cases")}
            labelledBy="cases-heading"
            rows={cases}
            rowKey={(item) => item.case_id}
            // A reconciliation case is an unanswered question, which is what the board is
            // for -- so every row carries the mark rather than none of them.
            rowSeverity={() => "attention"}
            columns={[
              {
                header: text("finance.caseKind"),
                kind: "text",
                priority: 1,
                render: (item) => item.case_kind,
              },
              {
                header: text("finance.difference"),
                kind: "money",
                priority: 1,
                render: (item) => (
                  <span className="data" dir="ltr">
                    {money(item.difference_minor, item.currency)}
                  </span>
                ),
              },
              {
                header: text("finance.subject"),
                kind: "text",
                priority: 2,
                render: (item) => (
                  <>
                    {item.subject_kind}
                    <div className="muted" style={caption}>
                      <span className="data" dir="ltr">{item.subject_ref}</span>
                    </div>
                  </>
                ),
              },
              {
                header: text("finance.openFor"),
                kind: "text",
                priority: 2,
                render: (item) => (
                  <>
                    <span className="data">{formatInteger(item.age_days, numbering)}</span>{" "}
                    {text("finance.days")}
                  </>
                ),
              },
            ]}
          />
        )}
      </section>

      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("finance.recognition")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("finance.recognitionLead")}
        </p>
        {due.length === 0 ? (
          <Banner severity="info">{text("finance.noRecognition")}</Banner>
        ) : (
          <ul style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
            {due.map((item) => (
              <li key={item.schedule_id}>
                {item.basis}
                {" · "}
                <span className="data" dir="ltr">{item.source_ref}</span>
                {" · "}
                {item.amount_due_minor === null ? (
                  // An `on_delivery` schedule has no figure here, and inventing one would be
                  // reporting a delivery count this module does not own.
                  <span className="muted">{text("finance.dueOnDelivery")}</span>
                ) : (
                  <span className="data" dir="ltr">
                    {money(item.amount_due_minor, item.currency)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
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
  /**
   * The counts under the title.
   *
   * **The design's page header is a title and a line of figures, never a paragraph**, and
   * every drawn canvas does the same: "4,812 active · 312 expired · 68 frozen · all
   * locations". A board whose header carried only its own name made a reader scroll to find
   * out whether anything on it needed them.
   */
  figures?: React.ReactNode;
}) {
  return (
    <div className="stack">
      <PageHeader title={t(locale, "finance.title")} {...(figures ? { figures } : {})} />
      {children}
      {/* **The lead paragraph moved to the foot.** The design's page header is a title and a
          line of figures -- every drawn canvas does the same -- so an explanation of what the
          screen is was pushing the data a manager opens the page for below the fold. What is
          kept is the half that is a product disclosure rather than a description, and it
          answers a question here instead of delaying one. */}
      <p className="ds-screen-note">{t(locale, "finance.lead")}</p>
      <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
        {t(locale, "finance.asOf")}{" "}
        <span className="data" dir="ltr">{utcStamp(new Date().toISOString())}</span>
      </p>
    </div>
  );
}



const caption: React.CSSProperties = { fontSize: "var(--type-caption-size)" };

import { redirect } from "next/navigation";

import { Alert } from "@/components/controls";
import { formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate } from "@/lib/api";
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
  const text = (key: MessageKey) => t(locale, key);
  const chosen = await searchParams;

  if (!(await currentSession())) redirect("/login");

  const may = await gate("finance.ledger.read");
  if (!may.allowed) {
    return (
      <Shell locale={locale}>
        <Alert tone="info">
          {may.reachable ? text("gate.denied") : text("gate.unreachable")}
        </Alert>
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
        <Alert tone="error">
          {error instanceof ApiError && error.reason === "unreachable"
            ? text("error.network")
            : text("error.unexpected")}
        </Alert>
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
    <Shell locale={locale}>
      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("finance.lock")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("finance.lockLead")}
        </p>
        {attention.length > 0 ? (
          <Alert tone="warning">
            {text("finance.lockAttention")}{" "}
            {attention.map((p) => p.period_key).join(", ")}
          </Alert>
        ) : null}
        {periods.length === 0 ? (
          <Alert tone="info">{text("finance.noPeriods")}</Alert>
        ) : (
          <table
            tabIndex={0}
            style={{ width: "100%", borderCollapse: "collapse" }}
            aria-label={text("finance.lock")}
          >
            <thead>
              <tr>
                <th scope="col" style={head}>{text("finance.period")}</th>
                <th scope="col" style={head}>{text("finance.span")}</th>
                <th scope="col" style={head}>{text("finance.status")}</th>
                <th scope="col" style={head}>{text("finance.admitsTrade")}</th>
              </tr>
            </thead>
            <tbody>
              {periods.map((period) => (
                <tr key={period.period_id}>
                  <td style={cell}>
                    <span className="data" dir="ltr">{period.period_key}</span>
                  </td>
                  <td style={cell}>
                    <span className="data" dir="ltr">
                      {period.starts_on} → {period.ends_on}
                    </span>
                  </td>
                  <td style={cell}>
                    {period.status}
                    {period.reopen_reason === null ? null : (
                      <div className="muted" style={caption}>
                        {text("finance.reopenedBecause")} {period.reopen_reason}
                      </div>
                    )}
                  </td>
                  <td style={cell}>
                    {period.admits_trade ? text("finance.yes") : text("finance.no")}
                    {period.status === "closing" ? (
                      <div className="muted" style={caption}>
                        {text("finance.closingTakesOnlyTheClose")}
                      </div>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {absenceMeansNeverOpened ? (
          <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
            {text("finance.absenceMeansNeverOpened")}
          </p>
        ) : null}
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("finance.trialBalance")}</h2>
        {balance === null ? (
          <Alert tone="info">
            {balanceFailed ? text("finance.balanceUnreadable") : text("finance.noEntity")}
          </Alert>
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
              <Alert tone="success">{text("finance.balanced")}</Alert>
            ) : (
              <Alert tone="error">
                {text("finance.lostRows")}{" "}
                <span className="data" dir="ltr">
                  {money(balance.difference_minor, balance.currency)}
                </span>
              </Alert>
            )}
            {!hasPostings(balance) ? (
              <Alert tone="info">{text("finance.nothingPosted")}</Alert>
            ) : (
              <table
                tabIndex={0}
                style={{ width: "100%", borderCollapse: "collapse" }}
                aria-label={text("finance.trialBalance")}
              >
                <thead>
                  <tr>
                    <th scope="col" style={head}>{text("finance.account")}</th>
                    <th scope="col" style={head}>{text("finance.class")}</th>
                    <th scope="col" style={head}>{text("finance.debit")}</th>
                    <th scope="col" style={head}>{text("finance.credit")}</th>
                  </tr>
                </thead>
                <tbody>
                  {balance.lines.map((line) => (
                    <tr key={line.account_id}>
                      <td style={cell}>
                        <span className="data" dir="ltr">{line.account_code}</span>
                        <div className="muted" style={caption}>
                          {line.account_kind}
                          {line.status === "active"
                            ? ""
                            : ` · ${text("finance.retired")}`}
                        </div>
                      </td>
                      <td style={cell}>{line.account_class}</td>
                      <td style={cell}>
                        <span className="data" dir="ltr">
                          {money(line.debit_minor, balance.currency)}
                        </span>
                      </td>
                      <td style={cell}>
                        <span className="data" dir="ltr">
                          {money(line.credit_minor, balance.currency)}
                        </span>
                      </td>
                    </tr>
                  ))}
                  <tr>
                    <th scope="row" style={cell} colSpan={2}>
                      {text("finance.total")}
                    </th>
                    <td style={cell}>
                      <span className="data" dir="ltr">
                        {money(balance.debit_total_minor, balance.currency)}
                      </span>
                    </td>
                    <td style={cell}>
                      <span className="data" dir="ltr">
                        {money(balance.credit_total_minor, balance.currency)}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            )}
            <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
              {text("finance.balancedByConstruction")}
            </p>
          </>
        )}
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("finance.cases")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("finance.casesLead")}
        </p>
        {cases.length === 0 ? (
          <Alert tone="info">{text("finance.noCases")}</Alert>
        ) : (
          <table
            tabIndex={0}
            style={{ width: "100%", borderCollapse: "collapse" }}
            aria-label={text("finance.cases")}
          >
            <thead>
              <tr>
                <th scope="col" style={head}>{text("finance.caseKind")}</th>
                <th scope="col" style={head}>{text("finance.subject")}</th>
                <th scope="col" style={head}>{text("finance.difference")}</th>
                <th scope="col" style={head}>{text("finance.openFor")}</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((item) => (
                <tr key={item.case_id}>
                  <td style={cell}>{item.case_kind}</td>
                  <td style={cell}>
                    {item.subject_kind}
                    <div className="muted" style={caption}>
                      <span className="data" dir="ltr">{item.subject_ref}</span>
                    </div>
                  </td>
                  <td style={cell}>
                    <span className="data" dir="ltr">
                      {money(item.difference_minor, item.currency)}
                    </span>
                  </td>
                  <td style={cell}>
                    <span className="data">
                      {formatInteger(item.age_days, "latn")}
                    </span>{" "}
                    {text("finance.days")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("finance.recognition")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("finance.recognitionLead")}
        </p>
        {due.length === 0 ? (
          <Alert tone="info">{text("finance.noRecognition")}</Alert>
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

function Shell({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  return (
    <div className="stack" style={{ padding: "var(--space-6)", maxWidth: "960px" }}>
      <h1 style={{ margin: 0 }}>{t(locale, "finance.title")}</h1>
      <p className="muted" style={{ margin: 0 }}>
        {t(locale, "finance.lead")}
      </p>
      {children}
      <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
        {t(locale, "finance.asOf")}{" "}
        <span className="data" dir="ltr">{utcStamp(new Date().toISOString())}</span>
      </p>
    </div>
  );
}

const head: React.CSSProperties = {
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

const caption: React.CSSProperties = { fontSize: "var(--type-caption-size)" };

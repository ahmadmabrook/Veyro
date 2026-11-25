import { redirect } from "next/navigation";
import Link from "next/link";
import type { ReactNode } from "react";

import { Banner } from "@/components/ds/banner";
import { DataGrid } from "@/components/ds/data-grid";
import { MoneyValue } from "@/components/ds/money-value";
import { PageHeader } from "@/components/ds/page-header";
import { Prose } from "@/components/prose";
import { RecordHeader } from "@/components/ds/record-header";
import { Timeline, TimelineItem } from "@/components/ds/timeline";
import { fill, formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { currentSession, failureMessage, gateAll, gateMessage } from "@/lib/api";
import {
  band,
  fiscal,
  readInvoice,
  readInvoiceHistory,
  type InvoiceDetail,
  type InvoiceEvent,
  type InvoiceHistory,
} from "@/lib/invoice";
import { isWithheld, readMember360 } from "@/lib/people";
import { numerals } from "@/lib/display";
import { presentation } from "@/lib/preferences";
import { dayLabel, timeOfDay, utcStamp } from "@/lib/time";

/**
 * ADM-PAY-03 · INVOICE DETAIL — "One invoice, and its life".
 *
 * **Both reads existed and nothing rendered either.** `GET /finance/invoices/{id}/history`
 * carries a docstring naming this canvas by id -- "ADM-PAY-03's middle section" -- and was
 * built, tested and never opened. Every invoice on `/payments` and on a member's Billing tab
 * was a row that led nowhere.
 *
 * The canvas:
 *
 * > INV-20418 · UNPAID · 2 DAYS LATE
 * > Ahmad Nabulsi · issued 17 Aug · due 17 Aug · Khalda
 * > DESCRIPTION · QTY · AMOUNT
 * > WHAT HAS HAPPENED TO THIS INVOICE — issued, declined, retried, reminder drafted
 * > JOFOTARA — Not submitted: e-invoices are sent on payment, not issue
 * >
 * > **IMMUTABILITY** — Issued invoices are never edited. Corrections are credit notes with
 * > their own number and a link to the original. There is no edit affordance on this screen
 * > at any permission level — which is a design decision, not a missing feature, and the
 * > reason the timeline can be trusted as an audit trail.
 *
 * Four things the build decides rather than copies:
 *
 * - **There is no edit and no "Take payment".** The canvas's own immutability note is why
 *   there is no edit at any permission level, and it is a property of the schema here rather
 *   than a convention: the five ledger tables are insert-only for both runtime roles. Taking
 *   a payment is `finance.payment.take`, a stepped-up financial permission with no form in
 *   this build, so the page says what is owed and not what it cannot do.
 * - **"Not submitted" is correct, not a failure.** Jordan requires the settled transaction,
 *   so an unpaid invoice has nothing to report. A page that coloured every unfiled document
 *   would teach an operator to ignore the one that was genuinely rejected.
 * - **The timeline is composed from the insert-only tables, not from the status.** That is
 *   the server's decision and the reason the screen is worth having: a timeline built from
 *   the cached status says what is true now and nothing about how it got there.
 * - **The member's name is composed through MOD-014's gate.** MOD-017's reads carry no name
 *   by design, so a reader without `people.person.read` gets the invoice with an id -- not a
 *   refusal, because the invoice is not theirs to be refused.
 */
export default async function InvoicePage({
  params,
}: {
  params: Promise<{ invoiceId: string }>;
}) {
  const { invoiceId } = await params;
  const { locale } = await presentation();
  // **The tenant's numerals** -- ADR-0015. Every quantity on this page follows
  // `localization.numerals`; an identifier does not, and neither does money. One read for the
  // whole render: `conventions()` is React's per-request memo and the layout starts it.
  const numbering = await numerals();
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  const [mayInvoice, mayPeople] = await gateAll([
    "finance.account.read",
    "people.person.read",
  ] as const);

  if (!mayInvoice.allowed) {
    return (
      <Shell locale={locale}>
        <Banner severity="info">
          {text(gateMessage(mayInvoice))}
        </Banner>
      </Shell>
    );
  }

  let invoice: InvoiceDetail;
  let history: InvoiceHistory | null = null;
  try {
    invoice = await readInvoice(invoiceId);
  } catch (error) {
    return (
      <Shell locale={locale}>
        <Banner severity="critical">{text(failureMessage(error))}</Banner>
      </Shell>
    );
  }
  // **The timeline is its own read and its own failure.** An invoice whose history cannot be
  // fetched is still an invoice worth showing: losing the whole page would hide the figures
  // somebody came for over a section that explains them.
  history = await readInvoiceHistory(invoiceId).catch(() => null);
  // **The payer's name, composed through MOD-014's own gate.** MOD-017's reads carry no
  // name by design -- `finance.account.read` is held by a front desk and a turnstile, and a
  // money read returning names would be a lateral path around `people.person.read`. So the
  // page asks the module that owns it, and a reader without that permission sees the id
  // rather than a refusal: the invoice is not theirs to be refused.
  const payer = mayPeople.allowed
    ? await readMember360(invoice.payer_person_id)
      .then((record) => record.person.legal_name)
      .catch(() => null)
    : null;

  const status = band(invoice);
  const filing = fiscal(invoice);
  const outstanding = Math.max(
    0, invoice.gross_minor - invoice.paid_minor - invoice.credited_minor);

  return (
    <div className="ds-inspector-pane">
      <RecordHeader
        name={invoice.document_number}
        band={{ text: text(status.key), tone: status.tone }}
        subline={
          <>
            {payer === null ? (
              <span className="data" dir="ltr">
                {invoice.payer_person_id.slice(0, 8)}
              </span>
            ) : (
              <Link href={`/people/${invoice.payer_person_id}`}>
                {/* Masked on a level-1 session, which is a fact about this reader rather
                    than about the invoice -- and "Name withheld" beside an invoice number
                    is the honest version of a blank. */}
                {isWithheld(payer) ? text("member.nameWithheld") : payer}
              </Link>
            )}
            {" · "}
            {text("invoice.issued")}{" "}
            <span className="data" dir="ltr">{invoice.issued_on}</span>
            {" · "}
            {text("invoice.due")}{" "}
            <span className="data" dir="ltr">{invoice.due_on}</span>
            {invoice.days_late > 0 ? (
              <> {"· "}{fill(locale, "invoice.daysLate", { count: invoice.days_late }, numbering)}</>
            ) : null}
            {" · "}
            {invoice.document_kind}
          </>
        }
      />
      <div className="ds-record-body">
        {/* The scheme's deadline, which is the one date in this module that is somebody
            else's and cannot be extended. The server lifts it out of the events because a
            banner is about one deadline. */}
        {history?.evidence_due_on ? (
          <Banner severity="critical">
            {fill(locale, "invoice.evidenceDue", { date: history.evidence_due_on })}
          </Banner>
        ) : null}

        <section className="ds-panel" aria-labelledby="lines-heading">
          <div className="ds-panel-head">
            <h2 id="lines-heading" className="ds-panel-title">{text("invoice.lines")}</h2>
          </div>
          <DataGrid
            caption={text("invoice.lines")}
            labelledBy="lines-heading"
            rows={invoice.lines}
            rowKey={(line) => String(line.line_number)}
            columns={[
              {
                header: text("invoice.description"),
                kind: "text",
                priority: 1,
                render: (line) => (
                  <>
                    {line.description}
                    <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
                      {/* **The rate, not a word.** A line is either taxed at a rate the
                          invoice recorded or it is not, and "tax exempt" is what a zero
                          rate means -- MOD-017 records whatever rate was applied, because
                          there is no tax engine to ask. */}
                      {line.tax_rate_bp === 0
                        ? text("invoice.taxExempt")
                        : fill(locale, "invoice.taxedAt",
                          { rate: (line.tax_rate_bp / 100).toFixed(2) })}
                    </div>
                  </>
                ),
              },
              {
                header: text("invoice.quantity"),
                kind: "text",
                priority: 2,
                render: (line) => (
                  <span className="data" dir="ltr">
                    {formatInteger(line.quantity, numbering)}
                  </span>
                ),
              },
              {
                header: text("invoice.amount"),
                kind: "money",
                priority: 1,
                render: (line) => (
                  <MoneyValue
                    kind="neutral"
                    amountMinor={line.gross_minor}
                    currency={invoice.currency}
                  />
                ),
              },
            ]}
          />
          <div className="ds-panel-body">
            <dl className="facts">
              <Fact label={text("invoice.net")}>
                <MoneyValue
                  kind="neutral" amountMinor={invoice.net_minor} currency={invoice.currency}
                />
              </Fact>
              <Fact label={text("invoice.tax")}>
                <MoneyValue
                  kind="neutral" amountMinor={invoice.tax_minor} currency={invoice.currency}
                />
              </Fact>
              {/* `neutral`, not `aggregate`: the split-decimal treatment is for a metric
                  cell's display figure, and beside `JOD 45.00` and `JOD 7.20` in the same
                  list it reads as a different kind of number rather than their sum. */}
              <Fact label={text("invoice.total")}>
                <MoneyValue
                  kind="neutral"
                  amountMinor={invoice.gross_minor}
                  currency={invoice.currency}
                />
              </Fact>
              <Fact label={text("invoice.paid")}>
                <MoneyValue
                  kind="neutral" amountMinor={invoice.paid_minor} currency={invoice.currency}
                />
              </Fact>
              {invoice.refunded_minor === 0 ? null : (
                <Fact label={text("invoice.refunded")}>
                  <MoneyValue
                    kind="refunded"
                    amountMinor={invoice.refunded_minor}
                    currency={invoice.currency}
                  />
                </Fact>
              )}
              <Fact label={text("invoice.outstanding")}>
                <MoneyValue
                  kind={outstanding > 0 ? "owed" : "neutral"}
                  amountMinor={outstanding}
                  currency={invoice.currency}
                />
              </Fact>
            </dl>
          </div>
        </section>

        {history === null ? (
          <section className="ds-panel">
            <div className="ds-panel-head">
              <h2 className="ds-panel-title">{text("invoice.history")}</h2>
            </div>
            <div className="ds-panel-body">
              <Banner severity="attention">{text("invoice.noHistory")}</Banner>
            </div>
          </section>
        ) : (
          // `Timeline` carries its own heading, so wrapping it in a panel with the same
          // one printed it twice.
          <Timeline label={text("invoice.history")} footer={history.immutable_because}>
            {history.events.map((event, index) => (
              <Event
                key={`${event.kind}-${event.at}-${index}`}
                event={event}
                locale={locale}
              />
            ))}
          </Timeline>
        )}

        <section className="ds-panel">
          <div className="ds-panel-head">
            <h2 className="ds-panel-title">{text("invoice.fiscal")}</h2>
          </div>
          <div className="ds-panel-body">
            <Banner severity={filing.needsSomebody ? "critical" : "info"}>
              {text(filing.key)}
            </Banner>
            <dl className="facts">
              <Fact label={text("invoice.fiscalState")}>
                <span className="data" dir="ltr">{invoice.fiscal_status}</span>
              </Fact>
              {invoice.fiscal_ack_ref === null ? null : (
                <Fact label={text("invoice.fiscalRef")}>
                  <span className="data" dir="ltr">{invoice.fiscal_ack_ref}</span>
                </Fact>
              )}
              {invoice.fiscal_acked_at === null ? null : (
                <Fact label={text("invoice.fiscalWhen")}>
                  <span className="data" dir="ltr">{utcStamp(invoice.fiscal_acked_at)}</span>
                </Fact>
              )}
              {invoice.fiscal_exemption_reason === null ? null : (
                // **The one fiscal state whose whole meaning is its reason.** A constraint
                // makes the reason and the state the same fact, so a state shown without it
                // is a claim with no basis.
                <Fact label={text("invoice.fiscalExempt")}>
                  {invoice.fiscal_exemption_reason}
                </Fact>
              )}
            </dl>
          </div>
        </section>

        {invoice.credit_notes.length === 0 && invoice.credits_invoice_id === null ? null : (
          <section className="ds-panel">
            <div className="ds-panel-head">
              <h2 className="ds-panel-title">{text("invoice.corrections")}</h2>
            </div>
            <div className="ds-panel-body">
              {invoice.credits_invoice_id === null ? null : (
                <p style={{ margin: 0 }}>
                  {text("invoice.creditsThis")}{" "}
                  <Link href={`/finance/invoices/${invoice.credits_invoice_id}`}>
                    {text("invoice.openOriginal")}
                  </Link>
                </p>
              )}
              {invoice.credit_notes.map((note) => (
                <p key={note.invoice_id} style={{ margin: 0 }}>
                  <Link href={`/finance/invoices/${note.invoice_id}`}>
                    <span className="data" dir="ltr">{note.document_number}</span>
                  </Link>
                  {" · "}
                  <MoneyValue
                    kind="refunded"
                    amountMinor={note.gross_minor}
                    currency={note.currency}
                  />
                  {" · "}
                  <span className="data" dir="ltr">{note.issued_on}</span>
                </p>
              ))}
            </div>
            <p className="ds-panel-note">{text("invoice.correctionNote")}</p>
          </section>
        )}

        {/* The canvas's own immutability note, as a product fact rather than a caption --
            and the two actions it draws that this build does not have. */}
        <section className="page-section">
          <h2 style={{ margin: 0 }}>{text("invoice.notYet")}</h2>
          <dl className="facts">
            <Fact label={text("invoice.noTakePaymentTitle")}>
              <Prose>{text("invoice.noTakePaymentWhy")}</Prose>
            </Fact>
            <Fact label={text("invoice.noEditTitle")}>{text("invoice.noEditWhy")}</Fact>
          </dl>
        </section>
      </div>
    </div>
  );
}

function Event({ event, locale }: { event: InvoiceEvent; locale: Locale }) {
  const text = (key: MessageKey) => t(locale, key);
  // The spine's tone, by what the row is. A declined attempt and a dunning step are the two
  // that mean somebody has to do something; a payment is the ordinary good case.
  const tone = event.kind === "refund" || event.kind === "dispute"
    ? "money" as const
    : event.kind === "payment"
      ? "visit" as const
      : event.kind === "payment_intent" && event.status !== "succeeded"
        ? "money" as const
        : "system" as const;
  return (
    <TimelineItem
      time={timeOfDay(event.at)}
      day={dayLabel(event.at)}
      tone={tone}
      title={text(`invoice.event.${event.kind}` as MessageKey)}
      {...(event.amount_minor !== undefined && event.currency !== undefined
        ? {
          money: (
            <MoneyValue
              kind={event.kind === "refund" ? "refunded" : "neutral"}
              amountMinor={event.amount_minor}
              currency={event.currency}
            />
          ),
        }
        : {})}
      meta={
        <>
          {[event.status, event.method, event.dispute_kind, event.reason_code,
            event.detail].filter(Boolean).join(" · ")}
          {event.stage === undefined ? null : (
            <> {"· "}{fill(locale, "invoice.dunningStage", {
              stage: String(event.stage), attempts: String(event.attempts ?? 0),
            })}</>
          )}
        </>
      }
    />
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="muted">{label}</dt>
      <dd style={{ margin: 0 }}>{children}</dd>
    </>
  );
}

/** The shell for a page with no invoice to name. */
function Shell({ locale, children }: { locale: Locale; children: ReactNode }) {
  return (
    <div className="ds-inspector-pane">
      <PageHeader title={t(locale, "invoice.title")} />
      <div className="ds-record-body">{children}</div>
    </div>
  );
}

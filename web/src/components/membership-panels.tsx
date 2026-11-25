import Link from "next/link";

import { Banner } from "@/components/ds/banner";
import { MoneyValue } from "@/components/ds/money-value";
import {
  fill, formatInteger, formatMoney, t, type Locale, type MessageKey,
} from "@/i18n/locale";
import { gate, gateAll, gateMessage, gateVerdict, failureMessage, type GateAnswer }
  from "@/lib/api";
import { readCancellationPreview, readFreezeAllowance } from "@/lib/membership";
import { affordanceFor, type FreezeAllowance } from "@/lib/freeze";
import {
  affordanceFor as cancelAffordanceFor,
  commitmentLine,
  feeLines,
  freezeOffer,
  type CancellationQuote,
} from "@/lib/cancellation";
import { readAttendance } from "@/lib/member-record";
import { CancelForm } from "@/app/people/[personId]/cancel-form";
import { PlanMoveForm } from "@/app/people/[personId]/plan-form";
import {
  expiring,
  lossState,
  offerable,
  planLabel,
  refusalMessage,
  stillBooked,
  timingMessage,
  type ChangeQuote,
  type PlanOption,
} from "@/lib/downgrade";
import { readPlanChangeQuote, readPlans } from "@/lib/downgrade-reads";
import { utcDate } from "@/lib/time";
import { FreezeForm } from "@/app/people/[personId]/freeze-form";
import {
  kindName,
  kindWord,
  nextExpiry,
  readWallets,
  type WalletStatement,
} from "@/lib/wallet";
import {
  listAccounts,
  listGrants,
  listInvoices,
  listMemberships,
  money,
  outstandingMinor,
  remaining,
  type BillingAccount,
  type EntitlementGrant,
  type InvoiceRow,
  type MembershipRow,
} from "@/lib/membership";

/**
 * MOD-017 on a member's page: what they agreed to, what it entitles them to, what they owe.
 *
 * **This is a composition, not a join.** Paragraph 1300 bars cross-domain write-table access,
 * so MOD-014's Member 360 cannot read MOD-017's tables and says so in its own `sections`
 * block. A *surface* has no such restriction and every reason to compose: it calls each
 * module's own routes, through each module's own gate, and renders the result beside the
 * person MOD-014 answered for. That is where the two belong together.
 *
 * **Every figure here is a `MoneyValue`**, which it was not: this block formatted each
 * amount into a plain string and put it in a `.data` span. §39 is explicit -- "never a bare
 * number in a money column" -- and the kind is what carries the meaning: `owed` sets the
 * outstanding figure in the critical ink, `aggregate` de-emphasises the minor units so a
 * column of amounts aligns on the major, and `notApplicable` renders the em-dash for a
 * member with no billing account rather than a zero that reads as "nothing owed". Found by
 * a test looking for `.ds-money` on this tab and finding none.
 *
 * **Three gates, asked separately.** `membership.record.read`, `membership.entitlement.read`
 * and `finance.account.read` are three permissions and a reader may hold any subset -- a coach
 * sees the membership and not the money. A refused block says it was refused; it does not
 * render empty, because "this member has no invoices" and "you may not see them" are different
 * facts and only the first is about the member. MOD-019's roster block makes the same
 * distinction for the same reason.
 *
 * **No name, no address, no birth date passes through here.** MOD-017's reads carry none --
 * deliberately, so that `membership.record.read`, which a front desk and a turnstile hold,
 * cannot become a lateral read path around `people.person.read`. The person's identity on this
 * page comes from MOD-014 above, masked by class and by assurance.
 */
export async function MembershipPanels({
  personId,
  locale,
  only,
  cancelling = false,
  movingPlan = false,
  toVariantId = "",
}: {
  personId: string;
  locale: Locale;
  /**
   * Which of the three blocks to render.
   *
   * ADM-MEM-01 puts membership and billing on **separate tabs**, so a page asking for the
   * Billing tab must not also render the agreement above it -- that is the single-page stack
   * this screen was rebuilt out of. Omitted renders all three, which is what any other
   * surface composing a member wants.
   */
  only?: "membership" | "billing";
  /**
   * Whether ADM-MSH-07's sheet is open.
   *
   * **The canvas draws these as side sheets over Member 360 and this app has none**, so the
   * sheet is a query parameter on the tab: `?tab=membership&cancel=1`. That keeps the
   * canvas's own structure -- "the member's context stays visible while you change their
   * agreement" -- and gives "Keep it" something to do, which a permanently-open destructive
   * form cannot. It also means the form is opened deliberately rather than sitting under the
   * membership it would end.
   */
  cancelling?: boolean;
  /**
   * Whether ADM-MSH-06's sheet is open, and which plan it is quoting.
   *
   * `?tab=membership&plan=1` opens the picker and `&to=<variant>` quotes one, which is the
   * same query-parameter shape the cancellation uses and for the same reason. The two-step
   * is the canvas's own: the loss is stated before the saving, so a plan is chosen, the
   * consequence is read, and only then is anything written.
   */
  movingPlan?: boolean;
  toVariantId?: string;
}) {
  const text = (key: MessageKey) => t(locale, key);
  // One round trip rather than three; see `member-metrics.tsx` for why that matters.
  const [records, entitlements, finance, wallet] = await gateAll([
    "membership.record.read",
    "membership.entitlement.read",
    "finance.account.read",
    "finance.wallet.read",
  ] as const);

  const show = (block: "membership" | "billing") => only === undefined || only === block;

  return (
    <>
      {show("membership") ? (
      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("membership.title")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("membership.lead")}
        </p>
        <Block answer={records} locale={locale}>
          <Memberships personId={personId} locale={locale} />
        </Block>
      </section>
      ) : null}

      {/* **ADM-MSH-03, and the first stepped-up form in this app.** Every other absent form
          here is a financial-class write and the inventory said so -- "a button that
          answered 403 is worse than its absence". What makes this one buildable is not a
          change to the permission but the step-up this app already has: the block offers it
          with `next` back to this member, the way the member record already offers one for a
          masked field. A step-up opens a twelve-hour window, so it is one recovery code a
          shift rather than one an act, and the allowance panel reads without one. */}
      {show("membership") ? (
        <Freezing personId={personId} locale={locale} />
      ) : null}

      {/* **ADM-MSH-07, and the third of the canvas's "three consequence-heavy actions".**
          The other two are a sale and an upgrade, and both end in taking a payment this
          build has no provider for; a cancellation ends in a disclosure and a recorded
          decision, which is why this one is buildable and they are not. */}
      {show("membership") ? (
        <Cancelling personId={personId} locale={locale} open={cancelling} />
      ) : null}

      {/* **ADM-MSH-06, and the read that let it be built.** `plan-change-preview` takes a
          successor agreement and drawing one up is a financial write, so a tier-3 screen had
          to commit in order to disclose. `plan-change-quote` is keyed on the plan instead,
          which is what makes the canvas's own order possible: "the loss is stated before the
          saving". ADM-MSH-05's upgrade is the same sheet read the other way -- the kind is
          derived from the two prices, never declared. */}
      {show("membership") ? (
        <MovingPlan
          personId={personId} locale={locale} open={movingPlan}
          toVariantId={toVariantId}
        />
      ) : null}

      {show("membership") ? (
      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("membership.entitlements")}</h2>
        <Block answer={entitlements} locale={locale}>
          <Grants personId={personId} locale={locale} />
        </Block>
      </section>
      ) : null}

      {show("billing") ? (
      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("wallet.title")}</h2>
        <Block answer={wallet} locale={locale}>
          <Wallet personId={personId} locale={locale} />
        </Block>
      </section>
      ) : null}

      {show("billing") ? (
      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("membership.finance")}</h2>
        <Block answer={finance} locale={locale}>
          <Finance personId={personId} locale={locale} />
        </Block>
      </section>
      ) : null}
    </>
  );
}

/**
 * A gated block: refused, unreachable, or the thing itself.
 *
 * The refusal is rendered as information rather than as an error, because being refused a
 * block you do not hold the permission for is the system working. `reachable` is false when
 * the identity cannot hold the permission at any assurance, which is a different sentence
 * from "sign in more strongly".
 */
function Block({
  answer,
  locale,
  children,
}: {
  // **The whole answer, not two booleans of it.** A refusal has four meanings -- the gate
  // said no, the level is unreachable in this build, a step-up would open it, or the request
  // never got an answer -- and a narrowed shape here reported the last as the first.
  answer: GateAnswer;
  locale: Locale;
  children: React.ReactNode;
}) {
  if (answer.allowed) return <>{children}</>;
  return <Banner severity="info">{t(locale, gateMessage(answer))}</Banner>;
}

async function Memberships({ personId, locale }: { personId: string; locale: Locale }) {
  const text = (key: MessageKey) => t(locale, key);
  let rows: MembershipRow[];
  try {
    rows = (await listMemberships(personId)).memberships;
  } catch (error) {
    return <Failed error={error} locale={locale} />;
  }
  if (rows.length === 0) return <Banner severity="info">{text("membership.none")}</Banner>;
  return (
    <>
      <table
        tabIndex={0}
        style={{ width: "100%", borderCollapse: "collapse" }}
        aria-label={text("membership.title")}
      >
        <thead>
          <tr>
            <th scope="col" style={head}>{text("membership.number")}</th>
            <th scope="col" style={head}>{text("membership.kind")}</th>
            <th scope="col" style={head}>{text("membership.status")}</th>
            <th scope="col" style={head}>{text("membership.period")}</th>
            <th scope="col" style={head}>{text("membership.price")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.membership_id}>
              <td style={cell}>
                <span className="data" dir="ltr">{row.membership_number}</span>
              </td>
              <td style={cell}>
                {row.membership_kind}
                <div className="muted" style={caption}>
                  {row.billing_period}
                  {row.is_off_peak ? ` · ${text("membership.offPeak")}` : ""}
                </div>
              </td>
              <td style={cell}>
                {row.status}
                <div className="muted" style={caption}>
                  {text("membership.since")}{" "}
                  <span className="data" dir="ltr">{row.status_effective_on}</span>
                </div>
              </td>
              <td style={cell}>
                {row.current_period_start === null ? (
                  <span className="muted">{text("membership.noPeriod")}</span>
                ) : (
                  <span className="data" dir="ltr">
                    {row.current_period_start} → {row.current_period_end}
                  </span>
                )}
              </td>
              <td style={cell}>
                <MoneyValue kind="aggregate" amountMinor={row.amount_minor}
                  currency={row.currency} />
                {row.minimum_term_ends_on === null ? null : (
                  <div className="muted" style={caption}>
                    {text("membership.minimumTerm")}{" "}
                    <span className="data" dir="ltr">{row.minimum_term_ends_on}</span>
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
        {text("membership.statusIsNow")}
      </p>
      <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
        {text("membership.twoNumbers")}
      </p>
    </>
  );
}

async function Grants({ personId, locale }: { personId: string; locale: Locale }) {
  const text = (key: MessageKey) => t(locale, key);
  let page: { grants: EntitlementGrant[]; balance_is_unswept: boolean };
  try {
    page = await listGrants(personId);
  } catch (error) {
    return <Failed error={error} locale={locale} />;
  }
  if (page.grants.length === 0) {
    return <Banner severity="info">{text("membership.noGrants")}</Banner>;
  }
  return (
    <>
      <table
        tabIndex={0}
        style={{ width: "100%", borderCollapse: "collapse" }}
        aria-label={text("membership.entitlements")}
      >
        <thead>
          <tr>
            <th scope="col" style={head}>{text("membership.entitlement")}</th>
            <th scope="col" style={head}>{text("membership.left")}</th>
            <th scope="col" style={head}>{text("membership.held")}</th>
            <th scope="col" style={head}>{text("membership.status")}</th>
            <th scope="col" style={head}>{text("membership.valid")}</th>
          </tr>
        </thead>
        <tbody>
          {page.grants.map((grant) => {
            const left = remaining(grant);
            return (
              <tr key={grant.grant_id}>
                <td style={cell}>
                  {grant.display_name}
                  <div className="muted" style={caption}>
                    <span className="data" dir="ltr">{grant.policy_key}</span>
                  </div>
                </td>
                <td style={cell}>
                  {left.kind === "unlimited" ? (
                    // Not "∞" and not a number: an uncounted grant has no balance, and a
                    // figure here would be a quantity the module does not keep.
                    <span className="muted">{text("membership.unlimited")}</span>
                  ) : (
                    <span className="data">
                      {formatInteger(left.balance ?? 0, "latn")}
                      {grant.granted_quantity === null
                        ? ""
                        : ` / ${formatInteger(grant.granted_quantity, "latn")}`}
                    </span>
                  )}
                </td>
                <td style={cell}>
                  {left.kind === "unlimited" ? (
                    <span className="muted">—</span>
                  ) : (
                    <span className="data">{formatInteger(left.held ?? 0, "latn")}</span>
                  )}
                </td>
                <td style={cell}>{grant.status}</td>
                <td style={cell}>
                  <span className="data" dir="ltr">
                    {grant.valid_from.slice(0, 10)}
                    {grant.valid_to === null ? "" : ` → ${grant.valid_to.slice(0, 10)}`}
                  </span>
                  {grant.usable_from_minute === null ? null : (
                    <div className="muted" style={caption}>
                      {text("membership.offPeakWindow")}
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {page.balance_is_unswept ? (
        <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
          {text("membership.unswept")}
        </p>
      ) : null}
    </>
  );
}

/**
 * ADM-PAY-07 · WALLET & CREDITS, on the member whose wallet it is.
 *
 * **Four balances, not one**, which is paragraph 1686 and MOD-018 calls it a Critical
 * Control: a member holding 50.00 they paid in and 10.00 the tenant gave away holds two
 * different things, and only the first is money the tenant owes. The canvas draws a single
 * balance; summing them here would erase the distinction that decides whether a refund is
 * even possible, so the total leads and the kinds sit under it.
 *
 * **Each entry names its origin**, which is the canvas's own rule: *"Always labelled credit,
 * never a negative balance. Each entry names its origin — a cancelled class, an
 * overpayment, a goodwill gesture — because unexplained credit is indistinguishable from an
 * error."* The origin is the tenant's own prose on the entry, and a routine tenant-wide
 * reader sees it -- the disclosure MOD-018 records for this read, and the place
 * `Decision.mask` would apply if this path asked the gate for one.
 *
 * **A lapsed entry is shown, marked.** `wallet_statement` returns it rather than dropping
 * it because "where did my 10.00 go" is the question a member actually asks, and a
 * statement that silently omitted the expiry cannot answer it.
 *
 * **There is no Top up and no Add credit.** The canvas draws both; both are writes, and
 * `finance.wallet.credit` is a stepped-up financial permission with no form in this build.
 * A button that answered 403 is worse than the gap -- ADM-MEM-05's rule.
 */
async function Wallet({ personId, locale }: { personId: string; locale: Locale }) {
  const text = (key: MessageKey) => t(locale, key);
  let wallets: WalletStatement[];
  try {
    wallets = (await readWallets(personId)).wallets;
  } catch (error) {
    return <Failed error={error} locale={locale} />;
  }

  // **A member with no wallet is not a failure and not an empty table.** Most members never
  // hold credit, and "this member holds none" is a fact somebody can act on; a blank panel
  // reads as a figure that failed to load.
  if (wallets.length === 0) {
    return <Banner severity="info">{text("wallet.none")}</Banner>;
  }
  return (
    <>
      {wallets.map((statement) => (
        <WalletCurrency key={statement.currency} statement={statement} locale={locale} />
      ))}
      <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
        {text("wallet.originWhy")}
      </p>
      <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
        {text("wallet.noWrites")}
      </p>
    </>
  );
}

/** One wallet: a balance, what expires, and every movement that made it. */
function WalletCurrency({
  statement,
  locale,
}: {
  statement: WalletStatement;
  locale: Locale;
}) {
  const text = (key: MessageKey) => t(locale, key);
  const expiry = nextExpiry(statement);
  const kinds = Object.entries(statement.balances).filter(([, minor]) => minor !== 0);

  return (
    <>
      <dl className="facts">
        <dt className="muted">{text("wallet.balance")}</dt>
        <dd style={{ margin: 0 }}>
          <MoneyValue kind="aggregate" amountMinor={statement.spendable_minor}
            currency={statement.currency} />
        </dd>
        <dt className="muted">{text("wallet.refundable")}</dt>
        <dd style={{ margin: 0 }}>
          <MoneyValue kind="aggregate" amountMinor={statement.refundable_minor}
            currency={statement.currency} />
          <div className="muted" style={caption}>{text("wallet.refundableWhy")}</div>
        </dd>
        {expiry === null ? null : (
          <>
            <dt className="muted">{text("wallet.expiring")}</dt>
            <dd style={{ margin: 0 }}>
              <MoneyValue kind="aggregate" amountMinor={expiry.amountMinor}
                currency={statement.currency} />
              {" \u00b7 "}
              {text("wallet.expires")}{" "}
              <span className="data" dir="ltr">{expiry.on}</span>
            </dd>
          </>
        )}
      </dl>

      {kinds.length < 2 ? null : (
        <dl className="facts">
          {kinds.map(([kind, minor]) => {
            const named = kindName(kind);
            return (
              <div key={kind} style={{ display: "contents" }}>
                <dt className="muted">
                  {named ? text(named) : <span className="data" dir="ltr">{kind}</span>}
                </dt>
                <dd style={{ margin: 0 }}>
                  <MoneyValue kind="aggregate" amountMinor={minor}
                    currency={statement.currency} />
                </dd>
              </div>
            );
          })}
        </dl>
      )}

      {statement.lines.length === 0 ? (
        <Banner severity="info">{text("wallet.noMovements")}</Banner>
      ) : (
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <caption className="ds-visually-hidden">{text("wallet.title")}</caption>
          <thead>
            <tr>
              <th style={head}>{text("wallet.date")}</th>
              <th style={head}>{text("wallet.movement")}</th>
              <th style={head}>{text("wallet.amount")}</th>
            </tr>
          </thead>
          <tbody>
            {statement.lines.map((line, index) => (
              <tr key={`${line.at}-${index}`}>
                <td style={cell}>
                  <span className="data" dir="ltr">{line.at.slice(0, 10)}</span>
                </td>
                <td style={cell}>
                  {line.reason}
                  <div className="muted" style={caption}>
                    {/* **A credit's kind is where it came from; a debit's is which pocket it
                        came out of.** The same word cannot do both: "Given away" over a
                        spend reads as though the gym gave away a protein bar. */}
                    {line.amount_minor < 0
                      ? fill(locale, "wallet.spentFrom", {
                          kind: kindWord(line.value_kind) === null
                            ? line.value_kind
                            : text(kindWord(line.value_kind) as MessageKey),
                        })
                      : kindName(line.value_kind) === null
                        ? line.value_kind
                        : text(kindName(line.value_kind) as MessageKey)}
                    {line.expires_on === null ? null : (
                      <>
                        {" \u00b7 "}
                        {line.lapsed ? text("wallet.lapsed") : text("wallet.expires")}{" "}
                        <span className="data" dir="ltr">{line.expires_on}</span>
                      </>
                    )}
                  </div>
                </td>
                <td style={cell}>
                  {/* **Signed on one axis**, which is the payments ledger's rule applied to a
                      wallet: a spend is a different sign, never a credit of a different
                      colour. `MoneyValue` carries the magnitude and the sign leads it, so a
                      column of movements still adds up by eye. */}
                  <span className="data" dir="ltr">
                    {line.amount_minor < 0 ? "\u2212" : "+"}
                  </span>
                  <MoneyValue kind="aggregate" amountMinor={Math.abs(line.amount_minor)}
                    currency={statement.currency} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

async function Finance({ personId, locale }: { personId: string; locale: Locale }) {
  const text = (key: MessageKey) => t(locale, key);
  let accounts: BillingAccount[];
  let invoices: InvoiceRow[];
  try {
    const [a, i] = await Promise.all([listAccounts(personId), listInvoices(personId)]);
    accounts = a.accounts;
    invoices = i.invoices;
  } catch (error) {
    return <Failed error={error} locale={locale} />;
  }
  if (accounts.length === 0 && invoices.length === 0) {
    return <Banner severity="info">{text("membership.noFinance")}</Banner>;
  }
  const owed = outstandingMinor(invoices);
  const currency = invoices[0]?.currency ?? accounts[0]?.currency ?? "";
  return (
    <>
      {/* **No wrapper around each pair.** `.facts` is a two-column grid whose items are the
          `dt` and `dd` themselves; a `<div>` around each pair is valid HTML and makes the div
          the grid item, so the two labels sat side by side with their values beneath instead
          of as label/value rows. Found by looking at the page -- every assertion about the
          text passed either way. */}
      <dl className="facts">
        <dt className="muted">{text("membership.accounts")}</dt>
        <dd style={{ margin: 0 }}>
          {accounts.length === 0 ? (
            <span className="muted">{text("membership.noAccount")}</span>
          ) : (
            accounts.map((account) => (
              <div key={account.billing_account_id}>
                <span className="data" dir="ltr">{account.account_number}</span>
                {" · "}
                {account.account_kind}
                {" · "}
                {account.status}
              </div>
            ))
          )}
        </dd>
        <dt className="muted">{text("membership.outstanding")}</dt>
        <dd style={{ margin: 0 }}>
          {currency === "" ? (
            // No account, so no currency: `notApplicable` is the kind for a figure that
            // does not exist, and it renders the em-dash rather than a zero.
            <MoneyValue kind="notApplicable" />
          ) : (
            <MoneyValue kind="owed" amountMinor={owed} currency={currency} />
          )}
        </dd>
      </dl>
      {invoices.length === 0 ? (
        <Banner severity="info">{text("membership.noInvoices")}</Banner>
      ) : (
        <table
          tabIndex={0}
          style={{ width: "100%", borderCollapse: "collapse" }}
          aria-label={text("membership.finance")}
        >
          <thead>
            <tr>
              <th scope="col" style={head}>{text("membership.document")}</th>
              <th scope="col" style={head}>{text("membership.issued")}</th>
              <th scope="col" style={head}>{text("membership.gross")}</th>
              <th scope="col" style={head}>{text("membership.paid")}</th>
              <th scope="col" style={head}>{text("membership.payment")}</th>
              <th scope="col" style={head}>{text("membership.fiscal")}</th>
            </tr>
          </thead>
          <tbody>
            {invoices.map((invoice) => (
              <tr key={invoice.invoice_id}>
                <td style={cell}>
                  {/* **A row that leads somewhere.** ADM-PAY-03 is the invoice's own
                      screen and both its reads were built long before anything rendered
                      them, so every invoice in this app was a figure with no way in. */}
                  <Link href={`/finance/invoices/${invoice.invoice_id}`}>
                    <span className="data" dir="ltr">{invoice.document_number}</span>
                  </Link>
                  {invoice.document_kind === "invoice" ? null : (
                    <div className="muted" style={caption}>
                      {text("membership.creditNote")}
                    </div>
                  )}
                </td>
                <td style={cell}>
                  <span className="data" dir="ltr">{invoice.issued_on}</span>
                  <div className="muted" style={caption}>
                    {text("membership.due")}{" "}
                    <span className="data" dir="ltr">{invoice.due_on}</span>
                  </div>
                </td>
                <td style={cell}>
                  <MoneyValue kind="aggregate" amountMinor={invoice.gross_minor}
                    currency={invoice.currency} />
                </td>
                <td style={cell}>
                  <MoneyValue kind="aggregate" amountMinor={invoice.paid_minor}
                    currency={invoice.currency} />
                </td>
                <td style={cell}>{invoice.payment_status}</td>
                <td style={cell}>{invoice.fiscal_status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
        {text("membership.twoStatuses")}
      </p>
    </>
  );
}

/** A read that failed. The network case is worth telling apart from everything else. */
function Failed({ error, locale }: { error: unknown; locale: Locale }) {
  return (
    <Banner severity="critical">
      {t(locale, failureMessage(error))}
    </Banner>
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


/**
 * ADM-MSH-03's freeze, with the consequence panel the canvas puts above the button.
 *
 * **Three answers, not two.** The allowance reads on `membership.record.read`, which is
 * routine; the act needs `membership.lifecycle.change`, which is financial. So a reader can
 * be in one of three states and each has a different next step: they may act, they may act
 * after a step-up, or they may not act at all. A page that collapsed the last two would send
 * somebody to find a second factor that changes nothing.
 */
async function Freezing({ personId, locale }: { personId: string; locale: Locale }) {
  const text = (key: MessageKey) => t(locale, key);
  let live: MembershipRow | undefined;
  try {
    live = (await listMemberships(personId)).memberships.find(
      (row) => row.status === "active" || row.status === "frozen");
  } catch {
    // The block above already reported the failure; a second banner for the same request
    // would be the same fact twice.
    return null;
  }
  if (live === undefined) return null;

  let allowance: FreezeAllowance;
  try {
    allowance = await readFreezeAllowance(live.membership_id);
  } catch {
    return null;
  }

  const may = await gate("membership.lifecycle.change");
  const affordance = affordanceFor(allowance, {
    allowed: may.allowed, verdict: gateVerdict(may),
  });

  return (
    <section className="page-section" aria-labelledby={`freeze-${live.membership_id}`}>
      <h2 id={`freeze-${live.membership_id}`} style={{ margin: 0 }}>
        {text("freeze.title")}
      </h2>

      {/* **The allowance, before anything else.** The canvas puts "2 of 3 freeze months used
          this year" in the consequence panel, and this is the figure behind it -- readable
          at last, and from the expression the write itself checks against. */}
      <p style={{ margin: 0 }}>
        {fill(locale, "freeze.used", {
          used: formatInteger(allowance.days_used, "latn"),
          allowed: formatInteger(allowance.allowance_days, "latn"),
        })}
      </p>
      {allowance.counting_an_open_freeze ? (
        <Banner severity="attention">{text("freeze.openNow")}</Banner>
      ) : null}
      <p className="muted" style={{ margin: 0 }}>
        {fill(locale, "freeze.window", {
          from: allowance.may_start_between.from, to: allowance.may_start_between.to,
        })}
        {" · "}
        {text("freeze.windowWhy")}
      </p>

      {/* **Four answers, decided in one place.** `affordanceFor` is a function so that every
          branch of it has a test: the "this contract allows no freezing" path had none,
          because the fixture's contract allows thirty days and the branch never rendered --
          a mutation deleting it passed a green suite, which is the "branch no fixture can
          reach" shape this repository records for four modules. */}
      {affordance === "no_allowance" ? (
        <Banner severity="info">{text("freeze.noAllowance")}</Banner>
      ) : affordance === "form" ? (
        <FreezeForm
          locale={locale}
          numbering="latn"
          personId={personId}
          membershipId={live.membership_id}
          allowance={allowance}
        />
      ) : affordance === "step_up" ? (
        <>
          <Banner severity="info">{text("freeze.stepUpFirst")}</Banner>
          <Link
            href={`/step-up?for=financial&action=membership.lifecycle.change&next=${
              encodeURIComponent(`/people/${personId}?tab=membership`)}`}
          >
            {text("freeze.stepUp")}
          </Link>
        </>
      ) : (
        <Banner severity="info">
          {affordance === "refused" && gateVerdict(may) === "denied"
            ? text("freeze.notPermitted") : text(gateMessage(may))}
        </Banner>
      )}

      <dl className="facts">
        {([
          ["freeze.gapOverrideLabel", "freeze.gapOverride"],
          ["freeze.gapUndoLabel", "freeze.gapUndo"],
        ] as [MessageKey, MessageKey][]).map(([label, why]) => (
          <div key={label} style={{ display: "contents" }}>
            <dt className="muted">{text(label)}</dt>
            <dd style={{ margin: 0 }}>{text(why)}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}


/**
 * ADM-MSH-07's cancellation, with the money consequence before the commit.
 *
 * **The canvas's three facts, and each of them is a different sentence depending on the
 * contract.** "His 12-month commitment runs to March. Cancelling now triggers a two-month
 * fee of JOD 80.00, and his access ends on 7 September after the notice period" is one of
 * four commitment states, and the other three would be false if this rendered that sentence
 * for everybody -- a member on a rolling contract has no commitment, one whose term has run
 * out has one that no longer binds, and one whose contract offers no buy-out cannot leave
 * early at all. `commitmentLine` is where that is decided, so each branch has a test.
 *
 * **The interruption above the button is the canvas's, and its argument is conditional.**
 * "He stopped visiting 12 days ago and has not given a reason. A freeze costs him nothing
 * and keeps the commitment intact" joins two claims that are not always both true, so
 * `freezeOffer` returns which of them holds and the panel says only that much. A page that
 * told a member on a monthly rolling contract that a freeze "keeps the commitment intact"
 * would be describing a benefit that does not exist.
 *
 * **Attendance is composed through its own gate and its absence is not dormancy.** The last
 * visit is MOD-022's and needs `access.zone.read`, which a reader of a membership may not
 * hold; an unknown last visit means the freeze is not offered on dormancy grounds rather
 * than offered on the assumption that nobody has come. MOD-014's rule, in the same
 * direction: absent data is not a fact about somebody.
 */
async function Cancelling(
  { personId, locale, open }: { personId: string; locale: Locale; open: boolean },
) {
  const text = (key: MessageKey) => t(locale, key);
  const back = `/people/${personId}?tab=membership`;

  let live: MembershipRow | undefined;
  try {
    live = (await listMemberships(personId)).memberships.find(
      (row) => row.status === "active" || row.status === "frozen");
  } catch {
    // The membership block above already reported the failure; a second banner for the same
    // request would be the same fact twice.
    return null;
  }
  if (live === undefined) return null;

  let quote: CancellationQuote;
  try {
    quote = await readCancellationPreview(live.membership_id);
  } catch {
    return null;
  }

  // **Closed is one control, because the consequence belongs in the sheet.** Printing the
  // fee under every member's membership would make a figure nobody asked for the most
  // prominent thing on the tab, and the canvas puts it behind the deliberate act of opening
  // the sheet.
  if (!open) {
    return (
      <section className="page-section" aria-labelledby={`cancel-${live.membership_id}`}>
        <h2 id={`cancel-${live.membership_id}`} style={{ margin: 0 }}>
          {text("cancel.title")}
        </h2>
        <p className="muted" style={{ margin: 0 }}>{text("cancel.closedLead")}</p>
        <p style={{ margin: 0 }}>
          <Link href={`${back}&cancel=1`}>{text("cancel.open")}</Link>
        </p>
      </section>
    );
  }

  const may = await gate("membership.lifecycle.change");
  const affordance = cancelAffordanceFor(quote, {
    allowed: may.allowed, verdict: gateVerdict(may),
  });

  let daysSince: number | null = null;
  const maySee = await gate("access.zone.read");
  if (maySee.allowed) {
    try {
      daysSince = (await readAttendance(personId)).days_since;
    } catch {
      daysSince = null;
    }
  }
  const offer = freezeOffer(quote, daysSince);
  const line = commitmentLine(quote);
  const lines = feeLines(quote);
  const feeText = money(quote.disclosed_fee_minor, quote.disclosed_fee_currency);

  return (
    <section className="page-section" aria-labelledby={`cancel-${live.membership_id}`}>
      <h2 id={`cancel-${live.membership_id}`} style={{ margin: 0 }}>
        {text("cancel.title")}
      </h2>

      {/* **The consequence, where the canvas puts it: above everything else.** The
          commitment, then the money, then the date -- in that order, because that is the
          order the canvas states them and the order a member asks about them. */}
      <div className="ds-freeze-consequence">
        {line === "none" ? null : (
          <p style={{ margin: 0 }}>
            {line === "served"
              ? fill(locale, "cancel.termServed", { date: quote.commitment.ends_on ?? "" })
              : line === "held_to_term"
                ? fill(locale, "cancel.termHolds",
                       { date: quote.commitment.ends_on ?? "" })
                : fill(locale, "cancel.termEarly",
                       { months: formatInteger(quote.commitment.minimum_term_months, "latn"),
                         date: quote.commitment.ends_on ?? "" })}
          </p>
        )}
        <p style={{ margin: 0 }}>
          <strong>
            {quote.disclosed_fee_minor === 0
              ? text("cancel.noFee")
              : fill(locale, "cancel.feeIs", { fee: feeText })}
          </strong>
        </p>
        {lines.length > 1 ? (
          <dl className="facts">
            {lines.map((part) => (
              <div key={part.key} style={{ display: "contents" }}>
                <dt className="muted">{text(part.key)}</dt>
                <dd style={{ margin: 0 }}>
                  <MoneyValue
                    kind="owed" amountMinor={part.minor}
                    currency={quote.disclosed_fee_currency}
                  />
                </dd>
              </div>
            ))}
          </dl>
        ) : null}
        <p style={{ margin: 0 }}>
          {quote.ends_immediately
            ? text("cancel.endsToday")
            : fill(locale, "cancel.endsOn",
                   { date: quote.effective_on,
                     days: formatInteger(quote.notice_days, "latn") })}
        </p>
      </div>

      {/* **"Before you cancel", which is the canvas's own heading.** It is an interruption
          rather than a warning: the next step is a different act, not a confirmation, so it
          carries the link to the freeze rather than a tone that says something went wrong. */}
      {offer !== null ? (
        <div className="ds-freeze-consequence">
          <p style={{ margin: 0 }}><strong>{text("cancel.beforeYouCancel")}</strong></p>
          <p style={{ margin: 0 }}>
            {offer === "dormant_and_committed"
              ? fill(locale, "cancel.offerDormantCommitted",
                     { days: formatInteger(daysSince ?? 0, "latn") })
              : offer === "dormant"
                ? fill(locale, "cancel.offerDormant",
                       { days: formatInteger(daysSince ?? 0, "latn") })
                : text("cancel.offerCommitted")}
          </p>
          <p style={{ margin: 0 }}>
            <Link href={back}>{text("cancel.offerFreeze")}</Link>
          </p>
        </div>
      ) : null}

      {affordance === "cannot" ? (
        <Banner severity="info">{text("cancel.cannot")}</Banner>
      ) : affordance === "form" ? (
        <CancelForm
          locale={locale}
          personId={personId}
          membershipId={live.membership_id}
          feeMinor={quote.disclosed_fee_minor}
          currency={quote.disclosed_fee_currency}
          version={quote.version}
          feeText={feeText}
          backHref={back}
        />
      ) : affordance === "step_up" ? (
        <>
          <Banner severity="info">{text("cancel.stepUpFirst")}</Banner>
          <Link
            href={`/step-up?for=financial&action=membership.lifecycle.change&next=${
              encodeURIComponent(`${back}&cancel=1`)}`}
          >
            {text("cancel.stepUp")}
          </Link>
        </>
      ) : (
        <Banner severity="info">
          {affordance === "refused" && gateVerdict(may) === "denied"
            ? text("cancel.notPermitted") : text(gateMessage(may))}
        </Banner>
      )}

      <dl className="facts">
        {([
          ["cancel.gapFeeLabel", "cancel.gapFee"],
          ["cancel.gapChargeLabel", "cancel.gapCharge"],
        ] as [MessageKey, MessageKey][]).map(([label, why]) => (
          <div key={label} style={{ display: "contents" }}>
            <dt className="muted">{text(label)}</dt>
            <dd style={{ margin: 0 }}>{text(why)}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/**
 * ADM-MSH-06 · DOWNGRADE · TIER 3, and ADM-MSH-05's upgrade read the other way.
 *
 * The canvas, verbatim: **"Dana · Club+ to Club** — She loses: Access to Abdoun and Sweifieh ·
 * 2 monthly PT sessions · her 4 unused PT credits expire on 1 Sep. Takes effect **1
 * September**, not today — she has paid for August at the higher rate and keeps it. New
 * monthly: **JOD 55.00**." And its note: "The loss is stated before the saving, and the credit
 * expiry is the line that matters — a member who discovers it afterwards has been quietly
 * charged for something they never got."
 *
 * **Three facts, and the build had one of them until ADR-0013.** What a plan grants had no
 * table at all — `mem_entitlement_policies` had a consumer and no producer, so activating a
 * membership granted nothing and `change_membership_plan` said in its own response that it
 * could not know which rights the plan being left gave.
 *
 * **No `kind` field anywhere on this screen.** The direction is derived from the two prices,
 * because an upgrade and a downgrade differ in *both* things that matter — when it takes
 * effect and what it charges — so a caller able to declare `downgrade` on a dearer plan would
 * get the next-renewal timing *and* no charge. This build has shipped that shape in six
 * modules.
 */
async function MovingPlan(
  { personId, locale, open, toVariantId }: {
    personId: string; locale: Locale; open: boolean; toVariantId: string;
  },
) {
  const text = (key: MessageKey) => t(locale, key);
  const back = `/people/${personId}?tab=membership`;

  let live: MembershipRow | undefined;
  try {
    live = (await listMemberships(personId)).memberships.find(
      (row) => row.status === "active" || row.status === "frozen");
  } catch {
    // The membership block above already reported the failure; a second banner for the same
    // request would be the same fact twice.
    return null;
  }
  if (live === undefined) return null;

  // **Closed is one control**, which is the cancellation sheet's own reasoning: printing every
  // member's plan options under their membership would make a question nobody asked the most
  // prominent thing on the tab.
  if (!open) {
    return (
      <section className="page-section" aria-labelledby={`plan-${live.membership_id}`}>
        <h2 id={`plan-${live.membership_id}`} style={{ margin: 0 }}>
          {text("downgrade.title")}
        </h2>
        <p className="muted" style={{ margin: 0 }}>{text("downgrade.closedLead")}</p>
        <p style={{ margin: 0 }}>
          <Link href={`${back}&plan=1`}>{text("downgrade.open")}</Link>
        </p>
      </section>
    );
  }

  const [mayRead, mayPrice, mayWrite] = await gateAll([
    "membership.entitlement.read", "catalog.price.read", "membership.agreement.write",
  ] as const);

  let plans: PlanOption[] = [];
  if (mayPrice.allowed && mayRead.allowed) {
    try {
      plans = offerable(await readPlans(locale), live.variant_id ?? "");
    } catch {
      plans = [];
    }
  }

  let quote: ChangeQuote | null = null;
  const chosen = plans.find((one) => one.variant_id === toVariantId);
  if (chosen !== undefined) {
    try {
      quote = await readPlanChangeQuote(live.membership_id, chosen.variant_id);
    } catch {
      quote = null;
    }
  }

  const named = chosen === undefined ? null : planLabel(chosen);
  const amount = (minor: number, currency: string) =>
    formatMoney(minor, currency, "latn", locale);

  return (
    <section className="page-section" aria-labelledby={`plan-${live.membership_id}`}>
      <h2 id={`plan-${live.membership_id}`} style={{ margin: 0 }}>
        {text("downgrade.title")}
      </h2>

      {!mayRead.allowed || !mayPrice.allowed ? (
        <Banner severity="attention"
          title={text(gateMessage(mayRead.allowed ? mayPrice : mayRead))}>
          {text("downgrade.closedLead")}
        </Banner>
      ) : plans.length === 0 ? (
        <Banner severity="attention" title={text("downgrade.noPlans")}>
          {text("downgrade.noPlansWhat")}
        </Banner>
      ) : (
        <>
          <h3 style={{ margin: 0 }}>{text("downgrade.pickAPlan")}</h3>
          <p className="muted" style={{ margin: 0 }}>{text("downgrade.pickAPlanWhy")}</p>
          <ul className="ds-desk-rows">
            {plans.map((one) => {
              const label = planLabel(one);
              const picked = one.variant_id === toVariantId;
              return (
                <li key={one.variant_id} className="ds-desk-row">
                  <span className="ds-desk-row-name">
                    {picked ? label.name : (
                      <Link href={`${back}&plan=1&to=${one.variant_id}`}>{label.name}</Link>
                    )}
                  </span>
                  <span className="muted ds-desk-row-context">
                    {[label.qualifier, one.billing_period].join(" · ")}
                  </span>
                </li>
              );
            })}
          </ul>
        </>
      )}

      {quote !== null && named !== null ? (
        <PlanConsequence
          locale={locale} quote={quote} planName={named.name}
          membershipId={live.membership_id} personId={personId}
          termsId={chosen?.membership_terms_id ?? ""}
          variantId={chosen?.variant_id ?? ""}
          amount={amount}
          canWrite={mayWrite.allowed}
          stepUpHref={gateVerdict(mayWrite) === "needs_step_up"
            ? `/step-up?for=financial&action=membership.agreement.write`
              + `&next=${encodeURIComponent(`${back}&plan=1&to=${toVariantId}`)}`
            : null}
        />
      ) : null}

      <p className="muted" style={{ margin: 0 }}>
        <Link href={back}>{text("downgrade.keep")}</Link>
      </p>
    </section>
  );
}

/** The consequence, in the canvas's own order: the loss, then the date, then the money. */
function PlanConsequence({
  locale, quote, planName, membershipId, personId, termsId, variantId, amount,
  canWrite, stepUpHref,
}: {
  locale: Locale;
  quote: ChangeQuote;
  planName: string;
  membershipId: string;
  personId: string;
  termsId: string;
  variantId: string;
  amount: (minor: number, currency: string) => string;
  canWrite: boolean;
  stepUpHref: string | null;
}) {
  const text = (key: MessageKey) => t(locale, key);
  const loss = lossState(quote.entitlements);
  const timing = timingMessage(quote);
  const refusal = quote.refused_because === null
    ? null : refusalMessage(quote.refused_because);
  const expires = expiring(quote.entitlements);
  const booked = stillBooked(quote.entitlements);

  const rightLabel = (one: { display_name: string; location_id: string | null }) =>
    one.location_id === null
      ? fill(locale, "downgrade.lostAllClubs", { right: one.display_name })
      : fill(locale, "downgrade.lostAtOneClub", { right: one.display_name });

  return (
    <div className="ds-freeze-consequence" data-testid="plan-consequence">
      {/* **The loss first**, which is the canvas's instruction rather than a layout
          preference: "the loss is stated before the saving". */}
      {loss.kind === "nothingDeclared" ? (
        <Banner severity="attention" title={text("downgrade.nothingDeclared")}>
          {text("downgrade.nothingDeclaredWhat")}
        </Banner>
      ) : loss.kind === "sameRights" ? (
        <Banner severity="info" title={text("downgrade.sameRights")}>
          {text("downgrade.sameRightsWhat")}
        </Banner>
      ) : (
        <>
          {quote.entitlements.lost.length > 0 || quote.entitlements.requantified.length > 0
            ? (
              <>
                <p style={{ margin: 0 }}><strong>{text("downgrade.loses")}</strong></p>
                <ul style={{ margin: 0 }}>
                  {quote.entitlements.lost.map((one) => (
                    <li key={`${one.policy_key}-${one.location_id ?? "all"}`}>
                      {rightLabel(one)}
                    </li>
                  ))}
                  {quote.entitlements.requantified.map((one) => (
                    <li key={`q-${one.policy_key}-${one.location_id ?? "all"}`}>
                      {fill(locale, "downgrade.requantified", {
                        right: one.display_name,
                        was: formatInteger(one.from_quantity ?? 0, "latn"),
                        now: formatInteger(one.to_quantity ?? 0, "latn"),
                      })}
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
          {quote.entitlements.gained.length > 0 ? (
            <>
              <p style={{ margin: 0 }}><strong>{text("downgrade.gains")}</strong></p>
              <ul style={{ margin: 0 }}>
                {quote.entitlements.gained.map((one) => (
                  <li key={`g-${one.policy_key}-${one.location_id ?? "all"}`}>
                    {rightLabel(one)}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </>
      )}

      {/* **The credits, which the canvas calls the line that matters.** `written_off` is the
          balance and the balance is already net of what is held, so a booking is protected
          and gets its own sentence rather than being counted as a loss. */}
      {expires.length > 0 ? (
        <>
          <p style={{ margin: 0 }}><strong>{text("downgrade.expiring")}</strong></p>
          <ul style={{ margin: 0 }}>
            {expires.map((one) => (
              <li key={one.grant_id}>
                {one.valid_to === null
                  ? fill(locale, "downgrade.expiringNoDate", {
                    count: one.written_off_on_the_change ?? 0,
                    right: one.display_name,
                  })
                  : fill(locale, "downgrade.expiringOne", {
                    count: one.written_off_on_the_change ?? 0,
                    right: one.display_name,
                    on: utcDate(one.valid_to),
                  })}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {booked.map((one) => (
        <p key={`b-${one.grant_id}`} className="muted" style={{ margin: 0 }}>
          {fill(locale, "downgrade.stillBooked",
            { count: one.held ?? 0, right: one.display_name })}
        </p>
      ))}

      {/* Then the date, with the reason the canvas gives rather than the rule. */}
      <p style={{ margin: 0 }}>{fill(locale, timing.key, timing.values)}</p>

      {/* And the money last. */}
      <p style={{ margin: 0 }}>
        {fill(locale, "downgrade.newAmount", {
          period: quote.billing_period ?? "",
          amount: amount(quote.to_amount_minor, quote.currency),
        })}
        {" "}
        {quote.due_minor === 0 || quote.due_minor === null
          ? text("downgrade.dueNothing")
          : fill(locale, "downgrade.dueNow",
            { amount: amount(quote.due_minor, quote.currency) })}
      </p>
      <p className="muted" style={{ margin: 0 }}>{text("downgrade.notCharged")}</p>

      {!quote.may_change ? (
        <Banner severity="attention" title={text("downgrade.refused")}>
          {/* A vocabulary the backend stores is never a label -- and an unknown value falls
              through to its stored form rather than to "refused", because the set is the
              server's and hiding a reason somebody needs is worse than an ugly one. */}
          {refusal === null ? (quote.refused_because ?? "") : text(refusal)}
        </Banner>
      ) : (
        <PlanMoveForm
          locale={locale} membershipId={membershipId} personId={personId}
          termsId={termsId} variantId={variantId} planName={planName}
          canWrite={canWrite} stepUpHref={stepUpHref}
        />
      )}
    </div>
  );
}

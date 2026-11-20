import Link from "next/link";

import { Banner } from "@/components/ds/banner";
import { MoneyValue } from "@/components/ds/money-value";
import { formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { gateAll, failureMessage } from "@/lib/api";
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
}) {
  const text = (key: MessageKey) => t(locale, key);
  // One round trip rather than three; see `member-metrics.tsx` for why that matters.
  const [records, entitlements, finance] = await gateAll([
    "membership.record.read",
    "membership.entitlement.read",
    "finance.account.read",
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
        <Block allowed={records.allowed} reachable={records.reachable} locale={locale}>
          <Memberships personId={personId} locale={locale} />
        </Block>
      </section>
      ) : null}

      {show("membership") ? (
      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("membership.entitlements")}</h2>
        <Block
          allowed={entitlements.allowed}
          reachable={entitlements.reachable}
          locale={locale}
        >
          <Grants personId={personId} locale={locale} />
        </Block>
      </section>
      ) : null}

      {show("billing") ? (
      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("membership.finance")}</h2>
        <Block allowed={finance.allowed} reachable={finance.reachable} locale={locale}>
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
  allowed,
  reachable,
  locale,
  children,
}: {
  allowed: boolean;
  reachable: boolean;
  locale: Locale;
  children: React.ReactNode;
}) {
  if (allowed) return <>{children}</>;
  return (
    <Banner severity="info">
      {t(locale, reachable ? "gate.denied" : "gate.unreachable")}
    </Banner>
  );
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

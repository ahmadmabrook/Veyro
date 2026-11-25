import { redirect } from "next/navigation";

import { PageHeader } from "@/components/ds/page-header";
import { ProseNote } from "@/components/prose";
import { fill, formatInteger, formatMoney, t, type MessageKey, type Numbering } from "@/i18n/locale";
import { currentSession, gate, gateMessage } from "@/lib/api";
import { readCashSessions } from "@/lib/cash-reads";
import { readStaff } from "@/lib/staff";
import type { CashSession } from "@/lib/cash";
import { listAccounts } from "@/lib/ledger";
import { listLegalEntities } from "@/lib/organization";
import { isWithheld } from "@/lib/people";
import { numerals } from "@/lib/display";
import { presentation } from "@/lib/preferences";
import { utcStamp } from "@/lib/time";

import { CloseDrawerForm } from "./close-form";

/**
 * ADM-PAY-09 · CASH RECONCILIATION — "Closing Layla's shift".
 *
 * **The screen could not be drawn until this session, and the reason is the sixth instance
 * of a shape this build keeps producing.** `open_cash_session` and `close_cash_session`
 * have existed since MOD-018 and nothing read them: a drawer could be opened and the only
 * way to learn what was in it was to close it and read the refusal.
 * `GET /ledger/cash-sessions` is the read.
 *
 * **The expected figure is shown before the count is entered, and the canvas says why**:
 * *"Hiding it would be a fraud control; showing it is an accuracy control, and accuracy is
 * the more common problem."* So the breakdown — the float, what came in, what went out and
 * what should therefore be in the drawer — is above the input rather than revealed after
 * it. The figure is the drawer account's own balance, derived from its postings with no
 * number any caller sent, which is what makes it safe to show.
 *
 * **Two things the canvas draws that this build does not have, said rather than faked.**
 * The design gates the note on a JOD 2.00 threshold; MOD-018 states in as many words that a
 * tenant's tolerance is a commercial decision the sources do not name, so the floor applies
 * instead and *every* difference needs a sentence — stricter, not looser. And the design
 * has a second person counter-sign: nothing here records one, and which permission approves
 * a till, above what figure, and who may not approve their own are product decisions nobody
 * has made. A button that recorded no second person would be worse than its absence.
 */
export default async function CashPage() {
  const { locale } = await presentation();
  // **The tenant's numerals rather than a constant** -- ADR-0015. Every count, date and time
  // on this page follows `localization.numerals`; money does not, and `MoneyValue` carries no
  // `numbering` prop at all so that exception is the component's rule rather than this page's
  // to remember. One read for the whole render: `conventions()` is React's per-request memo
  // and the layout starts it, so this costs no round trip of its own.
  const numbering = await numerals();
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  // **`finance.cash.session` and not `finance.ledger.read`.** This is the drawer workflow,
  // and whoever may close a till may certainly see it; an accountant holding only the
  // ledger read sees the drawer's balance as a line on the trial balance, which is the
  // figure they actually want.
  const may = await gate("finance.cash.session");
  if (!may.allowed) {
    // **A refusal, a step-up and a dead gate are different facts**, and `gateMessage` is
    // what tells them apart -- every page in this app once said "Not permitted" for all
    // four, so a reader went and asked for a grant they already held.
    return (
      <div className="stack">
        <PageHeader title={text("cash.heading")} />
        <ProseNote>{text("cash.refusedWhy")}</ProseNote>
        <p className="muted">{text(gateMessage(may))}</p>
      </div>
    );
  }

  const [drawers, entities, accounts, staff] = await Promise.all([
    readCashSessions({ limit: 50 }),
    listLegalEntities().catch(() => null),
    listAccounts().catch(() => null),
    // **Who opened the drawer, which the canvas puts in the heading: "Closing Layla's
    // shift".** MOD-018 records an identity and MOD-014 holds the person, and the two meet
    // only at `ppl_identity_links` -- so the surface composes, exactly as the staff list
    // does, rather than the ledger service reaching across into another module's tables.
    // A reader without `people.person.read` gets the drawer's own label instead, which is
    // the tenant's name for that till and is a true heading rather than a refusal.
    readStaff({ limit: 200 }).catch(() => null),
  ]);
  // **And the name is often withheld, which is the finding rather than a fallback.**
  // `legal_name` is an identity-class field, so a routine AAL-1 session -- the level the
  // receptionist this screen is drawn for actually holds -- reads `***`. The canvas's
  // heading is "Closing Layla's shift"; a product that masks the name from its own reader
  // cannot write that heading honestly, and "Closing ***'s shift" is worse than the
  // drawer's own label, which is the tenant's name for that till and is always true.
  const nameOf = (identityId: string): string | null => {
    const row = staff?.staff.find((one) => one.identity_id === identityId);
    if (row === undefined) return null;
    const name = row.preferred_name ?? row.legal_name;
    return isWithheld(name) || name === null ? null : name;
  };

  const open = drawers.sessions.filter((one) => one.status === "open");
  const closed = drawers.sessions.filter((one) => one.status !== "open");
  // Where a variance posts. A tenant whose chart has none cannot close a short drawer at
  // all, and the form says so rather than letting the server answer 422 about an account
  // the reader cannot see from here.
  const suspense = accounts?.accounts.find(
    (one) => one.account_kind === "suspense" && one.status === "active");
  const entity = entities?.[0];
  const money = (minor: number, currency: string) =>
    // `latn`, not the tenant's: ADM-SET-07's money exception. See the comment above.
    formatMoney(minor, currency, "latn", locale);

  return (
    <div className="stack">
      <PageHeader title={text("cash.heading")} />
      <ProseNote>{text("cash.title")}</ProseNote>

      <section className="page-section" aria-labelledby="cash-open">
        <h2 id="cash-open">{text("cash.openTitle")}</h2>
        {open.length === 0 ? (
          <p className="muted">{text("cash.noneOpen")}</p>
        ) : (
          open.map((drawer) => (
            <Drawer
              key={drawer.session_id}
              drawer={drawer}
              money={money}
              text={text}
              locale={locale}
              numbering={numbering}
              openedBy={nameOf(drawer.opened_by)}
              legalEntityId={entity?.legal_entity_id ?? ""}
              suspenseAccountId={suspense?.account_id ?? ""}
            />
          ))
        )}
      </section>

      <section className="page-section" aria-labelledby="cash-closed">
        <h2 id="cash-closed">{text("cash.closedTitle")}</h2>
        {closed.length === 0 ? (
          <p className="muted">{text("cash.noneClosed")}</p>
        ) : (
          <ul className="ds-cash-closed">
            {closed.map((one) => (
              <li key={one.session_id}>
                <span>{one.drawer_label}</span>
                <span className="data" dir="ltr">
                  {one.counted_minor === null ? "—" : money(one.counted_minor, one.currency)}
                </span>
                {one.variance_minor !== null && one.variance_minor !== 0 ? (
                  <>
                    <span className="muted">{text("cash.varianceOf")}</span>
                    <span className="data" dir="ltr">
                      {money(one.variance_minor, one.currency)}
                    </span>
                  </>
                ) : null}
                {one.variance_reason === null ? null : (
                  <span className="muted">
                    {text("cash.reasonGiven")}: {one.variance_reason}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="page-section" aria-labelledby="cash-gaps">
        <h2 id="cash-gaps">{text("cash.gapsTitle")}</h2>
        <dl className="facts">
          {([
            ["cash.gapCosignLabel", "cash.gapCosign"],
            ["cash.gapThresholdLabel", "cash.gapThreshold"],
            ["cash.gapSpanLabel", "cash.gapSpan"],
            ["cash.gapEntryLabel", "cash.entryNote"],
            ["cash.gapWhoLabel", "cash.gapWho"],
          ] as [MessageKey, MessageKey][]).map(([label, why]) => (
            <div key={label} style={{ display: "contents" }}>
              <dt className="muted">{text(label)}</dt>
              <dd style={{ margin: 0 }}>{text(why)}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}

/** One drawer: the breakdown the canvas draws, then the count. */
function Drawer({
  drawer, money, text, locale, numbering, openedBy, legalEntityId, suspenseAccountId,
}: {
  drawer: CashSession;
  /** Who opened it, where the reader may know. The canvas names the person. */
  openedBy: string | null;
  money: (minor: number, currency: string) => string;
  text: (key: MessageKey) => string;
  locale: "en" | "ar";
  /**
   * The tenant's numeral system, for the counts and dates this renders.
   *
   * **Widened from the literal `"latn"` by ADR-0015**, which is what the setting reaching a
   * page means. Money is the exception and is not rendered through this: `MoneyValue` carries
   * no numbering at all, and a direct `formatMoney` here passes the literal.
   */
  numbering: Numbering;
  legalEntityId: string;
  suspenseAccountId: string;
}) {
  // **The entry count sits on the line it counts**, as the canvas has it ("Cash taken · 14
  // sales"), rather than in a sentence under the table -- a note that long between the
  // figure and the input is a wall where the design has a label.
  const rows: [string, string | null, number][] = [
    [text("cash.float"), null, drawer.opening_float_minor],
    [text("cash.taken"),
     fill(locale, "cash.takenEntries",
          { count: formatInteger(drawer.entries_in, numbering) }),
     drawer.taken_minor],
    [text("cash.paidOut"), null, drawer.paid_out_minor],
  ];
  return (
    <article className="ds-cash-drawer">
      <h3>
        {fill(locale, "cash.closing", { drawer: openedBy ?? drawer.drawer_label })}
      </h3>
      <p className="muted" style={{ margin: 0 }}>
        {fill(locale, "cash.openedAt", { at: utcStamp(drawer.opened_at) })}
      </p>

      {/* **The expected figure, above the input.** The canvas's own decision, and the sum
          of the three rows above it by construction -- which is what makes it checkable by
          the person holding the notes rather than a number they have to trust. */}
      <dl className="ds-cash-breakdown">
        {rows.map(([label, aside, minor]) => (
          <div key={label} style={{ display: "contents" }}>
            <dt>
              {label}
              {aside === null ? null : <span className="muted"> · {aside}</span>}
            </dt>
            <dd className="data" dir="ltr">{money(minor, drawer.currency)}</dd>
          </div>
        ))}
        <div style={{ display: "contents" }}>
          <dt className="ds-cash-total">{text("cash.expected")}</dt>
          <dd className="ds-cash-total data" dir="ltr">
            {drawer.expected_minor === null
              ? "—" : money(drawer.expected_minor, drawer.currency)}
          </dd>
        </div>
      </dl>
      {drawer.expected_minor === null ? null : (
        <CloseDrawerForm
          locale={locale}
          sessionId={drawer.session_id}
          legalEntityId={legalEntityId}
          suspenseAccountId={suspenseAccountId}
          currency={drawer.currency}
          expectedMinor={drawer.expected_minor}
        />
      )}
    </article>
  );
}

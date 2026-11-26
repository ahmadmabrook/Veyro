import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { NotYet } from "@/components/not-yet";
import { MetricCell, MetricRow } from "@/components/ds/metric-cell";
import { MoneyValue } from "@/components/ds/money-value";
import { PageHeader } from "@/components/ds/page-header";
import { ProseNote } from "@/components/prose";
import { Withheld } from "@/components/withheld";
import { fill, formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { currentSession, failureMessage, gateAll, gateMessage, gateVerdict } from "@/lib/api";
import {
  evidenceFrom,
  kindName,
  readAttendanceWindow,
  readDisputes,
  reasonName,
  statusName,
  undecided,
  urgency,
  type Dispute,
  type DisputeList,
  type Evidence,
} from "@/lib/disputes";
import { readMembership } from "@/lib/membership";
import { listMembers } from "@/lib/members-reads";
import { isWithheld, withheldRemedy } from "@/lib/people";
import { numerals } from "@/lib/display";
import { presentation } from "@/lib/preferences";

/**
 * ADM-PAY-10 · DISPUTE · ACCOUNTANT ONLY.
 *
 * The canvas, in full:
 *
 * > `DISPUTED`  **INV-19102**
 * > Faris Alami's bank has challenged **JOD 78.00** from 2 June, claiming the service was
 * > not received. The amount is held by the acquirer.
 * > ┌ Evidence due 26 August · 7 days
 * > └ Missing the deadline forfeits the amount automatically.
 * > EVIDENCE VEYRO CAN ASSEMBLE
 * > ☑ 11 check-ins in the billed month
 * > ☑ Signed membership contract
 * > ☑ Invoice and JoFotara reference
 * > ☐ Written statement · you add this
 * > `[Submit evidence]` `[Accept the loss]`
 * > The check-in record is the strongest evidence a gym has and Veyro assembles it
 * > automatically. Accepting the loss is a real option and is recorded as a decision, not a
 * > lapse.
 *
 * **Three routes could record, answer and settle a chargeback and nothing could list one.**
 * A dispute existed only for whoever had just written it — this build's recurring "a writer
 * with no reader" shape, closed here by `GET /finance/disputes`, which also computes the
 * deadline rather than leaving a reader to subtract two dates: `collections.evidence_window`
 * already decides it and a second definition of the one figure the screen is about would be
 * the integrations board's finding again.
 *
 * **The evidence list is assembled, and that is the screen's claim.** "Veyro assembles it
 * automatically" is only true if something does, so each line is a real read through its own
 * gate rather than a tick drawn next to a sentence:
 *
 * - **The check-ins** come from `GET /access/attendance/window`, which did not exist.
 *   `person_attendance` answers how often somebody *was* coming — a habit measured over the
 *   weeks before their last visit — and a chargeback is answered with a different question:
 *   did they come during the period this invoice billed for. Counted from entries and never
 *   from decisions, because a card failing at the door produces refused decisions for
 *   exactly the member whose attendance is being proved.
 * - **The signed contract** is the agreement's own `signed_at` and `signature_kind`, read
 *   through `membership.record.read`.
 * - **The invoice and its fiscal acknowledgement** ride on the dispute read.
 * - **The written statement** is the operator's, and the canvas says so: `☐ you add this`.
 *
 * **A refused read is not a missing piece of evidence.** The canvas has two states and this
 * build needs three: a reader without `access.decision.read` would otherwise be told the gym
 * cannot prove attendance it can prove. `EvidenceState` carries `refused` for that.
 *
 * **Neither button exists.** `respond_to_dispute` and `settle_dispute` are both stepped-up
 * financial writes with no form in this build, and "Accept the loss" is the more
 * consequential of the two — the canvas itself calls it a decision rather than a lapse,
 * which is an argument for recording who made it, not for a button that answers 403.
 */

export const dynamic = "force-dynamic";

export default async function DisputesPage({
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
  const only = typeof query.status === "string" ? query.status : undefined;

  if (!(await currentSession())) redirect("/login?next=/payments/disputes");

  const [mayDisputes, mayPeople, mayAttendance, mayMembership, mayNames] = await gateAll([
    // **Routine, and the board exists because of it.** `finance.dispute.manage` is
    // financial, so a board behind it is one an accountant reaches only after a step-up
    // -- and the thing this screen is for is noticing that seven days are left.
    "finance.dispute.read",
    "people.person.read",
    "access.decision.read",
    "membership.record.read",
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

  if (!mayDisputes.allowed) {
    // **No step-up offer, because the permission is routine.** A step-up cannot lift a
    // refusal of a routine action, so the branch would be a declared remedy nothing can
    // reach -- the defect this repository names in four modules. A reader refused here
    // needs the grant, and `gateMessage` says which.
    return (
      <Shell locale={locale}>
        <Banner severity="info">{text(gateMessage(mayDisputes))}</Banner>
      </Shell>
    );
  }

  let list: DisputeList;
  try {
    list = await readDisputes(only ? { status: only } : {});
  } catch (error) {
    return (
      <Shell locale={locale}>
        <Banner severity="critical">{text(failureMessage(error))}</Banner>
      </Shell>
    );
  }

  const names = mayPeople.allowed
    ? await listMembers({ limit: 200 })
      .then((page) => new Map(page.people.map((p) => [p.person_id, p.legal_name])))
      .catch(() => null)
    : null;

  // The evidence, assembled per dispute. Bounded by the page's own `limit`, and only for
  // the ones still to be decided — a dispute already won or lost needs no case made.
  const evidence = new Map<string, Evidence[]>();
  for (const dispute of list.disputes) {
    if (!undecided(dispute)) continue;
    evidence.set(dispute.dispute_id, await assemble(
      dispute, { mayAttendance: mayAttendance.allowed, mayMembership: mayMembership.allowed },
    ));
  }

  const exposure = list.at_stake[0] ?? null;

  return (
    <Shell
      locale={locale}
      // **How many and how much, promoted.** A chargeback has a deadline and an amount that
      // is forfeited if it passes, and both figures sat at `type.bodySm` beside the as-of
      // date. The date stays on the figures line, which is where freshness belongs.
      metrics={
        list.count === 0 ? undefined : (
          <MetricRow label={text("dispute.heading")}>
            <MetricCell
              label={text("dispute.heading")}
              value={<span className="data" dir="ltr">
                {formatInteger(list.count, numbering)}
              </span>}
            />
            {/* `owed` — money being taken back, which is the kind this is. */}
            {exposure === null ? null : (
              <MetricCell
                label={text("dispute.atStake")}
                value={
                  <MoneyValue
                    kind="owed"
                    amountMinor={exposure.amount_minor}
                    currency={exposure.currency}
                  />
                }
              />
            )}
          </MetricRow>
        )
      }
      figures={
        list.count === 0 ? (
          text("dispute.noneOpen")
        ) : (
          <span className="data" dir="ltr">{list.as_of}</span>
        )
      }
    >
      {/* **The remedy belongs on the board.** Every payer here reads "Withheld" on a
          level-1 session, and the canvas names the member in its opening sentence — a
          dispute you cannot attach to a person is one nobody can act on. Same offer the
          members list and the recovery workspace make, and shown only when something is
          actually withheld. */}
      {list.disputes.some((d) => isWithheld(names?.get(d.payer_person_id) ?? "")) ? (
        <p className="ds-note">
          {remedy === "step_up" ? (
            <>
              {text("dispute.namesWithheld")}{" "}
              <Link
                href={`/step-up?for=financial&action=member.identity.read&next=${
                  encodeURIComponent("/payments/disputes")}`}
              >
                {text("member.raiseSession")}
              </Link>
            </>
          ) : remedy === "no_answer" ? (
            text("member.namesWithheldNoAnswer")
          ) : (
            text("member.namesWithheldNotHeld")
          )}
        </p>
      ) : null}

      {list.count === 0 ? (
        <Banner severity="info">{text("dispute.empty")}</Banner>
      ) : (
        list.disputes.map((dispute) => (
          <DisputeCard
            key={dispute.dispute_id}
            locale={locale}
            dispute={dispute}
            name={names === null ? null : names.get(dispute.payer_person_id) ?? null}
            namesRefused={names === null}
            evidence={evidence.get(dispute.dispute_id) ?? null}
            nameWithheld={nameWithheld}
          />
        ))
      )}

      <NotYet locale={locale} items={["dispute.submitTitle", "dispute.acceptTitle", "dispute.heldTitle"]} />
    </Shell>
  );
}

/**
 * Fetch what the evidence list needs, then let the lib classify it.
 *
 * The split is this repository's own `domain` / `service` shape: the reads live here and
 * the three states live in `evidenceFrom`, where both of the ones a fixture cannot reach
 * are provable. A classification written inline would have `refused` reachable only by
 * signing in as somebody the fixture does not have.
 */
async function assemble(
  dispute: Dispute,
  may: { mayAttendance: boolean; mayMembership: boolean },
): Promise<Evidence[]> {
  const attendance = may.mayAttendance && dispute.billed_on !== null
    ? await readAttendanceWindow(
      dispute.payer_person_id, dispute.billed_on, dispute.opened_on).catch(() => null)
    : null;
  const membership = may.mayMembership && dispute.membership_id !== null
    ? await readMembership(dispute.membership_id).catch(() => null)
    : null;
  return evidenceFrom(dispute, {
    mayAttendance: may.mayAttendance,
    attendance,
    mayMembership: may.mayMembership,
    membershipRead: membership !== null,
    signedAt: membership?.agreement?.signed_at ?? null,
    signatureKind: membership?.agreement?.signature_kind ?? null,
  });
}

function DisputeCard({
  locale,
  dispute,
  name,
  namesRefused,
  evidence,
  nameWithheld,
}: {
  locale: Locale;
  dispute: Dispute;
  name: string | null;
  namesRefused: boolean;
  evidence: Evidence[] | null;
  // Which sentence a withheld name gets: decided by the page from the gate's answer, because
  // only the page knows whether a step-up would lift the mask for this reader.
  nameWithheld: MessageKey;
}) {
  const text = (key: MessageKey) => t(locale, key);
  const level = urgency(dispute);
  const status = statusName(dispute.status);
  const kind = kindName(dispute.dispute_kind);
  const reason = reasonName(dispute.reason_code);
  const heading = `dispute-${dispute.dispute_id}`;

  return (
    <section className="page-section" aria-labelledby={heading}>
      <h2 id={heading} style={{ margin: 0 }}>
        <span className="data" dir="ltr">
          {dispute.document_number ?? dispute.provider_case_ref}
        </span>
        {" · "}
        {status === null ? dispute.status : text(status)}
      </h2>

      {/* The canvas's opening sentence, composed from what the read returns. */}
      <p style={{ margin: 0 }}>
        {namesRefused ? (
          <span className="muted">{text("payer.nameNeedsPermission")}</span>
        ) : name === null ? (
          <span className="muted">{text("dispute.notOnThisPage")}</span>
        ) : isWithheld(name) ? (
          <Withheld locale={locale} reason={nameWithheld} />
        ) : (
          <Link href={`/people/${dispute.payer_person_id}`}>{name}</Link>
        )}
        {" — "}
        {fill(locale, "dispute.challenged", {
          kind: kind === null ? dispute.dispute_kind : text(kind),
          on: dispute.paid_at.slice(0, 10),
        })}{" "}
        <MoneyValue
          kind="owed"
          amountMinor={dispute.amount_minor}
          currency={dispute.currency}
        />
        {". "}
        {reason === null
          ? <span className="data" dir="ltr">{dispute.reason_code}</span>
          : text(reason)}
      </p>

      {/* **The deadline, in its own box.** The canvas draws it bordered in the error ink and
          follows it with what missing it costs, which is the sentence the box is for: a
          date with no consequence beside it is a date somebody files. */}
      <Banner severity={level === "noted" ? "info" : "critical"}>
        {level === "closed"
          ? fill(locale, "dispute.windowClosed", { days: -dispute.days_remaining })
          : fill(locale, "dispute.due", {
            on: dispute.respond_due_on, days: dispute.days_remaining,
          })}
          {" "}
        {text(level === "closed" ? "dispute.forfeited" : "dispute.missingForfeits")}
      </Banner>

      {evidence === null ? (
        <p className="muted" style={{ margin: 0 }}>{text("dispute.settledNoCase")}</p>
      ) : (
        <>
          <h3 className="ds-sec-label" style={{ margin: 0 }}>
            {text("dispute.evidenceTitle")}
          </h3>
          <ul className="ds-evidence">
            {evidence.map((item) => (
              <li key={item.key} data-state={item.state}>
                <span className="ds-evidence-mark" aria-hidden="true">
                  {item.state === "have" ? "☑" : "☐"}
                </span>
                <span className="ds-evidence-what">
                  {text(item.label)}
                  {item.detail === undefined ? null : (
                    <>
                      {" "}
                      <span className="data" dir="ltr">{item.detail}</span>
                    </>
                  )}
                  {item.note === undefined ? null : (
                    <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
                      {text(item.note)}
                    </div>
                  )}
                </span>
                {/* The mark is never alone: §15's rule, and here the three states have
                    three different meanings rather than two. */}
                <span className="ds-visually-hidden">
                  {text(`dispute.state.${item.state}` as MessageKey)}
                </span>
              </li>
            ))}
          </ul>
          <ProseNote>{text("dispute.strongestEvidence")}</ProseNote>
        </>
      )}
    </section>
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
   * The metric row, immediately under the header. A slot rather than the first child: the
   * refusal and read-failure returns have a header and nothing to measure, and an empty set
   * already says so in a banner.
   */
  metrics?: React.ReactNode;
}) {
  return (
    <div className="stack">
      <PageHeader
        title={t(locale, "dispute.heading")}
        {...(figures ? { figures } : {})}
      />
      {metrics}
      {children}
    </div>
  );
}

import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { MoneyValue } from "@/components/ds/money-value";
import { PageHeader } from "@/components/ds/page-header";
import { Prose, ProseNote } from "@/components/prose";
import { Withheld } from "@/components/withheld";
import { fill, t, type Locale, type MessageKey } from "@/i18n/locale";
import { currentSession, failureMessage, gateAll, gateMessage } from "@/lib/api";
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
import { isWithheld } from "@/lib/people";
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
  const text = (key: MessageKey) => t(locale, key);
  const query = await searchParams;
  const only = typeof query.status === "string" ? query.status : undefined;

  if (!(await currentSession())) redirect("/login?next=/payments/disputes");

  const [mayDisputes, mayPeople, mayAttendance, mayMembership] = await gateAll([
    // **Routine, and the board exists because of it.** `finance.dispute.manage` is
    // financial, so a board behind it is one an accountant reaches only after a step-up
    // -- and the thing this screen is for is noticing that seven days are left.
    "finance.dispute.read",
    "people.person.read",
    "access.decision.read",
    "membership.record.read",
  ] as const);

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
      figures={
        list.count === 0 ? (
          text("dispute.noneOpen")
        ) : (
          <>
            {fill(locale, "dispute.count", { count: list.count })}
            {exposure === null ? null : (
              <>
                {" · "}
                {/* `owed` — money being taken back, which is the kind this is. */}
                <MoneyValue
                  kind="owed"
                  amountMinor={exposure.amount_minor}
                  currency={exposure.currency}
                />{" "}
                {text("dispute.atStake")}
              </>
            )}
            {" · "}
            <span className="data" dir="ltr">{list.as_of}</span>
          </>
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
          {text("dispute.namesWithheld")}{" "}
          <Link
            href={`/step-up?for=financial&action=member.identity.read&next=${
              encodeURIComponent("/payments/disputes")}`}
          >
            {text("member.raiseSession")}
          </Link>
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
          />
        ))
      )}

      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("dispute.notYet")}</h2>
        <dl className="facts">
          <dt className="muted">{text("dispute.submitTitle")}</dt>
          <dd style={{ margin: 0 }}><Prose>{text("dispute.submitWhy")}</Prose></dd>
          <dt className="muted">{text("dispute.acceptTitle")}</dt>
          <dd style={{ margin: 0 }}><Prose>{text("dispute.acceptWhy")}</Prose></dd>
          <dt className="muted">{text("dispute.heldTitle")}</dt>
          <dd style={{ margin: 0 }}><Prose>{text("dispute.heldWhy")}</Prose></dd>
        </dl>
      </section>
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
}: {
  locale: Locale;
  dispute: Dispute;
  name: string | null;
  namesRefused: boolean;
  evidence: Evidence[] | null;
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
          <span className="data" dir="ltr">{dispute.payer_person_id.slice(0, 8)}</span>
        ) : name === null ? (
          <span className="muted">{text("dispute.notOnThisPage")}</span>
        ) : isWithheld(name) ? (
          <Withheld locale={locale} reason="member.withheldIdentity" />
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
}: {
  locale: Locale;
  children: React.ReactNode;
  figures?: React.ReactNode;
}) {
  return (
    <div className="stack">
      <PageHeader
        title={t(locale, "dispute.heading")}
        {...(figures ? { figures } : {})}
      />
      {children}
    </div>
  );
}

import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { NotYet, PageHeader } from "@/components/ds/page-header";
import { fill, t, type MessageKey } from "@/i18n/locale";
import { currentSession, gate, gateAll, gateMessage, gateVerdict } from "@/lib/api";
import { listSellablePlans } from "@/lib/leads-reads";
import { numerals } from "@/lib/display";
import { presentation } from "@/lib/preferences";
import { headlineDays, planChoice, type TrialPlan } from "@/lib/walk-in-trial";
import { withheldRemedy } from "@/lib/mask";

import { TrialForm } from "./trial-form";

/**
 * FD-05 · WALK-IN TRIAL.
 *
 * "Two fields and a start: name and phone. Creates a lead already in trial state with the
 * clock running. Everything else is captured later by the sales team -- a person standing at
 * a desk will not complete a form."
 *
 * **The first Front Desk screen reachable without an id**, which is why it is also the first
 * `/desk` route in the rail. FD-01, the live check-in a receptionist actually starts their
 * shift on, is unbuilt; FD-06 and FD-03 are reached from a class and a refusal.
 *
 * **Five permissions, one answer, and the step-up offered before the button.** The command
 * writes a person, a lead, an agreement and an activation, and three of those are financial
 * class -- so an ordinary password session cannot press it. That is the honest cost rather
 * than a reason to withhold the screen: one step-up per twelve-hour window is a receptionist
 * stepping up once at the start of a shift, which is ADM-MSH-03's precedent. A button that
 * answered 403 would be worse than its absence; a button that asks first is what this app
 * already does for a masked read.
 *
 * **The read gate is what the screen is for**, as on ADM-CRM-04: without `people.person.read`
 * there is no duplicate check, and a door that creates records with no check is the opposite
 * of this screen's purpose -- the record created here is the one the member converts on, so a
 * duplicate made at this door is a duplicate in the membership, the billing and the door log
 * afterwards.
 *
 * **The heading names the trial's length because the canvas's does**: "Start a 7-day trial"
 * is a figure, so it comes from the published plan's own `trial_days` rather than being
 * written into a string. With two plans of different lengths there is no single answer until
 * one is chosen, and a heading naming one of them would be naming whichever sorted first.
 */
export default async function WalkInTrialPage() {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);
  // **The tenant's numerals rather than a constant** -- ADR-0015. Every count, date and time
  // on this page follows `localization.numerals`; money does not, and `MoneyValue` carries no
  // `numbering` prop at all so that exception is the component's rule rather than this page's
  // to remember. One read for the whole render: `conventions()` is React's per-request memo
  // and the layout starts it, so this costs no round trip of its own.
  const numbering = await numerals();

  if (!(await currentSession())) redirect("/login");

  const [read, lead, person, agreement, activate, mayNames] = await gateAll([
    "people.person.read",
    "crm.lead.write",
    "people.person.write",
    "membership.agreement.write",
    "membership.agreement.activate",
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

  if (!read.allowed) {
    return (
      <>
        <PageHeader title={text("deskTrial.heading")} />
        <Banner severity="attention" title={text(gateMessage(read))}>
          {text("deskTrial.needsRead")}
          {gateVerdict(read) === "needs_step_up" ? (
            <>
              {" "}
              <Link href={
                "/step-up?for=financial&action=people.person.read&next=/desk/trial"
              }>
                {text("member.raiseSession")}
              </Link>
            </>
          ) : null}
        </Banner>
      </>
    );
  }

  // **One answer for the whole press, because the command is one request.** Five permissions
  // and a partial grant is still a button that cannot work, so the page asks whether the
  // press is possible rather than reporting which of the five is missing -- and the verdict
  // comes from the strongest refusal, because a step-up fixes `needs_step_up` and nothing
  // fixes `denied`.
  const writes = [lead, person, agreement, activate];
  const canStart = writes.every((one) => one.allowed);
  const blocked = writes.find((one) => !one.allowed);
  const startVerdict = blocked === undefined ? "denied" : gateVerdict(blocked);

  // **The plan read is `catalog.product.read`'s and the page says when it is closed**, for
  // the configuration board's reason: a tenant with no trial and a reader who may not see the
  // catalogue are different facts, and an empty answer rendered as the first would tell a
  // receptionist their gym sells no trial.
  const mayPlans = await gate("catalog.product.read");
  const plans: readonly TrialPlan[] = mayPlans.allowed
    ? (await listSellablePlans({ trials: "only" })).plans
    : [];
  const choice = planChoice(plans);
  const days = headlineDays(choice);

  return (
    <>
      <PageHeader
        title={days === null
          ? text("deskTrial.heading")
          : fill(locale, "deskTrial.headingDays", { count: days }, numbering)}
        figures={text("deskTrial.lead")}
      />

      {!mayPlans.allowed ? (
        <Banner severity="attention" title={text("deskTrial.plansRefused")}>
          {text("deskTrial.plansRefusedWhat")}
        </Banner>
      ) : choice.kind === "none" ? (
        <Banner severity="attention" title={text("deskTrial.noPlan")}>
          {text("deskTrial.noPlanWhat")}
        </Banner>
      ) : (
        <TrialForm
        nameWithheld={nameWithheld}
          locale={locale} numbering={numbering}
          canStart={canStart} startVerdict={startVerdict} choice={choice}
        />
      )}

      <NotYet title={text("deskTrial.notYet")}>
        <dt>{text("deskTrial.gapCredential")}</dt>
        <dd>{text("deskTrial.gapCredentialWhy")}</dd>
        <dt>{text("deskTrial.gapInvitation")}</dt>
        <dd>{text("deskTrial.gapInvitationWhy")}</dd>
        <dt>{text("deskTrial.gapOwner")}</dt>
        <dd>{text("deskTrial.gapOwnerWhy")}</dd>
        <dt>{text("deskTrial.gapNumber")}</dt>
        <dd>{text("deskTrial.gapNumberWhy")}</dd>
      </NotYet>
    </>
  );
}

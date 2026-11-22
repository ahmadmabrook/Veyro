import Link from "next/link";

import { Banner } from "@/components/ds/banner";
import { PageHeader } from "@/components/ds/page-header";
import { StatusBadge } from "@/components/ds/status-badge";
import { fill, t, type MessageKey } from "@/i18n/locale";
import { ApiError, gateAll, gateMessage, gateVerdict } from "@/lib/api";
import {
  doorOf, isDeviceFault, latestRefusal, overrideOffer, overriddenSince, sayFor,
  type AccessDecision,
} from "@/lib/denial";
import { readAttendance, readDecisions, type PersonAttendance } from "@/lib/denial-reads";
import { readZone } from "@/lib/access";
import { readNames } from "@/lib/desk-reads";
import { nameOf } from "@/lib/desk";
import { presentation } from "@/lib/preferences";
import { utcStamp } from "@/lib/time";

import { OverrideForm } from "./override-form";

/**
 * FD-03 · ACCESS DENIED · WHAT TO SAY AND DO · RECEP.
 *
 * > "**His membership ended on 7 August** and the 14-day grace ran out five days ago. He was
 * > here three times a week for two years — worth asking whether something changed before you
 * > lead with the renewal." … "Without override authority the last button is absent and the
 * > panel names Ziad as the person to call. Never a locked control with no route."
 *
 * **This is the one screen in the product where what a receptionist may say is governed by a
 * permission**, and that is MOD-022 working rather than a gap. A refusal carries a public
 * line a door may display and a private reason behind `access.decision.read_reason`, which is
 * financial class -- and the split is over the *code* as well as the prose, because "both
 * reviewers found that the split gated the sentence and not the fact". So a password-only
 * desk lands on `see_front_desk` for every restricted reason, which is exactly what the
 * member was told, and the sentence the canvas prints needs a step-up.
 *
 * **Four modules on one screen, composed rather than joined.** The refusal and the pattern
 * are MOD-022's, the name is MOD-014's, and each is asked through its own gate -- paragraph
 * 1300 bars the join and a surface asking three times is not one.
 *
 * **Three of the canvas's four actions are absent and each says why.** Renewing and a day
 * pass are sales, and taking money is reserved to the owner of this build; the photo needs an
 * object store. The fourth, "Let in, flag it", is MOD-022's own override: a decision in its
 * own right rather than a flag on one, so the refusal stays in the log beside it.
 */
export default async function DenialPage(
  { params }: { params: Promise<{ personId: string }> },
) {
  const { personId } = await params;
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);

  const [mayDecisions, mayReason, mayOverride, mayPeople, mayZone] = await gateAll([
    "access.decision.read",
    "access.decision.read_reason",
    "access.decision.override",
    "people.person.read",
    "access.zone.read",
  ] as const);

  if (!mayDecisions.allowed) {
    return (
      <>
        <PageHeader title={text("denial.title")} />
        <Banner severity="info">{text(gateMessage(mayDecisions))}</Banner>
      </>
    );
  }

  let decisions: AccessDecision[] = [];
  let failed = false;
  try {
    decisions = (await readDecisions(personId)).decisions;
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    failed = true;
  }
  if (failed) {
    return (
      <>
        <PageHeader title={text("denial.title")} />
        <Banner severity="critical">{text("error.unexpected")}</Banner>
      </>
    );
  }

  const refusal = latestRefusal(decisions);
  if (refusal === null) {
    return (
      <>
        <PageHeader title={text("denial.title")} />
        <Banner severity="info">{text("denial.noRefusal")}</Banner>
      </>
    );
  }

  // The pattern and the name, each through its own gate. A refusal with neither is still the
  // screen; a blank where a name belongs is not.
  const attendance: PersonAttendance | null = await readAttendance(personId)
    .catch(() => null);
  const names = mayPeople.allowed ? await readNames([personId]).catch(() => null) : null;
  // **Which door, which the canvas puts under the name.** A fifth gate rather than a join:
  // a reader may hold the decision read without the zone read, and `doorOf` answers `null`
  // rather than guessing -- a receptionist sent to the wrong lane walks away from the person
  // in front of them.
  const zone = mayZone.allowed ? await readZone(refusal.zone_id).catch(() => null) : null;
  const door = doorOf(zone, refusal.point_id);
  const person = names?.get(personId);
  const shown = nameOf(person);

  const say = sayFor(refusal.code);
  const alreadyIn = overriddenSince(decisions, refusal);
  const offer = overrideOffer(
    { allowed: mayOverride.allowed, verdict: gateVerdict(mayOverride) },
    alreadyIn !== null,
  );

  return (
    <div className="stack" data-density="touch">
      {/* **The member's name is the title**, which the canvas draws and which the members
          list already learned: a bare marker under a generic heading is a reader looking in
          two places for who this is. Masked at an ordinary sign-in, named once stepped up. */}
      <PageHeader
        title={shown ?? text("member.nameWithheld")}
        figures={
          <>
            {/* **The design system's own vocabulary**, which already has this word: a badge
                whose *state* a screen invents is a badge two screens spell differently. The
                word beside it is localized, because the vocabulary is English and this is
                the first screen in the app to render one -- an untranslated badge in an
                Arabic line is the finding this repository has now recorded five times. */}
            <StatusBadge status="Denied" label={text("denial.badge")} />
            {door === null ? null : <> · {door.zone} · {door.point}</>}
            {" · "}
            <span className="data" dir="ltr">{utcStamp(refusal.decided_at)}</span>
            {person?.member_number ? <> · {person.member_number}</> : null}
          </>
        }
      />
      {/* **What to say, which is the screen's own title.** The sentence comes from the code
          rather than from the prose: a surface that parsed a reason string to decide what to
          show is the shape MOD-016 shipped, where four English words were the whole
          enforcement of a usage limit. */}
      <section className="page-section" aria-labelledby="say-heading">
        <h2 id="say-heading">{text("denial.whatToSay")}</h2>
        <p className="ds-denial-say">
          {say === null ? refusal.public_reason : text(say)}
        </p>
        {isDeviceFault(refusal.code) ? (
          <Banner severity="attention">{text("denial.deviceFault")}</Banner>
        ) : null}
        {/* The private reason, where this session may read it. `reason_withheld` is the
            module's own answer to whether it kept one back *from this caller*, so the offer
            appears exactly where there is something behind it rather than on every refusal.
            **It was spelled `masked` here and the server has never sent that field**, so this
            branch never rendered at all -- found by a browser test looking for the link. */}
        {refusal.private_reason !== null ? (
          <p className="muted">{refusal.private_reason}</p>
        ) : refusal.reason_withheld
          && gateVerdict(mayReason) === "needs_step_up" ? (
            <p className="muted">
              <Link href={
                "/step-up?for=financial&action=access.decision.read_reason"
                + `&next=/desk/denials/${personId}`
              }>
                {text("denial.seeWhy")}
              </Link>
            </p>
          ) : null}
      </section>

      {/* **"He was here three times a week for two years."** The canvas's own reason for
          putting it here: a gap means nothing until you know what it is a gap from, and a
          screen that led with the renewal before asking what changed is the thing the
          sentence warns against. */}
      <section className="page-section" aria-labelledby="pattern-heading">
        <h2 id="pattern-heading">{text("denial.history")}</h2>
        {attendance === null || attendance.days_since === null ? (
          <p className="muted">{text("denial.historyNone")}</p>
        ) : (
          <>
            <p>
              {/* **`count` as a number, which `fill` requires of a plural message**: it
                  picks the CLDR category from it, and Arabic has six where English has two.
                  Passing only the formatted string throws -- and it threw on this page
                  until a screenshot caught it, because the placeholder was named for what
                  it meant rather than for what the mechanism needs. */}
              {/* **Nought days ago is "today", which no plural form says well.** English
                  has no CLDR `zero` category at all, so it falls to `other` and reads "last
                  in 0 days ago"; Arabic has one, and writing "today" into it makes the
                  category mean something other than its count. The branch is clearer than
                  either. */}
              {attendance.days_since === 0
                ? text("denial.lastVisitToday")
                : fill(locale, "denial.lastVisit", { count: attendance.days_since })}
              {attendance.entries_per_week === null ? null : (
                <>
                  {" · "}
                  {/* **Rounded, and the sentence says "about".** The canvas writes "3x a
                      week" and this app has one number-rendering path, which refuses a
                      fraction -- `formatInteger` throws, deliberately, because a
                      cross-runtime parity test compares it against the backend character
                      for character. "4.9 times a week" is false precision for a pattern
                      anyway: the figure exists to tell somebody who came often from
                      somebody who did not. */}
                  {fill(locale, "denial.wasComing", {
                    count: Math.round(attendance.entries_per_week),
                  })}
                </>
              )}
            </p>
            <p className="muted">{text("denial.beforeYouLead")}</p>
          </>
        )}
      </section>

      <section className="page-section ds-denial-override" aria-labelledby="override-heading">
        <h2 id="override-heading">{text("denial.override")}</h2>
        <p className="muted">{text("denial.overrideWhat")}</p>
        {offer === "already" ? (
          <Banner severity="info">{text("denial.alreadyOverridden")}</Banner>
        ) : offer === "form" ? (
          <OverrideForm
            locale={locale} personId={personId} pointId={refusal.point_id}
            decisionId={refusal.decision_id}
          />
        ) : offer === "step_up" ? (
          <p>
            {text("denial.overrideNeedsStepUp")}{" "}
            <Link href={
              "/step-up?for=financial&action=access.decision.override"
              + `&next=/desk/denials/${personId}`
            }>
              {text("denial.raiseSession")}
            </Link>
          </p>
        ) : (
          /* **"Never a locked control with no route."** The button is absent, which is the
             canvas's own instruction -- and naming the person to call is the half this build
             cannot do, so it says that rather than inventing a name. */
          <>
            <p>{text("denial.overrideDenied")}</p>
            <p className="muted">{text("denial.overrideWhoToAsk")}</p>
          </>
        )}
      </section>

      <section className="page-section ds-denial-gaps">
        <h2>{text("denial.notYet")}</h2>
        <dl className="facts">
          <dt>{text("denial.gapRenew")}</dt>
          <dd>{text("denial.gapRenewWhy")}</dd>
          <dt>{text("denial.gapDayPass")}</dt>
          <dd>{text("denial.gapDayPassWhy")}</dd>
          <dt>{text("denial.gapWhere")}</dt>
          <dd>{text("denial.gapWhereWhy")}</dd>
          <dt>{text("denial.gapPhoto")}</dt>
          <dd>{text("denial.gapPhotoWhy")}</dd>
        </dl>
      </section>
    </div>
  );
}

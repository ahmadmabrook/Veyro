import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { MetricCell } from "@/components/ds/metric-cell";
import { RecordHeader } from "@/components/ds/record-header";
import { Timeline, TimelineItem } from "@/components/ds/timeline";
import { ProseNote } from "@/components/prose";
import { Withheld } from "@/components/withheld";
import {
  fill, formatInteger, t, type Locale, type MessageKey,
} from "@/i18n/locale";
import { ApiError, currentSession, gateAll, gateMessage, gateVerdict } from "@/lib/api";
import { readNames } from "@/lib/desk-reads";
import {
  INTERESTS, engagementWord, interestWord, kindWord, nextStage, sinceLabel, stageWord,
  type LeadDetail, type TrialCard,
} from "@/lib/leads";
import { readLead, readLeadTrial } from "@/lib/leads-reads";
import { isWithheld } from "@/lib/people";
import { presentation } from "@/lib/preferences";
import { dayLabel, monthDayLabel, timeOfDay } from "@/lib/time";
import { LOST_REASONS, reasonWord, recontactSentence } from "@/lib/lost";
import { urgencyKey, usageSentence } from "@/lib/trial";

import {
  InterestsForm, MarkLostForm, NextActionForm, OwnerForm, ReopenForm, StageForm,
  TouchpointForm, WithdrawInterestForm,
} from "./forms";

/**
 * ADM-CRM-03 · LEAD PROFILE — "Rana Sabbagh / NO CONTACT · 2 DAYS / Sweifieh open day ·
 * +962 79 411 0288 · interested in classes and PT" over four metrics and a TOUCHPOINTS list.
 *
 * **Five working forms**, because every MOD-027 permission is routine: a touchpoint, a stage
 * move, the ownership, the next action and the interests. Elsewhere in this app a write form
 * is absent because its permission is a stepped-up financial one and "a button that answered
 * 403 is worse than its absence"; none of these is.
 *
 * **The canvas's four trial figures are drawn now, and this paragraph used to say they were
 * not.** `4 VISITS`, `4 CLASSES`, `2 DAYS LEFT` and `High ENGAGEMENT` all need a trial, and
 * the note here said "nothing in this build marks a product as one" -- which ADR-0010 D7
 * settled and ADM-CRM-05 rendered. A gap note outliving its gap is a claim about the product,
 * and this one sat in the docstring of the file that closed it. What is still true is the
 * reason the cells are conditional: a cell reading `0 VISITS` for a member who has been four
 * times is the confident wrong answer MOD-014's own 360 was bitten by, so the sales row is
 * drawn for a lead with no trial and the trial row for one with.
 *
 * **The phone number is not here either.** The canvas puts it in the subline; it is a contact
 * point on the member record behind its own permission, and this screen composes the name
 * through `GET /people/names` and does not reach the number.
 */
export default async function LeadPage({
  params,
  searchParams,
}: {
  params: Promise<{ leadId: string }>;
  searchParams: Promise<{ lost?: string }>;
}) {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);
  const { leadId } = await params;
  // ADM-CRM-07's side sheet, as a parameter on the profile. ADM-MSH-07's judgement: this app
  // has no side sheet, and a query string keeps the member's context on screen while giving
  // "Keep it open" somewhere to go.
  const sheetOpen = (await searchParams).lost === "1";

  if (!(await currentSession())) redirect("/login");

  const [mayLead, mayTouch, mayWrite, mayPeople, mayVisits, mayBookings] = await gateAll([
    "crm.lead.read", "crm.touchpoint.write", "crm.lead.write", "people.person.read",
    // **ADM-CRM-05's card carries three modules' facts**, so it asks for all three: the
    // window is MOD-017's, the visits are MOD-022's entry events and the classes are
    // MOD-020's settled bookings. Three of its four cells is not the card the canvas draws,
    // so the read is skipped rather than half-made and the screen says which reads it wants.
    "access.decision.read", "booking.booking.read",
  ] as const);

  if (!mayLead.allowed) {
    const verdict = gateVerdict(mayLead);
    return (
      <div className="stack">
        <Banner severity={verdict === "gate_failed" ? "critical" : "info"}>
          {verdict === "denied" ? text("lead.refused") : text(gateMessage(mayLead))}
        </Banner>
        <Link href="/leads">{text("lead.backToBoard")}</Link>
      </div>
    );
  }

  let lead: LeadDetail | null = null;
  let trial: TrialCard | null = null;
  let missing = false;
  let failed = false;
  let names = new Map<string, { person_id: string; legal_name: string | null }>();
  try {
    lead = await readLead(leadId);
    trial = mayVisits.allowed && mayBookings.allowed
      ? await readLeadTrial(leadId).catch(() => null)
      : null;
    const wanted = [lead.person_id, ...(lead.owner_person_id ? [lead.owner_person_id] : [])];
    names = mayPeople.allowed
      ? await readNames(wanted).catch(() => new Map())
      : new Map();
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 404) missing = true;
    else failed = true;
  }

  if (missing || lead === null) {
    return (
      <div className="stack">
        <Banner severity="info">{text(failed ? "error.unexpected" : "lead.notFound")}</Banner>
        <Link href="/leads">{text("lead.backToBoard")}</Link>
      </div>
    );
  }

  const nameOf = (personId: string | null): string | null => {
    if (personId === null) return null;
    const name = names.get(personId)?.legal_name ?? null;
    // A masked value is a marker rather than a name -- the board paid for discovering that
    // `***` renders as though somebody were called it.
    return name !== null && !isWithheld(name) ? name : null;
  };

  const name = nameOf(lead.person_id);
  const owner = lead.owner_person_id === null ? null : nameOf(lead.owner_person_id);
  const interests = lead.interests
    .map((one) => {
      const key = interestWord(one);
      return key === null ? one : t(locale, key);
    })
    .join(" · ");
  const stage = (() => {
    const key = stageWord(lead.stage);
    return key === null ? lead.stage : t(locale, key);
  })();
  const onward = nextStage(lead.stage);
  //: The trial, where there is one. ADM-CRM-05 is a *state* of this screen rather than a
  //: route of its own, which the canvas says by labelling one card with both ids -- so the
  //: band, the metric row and one section change and everything else stays.
  const running = trial !== null && trial.on_trial ? trial : null;
  // The same `as const` every other screen uses, and the reason the integer formatter takes
  // it as an argument rather than reading a locale: a numeral system is a tenant setting this
  // build does not carry, and one number path is what the cross-runtime parity test holds.
  const numbering = "latn" as const;
  /**
   * The header's one band.
   *
   * **A running trial outranks the cold mark.** "DAY 6 OF 7" is the canvas's own band on this
   * card, and a trialist is not somebody nobody has rung -- the clock that matters is the one
   * running out. `RecordHeader` draws one band, so this is a choice rather than two, and it
   * is computed here because a JSX comment cannot sit in an attribute position.
   */
  const band = running !== null
    ? {
        band: {
          text: fill(locale, "trial.band",
                     { day: running.day_of, of: running.of_days }),
          tone: "warning" as const,
        },
      }
    : lead.going_cold
      ? { band: { text: text("lead.bandCold"), tone: "warning" as const } }
      : {};

  return (
    <div className="stack">
      <RecordHeader
        id="lead-heading"
        name={
          name ?? <Withheld locale={locale} reason="member.withheldIdentity" />
        }
        {...band}
        subline={
          <>
            {lead.source === null
              ? text("lead.sublineNoSource")
              : fill(locale, "lead.sublineSource", { source: lead.source })}
            {" · "}
            {owner === null
              ? text(lead.owner_person_id === null
                ? "lead.sublineUnowned" : "member.withheld")
              : fill(locale, "lead.sublineOwner", { owner })}
            {" · "}
            {interests === ""
              ? text("lead.sublineNoInterests")
              : fill(locale, "lead.sublineInterests", { interests })}
          </>
        }
      />

      {/* **The metric row is the trial's four while one is running**, which is ADM-CRM-05's
          own card: `4 VISITS · 4 CLASSES · 2 DAYS LEFT · High ENGAGEMENT`. A row that showed
          the sales four beside them would be eight cells where the canvas draws four, and the
          sales figures are the ones a trial has already answered -- the stage is "on trial"
          and the last contact is a visit. */}
      {running === null ? (
        <section className="metrics" aria-label={text("lead.title")}>
          <MetricCell label={text("lead.metaStage")} value={stage} />
          <MetricCell
            label={text("lead.metaSince")}
            value={sinceLabel(locale, lead.hours_since_contact)}
          />
          <MetricCell
            label={text("lead.metaTouchpoints")}
            value={String(lead.touchpoint_count)}
          />
          <MetricCell
            label={text("lead.metaNext")}
            value={lead.next_action ?? text("leads.noNext")}
            {...(lead.next_action_on !== null ? { comparison: lead.next_action_on } : {})}
          />
        </section>
      ) : (
        <section className="metrics" aria-label={text("trial.engagement")}>
          <MetricCell
            label={text("trial.visits")}
            value={formatInteger(running.visits, numbering)}
          />
          <MetricCell
            label={text("trial.classes")}
            value={formatInteger(running.classes, numbering)}
          />
          <MetricCell
            label={text("trial.daysLeft")}
            value={formatInteger(running.days_left, numbering)}
          />
          {/* **A word, never the stored band.** A vocabulary the backend stores is never a
              label, which this app has five recorded defects from -- and `null` falls through
              to the stored form rather than to a guess, because the set is the server's and
              may grow. */}
          <MetricCell
            label={text("trial.engagement")}
            value={(() => {
              const key = engagementWord(running.engagement);
              return key === null ? running.engagement : text(key);
            })()}
          />
        </section>
      )}

      {/* ADM-CRM-05's consequence panel: the urgency, the sentence, and the one action --
          which this build cannot take, so it says what it would take instead. */}
      {running === null ? null : (
        <section className="page-section" aria-labelledby="lead-trial">
          <h2 id="lead-trial">
            {running.ends_tomorrow || running.days_left <= 1
              ? text(urgencyKey(running))
              : fill(locale, "trial.running", { count: running.days_left })}
          </h2>
          <p>{text(usageSentence(running))}</p>
          <ProseNote>{text("trial.visitsAreEntries")}</ProseNote>
          <ProseNote>{text("trial.engagementIsUse")}</ProseNote>
          {/* **One `dd` per `dt`.** `.facts` is a two-column grid whose items are the `dt`
              and the `dd` themselves, so a second `dd` under one `dt` is auto-placed into a
              track with **zero width**: 5,687 pixels tall, `visibility: visible`, and a box
              a reader cannot see -- which Playwright correctly calls hidden. The membership
              block paid for the other half of this rule, where wrapping each pair in a
              `<div>` made the div the grid item and put both labels on one row. */}
          {/* **The canvas's own control, which was a gap entry until ADM-CRM-06 existed.**
              It read "Converting is a plan change ... so it is a form this screen does not
              have yet", and the screen is there now -- so the note goes with the gap, in the
              same change, which is this repository's rule about a gap list being a claim
              about the product. What the conversion screen still does not do is take the
              money, and it says so where the figure is rather than here. */}
          <p>
            <Link href={`/leads/${leadId}/convert`}>{text("trial.convert")}</Link>
          </p>
          <ProseNote>{text("trial.convertShowsTheCost")}</ProseNote>
        </section>
      )}

      {/* **Which of the two absences this is.** A reader who may not make the card's three
          reads is told so; a reader who may and got nothing back had a request fail, which is
          a different fact with a different next step. **Not a note for "no trial"**: three of
          the five board columns are people without one, so the ordinary state says nothing and
          the sales metric row above is the screen. */}
      {mayVisits.allowed && mayBookings.allowed ? (
        trial === null ? <ProseNote>{text("error.unexpected")}</ProseNote> : null
      ) : (
        <ProseNote>{text("trial.refused")}</ProseNote>
      )}

      {/* **The empty state is not inside the list.** `Timeline` renders an `<ol>`, and an
          `<ol>` may hold only `<li>` -- a banner in there is an axe violation, which the
          profile's own scan caught. An empty timeline is a sentence rather than a list of
          one, so it replaces the component instead of sitting inside it. */}
      {lead.touchpoints.length === 0 ? (
        <section className="page-section" aria-labelledby="lead-timeline-empty">
          <h2 id="lead-timeline-empty">{text("lead.timeline")}</h2>
          <Banner severity="info">{text("lead.timelineEmpty")}</Banner>
        </section>
      ) : (
        <Timeline label={text("lead.timeline")}>
          {lead.touchpoints.map((touch) => {
            const kind = kindWord(touch.kind);
            return (
              <TimelineItem
                key={touch.touchpoint_id}
                // UTC, and the gutter says so -- which is the one "today" this build has: a
                // tenant with clubs in two zones has two local todays and a timeline
                // carrying neither.
                time={timeOfDay(touch.occurred_at)}
                day={dayLabel(touch.occurred_at)}
                tone="visit"
                title={kind === null ? touch.kind : t(locale, kind)}
                meta={
                  touch.summary_withheld
                    ? <Withheld locale={locale} reason="lead.summaryWithheld" />
                    : touch.summary
                }
              />
            );
          })}
        </Timeline>
      )}

      {mayTouch.allowed ? (
        <section className="page-section" aria-labelledby="lead-record">
          <h2 id="lead-record">{text("lead.sectionRecord")}</h2>
          <TouchpointForm
            locale={locale}
            leadId={leadId}
            kinds={kindOptions(locale)}
          />
        </section>
      ) : null}

      {mayWrite.allowed ? (
        <>
          <section className="page-section" aria-labelledby="lead-stage">
            <h2 id="lead-stage">{text("lead.sectionStage")}</h2>
            <StageForm
              locale={locale}
              leadId={leadId}
              next={onward === null ? null : {
                value: onward,
                label: fill(locale, "lead.stageTo", { stage: stageLabel(locale, onward) }),
              }}
            />
          </section>

          <section className="page-section" aria-labelledby="lead-owner">
            <h2 id="lead-owner">{text("lead.sectionOwner")}</h2>
            <OwnerForm
              locale={locale}
              leadId={leadId}
              owned={lead.owner_person_id !== null}
            />
          </section>

          <section className="page-section" aria-labelledby="lead-next">
            <h2 id="lead-next">{text("lead.sectionNext")}</h2>
            <NextActionForm
              locale={locale}
              leadId={leadId}
              set={lead.next_action !== null}
            />
          </section>

          <section className="page-section" aria-labelledby="lead-interests">
            <h2 id="lead-interests">{text("lead.sectionInterests")}</h2>
            <InterestsForm
              locale={locale}
              leadId={leadId}
              held={lead.interests}
              options={INTERESTS.map((one) => ({
                value: one, label: interestLabel(locale, one),
              }))}
            />
            {/* **Each held interest can be taken back now**, which is ADR-0010 D11 and the
                remedy this section's own note used to say was missing: until the withdrawal
                existed, a tick here was permanent on a routine permission -- MOD-013's rule.
                A row per interest rather than one multi-select, because taking one back is a
                single decision and a form that could withdraw three at once would be a
                control nobody asked for. */}
            {lead.interests.map((one) => (
              <WithdrawInterestForm
                key={one}
                locale={locale}
                leadId={leadId}
                interest={one}
                label={interestLabel(locale, one)}
              />
            ))}
          </section>

          {/* ADM-CRM-07. **A side sheet in the design and a query parameter here**, which is
              ADM-MSH-07's judgement: this app has no side sheet, and `?lost=1` keeps the
              member's context on screen while giving "Keep it open" something to do. A
              permanently-open destructive form has no way out. */}
          <section className="page-section" aria-labelledby="lead-lost">
            <h2 id="lead-lost">{text("lost.title")}</h2>
            {lead.lost ? (
              <div className="stack">
                <Banner severity="info">
                  {fill(locale, "lost.wasLost", {
                    date: lead.lost_at === null
                      ? "" : monthDayLabel(lead.lost_at.slice(0, 10), locale),
                    reason: (() => {
                      const key = lead.lost_reason === null
                        ? null : reasonWord(lead.lost_reason);
                      return key === null
                        ? (lead.lost_reason ?? "") : text(key);
                    })(),
                  })}
                </Banner>
                {lead.lost_detail === null
                  ? null : <ProseNote>{lead.lost_detail}</ProseNote>}
                {/* **The stage is still there**, which is the decision this screen exists to
                    make visible: a sixth stage would have needed a backwards edge on reopen,
                    and that would make the board's own counts unreconstructable. */}
                <ProseNote>
                  {fill(locale, "lost.stageKept", { stage })}
                </ProseNote>
                <ProseNote>{text(recontactSentence(lead.recontactable))}</ProseNote>
                <ReopenForm locale={locale} leadId={leadId} />
              </div>
            ) : sheetOpen ? (
              <div className="stack">
                <p>
                  {name === null
                    ? text("lost.whyUnnamed")
                    : fill(locale, "lost.why", { name })}
                </p>
                <MarkLostForm
                  locale={locale}
                  leadId={leadId}
                  reasons={LOST_REASONS.map((one) => ({
                    value: one.value, label: text(one.label),
                  }))}
                />
                <ProseNote>{text("lost.note")}</ProseNote>
                <ProseNote>{text("lost.feedsReport")}</ProseNote>
                <Link href={`/leads/${leadId}`}>{text("lost.keepOpen")}</Link>
              </div>
            ) : (
              <Link href={`/leads/${leadId}?lost=1`}>{text("lost.title")}</Link>
            )}
          </section>
        </>
      ) : null}

      <ProseNote>{text("leads.nameIsElsewhere")}</ProseNote>

      <section className="page-section" aria-labelledby="lead-gaps">
        <h2 id="lead-gaps">{text("leads.gaps")}</h2>
        <dl className="facts">
          <dt>{text("lead.gapTrialLabel")}</dt>
          <dd>{text("lead.gapTrial")}</dd>
          <dt>{text("lead.gapPhoneLabel")}</dt>
          <dd>{text("lead.gapPhone")}</dd>
          <dt>{text("lead.gapWhatsAppLabel")}</dt>
          <dd>{text("lead.gapWhatsApp")}</dd>
        </dl>
      </section>

      <Link href="/leads">{text("lead.backToBoard")}</Link>
    </div>
  );
}

function stageLabel(locale: Locale, stage: string): string {
  const key = stageWord(stage);
  return key === null ? stage : t(locale, key);
}

function interestLabel(locale: Locale, interest: string): string {
  const key = interestWord(interest);
  return key === null ? interest : t(locale, key);
}

function kindOptions(locale: Locale): { value: string; label: string }[] {
  return ["call", "message", "email", "visit", "tour", "note"].map((kind) => {
    const key = kindWord(kind);
    return { value: kind, label: key === null ? kind : t(locale, key) };
  });
}

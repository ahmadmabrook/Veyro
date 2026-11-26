import Link from "next/link";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { AttentionRow } from "@/components/ds/attention-row";
import { Banner } from "@/components/ds/banner";
import { Inspector, InspectorList, PersonRow } from "@/components/ds/inspector";
import { MoneyValue } from "@/components/ds/money-value";
import { RecordHeader, Tabs } from "@/components/ds/record-header";
import { Timeline, TimelineFilter, TimelineItem } from "@/components/ds/timeline";
import { memberFacts } from "@/components/member-metrics";
import { MembershipPanels } from "@/components/membership-panels";
import { Withheld } from "@/components/withheld";
import { fill, formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import {
  ApiError, currentSession, failureMessage, gate, gateAll, gateMessage, gateVerdict,
} from "@/lib/api";
import { listMembers } from "@/lib/members-reads";
import { MetricCell, MetricRow } from "@/components/ds/metric-cell";
import {
  classifyEvent,
  credentialKindName,
  isTimelineFilter,
  readAttendance,
  readCredentials,
  TIMELINE_FILTERS,
  type TimelineFilterKey,
} from "@/lib/member-record";
import {
  isWithheld, readMember360, splitComposed, splitSections, withheldRemedy, type Member360, type Note, type Person, type TimelineEntry, type WithheldRemedy,
} from "@/lib/people";
import { numerals } from "@/lib/display";
import { presentation } from "@/lib/preferences";
import { dayLabel, timeOfDay, utcStamp } from "@/lib/time";

/**
 * Member 360 — ADM-MEM-01, drawn as the design draws it.
 *
 * **This page had every fact and none of the anatomy.** It rendered an `<h1>` and nine
 * stacked `<dl>` blocks; the canvas draws pattern 02 (the queue it was opened from, pinned
 * beside the record), a header with the member's name, a status band and the actions, nine
 * tabs, the one thing wrong as an inline AttentionRow, five MetricCells, and a timeline with
 * a time gutter and a coloured spine. Every piece of that is a component in the design's own
 * list for this screen, and the list is the specification.
 *
 * Three things the rebuild had to decide rather than copy, each recorded where it is made:
 *
 * - **Four of the nine tabs are not drawn**, because coaching, bookings per person,
 *   purchases and documents each need a module or a read this build does not have. They are
 *   named at the foot with the reason, which is ADM-MEM-05's rule applied to a tab: a control
 *   that opens an empty panel says the member has no bookings.
 *
 *   **Attendance was on that list and should not have been.** `GET /access/attendance` was
 *   built for the LAST VISIT metric cell above and the note still said attendance per person
 *   needed a read this build does not have -- a claim about what the product cannot do goes
 *   stale the moment somebody builds it. MOD-014's own 360 record carries the same defect:
 *   five sections said "not built in this repository" and four of those modules had been
 *   built since. ADM-MEM-07 is a tab now.
 * - **Three of the five timeline filters are not drawn**, for the same reason: MOD-014
 *   projects nine event types and none of MOD-019's, MOD-020's or MOD-013's is among them.
 * - **No action button is drawn at all.** "Take payment · JOD 55.00" is the canvas's primary
 *   action and every member-facing write in this build is a stepped-up financial permission
 *   with no form behind it. The AttentionRow says what is owed and what the product cannot do
 *   about it from here.
 *
 * **This is also the one surface in the build where `Decision.mask` reaches a reader**, and
 * the rendering is still the point: a withheld value is marked with its reason, because an
 * empty cell is indistinguishable from "there was nothing here", which is the one reading that
 * is always wrong. The two reasons have different remedies -- an identity field needs a
 * stronger sign-in, which the step-up link offers; a health field needs a level this screen
 * cannot reach -- a passkey on a hardware authenticator, which no page here enrols -- in
 * this build, because `member.health.read` is `biometric_sensitive`, which maps to assurance
 * level 3, which is reached by signing in with a passkey and not by a step-up.
 */

const TABS =
  ["overview", "membership", "billing", "attendance", "access", "notes"] as const;
type TabKey = (typeof TABS)[number];

const TAB_LABEL: Record<TabKey, MessageKey> = {
  overview: "member.tabOverview",
  membership: "member.tabMembership",
  billing: "member.tabBilling",
  attendance: "member.tabAttendance",
  access: "member.tabAccess",
  notes: "member.tabNotes",
};

function isTab(value: string | undefined): value is TabKey {
  return value !== undefined && (TABS as readonly string[]).includes(value);
}

export default async function Member360Page({
  params,
  searchParams,
}: {
  params: Promise<{ personId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { personId } = await params;
  const query = await searchParams;
  // **The tenant's numerals** -- ADR-0015. The quantities on this record follow
  // `localization.numerals`; money does not, and `MoneyValue` carries no numbering at all.
  const numbering = await numerals();
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);
  const tabParam = typeof query.tab === "string" ? query.tab : undefined;
  const tab: TabKey = isTab(tabParam) ? tabParam : "overview";
  // ADM-MSH-07's sheet, which this app draws as a parameter on the tab rather than as an
  // overlay -- see `MembershipPanels`' own note on why.
  const cancelling = query.cancel === "1";
  // ADM-MSH-06, the same query-parameter shape and for the same reason: this app has no side
  // sheet, and a permanently-open form that moves a member's plan has no way out. `to` names
  // the plan being quoted, so the picker and the consequence are one URL a reader can share.
  const movingPlan = query.plan === "1";
  const toVariantId = typeof query.to === "string" ? query.to : "";
  const filterParam = typeof query.filter === "string" ? query.filter : undefined;
  const filter: TimelineFilterKey = isTimelineFilter(filterParam) ? filterParam : "all";

  if (!(await currentSession())) redirect("/login");

  // **Batched**, because `/authz/checks` exists for it. `member.identity.read` is not for
  // this read -- it is what says whether a withheld *identity* field's remedy is a step-up or
  // whether this role does not include identity fields at all.
  const [may, mayNames] = await gateAll([
    "people.person.read", "member.identity.read",
  ] as const);
  // **A contact field is a different control and has no step-up.** `member.profile.read` is
  // `data_access` with no financial class, so a contact value is masked when the reader does
  // not hold the permission and a stronger sign-in never lifts it -- yet the panel below said
  // "identity fields need a stronger sign-in. Step up and the value is readable." for a phone
  // number, which was false in every case rather than in some. Its own key now.
  const remedy = withheldRemedy(gateVerdict(mayNames));
  const nameWithheld: MessageKey = remedy === "step_up"
    ? "member.withheldIdentity"
    : "member.withheldIdentityNoRemedy";
  if (!may.allowed) {
    return (
      <Banner severity="info">
        {text(gateMessage(may))}
      </Banner>
    );
  }

  let record: Member360;
  try {
    record = await readMember360(personId);
  } catch (error) {
    // **A malformed id in the URL is "no such person", not "something went wrong".** The
    // route shape-checks the id and answers 422 `bad_person_id`; rendering that as an
    // unexpected error tells the reader the product is broken when what happened is that
    // they followed a bad link. 404 and 422 are the same fact to somebody reading a page.
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) {
      return <Banner severity="info">{text("member.notFound")}</Banner>;
    }
    return (
      <Banner severity="critical">
        {text(failureMessage(error))}
      </Banner>
    );
  }

  // The pinned pane. **The same read the members list uses**, so the two agree about who is
  // in the tenant and in what order -- a second ordering here would make the queue the reader
  // came from and the queue beside the record disagree, which is the one thing pattern 02's
  // "list keeps position" rule is about.
  const queue = await listMembers({ limit: 25 }).catch(() => null);
  const facts = await memberFacts(personId, locale);
  const { available, unavailable } = splitSections(record.sections);
  // **The projection's gaps, minus the three this page fills itself.** MOD-014 says
  // "MOD-017 owns this and nothing here reads it" about membership, entitlements and
  // finance -- true of the projection and the reason paragraph 1300 exists -- and this page
  // composes all three on its own tabs. Rendering that unfiltered put "membership: nothing
  // here reads it" under a Membership tab full of memberships.
  const { composed, absent } = splitComposed(unavailable);
  const name = isWithheld(record.person.legal_name)
    ? text("member.nameWithheld")
    : (record.person.preferred_name && !isWithheld(record.person.preferred_name)
      ? record.person.preferred_name
      : record.person.legal_name);

  const href = (next: string) =>
    `/people/${encodeURIComponent(personId)}${next === "overview" ? "" : `?tab=${next}`}`;

  return (
    <Inspector
      list={
        <InspectorList
          label={text("member.queue")}
          title={text("member.queue")}
          counts={
            queue === null
              ? text("member.queueUnavailable")
              : fill(locale, "member.queueCounts", {
                shown: formatInteger(queue.people.length, numbering),
                total: formatInteger(queue.total, numbering),
              })
          }
          // **The canvas prints `↑↓ moves · ⏎ opens · list keeps position` and two of those
          // three are what a list of links already does.** `↑↓` is a listbox behaviour that
          // would need client JavaScript and its own focus management, so the footer says
          // what this pane does rather than quoting a key that is not bound.
          footer={text("member.queueKeys")}
        >
          {(queue?.people ?? []).map((row) => (
            <PersonRow
              key={row.person_id}
              href={`/people/${encodeURIComponent(row.person_id)}`}
              current={row.person_id === personId}
              name={isWithheld(row.legal_name) ? text("member.nameWithheld") : row.legal_name}
              detail={row.lifecycle_state ?? text("members.noProfile")}
              figure={
                <span className="data" dir="ltr">
                  {row.member_number ?? "—"}
                </span>
              }
            />
          ))}
        </InspectorList>
      }
    >
      <RecordHeader
        avatar
        name={name}
        {...(facts.band
          ? { band: { text: text(facts.band.key), tone: facts.band.tone } }
          : {})}
        subline={
          <>
            {record.member_profile?.lifecycle_state ?? text("members.noProfile")}
            {record.member_profile?.joined_on
              ? <> {"· "}{fill(locale, "member.since",
                { date: record.member_profile.joined_on })}</>
              : null}
            {record.member_profile?.member_number
              ? <> {"· "}<span className="data" dir="ltr">
                {record.member_profile.member_number}
              </span></>
              : null}
          </>
        }
        tabs={
          <Tabs
            label={text("member.tabs")}
            current={tab}
            href={href}
            tabs={TABS.map((key) => ({ key, label: text(TAB_LABEL[key]) }))}
          />
        }
      />
      <div className="ds-record-body">
        {tab === "overview" ? (
          <Overview
            record={record}
            facts={facts}
            locale={locale}
            personId={personId}
            filter={filter}
            nameWithheld={nameWithheld}
            remedy={remedy}
          />
        ) : null}
        {tab === "membership" || tab === "billing" ? (
          <MembershipPanels
            personId={personId} locale={locale} only={tab}
            cancelling={cancelling}
            movingPlan={movingPlan} toVariantId={toVariantId}
          />
        ) : null}
        {tab === "attendance"
          ? <AttendanceTab personId={personId} locale={locale} />
          : null}
        {tab === "access" ? <AccessTab personId={personId} locale={locale} /> : null}
        {tab === "notes" ? <Notes record={record} locale={locale} /> : null}

        {/* **At the foot, on every tab, and only what is genuinely absent.** A reader who
            switched to Billing because Overview was quiet still needs to know which areas of
            a member's life this product does not hold -- and what it does hold, elsewhere on
            this page, must not appear here as a gap. */}
        <section className="ds-panel">
          <div className="ds-panel-head">
            <h2 className="ds-panel-title">{text("member.unavailable")}</h2>
          </div>
          <div className="ds-panel-body">
            <p className="muted" style={{ margin: 0 }}>{text("member.unavailableWhy")}</p>
            <dl className="facts">
              {/* **The section name, not the server's sentence.** Each `why` is written for
                  whoever maintains Veyro -- "class attendance ... is MOD-020's (OPS-02) and
                  nothing here reads it" -- and this is a member's record, read by a
                  receptionist with that member in front of them. The product fact an operator
                  needs is which parts of a member's life Veyro does not hold, which is the
                  list itself; the module that would hold them is not something they can act
                  on or look up. The backend keeps returning the sentence, and this stops
                  printing it. */}
              {absent.map(([section]) => (
                <Fact key={section} label={section}>
                  <span className="muted">{text("member.sectionNotHeld")}</span>
                </Fact>
              ))}
            </dl>
          </div>
          <p className="ds-panel-note">
            {fill(locale, "member.composedElsewhere", {
              sections: composed.map(([section]) => section).join(" · "),
            })}
          </p>
          <p className="ds-panel-note">
            {text("member.composedFrom")}{": "}
            {available.map(([section]) => section).join(" · ")}
            {" · "}
            {text("member.consents")}{" "}
            <span className="data">
              {formatInteger(record.consent_record_count, numbering)}
            </span>
          </p>
        </section>
      </div>
    </Inspector>
  );
}

/**
 * The Overview tab, which is the canvas: the one thing wrong, the five metrics, the timeline
 * and the side panels.
 */
async function Overview({
  record,
  facts,
  locale,
  personId,
  filter,
  nameWithheld,
  remedy,
}: {
  record: Member360;
  facts: Awaited<ReturnType<typeof memberFacts>>;
  locale: Locale;
  personId: string;
  filter: TimelineFilterKey;
  nameWithheld: MessageKey;
  remedy: WithheldRemedy;
}) {
  // **The tenant's numerals** -- ADR-0015, one read for the whole render.
  const numbering = await numerals();
  const text = (key: MessageKey) => t(locale, key);
  const shown = filter === "all"
    ? record.timeline
    : record.timeline.filter((entry) => classifyEvent(entry.event_type).filter === filter);

  return (
    <>
      {/* **The AttentionRow is inline and conditional.** The canvas's own note over the
          healthy member: "No green badges. The absence of an alert band *is* the signal." So
          a member in good standing gets no row here at all rather than a reassuring one. */}
      {facts.band && facts.outstandingMinor !== null && facts.currency !== null
        && facts.outstandingMinor > 0 ? (
          <ul className="ds-queue" aria-label={text("member.attention")}>
            <AttentionRow
              id="member-attention"
              severity="critical"
              category={text("member.categoryMoney")}
              kind="money"
              when={text("member.asOfNow")}
              money={{
                amount: (
                  <MoneyValue
                    kind="owed"
                    amountMinor={facts.outstandingMinor}
                    currency={facts.currency}
                  />
                ),
                meaning: text("member.owedMeaning"),
              }}
              headline={text("member.bandOverdueHeadline")}
              evidence={text("member.overdueEvidence")}
              // **No action button.** Taking a payment is `finance.payment.take`, a
              // stepped-up financial permission with no form in this build, and a button
              // that answered 403 would be worse than the gap.
              actions={null}
            />
          </ul>
        ) : null}

      {facts.row}

      <div className="ds-record-split">
        <Timeline
          label={text("member.timeline")}
          filters={TIMELINE_FILTERS.map((key) => (
            <TimelineFilter
              key={key}
              current={key === filter}
              href={`/people/${encodeURIComponent(personId)}${
                key === "all" ? "" : `?filter=${key}`}`}
            >
              {text(`member.filter.${key}` as MessageKey)}
            </TimelineFilter>
          ))}
          footer={
            record.timeline.length === 0
              ? text("member.noTimeline")
              : fill(locale, "member.timelineCount", { count: record.timeline.length }, numbering)
          }
        >
          {shown.map((entry) => (
            <Entry key={entry.entry_id} entry={entry} locale={locale} />
          ))}
        </Timeline>

        <div className="ds-record-side">
          <IdentityPanel
            person={record.person} locale={locale} nameWithheld={nameWithheld}
            remedy={remedy}
          />
          <ContactPanel person={record.person} locale={locale} />
        </div>
      </div>
    </>
  );
}

function Entry({ entry, locale }: { entry: TimelineEntry; locale: Locale }) {
  const { tone } = classifyEvent(entry.event_type);
  return (
    <TimelineItem
      time={timeOfDay(entry.occurred_at)}
      day={dayLabel(entry.occurred_at)}
      tone={tone}
      title={
        isWithheld(entry.summary)
          ? <Withheld locale={locale} reason="member.withheldHealth" />
          : entry.summary
      }
      meta={
        <span className="data" dir="ltr">
          {entry.event_type} · {utcStamp(entry.occurred_at)}
        </span>
      }
    />
  );
}

/** MOD-022 on a member's page: what they hold, and the decisions taken on it. */
/**
 * ADM-MEM-07 · ATTENDANCE — when they come in, how often, and what the chart cannot say.
 *
 * **The read existed and the tab said it did not.** This page's own notes listed attendance
 * among five tabs "not drawn, because attendance per person, coaching, bookings per person,
 * purchases and documents each need a module or a read this build does not have" --
 * and `GET /access/attendance` had already been built for the LAST VISIT metric cell above.
 * A claim about what the product cannot do goes stale the moment somebody builds it, which
 * is the defect MOD-014's own 360 record carries: five of its sections said "not built in
 * this repository" and four of those modules had been built since.
 *
 * Three decisions:
 *
 * - **The empty weeks are drawn.** The canvas's own reading is "three weeks at zero", which
 *   means nothing unless the zeros are there -- and a series that omitted them, which is what
 *   a `GROUP BY` returns if nobody fills the gaps, draws a member who trained steadily.
 * - **No reading of the chart is offered.** The canvas prints a sentence under it: "the drop
 *   starts the week after his last PT session, not the week his payment failed". Relating a
 *   gap to a cause needs a module that reasons about it, and a plausible sentence written
 *   here would be the Command Center's withheld interpretation panel in a worse place.
 * - **Lifetime is beside the gap on purpose.** Nineteen days reads differently against two
 *   hundred visits than against six, which is why the canvas draws all three figures.
 */
async function AttendanceTab({ personId, locale }: { personId: string; locale: Locale }) {
  const text = (key: MessageKey) => t(locale, key);
  // **The tenant's numerals rather than a constant** -- ADR-0015. Every count, date and time
  // on this page follows `localization.numerals`; money does not, and `MoneyValue` carries no
  // `numbering` prop at all so that exception is the component's rule rather than this page's
  // to remember. One read for the whole render: `conventions()` is React's per-request memo
  // and the layout starts it, so this costs no round trip of its own.
  const numbering = await numerals();
  const may = await gate("access.zone.read");
  if (!may.allowed) {
    return <Banner severity="info">{text(gateMessage(may))}</Banner>;
  }
  let seen: Awaited<ReturnType<typeof readAttendance>>;
  try {
    seen = await readAttendance(personId);
  } catch {
    return <Banner severity="attention">{text("error.unexpected")}</Banner>;
  }

  const peak = Math.max(1, ...seen.by_week.map((week) => week.entries));
  const count = (value: number) => (
    <span className="data" dir="ltr">{formatInteger(value, numbering)}</span>
  );

  return (
    <section className="ds-panel">
      <div className="ds-panel-head">
        <h2 className="ds-panel-title">{text("member.tabAttendance")}</h2>
      </div>
      <div className="ds-panel-body">
        <MetricRow label={text("member.tabAttendance")}>
          <MetricCell
            label={text("attendance.sinceLast")}
            {...(seen.days_since === null
              ? {
                  freshness: "unavailable" as const,
                  unavailableBecause: text("member.neverVisited"),
                }
              : {
                  value: (
                    <span className="data" dir="ltr">
                      {fill(locale, "attendance.days", { count: seen.days_since }, numbering)}
                    </span>
                  ),
                  comparison: seen.last_location ?? undefined,
                })}
          />
          <MetricCell
            label={text("attendance.weeklyAvg")}
            {...(seen.entries_per_week === null
              ? {
                  freshness: "unavailable" as const,
                  unavailableBecause: text("member.neverVisited"),
                }
              : {
                  value: <span className="data" dir="ltr">{seen.entries_per_week}</span>,
                  comparison: fill(locale, "attendance.overWeeks", { count: seen.weeks }, numbering),
                })}
          />
          <MetricCell label={text("attendance.lifetime")} value={count(seen.lifetime_entries)} />
        </MetricRow>

        <h3 id="attendance-chart">
          {fill(locale, "attendance.perWeek", { count: seen.chart_weeks }, numbering)}
        </h3>
        {/* **The canvas's shape, with the figures still reachable.** It draws twelve vertical
            bars about a hundred pixels tall with the two ends of the axis labelled; a row per
            week was the same data at three times the height, on a tab that is one of six.
            Each bar carries its week and its count as text for a screen reader, because a bar
            is a colour-and-length signal and §15's rule -- nothing carries meaning alone --
            is what the figures are for. The zero weeks are drawn, because "three weeks at
            zero" is the canvas's own reading of this chart. */}
        <ol className="ds-weekbars" aria-labelledby="attendance-chart">
          {seen.by_week.map((week) => (
            <li key={week.starts_on} className="ds-weekbar">
              <span
                className="ds-weekbar-fill"
                style={{ blockSize: `${Math.round((week.entries / peak) * 100)}%` }}
                aria-hidden="true"
              />
              <span className="ds-visually-hidden">
                {week.starts_on}: {formatInteger(week.entries, numbering)}
              </span>
            </li>
          ))}
        </ol>
        <p className="ds-weekbars-axis">
          <span className="data" dir="ltr">{seen.by_week[0]?.starts_on}</span>
          <span className="data" dir="ltr">
            {seen.by_week[seen.by_week.length - 1]?.ends_on}
          </span>
        </p>
        <p className="ds-note">{text("attendance.noReading")}</p>

        <h3 id="attendance-recent">{text("attendance.recent")}</h3>
        {seen.recent.length === 0 ? (
          <Banner severity="info">{text("member.neverVisited")}</Banner>
        ) : (
          <dl className="facts" aria-labelledby="attendance-recent">
            {seen.recent.map((visit, index) => (
              <div key={`${visit.on}-${index}`} style={{ display: "contents" }}>
                <dt className="muted data" dir="ltr">{visit.on}</dt>
                <dd style={{ margin: 0 }}>
                  {visit.location_name}
                  {" \u00b7 "}
                  <span className="data" dir="ltr">{visit.at}</span>
                  {visit.credential_kind === null ? null : (
                    <>
                      {" \u00b7 "}
                      {/* The word, not the column's value: the canvas reads "card", not
                          `nfc_card`, and a stored value rendered as a label is Latin letters
                          in the middle of an Arabic line. */}
                      {credentialKindName(visit.credential_kind) === null ? (
                        <span className="data" dir="ltr">{visit.credential_kind}</span>
                      ) : (
                        text(credentialKindName(visit.credential_kind) as MessageKey)
                      )}
                    </>
                  )}
                </dd>
              </div>
            ))}
          </dl>
        )}
        <p className="ds-note">{text("attendance.credentialNote")}</p>
      </div>
    </section>
  );
}

async function AccessTab({ personId, locale }: { personId: string; locale: Locale }) {
  // **The tenant's numerals** -- ADR-0015, one read for the whole render.
  const numbering = await numerals();
  const text = (key: MessageKey) => t(locale, key);
  const may = await gate("access.credential.read");
  if (!may.allowed) {
    return (
      <Banner severity="info">
        {text(gateMessage(may))}
      </Banner>
    );
  }
  let held: Awaited<ReturnType<typeof readCredentials>>;
  try {
    held = await readCredentials(personId);
  } catch {
    return <Banner severity="attention">{text("error.unexpected")}</Banner>;
  }
  return (
    <section className="ds-panel">
      <div className="ds-panel-head">
        <h2 className="ds-panel-title">{text("member.tabAccess")}</h2>
      </div>
      <div className="ds-panel-body">
        {held.credentials.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>{text("member.noCredentials")}</p>
        ) : (
          <dl className="facts">
            {held.credentials.map((credential) => (
              <Fact
                key={credential.credential_id}
                label={
                  credentialKindName(credential.kind) === null
                    ? credential.kind
                    : text(credentialKindName(credential.kind) as MessageKey)
                }
              >
                {credential.state}
                {credential.expires_at
                  ? <> {"· "}<span className="data" dir="ltr">
                    {credential.expires_at.slice(0, 10)}
                  </span></>
                  : null}
                {/* **ADM-ACC-03's second line, and it is what makes the row actionable.**
                    The canvas draws "Issued 4 Mar 2024 · 214 uses" and "last used 31 Jul".
                    A card issued two years ago and never presented is one somebody should
                    cancel; one used this morning is not, and `state` reads `active` for
                    both. Never presented is said rather than counted as zero uses "long
                    ago", because only the date tells a new card from a dead one. */}
                <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
                  {text("credential.issued")}{" "}
                  <span className="data" dir="ltr">{credential.issued_at.slice(0, 10)}</span>
                  {" \u00b7 "}
                  {credential.last_used_at === null
                    ? text("credential.neverUsed")
                    : (
                      <>
                        {fill(locale, "credential.uses", { count: credential.uses }, numbering)}
                        {" \u00b7 "}
                        {text("credential.lastUsed")}{" "}
                        <span className="data" dir="ltr">
                          {credential.last_used_at.slice(0, 10)}
                        </span>
                      </>
                    )}
                </div>
              </Fact>
            ))}
          </dl>
        )}
      </div>
      {/* The canvas's own note under this block: "Biometric data is never displayed or
          exportable — only whether enrolment exists." This build goes further by
          construction: there is no column a credential's value could be read from, because
          the stored value is a SHA-256 digest and the read never returns it. */}
      <p className="ds-panel-note">{text("member.credentialNote")}</p>
      {/* **The canvas draws a last-four and this build has none**, which is the stronger
          position rather than a gap to apologise for: `credential_digest` is a SHA-256 of
          the presented secret and no column ever held a partial card number. Said out loud,
          because a reader looking for "Card ···8841" and finding a kind would otherwise
          assume the screen lost it. */}
      <p className="ds-panel-note">{text("credential.noLastFour")}</p>
      {/* ADM-ACC-03's two actions are writes: issuing a card and reporting one lost both
          need `devices.credential.write`, a stepped-up financial-class permission with no
          form in this build. A button that answered "not permitted" is worse than one that
          is absent -- ADM-MEM-05's rule. */}
      <p className="ds-panel-note">{text("credential.noWrites")}</p>
    </section>
  );
}

function Notes({ record, locale }: { record: Member360; locale: Locale }) {
  const text = (key: MessageKey) => t(locale, key);
  return (
    <section className="ds-panel">
      <div className="ds-panel-head">
        <h2 className="ds-panel-title">{text("member.notes")}</h2>
      </div>
      <div className="ds-panel-body">
        {record.notes.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>{text("member.noNotes")}</p>
        ) : (
          <ul className="stack" style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
            {record.notes.map((note) => (
              <li key={note.note_id}>
                <NoteBody note={note} locale={locale} />
                <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
                  {note.note_class}
                  {" · "}
                  <span className="data" dir="ltr">{utcStamp(note.recorded_at)}</span>
                  {note.withdrawn_at ? ` · ${text("member.noteWithdrawn")}` : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
      {/* A note is insert-only and so is a timeline entry: a correction is a new note and a
          retraction leaves the original visible, which is what makes a note usable in the
          dispute it exists for -- and why both survive an erasure. */}
      <p className="ds-panel-note">{text("member.notesInsertOnly")}</p>
    </section>
  );
}

function IdentityPanel({ person, locale, nameWithheld, remedy }: {
  person: Person; locale: Locale;
  // Which sentence a withheld identity field gets, and whether there is a remedy to offer:
  // the page decides both from the gate's answer, because only the page knows. They travel
  // together rather than one being re-derived from the other -- comparing `nameWithheld`
  // against a key would be the same test spelled a second way.
  nameWithheld: MessageKey;
  remedy: WithheldRemedy;
}) {
  const text = (key: MessageKey) => t(locale, key);
  // **The remedy, where the refusal is.** An identity field is withheld because this session
  // is assurance level 1 and `member.identity.read` is a financial action -- which is a thing
  // the reader can fix, unlike the health class, where nobody in this build can.
  const identityWithheld =
    isWithheld(person.legal_name)
    || isWithheld(person.preferred_name)
    || isWithheld(person.date_of_birth);
  return (
    <section className="ds-panel">
      <div className="ds-panel-head">
        <h2 className="ds-panel-title">{text("member.identity")}</h2>
      </div>
      <div className="ds-panel-body">
        <dl className="facts">
          <Fact label={text("member.legalName")}>
            {isWithheld(person.legal_name)
              ? <Withheld locale={locale} reason={nameWithheld} />
              : person.legal_name}
          </Fact>
          <Fact label={text("member.dateOfBirth")}>
            {person.date_of_birth === null
              ? "—"
              : isWithheld(person.date_of_birth)
                ? <Withheld locale={locale} reason={nameWithheld} />
                : <span className="data" dir="ltr">{person.date_of_birth}</span>}
          </Fact>
        </dl>
        {/* **A custom field keeps its own list.** It is a tenant-declared field rather than
            a canonical identity column, and merging the two put three withheld markers in
            one `dl` -- which is exactly the scoping the people spec's own comment warns
            about: a marker belonging to a different field then satisfies an assertion about
            this one, and the mutation that pointed a health field at the step-up remedy
            goes uncaught. */}
        {person.custom_fields.length === 0 ? null : (
          <dl className="facts">
            {person.custom_fields.map((field) => (
              <Fact key={field.field_key} label={field.display_name}>
                {/* **Three classes, three remedies.** Health needs a level this screen
                    cannot reach, contact needs a permission no step-up gives, and identity
                    is the one the gate's answer decides -- so the two-way split that was
                    here sent a contact field's reader to a step-up that lifts nothing, and
                    told a reader who holds no identity read that one would. */}
                {field.redacted || isWithheld(field.value)
                  ? <Withheld
                    locale={locale}
                    reason={
                      field.sensitivity === "health" || field.sensitivity === "biometric"
                        ? "member.withheldHealth"
                        : field.sensitivity === "contact"
                          ? "member.withheldContact"
                          : nameWithheld
                    }
                  />
                  : field.value}
              </Fact>
            ))}
          </dl>
        )}
        {/* **The offer, only where it is one.** This rendered for anybody whose identity
            fields were withheld, which includes a reader who holds `member.identity.read` at
            no assurance at all -- so a front desk was handed a link that costs a single-use
            recovery code and lifts nothing. The marker above says the fact; this says the
            remedy, and only when there is one. */}
        {identityWithheld && remedy === "step_up" ? (
          <p style={{ margin: 0 }}>
            <Link
              // **The action, so the prompt can name it.** ADM-AUTH-02's own line is
              // "You're about to <the action>", and a re-authentication page that says only
              // "this action needs a stronger sign-in" asks somebody to remember what they
              // clicked. The step-up page looks the name up in MOD-008's catalogue rather
              // than echoing it, so a link cannot put prose on that page.
              href={`/step-up?for=financial&action=member.identity.read&next=${
                encodeURIComponent(`/people/${person.person_id}`)}`}
            >
              {text("member.raiseSession")}
            </Link>
          </p>
        ) : null}
      </div>
      {/* **An unknown birth date is not a minor**, which is MOD-014's own uncomfortable and
          correct direction: treating every undated person as one would make a guardian
          relationship mandatory before anybody could read the record of a member who never
          gave a birthday, which is most leads. */}
      <p className="ds-panel-note">
        {person.is_minor ? text("member.minor") : text("member.notMinor")}
      </p>
    </section>
  );
}

function ContactPanel({ person, locale }: { person: Person; locale: Locale }) {
  const text = (key: MessageKey) => t(locale, key);
  return (
    <section className="ds-panel">
      <div className="ds-panel-head">
        <h2 className="ds-panel-title">{text("member.contacts")}</h2>
      </div>
      <div className="ds-panel-body">
        {person.contact_points.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>{text("member.noContacts")}</p>
        ) : (
          <dl className="facts">
            {person.contact_points.map((contact) => (
              <Fact
                key={contact.contact_point_id}
                label={contact.kind + (contact.is_primary ? ` · ${text("member.primary")}` : "")}
              >
                {isWithheld(contact.value_raw)
                  ? <Withheld locale={locale} reason="member.withheldContact" />
                  : <span className="data" dir="ltr">{contact.value_raw}</span>}
                {" · "}
                {/* **A verification is recorded, not performed**: nothing here sends a code
                    or reads a reply, so the row says a named actor asserted it at a time. */}
                <span className="muted">
                  {contact.verified_at ? text("member.verified") : text("member.unverified")}
                </span>
              </Fact>
            ))}
          </dl>
        )}
        {person.tags.length > 0 ? (
          <p style={{ margin: 0 }}>
            <span className="muted">{text("member.tags")}</span>{": "}
            {person.tags.map((tag) => tag.display_name).join(", ")}
          </p>
        ) : null}
        {person.relationships.length > 0 ? (
          <dl className="facts">
            {person.relationships.map((relationship) => (
              <Fact key={relationship.relationship_id} label={relationship.kind}>
                <span className="data" dir="ltr">
                  {relationship.started_on ?? "—"} → {relationship.ended_on ?? "—"}
                </span>
              </Fact>
            ))}
          </dl>
        ) : null}
      </div>
    </section>
  );
}

function NoteBody({ note, locale }: { note: Note; locale: Locale }) {
  if (note.redacted || isWithheld(note.body)) {
    return (
      <Withheld
        locale={locale}
        reason={
          note.visibility_class === "health" || note.visibility_class === "biometric"
            ? "member.withheldHealth"
            : "member.withheldIdentity"
        }
      />
    );
  }
  return <span>{note.body}</span>;
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="muted">{label}</dt>
      <dd style={{ margin: 0 }}>{children}</dd>
    </>
  );
}

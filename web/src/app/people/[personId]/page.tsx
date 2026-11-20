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
import { ApiError, currentSession, gate, failureMessage } from "@/lib/api";
import { listMembers } from "@/lib/members-reads";
import {
  classifyEvent,
  isTimelineFilter,
  readCredentials,
  TIMELINE_FILTERS,
  type TimelineFilterKey,
} from "@/lib/member-record";
import {
  isWithheld,
  readMember360,
  splitComposed,
  splitSections,
  type Member360,
  type Note,
  type Person,
  type TimelineEntry,
} from "@/lib/people";
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
 * - **Five of the nine tabs are not drawn**, because attendance per person, coaching,
 *   bookings per person, purchases and documents each need a module or a read this build does
 *   not have. They are named at the foot with the reason, which is ADM-MEM-05's rule applied
 *   to a tab: a control that opens an empty panel says the member has no bookings.
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
 * stronger sign-in, which the step-up link offers; a health field cannot be read by anybody in
 * this build, because `member.health.read` is `biometric_sensitive`, which maps to assurance
 * level 3, which needs a hardware authenticator MOD-007 cannot verify.
 */

const TABS = ["overview", "membership", "billing", "access", "notes"] as const;
type TabKey = (typeof TABS)[number];

const TAB_LABEL: Record<TabKey, MessageKey> = {
  overview: "member.tabOverview",
  membership: "member.tabMembership",
  billing: "member.tabBilling",
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
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);
  const tabParam = typeof query.tab === "string" ? query.tab : undefined;
  const tab: TabKey = isTab(tabParam) ? tabParam : "overview";
  const filterParam = typeof query.filter === "string" ? query.filter : undefined;
  const filter: TimelineFilterKey = isTimelineFilter(filterParam) ? filterParam : "all";

  if (!(await currentSession())) redirect("/login");

  const may = await gate("people.person.read");
  if (!may.allowed) {
    return (
      <Banner severity="info">
        {may.reachable ? text("gate.denied") : text("gate.unreachable")}
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
                shown: formatInteger(queue.people.length, "latn"),
                total: formatInteger(queue.total, "latn"),
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
          />
        ) : null}
        {tab === "membership" || tab === "billing" ? (
          <MembershipPanels personId={personId} locale={locale} only={tab} />
        ) : null}
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
              {absent.map(([section, why]) => (
                <Fact key={section} label={section}>
                  <span className="muted">{why}</span>
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
              {formatInteger(record.consent_record_count, "latn")}
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
}: {
  record: Member360;
  facts: Awaited<ReturnType<typeof memberFacts>>;
  locale: Locale;
  personId: string;
  filter: TimelineFilterKey;
}) {
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
              : fill(locale, "member.timelineCount", { count: record.timeline.length })
          }
        >
          {shown.map((entry) => (
            <Entry key={entry.entry_id} entry={entry} locale={locale} />
          ))}
        </Timeline>

        <div className="ds-record-side">
          <IdentityPanel person={record.person} locale={locale} />
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
async function AccessTab({ personId, locale }: { personId: string; locale: Locale }) {
  const text = (key: MessageKey) => t(locale, key);
  const may = await gate("access.credential.read");
  if (!may.allowed) {
    return (
      <Banner severity="info">
        {text(may.reachable ? "gate.denied" : "gate.unreachable")}
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
              <Fact key={credential.credential_id} label={credential.kind}>
                {credential.state}
                {credential.expires_at
                  ? <> {"· "}<span className="data" dir="ltr">
                    {credential.expires_at.slice(0, 10)}
                  </span></>
                  : null}
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

function IdentityPanel({ person, locale }: { person: Person; locale: Locale }) {
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
              ? <Withheld locale={locale} reason="member.withheldIdentity" />
              : person.legal_name}
          </Fact>
          <Fact label={text("member.dateOfBirth")}>
            {person.date_of_birth === null
              ? "—"
              : isWithheld(person.date_of_birth)
                ? <Withheld locale={locale} reason="member.withheldIdentity" />
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
                {field.redacted || isWithheld(field.value)
                  ? <Withheld
                    locale={locale}
                    reason={
                      field.sensitivity === "health" || field.sensitivity === "biometric"
                        ? "member.withheldHealth"
                        : "member.withheldIdentity"
                    }
                  />
                  : field.value}
              </Fact>
            ))}
          </dl>
        )}
        {identityWithheld ? (
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
                  ? <Withheld locale={locale} reason="member.withheldIdentity" />
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

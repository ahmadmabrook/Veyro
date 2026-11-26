import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { PageHeader } from "@/components/ds/page-header";
import { NotYet } from "@/components/not-yet";
import { MetricCell, MetricRow } from "@/components/ds/metric-cell";
import { Timeline, TimelineItem } from "@/components/ds/timeline";
import { Withheld } from "@/components/withheld";
import { fill, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gateAll, gateMessage, gateVerdict } from "@/lib/api";
import { numerals } from "@/lib/display";
import { presentation } from "@/lib/preferences";
import {
  caseStatusWord, compactDuration, priorityWord, sheetControls, sourceWord,
  stateWord, subjectKindWord, word,
  type AttentionItem,
} from "@/lib/tasks";
import { readAttentionItem, readWorkload } from "@/lib/tasks-reads";
import { readNames } from "@/lib/desk-reads";
import { isWithheld } from "@/lib/people";
import { dayLabel, timeOfDay, utcStamp } from "@/lib/time";

import { AssignForm, ResolveForm, ReturnForm, SnoozeForm } from "./forms";

/**
 * ADM-CC-06 · ATTENTION ITEM DETAIL — "Where an exception gets resolved."
 *
 * **The canvas draws this as a side sheet over the Command Center and this is a page**, which
 * is the one deviation worth naming first. Two reasons, and the second is the real one:
 *
 * - This app has no `SideSheet` component and the design does not specify one. It is named in
 *   Batch F's component list and nothing in the sources gives its anatomy or measurements, so
 *   building one would be inventing the part of the design that is missing rather than
 *   implementing the part that is there. `Inspector` is pattern 02's two-pane shape and is
 *   drawn for a list beside a record, which is not a sheet over a queue.
 * - **Nothing routes into it from the Command Center**, because that queue is computed live
 *   from MOD-017's collections, MOD-019's staffing and MOD-022's doors rather than filed as
 *   `tsk_cases` rows. So there is no originating row for an Esc to return focus to, and the
 *   canvas's keyboard contract has nothing to bind. Deciding which computed item becomes a
 *   case is a product decision about what an exception *is*, and it is not settled here.
 *
 * What the canvas specifies and this screen does keep: the four header facts, the records the
 * item is about, the history of what has already happened, and the five states — each with
 * **every action visible** and only some of them live, which is its own most specific rule.
 *
 * **The age is the server's `took_seconds` where the item is settled and derived here where
 * it is not**, and the distinction matters: a resolved item's elapsed time is a fact about the
 * past that cannot move, and an open item's age is a fact about now. The first comes from the
 * read; the second is this page's only arithmetic and it is one subtraction.
 *
 * **The affected records carry a reference and not a name.** The canvas links each to its
 * member; `tasks.case.read` is routine, so a name here would be a way around the permission
 * that guards a person's record — MOD-010's `events.event.read` finding. A `member` reference
 * links to the record, which asks MOD-014's own gate; a `lead`, an `asset` or a `workflow`
 * resolves against nothing in this build and says so rather than looking verified.
 */
export default async function AttentionItemPage({
  params,
}: {
  params: Promise<{ caseId: string }>;
}) {
  const { locale } = await presentation();
  // **The tenant's numerals** -- ADR-0015. Every quantity on this page follows
  // `localization.numerals`; an identifier does not, and neither does money. One read for the
  // whole render: `conventions()` is React's per-request memo and the layout starts it.
  const numbering = await numerals();
  const text = (key: MessageKey) => t(locale, key);
  const { caseId } = await params;

  if (!(await currentSession())) redirect("/login");

  const [mayRead, mayWrite, mayPeople] = await gateAll([
    "tasks.case.read", "tasks.case.write", "people.person.read",
  ] as const);

  if (!mayRead.allowed) {
    const verdict = gateVerdict(mayRead);
    return (
      <Shell locale={locale}>
        <Banner severity={verdict === "gate_failed" ? "critical" : "info"}>
          {verdict === "denied" ? text("case.refused") : text(gateMessage(mayRead))}
        </Banner>
      </Shell>
    );
  }

  let item: AttentionItem | null = null;
  let missing = false;
  try {
    item = await readAttentionItem(caseId);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 404 || error.status === 422) missing = true;
  }

  if (missing || item === null) {
    return (
      <Shell locale={locale}>
        <Banner severity={missing ? "info" : "critical"}>
          {text(missing ? "case.notFound" : "error.unexpected")}
        </Banner>
      </Shell>
    );
  }

  // **The names the canvas asks for, composed through MOD-014's own gate.** "THE SIX RECORDS
  // · EACH LINKS TO ITS MEMBER", and this read carries references rather than names because
  // `tasks.case.read` is routine. A *surface* has no such restriction and every reason to
  // compose, which is FD-06's roster and the Member 360 before it: one batched request for
  // every row, masked by the module that owns the name. A reader without the permission gets
  // the reference, which is still enough to say which record this is.
  //
  // **And whether this reader is anybody**, which decides one control: "Assign to me" needs a
  // person, and an identity with no `ppl_identity_links` row holds the permission and is
  // nobody. The server refuses it by name; offering a button that will be refused is FD-06's
  // own finding, so the flag turns the refusal into a control that says why.
  // **The assignee is in the same batch**, because "OWNER · Nadia" is a name on the canvas
  // and a bare uuid is the thing this app has a recorded finding about one screen over: a
  // `role_key` printed beside its own display name. One request answers the records and the
  // owner together.
  const members = [
    ...item.affected
      .filter((record) => record.affected_kind === "member")
      .map((record) => record.affected_id),
    ...(item.assignee_person_id === null ? [] : [item.assignee_person_id]),
  ];
  const [names, workload] = await Promise.all([
    mayPeople.allowed && members.length > 0
      ? readNames(members).catch(() => new Map())
      : Promise.resolve(new Map()),
    mayWrite.allowed ? readWorkload().catch(() => null) : Promise.resolve(null),
  ]);
  const nobody = workload?.mine_is_zero_without_a_person_record ?? false;

  const controls = sheetControls(item.state);
  const now = new Date();
  // The header's AGE: the recorded elapsed time where it is settled, the live one where it is
  // not. Two different facts and only one of them can move.
  const age = item.took_seconds ?? Math.max(
    0, Math.floor((now.getTime() - Date.parse(item.opened_at)) / 1000));
  // The commonest deferral is about a week out, so the form opens there rather than empty.
  const inAWeek = new Date(now.getTime() + 7 * 86_400_000).toISOString().slice(0, 10);

  return (
    <Shell locale={locale} item={item}>
      {/* The four facts the canvas prints under the headline. `MetricCell` is the design's own
          component for a labelled figure, which is what each of these is. */}
      <MetricRow label={text("case.title")}>
        <MetricCell
          label={text("case.factOwner")}
          value={
            item.state === "mine" ? text("case.assignedToYou")
              : item.assignee_person_id === null ? text("case.unassigned")
              : memberLabel(locale, names.get(item.assignee_person_id))
          }
        />
        <MetricCell label={text("case.factAge")} value={compactDuration(age)} />
        <MetricCell
          label={text("case.factAffected")}
          value={fill(locale, "case.affectedCount", { count: item.affected_count }, numbering)}
        />
        <MetricCell
          label={text("case.factSource")}
          value={word(locale, sourceWord(item.source), item.source)}
        />
      </MetricRow>

      {/* **The state is a sentence, not only a badge.** `StatusBadge`'s vocabulary is closed
          over membership, payment, booking and access, and an item's state is none of them --
          the nearest word, `Cancelled`, is a membership state, and putting a membership word
          on an exception is how two screens come to spell one thing two ways. So it is marked
          text with its own five words, which is the same judgement the account page's passkey
          state records. */}
      <p className="ds-note">
        <strong>{word(locale, stateWord(item.state), item.state)}</strong>
        {item.state === "someone_else" ? ` — ${text("case.handling")}` : ""}
        {item.state === "snoozed" && item.snoozed_until !== null
          ? ` — ${fill(locale, "case.snoozedUntil", {
              when: utcStamp(item.snoozed_until) })}`
          : ""}
        {item.state === "resolved" && item.resolved_at !== null
          ? ` — ${fill(locale, "case.resolvedAt", {
              when: utcStamp(item.resolved_at) })} · ${
              fill(locale, "case.took", { took: compactDuration(age) })}`
          : ""}
      </p>

      {/* The deferral's and the resolution's own prose, masked for anybody who could not have
          written it: it is free text about a person, and MOD-019 learned that a reason column
          is where a health fact goes in practice. Marked rather than dropped -- an absent
          field reads as "there was nothing here", the one answer that is always wrong. */}
      {item.snooze_reason !== null ? (
        <p className="ds-note">
          {text("case.reasonLabel")}:{" "}
          {item.reason_masked
            ? <Withheld locale={locale} reason="case.reasonsMasked" />
            : item.snooze_reason}
        </p>
      ) : null}
      {item.resolution_reason !== null ? (
        <p className="ds-note">
          {text("case.resolveReasonLabel")}:{" "}
          {item.reason_masked
            ? <Withheld locale={locale} reason="case.reasonsMasked" />
            : item.resolution_reason}
        </p>
      ) : null}

      <section className="page-section" aria-labelledby="case-records">
        <h2 id="case-records">{text("case.recordsHeading")}</h2>
        {item.affected.length === 0 ? (
          <p className="muted">{text("case.recordsEmpty")}</p>
        ) : (
          <ul className="ds-report-list">
            {item.affected.map((record) => (
              <li
                key={`${record.affected_kind}:${record.affected_id}`}
                className="ds-report-row"
              >
                <div className="ds-report-main">
                  {record.affected_kind === "member" ? (
                    // **Still a link where the name is withheld**, which is this app's own
                    // hard-won rule: a marker rendered *instead of* the link made the members
                    // and staff lists dead ends on a receptionist's own credential, found
                    // twice by an independent tester against the same cell.
                    <Link
                      className="ds-report-name"
                      href={`/people/${record.affected_id}`}
                    >
                      {memberLabel(locale, names.get(record.affected_id))}
                    </Link>
                  ) : (
                    <span className="ds-report-name">
                      {word(locale, subjectKindWord(record.affected_kind),
                            record.affected_kind)}
                    </span>
                  )}
                  <p className="ds-report-summary">
                    <span className="data" dir="ltr">{record.affected_id}</span>
                    {/* A kind nothing in this build resolves is a claim rather than a
                        reference, and the read says which -- so an id that looks verified
                        is not presented as one. */}
                    {record.subject_is_a_recorded_claim
                      ? ` · ${text("tasks.subjectClaim")}`
                      : ""}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
        {item.withdrawn.length > 0 ? (
          <>
            <h3>{text("case.withdrawnHeading")}</h3>
            <ul className="ds-note">
              {item.withdrawn.map((record) => (
                <li key={`${record.affected_kind}:${record.affected_id}`}>
                  <span className="data" dir="ltr">{record.affected_id}</span>
                  {" — "}
                  {record.withdraw_reason === null
                    ? "—"
                    : item.reason_masked
                      ? <Withheld locale={locale} reason="case.reasonsMasked" />
                      : record.withdraw_reason}
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </section>

      {/* **No heading of its own, because `Timeline` draws one with the same words.** A
          visible heading over a component that repeats it is the sentence said twice, and a
          *hidden* one is worse: a sighted reader does not see it and a screen-reader user
          hears it twice, which is exactly the `DataGrid` caption finding. The member record
          renders its own timeline with no wrapper heading for the same reason. */}
      <section className="page-section" aria-label={text("case.historyHeading")}>
        {item.entries.length === 0 ? (
          <p className="muted">{text("case.historyEmpty")}</p>
        ) : (
          <Timeline label={text("case.historyHeading")}>
            {item.entries.map((entry, index) => (
              <TimelineItem
                key={`${entry.occurred_at}-${index}`}
                time={timeOfDay(entry.occurred_at)}
                day={dayLabel(entry.occurred_at, now)}
                tone="system"
                title={entry.summary}
                // **The zone is on the row, because the gutter's clock is UTC.** Ten sites
                // in this app rendered a bare wall time with no zone on it, which was merely
                // ambiguous while every screen did it and became misleading the day one
                // started converting. A case belongs to the tenant rather than to a site, so
                // there is nothing here to convert into.
                meta={`${utcStamp(entry.occurred_at)} · ${entry.entry_kind} · ${
                  text("case.entryBy")} ${entry.recorded_by}`}
              />
            ))}
          </Timeline>
        )}
      </section>

      <section className="page-section" aria-labelledby="case-actions">
        <h2 id="case-actions">{text("case.actionsHeading")}</h2>

        {/* The note explaining why these controls are inert has gone: the state line above
            already says somebody else is handling this and that every action does nothing
            until you take it over, which is the same sentence at the point of use. */}
        {item.state === "resolved" ? (
          <Banner severity="info">{text("case.resolvedNoReopen")}</Banner>
        ) : null}

        {mayWrite.allowed ? (
          <div className="stack">
            {nobody ? <Banner severity="info">{text("case.writeNobody")}</Banner> : null}
            {controls.assignToMe || item.state === "someone_else" ? (
              <AssignForm
                locale={locale} caseId={item.case_id}
                label={controls.takeOver ? "case.takeOver" : "case.assignToMe"}
                release={false}
                live={(controls.assignToMe || controls.takeOver) && !nobody}
              />
            ) : null}
            {controls.release ? (
              <AssignForm
                locale={locale} caseId={item.case_id} label="case.release"
                release live
              />
            ) : null}
            {item.state !== "resolved" && item.state !== "snoozed" ? (
              <SnoozeForm
                locale={locale} caseId={item.case_id}
                live={controls.snooze} defaultDate={inAWeek}
              />
            ) : null}
            {item.state === "snoozed" ? (
              <ReturnForm
                locale={locale} caseId={item.case_id} live={controls.returnToQueue}
              />
            ) : null}
            {item.state !== "resolved" ? (
              <ResolveForm
                locale={locale} caseId={item.case_id} live={controls.resolve}
              />
            ) : null}
          </div>
        ) : (
          <Banner severity="info">{text("case.refused")}</Banner>
        )}

        {/* The canvas's secondary route, which this build has: MOD-017's dunning workspace. */}
        <p>
          <Link href="/payments/recovery">{text("case.openRecovery")}</Link>
        </p>
      </section>

      <NotYet
        locale={locale}
        items={["tasks.gapSideSheetLabel", "tasks.gapUndoLabel", "tasks.gapReopenLabel",
                "tasks.gapBatchLabel", "tasks.gapScopeLabel"]}
      />
    </Shell>
  );
}


/**
 * An affected member's name, the withheld marker, or the kind where there is no name to be had.
 *
 * Three cases rather than two: a reader without `people.person.read` gets no row from
 * `/people/names` at all, which is a different fact from a row whose name is masked -- the
 * first is "you may not ask" and the second is "you asked and this session cannot read
 * identity fields". Both leave the reference below, which is what identifies the record.
 */
function memberLabel(
  locale: Locale,
  person: { legal_name: string | null; preferred_name: string | null } | undefined,
): string {
  if (person === undefined) return t(locale, "tasks.subjectMember");
  const name = person.preferred_name ?? person.legal_name;
  if (name === null || isWithheld(name)) return t(locale, "member.withheld");
  return name;
}

function Shell({
  locale, item, children,
}: {
  locale: Locale;
  item?: AttentionItem;
  children: React.ReactNode;
}) {
  const text = (key: MessageKey) => t(locale, key);
  return (
    <div className="stack">
      <PageHeader
        title={item?.title ?? text("case.title")}
        figures={item === undefined ? undefined : (
          <>
            <span className="data" dir="ltr">{item.case_number}</span>
            {" · "}
            {fill(locale, "case.raised", { when: utcStamp(item.opened_at) })}
            {" · "}
            {word(locale, caseStatusWord(item.status), item.status)}
            {item.priority === "normal"
              ? ""
              : ` · ${word(locale, priorityWord(item.priority), item.priority)}`}
            {item.running_sla_clock_id === null ? "" : ` · ${text("case.hasClock")}`}
          </>
        )}
        actions={<Link href="/tasks">{text("case.backToTasks")}</Link>}
      />
      {children}
    </div>
  );
}

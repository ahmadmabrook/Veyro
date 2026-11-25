"use client";

import Link from "next/link";
import { useActionState, useEffect, useRef, useState } from "react";

import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { ChoiceChips } from "@/components/ds/choice-chips";
import { Field } from "@/components/ds/field";
import {
  CANCELLATION_REASONS, noticeDays, noticeKey,
  type CancellationPreview, type Remedy,
} from "@/lib/cancel-class";
import { fill, t, type Locale, type MessageKey, type Numbering } from "@/i18n/locale";

import { cancelClass, previewCancelClass } from "./cancel-actions";
import { IDLE, type CancelClassState } from "./cancel-state";

export type Destination = {
  session_id: string;
  display_name: string;
  date: string;
  time: string;
  staff: string | null;
  free: number;
};

/**
 * ADM-SCH-07 · CANCEL A CLASS. ADR-0016.
 *
 * **The remedy is the screen.** The canvas's own last sentence -- "Cannot commit without
 * choosing what the members get. A cancellation that notifies nobody is the most damaging
 * thing this screen could permit, so the notification is the action rather than a follow-up"
 * -- is why there is no bare cancel button here and why the consequence is read before it.
 *
 * **The consequence is the server's, re-read whenever the choice changes.** "6 places free ·
 * 12 would need to choose another" is a statement about one destination, so a panel left
 * behind from a previous choice is a figure a manager would act on; the answer carries what it
 * was about, so a reply about an edited choice is simply not the one on screen.
 *
 * **The message is one preview of many.** It is rendered here in the reader's own language
 * from the same catalogue every other screen uses, because the backend has none -- and the
 * sheet says each member gets it in theirs, which is the canvas's own note.
 */
export function CancelClassSheet({
  sessionId, displayName, startsAt, timezone, localDate, todayLocalDate,
  booked, waiting, destinations, locale, numbering, back,
}: {
  sessionId: string;
  displayName: string;
  startsAt: string;
  timezone: string;
  localDate: string;
  /** Today at the club, so the notice is counted in one frame. */
  todayLocalDate: string;
  booked: number;
  waiting: number;
  destinations: readonly Destination[];
  locale: Locale;
  numbering: Numbering;
  back: string;
}) {
  const text = (key: MessageKey) => t(locale, key);
  const [state, commit, committing] = useActionState<CancelClassState, FormData>(
    cancelClass, IDLE);
  const [peek, preview, peeking] = useActionState<CancelClassState, FormData>(
    previewCancelClass, IDLE);
  const [reason, setReason] = useState("");
  const [remedy, setRemedy] = useState<Remedy | "">("");
  const [destination, setDestination] = useState("");
  const asked = useRef<HTMLFormElement>(null);

  // **The consequence is asked for when the choice changes**, which is what makes the figures
  // the ones the reader is looking at. A `requestSubmit` on the hidden preview form rather
  // than a fetch, so the server action is the one path to the read -- the same shape
  // ADM-SCH-03's live clash check uses.
  useEffect(() => {
    if (remedy === "") return;
    if (remedy === "move" && destination === "") return;
    asked.current?.requestSubmit();
  }, [remedy, destination]);

  if (state.message === "done" && state.recorded !== null) {
    return (
      <section className="ds-panel" aria-labelledby="cancel-heading">
        <div className="ds-panel-head">
          <h2 id="cancel-heading" className="ds-panel-title">
            {text("cancelClass.doneTitle")}
          </h2>
        </div>
        <div className="ds-panel-body stack">
          <Banner severity="info">
            {fill(locale, "cancelClass.doneCounts", {
              released: state.recorded.released,
              waiting: state.recorded.waitlistLapsed,
            }, numbering)}
          </Banner>
          {state.recorded.moved > 0 ? (
            <p style={{ margin: 0 }}>
              {fill(locale, "cancelClass.doneMoved",
                { count: state.recorded.moved }, numbering)}
            </p>
          ) : null}
          {state.recorded.credited > 0 ? (
            <p style={{ margin: 0 }}>
              {fill(locale, "cancelClass.doneCredited",
                { count: state.recorded.credited }, numbering)}
            </p>
          ) : null}
          {state.recorded.mustChoose.length > 0 ? (
            <Banner severity="attention">
              {fill(locale, "cancelClass.doneMustChoose",
                { count: state.recorded.mustChoose.length }, numbering)}
            </Banner>
          ) : null}
          {/* **The one thing this screen cannot do**, said where the canvas puts the
              notification: MOD-013 authors a message and sends nothing, and before that the
              address is a permission this command does not hold. */}
          <Banner severity="attention">{text("cancelClass.nobodyTold")}</Banner>
          <p style={{ margin: 0 }}><Link href={back}>{text("cancelClass.backToSession")}</Link></p>
        </div>
      </section>
    );
  }

  const answer: CancellationPreview | null =
    peek.previewFor !== null
      && peek.previewFor.remedy === remedy
      && peek.previewFor.toSessionId === (remedy === "move" ? destination : "")
      ? peek.preview
      : null;
  const chosen = destinations.find((option) => option.session_id === destination) ?? null;
  const notice = noticeKey(noticeDays(localDate, todayLocalDate));

  return (
    <section className="ds-panel" aria-labelledby="cancel-heading">
      <div className="ds-panel-head">
        <h2 id="cancel-heading" className="ds-panel-title">
          {fill(locale, "cancelClass.title", { name: displayName })}
        </h2>
        <Link href={back} className="ds-panel-action">{text("cancelClass.keepIt")}</Link>
      </div>
      <div className="ds-panel-body stack">
        {/* The canvas's own sub-line: "18 booked, 3 on the waitlist. This is tomorrow." */}
        <p className="muted" style={{ margin: 0 }}>
          {fill(locale, "cancelClass.counts", { booked, waiting }, numbering)}
          {" "}
          {notice === "cancelClass.noticeDays"
            ? fill(locale, notice,
              { count: noticeDays(localDate, todayLocalDate) }, numbering)
            : text(notice)}
        </p>

        {/* **The read form, hidden and submitted by the choices above it.** It carries the
            same three values the commit does, so the figures and the act cannot be about
            different things. */}
        <form ref={asked} action={preview} hidden>
          <input type="hidden" name="session_id" value={sessionId} />
          <input type="hidden" name="cancellation_reason" value={reason} />
          <input type="hidden" name="remedy" value={remedy} />
          <input type="hidden" name="to_session_id" value={destination} />
        </form>

        <form action={commit} className="stack">
          <input type="hidden" name="session_id" value={sessionId} />
          <input type="hidden" name="remedy" value={remedy} />
          <input type="hidden" name="to_session_id" value={destination} />

          <Field
            id="cancellation_reason"
            name="cancellation_reason"
            type="select"
            label={text("cancelClass.why")}
            description={text("cancelClass.whyGoesIntoTheMessage")}
            required
            {...(state.missing.reason ? {
              message: { kind: "error" as const, text: text("cancelClass.whyNeeded") },
            } : {})}
          >
            {/* The control swap the shell provides for exactly this, because the chosen
                reason is rendered into the message preview as it is picked. */}
            <select
              id="cancellation_reason" name="cancellation_reason"
              className="ds-field-input" value={reason}
              onChange={(event) => setReason(event.target.value)}
            >
              <option value="">{text("cancelClass.whyChoose")}</option>
              {CANCELLATION_REASONS.map((code) => (
                <option key={code} value={code}>
                  {text(`cancelClass.reason.${code}` as MessageKey)}
                </option>
              ))}
            </select>
          </Field>

          <ChoiceChips
            name="remedy_choice"
            legend={fill(locale, "cancelClass.whatTheyGet", { count: booked }, numbering)}
            single
            required
            options={[
              { value: "move", label: text("cancelClass.remedyMove") },
              { value: "credit", label: text("cancelClass.remedyCredit") },
            ]}
            onChange={(values) => setRemedy((values[0] as Remedy | undefined) ?? "")}
            {...(state.missing.remedy ? { note: (
              <span className="field-message field-message-error">
                {text("cancelClass.remedyNeeded")}
              </span>
            ) } : {})}
          />

          {remedy === "move" ? (
            <Field
              id="destination"
              name="destination_choice"
              type="select"
              label={text("cancelClass.moveTo")}
              required
              {...(state.missing.destination ? {
                message: {
                  kind: "error" as const, text: text("cancelClass.moveToNeeded"),
                },
              } : {})}
            >
              <select
                id="destination" name="destination_choice"
                className="ds-field-input" value={destination}
                onChange={(event) => setDestination(event.target.value)}
              >
                <option value="">{text("cancelClass.moveToChoose")}</option>
                {destinations.map((option) => (
                  <option key={option.session_id} value={option.session_id}>
                    {option.date} {option.time} · {option.display_name}
                    {option.staff === null ? "" : ` · ${option.staff}`}
                  </option>
                ))}
              </select>
            </Field>
          ) : null}

          <Consequence
            answer={answer} peeking={peeking} remedy={remedy} chosen={chosen}
            locale={locale} numbering={numbering} />

          {answer === null ? null : (
            <Message
              answer={answer} reason={reason} chosen={chosen} name={displayName}
              startsAt={startsAt} timezone={timezone} locale={locale}
              numbering={numbering} />
          )}

          {state.error === null ? null : (
            <Banner severity={state.error === "cancelClass.needsStepUp" ? "info" : "critical"}>
              {text(state.error)}
              {state.error === "cancelClass.needsStepUp" ? (
                <>
                  {" "}
                  <Link
                    href={`/step-up?for=financial&action=scheduling.session.change`
                      + `&next=${encodeURIComponent(back)}`}
                  >
                    {text("cancelClass.raise")}
                  </Link>
                </>
              ) : null}
            </Banner>
          )}

          <div className="row">
            <Button type="submit" variant="destructive" size="lg"
              state={committing ? "loading" : "default"}
              label={fill(locale, "cancelClass.commit",
                { count: booked + waiting }, numbering)} />
            {/* **"Find a coach instead" names what is missing rather than being a dead
                control.** ADM-SCH-03's clash check is built and is about a class being
                created; substituting an instructor on a published session has no form, so a
                button here would answer nothing. "Never a locked control with no route." */}
            <Link href={back}>{text("cancelClass.keepIt")}</Link>
          </div>
          <p className="muted" style={{ margin: 0 }}>
            {text("cancelClass.findACoach")}
          </p>
        </form>
      </div>
    </section>
  );
}

/**
 * What the chosen remedy costs, from the server.
 *
 * **An empty panel while the read is in flight rather than the previous answer.** A figure
 * about the destination somebody has just changed away from is the one a manager would act
 * on, so it is not shown at all.
 */
function Consequence({
  answer, peeking, remedy, chosen, locale, numbering,
}: {
  answer: CancellationPreview | null;
  peeking: boolean;
  remedy: Remedy | "";
  chosen: Destination | null;
  locale: Locale;
  numbering: Numbering;
}) {
  const text = (key: MessageKey) => t(locale, key);
  if (remedy === "") return <Banner severity="info">{text("cancelClass.chooseFirst")}</Banner>;
  if (peeking || answer === null) {
    return <p className="muted" style={{ margin: 0 }}>{text("cancelClass.reading")}</p>;
  }
  if (answer.remedy === "credit") {
    return (
      <Banner severity="info">
        {answer.credit === null
          ? text("cancelClass.creditUnavailable")
          : fill(locale, "cancelClass.creditEach", { days: answer.credit.days }, numbering)}
      </Banner>
    );
  }
  return (
    <>
      <Banner severity={answer.must_choose_count > 0 ? "attention" : "info"}>
        {chosen === null || chosen.staff === null
          ? fill(locale, "cancelClass.moveNoCoach",
            { free: answer.destination?.places_free ?? 0 }, numbering)
          : fill(locale, "cancelClass.moveWithCoach", {
            coach: chosen.staff, free: answer.destination?.places_free ?? 0,
          }, numbering)}
        {answer.must_choose_count > 0 ? (
          <>
            {" "}
            {fill(locale, "cancelClass.wouldChoose",
              { count: answer.must_choose_count }, numbering)}
          </>
        ) : null}
      </Banner>
      {answer.must_choose.some((who) => who.reason === "ineligible") ? (
        <p className="muted" style={{ margin: 0 }}>
          {fill(locale, "cancelClass.someIneligible", {
            count: answer.must_choose.filter((w) => w.reason === "ineligible").length,
          }, numbering)}
        </p>
      ) : null}
      {answer.must_choose.some((who) => who.reason === "already_booked") ? (
        <p className="muted" style={{ margin: 0 }}>
          {fill(locale, "cancelClass.someAlreadyThere", {
            count: answer.must_choose.filter((w) => w.reason === "already_booked").length,
          }, numbering)}
        </p>
      ) : null}
    </>
  );
}

/** The canvas's "They will receive", in the reader's own language. */
function Message({
  answer, reason, chosen, name, startsAt, timezone, locale, numbering,
}: {
  answer: CancellationPreview;
  reason: string;
  chosen: Destination | null;
  name: string;
  startsAt: string;
  timezone: string;
  locale: Locale;
  numbering: Numbering;
}) {
  const text = (key: MessageKey) => t(locale, key);
  const why = reason === ""
    ? text("cancelClass.whyUnstated")
    : text(`cancelClass.reason.${reason}` as MessageKey);
  const body = answer.remedy === "move" && chosen !== null
    ? fill(locale, "cancelClass.messageMove", {
      name, why, day: chosen.date, time: chosen.time,
    })
    : fill(locale, "cancelClass.messageCredit", {
      name, why, days: answer.credit?.days ?? 30,
    }, numbering);
  return (
    <section className="ds-panel">
      <div className="ds-panel-head">
        <h3 className="ds-panel-title">{text("cancelClass.theyWillReceive")}</h3>
      </div>
      <div className="ds-panel-body stack">
        <p style={{ margin: 0 }}>{body}</p>
        <p className="muted" style={{ margin: 0 }}>
          {/* **`count`, not `waiting`.** `fill` picks the plural form from `values.count` and
              throws otherwise -- so a plural message passed any other key name is a 500 on a
              rendered page, which `npm test`'s own sweep catches and a single-file run does
              not. And an empty queue is a *different sentence* rather than a `zero` form,
              because English CLDR has no `zero` category and a form the language never picks
              is a declared value nothing writes. */}
          {answer.waiting === 0
            ? text("cancelClass.eachLanguage")
            : fill(locale, "cancelClass.eachLanguageWaitlist",
              { count: answer.waiting }, numbering)}
        </p>
        <p className="muted" style={{ margin: 0 }}>
          <span className="data" dir="ltr">{timezone}</span>
          {" · "}
          <span className="data" dir="ltr">{startsAt.slice(0, 16).replace("T", " ")}</span>
        </p>
      </div>
    </section>
  );
}

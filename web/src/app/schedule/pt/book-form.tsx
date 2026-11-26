"use client";

import { useActionState, useEffect, useState } from "react";

import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { Field } from "@/components/ds/field";
import { ProseNote } from "@/components/prose";
import { conflictWord } from "@/lib/new-class";
import {
  fill, formatInteger, t,
  type Locale, type MessageKey, type Numbering,
} from "@/i18n/locale";
import {
  atClub, bookingState, instantFrom,
  type PersonalSessionQuote,
} from "@/lib/personal-session";
import { quotePersonalSession, type QuoteAnswer } from "@/lib/pt-check";

import { bookPersonalSession } from "./actions";
import { IDLE, type BookPtState } from "./state";

type Coach = { resource_id: string; display_name: string };

/** A quarter second, as ADM-SCH-03 uses: the canvas asks per change, not per
 *  keystroke, and a round trip per digit of a time field is a request storm. */
const DEBOUNCE_MS = 250;

/**
 * ADM-SCH-05 · SCHEDULE PT — the canvas, field for field.
 *
 * > **Book Yousef with Hala** · `WHEN Thu 17:30` · `LENGTH 55 min`
 * > Uses **1 of her 3 remaining credits**. Two left after this, expiring 30 November.
 * > `[Book · use 1 credit]`
 *
 * **The consequence panel is the server's and is re-read whenever the choice changes.** Which
 * credit would be spent and whether the coach is free are both answers about *one* proposal,
 * so a panel left over from a previous coach or a previous hour is a figure a desk would act
 * on. The answer carries the proposal it was about, so a reply about an edited choice is
 * simply not the one on screen — ADM-SCH-07's own derivation, which needed a ref to catch
 * until it was written this way.
 *
 * **The button says what it costs, and at zero credits it says what to do instead.** The
 * canvas is explicit — "never a blocked state with no way out" — and POS-05, which would sell
 * the package, has no implementation at all. So the screen names selling one as the next step
 * and says where it would happen rather than offering a control that answers nothing, which
 * is this app's own rule about a locked control with no route.
 */
export function BookPtForm({
  locale, numbering, personId, locationId, coaches, memberName, mayBook,
}: {
  locale: Locale;
  numbering: Numbering;
  personId: string;
  locationId: string;
  coaches: Coach[];
  /** `null` where the reader may not read a legal name, which is most sessions. */
  memberName: string | null;
  mayBook: boolean;
}) {
  const text = (key: MessageKey) => t(locale, key);
  const [state, act, pending] = useActionState<BookPtState, FormData>(
    bookPersonalSession, IDLE);

  const [coach, setCoach] = useState(coaches[0]?.resource_id ?? "");
  const [day, setDay] = useState("");
  const [clock, setClock] = useState("17:30");
  const [minutes, setMinutes] = useState(55);
  const [quote, setQuote] = useState<{ for: string; answer: PersonalSessionQuote } | null>(
    null);

  const startsAt = instantFrom(day, clock);
  // **The key of the proposal, so an answer cannot be read against a different one.** Four
  // fields decide the quote; anything else on this form does not.
  const proposal = startsAt === null || !coach
    ? null
    : `${coach}|${startsAt}|${minutes}`;

  // **The effect asks and nothing else.** Everything on screen is derived from the answer,
  // which carries the proposal it was about -- so a reply about a choice the reader has
  // already changed is simply not the answer to the one on screen, and there is nothing to
  // catch. ADM-SCH-03's own shape, and the linter states it as a rule: a synchronous
  // `setState` in an effect body is a value that should have been derived.
  useEffect(() => {
    if (proposal === null) return;
    const timer = setTimeout(() => {
      void quotePersonalSession({
        coachResourceId: coach, personId, locationId,
        startsAt: startsAt ?? "", minutes,
      }).then((answer: QuoteAnswer) => {
        setQuote(answer.outcome === "quoted"
          ? { for: proposal, answer: answer.quote }
          : null);
      });
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [proposal, coach, personId, locationId, startsAt, minutes]);

  // The answer only counts where it is about what is on screen now.
  const live = quote !== null && quote.for === proposal ? quote.answer : null;
  const where = live === null ? null : bookingState(live);

  if (state.booked) {
    const booked = state.booked;
    return (
      <Banner
        severity="info"
        title={text(booked.repeated ? "pt.alreadyBooked" : "pt.booked")}
      >
        {fill(locale, "pt.bookedBody", {
          coach: booked.coachName,
          at: atClub(booked.startsAt, booked.timezone, locale),
          minutes: formatInteger(booked.minutes, numbering),
        })}
        {booked.creditsRemaining === null ? null : (
          <>
            {" "}
            {fill(locale, "pt.leftAfter", { count: booked.creditsRemaining }, numbering)}
          </>
        )}
      </Banner>
    );
  }

  return (
    <form action={act} className="ds-pt-form">
      <input type="hidden" name="person_id" value={personId} />
      <input type="hidden" name="location_id" value={locationId} />
      <input type="hidden" name="starts_at" value={startsAt ?? ""} />
      {/* A key per submit rather than per render: one fixed at render would make a second
          deliberate booking read as a repeat of the first. */}
      <input type="hidden" name="idempotency_key" value={crypto.randomUUID()} />

      <Field id="pt-coach" name="coach_resource_id" label={text("pt.coach")}>
        <select
          id="pt-coach" name="coach_resource_id" className="ds-field-input"
          value={coach} onChange={(e) => setCoach(e.target.value)}
        >
          {coaches.map((one) => (
            <option key={one.resource_id} value={one.resource_id}>
              {one.display_name}
            </option>
          ))}
        </select>
      </Field>

      {/* The canvas's two fields, side by side as it draws them. */}
      <div className="ds-pt-when">
        <Field id="pt-day" name="day" label={text("pt.day")}>
          <input
            id="pt-day" type="date" className="ds-field-input data" dir="ltr"
            value={day} onChange={(e) => setDay(e.target.value)} aria-required="true"
          />
        </Field>
        <Field id="pt-clock" name="clock" label={text("pt.clock")}>
          <input
            id="pt-clock" type="time" className="ds-field-input data" dir="ltr"
            value={clock} onChange={(e) => setClock(e.target.value)} aria-required="true"
          />
        </Field>
        <Field id="pt-minutes" name="minutes" label={text("pt.length")}>
          {/* **ASCII, not the tenant's numerals.** Every rendered figure follows
              `localization.numerals`; a form field is typed back rather than read, and on an
              `arab` tenant a shaped figure in the box would be refused by the number input
              itself. ADM-PAY-06's own finding. */}
          <input
            id="pt-minutes" name="minutes" type="number" min={15} max={240} step={5}
            className="ds-field-input data" dir="ltr"
            value={String(minutes)}
            onChange={(e) => setMinutes(Number(e.target.value))}
          />
        </Field>
      </div>

      {/* ---------------------------------------------------- the consequence */}
      {live === null ? (
        <ProseNote>{text(proposal === null ? "pt.pickAnHour" : "pt.asking")}</ProseNote>
      ) : (
        <div className="ds-pt-consequence">
          {where === "ready" ? (
            <p>
              {live.credits_remaining === null
                ? text("pt.unlimitedCredit")
                : fill(locale, "pt.usesOne",
                  { count: live.credits_remaining }, numbering)}
              {live.credits_remaining_after === null ? null : (
                <>
                  {" "}
                  {fill(locale, "pt.leftAfter",
                    { count: live.credits_remaining_after }, numbering)}
                </>
              )}
              {live.credits_expire_at === null ? null : (
                <>
                  {" "}
                  {fill(locale, "pt.expiring", {
                    on: live.credits_expire_at.slice(0, 10),
                  })}
                </>
              )}
            </p>
          ) : null}

          {/* **Two refusals, never merged.** "Sell a package first" and "pick another hour"
              have different remedies, and a screen that said one for both would send a desk
              to the wrong one. Where both are in the way, both are said. */}
          {live.needs_a_package ? (
            <Banner severity="attention" title={text("pt.noCredit")}>
              {text("pt.sellAPackage")}
            </Banner>
          ) : null}
          {/* **The server's `detail` is a generator diagnostic and carries a resource
              id.** This read "staff 86807d78-62ea-... is already held by Evening yoga
              flow" to a receptionist until an independent tester put the page in front of
              a reader. Two reasons it cannot be rendered: a uuid is not a sentence, and
              the string is English prose composed on the server, which an Arabic reader
              could never be shown (ADR-0015's own finding). The *kind* is the fact and the
              catalogue words it -- through `conflictWord`, which ADM-SCH-03 already reads,
              because two wordings for one conflict kind is the duplication this build
              finds most often. An unknown kind falls through to a written sentence rather
              than to the diagnostic. */}
          {!live.coach_is_free ? (
            <Banner severity="attention" title={text("pt.coachBusy")}>
              {text(conflictWord(live.clashes[0]?.kind ?? "") ?? "pt.coachBusyBody")}
            </Banner>
          ) : null}
        </div>
      )}

      {state.error ? (
        <Banner severity="attention">{text(state.error)}</Banner>
      ) : null}

      <div className="ds-pt-actions">
        <Button
          type="submit" variant="primary" size="lg"
          state={pending || !mayBook || where !== "ready" ? "disabled" : "default"}
          label={where === "ready" && live !== null && live.credits_remaining !== null
            ? fill(locale, "pt.bookAndUse", { one: formatInteger(1, numbering) })
            : text("pt.book")}
        />
      </div>
      {!mayBook ? <ProseNote>{text("pt.needsPermission")}</ProseNote> : null}
      {memberName === null ? <ProseNote>{text("pt.whoseName")}</ProseNote> : null}
    </form>
  );
}

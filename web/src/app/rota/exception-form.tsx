"use client";

import { useActionState } from "react";

import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { Field } from "@/components/ds/field";
import { t, type Locale, type MessageKey } from "@/i18n/locale";

import { addException, withdrawException } from "./actions";
import { IDLE, type RotaState } from "./state";

/**
 * ADM-SCH-04's "Add an exception", and the half that had to be built first.
 *
 * **This is the only write form in this app that is not a member acting on their own
 * account**, and it exists because `scheduling.availability.write` is the one scheduling
 * permission that is routine rather than stepped-up — the catalogue says why: "a rota is
 * edited by the people who run the floor, and refusing them a step-up every time somebody
 * books a day off would make the rota wrong instead."
 *
 * **A client component, and it still works un-hydrated.** `useActionState` over a Server
 * Action posts natively when JavaScript has not loaded; what the hook adds is the refusal
 * being rendered rather than lost. The login page's own note is the warning behind that:
 * its first version was a client component whose un-hydrated form did a native *GET*, which
 * put the password in the query string.
 *
 * **A refusal names which refusal it is.** A 409 is a state somebody else changed, a 422 is
 * what the reader typed, a 403 is the permission and a 429 is a wait — four different next
 * steps, and "something went wrong" is none of them.
 */
export function ExceptionForm({
  locale, resourceId, defaultDate,
}: {
  locale: Locale;
  resourceId: string;
  /** The first day of the week on screen, so the form opens on the week being read. */
  defaultDate: string;
}) {
  const [state, action, pending] = useActionState<RotaState, FormData>(addException, IDLE);
  const text = (key: MessageKey) => t(locale, key);
  // **`rarer="optional"` and so nothing is marked**, which is the Field shell's own rule:
  // "required is marked, optional is not -- whichever is rarer gets the mark", written
  // against exactly this case, "a form where all but one are required". Every field here is
  // required, so four asterisks would be four marks carrying no information -- and they were
  // in the accessible name, where a screen reader read "Day star".
  const bad = (field: keyof RotaState["missing"]): { kind: "error"; text: string } | null =>
    state.missing[field] ? { kind: "error", text: text("rota.fieldNeeded") } : null;

  return (
    <form action={action} className="ds-rota-form">
      <input type="hidden" name="resource_id" value={resourceId} />
      <div className="ds-rota-form-fields">
        <Field
          id="rota-on-date" name="on_date" type="date" required rarer="optional"
          label={text("rota.formDay")}
          defaultValue={state.echo.on_date ?? defaultDate}
          message={bad("on_date")}
        />
        <Field
          id="rota-starts" name="starts_at" type="time" required rarer="optional"
          label={text("rota.formFrom")}
          defaultValue={state.echo.starts_at ?? ""}
          message={bad("starts_at")}
        />
        <Field
          id="rota-ends" name="ends_at" type="time" required rarer="optional"
          label={text("rota.formTo")}
          defaultValue={state.echo.ends_at ?? ""}
          message={bad("ends_at")}
        />
      </div>
      <Field
        id="rota-reason" name="reason" type="text" required rarer="optional"
        label={text("rota.formReason")}
        description={text("rota.formReasonWhy")}
        defaultValue={state.echo.reason ?? ""}
        message={bad("reason")}
      />
      <Button
        type="submit" variant="primary" size="lg"
        label={text("rota.formSubmit")}
        state={pending ? "loading" : "default"}
      />
      <Outcome locale={locale} state={state} />
    </form>
  );
}

/**
 * Take one back.
 *
 * **One form per window rather than one with a hidden id**, because a reason belongs to the
 * withdrawal it explains: a single shared field would carry the last thing typed onto
 * whichever row was pressed.
 */
export function WithdrawForm({
  locale, windowId, label,
}: {
  locale: Locale;
  windowId: string;
  /** Names which window this withdraws, so the control is not "Withdraw" ten times over. */
  label: string;
}) {
  const [state, action, pending] =
    useActionState<RotaState, FormData>(withdrawException, IDLE);
  const text = (key: MessageKey) => t(locale, key);

  return (
    <form action={action} className="ds-rota-withdraw">
      <input type="hidden" name="window_id" value={windowId} />
      <Field
        id={`withdraw-reason-${windowId}`} name="reason" type="text" required rarer="optional"
        label={text("rota.withdrawReason")}
        message={state.missing.reason
          ? { kind: "error", text: text("rota.fieldNeeded") }
          : null}
      />
      {/* **The accessible name says which window**, because "Withdraw" repeated down a
          list is a control a screen-reader user cannot tell apart. */}
      <Button
        type="submit" variant="secondary"
        label={`${text("rota.withdrawSubmit")} \u2014 ${label}`}
        state={pending ? "loading" : "default"}
      />
      <Outcome locale={locale} state={state} />
    </form>
  );
}

function Outcome({ locale, state }: { locale: Locale; state: RotaState }) {
  // **`Severity` has no "success"**, which is the design system's own vocabulary and not an
  // omission: a banner is for something a reader must notice, and `info` is what a completed
  // act is. The four severities are neutral, info, attention and critical.
  if (state.error !== null) {
    return <Banner severity="critical">{t(locale, state.error)}</Banner>;
  }
  if (state.message !== null) {
    return <Banner severity="info">{t(locale, state.message)}</Banner>;
  }
  return null;
}

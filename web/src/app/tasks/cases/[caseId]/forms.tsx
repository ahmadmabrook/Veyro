"use client";

import { useActionState } from "react";

import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { Field } from "@/components/ds/field";
import { t, type Locale, type MessageKey } from "@/i18n/locale";

import { assign, resolve, returnToQueue, snooze } from "./actions";
import { IDLE, type SheetState } from "./state";

/**
 * ADM-CC-06's controls.
 *
 * **Every action is rendered in every state and only some of them do anything**, which is the
 * canvas's rule for the state it is most specific about: an item assigned to somebody else
 * "keeps every action visible but read-only, with 'Nadia is handling this' and a Take over
 * that records the handover". Hiding them would make the sheet look like a different screen
 * depending on who opened it, and a reader who could not see that a deferral exists would ask
 * somebody for it. So an inert control is **rendered disabled with the sentence above it**
 * saying why — which is the one place in this app a disabled control is right, because the
 * remedy is on the screen beside it rather than somewhere a reader has to go and find.
 *
 * **One form per action rather than one with a hidden selector**, and the reason is the rota
 * form's: a reason belongs to the act it explains, so a single shared field would carry the
 * last thing typed onto whichever button was pressed.
 *
 * **A client component that still works un-hydrated.** `useActionState` over a Server Action
 * posts natively before JavaScript loads; what the hook adds is the refusal being rendered
 * rather than lost.
 */
function Outcome({ locale, state }: { locale: Locale; state: SheetState }) {
  if (state.error !== null) {
    return <Banner severity="critical">{t(locale, state.error)}</Banner>;
  }
  if (state.message !== null) {
    return <Banner severity="info">{t(locale, state.message)}</Banner>;
  }
  return null;
}

/** "Assign to me", "Take over" and "Release" — one route, and the act is derived. */
export function AssignForm({
  locale, caseId, label, release, live,
}: {
  locale: Locale;
  caseId: string;
  label: MessageKey;
  /** Whether this button hands the item back to its queue rather than claiming it. */
  release: boolean;
  live: boolean;
}) {
  const [state, action, pending] = useActionState<SheetState, FormData>(assign, IDLE);
  return (
    <form action={action}>
      <input type="hidden" name="case_id" value={caseId} />
      <input type="hidden" name="release" value={release ? "true" : "false"} />
      <Button
        type="submit"
        variant={release ? "secondary" : "primary"}
        label={t(locale, label)}
        state={!live ? "disabled" : pending ? "loading" : "default"}
      />
      <Outcome locale={locale} state={state} />
    </form>
  );
}

/** Defer it, with the reason and the return date the canvas requires. */
export function SnoozeForm({
  locale, caseId, live, defaultDate,
}: {
  locale: Locale;
  caseId: string;
  live: boolean;
  /** A week out, so the commonest deferral is one field. */
  defaultDate: string;
}) {
  const [state, action, pending] = useActionState<SheetState, FormData>(snooze, IDLE);
  const text = (key: MessageKey) => t(locale, key);
  // Every field here is required, so marking them all would be four marks carrying no
  // information -- the Field shell's own rule, "whichever is rarer gets the mark".
  const bad = (field: keyof SheetState["missing"]) =>
    state.missing[field] ? { kind: "error" as const, text: text("case.fieldNeeded") } : null;
  return (
    <form action={action} className="stack">
      <input type="hidden" name="case_id" value={caseId} />
      <Field
        id="case-snooze-until" name="until" type="date" required rarer="optional"
        label={text("case.untilLabel")}
        defaultValue={state.echo.until ?? defaultDate}
        message={bad("until")}
      />
      <Field
        id="case-snooze-reason" name="reason" type="text" required rarer="optional"
        label={text("case.reasonLabel")}
        description={text("case.snoozeNote")}
        defaultValue={state.echo.reason ?? ""}
        message={bad("reason")}
      />
      <Button
        type="submit" variant="secondary" label={text("case.snooze")}
        state={!live ? "disabled" : pending ? "loading" : "default"}
      />
      <Outcome locale={locale} state={state} />
    </form>
  );
}

/** Bring it back early — the remedy the routine deferral needs. */
export function ReturnForm({
  locale, caseId, live,
}: {
  locale: Locale;
  caseId: string;
  live: boolean;
}) {
  const [state, action, pending] = useActionState<SheetState, FormData>(
    returnToQueue, IDLE);
  const text = (key: MessageKey) => t(locale, key);
  return (
    <form action={action} className="stack">
      <input type="hidden" name="case_id" value={caseId} />
      <Field
        id="case-return-reason" name="reason" type="text" required rarer="optional"
        label={text("case.reasonLabel")}
        defaultValue={state.echo.reason ?? ""}
        message={
          state.missing.reason
            ? { kind: "error", text: text("case.fieldNeeded") }
            : null
        }
      />
      <Button
        type="submit" variant="secondary" label={text("case.returnToQueue")}
        state={!live ? "disabled" : pending ? "loading" : "default"}
      />
      <Outcome locale={locale} state={state} />
    </form>
  );
}

/**
 * Resolve it.
 *
 * **The note is above the button, not after it.** A resolution here is forward-only by
 * trigger and this build has no undo — the canvas's 30-second one has nothing to act on — so
 * the sentence that says so belongs where somebody reads it before pressing rather than where
 * they read it afterwards.
 */
export function ResolveForm({
  locale, caseId, live,
}: {
  locale: Locale;
  caseId: string;
  live: boolean;
}) {
  const [state, action, pending] = useActionState<SheetState, FormData>(resolve, IDLE);
  const text = (key: MessageKey) => t(locale, key);
  return (
    <form action={action} className="stack">
      <input type="hidden" name="case_id" value={caseId} />
      <Field
        id="case-resolve-reason" name="reason" type="text" required rarer="optional"
        label={text("case.resolveReasonLabel")}
        description={text("case.resolveNote")}
        defaultValue={state.echo.reason ?? ""}
        message={
          state.missing.reason
            ? { kind: "error", text: text("case.fieldNeeded") }
            : null
        }
      />
      <Button
        type="submit" variant="primary" label={text("case.resolve")}
        state={!live ? "disabled" : pending ? "loading" : "default"}
      />
      <Outcome locale={locale} state={state} />
    </form>
  );
}

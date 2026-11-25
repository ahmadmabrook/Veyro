"use client";

import { useActionState, useState } from "react";

import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { Field } from "@/components/ds/field";
import { fill, formatMoney, t, type Locale, type MessageKey } from "@/i18n/locale";
import { moneyOf, parseAmount, variance } from "@/lib/cash";

import { closeDrawer } from "./actions";
import { IDLE, type CashState } from "./state";

/**
 * ADM-PAY-09's count, and the variance that appears as it is typed.
 *
 * **The expected figure is on the page before the count is entered**, which is the canvas's
 * own decision and the reason this component takes it as a prop rather than revealing it
 * afterwards: *"Hiding it would be a fraud control; showing it is an accuracy control, and
 * accuracy is the more common problem."*
 *
 * **The variance shown here is arithmetic, not an answer.** The server derives the expected
 * figure from the drawer account's own postings and computes the difference itself; this
 * only tells the person at the till what they are about to submit, which is what makes the
 * reason field appear before they press anything. A screen that waited for the server to
 * say "short by 2.50" would ask for the explanation after the submit had already failed.
 */
export function CloseDrawerForm({
  locale, sessionId, legalEntityId, suspenseAccountId, currency, expectedMinor,
  back = "/payments/cash", askForNote = false,
}: {
  locale: Locale;
  sessionId: string;
  legalEntityId: string;
  /** Where a variance posts. Empty when the tenant's chart has no suspense account. */
  suspenseAccountId: string;
  currency: string;
  expectedMinor: number;
  /** Which surface asked, so the right path is revalidated. Both draw this form. */
  back?: string;
  /**
   * Whether to collect FD-07's handover note.
   *
   * **Off for ADM-PAY-09 and on for the front desk**, which is the design rather than a
   * convenience: the note is what one shift passes to the next, and the admin board is
   * somebody looking at every drawer in the tenant rather than a person going off shift. A
   * field asking an accountant what to tell the next receptionist is a field nobody fills.
   */
  askForNote?: boolean;
}) {
  const [state, action, pending] = useActionState<CashState, FormData>(closeDrawer, IDLE);
  const [typed, setTyped] = useState(state.echo.counted ?? "");
  const text = (key: MessageKey) => t(locale, key);

  const money = moneyOf(currency);
  const counted = money === null ? null : parseAmount(typed, money);
  const gap = variance(expectedMinor, counted);
  const out = gap !== null && gap !== 0;
  // `latn`: every figure in this form is money, which ADM-SET-07 exempts from the
  // tenant's numeral setting, so the component takes no numbering at all.
  const amount = (minor: number) => formatMoney(minor, currency, "latn", locale);

  return (
    <form action={action} className="ds-cash-form">
      <input type="hidden" name="session_id" value={sessionId} />
      <input type="hidden" name="legal_entity_id" value={legalEntityId} />
      <input type="hidden" name="suspense_account_id" value={suspenseAccountId} />
      <input type="hidden" name="currency" value={currency} />
      <input type="hidden" name="back" value={back} />

      <Field
        id={`counted-${sessionId}`} name="counted" type="currency" required
        rarer="optional"
        label={text("cash.counted")}
        defaultValue={state.echo.counted ?? ""}
        message={state.missing.counted
          ? { kind: "error", text: text("cash.countedInvalid") }
          : null}
      >
        {/* **The shell's own control, with one addition: it reports as it is typed.**
            `Field` renders the label, the message and the wrapper; passing children swaps
            only the control, so the class, the direction and the message wiring are the
            shell's and `${id}-message` is the id it gives that message. A `currency` field
            is bidi-isolated by type, which is why `dir` is set here too. */}
        <input
          id={`counted-${sessionId}`}
          name="counted"
          className="ds-field-input"
          inputMode="decimal"
          autoComplete="off"
          dir="ltr"
          required
          aria-describedby={
            state.missing.counted ? `counted-${sessionId}-message` : undefined}
          aria-invalid={state.missing.counted || undefined}
          defaultValue={state.echo.counted ?? ""}
          onChange={(event) => setTyped(event.target.value)}
        />
      </Field>

      {/* **The variance panel appears the moment the count is out**, which is what makes
          the reason a field somebody fills rather than a refusal they discover. The module
          is stricter than the canvas here: the canvas gates the note on a JOD 2.00
          threshold and this build has none, so *any* difference needs a sentence. */}
      {out ? (
        <div className="ds-cash-variance" data-direction={gap < 0 ? "short" : "over"}>
          <p className="ds-cash-variance-head">
            <span>{text(gap < 0 ? "cash.shortBy" : "cash.overBy")}</span>
            <span className="data" dir="ltr">{amount(Math.abs(gap))}</span>
          </p>
          <p className="muted" style={{ margin: 0 }}>{text("cash.varianceWhy")}</p>
          <Field
            id={`reason-${sessionId}`} name="reason" type="text" required
            rarer="optional"
            label={text("cash.varianceReason")}
            defaultValue={state.echo.reason ?? ""}
            message={state.missing.reason
              ? { kind: "error", text: text("cash.reasonNeeded") }
              : null}
          />
        </div>
      ) : (
        // The field stays in the form when the drawer balances, because a note on a
        // session that balanced is harmless and worth keeping — `check_close` says so in
        // as many words and deliberately has no branch refusing one.
        <input type="hidden" name="reason" value="" />
      )}

      {askForNote ? (
        <Field
          id={`note-${sessionId}`} name="note" type="textarea" rows={3}
          label={text("cash.handoverNote")}
          description={text("cash.handoverNoteWhat")}
          optionalLabel={text("field.optional")}
          defaultValue={state.echo.note ?? ""}
        />
      ) : null}

      <Button
        type="submit" variant="primary" size="lg"
        label={text("cash.close")}
        state={pending ? "loading" : "default"}
      />
      {state.error !== null ? (
        <Banner severity="critical">{t(locale, state.error)}</Banner>
      ) : state.message !== null ? (
        <Banner severity="info">{t(locale, state.message)}</Banner>
      ) : null}
      {counted !== null && !out ? (
        <p className="muted" style={{ margin: 0 }}>
          {fill(locale, "cash.balances", { amount: amount(expectedMinor) })}
        </p>
      ) : null}
    </form>
  );
}

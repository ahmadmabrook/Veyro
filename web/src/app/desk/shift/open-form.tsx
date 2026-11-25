"use client";

import { useActionState, useState } from "react";

import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { Field } from "@/components/ds/field";
import { fill, formatMoney, t, type Locale, type MessageKey } from "@/i18n/locale";
import { moneyOf, parseAmount } from "@/lib/cash";
import { accountsFor, actFor, countOwes, type Drawer } from "@/lib/shift";

import { openShift } from "./actions";
import { IDLE, type ShiftState } from "./state";

/**
 * FD-07 · OPEN A SHIFT — "COUNT THE FLOAT", and the sentence under it.
 *
 * **Two acts, one form, and which it is comes from the drawer's own balance.** A till that
 * was emptied has to be funded from the safe and the count is the money going in; a till that
 * still holds money is being handed over and the count is a check on what was left. The
 * server tells them apart the same way, so the form cannot offer a button the command then
 * refuses -- which is why `actFor` lives in `@/lib/shift` and is read by both ends.
 *
 * **The reason field appears as the count goes out**, like ADM-PAY-09's: the module refuses a
 * short handover with nothing written, so asking afterwards would ask for the explanation
 * after the submit had already failed. What is *not* gated on the count is the submit itself.
 */
export function OpenShiftForm({
  locale, drawer, locationId, legalEntityId, suspenseAccountId,
  safeAccountId,
}: {
  locale: Locale;
  drawer: Drawer;
  locationId: string;
  /** Empty where this session may not read the entities. Both postings need one. */
  legalEntityId: string;
  /** Where a handover difference lands. Empty when the chart has no suspense account. */
  suspenseAccountId: string;
  /** Where a float is drawn from. Empty when the chart has no second cash account. */
  safeAccountId: string;
}) {
  const [state, action, pending] = useActionState<ShiftState, FormData>(
    openShift, IDLE);
  const [typed, setTyped] = useState(state.echo.counted ?? "");
  const text = (key: MessageKey) => t(locale, key);

  const act = actFor(drawer);
  const money = moneyOf(drawer.currency);
  const counted = money === null ? null : parseAmount(typed, money);
  const owes = countOwes(drawer, counted);
  const out = owes.gap !== null && owes.gap !== 0;
  // `latn`: every figure in this form is money, which ADM-SET-07 exempts from the
  // tenant's numeral setting, so the component takes no numbering at all.
  const amount = (minor: number) => formatMoney(minor, drawer.currency, "latn", locale);

  // What the posting needs, and whether this session could read it. Said rather than left to
  // a 422, because the remedy is in the chart or in a permission rather than in this form.
  const accounts = accountsFor(act, {
    safe: safeAccountId, suspense: suspenseAccountId,
  });
  const posting = act === "fund" ? accounts.floatSource : accounts.suspense;
  const shortOfAccounts = owes.needsPosting
    && (legalEntityId === "" || posting === "");

  return (
    <form action={action} className="ds-cash-form">
      <input type="hidden" name="location_id" value={locationId} />
      <input type="hidden" name="cash_account_id" value={drawer.cash_account_id} />
      <input type="hidden" name="drawer_label" value={drawer.drawer_label} />
      <input type="hidden" name="currency" value={drawer.currency} />
      <input type="hidden" name="legal_entity_id" value={legalEntityId} />
      {/* Which account goes in which field is `accountsFor`'s, so a case can reach it: the
          two conditionals were inline and a mutation against them changed a hidden field no
          test pressed. */}
      <input type="hidden" name="float_source_account_id"
        value={accounts.floatSource} />
      <input type="hidden" name="suspense_account_id" value={accounts.suspense} />

      <Field
        id="float-counted" name="counted" type="currency" required rarer="optional"
        label={text(act === "fund" ? "deskShift.countTheFloat" : "deskShift.countWhatIsThere")}
        defaultValue={state.echo.counted ?? ""}
        message={money === null
          ? { kind: "error", text: text("deskShift.unknownCurrency") }
          : state.missing.counted
            ? { kind: "error", text: text("cash.countedInvalid") }
            : null}
      >
        {/* The shell's own control with one addition: it reports as it is typed, so the
            variance panel appears before anything is pressed. `Field` keeps the class, the
            direction and the message wiring, and `${id}-message` is the id it gives that
            message. */}
        <input
          id="float-counted" name="counted" className="ds-field-input"
          inputMode="decimal" autoComplete="off" dir="ltr" required
          aria-describedby={state.missing.counted ? "float-counted-message" : undefined}
          aria-invalid={state.missing.counted || undefined}
          defaultValue={state.echo.counted ?? ""}
          onChange={(event) => setTyped(event.target.value)}
        />
      </Field>

      {out && owes.gap !== null ? (
        <div className="ds-cash-variance" data-direction={owes.gap < 0 ? "short" : "over"}>
          <p className="ds-cash-variance-head">
            <span>{text(owes.gap < 0 ? "deskShift.shortBy" : "deskShift.overBy")}</span>
            <span className="data" dir="ltr">{amount(Math.abs(owes.gap))}</span>
          </p>
          {/* **The canvas's own sentence, and it is about attribution rather than blame.**
              "If your count differs, say so now -- a discrepancy found at open belongs to the
              previous shift." */}
          <p className="muted" style={{ margin: 0 }}>{text("deskShift.belongsBack")}</p>
          <Field
            id="handover-reason" name="reason" type="text" required rarer="optional"
            label={text("deskShift.whyItDiffers")}
            defaultValue={state.echo.reason ?? ""}
            message={state.missing.reason
              ? { kind: "error", text: text("deskShift.reasonNeeded") }
              : null}
          />
        </div>
      ) : (
        <input type="hidden" name="reason" value="" />
      )}

      {shortOfAccounts ? (
        <p className="muted" style={{ margin: 0 }}>
          {text(act === "fund" ? "deskShift.needsSafe" : "deskShift.needsSuspense")}
        </p>
      ) : null}

      <Button
        type="submit" variant="primary" size="lg"
        label={text("deskShift.openIt")}
        state={pending ? "loading"
          : money === null || shortOfAccounts ? "disabled" : "default"}
      />

      {state.error !== null ? (
        <Banner severity="critical">{text(state.error)}</Banner>
      ) : state.opened !== null ? (
        <Banner severity="info">
          {state.opened.repeated
            ? text("deskShift.openedAlready")
            : state.opened.wasHandover
              && state.opened.varianceMinor !== null && state.opened.varianceMinor !== 0
              ? fill(locale, "deskShift.openedShort",
                { amount: amount(Math.abs(state.opened.varianceMinor)) })
              : text("deskShift.opened")}
          {state.opened.caseId !== null ? ` ${text("deskShift.caseOpened")}` : null}
        </Banner>
      ) : null}
    </form>
  );
}

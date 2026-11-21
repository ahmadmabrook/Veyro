"use client";

import { useActionState, useState } from "react";

import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { Field } from "@/components/ds/field";
import { fill, formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { freezeDays, refusalFor, wouldRemain, type FreezeAllowance } from "@/lib/freeze";

import { freezeMembership } from "./freeze-actions";
import { IDLE, type FreezeState } from "./freeze-state";

/**
 * ADM-MSH-03 · FREEZE — "Freeze Ahmad's membership".
 *
 * **The consequence panel is above the button and fills in as the dates are typed**, which
 * is the canvas's own structure: FROM, UNTIL, REASON, then "Billing pauses from 1 Sep ·
 * access off for the month · renewal moves to 21 Oct · his Club rate is held · 2 of 3 freeze
 * months used this year", and only then Freeze. Stating the cost after the act would make
 * the panel a receipt; stating it before makes it the decision.
 *
 * **It states what this build actually does, which is less than the canvas says.** The
 * module keeps membership, billing and access deliberately separate — "a frozen membership
 * is not an unpaid one" — and a freeze moves the membership's own state; nothing here pauses
 * a billing schedule, because nothing drives one. The term is extended at *resume* by the
 * days actually frozen, so the new renewal date is not knowable at freeze time and the panel
 * does not invent one. The price is held because the agreement snapshots it. Each of those
 * is on the screen rather than implied.
 */
export function FreezeForm({
  locale, numbering, personId, membershipId, allowance,
}: {
  locale: Locale;
  numbering: "latn";
  personId: string;
  membershipId: string;
  allowance: FreezeAllowance;
}) {
  const [state, action, pending] =
    useActionState<FreezeState, FormData>(freezeMembership, IDLE);
  const [from, setFrom] = useState(state.echo.from ?? "");
  const [until, setUntil] = useState(state.echo.until ?? "");
  const text = (key: MessageKey) => t(locale, key);
  const count = (value: number) => formatInteger(value, numbering);

  const days = freezeDays(from, until);
  const refusal = from === "" && until === "" ? null : refusalFor(allowance, from, until);
  const left = wouldRemain(allowance, from, until);

  return (
    <form action={action} className="ds-freeze-form">
      <input type="hidden" name="membership_id" value={membershipId} />
      <input type="hidden" name="person_id" value={personId} />

      <div className="ds-freeze-dates">
        <Field
          id={`freeze-from-${membershipId}`} name="from" type="date" required
          rarer="optional"
          label={text("freeze.from")}
          defaultValue={state.echo.from ?? ""}
          message={state.missing.from
            ? { kind: "error", text: text("freeze.dateNeeded") } : null}
        >
          <input
            id={`freeze-from-${membershipId}`} name="from" type="date" required
            className="ds-field-input" dir="ltr"
            min={allowance.may_start_between.from}
            max={allowance.may_start_between.to}
            defaultValue={state.echo.from ?? ""}
            onChange={(event) => setFrom(event.target.value)}
          />
        </Field>
        <Field
          id={`freeze-until-${membershipId}`} name="until" type="date" required
          rarer="optional"
          label={text("freeze.until")}
          defaultValue={state.echo.until ?? ""}
          message={state.missing.until
            ? { kind: "error", text: text("freeze.untilAfterFrom") } : null}
        >
          <input
            id={`freeze-until-${membershipId}`} name="until" type="date" required
            className="ds-field-input" dir="ltr"
            min={from || allowance.may_start_between.from}
            defaultValue={state.echo.until ?? ""}
            onChange={(event) => setUntil(event.target.value)}
          />
        </Field>
      </div>

      <Field
        id={`freeze-reason-${membershipId}`} name="reason" type="text" required
        rarer="optional"
        label={text("freeze.reason")}
        description={text("freeze.reasonWhy")}
        defaultValue={state.echo.reason ?? ""}
        message={state.missing.reason
          ? { kind: "error", text: text("freeze.reasonNeeded") } : null}
      />

      {/* **The consequence, where the canvas puts it.** It appears once there is a span to
          state one about, and a refusal replaces it rather than sitting beside it: a panel
          describing what a freeze would do, under a sentence saying it cannot be taken, is
          two answers to one question. */}
      {refusal !== null ? (
        <Banner severity="attention">{text(refusal)}</Banner>
      ) : days === null ? null : (
        <div className="ds-freeze-consequence">
          <p style={{ margin: 0 }}>
            <strong>
              {fill(locale, "freeze.lasts", { days: count(days) })}
            </strong>
            {" · "}
            {fill(locale, "freeze.leaves", { days: count(Math.max(0, left ?? 0)) })}
          </p>
          <p className="muted" style={{ margin: 0 }}>{text("freeze.whatHappens")}</p>
        </div>
      )}

      <Button
        type="submit" variant="primary" size="lg"
        label={text("freeze.submit")}
        state={pending ? "loading" : "default"}
      />

      {state.error !== null ? (
        <Banner severity="critical">{t(locale, state.error)}</Banner>
      ) : state.message !== null ? (
        <Banner severity="info">{t(locale, state.message)}</Banner>
      ) : null}
    </form>
  );
}

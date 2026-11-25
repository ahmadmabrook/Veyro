"use client";

import { useActionState, useState } from "react";

import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { Field } from "@/components/ds/field";
import { fill, t, type Locale, type MessageKey } from "@/i18n/locale";
import { confirmsPlan } from "@/lib/downgrade";

import { movePlan } from "./plan-actions";
import { IDLE, type PlanMoveState } from "./plan-state";

/**
 * ADM-MSH-06's confirmation, which is the plan's name rather than a figure.
 *
 * **ADM-MSH-09 types an amount because the act *is* the amount.** This act is a move between
 * two plans and the money is a consequence of it — and on a downgrade the figure is zero, so
 * typing it would be typing "0.00" to confirm losing access to two clubs. The canvas's own
 * button is "Downgrade from 1 Sep", which names the change.
 *
 * **The loss is above this component, not in it.** The canvas puts the consequence first and
 * the control last, and the consequence is a server read rendered on the server — so this is
 * the smallest client component that can hold a typed field, which is the same division the
 * cancellation sheet makes.
 */
export function PlanMoveForm({
  locale, membershipId, personId, termsId, variantId, planName, canWrite, stepUpHref,
}: {
  locale: Locale;
  membershipId: string;
  personId: string;
  termsId: string;
  variantId: string;
  planName: string;
  canWrite: boolean;
  /** Where to send a session that could step up, or `null` when nothing would help. */
  stepUpHref: string | null;
}) {
  const [state, action, pending] = useActionState<PlanMoveState, FormData>(
    movePlan, IDLE);
  const [confirm, setConfirm] = useState(state.echo.confirm ?? "");
  const text = (key: MessageKey) => t(locale, key);
  const typed = confirmsPlan(confirm, planName);

  if (state.moved !== null) {
    return (
      <Banner severity="info">
        {fill(locale, "downgrade.changed",
          { plan: state.moved.planName, on: state.moved.effectiveOn })}
      </Banner>
    );
  }

  return (
    <form action={action} className="ds-cash-form">
      <input type="hidden" name="membership_id" value={membershipId} />
      <input type="hidden" name="person_id" value={personId} />
      <input type="hidden" name="membership_terms_id" value={termsId} />
      <input type="hidden" name="to_variant_id" value={variantId} />
      <input type="hidden" name="plan_name" value={planName} />

      <Field
        id="plan-confirm" name="confirm" type="text" required rarer="optional"
        label={fill(locale, "downgrade.typeToConfirm", { plan: planName })}
        defaultValue={state.echo.confirm ?? ""}
        message={!typed && confirm.trim() !== ""
          ? { kind: "error", text: text("downgrade.confirmMismatch") }
          : null}
      >
        <input
          id="plan-confirm" name="confirm" className="ds-field-input"
          autoComplete="off" aria-required="true"
          defaultValue={state.echo.confirm ?? ""}
          onChange={(event) => setConfirm(event.target.value)}
        />
      </Field>

      {!canWrite ? (
        <p className="muted" style={{ margin: 0 }}>
          {text("downgrade.needsWrite")}
          {stepUpHref !== null ? (
            <>
              {" "}
              <a href={stepUpHref}>{text("member.raiseSession")}</a>
            </>
          ) : null}
        </p>
      ) : null}

      <Button
        type="submit" variant="primary" size="lg"
        label={text("downgrade.confirm")}
        state={pending ? "loading" : !canWrite || !typed ? "disabled" : "default"}
      />

      {state.error !== null ? (
        <Banner severity="critical">{text(state.error)}</Banner>
      ) : null}
    </form>
  );
}

"use client";

import { useActionState } from "react";

import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { ChoiceChips } from "@/components/ds/choice-chips";
import { Field } from "@/components/ds/field";
import { t, type Locale, type MessageKey } from "@/i18n/locale";

import {
  withdrawInterest, reopenLead, markLost, assignLead, moveStage, recordInterests, recordTouchpoint, setNextAction,
} from "./actions";
import { IDLE, type LeadState } from "./state";

/**
 * ADM-CRM-03's five forms.
 *
 * **Each is its own `useActionState`**, so a refusal on one does not clear another's fields
 * and a message appears beside the control that produced it. One shared state would make
 * "assigned" appear over the touchpoint box.
 *
 * **Every submit stays enabled.** "Validate on blur, never on keystroke; re-validate on
 * submit" is the Input contract's rule, and a button that un-disables as fields become
 * acceptable is keystroke validation wearing a different control — it leaves a reader with a
 * dead button and no sentence. The missing field is named after the submit instead.
 */

function Outcome({ locale, state }: { locale: Locale; state: LeadState }) {
  if (state.error !== null) {
    return <Banner severity="critical">{t(locale, state.error)}</Banner>;
  }
  if (state.message !== null) {
    return <Banner severity="info">{t(locale, state.message)}</Banner>;
  }
  return null;
}

export function TouchpointForm({
  locale, leadId, kinds,
}: {
  locale: Locale;
  leadId: string;
  kinds: readonly { value: string; label: string }[];
}) {
  const [state, action, pending] = useActionState<LeadState, FormData>(
    recordTouchpoint, IDLE);
  const text = (key: MessageKey) => t(locale, key);
  return (
    <form action={action} className="stack">
      <input type="hidden" name="lead_id" value={leadId} />
      <Outcome locale={locale} state={state} />
      {/* `Field` takes the control as a child for a select: the shell owns the label, the
          description and the one message slot, and the control is whatever the type needs --
          which is how the design system avoids a prop per input kind. */}
      <Field
        id="lead-kind" name="kind" type="select" required
        label={text("lead.formKind")}
        description={text("lead.formKindHint")}
      >
        <select
          id="lead-kind" name="kind" className="ds-field-input"
          defaultValue={state.echo.kind ?? "call"}
        >
          {kinds.map((one) => (
            <option key={one.value} value={one.value}>{one.label}</option>
          ))}
        </select>
      </Field>
      <Field
        id="lead-summary" name="summary" type="textarea" required
        label={text("lead.formSummary")}
        description={text("lead.formSummaryHint")}
        defaultValue={state.echo.summary ?? ""}
        message={
          state.missing.summary
            ? { kind: "error", text: text("lead.formSummaryMissing") }
            : null
        }
      />
      <Button
        type="submit" variant="primary" size="lg"
        label={text("lead.formRecord")}
        state={pending ? "loading" : "default"}
      />
    </form>
  );
}

export function StageForm({
  locale, leadId, next,
}: {
  locale: Locale;
  leadId: string;
  /** The one stage the pipeline admits from here, or null at the end of it. */
  next: { value: string; label: string } | null;
}) {
  const [state, action, pending] = useActionState<LeadState, FormData>(moveStage, IDLE);
  const text = (key: MessageKey) => t(locale, key);
  if (next === null) {
    // **No button where the pipeline has no edge.** `toured` is the last sales stage and the
    // two columns after it are MOD-017's answer, so a control here would be one the server
    // refuses -- FD-06's "a button the module will refuse is worse than no button".
    return <p className="ds-note">{text("lead.stageIsLast")}</p>;
  }
  return (
    <form action={action} className="stack">
      <input type="hidden" name="lead_id" value={leadId} />
      <input type="hidden" name="to_stage" value={next.value} />
      <Outcome locale={locale} state={state} />
      <Button
        type="submit" variant="secondary" size="lg"
        label={next.label}
        state={pending ? "loading" : "default"}
      />
    </form>
  );
}

export function OwnerForm({
  locale, leadId, owned,
}: {
  locale: Locale;
  leadId: string;
  /** Whether anybody owns it, which decides which of the two controls is offered. */
  owned: boolean;
}) {
  const [state, action, pending] = useActionState<LeadState, FormData>(assignLead, IDLE);
  const text = (key: MessageKey) => t(locale, key);
  return (
    <form action={action} className="stack">
      <input type="hidden" name="lead_id" value={leadId} />
      <input type="hidden" name="release" value={owned ? "true" : "false"} />
      <Outcome locale={locale} state={state} />
      {/* **One control, because the server refuses a no-op.** Assigning the owner a lead
          already has is a 409 -- a write that changed nothing would bump the version and read
          as a handover somebody made -- so an owned lead is offered the release and an unowned
          one the claim. Which act the claim turns out to be is the server's to name. */}
      <Button
        type="submit" variant="secondary" size="lg"
        label={text(owned ? "lead.formRelease" : "lead.formClaim")}
        state={pending ? "loading" : "default"}
      />
      <p className="ds-note">{text(owned ? "lead.releaseNote" : "lead.claimNote")}</p>
    </form>
  );
}

export function NextActionForm({
  locale, leadId, set,
}: {
  locale: Locale;
  leadId: string;
  /** Whether there is one, which is what makes the clear worth offering. */
  set: boolean;
}) {
  const [state, action, pending] = useActionState<LeadState, FormData>(setNextAction, IDLE);
  const text = (key: MessageKey) => t(locale, key);
  return (
    <form action={action} className="stack">
      <input type="hidden" name="lead_id" value={leadId} />
      <Outcome locale={locale} state={state} />
      <Field
        id="lead-next" name="next_action" type="text" required
        label={text("lead.formNext")}
        description={text("lead.formNextHint")}
        defaultValue={state.echo.action ?? ""}
        message={
          state.missing.action ? { kind: "error", text: text("lead.formNextMissing") } : null
        }
      />
      <Field
        id="lead-next-on" name="next_action_on" type="date" required
        label={text("lead.formNextOn")}
        defaultValue={state.echo.on ?? ""}
        message={
          state.missing.on ? { kind: "error", text: text("lead.formNextOnMissing") } : null
        }
      />
      <Button
        type="submit" variant="primary" size="lg"
        label={text("lead.formSetNext")}
        state={pending ? "loading" : "default"}
      />
      {set ? (
        <Button
          type="submit" variant="tertiary" size="lg"
          name="clear" value="true"
          label={text("lead.formClearNext")}
          state={pending ? "loading" : "default"}
        />
      ) : null}
    </form>
  );
}

export function InterestsForm({
  locale, leadId, held, options,
}: {
  locale: Locale;
  leadId: string;
  held: readonly string[];
  options: readonly { value: string; label: string }[];
}) {
  const [state, action, pending] = useActionState<LeadState, FormData>(
    recordInterests, IDLE);
  const text = (key: MessageKey) => t(locale, key);
  const offer = options.filter((one) => !held.includes(one.value));
  if (offer.length === 0) {
    return <p className="ds-note">{text("lead.interestsAllHeld")}</p>;
  }
  return (
    <form action={action} className="stack">
      <input type="hidden" name="lead_id" value={leadId} />
      <Outcome locale={locale} state={state} />
      <fieldset style={{ border: 0, margin: 0, padding: 0 }}>
        <legend>{text("lead.formInterests")}</legend>
        {offer.map((one) => (
          <label key={one.value} style={{ display: "block" }}>
            <input type="checkbox" name="interest" value={one.value} /> {one.label}
          </label>
        ))}
      </fieldset>
      {state.missing.interests ? (
        <Banner severity="attention">{text("lead.formInterestsMissing")}</Banner>
      ) : null}
      <Button
        type="submit" variant="secondary" size="lg"
        label={text("lead.formAddInterests")}
        state={pending ? "loading" : "default"}
      />
    </form>
  );
}


export function WithdrawInterestForm({
  locale, leadId, interest, label,
}: {
  locale: Locale;
  leadId: string;
  interest: string;
  label: string;
}) {
  const [state, action, pending] = useActionState<LeadState, FormData>(
    withdrawInterest, IDLE);
  const text = (key: MessageKey) => t(locale, key);
  return (
    <form action={action} className="ds-inline-form">
      <input type="hidden" name="lead_id" value={leadId} />
      <input type="hidden" name="interest" value={interest} />
      <Outcome locale={locale} state={state} />
      <Button
        type="submit" variant="ghost" size="sm"
        label={`${text("lost.withdrawInterest")} — ${label}`}
        state={pending ? "loading" : "default"}
      />
    </form>
  );
}


export function MarkLostForm({
  locale, leadId, reasons,
}: {
  locale: Locale;
  leadId: string;
  reasons: readonly { value: string; label: string }[];
}) {
  const [state, action, pending] = useActionState<LeadState, FormData>(markLost, IDLE);
  const text = (key: MessageKey) => t(locale, key);
  return (
    <form action={action} className="stack">
      <input type="hidden" name="lead_id" value={leadId} />
      <Outcome locale={locale} state={state} />
      {/* ADM-CRM-07's `ReasonPicker`: `ChoiceChips` in single mode, which is the same
          appearance ADM-CRM-04 draws its interests in rather than a second component. */}
      <ChoiceChips
        name="reason"
        legend={text("lost.reasonLegend")}
        options={reasons}
        single
        required
      />
      {/* **The canvas's "which gym, if he said" -- optional, and marked as such.** `rarer`
          is the shell's rule: on a form where most fields are required, the optional one
          carries the word, and the word comes from the catalogue because a hard-coded
          " (optional)" put Latin letters in the middle of an Arabic line for as long as the
          account page has had a field. */}
      <Field
        id="lost-detail" name="detail" type="text" rarer="optional"
        optionalLabel={text("field.optional")}
        label={text("lost.detailLabel")}
        description={text("lost.detailNote")}
      >
        <input
          id="lost-detail" name="detail" type="text" maxLength={500}
          className="ds-field-input" autoComplete="off"
        />
      </Field>
      <Button
        type="submit" variant="primary" size="lg"
        label={text("lost.submit")}
        state={pending ? "loading" : "default"}
      />
    </form>
  );
}


export function ReopenForm({
  locale, leadId,
}: {
  locale: Locale;
  leadId: string;
}) {
  const [state, action, pending] = useActionState<LeadState, FormData>(reopenLead, IDLE);
  const text = (key: MessageKey) => t(locale, key);
  return (
    <form action={action} className="stack">
      <input type="hidden" name="lead_id" value={leadId} />
      <Outcome locale={locale} state={state} />
      <Button
        type="submit" variant="primary" size="lg"
        label={text("lost.reopen")}
        state={pending ? "loading" : "default"}
      />
    </form>
  );
}

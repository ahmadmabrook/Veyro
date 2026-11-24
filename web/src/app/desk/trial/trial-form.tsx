"use client";

import Link from "next/link";
import { useActionState, useEffect, useState } from "react";

import { ContactMatchLine } from "@/components/contact-match-line";
import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { Field } from "@/components/ds/field";
import { fill, t, type Locale, type MessageKey } from "@/i18n/locale";
import { checkPhone, type DetectionAnswer } from "@/lib/contact-check";
import {
  DETECTION_DEBOUNCE_MS, detectionFor, holdReason, interruption, isAbout, mayCreate,
  worthChecking, type DetectionAnswerFor,
} from "@/lib/walk-in";
import { startedNow, type PlanChoice } from "@/lib/walk-in-trial";

import { startWalkInTrial } from "./actions";
import { IDLE, type WalkInTrialState } from "./state";

/**
 * FD-05 · WALK-IN TRIAL — "Two fields. Sales will get the rest later."
 *
 * The canvas is two fields, one button and one sentence about what the press does:
 *
 * > NAME · Maya Rifai
 * > PHONE · +962 78 993 1104
 * > **Start her trial now**
 * > Creates a lead already in trial with the clock running, a credential, and an app
 * > invitation by text. Yasmin picks it up on her pipeline within the minute.
 *
 * **The duplicate panel is borrowed, because the canvas does not draw one and the screen
 * needs it.** ADM-MEM-10 draws "This number already has a record" and ADM-CRM-04 draws the
 * same region saying nothing was found; a walk-in trial creates a `ppl_persons` row exactly
 * as both of those do, so leaving the check out would make this the one door in the product
 * where a duplicate is cheap to create. Every decision behind it is `@/lib/walk-in`'s,
 * imported rather than re-decided -- a lead *is* a person, so a number already on a record is
 * already on a record.
 *
 * **What is new is the second write path and the acknowledgement being sent on.** The command
 * refuses a number somebody holds, so "Different person" is not a client-side release here:
 * it is a field the request carries, because the server is the one that refuses. And "Start
 * the trial for them" is the sentence ADM-MEM-10 can only link to -- `POST /crm/walk-in-trial`
 * takes a `person_id`, so a match becomes a trial on *that* record with no second person.
 *
 * **One press and one window to report, which is the difference from ADM-CRM-04.** That form
 * makes two HTTP writes and tells the reader when the first landed and the second did not;
 * this one makes a single request whose four writes are resumable on the server (ADR-0010
 * D12), so the only thing to report is which steps it performed -- and the confirmation reads
 * them rather than assuming the press started something.
 */
export function TrialForm({
  locale, numbering, canStart, startVerdict, choice,
}: {
  locale: Locale;
  numbering: "latn";
  /** All five permissions, three of them financial class. */
  canStart: boolean;
  startVerdict: "gate_failed" | "unreachable_level" | "needs_step_up" | "denied";
  choice: PlanChoice;
}) {
  const [state, action, pending] = useActionState<WalkInTrialState, FormData>(
    startWalkInTrial, IDLE);
  const [phone, setPhone] = useState(state.echo.phone ?? "");
  const [answer, setAnswer] = useState<DetectionAnswerFor | null>(null);
  const [acknowledged, setAcknowledged] = useState<string | null>(null);
  const text = (key: MessageKey) => t(locale, key);

  useEffect(() => {
    const value = phone.trim();
    if (!worthChecking(value)) return;
    const timer = setTimeout(() => {
      void checkPhone(value).then((reply: DetectionAnswer) => {
        setAnswer(reply.outcome === "match"
          ? { value, outcome: "match", result: reply.result }
          : { value, outcome: reply.outcome });
      });
    }, DETECTION_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [phone]);

  const value = phone.trim();
  const detection = detectionFor(value, answer);
  const found = interruption(detection, acknowledged, value);
  const first = found?.matches[0] ?? null;
  const duplicate = found === null || first === null ? null : { first, count: found.count };
  const hold = holdReason(detection, acknowledged, value);
  const allowed = canStart && mayCreate(detection, acknowledged, value);

  if (state.started !== null) {
    const started = state.started;
    const now = startedNow(started.steps);
    return (
      <Banner
        severity="info"
        title={text(now ? "deskTrial.started" : "deskTrial.alreadyRunning")}
        actions={
          <Button
            variant="primary" size="md" href={`/leads/${started.leadId}`}
            label={text("deskTrial.openLead")}
          />
        }
      >
        {/* **Day one is a fact about the write, not a figure anybody computed.** A press that
            started a trial started it today, so the first day needs no clock; a press that
            found one already running cannot be told which day it is on without a *today*,
            which is on no response -- so that branch sends the reader to ADM-CRM-05's card,
            where the server answers it. */}
        {started.trialDays !== null && started.endsOn !== null ? (
          <p>
            {now
              ? fill(locale, "deskTrial.dayOne",
                     { count: started.trialDays, ends: started.endsOn }, numbering)
              : fill(locale, "deskTrial.endsOn", { ends: started.endsOn })}
          </p>
        ) : null}
        <p>{text(now ? "deskTrial.startedWhat" : "deskTrial.alreadyRunningWhat")}</p>
        {started.membershipNumber.length > 0 ? (
          <p className="muted">
            {fill(locale, "deskTrial.handle", { handle: started.membershipNumber })}
          </p>
        ) : null}
        {/* The two of the canvas's three promises this build does not keep, on the screen
            rather than only in the response: a desk told a text was sent would stop there. */}
        <p className="muted">{text("deskTrial.notSent")}</p>
      </Banner>
    );
  }

  return (
    <form action={action} className="ds-walk-in-form">
      {/* **Nothing is marked, because every field here is required.** The shell's rule is
          that the mark goes on the rarer side, and a form with no optional field has no rarer
          side -- so `rarer="optional"` leaves all three bare, which is what the canvas draws.
          `aria-required`, not `required`: this form has a second submit that legitimately
          needs neither field -- "Start the trial for them" names a person who already exists
          -- and a native constraint makes the browser refuse the whole form and fire no
          submit event at all. Found on ADM-CRM-04, where the same constraint also made the
          missing-field message unreachable. */}
      <Field
        id="desk-trial-name" name="name" type="text" required rarer="optional"
        label={text("deskTrial.name")}
        message={state.missing.name
          ? { kind: "error", text: text("deskTrial.nameNeeded") } : null}
      >
        <input
          id="desk-trial-name" name="name" type="text" aria-required="true"
          className="ds-field-input" autoComplete="off"
          aria-describedby={state.missing.name ? "desk-trial-name-message" : undefined}
          aria-invalid={state.missing.name ? true : undefined}
          defaultValue={state.echo.name ?? ""}
        />
      </Field>

      <Field
        id="desk-trial-phone" name="phone" type="phone" required rarer="optional"
        label={text("deskTrial.phone")}
        marked={duplicate !== null && !state.missing.phone ? "warning" : undefined}
        describedBy={duplicate !== null ? "desk-trial-duplicate-title" : undefined}
        message={state.missing.phone
          ? { kind: "error", text: text("deskTrial.phoneNeeded") } : null}
      >
        <input
          id="desk-trial-phone" name="phone" type="tel" inputMode="tel" dir="ltr"
          aria-required="true"
          className="ds-field-input data" autoComplete="off"
          aria-invalid={state.missing.phone ? true : undefined}
          aria-describedby={[
            state.missing.phone ? "desk-trial-phone-message" : null,
            duplicate !== null ? "desk-trial-duplicate-title" : null,
          ].filter(Boolean).join(" ") || undefined}
          defaultValue={state.echo.phone ?? ""}
          onChange={(event) => setPhone(event.target.value)}
        />
      </Field>

      {/* **The acknowledgement travels with the request**, which is the difference from the
          other two screens: there it releases a client-side hold, here the *server* is what
          refuses a number somebody holds, so the field is what says a human decided. */}
      {acknowledged !== null && acknowledged === value ? (
        <input type="hidden" name="different_person" value="1" />
      ) : null}

      <div aria-live="polite" className="ds-walk-in-detection">
        {duplicate !== null ? (
          <div className="ds-walk-in-duplicate" role="group"
               aria-labelledby="desk-trial-duplicate-title">
            <p id="desk-trial-duplicate-title" className="ds-walk-in-duplicate-title">
              {text("deskTrial.duplicate")}
            </p>
            <p className="ds-walk-in-match">
              <ContactMatchLine locale={locale} match={duplicate.first} />
              {". "}
              {text("deskTrial.insteadOfSecond")}
            </p>
            {duplicate.count > 1 ? (
              <p className="muted ds-walk-in-others">
                {fill(locale, "deskTrial.alsoHeldBy",
                      { count: duplicate.count - 1 }, numbering)}
              </p>
            ) : null}
            <div className="ds-walk-in-actions">
              <Button
                variant="primary" size="md"
                href={`/people/${duplicate.first.person_id}`}
                label={text("deskTrial.openThatRecord")}
              />
              {/* The trial on the record the check found, which needs no second person --
                  and still needs the step-up, because the agreement and the activation are
                  financial class whoever it is for. */}
              {canStart ? (
                <Button
                  type="submit" name="use_person" value={duplicate.first.person_id}
                  variant="secondary" size="md"
                  label={text("deskTrial.useThatPerson")}
                  state={pending ? "loading" : "default"}
                />
              ) : null}
              <Button
                variant="link" size="md"
                onClick={() => setAcknowledged(value)}
                label={text("deskTrial.differentPerson")}
              />
            </div>
          </div>
        ) : detection.kind === "failed" && isAbout(detection, value) ? (
          <div className="ds-walk-in-duplicate" role="group"
               aria-labelledby="desk-trial-failed-title">
            <p id="desk-trial-failed-title" className="ds-walk-in-duplicate-title">
              {text("deskTrial.checkFailed")}
            </p>
            <p className="ds-walk-in-match">{text("deskTrial.checkFailedWhat")}</p>
            <div className="ds-walk-in-actions">
              <Button
                variant="link" size="md"
                onClick={() => setAcknowledged(value)}
                label={text("deskTrial.differentPerson")}
              />
            </div>
          </div>
        ) : detection.kind === "clear" && isAbout(detection, value) ? (
          <div className="ds-walk-in-duplicate" role="group"
               aria-labelledby="desk-trial-clear-title">
            <p id="desk-trial-clear-title" className="ds-walk-in-duplicate-title">
              {text("deskTrial.clear")}
            </p>
            <p className="ds-walk-in-match">{text("deskTrial.clearWhat")}</p>
          </div>
        ) : null}
      </div>

      {/* **A third field only where the canvas's two cannot answer.** One published trial is
          the drawing and the command derives it; two is a case the design does not have, and
          choosing for the reader would be MOD-018's unordered lookup deciding what somebody
          was sold. */}
      {choice.kind === "several" ? (
        <Field
          id="desk-trial-plan" name="variant_id" type="select" required rarer="optional"
          label={text("deskTrial.plan")}
        >
          <select id="desk-trial-plan" name="variant_id" className="ds-field-input"
                  defaultValue={choice.plans[0]?.variant_id ?? ""}>
            {choice.plans.map((plan) => (
              <option key={plan.variant_id} value={plan.variant_id}>
                {plan.trial_days === null
                  ? plan.display_name
                  : fill(locale, "deskTrial.planOption",
                         { name: plan.display_name, count: plan.trial_days },
                         numbering)}
              </option>
            ))}
          </select>
        </Field>
      ) : null}

      <div className="ds-walk-in-submit">
        <Button
          type="submit"
          variant={duplicate === null ? "primary" : "secondary"}
          size="lg"
          label={text("deskTrial.start")}
          state={pending ? "loading" : allowed ? "default" : "disabled"}
        />
        {!canStart ? (
          <p className="muted ds-walk-in-hold">
            {text(startVerdict === "needs_step_up"
              ? "deskTrial.needsStepUp" : "deskTrial.notPermitted")}
            {startVerdict === "needs_step_up" ? (
              <>
                {" "}
                <Link href={
                  "/step-up?for=financial&action=membership.agreement.activate"
                  + "&next=/desk/trial"
                }>
                  {text("deskTrial.raiseSession")}
                </Link>
              </>
            ) : null}
          </p>
        ) : hold !== null ? (
          <p className="muted ds-walk-in-hold">{text(HOLD_MESSAGE[hold])}</p>
        ) : null}
        {/* The canvas's own sentence under the button, with the half that happens stated and
            the half that does not named below it. */}
        <p className="muted ds-walk-in-note">{text("deskTrial.whatItDoes")}</p>
      </div>

      {state.error !== null ? (
        <Banner severity="critical" title={text(state.error)}>
          {state.error === "deskTrial.needsStepUp" ? (
            <Link href={
              "/step-up?for=financial&action=membership.agreement.activate"
              + "&next=/desk/trial"
            }>
              {text("deskTrial.raiseSession")}
            </Link>
          ) : text("deskTrial.tryAgain")}
        </Banner>
      ) : null}
    </form>
  );
}

const HOLD_MESSAGE: Record<"checking" | "duplicate" | "unknown", MessageKey> = {
  checking: "deskTrial.holdChecking",
  duplicate: "deskTrial.holdDuplicate",
  unknown: "deskTrial.holdUnknown",
};

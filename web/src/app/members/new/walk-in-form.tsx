"use client";

import Link from "next/link";
import { useActionState, useEffect, useState } from "react";

import { ContactMatchLine } from "@/components/contact-match-line";
import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { Field } from "@/components/ds/field";
import { fill, t, type Locale, type MessageKey } from "@/i18n/locale";
import { checkPhone } from "@/lib/contact-check";
import {
  DETECTION_DEBOUNCE_MS, detectionFor, holdReason, interruption, isAbout, mayCreate,
  worthChecking, type DetectionAnswerFor,
} from "@/lib/walk-in";

import { createWalkIn } from "./actions";
import { IDLE, type WalkInState } from "./state";

/**
 * ADM-MEM-10 · ADD MEMBER MANUALLY — "New member · walk-in".
 *
 * The canvas is two fields and one interruption: NAME, PHONE, and when the number is already
 * on a record, "This number already has a record · **Hala Barakat** · joined Feb 2025.
 * Continue and you will create a second record for the same person." with "Open that record"
 * and "Different person". Its footnote states the mechanism: "Detection runs on phone as it
 * is typed, before anything is saved. Preventing the duplicate costs one screen; ADM-MEM-11
 * exists because prevention is never perfect."
 *
 * Four decisions in it are not rendering:
 *
 * - **A stale answer must never land.** The check is debounced and asynchronous, so a reply
 *   for a number the desk has already edited would mark a clear number as duplicated, or
 *   worse, clear a duplicated one. Every answer carries the value it was about and is
 *   discarded unless the field still holds it — which is also why `DetectionState` carries the
 *   value rather than a boolean.
 * - **A dismissal is about one number.** "Different person" answers *this* value; a dismissal
 *   that survived an edit would be a dismissal of a different number, and the next thing
 *   typed would go in with the banner hidden. The acknowledgement is the value itself, so
 *   changing a digit withdraws it.
 * - **A check that could not run is not a check that passed.** An unreachable server holds the
 *   button exactly as a match does, because "we do not know" and "it is free" are different
 *   facts and conflating them turns a network blip into a silent duplicate.
 * - **One primary per view.** When a duplicate is on screen, opening the existing record *is*
 *   the recommended action, so it takes the primary and the create drops to secondary. With
 *   no duplicate, the create is the primary. The rule is the design system's; which control
 *   it applies to is what the duplicate changes.
 */
export function WalkInForm({
  locale, numbering, canWrite, writeVerdict,
}: {
  locale: Locale;
  numbering: "latn";
  canWrite: boolean;
  /** Why the write is closed, where it is. Only `needs_step_up` is worth a link. */
  writeVerdict: "gate_failed" | "unreachable_level" | "needs_step_up" | "denied";
}) {
  const [state, action, pending] = useActionState<WalkInState, FormData>(createWalkIn, IDLE);
  const [phone, setPhone] = useState(state.echo.phone ?? "");
  const [answer, setAnswer] = useState<DetectionAnswerFor | null>(null);
  const [acknowledged, setAcknowledged] = useState<string | null>(null);
  const text = (key: MessageKey) => t(locale, key);

  // **The effect fires the request and nothing else.** Every other part of the state is
  // derived from the field, which is why there is no ref comparing a reply against the value
  // it was about: an answer carries its own value and is not the answer to any other.
  useEffect(() => {
    const value = phone.trim();
    if (!worthChecking(value)) return;
    const timer = setTimeout(() => {
      void checkPhone(value).then((reply) => {
        setAnswer(reply.outcome === "match"
          ? { value, outcome: "match", result: reply.result }
          : { value, outcome: reply.outcome });
      });
    }, DETECTION_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [phone]);

  const value = phone.trim();
  const detection = detectionFor(value, answer);
  // **`interruption`, not a second copy of its rule.** This component had its own
  // "a match about this value that nobody has acknowledged" for the banner while `mayCreate`
  // had the same comparison for the button, and the mutation sweep caught it: breaking one
  // left the other intact and the suite stayed green.
  //
  // **The first match, not the result**, so the type carries what the render needs: a
  // `found` state with an empty list cannot happen (the server answers `clear` for a count of
  // nought) and a component that asserted that would be relying on it.
  const found = interruption(detection, acknowledged, value);
  const first = found?.matches[0] ?? null;
  const duplicate = found === null || first === null
    ? null : { first, count: found.count };
  const hold = holdReason(detection, acknowledged, value);
  // **Not gated on the fields being filled**, which is the Input contract's own rule:
  // "validate on blur, never on keystroke; re-validate on submit". A submit that un-disables
  // as the fields become acceptable is keystroke validation wearing a different control, and
  // it leaves a reader with a dead button and no sentence. The server action returns which
  // field was missing and the shell shows it. What *does* hold the button is the duplicate
  // interruption, which is not validation: it is the canvas's own mechanism.
  const allowed = canWrite && mayCreate(detection, acknowledged, value);

  if (state.createdPersonId !== null) {
    return (
      <Banner
        severity="info"
        title={text("walkIn.created")}
        actions={
          <Button
            variant="primary" size="md" href={`/people/${state.createdPersonId}`}
            label={text("walkIn.openNew")}
          />
        }
      >
        {text("walkIn.createdWhat")}
      </Banner>
    );
  }

  return (
    <form action={action} className="ds-walk-in-form">
      {/* **`aria-required`, not `required`, and the two messages below are why.** A native
          `required` makes the browser refuse the submit and show its own bubble, so
          `missingFields` ran on no request that could ever be made and `walkIn.nameNeeded`
          and `walkIn.phoneNeeded` were a branch nothing could reach -- the decision was unit
          tested and the sentence was never rendered. The app's own rule says to validate on
          blur and re-validate on submit; a native bubble is the browser's version of a
          disabled submit, in a language this app did not choose.
          **Found on ADM-CRM-04**, where the same constraint blocked a second submit that
          legitimately needs neither field. */}
      <Field
        id="walk-in-name" name="name" type="text" required rarer="optional"
        label={text("walkIn.name")}
        message={state.missing.name
          ? { kind: "error", text: text("walkIn.nameNeeded") } : null}
      >
        <input
          id="walk-in-name" name="name" type="text" aria-required="true"
          className="ds-field-input" autoComplete="off"
          aria-describedby={state.missing.name ? "walk-in-name-message" : undefined}
          aria-invalid={state.missing.name ? true : undefined}
          defaultValue={state.echo.name ?? ""}
        />
      </Field>

      {/* **`type="phone"` is not cosmetic.** The shell bidi-isolates it and gives it a
          numeric keyboard from the type rather than from a passed prop, which is what the
          canvas draws: a mono value with `unicode-bidi: isolate`, so `+962 79 662 4180`
          reads the same way in Arabic as in English. */}
      <Field
        id="walk-in-phone" name="phone" type="phone" required rarer="optional"
        label={text("walkIn.phone")}
        // **Marked, not messaged.** The panel below carries the sentence as its title and
        // the canvas puts it there once; repeating it in the message slot renders "This
        // number already has a record" twice under one field, which is the duplication the
        // slot's own rule exists to prevent. The border is the mark and `describedBy` is
        // what makes it an explained one.
        marked={duplicate !== null && !state.missing.phone ? "warning" : undefined}
        describedBy={duplicate !== null ? "walk-in-duplicate-title" : undefined}
        message={state.missing.phone
          ? { kind: "error", text: text("walkIn.phoneNeeded") } : null}
      >
        {/* Mono, which the canvas draws and the design system states for "numbers, phone,
            currency and IDs": in Arabic `.data` swaps the family and keeps the tabular
            figures, so the number reads the same way in both. A child rather than the
            shell's own input, because the detection needs the value as it is typed. */}
        <input
          id="walk-in-phone" name="phone" type="tel" inputMode="tel" dir="ltr"
          aria-required="true"
          className="ds-field-input data" autoComplete="off"
          aria-invalid={state.missing.phone ? true : undefined}
          // Wired here rather than by the shell: a control passed as a child is opaque to it,
          // and this is the one message on the screen a reader must not miss.
          aria-describedby={[
            state.missing.phone ? "walk-in-phone-message" : null,
            duplicate !== null ? "walk-in-duplicate-title" : null,
          ].filter(Boolean).join(" ") || undefined}
          defaultValue={state.echo.phone ?? ""}
          onChange={(event) => setPhone(event.target.value)}
        />
      </Field>

      {/* **Live, so a screen reader hears the interruption rather than meeting it at the
          button.** Polite rather than assertive: it is an interruption to read, not an
          error to correct, and the field's own message carries it as well. */}
      <div aria-live="polite" className="ds-walk-in-detection">
        {duplicate !== null ? (
          /* **A bordered panel, not a Banner.** The canvas draws an inline box under the
             field -- a full border in the attention colour, its title in that colour -- and
             the design system's Banner is the page-level shape with a bar on its inline-start
             edge. The same split the freeze form makes for its consequence panel: a message
             about the whole screen is a Banner, a message about the field above it is not. */
          <div className="ds-walk-in-duplicate" role="group"
               aria-labelledby="walk-in-duplicate-title">
            <p id="walk-in-duplicate-title" className="ds-walk-in-duplicate-title">
              {text("walkIn.alreadyOnARecord")}
            </p>
            <p className="ds-walk-in-match">
              <ContactMatchLine locale={locale} match={duplicate.first} />
              {". "}
              {text("walkIn.secondRecord")}
            </p>
            {duplicate.count > 1 ? (
              <p className="muted ds-walk-in-others">
                {fill(locale, "walkIn.alsoHeldBy",
                      { count: duplicate.count - 1 }, numbering)}
              </p>
            ) : null}
            <div className="ds-walk-in-actions">
              <Button
                variant="primary" size="md"
                href={`/people/${duplicate.first.person_id}`}
                label={text("walkIn.openThatRecord")}
              />
              <Button
                variant="link" size="md"
                onClick={() => setAcknowledged(value)}
                label={text("walkIn.differentPerson")}
              />
            </div>
          </div>
        ) : detection.kind === "failed" && isAbout(detection, value) ? (
          <div className="ds-walk-in-duplicate" role="group"
               aria-labelledby="walk-in-failed-title">
            <p id="walk-in-failed-title" className="ds-walk-in-duplicate-title">
              {text("walkIn.checkFailed")}
            </p>
            <p className="ds-walk-in-match">{text("walkIn.checkFailedWhat")}</p>
            <div className="ds-walk-in-actions">
              <Button
                variant="link" size="md"
                onClick={() => setAcknowledged(value)}
                label={text("walkIn.differentPerson")}
              />
            </div>
          </div>
        ) : null}
      </div>

      <>
        <Field
          id="walk-in-email" name="email" type="email" rarer="required"
          label={text("walkIn.email")}
          defaultValue={state.echo.email ?? ""}
        />
        <Field
          id="walk-in-birth" name="birth_date" type="date" rarer="required"
          label={text("walkIn.birthDate")}
          description={text("walkIn.birthDateWhy")}
          defaultValue={state.echo.birthDate ?? ""}
        />
      </>

      <div className="ds-walk-in-submit">
        <Button
          type="submit"
          // One primary per view: with a duplicate on screen, opening the record it found is
          // the recommended action and this is not.
          variant={duplicate === null ? "primary" : "secondary"}
          size="lg"
          label={text("walkIn.create")}
          state={pending ? "loading" : allowed ? "default" : "disabled"}
        />
        {/* **The permission first, then the duplicate.** A reader who cannot create a record
            at all should learn that before they spend effort resolving an interruption —
            telling them to "open the record above, or say it is a different person" and
            *then* that they may not act is two answers in the wrong order. */}
        {!canWrite ? (
          // **Offered on arrival, not after a failed submit.** The freeze form's pattern:
          // a button that answers 403 is worse than its absence, and a sentence with no way
          // through is barely better. The link is here only for `needs_step_up`, because a
          // step-up cannot grant a permission nobody holds — offering one to a `denied`
          // reader sends them looking for a second factor that changes nothing.
          <p className="muted ds-walk-in-hold">
            {text(writeVerdict === "needs_step_up"
              ? "walkIn.needsStepUp" : "walkIn.notPermitted")}
            {writeVerdict === "needs_step_up" ? (
              <>
                {" "}
                <Link href={
                  "/step-up?for=financial&action=people.person.write&next=/members/new"
                }>
                  {text("walkIn.raiseSession")}
                </Link>
              </>
            ) : null}
          </p>
        ) : hold !== null ? (
          <p className="muted ds-walk-in-hold">{text(HOLD_MESSAGE[hold])}</p>
        ) : null}
      </div>

      {state.error !== null ? (
        <Banner severity="critical" title={text(state.error)}>
          {state.error === "walkIn.needsStepUp" ? (
            <Link href="/step-up?for=financial&action=people.person.write&next=/members/new">
              {text("walkIn.raiseSession")}
            </Link>
          ) : text("walkIn.tryAgain")}
        </Banner>
      ) : null}

      <p className="muted ds-walk-in-note">{text("walkIn.detectionNote")}</p>
    </form>
  );
}

const HOLD_MESSAGE: Record<"checking" | "duplicate" | "unknown", MessageKey> = {
  checking: "walkIn.holdChecking",
  duplicate: "walkIn.holdDuplicate",
  unknown: "walkIn.holdUnknown",
};

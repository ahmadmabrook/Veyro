"use client";

import Link from "next/link";
import { useActionState, useEffect, useState } from "react";

import { ContactMatchLine } from "@/components/contact-match-line";
import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { ChoiceChips } from "@/components/ds/choice-chips";
import { Field } from "@/components/ds/field";
import { fill, t, type Locale, type MessageKey, type Numbering } from "@/i18n/locale";
import { checkPhone, type DetectionAnswer } from "@/lib/contact-check";
import {
  DETECTION_DEBOUNCE_MS, detectionFor, holdReason, interruption, isAbout, mayCreate,
  worthChecking, type DetectionAnswerFor,
} from "@/lib/walk-in";

import { createLead } from "./actions";
import { IDLE, type NewLeadState } from "./state";

/**
 * ADM-CRM-04 · ADD LEAD — "New lead. Name and phone are enough. Everything else can wait."
 *
 * The canvas is two required fields, the detection panel, two optional fields and one button:
 *
 * > NAME · Rana Sabbagh
 * > PHONE · +962 79 411 0288
 * > **No existing record** — Checked as you typed against members and leads. If this number
 * > already existed, that record would open instead of a second one being created.
 * > SOURCE · OPTIONAL — Sweifieh open day ▾
 * > INTEREST · OPTIONAL — [Classes] [PT] ( Gym only )
 * > Save lead
 *
 * **The state this canvas draws is the *clear* one, which is the difference from ADM-MEM-10
 * and the reason the panel is not a warning component.** The walk-in screen draws the same
 * panel with "This number already has a record" in it; this one draws it saying nothing was
 * found. So the region is a standing detection panel rather than a severity indicator — the
 * design uses one treatment for both verdicts, in the attention ink, and that is its call
 * rather than a shortcut here. A reassurance rendered in green and a match rendered in amber
 * would be two components where the design has one.
 *
 * **Every decision behind the check is imported, not re-decided.** `@/lib/walk-in` holds the
 * detection, the stale-answer derivation, the acknowledgement rule and the hold, and
 * `@/lib/contact-check` is the request. A lead *is* a person, so a number already on a record
 * is already on a record: a second copy of this would be two definitions of "does this number
 * exist", and the day they disagreed one screen would create the duplicate the other
 * prevents.
 *
 * **What is new here is the third action, and it is the canvas's own sentence made real.**
 * "That record would open instead of a second one being created" is a statement about what
 * happens, and for a lead it is literally available: `POST /crm/leads` takes a `person_id`, so
 * a match can be turned into a lead against *that* person with one write and no second record
 * — and if they already have a lead the server returns theirs, which is the sentence exactly.
 * ADM-MEM-10 cannot do this, because a member is one command against a person who does not
 * exist yet; this screen can, and until it did `POST /crm/leads` had no caller for an existing
 * person anywhere in the product.
 *
 * **It is also the one control here a routine session can use.** Creating a person is
 * `people.person.write`, financial class and a step-up; opening a lead against one is
 * `crm.lead.write`, routine. So the two actions are gated separately and a desk at an ordinary
 * sign-in can still do the thing the duplicate check found for them.
 */
export function LeadForm({
  locale, numbering, canCreatePerson, personVerdict, canOpenLead, sources, interests, nameWithheld,
}: {
  nameWithheld: MessageKey;
  locale: Locale;
  /**
   * The tenant's numeral system, for the counts and dates this renders.
   *
   * **Widened from the literal `"latn"` by ADR-0015**, which is what the setting reaching a
   * page means. Money is the exception and is not rendered through this: `MoneyValue` carries
   * no numbering at all, and a direct `formatMoney` here passes the literal.
   */
  numbering: Numbering;
  /** `people.person.write` — the new-person half, financial class. */
  canCreatePerson: boolean;
  /** Why the person write is closed, where it is. Only `needs_step_up` is worth a link. */
  personVerdict: "gate_failed" | "unreachable_level" | "needs_step_up" | "denied";
  /** `crm.lead.write` — routine, and all the match path needs. */
  canOpenLead: boolean;
  /** ADM-CRM-04's dropdown. Empty where the tenant has declared none. */
  sources: readonly { value: string; label: string }[];
  interests: readonly { value: string; label: string }[];
}) {
  const [state, action, pending] = useActionState<NewLeadState, FormData>(createLead, IDLE);
  const [phone, setPhone] = useState(state.echo.phone ?? "");
  const [answer, setAnswer] = useState<DetectionAnswerFor | null>(null);
  const [acknowledged, setAcknowledged] = useState<string | null>(null);
  const text = (key: MessageKey) => t(locale, key);

  // The effect fires the request and nothing else: every other part of the state is derived
  // from the field, so an answer carries its own value and is not the answer to any other.
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
  const allowed = canCreatePerson && mayCreate(detection, acknowledged, value);

  if (state.createdLeadId !== null) {
    return (
      <Banner
        severity="info"
        title={text(state.openedExisting ? "newLead.opened" : "newLead.created")}
        actions={
          <Button
            variant="primary" size="md" href={`/leads/${state.createdLeadId}`}
            label={text("newLead.openNew")}
          />
        }
      >
        {text(state.openedExisting ? "newLead.openedWhat" : "newLead.createdWhat")}
      </Banner>
    );
  }

  return (
    <form action={action} className="ds-walk-in-form">
      {/* `rarer="optional"` and so nothing is marked on the two required fields, which is the
          shell's own rule applied to this canvas: the design marks SOURCE and INTEREST as
          optional and leaves NAME and PHONE bare, so optional is the rarer side here even
          though the count is two and two. */}
      {/* **`aria-required`, not `required`, and the difference is a control that works.**
          A native `required` makes the browser refuse the whole form, and this form has a
          second submit that legitimately needs neither field: "Add a lead for them" opens a
          lead against a person who already exists, so there is no name to type. With the
          native constraint on, pressing it produced a validation bubble on an empty Name and
          **no submit event at all** -- a dead button whose own sentence says it needs nothing.
          Found by probing the DOM after the click reported success.
          **And it is the app's own rule from the other side**: "validate on blur, never on
          keystroke; re-validate on submit". A native bubble is the browser's version of a
          disabled submit -- it stops the reader with a message this app did not write, in a
          language it did not choose, and it made `newLead.nameNeeded` unreachable. The server
          validates and the message slot carries the sentence. */}
      <Field
        id="new-lead-name" name="name" type="text" required rarer="optional"
        label={text("newLead.name")}
        message={state.missing.name
          ? { kind: "error", text: text("newLead.nameNeeded") } : null}
      >
        <input
          id="new-lead-name" name="name" type="text" aria-required="true"
          className="ds-field-input" autoComplete="off"
          aria-describedby={state.missing.name ? "new-lead-name-message" : undefined}
          aria-invalid={state.missing.name ? true : undefined}
          defaultValue={state.echo.name ?? ""}
        />
      </Field>

      <Field
        id="new-lead-phone" name="phone" type="phone" required rarer="optional"
        label={text("newLead.phone")}
        // Marked, not messaged: the panel below carries the sentence as its title and the
        // canvas puts it there once. Repeating it in the message slot renders it twice under
        // one field, which is the duplication the slot's own rule exists to prevent.
        marked={duplicate !== null && !state.missing.phone ? "warning" : undefined}
        describedBy={duplicate !== null ? "new-lead-duplicate-title" : undefined}
        message={state.missing.phone
          ? { kind: "error", text: text("newLead.phoneNeeded") } : null}
      >
        <input
          id="new-lead-phone" name="phone" type="tel" inputMode="tel" dir="ltr"
          aria-required="true"
          className="ds-field-input data" autoComplete="off"
          aria-invalid={state.missing.phone ? true : undefined}
          aria-describedby={[
            state.missing.phone ? "new-lead-phone-message" : null,
            duplicate !== null ? "new-lead-duplicate-title" : null,
          ].filter(Boolean).join(" ") || undefined}
          defaultValue={state.echo.phone ?? ""}
          onChange={(event) => setPhone(event.target.value)}
        />
      </Field>

      {/* Live, so a screen reader hears the verdict rather than meeting it at the button.
          Polite rather than assertive: it is an answer to read, not an error to correct, and
          in the clear state it is reassurance. */}
      <div aria-live="polite" className="ds-walk-in-detection">
        {duplicate !== null ? (
          <div className="ds-walk-in-duplicate" role="group"
               aria-labelledby="new-lead-duplicate-title">
            <p id="new-lead-duplicate-title" className="ds-walk-in-duplicate-title">
              {text("newLead.duplicate")}
            </p>
            <p className="ds-walk-in-match">
              <ContactMatchLine nameWithheld={nameWithheld} locale={locale} match={duplicate.first} />
              {". "}
              {text("newLead.insteadOfSecond")}
            </p>
            {duplicate.count > 1 ? (
              <p className="muted ds-walk-in-others">
                {fill(locale, "newLead.alsoHeldBy",
                      { count: duplicate.count - 1 }, numbering)}
              </p>
            ) : null}
            <div className="ds-walk-in-actions">
              {/* **The person's record, not a lead's.** `contact-match` answers about contact
                  points rather than sales records, so this screen cannot tell whether the
                  person already has a lead -- and pointing at `/leads/{id}` with a person id
                  would be a link to nothing. The member record is where a desk finds out who
                  this is, which is what the canvas's "that record would open" means for a
                  reader who is checking rather than acting. */}
              <Button
                variant="primary" size="md"
                href={`/people/${duplicate.first.person_id}`}
                label={text("newLead.openThatRecord")}
              />
              {/* The sentence made real: a lead against the person who is already there,
                  which needs one write and no second record. Routine, so it is offered to a
                  session that cannot create a person at all. */}
              {canOpenLead ? (
                <Button
                  type="submit" name="use_person" value={duplicate.first.person_id}
                  variant="secondary" size="md"
                  label={text("newLead.useThatPerson")}
                  state={pending ? "loading" : "default"}
                />
              ) : null}
              {/* **Borrowed from ADM-MEM-10, which draws the match state this canvas does
                  not.** Two records for one person is sometimes right -- a shared family line
                  is the ordinary case and paragraph 10200 requires a human rather than a
                  threshold -- and without the escape a desk could never record the second
                  sibling at all, because nothing else in this build creates a lead. */}
              <Button
                variant="link" size="md"
                onClick={() => setAcknowledged(value)}
                label={text("newLead.differentPerson")}
              />
            </div>
          </div>
        ) : detection.kind === "failed" && isAbout(detection, value) ? (
          <div className="ds-walk-in-duplicate" role="group"
               aria-labelledby="new-lead-failed-title">
            <p id="new-lead-failed-title" className="ds-walk-in-duplicate-title">
              {text("newLead.checkFailed")}
            </p>
            <p className="ds-walk-in-match">{text("newLead.checkFailedWhat")}</p>
            <div className="ds-walk-in-actions">
              <Button
                variant="link" size="md"
                onClick={() => setAcknowledged(value)}
                label={text("newLead.differentPerson")}
              />
            </div>
          </div>
        ) : detection.kind === "clear" && isAbout(detection, value) ? (
          // The state the canvas draws, with the mechanism sentence as its body. There is no
          // standing footnote on this screen, because that sentence is this panel's content
          // and saying it twice is what the walk-in's footnote slot is for there and not here.
          <div className="ds-walk-in-duplicate" role="group"
               aria-labelledby="new-lead-clear-title">
            <p id="new-lead-clear-title" className="ds-walk-in-duplicate-title">
              {text("newLead.clear")}
            </p>
            <p className="ds-walk-in-match">{text("newLead.clearWhat")}</p>
          </div>
        ) : null}
      </div>

      {/* The canvas's two optional fields. A source the tenant has not declared is not
          offered: an empty dropdown is a control that looks available and is not, and the
          sentence under it says where one comes from. */}
      {sources.length === 0 ? (
        <p className="muted ds-walk-in-note">{text("newLead.noSources")}</p>
      ) : (
        <Field
          id="new-lead-source" name="source_id" type="select" rarer="optional"
          optionalLabel={text("field.optional")}
          label={text("newLead.source")}
        >
          <select
            id="new-lead-source" name="source_id" className="ds-field-input"
            defaultValue={state.echo.source ?? ""}
          >
            <option value="">{text("newLead.noSourceChosen")}</option>
            {sources.map((one) => (
              <option key={one.value} value={one.value}>{one.label}</option>
            ))}
          </select>
        </Field>
      )}

      <ChoiceChips
        name="interest"
        legend={text("newLead.interest")}
        mark={text("field.optional")}
        options={interests}
        defaultSelected={state.echo.interests ?? []}
        // **Gym only is not combined with the other two**, which the words say and the server
        // refuses. Said before the choice rather than left to a 422, because this app's
        // validation handler deliberately names no field.
        note={text("newLead.interestExclusive")}
      />

      <div className="ds-walk-in-submit">
        <Button
          type="submit"
          // One primary per view: with a match on screen, opening the record it found is the
          // recommended action and this is not.
          variant={duplicate === null ? "primary" : "secondary"}
          size="lg"
          label={text("newLead.create")}
          state={pending ? "loading" : allowed ? "default" : "disabled"}
        />
        {/* The permission first, then the check: a reader who cannot create a person at all
            should learn that before they spend effort resolving an interruption -- and the
            sentence says the match path is still open to them, because it is. */}
        {!canCreatePerson ? (
          <p className="muted ds-walk-in-hold">
            {text(personVerdict === "needs_step_up"
              ? "newLead.needsStepUp" : "newLead.notPermitted")}
            {personVerdict === "needs_step_up" ? (
              <>
                {" "}
                <Link href={
                  "/step-up?for=financial&action=people.person.write&next=/leads/new"
                }>
                  {text("newLead.raiseSession")}
                </Link>
              </>
            ) : null}
            {canOpenLead ? <> {text("newLead.matchPathStillOpen")}</> : null}
          </p>
        ) : hold !== null ? (
          <p className="muted ds-walk-in-hold">{text(HOLD_MESSAGE[hold])}</p>
        ) : null}
      </div>

      {state.error !== null ? (
        <Banner severity="critical" title={text(state.error)}>
          {state.error === "newLead.needsStepUp" ? (
            <Link href="/step-up?for=financial&action=people.person.write&next=/leads/new">
              {text("newLead.raiseSession")}
            </Link>
          ) : state.orphanedPersonId !== null ? (
            <Link href={`/people/${state.orphanedPersonId}`}>
              {text("newLead.openOrphan")}
            </Link>
          ) : text("newLead.tryAgain")}
        </Banner>
      ) : null}
    </form>
  );
}

const HOLD_MESSAGE: Record<"checking" | "duplicate" | "unknown", MessageKey> = {
  checking: "newLead.holdChecking",
  duplicate: "newLead.holdDuplicate",
  unknown: "newLead.holdUnknown",
};

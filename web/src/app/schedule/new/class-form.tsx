"use client";

import Link from "next/link";
import { useActionState, useEffect, useState } from "react";

import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { ChoiceChips } from "@/components/ds/choice-chips";
import { Field } from "@/components/ds/field";
import { fill, t, type Locale, type MessageKey } from "@/i18n/locale";
import { checkClass, type CheckAnswer } from "@/lib/class-check";
import {
  WEEK, checkState, conflictWord, holdReason, mayCreate, perWeek, proposalKey,
  type CheckedProposal,
} from "@/lib/new-class";

import { createClass } from "./actions";
import { IDLE, type NewClassState } from "./state";

/** How long to wait after a field changes before asking. A person types faster than this. */
const DEBOUNCE_MS = 400;

type Choice = { value: string; label: string };

/**
 * ADM-SCH-03 · CREATE A CLASS — "New recurring class".
 *
 * **The live check is the screen**, and the canvas says so twice: "conflicts surface as the
 * coach field changes, not on save -- a save-time error means re-deciding everything else
 * too", and "it warns, it does not block: a manager may know Omar's PT is moving". So the
 * clash is a panel under the coach field rather than a refusal, and the two answers the canvas
 * draws are both offered: **Use Dana** sets the coach to a free one, and **Keep Omar anyway**
 * opens the written reason paragraph 1842 requires before a conflict may be overridden.
 *
 * **Two of the canvas's three sentences about the clash are the server's and one is not.**
 * "Omar already has PT at 19:00 Thursdays" is the conflict's own detail; "Dana and Yousef are
 * both qualified and free at that hour" is the alternatives list -- and only the *free* half
 * of it, because nothing in this build stores a skill, which the panel says rather than
 * letting the names imply it.
 *
 * **The capacity ceiling is the equipment that exists.** "Studio 2 holds 20 bikes. Capacity
 * cannot exceed the room" -- a fact about the bike row's quantity rather than a seat count on
 * a room, which this schema deliberately does not carry.
 */
export function ClassForm({
  locale, locationId, services, rooms, staff, today, until, canDraft, canPublish,
  canOverride, draftVerdict,
}: {
  locale: Locale;
  locationId: string;
  services: readonly Choice[];
  rooms: readonly Choice[];
  staff: readonly Choice[];
  /** The first date the class can run, which is tomorrow: derived, not drawn. */
  today: string;
  until: string;
  canDraft: boolean;
  canPublish: boolean;
  /** `scheduling.conflict.override` — what "Keep Omar anyway" costs. */
  canOverride: boolean;
  draftVerdict: "gate_failed" | "unreachable_level" | "needs_step_up" | "denied";
}) {
  const [state, action, pending] = useActionState<NewClassState, FormData>(
    createClass, IDLE);
  const text = (key: MessageKey) => t(locale, key);

  const [serviceId, setServiceId] = useState(services[0]?.value ?? "");
  const [roomId, setRoomId] = useState(rooms[0]?.value ?? "");
  const [staffId, setStaffId] = useState(staff[0]?.value ?? "");
  const [localTime, setLocalTime] = useState("19:00");
  const [duration, setDuration] = useState(60);
  const [capacity, setCapacity] = useState(20);
  const [waitlist, setWaitlist] = useState(5);
  const [weekdays, setWeekdays] = useState<number[]>([]);
  const [overrideReason, setOverrideReason] = useState("");
  const [answer, setAnswer] = useState<CheckedProposal | null>(null);

  const ready = Boolean(serviceId && roomId && staffId) && weekdays.length > 0;
  const key = proposalKey({
    locationId, serviceId, roomId, staffId, localTime, duration, capacity, waitlist,
    weekdays,
  });

  // **The effect asks and nothing else.** Every other part of the screen is derived from the
  // answer, which carries the key it was about -- so a reply about a proposal the reader has
  // already changed is not the answer to the one on screen and there is nothing to catch.
  // `@/lib/walk-in` records the same shape, and the linter states it as a rule: a synchronous
  // `setState` in an effect body is a value that should have been derived.
  useEffect(() => {
    if (!ready) return;
    const requirements: { kind: string; quantity: number; resource_id?: string }[] = [
      { kind: "service", quantity: 1, resource_id: serviceId },
      { kind: "room", quantity: 1, resource_id: roomId },
      { kind: "staff", quantity: 1, resource_id: staffId },
    ];
    const timer = setTimeout(() => {
      void checkClass({
        locationId, localTime, durationMinutes: duration, weekdays,
        startsOn: today, until, capacity, setupMinutes: 0, cleanupMinutes: 0,
        waitlistCapacity: waitlist, requirements,
      }).then((reply: CheckAnswer) => {
        setAnswer({ key, result: reply.outcome === "checked" ? reply.result : null });
      });
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [ready, key, locationId, serviceId, roomId, staffId, localTime, duration, capacity,
      waitlist, weekdays, today, until]);

  const asking = checkState(ready, key, answer);
  const check = asking.kind === "checked" ? asking.result : null;
  const fields = { serviceId, roomId, staffId, weekdays };
  const hold = holdReason(fields, check, overrideReason);
  const allowed = canDraft && canPublish && mayCreate(fields, check, overrideReason);
  const clashes = check?.conflicts ?? [];

  if (state.created !== null) {
    const made = state.created;
    return (
      <Banner
        severity="info"
        title={text("newClass.created")}
        actions={
          <Button
            variant="primary" size="md"
            href={`/schedule?location=${locationId}`}
            label={text("newClass.openCalendar")}
          />
        }
      >
        <p>{fill(locale, "newClass.createdWhat", { count: made.sessions }, "latn")}</p>
        {made.overridden ? <p className="muted">{text("newClass.createdOver")}</p> : null}
      </Banner>
    );
  }

  return (
    <form action={action} className="ds-walk-in-form">
      <input type="hidden" name="location_id" value={locationId} />
      <input type="hidden" name="starts_on" value={today} />
      <input type="hidden" name="until" value={until} />
      <input type="hidden" name="duration_minutes" value={duration} />
      <input
        type="hidden" name="display_name"
        value={services.find((one) => one.value === serviceId)?.label ?? ""}
      />

      <Field
        id="new-class-type" name="service_id" type="select" required rarer="optional"
        label={text("newClass.type")}
      >
        <select
          id="new-class-type" name="service_id" className="ds-field-input"
          value={serviceId} onChange={(event) => setServiceId(event.target.value)}
        >
          {services.map((one) => (
            <option key={one.value} value={one.value}>{one.label}</option>
          ))}
        </select>
      </Field>

      <Field
        id="new-class-coach" name="staff_id" type="select" required rarer="optional"
        label={text("newClass.coach")}
        marked={clashes.length > 0 ? "warning" : undefined}
        describedBy={clashes.length > 0 ? "new-class-clash-title" : undefined}
      >
        <select
          id="new-class-coach" name="staff_id" className="ds-field-input"
          value={staffId} onChange={(event) => setStaffId(event.target.value)}
          aria-describedby={clashes.length > 0 ? "new-class-clash-title" : undefined}
        >
          {staff.map((one) => (
            <option key={one.value} value={one.value}>{one.label}</option>
          ))}
        </select>
      </Field>

      {/* Live, so a screen reader hears the clash as it appears rather than meeting it at the
          button. Polite: it is an answer to read, not an error to correct. */}
      <div aria-live="polite" className="ds-walk-in-detection">
        {clashes.length > 0 ? (
          <div className="ds-walk-in-duplicate" role="group"
               aria-labelledby="new-class-clash-title">
            <p id="new-class-clash-title" className="ds-walk-in-duplicate-title">
              {text("newClass.clashTitle")}
            </p>
            <ul className="ds-walk-in-match">
              {clashes.slice(0, 4).map((clash, index) => {
                const word = conflictWord(clash.kind);
                return (
                  <li key={`${clash.starts_at}-${clash.kind}-${index}`}>
                    {/* The stored kind is never the label, and an unknown one falls through
                        to the server's own detail rather than to a word nobody wrote. */}
                    {word === null ? clash.detail : text(word)}
                    {clash.resource_name === null ? null : ` · ${clash.resource_name}`}
                    {" · "}
                    <span className="data">{clash.local_date}</span>
                  </li>
                );
              })}
            </ul>
            {check !== null && check.alternatives.length > 0 ? (
              <>
                <p className="muted ds-walk-in-others">{text("newClass.freeInstead")}</p>
                <div className="ds-walk-in-actions">
                  {check.alternatives.map((one) => (
                    <Button
                      key={one.resource_id}
                      variant="secondary" size="md"
                      onClick={() => setStaffId(one.resource_id)}
                      label={fill(locale, "newClass.useThem", {
                        name: one.display_name ?? one.resource_id,
                      })}
                    />
                  ))}
                </div>
              </>
            ) : null}
            {/* **"Keep Omar anyway", which opens the reason rather than being the decision.**
                Paragraph 1842's Critical Control is permission *and* reason, so the button
                reveals the field rather than committing -- and a reader who may not override
                is told so instead of being given a control that would be refused. */}
            {canOverride ? (
              <Field
                id="new-class-reason" name="override_reason" type="text" required
                rarer="optional"
                label={text("newClass.keepAnyway")}
                description={text("newClass.keepAnywayWhy")}
              >
                <input
                  id="new-class-reason" name="override_reason" type="text"
                  className="ds-field-input" autoComplete="off"
                  value={overrideReason}
                  onChange={(event) => setOverrideReason(event.target.value)}
                />
              </Field>
            ) : (
              <p className="muted ds-walk-in-hold">{text("newClass.noOverride")}</p>
            )}
          </div>
        ) : check !== null ? (
          <div className="ds-walk-in-duplicate" role="group"
               aria-labelledby="new-class-clear-title">
            <p id="new-class-clear-title" className="ds-walk-in-duplicate-title">
              {text("newClass.clear")}
            </p>
            <p className="ds-walk-in-match">
              {check.examined_from === null || check.examined_to === null
                ? text("newClass.clearWhat")
                : fill(locale, "newClass.clearRange", {
                    count: check.examined,
                    from: check.examined_from,
                    to: check.examined_to,
                  }, "latn")}
            </p>
          </div>
        ) : asking.kind === "unchecked" ? (
          <div className="ds-walk-in-duplicate" role="group"
               aria-labelledby="new-class-unchecked-title">
            <p id="new-class-unchecked-title" className="ds-walk-in-duplicate-title">
              {text("newClass.unchecked")}
            </p>
            <p className="ds-walk-in-match">{text("newClass.uncheckedWhat")}</p>
          </div>
        ) : null}
      </div>

      <Field
        id="new-class-room" name="room_id" type="select" required rarer="optional"
        label={text("newClass.room")}
      >
        <select
          id="new-class-room" name="room_id" className="ds-field-input"
          value={roomId} onChange={(event) => setRoomId(event.target.value)}
        >
          {rooms.map((one) => (
            <option key={one.value} value={one.value}>{one.label}</option>
          ))}
        </select>
      </Field>

      <Field
        id="new-class-capacity" name="capacity" type="number" required rarer="optional"
        label={text("newClass.capacity")}
      >
        <input
          id="new-class-capacity" name="capacity" type="number" inputMode="numeric"
          min={1} max={10000} className="ds-field-input data"
          value={capacity}
          onChange={(event) => setCapacity(Number(event.target.value) || 0)}
        />
      </Field>

      <Field
        id="new-class-time" name="local_time" type="text" required rarer="optional"
        label={text("newClass.time")}
        {...(check === null
          ? {}
          : { description: fill(locale, "newClass.inZone", { zone: check.timezone }) })}
      >
        <input
          id="new-class-time" name="local_time" type="time" dir="ltr"
          className="ds-field-input data"
          value={localTime} onChange={(event) => setLocalTime(event.target.value)}
        />
      </Field>

      <Field
        id="new-class-duration" name="duration" type="number" required rarer="optional"
        label={text("newClass.duration")}
      >
        <input
          id="new-class-duration" type="number" inputMode="numeric" min={1} max={1440}
          className="ds-field-input data"
          value={duration}
          onChange={(event) => setDuration(Number(event.target.value) || 0)}
        />
      </Field>

      <ChoiceChips
        name="weekday"
        legend={text("newClass.repeats")}
        options={WEEK.map((day) => ({ value: String(day.weekday), label: text(day.key) }))}
        defaultSelected={weekdays.map(String)}
        onChange={(values) => setWeekdays(values.map(Number))}
        required
        note={text("newClass.repeatsNote")}
      />

      <Field
        id="new-class-waitlist" name="waitlist_capacity" type="number" rarer="optional"
        optionalLabel={text("field.optional")}
        label={text("newClass.waitlist")}
        description={text("newClass.waitlistWhat")}
      >
        <input
          id="new-class-waitlist" name="waitlist_capacity" type="number"
          inputMode="numeric" min={0} max={10000} className="ds-field-input data"
          value={waitlist}
          onChange={(event) => setWaitlist(Number(event.target.value) || 0)}
        />
      </Field>

      <div className="ds-walk-in-submit">
        <Button
          type="submit"
          variant="primary" size="lg"
          label={weekdays.length === 0
            ? text("newClass.create")
            : fill(locale, "newClass.createCount",
                   { count: perWeek(weekdays) }, "latn")}
          state={pending ? "loading" : allowed ? "default" : "disabled"}
        />
        {!canDraft || !canPublish ? (
          <p className="muted ds-walk-in-hold">
            {text(draftVerdict === "needs_step_up"
              ? "newClass.needsStepUp" : "newClass.notPermitted")}
            {draftVerdict === "needs_step_up" ? (
              <>
                {" "}
                <Link href={
                  "/step-up?for=financial&action=scheduling.schedule.publish"
                  + `&next=/schedule/new%3Flocation=${locationId}`
                }>
                  {text("newClass.raiseSession")}
                </Link>
              </>
            ) : null}
          </p>
        ) : hold !== null ? (
          <p className="muted ds-walk-in-hold">{text(HOLD_MESSAGE[hold])}</p>
        ) : null}
        {/* The dates the rule covers, which the canvas draws no field for -- so they are
            derived and said rather than asked. */}
        <p className="muted ds-walk-in-note">
          {fill(locale, "newClass.window", { from: today, to: until })}
        </p>
      </div>

      {state.error !== null ? (
        <Banner severity="critical" title={text(state.error)}>
          {state.error === "newClass.needsStepUp" ? (
            <Link href={
              "/step-up?for=financial&action=scheduling.schedule.publish"
              + `&next=/schedule/new%3Flocation=${locationId}`
            }>
              {text("newClass.raiseSession")}
            </Link>
          ) : state.stoppedAt !== null ? (
            text(state.stoppedAt.reached === "drafted"
              ? "newClass.stoppedDrafted" : "newClass.stoppedPublished")
          ) : text("newClass.tryAgain")}
        </Banner>
      ) : null}
    </form>
  );
}

const HOLD_MESSAGE: Record<"fields" | "weekdays" | "reason", MessageKey> = {
  fields: "newClass.holdFields",
  weekdays: "newClass.holdWeekdays",
  reason: "newClass.holdReason",
};

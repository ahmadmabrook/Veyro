import { describe, expect, it } from "vitest";

import { MESSAGES } from "@/i18n/locale";
import {
  WEEK, checkState, conflictWord, holdReason, mayCreate, perWeek, proposalKey,
  type ConflictCheck,
} from "@/lib/new-class";

/**
 * ADM-SCH-03's decisions. The clash is the server's; what is here is when to ask, what to do
 * with an answer, and what holds the button.
 *
 * **Decisions rather than a rendered branch**, which this repository has a rule for: a surface
 * branch no fixture can reach is vacuity one layer up. The unchecked state is one of those -- a
 * browser test cannot reach it without taking the backend down.
 */

const answer = (over: Partial<ConflictCheck> = {}): ConflictCheck => ({
  clear: true, conflicts: [], alternatives: [], spare: {}, occurrences: 13, per_week: 1,
  examined: 8, examined_of: 13, examined_from: "2026-09-03", examined_to: "2026-10-22",
  timezone: "Asia/Amman", ...over,
});

const clash = {
  local_date: "2026-09-03", starts_at: "2026-09-03T16:00:00+00:00",
  kind: "double_booked", resource_id: "r1", resource_name: "Omar Salti",
  detail: "held by Spin", with_session_id: "s1",
};

const FIELDS = { serviceId: "s", roomId: "r", staffId: "c", weekdays: [3] };

describe("the week the chips draw", () => {
  it("starts on Sunday, which is the canvas's own order", () => {
    expect(WEEK.map((day) => day.key)).toEqual([
      "week.sun", "week.mon", "week.tue", "week.wed", "week.thu", "week.fri", "week.sat",
    ]);
  });

  it("keeps the storage convention underneath, which is 0-Monday", () => {
    // **Reading order and storage order are different facts**, which `/rota` already records:
    // `Window.weekday` is 0-Monday because that is Python's convention and says nothing about
    // which column a reader sees first. Sunday is 6 either way.
    expect(WEEK[0]?.weekday).toBe(6);
    expect(WEEK.map((day) => day.weekday).sort((a, b) => a - b))
      .toEqual([0, 1, 2, 3, 4, 5, 6]);
  });

  it("counts what the button states", () => {
    expect(perWeek([3])).toBe(1);
    expect(perWeek([1, 3])).toBe(2);
    expect(perWeek([])).toBe(0);
  });
});

describe("what is known about the proposal on screen", () => {
  it("is the answer only where the answer is about this proposal", () => {
    const key = proposalKey({
      locationId: "l", serviceId: "s", roomId: "r", staffId: "c", localTime: "19:00",
      duration: 60, capacity: 20, waitlist: 5, weekdays: [3],
    });
    expect(checkState(true, key, { key, result: answer() }).kind).toBe("checked");
    // **A reply about a proposal the reader has already changed is not the answer to this
    // one**, which is what makes the stale-answer race impossible rather than guarded.
    expect(checkState(true, key, { key: "other", result: answer() }).kind).toBe("asking");
    expect(checkState(true, key, null).kind).toBe("asking");
    expect(checkState(false, key, { key, result: answer() }).kind).toBe("incomplete");
  });

  it("keeps unchecked apart from clear, because they are different facts", () => {
    // A check the server could not be asked has not told anybody the hour is free -- "a
    // control consulted once is a control with a window", in a surface.
    expect(checkState(true, "k", { key: "k", result: null }).kind).toBe("unchecked");
    expect(checkState(true, "k", { key: "k", result: answer() }).kind).toBe("checked");
  });

  it("keys on every field the answer depends on and nothing else", () => {
    const base = {
      locationId: "l", serviceId: "s", roomId: "r", staffId: "c", localTime: "19:00",
      duration: 60, capacity: 20, waitlist: 5, weekdays: [3],
    };
    expect(proposalKey(base)).toBe(proposalKey({ ...base, weekdays: [3] }));
    // The order the chips were tapped in is not a different proposal.
    expect(proposalKey({ ...base, weekdays: [3, 1] }))
      .toBe(proposalKey({ ...base, weekdays: [1, 3] }));
    for (const changed of [
      { staffId: "other" }, { roomId: "other" }, { localTime: "20:00" },
      { capacity: 21 }, { duration: 45 }, { waitlist: 0 }, { weekdays: [3, 4] },
    ]) {
      expect(proposalKey({ ...base, ...changed })).not.toBe(proposalKey(base));
    }
  });
});

describe("what holds the button", () => {
  it("is never the clash itself, because it warns and does not block", () => {
    // The canvas's own sentence: "a manager may know Omar's PT is moving". What a clash
    // changes is the permission the create costs, not whether it may be attempted.
    const clashed = answer({ clear: false, conflicts: [clash] });
    expect(mayCreate(FIELDS, clashed, "his PT is moving")).toBe(true);
    expect(holdReason(FIELDS, clashed, "his PT is moving")).toBeNull();
  });

  it("is the written reason paragraph 1842 requires", () => {
    const clashed = answer({ clear: false, conflicts: [clash] });
    expect(mayCreate(FIELDS, clashed, "   ")).toBe(false);
    expect(holdReason(FIELDS, clashed, "")).toBe("reason");
  });

  it("is the three resources and at least one day", () => {
    expect(holdReason({ ...FIELDS, staffId: "" }, answer(), "")).toBe("fields");
    expect(holdReason({ ...FIELDS, weekdays: [] }, answer(), "")).toBe("weekdays");
    expect(holdReason(FIELDS, answer(), "")).toBeNull();
  });

  it("does not hold while no answer has arrived, which is what a warning means", () => {
    // A clash that has not been reported is not a clash somebody can act on, and holding the
    // button until the debounce lands would make the screen feel broken on every keystroke.
    expect(mayCreate(FIELDS, null, "")).toBe(true);
  });
});

describe("what a clash is called", () => {
  it("is a word from the catalogue and never the stored kind", () => {
    for (const kind of ["double_booked", "over_capacity", "elsewhere", "unavailable"]) {
      const key = conflictWord(kind);
      expect(key).not.toBeNull();
      expect(MESSAGES.en[key!]).toBeTruthy();
      expect(MESSAGES.ar[key!]).toBeTruthy();
    }
  });

  it("falls through to null for a kind this build has no word for", () => {
    // The set is `conflicts.py`'s and may grow; the caller then shows the server's own detail,
    // because hiding a clash somebody has to act on is worse than showing it raw.
    expect(conflictWord("something_new")).toBeNull();
  });
});

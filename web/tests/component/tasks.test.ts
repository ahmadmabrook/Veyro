import { describe, expect, it } from "vitest";

import { MESSAGES, MESSAGE_KEYS, fill, t, type MessageKey } from "@/i18n/locale";
import {
  TASK_VIEWS, UNANSWERABLE, WORK_SOURCES, caseStatusWord, compactDuration, dueLabel,
  dueState, durationWords, isTaskView, metaLine, priorityWord, sheetControls, sourceWord,
  stateWord, subjectKindWord, taskStatusWord, word,
  type AttentionState, type TaskRow,
} from "@/lib/tasks";

/**
 * ADM-TSK-01, ADM-CC-06 and ADM-CC-07's decisions, where they are decided.
 *
 * **The duration is the one worth testing hardest**, because two screens render the same
 * number two ways and the canvas's own fixture pins the format: `12m`, `1h 20m`, `2h 04m`
 * beside "Median 41 minutes". A padded minute after an hour is what keeps a column of
 * durations scannable, and `2h 4m` breaks it.
 */
describe("the duration a case took", () => {
  it("is the canvas's own compact form", () => {
    // Read off ADM-CC-07's `RESOLVED` fixture, which is the only statement of the format.
    expect(compactDuration(12 * 60)).toBe("12m");
    expect(compactDuration(80 * 60)).toBe("1h 20m");
    expect(compactDuration(124 * 60)).toBe("2h 04m");
    expect(compactDuration(6 * 60)).toBe("6m");
    // ADM-CC-06's AGE fact.
    expect(compactDuration(134 * 60)).toBe("2h 14m");
  });

  it("pads the minutes after an hour and not before one", () => {
    expect(compactDuration(60 * 60 + 4 * 60)).toBe("1h 04m");
    expect(compactDuration(4 * 60)).toBe("4m");
  });

  it("says so under a minute rather than rounding to zero", () => {
    // `0m` against a case resolved in forty seconds reads as a missing figure.
    expect(compactDuration(40)).toBe("<1m");
    expect(compactDuration(0)).toBe("<1m");
  });

  it("never puts a fraction or a NaN into the one number path", () => {
    // **The guard that matters is the non-finite one**, which the mutation sweep is what
    // established: flooring the seconds before the division was redundant, because the
    // division and the modulus produce integers whatever the input. `NaN` is the reachable
    // case -- the sheet's age is `now - Date.parse(opened_at)` -- and `formatInteger` throws
    // on it, which is a 500 on the page rather than a wrong number on it.
    for (const seconds of [59.9, 61.5, 3_601.7, 7_444.2]) {
      expect(() => compactDuration(seconds)).not.toThrow();
    }
    expect(compactDuration(3_601.7)).toBe("1h 00m");
    expect(() => compactDuration(Number.NaN)).not.toThrow();
    expect(compactDuration(Number.NaN)).toBe("<1m");
    expect(compactDuration(Number.POSITIVE_INFINITY)).toBe("<1m");
    expect(compactDuration(-90)).toBe("<1m");
    // And the prose rendering takes the same path, so the two cannot disagree about it.
    expect(durationWords(Number.NaN, "en")).toBe("under a minute");
  });

  it("is prose in the sub-line and the two agree on the number", () => {
    expect(durationWords(41 * 60, "en")).toBe("41 minutes");
    expect(durationWords(60 * 60, "en")).toBe("1 hour");
    expect(durationWords(124 * 60, "en")).toBe("2 hours 4 minutes");
    expect(durationWords(40, "en")).toBe("under a minute");
  });

  it("joins the two units with the conjunction the language wants", () => {
    // **English puts a space and Arabic puts a conjunction**, so a page concatenating two
    // plural phrases would put English structure into an Arabic line. The joiner is its own
    // message for that reason, and this asserts it is used rather than assumed.
    const arabic = durationWords(124 * 60, "ar");
    expect(arabic).toContain("و");
    expect(arabic).not.toBe("2 hours 4 minutes");
  });
});

describe("when a task is due", () => {
  const now = new Date("2026-08-19T09:00:00Z");

  it("reads today, tomorrow, a count, or a date", () => {
    expect(dueState("2026-08-19T23:00:00Z", now)).toEqual({ kind: "today" });
    expect(dueState("2026-08-20T06:00:00Z", now)).toEqual({ kind: "tomorrow" });
    expect(dueState("2026-08-26T06:00:00Z", now)).toEqual({ kind: "days", days: 7 });
    expect(dueState("2026-09-30T06:00:00Z", now)).toEqual({ kind: "date" });
    expect(dueState(null, now)).toEqual({ kind: "none" });
  });

  it("counts an overdue task in whole days", () => {
    // The canvas's own "overdue 2d".
    expect(dueState("2026-08-17T06:00:00Z", now)).toEqual({ kind: "overdue", days: 2 });
    expect(dueState("2026-08-18T06:00:00Z", now)).toEqual({ kind: "overdue", days: 1 });
  });

  /**
   * **Overdue is the instant and the rest is the calendar day, and the two are not the same
   * question.** The server's filter is `due_at < now()`, and the first version of `dueState`
   * compared dates on both sides -- so a task due at nine this morning read "due today" at
   * five in the afternoon while the Overdue chip above the table counted it. One board, two
   * definitions of late, found by the browser layer asserting that every row in the overdue
   * view says so.
   */
  it("calls a passed instant overdue and a later one today", () => {
    const afternoon = new Date("2026-08-19T17:00:00Z");
    expect(dueState("2026-08-19T09:00:00Z", afternoon))
      .toEqual({ kind: "overdue", days: 0 });
    expect(dueState("2026-08-19T21:00:00Z", afternoon)).toEqual({ kind: "today" });
  });

  it("takes `now` rather than reading the clock", () => {
    // Four defects in this repository had a green that depended on when the suite ran. A
    // date function that reads its own clock cannot be asserted at all near midnight.
    const midnight = new Date("2026-08-19T23:59:59Z");
    // Earlier today and already past: overdue by no whole days, which is its own label
    // because "overdue 0 days" is not a sentence.
    expect(dueState("2026-08-19T00:00:00Z", midnight))
      .toEqual({ kind: "overdue", days: 0 });
    expect(dueState("2026-08-20T00:00:00Z", midnight)).toEqual({ kind: "tomorrow" });
  });

  it("is measured in UTC days, like every other date on these surfaces", () => {
    // A tenant with clubs in two zones has two local todays and a task carries neither, so
    // labelling the day in any one site's zone would be wrong for the other.
    const now = new Date("2026-08-19T21:00:00Z");
    expect(dueState("2026-08-19T22:00:00Z", now)).toEqual({ kind: "today" });
  });
});

describe("ADM-CC-06's five states", () => {
  it("renders every action in every state and makes only some live", () => {
    // The canvas's most specific rule: assigned to somebody else "keeps every action visible
    // but read-only, with 'Nadia is handling this' and a Take over that records the
    // handover". So the handover is the one live control in the one state that is otherwise
    // inert -- hiding the rest would make the sheet a different screen per reader.
    const other = sheetControls("someone_else");
    expect(other.live).toBe(false);
    expect(other.takeOver).toBe(true);
    expect(other.snooze).toBe(false);
    expect(other.resolve).toBe(false);
  });

  it("offers the claim where nobody holds it and the release where this reader does", () => {
    expect(sheetControls("unassigned").assignToMe).toBe(true);
    expect(sheetControls("unassigned").release).toBe(false);
    expect(sheetControls("mine").release).toBe(true);
    expect(sheetControls("mine").assignToMe).toBe(false);
  });

  it("offers the return a deferral needs, and nothing on a resolved item", () => {
    // **The remedy is what makes the routine deferral safe**: a return date typed as next
    // year would otherwise hide an exception for eleven months with no way back.
    expect(sheetControls("snoozed").returnToQueue).toBe(true);
    expect(sheetControls("snoozed").snooze).toBe(false);
    // Reopen is the canvas's one action on a resolved item and is not built; the screen says
    // so rather than offering a control that would be refused.
    expect(sheetControls("resolved")).toEqual({
      live: false, assignToMe: false, release: false, takeOver: false,
      snooze: false, returnToQueue: false, resolve: false,
    });
  });

  it("never offers a claim and a release at once, in any state", () => {
    const states: AttentionState[] = [
      "unassigned", "mine", "someone_else", "resolved", "snoozed"];
    for (const state of states) {
      const controls = sheetControls(state);
      expect(controls.assignToMe && controls.release).toBe(false);
      // And `live` is false wherever nothing is live, so the page's one branch is honest.
      const any = controls.assignToMe || controls.release || controls.snooze
        || controls.returnToQueue || controls.resolve;
      expect(any).toBe(controls.live);
    }
  });
});

describe("a stored vocabulary is never a label", () => {
  it("maps every value each module declares", () => {
    for (const source of WORK_SOURCES) expect(sourceWord(source)).not.toBeNull();
    for (const status of ["open", "in_progress", "blocked", "done", "cancelled"]) {
      expect(taskStatusWord(status)).not.toBeNull();
    }
    for (const status of ["open", "resolved", "closed"]) {
      expect(caseStatusWord(status)).not.toBeNull();
    }
    for (const priority of ["low", "normal", "high", "urgent"]) {
      expect(priorityWord(priority)).not.toBeNull();
    }
    // AUT-02-R01's nine subject kinds, which `subjects.py` carries in the same order.
    for (const kind of ["member", "lead", "tenant", "invoice", "incident", "device",
      "booking", "asset", "workflow"]) {
      expect(subjectKindWord(kind)).not.toBeNull();
    }
    for (const state of ["unassigned", "mine", "someone_else", "resolved", "snoozed"]) {
      expect(stateWord(state)).not.toBeNull();
    }
  });

  it("returns null for a value it does not know, so the row shows it as stored", () => {
    // The members list's own judgement: the set is MOD-026's and may grow, and these are the
    // screens somebody filters and acts on -- hiding an unrecognised state behind "other"
    // would hide the row.
    expect(sourceWord("telepathy")).toBeNull();
    expect(taskStatusWord("semi_done")).toBeNull();
    expect(stateWord("parked")).toBeNull();
  });

  /**
   * **`MESSAGE_KEYS` is structurally blind to a string that never became a key**, so the
   * parity check cannot see a map whose values are English prose. This is that check run from
   * the side the catalogue cannot see: every key this module maps to exists in both
   * catalogues. MOD-013's board shipped eight English decision reasons onto an otherwise
   * correct Arabic page for exactly this reason.
   */
  it("maps only to keys both catalogues carry", () => {
    const keys: (MessageKey | null)[] = [
      ...WORK_SOURCES.map(sourceWord),
      ...["open", "in_progress", "blocked", "done", "cancelled"].map(taskStatusWord),
      ...["open", "resolved", "closed"].map(caseStatusWord),
      ...["low", "normal", "high", "urgent"].map(priorityWord),
      ...["member", "lead", "tenant", "invoice", "incident", "device", "booking", "asset",
        "workflow"].map(subjectKindWord),
      ...["unassigned", "mine", "someone_else", "resolved", "snoozed"].map(stateWord),
      ...Object.values(UNANSWERABLE),
    ];
    for (const key of keys) {
      expect(key).not.toBeNull();
      expect(MESSAGE_KEYS).toContain(key!);
      expect(MESSAGES.en[key!]).toBeDefined();
      expect(MESSAGES.ar[key!]).toBeDefined();
    }
  });

  it("renders the Arabic words in Arabic, which no structural check can see", () => {
    // Found by switching the language and looking at the page, which is how MOD-013's board's
    // eight English reasons were found. The assertion is that the string is not Latin.
    for (const source of WORK_SOURCES) {
      const arabic = t("ar", sourceWord(source)!);
      expect(arabic).toMatch(/[؀-ۿ]/);
      expect(arabic).not.toBe(t("en", sourceWord(source)!));
    }
  });
});

describe("ADM-TSK-01's three views", () => {
  it("are the canvas's own three, in its order", () => {
    expect([...TASK_VIEWS]).toEqual(["mine", "team", "overdue"]);
  });

  it("refuse anything else, so a query string cannot invent a fourth", () => {
    expect(isTaskView("mine")).toBe(true);
    expect(isTaskView("everything")).toBe(false);
    expect(isTaskView(undefined)).toBe(false);
    expect(isTaskView(7)).toBe(false);
  });

  it("each have a chip message carrying the count in both languages", () => {
    for (const key of ["tasks.chipMine", "tasks.chipTeam", "tasks.chipOverdue"] as const) {
      expect(fill("en", key, { count: 4 })).toContain("4");
      expect(fill("ar", key, { count: 4 })).toContain("4");
    }
  });
});

/**
 * ADM-TSK-01's meta line and its five due forms, which were page-local until the browser layer
 * showed why they must not be.
 *
 * **Three of the eight branches here have no browser fixture**, and that is what moving them
 * into the library is for: "due tomorrow", a task with no due date, and an exception whose
 * reference this reader may not read are all states the product produces and the seeded tenant
 * does not. A branch no fixture reaches is this repository's own recurring vacuity, found four
 * times in four modules on a surface -- so the ones a fixture cannot reach are asserted here
 * rather than left to look tested.
 */
describe("the meta line a task row carries", () => {
  const now = new Date("2026-08-19T09:00:00Z");
  const task = (over: Partial<TaskRow> = {}): TaskRow => ({
    task_id: "t", queue_id: "q", case_id: null, title: "Call Tareq",
    subject_kind: "tenant", subject_id: null, subject_is_a_recorded_claim: false,
    assignee_person_id: null, priority: "normal", status: "open",
    due_at: "2026-08-21T09:00:00Z", evidence_ref: null,
    created_at: "2026-08-01T09:00:00Z", settled_at: null, settle_reason: null,
    reason_masked: false, source: "manual", ...over,
  });

  it("names the exception where the reference can be read", () => {
    const line = metaLine(
      "en", task({ case_id: "c1" }), new Map([["c1", "EXC-8841"]]), now, "latn");
    expect(line).toContain("From exception EXC-8841");
    expect(line).not.toContain("Assigned by a person");
  });

  it("names the exception without a reference where it cannot", () => {
    // `tasks.case.read` is a separate permission, so a reader without it gets the fact and not
    // a uuid printed where a human reference belongs. No browser fixture: the owner holds it.
    const line = metaLine("en", task({ case_id: "c1" }), new Map(), now, "latn");
    expect(line).toContain("From an exception");
    expect(line).not.toContain("c1");
  });

  it("names how the task came to exist where no exception did", () => {
    expect(metaLine("en", task({ source: "automation" }), new Map(), now, "latn"))
      .toContain("Generated by an automation");
  });

  it("leaves out the tenant subject and the normal priority", () => {
    // Both are on every row and neither carries information on most of them: printing "This
    // organization" against six of seven rows is the canvas's two-part line padded with noise.
    const line = metaLine("en", task(), new Map(), now, "latn");
    expect(line).not.toContain("This organization");
    expect(line).not.toContain("Normal");
    const loud = metaLine(
      "en", task({ subject_kind: "member", priority: "high" }), new Map(), now, "latn");
    expect(loud).toContain("Member");
    expect(loud).toContain("High");
  });

  it("renders all five due forms, including the two no fixture reaches", () => {
    const at = (dueAt: string | null) =>
      dueLabel("en", dueState(dueAt, now), dueAt, now, "latn");
    expect(at("2026-08-19T18:00:00Z")).toBe("due today");
    expect(at("2026-08-20T09:00:00Z")).toBe("due tomorrow");
    expect(at("2026-08-24T09:00:00Z")).toBe("due in 5 days");
    expect(at("2026-09-30T09:00:00Z")).toBe("due 30 Sep");
    expect(at("2026-08-17T09:00:00Z")).toBe("overdue 2 days");
    // Zero whole days late, which is its own message because "overdue 0 days" is not a
    // sentence and English's plural rules pick `other` for 0.
    expect(at("2026-08-19T06:00:00Z")).toBe("overdue");
    expect(at(null)).toBe("no due date");
  });

  it("renders them in Arabic too, which no structural check can see", () => {
    const at = (dueAt: string | null) =>
      dueLabel("ar", dueState(dueAt, now), dueAt, now, "latn");
    for (const dueAt of [
      "2026-08-19T18:00:00Z", "2026-08-20T09:00:00Z", "2026-08-24T09:00:00Z",
      "2026-08-17T09:00:00Z", "2026-08-19T06:00:00Z", null,
    ]) {
      expect(at(dueAt)).toMatch(/[؀-ۿ]/);
    }
  });

  it("shows an unrecognised value as stored rather than hiding the row", () => {
    expect(word("en", null, "semi_done")).toBe("semi_done");
    expect(word("en", "tasks.statusOpen", "open")).toBe("Open");
  });
});

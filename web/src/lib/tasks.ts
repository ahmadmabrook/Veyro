import { fill, formatInteger, t, type Locale, type MessageKey, type Numbering }
  from "@/i18n/locale";
import { dayLabel } from "@/lib/time";

/**
 * ADM-TSK-01, ADM-CC-06 and ADM-CC-07 — the decisions the three task surfaces make, with no
 * I/O in any of them.
 *
 * **Here rather than beside each page, because all three read the same three facts** — a
 * source, a state and a duration — and the canvases are explicit that each of those is a
 * word rather than a number: "The source is always named — a task nobody can account for
 * gets ignored", ADM-CC-06's five states, and ADM-CC-07's "Median 41 minutes". A second copy
 * of any of them is how two screens come to spell one thing two ways, which this repository
 * has already paid for five times (`lifecycle_state`, the membership plan words, the wallet's
 * value kinds, a visit's credential kind, and the design system's own badge).
 *
 * **No stored vocabulary is rendered as a label.** `MESSAGE_KEYS` compares the two
 * catalogues against each other and is structurally blind to a string that never became a
 * key, so an English enum printed into an Arabic line is invisible to every layer except
 * looking at the page. Each `*Word` function returns a `MessageKey` or `null`, and `null`
 * means "show it as stored" rather than "other": these are the screens somebody filters and
 * acts on, so hiding an unrecognised state behind a catch-all would hide the row.
 */

export type WorkSource = "manual" | "automation" | "ai";

/** The three ADM-TSK-01 names, in its own order. */
export const WORK_SOURCES: readonly WorkSource[] = ["manual", "automation", "ai"] as const;

/** ADM-CC-06's five states, as `attention.item_state` derives them. */
export type AttentionState =
  | "unassigned" | "mine" | "someone_else" | "resolved" | "snoozed";

/** ADM-TSK-01's three chips, which are also the three views the list offers. */
export type TaskView = "team" | "mine" | "overdue";

export const TASK_VIEWS: readonly TaskView[] = ["mine", "team", "overdue"] as const;

export function isTaskView(value: unknown): value is TaskView {
  return typeof value === "string" && (TASK_VIEWS as readonly string[]).includes(value);
}

export type TaskRow = {
  task_id: string;
  queue_id: string;
  case_id: string | null;
  title: string;
  subject_kind: string;
  subject_id: string | null;
  subject_is_a_recorded_claim: boolean;
  assignee_person_id: string | null;
  priority: string;
  status: string;
  due_at: string | null;
  evidence_ref: string | null;
  created_at: string;
  settled_at: string | null;
  settle_reason: string | null;
  reason_masked: boolean;
  source: string;
};

export type QueueRow = {
  queue_id: string;
  queue_key: string;
  /**
   * **`display_name`, which is what the route sends.** The first version of this type called
   * it `name` and every queue on the board rendered as the fallback word "Queue" -- a
   * hand-written type over an untyped JSON response is invisible to every typecheck, which is
   * the `AccessDecision.masked` finding this repository already records. Read the response.
   */
  display_name: string;
  location_id: string | null;
  status: string;
};

export type CaseRow = {
  case_id: string;
  case_number: string;
  title: string;
  queue_id: string;
  subject_kind: string;
  subject_id: string | null;
  subject_is_a_recorded_claim: boolean;
  priority: string;
  status: string;
  opened_at: string;
  resolved_at: string | null;
  resolution_reason: string | null;
  reason_masked: boolean;
  recurs_from_case_id: string | null;
  source: string;
  assignee_person_id: string | null;
  snoozed_until: string | null;
  snooze_reason: string | null;
};

export type AffectedRecord = {
  affected_kind: string;
  affected_id: string;
  added_at: string;
  added_by: string;
  subject_is_a_recorded_claim: boolean;
};

export type WithdrawnRecord = {
  affected_kind: string;
  affected_id: string;
  withdrawn_at: string;
  withdrawn_by: string;
  withdraw_reason: string | null;
};

export type CaseEntry = {
  entry_kind: string;
  summary: string;
  occurred_at: string;
  recorded_by: string;
  document_ref: string | null;
};

export type AttentionItem = CaseRow & {
  opened_by: string;
  resolved_by: string | null;
  snoozed_at: string | null;
  state: AttentionState;
  actions_are_live: boolean;
  took_seconds: number | null;
  running_sla_clock_id: string | null;
  entries: CaseEntry[];
  affected: AffectedRecord[];
  withdrawn: WithdrawnRecord[];
  affected_count: number;
};

export type ResolvedCase = {
  case_id: string;
  case_number: string;
  title: string;
  queue_id: string;
  resolved_by: string | null;
  resolved_at: string;
  took_seconds: number;
  status: string;
  source: string;
  outcome: string | null;
  reason_masked: boolean;
};

export type ResolvedPage = {
  window_hours: number;
  since: string;
  resolved: number;
  median_seconds: number | null;
  cases: ResolvedCase[];
  no_un_resolve: string;
};

export type Workload = {
  as_of: string;
  window_hours: number;
  queue_id: string | null;
  mine: number;
  team: number;
  overdue: number;
  mine_is_zero_without_a_person_record: boolean;
  per_queue: { queue_id: string; status: string; open: number }[];
  aging: {
    bucket_days: number[];
    under_a_day: number;
    under_a_week: number;
    under_a_month: number;
    older: number;
  };
  bottleneck: { task_id: string; blocking: number }[];
  outcome: { status: string; source: string; settled: number }[];
  compliance: {
    met: number;
    breached: number;
    running: number;
    cancelled: number;
    met_basis_points: number | null;
  };
};

const SOURCE_WORDS: Record<string, MessageKey> = {
  manual: "tasks.sourceManual",
  automation: "tasks.sourceAutomation",
  ai: "tasks.sourceAi",
};

/** "assigned by a person · generated by an automation · suggested by Veyro". */
export function sourceWord(stored: string): MessageKey | null {
  return SOURCE_WORDS[stored] ?? null;
}

const TASK_STATUS_WORDS: Record<string, MessageKey> = {
  open: "tasks.statusOpen",
  in_progress: "tasks.statusInProgress",
  blocked: "tasks.statusBlocked",
  done: "tasks.statusDone",
  cancelled: "tasks.statusCancelled",
};

export function taskStatusWord(stored: string): MessageKey | null {
  return TASK_STATUS_WORDS[stored] ?? null;
}

const CASE_STATUS_WORDS: Record<string, MessageKey> = {
  open: "tasks.caseOpen",
  resolved: "tasks.caseResolved",
  closed: "tasks.caseClosed",
};

export function caseStatusWord(stored: string): MessageKey | null {
  return CASE_STATUS_WORDS[stored] ?? null;
}

const STATE_WORDS: Record<AttentionState, MessageKey> = {
  unassigned: "tasks.stateUnassigned",
  mine: "tasks.stateMine",
  someone_else: "tasks.stateSomeoneElse",
  resolved: "tasks.stateResolved",
  snoozed: "tasks.stateSnoozed",
};

export function stateWord(state: string): MessageKey | null {
  return STATE_WORDS[state as AttentionState] ?? null;
}

const PRIORITY_WORDS: Record<string, MessageKey> = {
  low: "tasks.priorityLow",
  normal: "tasks.priorityNormal",
  high: "tasks.priorityHigh",
  urgent: "tasks.priorityUrgent",
};

export function priorityWord(stored: string): MessageKey | null {
  return PRIORITY_WORDS[stored] ?? null;
}

const SUBJECT_WORDS: Record<string, MessageKey> = {
  member: "tasks.subjectMember",
  lead: "tasks.subjectLead",
  tenant: "tasks.subjectTenant",
  invoice: "tasks.subjectInvoice",
  incident: "tasks.subjectIncident",
  device: "tasks.subjectDevice",
  booking: "tasks.subjectBooking",
  asset: "tasks.subjectAsset",
  workflow: "tasks.subjectWorkflow",
};

export function subjectKindWord(stored: string): MessageKey | null {
  return SUBJECT_WORDS[stored] ?? null;
}

/**
 * `12m`, `1h 20m`, `2h 04m` — the compact duration ADM-CC-06's AGE fact and ADM-CC-07's TOOK
 * column are set in.
 *
 * **Mono data in Latin numerals, like every other `data` span here**, and built from two
 * integers through `formatInteger` rather than from a second number formatter: this app has
 * exactly one number-rendering path and a cross-runtime parity test that compares it against
 * the backend's character for character, because a receipt is rendered by the backend.
 *
 * **The minutes are padded when the hours are shown**, which is the canvas's own `2h 04m`
 * beside `1h 20m`. That is a presentation choice applied to an already-formatted integer, not
 * a second formatting rule: a column of durations is scanned vertically and `2h 4m` breaks
 * the alignment that makes the scan work.
 *
 * **Under a minute says so rather than rounding to zero.** `0m` against a case somebody
 * resolved in forty seconds reads as a missing figure; the canvas's smallest row is `6m`, so
 * it does not settle the question and the honest form does.
 */
export function compactDuration(seconds: number, numbering: Numbering = "latn"): string {
  const minutes = wholeMinutes(seconds);
  if (minutes < 1) return "<1m";
  const hours = Math.floor(minutes / 60);
  if (hours === 0) return `${formatInteger(minutes, numbering)}m`;
  const pad = formatInteger(minutes % 60, numbering).padStart(2, "0");
  return `${formatInteger(hours, numbering)}h ${pad}m`;
}

/**
 * Seconds as a whole number of minutes, and the one normalisation both renderings need.
 *
 * **This is where a guard is load-bearing and the obvious places are not**, which the mutation
 * sweep is what established: `Math.floor(seconds)` before the division was redundant, because
 * `Math.floor(seconds / 60)` and `% 60` produce integers whatever the input, and `Math.max(0,
 * …)` was redundant too, because every negative is already under a minute. Removing either
 * changed nothing and the sweep said so.
 *
 * What is *not* redundant is the non-finite case, and it is reachable rather than theoretical:
 * the sheet's age is `now - Date.parse(opened_at)`, which is `NaN` for an instant that does not
 * parse — and `NaN` is neither under a minute nor an integer, so it reaches `formatInteger`,
 * which throws. `fill` is how every figure on these pages is rendered, so that is a 500 on the
 * screen rather than a wrong number on it.
 *
 * `0` for an unanswerable input, which the callers render as "under a minute": wrong in a way
 * that says "no time has passed" rather than in a way that takes the page down, and the
 * alternative — a figure built from a value that is not a number — is not available.
 */
function wholeMinutes(seconds: number): number {
  if (!Number.isFinite(seconds) || seconds <= 0) return 0;
  return Math.floor(seconds / 60);
}

/**
 * The same duration as prose — "41 minutes", "2 hours 4 minutes" — for ADM-CC-07's sub-line,
 * which the canvas writes as "Median 41 minutes · all locations".
 *
 * **Two renderings of one number, both from the seconds the server computed.** The grid cell
 * is mono in a narrow column and the sub-line is a sentence, and the canvas sets them
 * differently; what would be wrong is two *definitions*, which is why the median itself is
 * `list_resolved`'s and neither of these recomputes it.
 *
 * **The joiner is its own message.** English puts a space between the two units and Arabic
 * puts a conjunction, so a page concatenating two plural phrases would put English structure
 * into an Arabic line -- `fill`'s own argument, one level up.
 */
export function durationWords(
  seconds: number,
  locale: Locale,
  numbering: Numbering = "latn",
): string {
  const minutes = wholeMinutes(seconds);
  if (minutes < 1) return t(locale, "tasks.underAMinute");
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  const minuteWords = (n: number) =>
    fill(locale, "tasks.minutes", { count: n }, numbering);
  if (hours === 0) return minuteWords(minutes);
  const hourWords = fill(locale, "tasks.hours", { count: hours }, numbering);
  if (rest === 0) return hourWords;
  return fill(
    locale, "tasks.hoursAndMinutes", { hours: hourWords, minutes: minuteWords(rest) });
}

/**
 * Which of ADM-TSK-01's five due forms a task is in — "due today", "overdue 2d", "due in
 * 18d", "due 25 Aug", or nothing at all.
 *
 * **Pure, and it takes `now`**, because a test that asserts "due today" has to be able to say
 * when today is: this repository has four recorded defects whose green depended on when the
 * suite ran.
 *
 * **Measured in whole days against the reader's own UTC day**, which is `dayLabel`'s rule and
 * for its reason: a tenant with clubs in two zones has two local todays and a task carries
 * neither, so labelling the day in any one site's zone would be wrong for the other.
 */
export type DueState =
  | { kind: "none" }
  | { kind: "overdue"; days: number }
  | { kind: "today" }
  | { kind: "tomorrow" }
  | { kind: "days"; days: number }
  | { kind: "date" };

/** Past this many days ahead a day count stops being useful and the date is clearer. */
export const DUE_DAYS_AHEAD = 14;

export function dueState(dueAt: string | null, now: Date): DueState {
  if (dueAt === null) return { kind: "none" };
  const at = Date.parse(dueAt);
  if (Number.isNaN(at)) return { kind: "none" };
  // **Overdue is the instant, not the calendar day, because that is what the filter counts.**
  // `due_at` is a timestamptz and the server's overdue filter is `due_at < now()`; the first
  // version of this compared dates, so a task due at nine this morning read "due today" at
  // five in the afternoon while the Overdue chip counted it -- the board's own figure
  // disagreeing with the row beside it. Found by the browser layer, which asserted that every
  // row in the overdue view says so.
  if (at < now.getTime()) {
    const days = Math.floor((now.getTime() - at) / 86_400_000);
    return { kind: "overdue", days };
  }
  // Ahead of it, the bucket is the calendar day: "due tomorrow" is about a date somebody
  // reads, not about the next twenty-four hours.
  const due = dueAt.slice(0, 10);
  const today = now.toISOString().slice(0, 10);
  if (due === today) return { kind: "today" };
  const days = Math.round(
    (Date.parse(`${due}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)) / 86_400_000);
  if (Number.isNaN(days)) return { kind: "none" };
  if (days === 1) return { kind: "tomorrow" };
  if (days <= DUE_DAYS_AHEAD) return { kind: "days", days };
  return { kind: "date" };
}

/**
 * ADM-CC-06's five states and the controls each one offers.
 *
 * **Every action is rendered in every state and only some of them do anything**, which is the
 * canvas's own rule for the state it is most specific about: assigned to someone else "keeps
 * every action visible but read-only, with 'Nadia is handling this' and a Take over that
 * records the handover". Hiding the actions would make the sheet look like a different screen
 * depending on who opened it -- and a reader who could not see that a snooze exists would ask
 * for it. So `live` is the one flag the page branches on, and `takeOver` is live in the one
 * state where nothing else is.
 */
export type SheetControls = {
  /** Whether this reader may act, which `attention.may_act` decides on the server too. */
  live: boolean;
  assignToMe: boolean;
  release: boolean;
  takeOver: boolean;
  snooze: boolean;
  returnToQueue: boolean;
  resolve: boolean;
};

export function sheetControls(state: AttentionState): SheetControls {
  const inert: SheetControls = {
    live: false, assignToMe: false, release: false, takeOver: false,
    snooze: false, returnToQueue: false, resolve: false,
  };
  switch (state) {
    case "unassigned":
      return { ...inert, live: true, assignToMe: true, snooze: true, resolve: true };
    case "mine":
      return { ...inert, live: true, release: true, snooze: true, resolve: true };
    case "someone_else":
      // Read-only, except the handover — which is the whole point of the state.
      return { ...inert, takeOver: true };
    case "snoozed":
      return { ...inert, live: true, returnToQueue: true, resolve: true };
    case "resolved":
      // Reopen is the canvas's one action here and is not built; `tasks.resolvedNoReopen`
      // says why on the screen rather than leaving a reader to find out by looking for it.
      return inert;
  }
}

/**
 * What the three screens cannot do, each with the product's own reason.
 *
 * Named on the page rather than quietly missing, which is this app's standing rule: a control
 * absent with no reason reads as a permission the reader lacks, and they go and ask for a
 * grant that does not exist.
 */
export const UNANSWERABLE = {
  /** ADM-TSK-01's `Assigned by Rania`. */
  assignedBy: "tasks.gapAssignedBy",
  /** ADM-CC-06's `Send 6 payment links`. */
  batchMessage: "tasks.gapBatchMessage",
  /** ADM-CC-06's resolved state. */
  reopen: "tasks.gapReopen",
  /** ADM-CC-06 is a sheet over the Command Center, and nothing routes into it. */
  sideSheet: "tasks.gapSideSheet",
  /** The 30-second undo the canvas puts on a resolution. */
  undo: "tasks.gapUndo",
  /** "A Club Manager sees only the two members at their club". */
  scope: "tasks.gapScope",
  /** The affected records "each link to its member". */
  affectedNames: "tasks.gapAffectedNames",
} as const satisfies Record<string, MessageKey>;

/**
 * The canvas's second line: "From exception EXC-8804 · due today".
 *
 * **Three forms, and the first half is the task's provenance rather than its source word.**
 * A task citing a case names the exception; one that does not names how it came to exist.
 * They are not alternatives in the data — a task has both — but they are alternatives on the
 * line, because the exception is the more specific of the two and the one the reader can open.
 */
export function metaLine(
  locale: Locale,
  task: TaskRow,
  caseNumbers: Map<string, string>,
  now: Date,
): string {
  const provenance = task.case_id === null
    ? word(locale, sourceWord(task.source), task.source)
    : (() => {
        const reference = caseNumbers.get(task.case_id);
        return reference === undefined
          ? t(locale, "tasks.fromExceptionUnnamed")
          : fill(locale, "tasks.fromException", { ref: reference });
      })();
  const parts = [
    provenance,
    dueLabel(locale, dueState(task.due_at, now), task.due_at, now),
  ];
  // **The subject only when it is not the tenant, and the priority only when it is not
  // normal.** Both are on every row and neither carries information on most of them: a task
  // about the organization itself has `subject_kind = "tenant"` by design -- its subject is
  // the row's own `tenant_id`, which RLS already bounds -- so printing "This organization"
  // against six of seven rows is the canvas's two-part meta line padded with noise. Found by
  // rendering the page and reading it, which is how the schedule board's wrong timezone was
  // found too.
  const subject = subjectKindWord(task.subject_kind);
  if (subject !== null && task.subject_kind !== "tenant") parts.push(t(locale, subject));
  const priority = priorityWord(task.priority);
  if (priority !== null && task.priority !== "normal") parts.push(t(locale, priority));
  return parts.join(" · ");
}

/**
 * ADM-TSK-01's five due forms.
 *
 * **The far one is a date rather than a day count**, which is the canvas's own "due 25 Aug":
 * past a fortnight a count stops being something a reader can place. `dayLabel` is the
 * repository's one date-in-a-gutter formatter and it is UTC-pinned for `dueState`'s reason.
 */
export function dueLabel(
  locale: Locale,
  due: ReturnType<typeof dueState>,
  dueAt: string | null,
  now: Date,
): string {
  switch (due.kind) {
    case "none": return t(locale, "tasks.noDue");
    case "today": return t(locale, "tasks.dueToday");
    case "tomorrow": return t(locale, "tasks.dueTomorrow");
    // **Zero days late is "overdue" with no count**, because "overdue 0 days" is not a
    // sentence -- and English's plural rules would pick it, since `other` covers 0. A task
    // due at nine this morning is overdue at five this afternoon and by no whole days.
    case "overdue":
      return due.days === 0
        ? t(locale, "tasks.overdueToday")
        : fill(locale, "tasks.overdueDays", { count: due.days });
    case "days": return fill(locale, "tasks.dueInDays", { count: due.days });
    case "date":
      return fill(locale, "tasks.dueOn", {
        date: dueAt === null ? "" : dayLabel(dueAt, now),
      });
  }
}

/**
 * A stored vocabulary word in the reader's language, or as stored when it is unknown.
 *
 * **Shown rather than hidden behind "other"**, which is the members list's own judgement: the
 * set is MOD-026's and may grow, and these are the screens somebody filters and acts on, so
 * hiding an unrecognised status would hide the row.
 */
export function word(locale: Locale, key: MessageKey | null, stored: string): string {
  return key === null ? stored : t(locale, key);
}

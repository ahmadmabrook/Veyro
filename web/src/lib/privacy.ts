import { api } from "@/lib/api";

/**
 * MOD-009's reads, typed: what this tenant processes, what it keeps, what it is holding, who
 * has asked for their data — and what this build cannot erase.
 *
 * **The last of those is the one with nowhere to live.** `deletion_is_complete()` returns
 * False and `plan_dsar` surfaces it per request, so the honest answer to "what can you delete"
 * was reachable only after somebody had asked you to delete something. The registry behind it
 * was visible in Python and in a test and nowhere a privacy officer could look. `GET
 * /privacy/erasure-reach` is that registry, and it reads nobody's rows: a tenant appears
 * nowhere in the answer, which is what makes it a statement about the software.
 *
 * **Five permissions, five blocks.** `privacy.purpose.read`, `privacy.retention.read`,
 * `privacy.dsar.read` and `privacy.incident.read` are separate, and a reader may hold any
 * subset. A refused block says so rather than rendering empty, because "this tenant has no
 * legal holds" and "you may not see them" are different facts and only the first is about the
 * tenant.
 */

export type ProcessingPurpose = {
  purpose_id: string;
  purpose_code: string;
  description: string;
  lawful_basis: string;
  controller_role: string;
  data_classes: string[];
  registered_at: string;
  retired_at: string | null;
};

export type RetentionPolicy = {
  policy_id: string;
  resource_type: string;
  data_class: string;
  retention_days: number;
  legal_basis: string;
  region: string | null;
  set_at: string;
};

export type LegalHold = {
  hold_id: string;
  subject_id: string | null;
  resource_type: string | null;
  reason: string;
  reference: string;
  placed_at: string;
  released_at: string | null;
  release_reason: string | null;
  placed_by: string;
  released_by: string | null;
};

export type DataSubjectRequest = {
  request_id: string;
  subject_id: string;
  request_type: string;
  status: string;
  received_at: string;
  due_at: string;
  completed_at: string | null;
  /** Derived by the server against its own clock, not by this page against the browser's. */
  overdue: boolean;
};

export type SecurityIncident = {
  incident_id: string;
  supersedes_incident_id: string | null;
  severity: string;
  category: string;
  summary: string;
  detected_at: string;
  personal_data_involved: string;
  notification_assessment: string | null;
  recorded_at: string;
};

export type ReachEntry = {
  schema: string;
  table: string;
  column: string;
  locate_by: string;
  clears: string[];
  reason: string;
};

export type ErasureReach = {
  erasure_is_complete: boolean;
  mechanisms: Record<string, ReachEntry[]>;
  counts: Record<string, number>;
  residue_count: number;
  why_incomplete: string;
};

export function listPurposes(): Promise<ProcessingPurpose[]> {
  return api("/privacy/purposes");
}

export function listRetention(): Promise<RetentionPolicy[]> {
  return api("/privacy/retention");
}

/**
 * Every hold, released ones included.
 *
 * **The route defaults to live holds only and the board wants both.** A released hold is the
 * evidence that a preservation ended, and releasing one is the single act that un-blocks
 * destruction of preserved evidence -- which is why MOD-009's review made its actor and its
 * reason mandatory, after finding that the release recorded nobody anywhere in the system.
 * Showing only the live ones would hide the act with the most consequence attached.
 *
 * The first version of this call omitted the flag while the page rendered a "Released" branch,
 * which made that branch unreachable: a declared state nothing writes, in a surface rather
 * than a service. Caught by the test that asserts both appear.
 */
export function listLegalHolds(): Promise<LegalHold[]> {
  return api("/privacy/legal-holds?include_released=true");
}

export function listRequests(): Promise<DataSubjectRequest[]> {
  return api("/privacy/requests");
}

export function listIncidents(): Promise<SecurityIncident[]> {
  return api("/privacy/incidents");
}

export function readErasureReach(): Promise<ErasureReach> {
  return api("/privacy/erasure-reach");
}

/**
 * A legal hold that is still preserving something.
 *
 * `released_at` is the whole of it: a hold is durable with no expiry, which is why
 * `fulfil_dsar` re-reads holds at the moment it acts rather than trusting the legal check it
 * passed earlier. Litigation ordinarily starts *after* a request is queued, and an erasure
 * that ran under a correctly-served preservation order and reported `completed` is the defect
 * two independent reviewers found in this module.
 */
export function holdIsLive(hold: LegalHold): boolean {
  return hold.released_at === null;
}

/**
 * The requests somebody has to act on, in the order their deadlines fall.
 *
 * Overdue first and then by due date: a regulator-facing deadline is the one number on this
 * screen with a consequence attached. A settled request is not in this list — `completed` and
 * `refused` are both answers, and a board that kept them here would make the queue grow for
 * ever and stop being read.
 */
export function needingAction(requests: DataSubjectRequest[]): DataSubjectRequest[] {
  // **Sorted by the deadline alone, because overdue-first is implied by it.** The first
  // version compared `overdue` before the date, and the mutation sweep reported that
  // comparison as uncaught: an overdue request is one whose due date has passed and a
  // not-overdue one is a date still to come, so a date sort already puts every overdue
  // request ahead of every other. The comparison was dead logic that read as a control --
  // the same judgement the backend rules file records for a constraint subsumed by a
  // sibling, which is to delete it and keep the primitive statement rather than write a
  // case that cannot exist.
  return requests
    .filter((r) => r.status !== "completed" && r.status !== "refused")
    .sort((a, b) => a.due_at.localeCompare(b.due_at));
}

/**
 * Which mechanisms destroy identifying material and which are the residue.
 *
 * Four of the six do something; `unreachable` and `write_once` are what survives. They are
 * kept apart from each other too: `unreachable` is the database refusing — no UPDATE grant and
 * no DELETE — and `write_once` is a service writing once with no erasure path clearing it,
 * which is weaker and is the truer word for five columns that used to claim the stronger one.
 */
export const RESIDUE_MECHANISMS = ["unreachable", "write_once"] as const;

export function residueOf(reach: ErasureReach): ReachEntry[] {
  return RESIDUE_MECHANISMS.flatMap((m) => reach.mechanisms[m] ?? []);
}

export function erasesOf(reach: ErasureReach): ReachEntry[] {
  return Object.entries(reach.mechanisms)
    .filter(([m]) => !(RESIDUE_MECHANISMS as readonly string[]).includes(m))
    .flatMap(([, rows]) => rows);
}

/**
 * The residue grouped by the part of the system it lives in.
 *
 * **371 of 388 subject-bearing columns survive an erasure, and a table of 371 rows is a wall
 * rather than a disclosure.** The useful facts are the proportion and the *shape*: which parts
 * of the system keep a person's data and why each of them is right to. A privacy officer
 * reasons in those terms -- "the ledger survives, the audit chain survives" -- not column by
 * column, and 25,000 pixels of reasons is a page nobody scrolls to the end of.
 *
 * The grouping is the schema plus the table's module prefix, because that is what the prefix
 * is for: `led_` is the financial ledger, `evt_` the event outbox, `acc_` the access
 * decisions. A table with no prefix groups under its schema alone.
 *
 * The full per-column registry is still in the route for anybody who needs it. What the page
 * shows is the answer to the question somebody actually asks.
 */
export type ResidueGroup = {
  area: string;
  columns: number;
  tables: string[];
  /** One entry's reason, as an example of why this area keeps what it keeps. */
  example: string;
};

export function groupResidue(reach: ErasureReach): ResidueGroup[] {
  const groups = new Map<string, { tables: Set<string>; columns: number; example: string }>();
  for (const entry of residueOf(reach)) {
    const prefix = entry.table.includes("_")
      ? `${entry.table.slice(0, entry.table.indexOf("_"))}_`
      : "";
    const area = `${entry.schema}.${prefix}`;
    const group = groups.get(area) ?? { tables: new Set(), columns: 0, example: entry.reason };
    group.tables.add(entry.table);
    group.columns += 1;
    groups.set(area, group);
  }
  return [...groups.entries()]
    .map(([area, g]) => ({
      area,
      columns: g.columns,
      tables: [...g.tables].sort(),
      example: g.example,
    }))
    // Largest first: the areas keeping the most are the ones a disclosure is about.
    .sort((a, b) => b.columns - a.columns || a.area.localeCompare(b.area));
}

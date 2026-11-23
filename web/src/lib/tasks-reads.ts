import { api } from "@/lib/api";

import type {
  AttentionItem, CaseRow, QueueRow, ResolvedPage, TaskRow, TaskView, Workload,
} from "@/lib/tasks";

/**
 * The reads the three task surfaces make, and the reason there are five of them.
 *
 * MOD-026 owns the task, the case and the queue; the names on them are MOD-014's and the
 * figures a resolution is about are other modules'. Paragraph 1300 bars a cross-domain join,
 * so each surface asks each module its own question through its own gate and composes -- one
 * extra request for a table rather than one per row, which is what the members list and the
 * Member 360 already do.
 */

/**
 * ADM-TSK-01's list, in one of its three views.
 *
 * **`mine` is a flag rather than a person id**, and that is the one thing about this read
 * worth knowing: the browser has no person id for the reader -- a session carries an
 * `identity_id`, and the link to a person is MOD-014's through `ppl_identity_links` -- so a
 * client-side "mine" filter is not expressible at all. Sending one would also let a reader
 * ask the question as somebody else, which is MOD-020's four caller-supplied person ids in
 * one route. The server derives it, the way `/tasks/workload` already does for the count the
 * chip shows.
 */
export function listTasks(params: {
  view?: TaskView;
  queueId?: string;
  limit?: number;
}): Promise<{ tasks: TaskRow[] }> {
  const query = new URLSearchParams();
  // **All three views are work in hand, which is what the chips count.** Without it the
  // unfiltered board read "Team · 5" over a table of six rows, one of them already done --
  // one screen with two definitions of "open", found by rendering the page and reading it.
  query.set("in_hand", "true");
  if (params.view === "mine") query.set("mine", "true");
  if (params.view === "overdue") query.set("overdue", "true");
  if (params.queueId) query.set("queue_id", params.queueId);
  query.set("limit", String(params.limit ?? 50));
  return api(`/tasks?${query.toString()}`);
}

/** The three chips, and R07's aging, bottleneck and compliance figures. */
export function readWorkload(queueId?: string): Promise<Workload> {
  const query = new URLSearchParams();
  if (queueId) query.set("queue_id", queueId);
  const tail = query.toString();
  return api(`/tasks/workload${tail ? `?${tail}` : ""}`);
}

/**
 * The queues, for the name a task's queue is shown by.
 *
 * `tasks.queue.read` is its own permission, so a reader may hold the task read and not this
 * one -- and then the queue is shown as its id rather than as a blank, because a task with no
 * queue is not a state this schema has.
 */
export function listQueues(limit = 100): Promise<{ queues: QueueRow[] }> {
  return api(`/tasks/queues?limit=${limit}`);
}

/**
 * The cases, for the reference a task's exception is shown by.
 *
 * ADM-TSK-01's meta line is "From exception EXC-8804", and a task row carries a `case_id` and
 * not a `case_number`. One read indexed by id answers every row; `tasks.case.read` is a
 * separate permission, so a reader without it gets "from an exception" with no reference
 * rather than a uuid printed where a human reference belongs.
 */
export function listCases(limit = 100): Promise<{ cases: CaseRow[] }> {
  return api(`/tasks/cases?limit=${limit}`);
}

/** ADM-CC-06's sheet. The viewer is derived on the server; nothing is passed for it. */
export function readAttentionItem(caseId: string): Promise<AttentionItem> {
  return api(`/tasks/cases/${caseId}/attention`);
}

/** ADM-CC-07, scoped to the server's own 24-hour default. */
export function listResolved(): Promise<ResolvedPage> {
  return api("/tasks/resolved");
}

"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api, correlationId } from "@/lib/api";

import { IDLE, type BulkState } from "./state";

/**
 * ADM-TSK-01's bulk completion — the one write its canvas draws, and the first write in this
 * app that settles several records in one act.
 *
 * **It is buildable because every MOD-026 permission is routine.** `tasks.task.write` is
 * `data_access` with no financial class, and the catalogue argues for it: "Raising, assigning
 * and settling a task is the ordinary work of a shift." Every other absent form in this app
 * is a stepped-up financial permission where "a button that answered 403 is worse than its
 * absence"; this is not one of them.
 *
 * **A reason is required, and that is the schema's rule rather than this form's politeness.**
 * `tsk_tasks` carries an attribution trio on a settlement, because "why was this not done"
 * is the question R07's outcome reporting exists to answer and a settled task with no account
 * of itself answers it with silence. One reason is recorded on every task in the selection,
 * which is what makes this one act rather than a loop a reader has to narrate.
 *
 * **There is no bulk route, deliberately, and this is a loop over the single one.** A route
 * that took a list of ids and settled them would need to decide what a partial failure means
 * — and it means something different per task, because the refusals are per task: a blocked
 * task is unblocked before it is finished, a cancelled one cannot be completed, and a task
 * somebody else settled in the meantime is already done. So each refusal is reported with the
 * task it belongs to and the reader is told how many of how many landed. A single 409 for the
 * batch would have hidden which task caused it.
 */
export async function completeSelected(
  _previous: BulkState,
  form: FormData,
): Promise<BulkState> {
  const ids = form.getAll("task_id").map(String).filter((id) => id.length > 0);
  const reason = String(form.get("reason") ?? "").trim();
  const echo = { reason };

  if (reason.length === 0) {
    return { ...IDLE, missing: { reason: true }, echo };
  }
  if (ids.length === 0) {
    return { ...IDLE, error: "tasks.bulkNone", echo };
  }

  const refused: BulkState["refused"] = [];
  let done = 0;
  // **Sequential, because the limiter is per identity.** MOD-011 budgets `api.request` at
  // 600 a minute and a fan-out of fifty settlements from one reader is exactly the burst that
  // reads as a fault; a bounded selection settled in order costs the same total and never
  // trips it. The bound is the page's own: a selection is made from the rows on screen.
  for (const id of ids) {
    try {
      await api(`/tasks/${encodeURIComponent(id)}/status`, {
        method: "POST",
        body: { target: "done", reason, correlation_id: correlationId() },
      });
      done += 1;
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      // The reader's own next step differs by which it is, so the reason travels with the
      // task rather than being collapsed into "some of these failed".
      if (error.reason === "unreachable") {
        return { ...IDLE, done, asked: ids.length, error: "error.network", refused, echo };
      }
      if (error.status === 429) {
        return { ...IDLE, done, asked: ids.length, error: "error.tooMany", refused, echo };
      }
      refused.push({ task_id: id, reason: error.reason ?? String(error.status) });
    }
  }

  revalidatePath("/tasks");
  if (done === 0) {
    return { ...IDLE, done, asked: ids.length, error: "tasks.bulkFailed", refused, echo };
  }
  return { ...IDLE, done, asked: ids.length, refused };
}

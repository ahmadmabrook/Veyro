"use client";

import { useActionState } from "react";
import Link from "next/link";

import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { DataGrid } from "@/components/ds/data-grid";
import { Field } from "@/components/ds/field";
import { fill, t, type Locale, type MessageKey } from "@/i18n/locale";

import { completeSelected } from "./actions";
import { IDLE, type BulkState } from "./state";

/**
 * ADM-TSK-01's rows, with the selection and the bulk completion the canvas draws.
 *
 * **Every display string is computed on the server and passed in.** A due label is relative
 * to today, and a client computing its own `new Date()` during render would disagree with the
 * server's markup on every load near midnight — a hydration mismatch that renders as a
 * flicker and is a wrong date for a second. This repository has four recorded defects whose
 * green depended on when the suite ran; a figure that depends on *which process* computed it
 * is the same family.
 *
 * **The selection is a form, so it works un-hydrated.** Checkboxes named `task_id` and a
 * submit is the whole mechanism; `useActionState` exists only to render what came back, which
 * is the rota form's decision and the sign-in page's before it.
 *
 * **The submit is not disabled on an empty selection**, which is the Input contract's rule
 * applied to a button: "Validate on blur, never on keystroke; re-validate on submit." A
 * control that un-disables as boxes are ticked is keystroke validation wearing a different
 * hat, and it leaves a reader with a dead button and no sentence. Pressing it with nothing
 * selected says so.
 */
export type TaskDisplay = {
  task_id: string;
  title: string;
  /** "From exception EXC-8804 · due today" — the canvas's own meta line, already filled. */
  meta: string;
  queue: string;
  source: string;
  status: string;
  due: string;
  /** Past its due date, for the row's edge-mark. */
  overdue: boolean;
  /** The exception this task was born from, when there is one. */
  caseId: string | null;
  /** A settled task cannot be settled again, so it carries no checkbox. */
  settleable: boolean;
};

export function TaskTable({
  locale,
  rows,
  mayWrite,
  countLabel,
}: {
  locale: Locale;
  rows: TaskDisplay[];
  mayWrite: boolean;
  countLabel: string;
}) {
  const [state, action, pending] = useActionState<BulkState, FormData>(
    completeSelected, IDLE);
  const text = (key: MessageKey) => t(locale, key);

  const grid = (
    <DataGrid
      caption={text("tasks.title")}
      labelledBy="tasks-heading"
      rows={rows}
      rowKey={(row) => row.task_id}
      rowSeverity={(row) => (row.overdue ? "attention" : null)}
      countLabel={countLabel}
      columns={[
        ...(mayWrite
          ? [{
              header: text("tasks.bulkSelect"),
              kind: "action" as const,
              priority: 1 as const,
              render: (row: TaskDisplay) =>
                row.settleable ? (
                  <input
                    type="checkbox"
                    name="task_id"
                    value={row.task_id}
                    aria-label={`${text("tasks.bulkSelect")}: ${row.title}`}
                  />
                ) : null,
            }]
          : []),
        {
          header: text("tasks.colTask"),
          kind: "text" as const,
          priority: 1 as const,
          render: (row: TaskDisplay) => (
            <>
              {row.caseId === null ? (
                <span>{row.title}</span>
              ) : (
                // "Tasks born from an exception link back to it" — which is the canvas's own
                // line and the only navigation into ADM-CC-06 this build has.
                <Link href={`/tasks/cases/${row.caseId}`}>{row.title}</Link>
              )}
              <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
                {row.meta}
              </div>
            </>
          ),
        },
        {
          header: text("tasks.colQueue"),
          kind: "text" as const,
          priority: 3 as const,
          render: (row: TaskDisplay) => row.queue,
        },
        {
          header: text("tasks.colSource"),
          kind: "text" as const,
          priority: 2 as const,
          render: (row: TaskDisplay) => row.source,
        },
        {
          header: text("tasks.colStatus"),
          kind: "text" as const,
          priority: 2 as const,
          render: (row: TaskDisplay) => row.status,
        },
        {
          header: text("tasks.colDue"),
          kind: "date" as const,
          priority: 1 as const,
          render: (row: TaskDisplay) => row.due,
        },
      ]}
    />
  );

  if (!mayWrite) return grid;

  return (
    <form action={action} className="stack">
      {grid}

      <section className="page-section" aria-labelledby="tasks-bulk">
        <h2 id="tasks-bulk">{text("tasks.bulkHeading")}</h2>

        {state.done > 0 && state.refused.length === 0 ? (
          <Banner severity="info">
            {fill(locale, "tasks.bulkDone", { count: state.done })}
          </Banner>
        ) : null}
        {state.done > 0 && state.refused.length > 0 ? (
          <Banner severity="attention">
            {fill(locale, "tasks.bulkPartial", { done: state.done, asked: state.asked })}
          </Banner>
        ) : null}
        {state.error !== null ? (
          <Banner severity="critical">{text(state.error)}</Banner>
        ) : null}

        {/* **Named, never summarised.** Each refusal belongs to a task, and the reader's next
            step differs by which: a blocked task is unblocked before it is finished, and one
            somebody else settled in the meantime is already done. A single message for the
            batch would hide which task caused it. */}
        {state.refused.length > 0 ? (
          <ul className="ds-note">
            {state.refused.map((entry) => (
              <li key={entry.task_id}>
                <span className="data" dir="ltr">{entry.task_id}</span>
                {" — "}
                <span className="data" dir="ltr">{entry.reason}</span>
              </li>
            ))}
          </ul>
        ) : null}

        <Field
          id="tasks-bulk-reason" name="reason" type="text" required rarer="optional"
          label={text("tasks.bulkReason")}
          description={text("tasks.bulkReasonHint")}
          defaultValue={state.echo.reason ?? ""}
          message={
            state.missing.reason
              ? { kind: "error", text: text("tasks.bulkReasonHint") }
              : null
          }
        />
        <Button
          type="submit" variant="primary" size="lg"
          label={text("tasks.bulkComplete")}
          state={pending ? "loading" : "default"}
        />
      </section>
    </form>
  );
}

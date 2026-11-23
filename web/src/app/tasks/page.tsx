import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { ProseNote } from "@/components/prose";
import { fill, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gateAll, gateMessage, gateVerdict } from "@/lib/api";
import { presentation } from "@/lib/preferences";
import {
  TASK_VIEWS, UNANSWERABLE, dueLabel, dueState, isTaskView, metaLine, sourceWord,
  taskStatusWord, word,
  type CaseRow, type QueueRow, type TaskRow, type TaskView, type Workload,
} from "@/lib/tasks";
import { listCases, listQueues, listTasks, readWorkload } from "@/lib/tasks-reads";

import { TaskTable, type TaskDisplay } from "./task-table";

/**
 * ADM-TSK-01 · TASKS — "Assigned, due, source (manual, automation, AI), bulk complete.
 * Tasks generated from attention items link back to them."
 *
 * **Three chips, and the one this app could not have built in the client.** `Mine · 4 ·
 * Team · 11 · Overdue · 2` are filters, and "mine" needs the reader's own person id — which a
 * browser does not have: a session carries an `identity_id`, and the link to a person is
 * MOD-014's through `ppl_identity_links`. So `GET /tasks` takes `mine=true` and derives it,
 * the way `/tasks/workload` already derives the count the chip shows. Sending a person id up
 * from the client would also let a reader ask the question as somebody else, which is
 * MOD-020's four caller-supplied person ids in one route.
 *
 * **The counts are the tenant's, the rows are the page's.** Every chip's figure comes from
 * `/tasks/workload`, which counts over the queue rather than over the fifty rows loaded —
 * the members list's own finding, where summing the page was honest and still the wrong
 * number in the place a manager reads the business.
 *
 * **The meta line is composed from three modules and says so when it cannot be.** "From
 * exception EXC-8804" needs the case's human reference, which a task row carries as an id;
 * `tasks.case.read` is a separate permission, so a reader without it gets "From an exception"
 * rather than a uuid printed where a reference belongs. What nothing here can say is **who
 * assigned it** — a task carries an assignee and no assigner, so the canvas's "Assigned by
 * Rania" is in the gap list rather than approximated.
 *
 * **Completing a task does not resolve the exception**, which the canvas is explicit about and
 * which this build enforces by having no path between them: the bulk completion settles tasks
 * and touches no case. "The work and the record of the work are separate, which is why the
 * Command Center count does not drop when someone ticks a box here."
 */
export default async function TasksPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);
  const params = await searchParams;
  const wanted = typeof params.view === "string" ? params.view : undefined;
  const view: TaskView = isTaskView(wanted) ? wanted : "team";

  if (!(await currentSession())) redirect("/login");

  // One round trip for all four questions this page asks the gate.
  const [mayTasks, mayWrite, mayQueues, mayCases] = await gateAll([
    "tasks.task.read", "tasks.task.write", "tasks.queue.read", "tasks.case.read",
  ] as const);

  if (!mayTasks.allowed) {
    const verdict = gateVerdict(mayTasks);
    return (
      <Shell locale={locale} view={view} workload={null}>
        {/* **A refusal and a failure are different facts**, and `gateAll` fails closed --
            which is right for access and means a transport failure arrives in the shape of a
            refusal. `denied` is the only one about this reader's own grants; the other three
            are about the gate, the assurance ceiling or the network, and each has a different
            next step. */}
        <Banner severity={verdict === "gate_failed" ? "critical" : "info"}>
          {verdict === "denied" ? text("tasks.refused") : text(gateMessage(mayTasks))}
        </Banner>
      </Shell>
    );
  }

  let tasks: TaskRow[] = [];
  let workload: Workload | null = null;
  let queues: QueueRow[] = [];
  let cases: CaseRow[] = [];
  let failed = false;
  try {
    const [list, counts, queueList, caseList] = await Promise.all([
      listTasks({ view }),
      readWorkload(),
      // Each composed half is optional and refused separately, so a reader holding the task
      // read alone still gets the table rather than an error about a different permission.
      mayQueues.allowed
        ? listQueues().catch(() => ({ queues: [] }))
        : Promise.resolve({ queues: [] }),
      mayCases.allowed
        ? listCases().catch(() => ({ cases: [] }))
        : Promise.resolve({ cases: [] }),
    ]);
    tasks = list.tasks;
    workload = counts;
    queues = queueList.queues;
    cases = caseList.cases;
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    failed = true;
  }

  if (failed) {
    return (
      <Shell locale={locale} view={view} workload={null}>
        <Banner severity="critical">{text("error.unexpected")}</Banner>
      </Shell>
    );
  }

  const queueNames = new Map(queues.map((queue) => [queue.queue_id, queue.display_name]));
  const caseNumbers = new Map(cases.map((entry) => [entry.case_id, entry.case_number]));
  // **One `now` for the whole page.** Every due label on screen is relative to the same
  // instant, which is what makes "due today" and "overdue 1 day" consistent down a column.
  const now = new Date();

  const rows: TaskDisplay[] = tasks.map((task) => {
    const due = dueState(task.due_at, now);
    return {
      task_id: task.task_id,
      title: task.title,
      meta: metaLine(locale, task, caseNumbers, now),
      queue: queueNames.get(task.queue_id) ?? text("tasks.queueUnnamed"),
      source: word(locale, sourceWord(task.source), task.source),
      status: word(locale, taskStatusWord(task.status), task.status),
      due: dueLabel(locale, due, task.due_at, now),
      overdue: due.kind === "overdue",
      caseId: task.case_id,
      // **A blocked task is unblocked before it is finished**, which is MOD-026's own rule
      // and the schema's: `blocked -> done` is not an edge, in the Python table and in the
      // trigger. So the row carries no checkbox rather than one the server would refuse --
      // FD-06's "a button the module will refuse is worse than no button", applied to the one
      // status in hand that cannot be settled. The other two are `open` and `in_progress`,
      // and `in_hand` guarantees the list holds no settled task at all.
      settleable: task.status === "open" || task.status === "in_progress",
    };
  });

  return (
    <Shell locale={locale} view={view} workload={workload}>
      {/* **A count of zero is four different facts here**, which is why the empty state names
          the view rather than saying "no data": an empty "mine" is nothing assigned to you, an
          empty "overdue" is a queue in hand, and an empty "team" is an empty queue. */}
      {rows.length === 0 ? (
        <Banner severity="info">
          {text(view === "mine" ? "tasks.emptyMine"
            : view === "overdue" ? "tasks.emptyOverdue" : "tasks.empty")}
        </Banner>
      ) : (
        <TaskTable
          locale={locale}
          rows={rows}
          mayWrite={mayWrite.allowed}
          countLabel={fill(locale, "tasks.countLabel", { count: rows.length })}
        />
      )}

      <ProseNote>{text("tasks.inHandOnly")}</ProseNote>
      <ProseNote>{text("tasks.blockedFirst")}</ProseNote>
      <ProseNote>{text("tasks.separateFromException")}</ProseNote>
      <ProseNote>{text("tasks.sourceAlwaysNamed")}</ProseNote>

      <section className="page-section" aria-labelledby="tasks-gaps">
        <h2 id="tasks-gaps">{text("tasks.gaps")}</h2>
        <dl className="facts">
          <Gap locale={locale} label="tasks.gapAssignedByLabel" why={UNANSWERABLE.assignedBy} />
          <Gap locale={locale} label="tasks.gapScopeLabel" why={UNANSWERABLE.scope} />
          <Gap locale={locale} label="tasks.gapSideSheetLabel" why={UNANSWERABLE.sideSheet} />
        </dl>
      </section>
    </Shell>
  );
}

function Gap({
  locale, label, why,
}: {
  locale: Locale;
  label: MessageKey;
  why: MessageKey;
}) {
  return (
    <>
      <dt className="muted">{t(locale, label)}</dt>
      <dd style={{ margin: 0 }}>{t(locale, why)}</dd>
    </>
  );
}

/**
 * The page's own chrome: a title, the three chips, and the compact density the members-list
 * archetype is set at.
 */
function Shell({
  locale, view, workload, children,
}: {
  locale: Locale;
  view: TaskView;
  /** Absent where the gate refused or the read failed, so the chips are not drawn as zeros. */
  workload: Workload | null;
  children: React.ReactNode;
}) {
  const text = (key: MessageKey) => t(locale, key);
  return (
    <div className="stack" data-density="compact">
      <div className="ds-page-head">
        <div className="ds-page-head-text">
          <h1 id="tasks-heading" style={{ margin: 0 }}>{text("tasks.title")}</h1>
        </div>
        <div className="ds-page-head-end">
          <Link href="/tasks/resolved">{text("resolved.title")}</Link>
        </div>
      </div>

      {workload === null ? null : (
        <nav aria-label={text("tasks.title")} className="ds-filter-bar">
          {TASK_VIEWS.map((each) => (
            <Link
              key={each}
              href={each === "team" ? "/tasks" : `/tasks?view=${each}`}
              aria-current={each === view ? "page" : undefined}
              className="ds-filter-chip"
            >
              {fill(locale, chipKey(each), { count: workload[each] })}
            </Link>
          ))}
        </nav>
      )}

      {/* **"Mine · 0" is two different facts and only one of them is about the work.** An
          identity with no person record counts nothing here, which is not an empty queue --
          it is a link MOD-014 makes and nobody has made for this one. Staff hold permissions
          and do not have to be anybody in particular, so this is ordinary rather than an
          error, and saying so is cheaper than a reader concluding their tasks vanished. */}
      {workload?.mine_is_zero_without_a_person_record ? (
        <Banner severity="info">{text("tasks.mineNeedsPerson")}</Banner>
      ) : null}

      {children}
    </div>
  );
}

function chipKey(view: TaskView): MessageKey {
  return view === "mine" ? "tasks.chipMine"
    : view === "team" ? "tasks.chipTeam" : "tasks.chipOverdue";
}

import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { DataGrid } from "@/components/ds/data-grid";
import { ProseNote } from "@/components/prose";
import { fill, t, type Locale, type MessageKey, type Numbering } from "@/i18n/locale";
import { ApiError, currentSession, gateAll, gateMessage, gateVerdict } from "@/lib/api";
import { numerals } from "@/lib/display";
import { presentation } from "@/lib/preferences";
import {
  compactDuration, durationWords,
  type QueueRow, type ResolvedCase, type ResolvedPage,
} from "@/lib/tasks";
import { listQueues, listResolved } from "@/lib/tasks-reads";

/**
 * ADM-CC-07 · RESOLVED TODAY — "Same grid, scoped to resolutions in the last 24h. Columns:
 * item, resolver, time to resolve, outcome. Exists so a manager can see what their team
 * handled without asking. Read-only for everyone; no un-resolve."
 *
 * **Read-only is a property of this build, not a restraint of this page.** The canvas is
 * explicit — "Read-only for every role, including Owner. There is no un-resolve — reopening
 * happens on the item itself and appears here as a new row, so this list is a record rather
 * than a state" — and MOD-026 has no route that reverses a resolution: a case moves forward
 * only, by trigger, and a problem that returns is a new case citing the old one. So there is
 * nothing here to withhold from a role, which is why the page carries no write gate at all.
 *
 * **The median is the server's and is rendered twice from one number.** `list_resolved`
 * computes it, because "a median in a client is a second definition of a figure a manager
 * quotes" — MOD-018's one-module-two-definitions finding. The grid cell is mono in a narrow
 * column and the sub-line is a sentence, which is how the canvas sets them; what would be
 * wrong is two definitions, not two renderings.
 *
 * **An empty window has no median rather than a median of zero**, which is MOD-011's rule
 * arriving on a surface: a dashboard reporting zero would read as a team resolving everything
 * instantly, and the server returns `null` for exactly that reason.
 *
 * **The outcome is a masked column.** A resolution's prose is free text written about a
 * person, and MOD-019 learned that a reason column is where a health fact goes in practice —
 * so it is readable by whoever may settle a case and marked for everybody else. The grid's
 * own `restricted` mechanism renders the marker rather than a blank, because an empty cell
 * reads as "nothing was recorded".
 */
export default async function ResolvedPageView() {
  const { locale } = await presentation();
  // **The tenant's numerals** -- ADR-0015. Every quantity on this page follows
  // `localization.numerals`; an identifier does not, and neither does money. One read for the
  // whole render: `conventions()` is React's per-request memo and the layout starts it.
  const numbering = await numerals();
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  const [mayCases, mayQueues] = await gateAll([
    "tasks.case.read", "tasks.queue.read",
  ] as const);

  if (!mayCases.allowed) {
    const verdict = gateVerdict(mayCases);
    return (
      <Shell locale={locale} numbering={numbering} page={null}>
        <Banner severity={verdict === "gate_failed" ? "critical" : "info"}>
          {verdict === "denied" ? text("case.refused") : text(gateMessage(mayCases))}
        </Banner>
      </Shell>
    );
  }

  let page: ResolvedPage | null = null;
  let queues: QueueRow[] = [];
  try {
    const [resolved, queueList] = await Promise.all([
      listResolved(),
      mayQueues.allowed
        ? listQueues().catch(() => ({ queues: [] }))
        : Promise.resolve({ queues: [] }),
    ]);
    page = resolved;
    queues = queueList.queues;
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
  }

  if (page === null) {
    return (
      <Shell locale={locale} numbering={numbering} page={null}>
        <Banner severity="critical">{text("error.unexpected")}</Banner>
      </Shell>
    );
  }

  const queueNames = new Map(queues.map((queue) => [queue.queue_id, queue.display_name]));

  return (
    <Shell locale={locale} numbering={numbering} page={page}>
      {page.cases.length === 0 ? (
        <Banner severity="info">{text("resolved.empty")}</Banner>
      ) : (
        <DataGrid
          caption={text("resolved.title")}
          countLabel={null}
          labelledBy="resolved-heading"
          rows={page.cases}
          rowKey={(row) => row.case_id}
          restrictedLabel={text("member.withheld")}
          columns={[
            {
              header: text("resolved.colItem"),
              kind: "text",
              priority: 1,
              render: (row: ResolvedCase) => (
                <>
                  <Link href={`/tasks/cases/${row.case_id}`}>{row.title}</Link>
                  <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
                    <span className="data" dir="ltr">{row.case_number}</span>
                    {" · "}
                    {queueNames.get(row.queue_id) ?? text("tasks.queueUnnamed")}
                  </div>
                </>
              ),
            },
            {
              // **A reference, not a name.** `tasks.case.read` is routine, so a resolver's
              // legal name here would be a way around the permission that guards a person's
              // record -- MOD-010's `events.event.read` finding, which the list route itself
              // answers for by carrying ids only.
              header: text("resolved.colResolver"),
              kind: "person",
              priority: 2,
              render: (row: ResolvedCase) =>
                row.resolved_by === null ? (
                  <span className="muted">{"—"}</span>
                ) : (
                  <span className="data" dir="ltr">{row.resolved_by}</span>
                ),
            },
            {
              header: text("resolved.colTook"),
              kind: "text",
              priority: 1,
              render: (row: ResolvedCase) => (
                <span className="data" dir="ltr">
                  {compactDuration(row.took_seconds)}
                </span>
              ),
            },
            {
              header: text("resolved.colOutcome"),
              kind: "text",
              priority: 2,
              restricted: (row: ResolvedCase) => row.reason_masked && row.outcome !== null,
              render: (row: ResolvedCase) =>
                row.outcome === null
                  ? <span className="muted">{text("resolved.noOutcome")}</span>
                  : row.outcome,
            },
          ]}
        />
      )}

      <ProseNote>{text("resolved.readOnly")}</ProseNote>
      <ProseNote>{text("resolved.resolverIsAnIdentity")}</ProseNote>
    </Shell>
  );
}

function Shell({
  locale, page, children, numbering,
}: {
  locale: Locale;
  numbering: Numbering;
  /** Absent where the gate refused or the read failed, so no figure is drawn as a zero. */
  page: ResolvedPage | null;
  children: React.ReactNode;
}) {
  const text = (key: MessageKey) => t(locale, key);
  return (
    <div className="stack" data-density="compact">
      <div className="ds-page-head">
        <div className="ds-page-head-text">
          <h1 id="resolved-heading" style={{ margin: 0 }}>{text("resolved.title")}</h1>
        </div>
        <div className="ds-page-head-end">
          <Link href="/tasks">{text("case.backToTasks")}</Link>
        </div>
      </div>

      {/* The canvas's sub-line: "7 resolved today · Median 41 minutes · all locations". */}
      {page === null ? null : (
        <p className="muted" style={{ margin: 0 }}>
          {fill(locale, "resolved.count", { count: page.resolved }, numbering)}
          {" · "}
          {page.median_seconds === null
            ? text("resolved.noMedian")
            : fill(locale, "resolved.median", {
                took: durationWords(page.median_seconds, locale),
              })}
        </p>
      )}

      {children}
    </div>
  );
}

import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { DataGrid } from "@/components/ds/data-grid";
import { MetricCell, MetricRow } from "@/components/ds/metric-cell";
import { PageHeader } from "@/components/ds/page-header";
import { NotYet } from "@/components/not-yet";
import { formatInteger, t, type Locale, type MessageKey, type Numbering } from "@/i18n/locale";
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
            // **There is no RESOLVER column, and that is the honest render rather than a
            // deviation.** `resolved_by` is an *identity* id and the link to a person is
            //MOD-014's, which this read does not cross -- so the only thing this build can
            //put in that cell is a uuid. Forty identical 36-character ids is a column an
            //operator cannot act on, taking a quarter of the table's width, and an id in a
            //person column reads as a name that failed to load. The absence is named in the
            //gap line instead. The permission reasoning that chose an id over a name still
            //holds and is why a name cannot simply be fetched: `tasks.case.read` is routine,
            //so naming the resolver here would be a way around the permission guarding a
            // person's record -- MOD-010's `events.event.read` finding.
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

      <NotYet locale={locale} items={["resolved.gapResolver"]} />

      {/* Two notes have gone: that this list is read-only with no un-resolve, and why the
          RESOLVER column carries an id rather than a name. Neither changes what a reader does
          here -- the page offers no control for either to qualify. */}
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
      <PageHeader
        id="resolved-heading"
        title={text("resolved.title")}
        actions={<Link href="/tasks">{text("case.backToTasks")}</Link>}
      />

      {/* **The two figures the canvas states, at the scale they deserve.** Its sub-line is
          "7 resolved today · Median 41 minutes", which is the whole subject of this board --
          how much got finished and how long it took -- so they lead rather than sitting in
          grey under the title. A median with nothing behind it is `unavailable` rather than a
          zero: `MetricCell`'s own rule, because an em dash there reads as a measurement of no
          time at all. */}
      {page === null ? null : (
        <MetricRow label={text("resolved.title")}>
          <MetricCell
            label={text("resolved.figResolved")}
            value={formatInteger(page.resolved, numbering)}
          />
          {page.median_seconds === null ? (
            <MetricCell
              label={text("resolved.figMedian")}
              freshness="unavailable"
              unavailableBecause={text("resolved.noMedian")}
            />
          ) : (
            <MetricCell
              label={text("resolved.figMedian")}
              value={durationWords(page.median_seconds, locale)}
            />
          )}
        </MetricRow>
      )}

      {children}
    </div>
  );
}

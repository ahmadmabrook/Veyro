import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { LeadCard, PipelineColumn } from "@/components/ds/pipeline-column";
import { Withheld } from "@/components/withheld";
import { ProseNote } from "@/components/prose";
import { fill, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gateAll, gateMessage, gateVerdict } from "@/lib/api";
import { readNames } from "@/lib/desk-reads";
import { isWithheld } from "@/lib/people";
import {
  BOARD_COLUMNS, CARDS_PER_COLUMN, columnCount, columnNote, isLeadFilter,
  isLeadView, metaLine, sinceLabel,
  stageWord,
  type Board, type LeadFilter, type LeadRow, type LeadView,
} from "@/lib/leads";
import { listLeads, readBoard } from "@/lib/leads-reads";
import { presentation } from "@/lib/preferences";

import { LeadTable, type LeadDisplay } from "./lead-table";

/**
 * ADM-CRM-01 · LEAD PIPELINE and ADM-CRM-02 · LEAD LIST — two views of one list.
 *
 * The canvas draws a board of five columns with a "Board view" toggle beside a table, so the
 * view is a parameter and the rows are the same rows. The board is `PipelineColumn` and
 * `LeadCard`, which ADM-CRM-01's own COMPONENTS line names; the table is `DataGrid`, which
 * ADM-CRM-02's note asks for in as many words.
 *
 * **Not one name per row.** A lead is a `ppl_persons` row and this module holds no name at
 * all, so the names arrive from `GET /people/names` in one batch -- the round-trip problem
 * the staff list paid for once, on a board that draws up to fifty.
 *
 * **The board's counts are the tenant's and the table's rows are a page.** `GET /crm/board`
 * counts over every lead; a chip figure taken from the fifty rows loaded would be the
 * members-list finding, where summing the page was honest and still the wrong number in the
 * place a manager reads the business.
 *
 * **"On trial" is drawn and empty, with the reason on the column.** Nothing in this build
 * marks a product as a trial, so no lead can be on one; hiding the column would make the
 * board read as four stages, which is a different product from the one the design draws.
 */
export default async function LeadsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);
  const params = await searchParams;
  const wantedView = typeof params.view === "string" ? params.view : undefined;
  const view: LeadView = isLeadView(wantedView) ? wantedView : "board";
  const wantedFilter = typeof params.filter === "string" ? params.filter : undefined;
  const filter: LeadFilter = isLeadFilter(wantedFilter) ? wantedFilter : "all";

  if (!(await currentSession())) redirect("/login");

  const [mayLeads, mayPeople] = await gateAll(["crm.lead.read", "people.person.read"] as const);

  if (!mayLeads.allowed) {
    const verdict = gateVerdict(mayLeads);
    return (
      <Shell locale={locale} view={view} filter={filter} board={null} coldAfter={48}>
        <Banner severity={verdict === "gate_failed" ? "critical" : "info"}>
          {verdict === "denied" ? text("leads.refused") : text(gateMessage(mayLeads))}
        </Banner>
      </Shell>
    );
  }

  let leads: LeadRow[] = [];
  let board: Board | null = null;
  let coldAfter = 48;
  let names = new Map<string, { person_id: string; legal_name: string | null }>();
  let failed = false;
  try {
    const [list, counts] = await Promise.all([
      listLeads({ filter }),
      readBoard({ mine: filter === "mine" }),
    ]);
    leads = list.leads;
    coldAfter = list.going_cold_after_hours;
    board = counts;
    // The owner's name as well as the lead's, in the same batch: both are MOD-014's and a
    // second request for the second column would be two round trips for one table.
    const wanted = [
      ...leads.map((lead) => lead.person_id),
      ...leads.flatMap((lead) => (lead.owner_person_id ? [lead.owner_person_id] : [])),
    ];
    names = mayPeople.allowed
      ? await readNames(wanted).catch(() => new Map())
      : new Map();
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    failed = true;
  }

  if (failed) {
    return (
      <Shell locale={locale} view={view} filter={filter} board={null} coldAfter={coldAfter}>
        <Banner severity="critical">{text("error.unexpected")}</Banner>
      </Shell>
    );
  }

  const nameOf = (personId: string | null): string | null => {
    if (personId === null) return null;
    const found = names.get(personId);
    // **`null` is withheld, and a masked value is a marker rather than a name.**
    // `GET /people/names` returns the *marker* for a field this session cannot read, not a
    // null -- so the first version of this rendered `***` as though somebody were called
    // that, and the board's own step-up offer never appeared because nothing looked
    // withheld. `isWithheld` is MOD-014's own test for it, which the members list already
    // uses. An absent entry is withheld too: a reader without `people.person.read` gets no
    // batch at all, which is the same fact one step further away.
    const name = found?.legal_name ?? null;
    return name !== null && !isWithheld(name) ? name : null;
  };

  const rows: LeadDisplay[] = leads.map((lead) => ({
    lead_id: lead.lead_id,
    name: nameOf(lead.person_id),
    meta: metaLine(locale, lead),
    source: lead.source ?? text("leads.noSource"),
    owner: lead.owner_person_id === null ? null : (nameOf(lead.owner_person_id) ?? ""),
    age: sinceLabel(locale, lead.hours_since_contact),
    next: lead.next_action ?? text("leads.noNext"),
    stage: wordFor(locale, stageWord(lead.stage), lead.stage),
    cold: lead.going_cold,
  }));

  if (board?.mine_is_zero_without_a_person_record !== undefined) {
    return (
      <Shell locale={locale} view={view} filter={filter} board={board} coldAfter={coldAfter}>
        {/* **Two different facts and only one is about the work.** A reader whose sign-in is
            not linked to a person owns no leads, and so does a reader with an empty queue --
            the first is ordinary, because staff hold permissions and do not have to be
            anybody in particular. MOD-026's board says the same thing one module over. */}
        <Banner severity="info">{text("leads.mineNeedsAPerson")}</Banner>
      </Shell>
    );
  }

  return (
    <Shell locale={locale} view={view} filter={filter} board={board} coldAfter={coldAfter}>
      {rows.some((row) => row.name === null) ? (
        <p className="ds-note">
          {text("leads.namesWithheld")}{" "}
          <Link
            href={`/step-up?for=financial&action=member.identity.read&next=${
              encodeURIComponent(view === "table" ? "/leads?view=table" : "/leads")}`}
          >
            {text("member.raiseSession")}
          </Link>
        </p>
      ) : null}

      {rows.length === 0 ? (
        <Banner severity="info">
          {text(filter === "going_cold" ? "leads.emptyCold"
            : filter === "mine" ? "leads.emptyMine" : "leads.empty")}
        </Banner>
      ) : view === "table" ? (
        <>
          <LeadTable
            locale={locale}
            rows={rows}
            countLabel={fill(locale, "leads.countLabel", { count: rows.length })}
          />
          <ProseNote>{text("leads.ageCarriesColour")}</ProseNote>
        </>
      ) : (
        <Board
          locale={locale}
          board={board}
          leads={leads}
          nameOf={nameOf}
        />
      )}
      <ProseNote>{text("leads.nameIsElsewhere")}</ProseNote>
      <section className="page-section" aria-labelledby="leads-gaps">
        <h2 id="leads-gaps">{text("leads.gaps")}</h2>
        <dl className="facts">
          <dt>{text("leads.gapSuggestionLabel")}</dt>
          <dd>{text("leads.gapSuggestion")}</dd>
          <dt>{text("leads.gapConversionLabel")}</dt>
          <dd>{text("leads.gapConversion")}</dd>
        </dl>
      </section>
    </Shell>
  );
}

/** The word for a stored value, or the value itself where this build has no word for it. */
function wordFor(locale: Locale, key: MessageKey | null, raw: string): string {
  return key === null ? raw : t(locale, key);
}

function Board({
  locale, board, leads, nameOf,
}: {
  locale: Locale;
  board: Board | null;
  leads: LeadRow[];
  nameOf: (personId: string | null) => string | null;
}) {
  const text = (key: MessageKey) => t(locale, key);
  const counts = new Map((board?.columns ?? []).map((one) => [one.stage, one.count]));
  // **The cards come from the page and the counts from the tenant**, which is why a column
  // can say 12 over two cards and an overflow line rather than over twelve: the board read
  // counts every lead and this list is a bounded page.
  // **The cards sit in the column their *stored* stage names.** The two derived columns are
  // the board read's answer and no lead in this slice is in them, so a card never appears
  // under `on_trial` or `joined` -- which the column's own note says.
  const byStage = new Map<string, LeadRow[]>();
  for (const lead of leads) {
    byStage.set(lead.stage, [...(byStage.get(lead.stage) ?? []), lead]);
  }
  return (
    <section aria-label={text("leads.boardLabel")} className="ds-pipeline">
      {BOARD_COLUMNS.map((stage) => {
        const held = byStage.get(stage) ?? [];
        const total = counts.get(stage) ?? 0;
        const shown = held.slice(0, CARDS_PER_COLUMN);
        const hidden = total - shown.length;
        const note = columnNote(stage);
        const title = wordFor(locale, stageWord(stage), stage);
        return (
          <PipelineColumn
            key={stage}
            title={title}
            count={columnCount(total)}
            countLabel={fill(locale, "leads.columnLabel", {
              stage: title, count: total,
            })}
            {...(hidden > 0
              ? { overflow: fill(locale, "leads.more", { count: hidden }) }
              : note !== null && total === 0
                ? { overflow: text(note) }
                : {})}
          >
            {shown.map((lead) => (
              <LeadCard
                key={lead.lead_id}
                href={`/leads/${lead.lead_id}`}
                name={
                  nameOf(lead.person_id) ?? (
                    <Withheld locale={locale} reason="member.withheldIdentity" />
                  )
                }
                meta={metaLine(locale, lead)}
                {...(lead.going_cold ? { mark: text("leads.cold") } : {})}
              />
            ))}
          </PipelineColumn>
        );
      })}
    </section>
  );
}

function Shell({
  locale, view, filter, board, coldAfter, children,
}: {
  locale: Locale;
  view: LeadView;
  filter: LeadFilter;
  board: Board | null;
  coldAfter: number;
  children: React.ReactNode;
}) {
  const text = (key: MessageKey) => t(locale, key);
  const here = (over: { view?: LeadView; filter?: LeadFilter }) => {
    const next = new URLSearchParams();
    next.set("view", over.view ?? view);
    next.set("filter", over.filter ?? filter);
    return `/leads?${next.toString()}`;
  };
  return (
    <div className="stack">
      <header className="ds-page-head">
        <h1 id="leads-heading">{text("leads.heading")}</h1>
        {board === null ? null : (
          <p className="muted">
            {fill(locale, "leads.openLeads", { count: board.open_leads })}
            {" · "}
            {fill(locale, "leads.goingCold", { count: board.going_cold })}
          </p>
        )}
      </header>

      <nav aria-label={text("leads.title")} className="chips">
        <Link href={here({ filter: "all" })} aria-current={filter === "all" ? "page" : undefined}>
          {text("leads.filterAll")}
        </Link>
        <Link
          href={here({ filter: "going_cold" })}
          aria-current={filter === "going_cold" ? "page" : undefined}
        >
          {fill(locale, "leads.filterCold", { count: coldAfter })}
        </Link>
        <Link
          href={here({ filter: "mine" })}
          aria-current={filter === "mine" ? "page" : undefined}
        >
          {text("leads.filterMine")}
        </Link>
        <Link
          href={here({ view: view === "board" ? "table" : "board" })}
          aria-current={undefined}
        >
          {text(view === "board" ? "leads.viewTable" : "leads.viewBoard")}
        </Link>
      </nav>

      {children}
    </div>
  );
}

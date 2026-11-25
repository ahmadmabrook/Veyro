import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { PageHeader } from "@/components/ds/page-header";
import { LeadCard, PipelineColumn } from "@/components/ds/pipeline-column";
import { Withheld } from "@/components/withheld";
import { ProseNote } from "@/components/prose";
import { fill, t, type Locale, type MessageKey, type Numbering } from "@/i18n/locale";
import { ApiError, currentSession, gateAll, gateMessage, gateVerdict } from "@/lib/api";
import { readNames } from "@/lib/desk-reads";
import { isWithheld, withheldRemedy } from "@/lib/people";
import {
  BOARD_COLUMNS, CARDS_PER_COLUMN, columnCount, columnNote, isLeadFilter,
  isLeadView, metaLine, sinceLabel,
  stageWord,
  type Board, type LeadFilter, type LeadRow, type LeadView,
} from "@/lib/leads";
import { listLeads, readBoard } from "@/lib/leads-reads";
import { numerals } from "@/lib/display";
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
 * **The last two columns are the server's derivation, not this screen's.** "On trial" is an
 * active membership on a product whose terms declare `trial_days` and "Joined" is one whose
 * terms do not -- both through MOD-017's supersession chain, so a member who converted by
 * superseding the trial's agreement moves out of the trial column rather than staying in it
 * for ever. They carried a "nothing marks a product as a trial" note until ADR-0010 D7
 * settled the marker; the note is deleted rather than reworded, because a gap list is a claim
 * about the product.
 */
export default async function LeadsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await presentation();
  // **The tenant's numerals** -- ADR-0015. The column counts are quantities, so they follow
  // `localization.numerals` like every other count in the product.
  const numbering = await numerals();
  const text = (key: MessageKey) => t(locale, key);
  const params = await searchParams;
  const wantedView = typeof params.view === "string" ? params.view : undefined;
  const view: LeadView = isLeadView(wantedView) ? wantedView : "board";
  const wantedFilter = typeof params.filter === "string" ? params.filter : undefined;
  const filter: LeadFilter = isLeadFilter(wantedFilter) ? wantedFilter : "all";

  if (!(await currentSession())) redirect("/login");

  const [mayLeads, mayPeople, mayWrite, mayNames] = await gateAll([
    "crm.lead.read",
    "people.person.read",
    // **For the header's "Add a lead" and nothing else.** The live ADM-CRM-01 screen draws
    // `prim('Add a lead')` in its header row and this page rendered nothing there -- the same
    // shape as ADM-MEM-05's missing "Add member", and with the same consequence: ADM-CRM-04
    // is the only way to open a lead from a cold start and nothing led to it. Shown by the
    // verdict rather than by `allowed`, because `people.person.write` is financial class and
    // the screen it leads to offers the step-up: hiding it from somebody who could step up
    // makes the capability undiscoverable, and showing it to somebody the gate denies
    // outright is a button that answers 403.
    "people.person.write",
    // For the withheld marker's remedy, not for any read. See `@/lib/mask`.
    "member.identity.read",
  ] as const);
  // **The remedy has to match the cause.** A legal name is MOD-014's `identity` class and
  // `member.identity.read` opens it; that permission is `financial`, so a step-up lifts the
  // mask for a session holding the grant at too low an assurance and does nothing for a role
  // that does not hold it. The row said "step up" to both until now. See `@/lib/mask`.
  const remedy = withheldRemedy(gateVerdict(mayNames));
  const nameWithheld: MessageKey = remedy === "step_up"
    ? "member.withheldIdentity"
    : "member.withheldIdentityNoRemedy";

  const addLead = gateVerdict(mayWrite) === "denied" ? undefined : (
    <Button
      variant="secondary" size="md" href="/leads/new"
      label={text("leads.addLead")}
    />
  );

  if (!mayLeads.allowed) {
    const verdict = gateVerdict(mayLeads);
    return (
      <Shell locale={locale} numbering={numbering} view={view} filter={filter} board={null} coldAfter={48} action={addLead}>
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
      <Shell locale={locale} numbering={numbering} view={view} filter={filter} board={null} coldAfter={coldAfter} action={addLead}>
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
    meta: metaLine(locale, lead, numbering),
    source: lead.source ?? text("leads.noSource"),
    owner: lead.owner_person_id === null ? null : (nameOf(lead.owner_person_id) ?? ""),
    age: sinceLabel(locale, lead.hours_since_contact, numbering),
    next: lead.next_action ?? text("leads.noNext"),
    // **The board's column, not the stored sales stage.** The two disagree for anybody
    // with a membership, and the table is the other view of the same list.
    stage: wordFor(locale, stageWord(lead.board_stage), lead.board_stage),
    cold: lead.going_cold,
  }));

  if (board?.mine_is_zero_without_a_person_record !== undefined) {
    return (
      <Shell locale={locale} numbering={numbering} view={view} filter={filter} board={board} coldAfter={coldAfter} action={addLead}>
        {/* **Two different facts and only one is about the work.** A reader whose sign-in is
            not linked to a person owns no leads, and so does a reader with an empty queue --
            the first is ordinary, because staff hold permissions and do not have to be
            anybody in particular. MOD-026's board says the same thing one module over. */}
        <Banner severity="info">{text("leads.mineNeedsAPerson")}</Banner>
      </Shell>
    );
  }

  return (
    <Shell locale={locale} numbering={numbering} view={view} filter={filter} board={board} coldAfter={coldAfter} action={addLead}>
      {rows.some((row) => row.name === null) ? (
        <p className="ds-note">
          {remedy === "step_up" ? (
            <>
              {text("leads.namesWithheld")}{" "}
              <Link
                href={`/step-up?for=financial&action=member.identity.read&next=${
                  encodeURIComponent(view === "table" ? "/leads?view=table" : "/leads")}`}
              >
                {text("member.raiseSession")}
              </Link>
            </>
          ) : remedy === "no_answer" ? (
            text("member.namesWithheldNoAnswer")
          ) : (
            text("member.namesWithheldNotHeld")
          )}
        </p>
      ) : null}

      {rows.length === 0 ? (
        <Banner severity="info">
          {text(filter === "going_cold" ? "leads.emptyCold"
            : filter === "mine" ? "leads.emptyMine"
            : filter === "lost" ? "leads.emptyLost" : "leads.empty")}
        </Banner>
      ) : view === "table" ? (
        <>
          <LeadTable
            locale={locale}
            rows={rows}
            countLabel={fill(locale, "leads.countLabel", { count: rows.length }, numbering)}
            nameWithheld={nameWithheld}
          />
          <ProseNote>{text("leads.ageCarriesColour")}</ProseNote>
        </>
      ) : (
        <Board
          locale={locale}
          board={board}
          leads={leads}
          nameOf={nameOf}
          nameWithheld={nameWithheld}
          numbering={numbering}
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
  locale, board, leads, nameOf, nameWithheld, numbering,
}: {
  locale: Locale;
  board: Board | null;
  leads: LeadRow[];
  nameOf: (personId: string | null) => string | null;
  // Which sentence a withheld name gets: the page decides it from the gate's answer, because
  // only the page knows whether a step-up would lift the mask for this reader.
  nameWithheld: MessageKey;
  numbering: Numbering;
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
            count={columnCount(total, numbering)}
            countLabel={fill(locale, "leads.columnLabel", {
              stage: title, count: total,
            })}
            {...(hidden > 0
              ? { overflow: fill(locale, "leads.more", { count: hidden }, numbering) }
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
                    <Withheld locale={locale} reason={nameWithheld} />
                  )
                }
                meta={metaLine(locale, lead, numbering)}
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
  locale, view, filter, board, coldAfter, action, children, numbering,
}: {
  locale: Locale;
  numbering: Numbering;
  view: LeadView;
  filter: LeadFilter;
  board: Board | null;
  coldAfter: number;
  /**
   * The header's end slot. The live ADM-CRM-01 screen draws "Add a lead" there and this one
   * rendered nothing -- and it was not in the gap list either, so a specified control was
   * missing from the screen with no record anywhere that it was missing. ADM-CRM-04 is that
   * screen, and this is the only way to reach it.
   */
  action?: React.ReactNode;
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
      {/* **`PageHeader`, not a hand-rolled head.** This screen wrote its own header -- the
          same markup, with the figures in `.muted` rather than `.ds-page-figures` -- which is
          an ad-hoc copy of an approved component, and §8 of the directive of 2026-11-20
          forbids exactly that. The component carries the flex row, the text column's
          `min-inline-size` and the end slot, so the only thing this screen decides is what
          goes in them. */}
      <PageHeader
        id="leads-heading"
        title={text("leads.heading")}
        figures={board === null ? undefined : (
          <>
            {fill(locale, "leads.openLeads", { count: board.open_leads }, numbering)}
            {" · "}
            {fill(locale, "leads.goingCold", { count: board.going_cold }, numbering)}
          </>
        )}
        actions={action}
      />

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
        {/* **Table only, because the board has no column for it.** ADM-CRM-01 draws five
            stages and ADM-CRM-07 is a side sheet, so a lost chip on the board would ask for a
            list the board cannot draw -- and a chip that changed the view under the reader
            would be worse than one that is not there. */}
        {view === "table" ? (
          <Link
            href={here({ filter: "lost" })}
            aria-current={filter === "lost" ? "page" : undefined}
          >
            {text("leads.filterLost")}
          </Link>
        ) : null}
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

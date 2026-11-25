import Link from "next/link";

import { DataGrid } from "@/components/ds/data-grid";
import { Withheld, WithheldLink } from "@/components/withheld";
import { t, type Locale, type MessageKey } from "@/i18n/locale";

/** One row of ADM-CRM-02's table, with every display string computed on the server. */
export type LeadDisplay = {
  lead_id: string;
  /** The person's name as MOD-014 gives it, or null where it is withheld. */
  name: string | null;
  meta: string;
  source: string;
  owner: string | null;
  age: string;
  next: string;
  stage: string;
  cold: boolean;
};

/**
 * ADM-CRM-02 · LEAD LIST · TABLE VIEW.
 *
 * "Same grid component as the members list at the same 34px. ... Age is the sortable column
 * that matters -- a lead's value decays by the hour, so it carries colour where the others do
 * not."
 *
 * **The colour is `rowSeverity`, not a painted cell.** A cold lead is the one row state this
 * board has, and the grid's own severity is where it belongs: a screen that painted its own
 * would be the rule the usage sweep exists to keep.
 *
 * **A withheld name is still a link.** On an ordinary sign-in every identity field is masked,
 * and a row whose name was marked and not linked made the members list a dead end for the
 * front desk's own credential -- found twice by an independent tester, against the same cell.
 * The label a screen reader hears is built from what is *not* withheld: the source and the
 * age, which are this module's own.
 */
export function LeadTable({
  locale, rows, countLabel, nameWithheld,
}: {
  // Which sentence a withheld name gets: the page decides it from the gate's answer, because
  // only the page knows whether a step-up would lift the mask for this reader.
  nameWithheld: MessageKey;
  locale: Locale;
  rows: LeadDisplay[];
  countLabel: string;
}) {
  const text = (key: MessageKey) => t(locale, key);
  return (
    <DataGrid
      caption={text("leads.title")}
      labelledBy="leads-heading"
      rows={rows}
      rowKey={(row) => row.lead_id}
      rowSeverity={(row) => (row.cold ? "attention" : null)}
      countLabel={countLabel}
      columns={[
        {
          header: text("leads.colLead"),
          kind: "person" as const,
          priority: 1 as const,
          render: (row: LeadDisplay) => (
            <>
              {row.name === null ? (
                <WithheldLink
                  locale={locale}
                  reason={nameWithheld}
                  href={`/leads/${row.lead_id}`}
                  label={row.meta}
                />
              ) : (
                <Link href={`/leads/${row.lead_id}`}>{row.name}</Link>
              )}
              <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
                {row.meta}
              </div>
            </>
          ),
        },
        {
          header: text("leads.colSource"),
          kind: "text" as const,
          priority: 2 as const,
          render: (row: LeadDisplay) => row.source,
        },
        {
          header: text("leads.colOwner"),
          kind: "person" as const,
          priority: 3 as const,
          render: (row: LeadDisplay) =>
            row.owner === null ? (
              <span className="muted">{text("leads.noOwner")}</span>
            ) : row.owner === "" ? (
              // An owner whose own name is withheld. The cell says so rather than printing a
              // uuid where a name belongs, which is the members list's own finding.
              <Withheld locale={locale} reason={nameWithheld} />
            ) : (
              row.owner
            ),
        },
        {
          header: text("leads.colStage"),
          kind: "text" as const,
          priority: 2 as const,
          render: (row: LeadDisplay) => row.stage,
        },
        {
          header: text("leads.colAge"),
          kind: "date" as const,
          priority: 1 as const,
          render: (row: LeadDisplay) => row.age,
        },
        {
          header: text("leads.colNext"),
          kind: "text" as const,
          priority: 3 as const,
          render: (row: LeadDisplay) => row.next,
        },
      ]}
    />
  );
}

import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { DataGrid } from "@/components/ds/data-grid";
import { NotYet, PageHeader } from "@/components/ds/page-header";
import { fill, formatInteger, t, type MessageKey } from "@/i18n/locale";
import { currentSession, gate, gateMessage, gateVerdict } from "@/lib/api";
import { numerals } from "@/lib/display";
import {
  GRACE_KEY,
  RETRY_KEY,
  isDefaulted,
  readDunningPolicy,
  type DunningStage,
} from "@/lib/dunning";
import { presentation } from "@/lib/preferences";

import { PolicyForm } from "./policy-form";

/**
 * ADM-PAY-06 · DUNNING — what happens when a payment fails, and the floor beneath it.
 *
 * **Two of the canvas's five settings are controls and three are named absences**, which is
 * the whole shape of this screen. `retry_attempts` is what ADM-PAY-05's workspace sorts by and
 * `access_grace_days` is the day the journey starts recommending that access be restricted;
 * the hour a retry runs, the drafted message held for approval and the exception threshold
 * each configure machinery this build does not have. A control for one of those would be worse
 * than its absence: a tenant would believe they had configured something.
 *
 * **The journey is rendered rather than described.** The two figures produce five dated steps
 * and the server returns them, so what a reader checks is the thing the module will do rather
 * than a sentence about it — and the page holds no second copy of the stage table to disagree
 * with `collections.stages`.
 *
 * **The NEVER block is not a setting, and the canvas says so**: "it is the floor beneath every
 * dunning policy". Two of its four rules are properties of this build rather than intentions —
 * an access recommendation is recorded and never applied, and there is no stored card to
 * charge — and the list says which, because a floor a reader cannot tell from an intention is
 * a floor they have to take on trust.
 */
export default async function DunningRulesPage() {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);
  const numbering = await numerals();

  const session = await currentSession();
  if (!session) redirect("/login");

  const [mayRead, mayWrite] = await Promise.all([
    gate("finance.dunning.read"),
    gate("finance.dunning.manage"),
  ]);
  const policy = mayRead.allowed ? await readDunningPolicy().catch(() => null) : null;

  if (policy === null) {
    return (
      <div className="stack">
        <PageHeader title={text("dunning.title")} />
        <Banner severity="info" title={text("dunning.whenFails")}>
          {text(mayRead.allowed ? "error.unexpected" : gateMessage(mayRead))}
        </Banner>
      </div>
    );
  }

  const bothDefaulted = isDefaulted(policy, RETRY_KEY) && isDefaulted(policy, GRACE_KEY);

  return (
    <div className="stack">
      <PageHeader
        title={text("dunning.title")}
        figures={
          <>
            {fill(locale, "dunning.retriesCounted",
                  { count: policy.retry_attempts }, numbering)}
            {" · "}
            {fill(locale, "dunning.graceCounted",
                  { count: policy.access_grace_days }, numbering)}
          </>
        }
      />

      <section className="page-section">
        <h2 id="dunning-rules">{text("dunning.whenFails")}</h2>
        {/* **A default is not a decision**, which is the distinction MOD-005's own board draws
            for `scope_type: "default"`: the figures a reader sees are the journey this build
            already ran, and only one of the two is something to change. */}
        {bothDefaulted ? <p className="ds-note">{text("dunning.defaulted")}</p> : null}
        {/* **No `numbering`**, deliberately: a form field's value is typed back rather than
            rendered, so it stays ASCII. On an `arab` tenant a formatted figure in the box
            would be refused by the action's own parser -- the one place in this app where the
            tenant's numerals are correctly not applied. */}
        <PolicyForm
          locale={locale}
          retryAttempts={policy.retry_attempts}
          accessGraceDays={policy.access_grace_days}
          canWrite={mayWrite.allowed}
          stepUpHref={gateVerdict(mayWrite) === "needs_step_up"
            ? "/step-up?for=financial&action=finance.dunning.manage"
              + "&next=/payments/dunning"
            : null}
        />
        <p className="ds-note">{text("dunning.accountTerms")}</p>
      </section>

      <section className="page-section">
        <h2 id="dunning-journey">{text("dunning.journey")}</h2>
        <DataGrid
          caption={text("dunning.journey")}
          countLabel={fill(locale, "grid.count.stages", { count: policy.stages.length }, numbering)}
          labelledBy="dunning-journey"
          rows={policy.stages}
          rowKey={(row: DunningStage) => String(row.stage)}
          // **The restricting step is the one the setting moves**, so it is the one marked:
          // every other row is the product's own notice schedule and unremarkable.
          rowSeverity={(row: DunningStage) =>
            (row.access_recommendation === "restrict" ? "attention" : null)}
          columns={[
            {
              header: text("dunning.stage"),
              kind: "text",
              priority: 1,
              // A bare number needs no message: the same `{count}` in both catalogues is
              // what the untranslated-key sweep flags, and it is right to.
              render: (row: DunningStage) => (
                <span className="data">{formatInteger(row.stage, numbering)}</span>
              ),
            },
            {
              header: text("dunning.day"),
              // **`text`, not `date`.** A day offset is a count of days from a due date, not
              // a date: the grid's `date` kind is for an instant and would align and format it
              // as one, and the due date it is counted from differs per invoice.
              kind: "text",
              priority: 1,
              render: (row: DunningStage) => (
                <span className="data">{fill(locale, "dunning.dayNumber",
                  { count: row.days_after_due }, numbering)}</span>
              ),
            },
            {
              header: text("dunning.notice"),
              kind: "text",
              priority: 2,
              // The notification key, not a sentence: nothing sends, and a rendered message
              // would be a claim that one had been authored for this step.
              render: (row: DunningStage) => (
                <span className="data" dir="ltr">{row.notification_key}</span>
              ),
            },
            {
              header: text("dunning.access"),
              kind: "text",
              priority: 1,
              render: (row: DunningStage) =>
                text(`dunning.access.${row.access_recommendation}` as MessageKey),
            },
          ]}
        />
        <p className="ds-note">{text("dunning.accessIsRecorded")}</p>
      </section>

      <section className="page-section">
        <h2 id="dunning-floor">{text("dunning.floorTitle")}</h2>
        <ul className="ds-note">
          {policy.floor.map((one) => (
            <li key={one.rule}>
              {text(`dunning.floor.${one.rule}` as MessageKey)}
              {" — "}
              <span className="muted">
                {text(one.enforced ? "dunning.floorEnforced" : "dunning.floorIntended")}
              </span>
            </li>
          ))}
        </ul>
        <p className="ds-note">{text("dunning.floorNote")}</p>
      </section>

      <NotYet title={text("dunning.notYet")}>
        {policy.not_settable.map((one) => (
          <div key={one.setting} style={{ display: "contents" }}>
            <dt>{text(`dunning.not_settable.${one.setting}` as MessageKey)}</dt>
            <dd>{text(`dunning.waits.${one.waits_on}` as MessageKey)}</dd>
          </div>
        ))}
      </NotYet>
    </div>
  );
}

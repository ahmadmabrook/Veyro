import { redirect } from "next/navigation";
import Link from "next/link";

import { Banner } from "@/components/ds/banner";
import { PageHeader } from "@/components/ds/page-header";
import { ProseNote } from "@/components/prose";
import { t, type MessageKey } from "@/i18n/locale";
import { currentSession, gateAll, gateVerdict } from "@/lib/api";
import { presentation } from "@/lib/preferences";
import { REPORTS, UNBUILT } from "@/lib/reports";

/**
 * ADM-RPT-01 · REPORTS INDEX — "Reports, and the gate in front of an export".
 *
 * **The index is a gate, and the canvas says exactly what that buys**: "A Club Manager
 * opening this screen sees four reports, not six. The two financial ones are absent — not
 * listed and locked." So every entry names the permission its report needs, the page asks
 * `/authz/checks` about all of them in one round trip, and an entry the session cannot open
 * is not rendered. That is the rail's rule applied to a page, and §21's reason holds here
 * too: a greyed row is a promise that something could be unlocked.
 *
 * **What this build cannot report is named, not quietly missing.** The canvas lists six
 * reports and two exist. If the other four were simply absent they would read as four more
 * permissions the reader lacks -- and that is a false thing to teach somebody, because they
 * would go and ask for a grant that does not exist. Attendance, Coaching, Leads and Tax each
 * say which module they need. An index is a claim about what can be reported, so a short one
 * has to say why it is short.
 *
 * **ADM-RPT-05, the export gate, is the part worth not approximating.** The canvas draws a
 * tier-4 gate in front of every export of personal or financial data: a written reason
 * recorded and visible to the tenant, an option to leave contact details out, and step-up
 * authentication before the file is produced. Nothing in this build exports anything, so
 * there is nothing for the gate to stand in front of -- and a button that produced a file
 * without that record would be the control removed rather than the feature added. The screen
 * says so where the Export button would be.
 */
export default async function ReportsPage() {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  // One round trip for every report's permission. The same question the page behind each
  // entry will ask, with the same scope resolution and the same assurance weighing -- not a
  // permission list, which is MOD-014's "a grant is not a session" finding.
  const answers = await gateAll(REPORTS.map((report) => report.permission));
  const open = REPORTS.filter((_, index) => answers[index]?.allowed === true);

  // **A refusal and a failure are different facts, and this page told the first story about
  // the second.** `gateAll` fails closed, which is right for access: an unreachable gate is
  // not permission. But the empty state then said "No report here is open to this session --
  // that is about your own access", which is a confident wrong answer when the gate simply
  // could not be reached. Found by TestSprite, which reported the Revenue report absent for
  // an owner holding every permission in the catalogue; the page had been handed six closed
  // answers by a failed request and had no way to tell them from six refusals.
  //
  // Every refusal carrying a transport reason rather than `forbidden` means the gate did not
  // answer. `/finance` already makes this distinction for its trial balance.
  const unreachable = open.length === 0
    && answers.every((answer) => gateVerdict(answer) === "gate_failed");

  return (
    <>
      <PageHeader title={text("reports.heading")} />
      <ProseNote>{text("reports.lead")}</ProseNote>

      {unreachable ? (
        <Banner severity="critical">{text("reports.gateUnreachable")}</Banner>
      ) : open.length === 0 ? (
        // **Not a repeat of the lead.** An empty index has one thing to say that a populated
        // one does not: no report here is open to this session, which is a fact about the
        // reader's own access rather than about the product. The section below still names
        // what this build cannot report at all, so the two absences stay apart.
        <Banner severity="info">{text("reports.noneOpen")}</Banner>
      ) : (
        <ul className="ds-report-list" aria-label={text("reports.title")}>
          {open.map((report) => (
            <li key={report.href} className="ds-report-row">
              <div className="ds-report-main">
                <Link className="ds-report-name" href={report.href}>
                  {text(report.name)}
                </Link>
                <p className="ds-report-summary">{text(report.summary)}</p>
              </div>
              {/* The canvas prints the roles at the row's end. They are descriptive -- the
                  gate above decided whether this row exists at all -- so they are labelled
                  rather than left as four bare letters a reader has to decode. */}
              <span className="ds-report-roles data" dir="ltr">
                <span className="ds-visually-hidden">{text("reports.rolesLabel")}: </span>
                {report.roles}
              </span>
            </li>
          ))}
        </ul>
      )}

      <section className="page-section" aria-labelledby="reports-unbuilt">
        <h2 id="reports-unbuilt">{text("reports.notBuilt")}</h2>
        <dl className="facts">
          {UNBUILT.map((entry) => (
            <div key={entry.name} style={{ display: "contents" }}>
              <dt className="muted">{text(entry.name)}</dt>
              <dd style={{ margin: 0 }}>{text(entry.why)}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="page-section" aria-labelledby="reports-export">
        <h2 id="reports-export">{text("reports.exportTitle")}</h2>
        <ProseNote>{text("reports.exportBody")}</ProseNote>
      </section>
    </>
  );
}

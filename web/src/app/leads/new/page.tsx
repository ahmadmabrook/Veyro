import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { NotYet, PageHeader } from "@/components/ds/page-header";
import { t, type MessageKey } from "@/i18n/locale";
import { currentSession, gate, gateAll, gateMessage, gateVerdict } from "@/lib/api";
import { INTERESTS, interestWord } from "@/lib/leads";
import { listSources } from "@/lib/leads-reads";
import { presentation } from "@/lib/preferences";

import { LeadForm } from "./lead-form";

/**
 * ADM-CRM-04 · ADD LEAD.
 *
 * The one route into MOD-027's write path from a cold start, and the only screen in this app
 * that creates a `ppl_persons` row other than ADM-MEM-10 — which is the same check, the same
 * decisions and a different second write.
 *
 * **The read gate is what the screen is for.** Without `people.person.read` there is no
 * duplicate check, and a form that created records with no check is the opposite of this
 * screen's purpose, so the page refuses rather than degrading into one. That is ADM-MEM-10's
 * own judgement and it holds harder here: a lead is the record a member grows out of, and
 * "the lead ID becomes the member ID" means a duplicate created at this door is a duplicate
 * in the membership, the billing and the door log afterwards.
 *
 * **Three write-side answers, because three permissions decide different halves.** Creating a
 * person is `people.person.write`, financial class and a step-up; opening a lead against an
 * existing person is `crm.lead.write`, routine; and the dropdown needs `crm.source.read`,
 * which is a third. A page that asked one question would either offer a control that answers
 * 403 or withhold one that works.
 *
 * **The sub-line is rendered, and this is the one screen where that is not the prose
 * `PageHeader` bans.** Its rule is that the design's header is a title and a line of figures,
 * derived from every data canvas — and ADM-MEM-10's canvas obeys it, with the title and
 * nothing under it. This canvas draws "Name and phone are enough. Everything else can wait."
 * in the secondary ink under "New lead", and that sentence is not a description of the screen:
 * it is the form's own instruction, telling a receptionist they may stop after two fields.
 * A form has nothing to count, so the slot it would otherwise fill is free.
 */
export default async function NewLeadPage() {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);
  // The same `as const` the member record uses, and the reason the integer formatter takes
  // it as an argument rather than reading a locale.
  const numbering = "latn" as const;

  if (!(await currentSession())) redirect("/login");

  const [read, write, mayLead] = await gateAll([
    "people.person.read",
    "people.person.write",
    "crm.lead.write",
  ] as const);

  if (!read.allowed) {
    return (
      <>
        <PageHeader title={text("newLead.heading")} />
        <Banner severity="attention" title={text(gateMessage(read))}>
          {text("newLead.needsRead")}
          {gateVerdict(read) === "needs_step_up" ? (
            <>
              {" "}
              <Link href="/step-up?for=financial&action=people.person.read&next=/leads/new">
                {text("member.raiseSession")}
              </Link>
            </>
          ) : null}
        </Banner>
      </>
    );
  }

  // **A source nobody may read and a tenant with no sources are different facts**, so the
  // dropdown's absence is attributed rather than left to look like an empty catalogue —
  // which is the configuration board's own rule about a flag list.
  const maySources = await gate("crm.source.read");
  const sources = maySources.allowed
    ? (await listSources()).sources.map(
        (one) => ({ value: one.source_id, label: one.display_name }))
    : [];

  const interests = INTERESTS.map((value) => {
    const word = interestWord(value);
    // A vocabulary the backend stores is never a label, and `null` means this build has no
    // word for a value the server grew — in which case the stored form is shown rather than
    // the option being dropped, because a missing choice is a choice nobody can make.
    return { value, label: word === null ? value : text(word) };
  });

  return (
    <>
      <PageHeader title={text("newLead.heading")} figures={text("newLead.lead")} />

      <LeadForm
        locale={locale} numbering={numbering}
        canCreatePerson={write.allowed} personVerdict={gateVerdict(write)}
        canOpenLead={mayLead.allowed}
        sources={sources} interests={interests}
      />

      {maySources.allowed ? null : (
        <p className="muted ds-walk-in-note">{text("newLead.sourcesRefused")}</p>
      )}

      {/* Named rather than drawn, with the product's reason for each. A control that does
          nothing is worse than one that is not there, and a field whose value this build
          would drop on the floor is worse still. */}
      <NotYet title={text("newLead.notYet")}>
        <dt>{text("newLead.gapOwner")}</dt>
        <dd>{text("newLead.gapOwnerWhy")}</dd>
        <dt>{text("newLead.gapTrial")}</dt>
        <dd>{text("newLead.gapTrialWhy")}</dd>
        <dt>{text("newLead.gapAtomic")}</dt>
        <dd>{text("newLead.gapAtomicWhy")}</dd>
        <dt>{text("newLead.gapEmail")}</dt>
        <dd>{text("newLead.gapEmailWhy")}</dd>
      </NotYet>
    </>
  );
}

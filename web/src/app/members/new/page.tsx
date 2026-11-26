import Link from "next/link";

import { Banner } from "@/components/ds/banner";
import { NotYet } from "@/components/not-yet";
import { PageHeader } from "@/components/ds/page-header";
import { t, type MessageKey } from "@/i18n/locale";
import { gateAll, gateMessage, gateVerdict } from "@/lib/api";
import { numerals } from "@/lib/display";
import { presentation } from "@/lib/preferences";
import { withheldRemedy } from "@/lib/mask";

import { WalkInForm } from "./walk-in-form";

/**
 * ADM-MEM-10 · ADD MEMBER MANUALLY · RECEP, SALES.
 *
 * The design: "Sale sheet preceded by an identity block: name, phone, email, date of birth,
 * emergency contact, waiver. Duplicate detection runs on phone as it is typed and offers the
 * existing record rather than creating a second one." The drawn canvas is the identity block
 * and the interruption, and its footnote says why the screen exists at all: "Preventing the
 * duplicate costs one screen; ADM-MEM-11 exists because prevention is never perfect."
 *
 * **It needed a read that did not exist.** `find_duplicates` scores *pairs that already
 * exist* — both sides have to be rows — so the one moment a duplicate is cheap to prevent,
 * the moment before the second record is written, had nothing to ask. The index it uses has
 * been in MOD-014's schema since the module was built, with its own comment about finding
 * everybody who shares a value, and no route could pass it one. `GET /people/contact-match`
 * is that read, and this is the eighth instance of this build's "a writer with no reader"
 * shape found by trying to render something.
 *
 * **Two gates, asked separately, because they are not the same answer.** The check is
 * `people.person.read` and routine; the create is `people.person.write` and financial class,
 * which needs a stepped-up session. That split is the right way round and the page says so: a
 * desk can always find out that a record exists, and only creating a second one costs more.
 * A reader who holds the write at a password-only sign-in is offered the step-up rather than
 * a button that answers 403 — the freeze form's pattern, which is what made every form of
 * this kind buildable.
 *
 * **Three parts of the design are named rather than drawn**, each for a reason that is the
 * product's and not this screen's:
 *
 * - **The sale sheet.** ADM-MSH-01 is selling a membership: a price resolved through MOD-016,
 *   an agreement against a published contract version, a recorded signature and an
 *   activation. That is a flow rather than a field, and it is blocked on its own terms.
 * - **The emergency contact.** It is a second person and a relationship between them, and
 *   `ppl_relationships_kind` admits five kinds, none of which is one. `household` is the
 *   nearest and would be a different fact recorded under its name.
 * - **The waiver.** A waiver is a consent record citing a published document version and
 *   recorded for somebody else, which is `privacy.consent.record_on_behalf` — a separate and
 *   stronger permission, made so by MOD-009's own review because naming another subject is
 *   an escalation. A definition *can* be published here; none is, and which one a walk-in
 *   waiver cites is a product decision nobody has stated. A tick box with no version behind
 *   it would be a consent to nothing.
 */
export default async function AddMemberPage() {
  const { locale } = await presentation();
  // **The tenant's numerals rather than a constant** -- ADR-0015. Every count, date and time
  // on this page follows `localization.numerals`; money does not, and `MoneyValue` carries no
  // `numbering` prop at all so that exception is the component's rule rather than this page's
  // to remember. One read for the whole render: `conventions()` is React's per-request memo
  // and the layout starts it, so this costs no round trip of its own.
  const numbering = await numerals();
  const [read, write, mayNames] = await gateAll([
    "people.person.read",
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

  // **The read is what the screen is for.** Without it there is no duplicate check, and a
  // form that created records with no check is the opposite of this screen's purpose — so
  // the page refuses rather than degrading into one.
  if (!read.allowed) {
    return (
      <>
        <PageHeader title={t(locale, "walkIn.title")} />
        <Banner severity="attention" title={t(locale, gateMessage(read))}>
          {t(locale, "walkIn.needsRead")}
          {gateVerdict(read) === "needs_step_up" ? (
            <>
              {" "}
              <Link href="/step-up?for=financial&action=people.person.read&next=/members/new">
                {t(locale, "member.raiseSession")}
              </Link>
            </>
          ) : null}
        </Banner>
      </>
    );
  }

  return (
    <>
      {/* **"New member · walk-in" is the screen's title, not a subtitle under one.** The
          canvas's "ADM-MEM-10 · ADD MEMBER MANUALLY" strip is the specification's own label
          for the card, the way every canvas labels every card; the product title underneath
          it is this. The first version put "Add a member" above it and stacked the two, which
          is two titles for one screen — and the second was an h2, so a screen reader heard a
          section inside a page that has no other section.
          **And no explanatory lead.** The members list's own rule, stated where it was
          written: "the design's header is a title and a sub-line of figures; a paragraph
          describing what the screen is belongs in this file's own comments". This screen has
          nothing to count, so the header is the title alone. */}
      <PageHeader title={t(locale, "walkIn.heading")} />
      {/* **The verdict, not a boolean.** "A stronger sign-in would open this" and "you may
          not" are different facts with different next steps, and a form given one bit cannot
          tell them apart — so it would either offer a step-up to somebody it cannot help or
          withhold one from somebody it can. `gateVerdict` is what separates them. */}
      <WalkInForm
        nameWithheld={nameWithheld}
        locale={locale} numbering={numbering}
        canWrite={write.allowed} writeVerdict={gateVerdict(write)}
      />

      {/* Named rather than drawn, with the product's reason for each. A control that does
          nothing is worse than one that is not there, and a field whose value this build
          would drop on the floor is worse still. */}
      <NotYet locale={locale} items={["walkIn.gapSale", "walkIn.gapEmergency", "walkIn.gapWaiver", "walkIn.gapEmailCheck"]} />
    </>
  );
}

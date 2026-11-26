import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { PageHeader } from "@/components/ds/page-header";
import { NotYet } from "@/components/not-yet";
import { numerals } from "@/lib/display";
import { fill, t, type MessageKey } from "@/i18n/locale";
import { currentSession, gate, gateAll, gateMessage } from "@/lib/api";
import { readNames } from "@/lib/desk-reads";
import { listLocations } from "@/lib/organization";
import { isWithheld } from "@/lib/mask";
import { presentation } from "@/lib/preferences";
import { listSchedulableResources } from "@/lib/rota";

import { BookPtForm } from "./book-form";

/**
 * ADM-SCH-05 · SCHEDULE PT — "Book Yousef with Hala". ADR-0019.
 *
 * **The member comes from the link and the coach is picked here**, which is the canvas's own
 * shape read from the flow: the title names both because both are already chosen, and the one
 * a desk knows first is the member — they are standing there, and their credits are on the
 * membership tab this screen is reached from. A member *picker* would be a select of every
 * person in the tenant, which the canvas does not draw and which does not survive a second
 * club.
 *
 * **Three permissions, because the button is three acts**: creating the session, taking the
 * member's place and spending their credit. All three are routine — `data_access` with no
 * financial class — so this is MOD-019's second write form and the first that needs no
 * step-up offered before it: booking a coach for an hour is the ordinary work of a shift,
 * which is the argument the catalogue already makes for `scheduling.place.hold`.
 *
 * **What the canvas draws that this cannot** is the zero-credit button: "Sell a package first
 * ... opens POS-05 with Hala and Yousef pre-filled". The Point of Sale surface has no
 * implementation at all and taking money is the payment provider besides, so the screen names
 * selling a package as the next step and says where it would happen rather than offering a
 * control that answers nothing. "Never a blocked state with no way out" is honoured by saying
 * what the way out is.
 */
export default async function SchedulePtPage({
  searchParams,
}: {
  searchParams: Promise<{ person?: string; location?: string }>;
}) {
  const { locale } = await presentation();
  const numbering = await numerals();
  const text = (key: MessageKey) => t(locale, key);
  const query = await searchParams;

  if (!(await currentSession())) redirect("/login");

  const may = await gate("scheduling.schedule.read");
  if (!may.allowed) {
    return (
      <>
        <PageHeader title={text("pt.heading")} />
        <Banner severity="attention" title={text(gateMessage(may))}>
          {text("pt.needsRead")}
        </Banner>
      </>
    );
  }

  const personId = query.person ?? "";
  if (!personId) {
    return (
      <>
        <PageHeader title={text("pt.heading")} />
        <Banner severity="info" title={text("pt.whichMember")}>
          {text("pt.reachedFromAMember")}
        </Banner>
        <p className="page-section">
          <Link href="/members">{text("pt.openTheMembers")}</Link>
        </p>
      </>
    );
  }

  const three = await gateAll([
    "scheduling.personal_session.book",
    "scheduling.place.hold",
    "membership.entitlement.draw",
  ]);
  // **All three, because the button is three acts.** A reader holding one of them can do none
  // of it, and offering a control that would be refused by name is worse than its absence.
  const mayBook = three.every((one) => one.allowed);

  // The coaches, the club, and the member's own name where this reader may read one.
  const [coaches, locations, names] = await Promise.all([
    listSchedulableResources({ kind: "staff" }).catch(() => null),
    listLocations().catch(() => null),
    readNames([personId]).catch(() => null),
  ]);

  const staff = (coaches?.resources ?? []).filter((one) => one.status === "active");
  // **The club from the link, or the only one there is.** A coach's holds and rota are read
  // against a site, and a screen that guessed would book somebody at the wrong building.
  const locationId = query.location
    ?? (locations?.length === 1 ? locations[0]!.location_id : "");

  if (staff.length === 0 || !locationId) {
    return (
      <>
        <PageHeader title={text("pt.heading")} />
        <Banner severity="info" title={text("pt.nothingToBookWith")}>
          {text(staff.length === 0 ? "pt.noCoaches" : "pt.whichClub")}
        </Banner>
      </>
    );
  }

  const found = names?.get(personId);
  // **A withheld name is a marker and not a null**, which is MOD-014's own test for it: the
  // read answers `***` for a field this session cannot read, and treating that as absent
  // renders it as somebody's name. Here it decides only whether the title can say who.
  const memberName = found && !isWithheld(found.legal_name)
    ? found.legal_name
    : null;

  return (
    <>
      <PageHeader
        title={memberName === null
          ? text("pt.heading")
          : fill(locale, "pt.headingWith", { member: memberName })}
        figures={[text("pt.oneCoachOneMember")]}
      />

      <section className="page-section" aria-labelledby="pt-form">
        <h2 id="pt-form" className="ds-visually-hidden">{text("pt.heading")}</h2>
        <BookPtForm
          locale={locale}
          numbering={numbering}
          personId={personId}
          locationId={locationId}
          coaches={staff.map((one) => ({
            resource_id: one.resource_id, display_name: one.display_name,
          }))}
          memberName={memberName}
          mayBook={mayBook}
        />
      </section>

      {/* Three absences, named. The reasoning each used to carry -- POS-05 has no
          implementation so the zero-credit button has nowhere to go, a standing weekly slot
          is a template question nobody has asked, MOD-013 authors a notification and sends
          nothing -- is in `contracts/ui/design-compliance.md`, which is where a reader of
          this repository looks and a receptionist does not. */}
      <NotYet
        locale={locale}
        items={["pt.gapPosLabel", "pt.gapRecurringLabel", "pt.gapNotifyLabel"]}
      />
    </>
  );
}

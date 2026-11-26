import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { PageHeader } from "@/components/ds/page-header";
import { NotYet } from "@/components/not-yet";
import { CloseDrawerForm } from "@/app/payments/cash/close-form";
import { fill, formatMoney, t, type MessageKey } from "@/i18n/locale";
import { currentSession, gate, gateAll, gateMessage, gateVerdict } from "@/lib/api";
import { listLocations } from "@/lib/organization";
import { presentation } from "@/lib/preferences";
import { utcStamp } from "@/lib/time";
import { actFor, handoverCase, nameOf, type Drawer } from "@/lib/shift";
import {
  readChart, readDrawers, readLegalEntities, readPeopleOfIdentities,
} from "@/lib/shift-reads";
import { readNames } from "@/lib/desk-reads";

import { OpenShiftForm } from "./open-form";

/**
 * FD-07 · SHIFT OPEN AND CLOSE.
 *
 * "Opening float count, closing count, expected from the ledger, variance with a required
 * note above threshold, handover to the next person. Prints or emails the shift report."
 *
 * **The canvas is the open**, and it is the half this build had no notion of: ADM-PAY-09
 * writes the close, so that form is imported rather than written again -- one definition of
 * an act that posts to suspense. What is here is the open, the handover, and the note that
 * travels between them.
 *
 * **"Kareem left JOD 50.00 at 16:04" is three modules on one line.** The figure is MOD-018's
 * drawer balance, the time is the previous session's own close, and the name is MOD-014's
 * through `ppl_identity_links` -- a till's `closed_by` is a MOD-007 identity, so the chain is
 * identity, then person, then `/people/names`, composed here because `veyro_cp_app` holds
 * nothing on the identity plane and paragraph 1300 bars the join.
 *
 * **Every permission this screen needs is `data_access` or `configuration`**, which is why it
 * has working buttons: `finance.cash.session` is routine because a front desk opens a drawer
 * every shift, and the catalogue says a step-up between the two ends would make the till
 * wrong rather than safe. It is the second Front Desk screen with a write and the third in
 * the app.
 */
export default async function ShiftPage({
  searchParams,
}: {
  searchParams: Promise<{ location_id?: string; drawer?: string }>;
}) {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);
  const params = await searchParams;

  if (!(await currentSession())) redirect("/login");

  const [till, ledger] = await gateAll([
    "finance.cash.session",
    "finance.ledger.read",
  ] as const);

  if (!till.allowed) {
    return (
      <>
        <PageHeader title={text("deskShift.heading")} />
        <Banner severity="attention" title={text(gateMessage(till))}>
          {text("deskShift.needsTill")}
          {gateVerdict(till) === "needs_step_up" ? (
            <>
              {" "}
              <Link href={
                "/step-up?for=configuration&action=finance.cash.session"
                + "&next=/desk/shift"
              }>
                {text("member.raiseSession")}
              </Link>
            </>
          ) : null}
        </Banner>
      </>
    );
  }

  // **Listing the sites is a different permission from opening a drawer**, which is the
  // schedule board's own finding: a session holding the till permission alone is told to
  // arrive from a link that names the site rather than shown an empty picker, because an
  // empty picker reads as "this tenant has no sites".
  const maySites = await gate("tenancy.organization.read");
  const locationId = params.location_id ?? "";
  if (locationId === "") {
    const sites = maySites.allowed ? await listLocations() : [];
    return (
      <>
        <PageHeader title={text("deskShift.heading")}
          figures={text("deskShift.lead")} />
        {!maySites.allowed ? (
          <Banner severity="attention" title={text("deskShift.whichSite")}>
            {text("deskShift.whichSiteRefused")}
          </Banner>
        ) : sites.length === 0 ? (
          <Banner severity="attention" title={text("deskShift.noSites")}>
            {text("deskShift.noSitesWhat")}
          </Banner>
        ) : (
          <nav aria-label={text("deskShift.whichSite")} className="ds-filter-bar">
            {sites.map((site) => (
              <Link key={site.location_id} className="ds-filter-chip"
                href={`/desk/shift?location_id=${site.location_id}`}>
                {site.location_name}
              </Link>
            ))}
          </nav>
        )}
      </>
    );
  }

  const { drawers, ...disclosure } = await readDrawers(locationId);

  // **The chart and the entity are what a posting needs**, and both are separate permissions:
  // a float comes from a `cash` account that is not the drawer, a difference lands in
  // `suspense`, and either posting names a legal entity. A session that cannot read them gets
  // the count field and a sentence rather than a button that answers 422.
  const chart = ledger.allowed ? (await readChart()).accounts : [];
  // **The same permission the sites came from**, which is also what reads the entities: a
  // location and a legal entity are both the organization's, so there is one gate here
  // rather than two that can disagree.
  const entities = maySites.allowed ? await readLegalEntities() : [];
  const legalEntityId = entities[0]?.legal_entity_id ?? "";
  const suspenseAccountId = chart.find(
    (account) => account.account_kind === "suspense")?.account_id ?? "";

  // **The names behind the actors, where this session may read them.** An identity with no
  // person is the ordinary staff case, so a drawer handed over by one says "a staff member"
  // rather than drawing a blank name -- which is only possible because the link read leaves
  // an unlinked identity out of its answer instead of returning it with a null.
  const identityIds = [...new Set(drawers.flatMap((one) => [
    one.open_session?.opened_by,
    one.handed_over?.closed_by,
  ]).filter((id): id is string => typeof id === "string" && id !== ""))];
  const mayPeople = await gate("people.person.read");
  const links = mayPeople.allowed && identityIds.length > 0
    ? (await readPeopleOfIdentities(identityIds)).people
    : [];
  const names = mayPeople.allowed && links.length > 0
    ? await readNames(links.map((one) => one.person_id))
    : new Map();
  // `nameOf` is `@/lib/shift`'s, so the three absences it has to treat alike -- an identity
  // that is nobody, a name this session may not read, and a person with none recorded -- have
  // cases a browser cannot reach: the fixture's drawer actors are linked to no person at all.
  const personOf = (identityId: string): string | null =>
    nameOf(identityId, links, names);

  const chosen = params.drawer ?? "";
  const drawer: Drawer | undefined = chosen === ""
    ? drawers[0]
    : drawers.find((one) => one.cash_account_id === chosen);
  const amount = (minor: number, currency: string) =>
    // **`latn`, and no tenant read on this page at all.** ADM-SET-07's money exception
    // covers every figure here -- a float, a count, a variance -- so there is nothing on
    // this screen that follows `localization.numerals` and nothing to fetch.
    formatMoney(minor, currency, "latn", locale);

  return (
    <>
      <PageHeader title={text("deskShift.heading")}
        figures={text("deskShift.lead")} />

      {drawers.length > 1 ? (
        <nav aria-label={text("deskShift.whichDrawer")} className="ds-filter-bar">
          {drawers.map((one: Drawer) => (
            <Link key={one.cash_account_id} className="ds-filter-chip"
              aria-current={one.cash_account_id === drawer?.cash_account_id
                ? "page" : undefined}
              href={`/desk/shift?location_id=${locationId}&drawer=${one.cash_account_id}`}>
              {one.drawer_label}
            </Link>
          ))}
        </nav>
      ) : null}

      {drawer === undefined ? (
        <Banner severity="attention" title={text("deskShift.noDrawers")}>
          {disclosure.a_drawer_is_an_account_that_has_had_a_session}
        </Banner>
      ) : (
        <section className="ds-cash-drawer">
          <h2>
            {fill(locale, "deskShift.drawerIs", {
              label: drawer.drawer_label,
              amount: amount(drawer.expected_minor, drawer.currency),
            })}
          </h2>
          <p className="muted" style={{ margin: 0 }}>
            {disclosure.expected_is_derived_from_postings}
          </p>

          {/* **The canvas's handover line, and the three states it does not draw.** A drawer
              banked to nothing, one whose standing money came from a journal rather than a
              shift, and one nobody has ever closed are all real and none of them has a person
              or a figure to name -- so printing the canvas's sentence for them would be the
              confident wrong answer MOD-014's own Member 360 was bitten by. */}
          <Handover drawer={drawer} personOf={personOf}
            amount={amount} locale={locale} />

          {actFor(drawer) === "close" && drawer.open_session !== null ? (
            legalEntityId === "" ? (
              <Banner severity="attention" title={text("deskShift.cannotClose")}>
                {text("deskShift.cannotCloseWhat")}
              </Banner>
            ) : (
              <CloseDrawerForm
                locale={locale}
                sessionId={drawer.open_session.session_id}
                legalEntityId={legalEntityId}
                suspenseAccountId={suspenseAccountId}
                currency={drawer.currency}
                expectedMinor={drawer.expected_minor}
                back="/desk/shift"
                askForNote
              />
            )
          ) : (
            <OpenShiftForm
              locale={locale} drawer={drawer}
              locationId={locationId}
              legalEntityId={legalEntityId}
              suspenseAccountId={suspenseAccountId}
              safeAccountId={chart.find(
                (account) => account.account_kind === "cash"
                  && account.account_id !== drawer.cash_account_id,
              )?.account_id ?? ""}
            />
          )}
        </section>
      )}

      <NotYet
        locale={locale}
        items={["deskShift.gapReport", "deskShift.gapThreshold", "deskShift.gapAbandon", "deskShift.gapWhichSite"]}
      />
    </>
  );
}

/** The handover panel: who left what, when, and what they passed on. */
function Handover({
  drawer, personOf, amount, locale,
}: {
  drawer: Drawer;
  personOf: (identityId: string) => string | null;
  amount: (minor: number, currency: string) => string;
  locale: Parameters<typeof t>[0];
}) {
  const text = (key: MessageKey) => t(locale, key);
  const left = handoverCase(drawer);
  const note = drawer.handed_over?.handover_note ?? null;

  return (
    <section data-testid="handover">
      <p style={{ margin: 0 }}>
        {left.kind === "left"
          ? fill(locale, "deskShift.leftBy", {
            who: personOf(left.by) ?? text("deskShift.aStaffMember"),
            amount: amount(left.counted, drawer.currency),
            at: utcStamp(left.at),
          })
          : left.kind === "emptied"
            ? text("deskShift.wasEmptied")
            : left.kind === "unattributed"
              ? fill(locale, "deskShift.standingUnattributed",
                { amount: amount(left.standing, drawer.currency) })
              : text("deskShift.firstEver")}
      </p>
      {note !== null ? (
        <>
          <h3 data-testid="handover-note-heading">
            {left.kind === "left"
              ? fill(locale, "deskShift.handedOverFrom", {
                who: personOf(left.by) ?? text("deskShift.aStaffMember"),
              })
              : text("deskShift.handedOver")}
          </h3>
          <p style={{ margin: 0 }}>{note}</p>
          <p className="muted" style={{ margin: 0 }}>{text("deskShift.noteWhat")}</p>
        </>
      ) : null}
    </section>
  );
}

import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { NotYet, PageHeader } from "@/components/ds/page-header";
import { t, type MessageKey } from "@/i18n/locale";
import { currentSession, gate, gateAll, gateMessage, gateVerdict } from "@/lib/api";
import { isUuid } from "@/lib/scheduling";
import { listLocations } from "@/lib/organization";
import { listSchedulableResources } from "@/lib/rota";
import { presentation } from "@/lib/preferences";

import { ClassForm } from "./class-form";

/**
 * ADM-SCH-03 · CREATE A CLASS.
 *
 * "Type, coach, room, capacity, recurrence, waitlist policy. Conflict detection on coach and
 * room runs as fields change, not on save."
 *
 * **MOD-019's first write form.** Every other write on this surface is read-only here and the
 * gap note said so for all five, which was true and is not a reason: three of these
 * permissions are financial class, and the step-up offered *before* the button is what makes a
 * form of this kind buildable at all -- ADM-MSH-03's precedent, and FD-05's.
 *
 * **Three permissions, because the button is three acts.** Drafting the template, publishing
 * it and generating its sessions are MOD-019's own division -- "a draft affects nobody and a
 * publication is what members plan their week around" -- so the page asks about all three and
 * the form reports which one it reached.
 *
 * **Four facts the canvas does not draw are derived and said**: the template's code, its
 * display name, the date range the rule covers, and the site. The first two because this build
 * has no template numbering scheme and asking a manager to invent one would be asking them to
 * do the product's job; the third because `recurrence.Rule` requires an end and "repeats
 * weekly" has none; the fourth from the link, which is the board's own pattern.
 */
export default async function NewClassPage({
  searchParams,
}: {
  searchParams: Promise<{ location?: string }>;
}) {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  const may = await gate("scheduling.schedule.read");
  if (!may.allowed) {
    return (
      <>
        <PageHeader title={text("newClass.heading")} />
        <Banner severity="attention" title={text(gateMessage(may))}>
          {text("newClass.needsRead")}
        </Banner>
      </>
    );
  }

  const [draft, publish, override] = await gateAll([
    "scheduling.template.write",
    "scheduling.schedule.publish",
    "scheduling.conflict.override",
  ] as const);

  const maySites = await gate("tenancy.organization.read");
  const sites = maySites.allowed ? await listLocations().catch(() => null) : null;
  const params = await searchParams;
  const chosen = isUuid(params.location) ? params.location : sites?.[0]?.location_id;
  if (chosen === undefined) {
    return (
      <>
        <PageHeader title={text("newClass.heading")} />
        <Banner severity="attention" title={text("newClass.noSite")}>
          {sites === null ? text("schedule.pickSiteInLink") : text("schedule.noLocation")}
        </Banner>
      </>
    );
  }

  // **Three pickers, one read each, narrowed by kind and site.** `listSchedulableResources`
  // is the rota picker's own read, taking a kind and a location -- a second one here would be
  // two definitions of "which rooms are at this club".
  const [services, rooms, staff] = await Promise.all([
    listSchedulableResources({ kind: "service" }).catch(() => null),
    listSchedulableResources({ kind: "room", locationId: chosen }).catch(() => null),
    listSchedulableResources({ kind: "staff", locationId: chosen }).catch(() => null),
  ]);

  // **A chart with nothing in it is a different fact from a refused read**, and both are
  // different from a tenant that has rooms at another club: the service format has no
  // location, so it is read tenant-wide, and the room and the coach are this club's.
  const missing = services === null || rooms === null || staff === null;
  const empty = !missing
    && (services.resources.length === 0 || rooms.resources.length === 0
        || staff.resources.length === 0);

  const today = new Date();
  const from = new Date(today.getTime() + 86_400_000).toISOString().slice(0, 10);
  // **Ninety days, derived, because the canvas draws no end date and the rule needs one.**
  // `recurrence.MAX_HORIZON_DAYS` is 400 and a term is the unit a gym publishes, so a quarter
  // is the honest default -- and the form says the dates rather than hiding them.
  const until = new Date(today.getTime() + 91 * 86_400_000).toISOString().slice(0, 10);

  return (
    <>
      <PageHeader title={text("newClass.heading")} figures={text("newClass.lead")} />

      {missing ? (
        <Banner severity="attention" title={text("newClass.chartRefused")}>
          {text("newClass.chartRefusedWhat")}
        </Banner>
      ) : empty ? (
        <Banner severity="attention" title={text("newClass.chartEmpty")}>
          {text("newClass.chartEmptyWhat")}
        </Banner>
      ) : (
        <ClassForm
          locale={locale}
          locationId={chosen}
          services={services.resources.map(
            (one) => ({ value: one.resource_id, label: one.display_name }))}
          rooms={rooms.resources.map(
            (one) => ({ value: one.resource_id, label: one.display_name }))}
          staff={staff.resources.map(
            (one) => ({ value: one.resource_id, label: one.display_name }))}
          today={from} until={until}
          canDraft={draft.allowed} canPublish={publish.allowed}
          canOverride={override.allowed}
          draftVerdict={gateVerdict(draft)}
        />
      )}

      <NotYet title={text("newClass.notYet")}>
        <dt>{text("newClass.gapCeiling")}</dt>
        <dd>{text("newClass.gapCeilingWhy")}</dd>
        <dt>{text("newClass.gapWaitlist")}</dt>
        <dd>{text("newClass.gapWaitlistWhy")}</dd>
        <dt>{text("newClass.gapQualified")}</dt>
        <dd>{text("newClass.gapQualifiedWhy")}</dd>
        <dt>{text("newClass.gapEdit")}</dt>
        <dd>{text("newClass.gapEditWhy")}</dd>
      </NotYet>

      <p className="muted ds-walk-in-note">
        <Link href={`/schedule?site=${chosen}`}>{text("newClass.backToCalendar")}</Link>
      </p>
    </>
  );
}

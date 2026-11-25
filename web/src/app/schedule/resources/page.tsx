import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { DataGrid } from "@/components/ds/data-grid";
import { PageHeader } from "@/components/ds/page-header";
import { ProseNote } from "@/components/prose";
import { fill, t, type MessageKey } from "@/i18n/locale";
import {
  currentSession,
  failureMessage,
  gate,
  gateMessage,
  gateVerdict,
} from "@/lib/api";
import { numerals } from "@/lib/display";
import { listLocations, type Location } from "@/lib/organization";
import { presentation } from "@/lib/preferences";
import {
  equipmentLine,
  isSpace,
  listSchedulingResources,
  type SchedulingResource,
  type SchedulingResourceList,
} from "@/lib/rooms";

/**
 * ADM-SCH-06 · ROOMS & RESOURCES. ADR-0018.
 *
 * The canvas is a read-only card: a table of `{{ r.name }} · {{ r.cap }} · {{ r.equip }}` and
 * one sentence beneath it.
 *
 * > Capacity here is the ceiling every class inherits. Double-booking is impossible because
 * > ADM-SCH-03 reads this list — the constraint lives in one place, not in each scheduler's
 * > memory.
 *
 * **Three different numbers, and this build had one of them.** `quantity` is how many of a
 * thing there are, a class's own places are on its capacity policy, and what the middle column
 * draws is neither: how many *people* a space holds. `0035` adds that and the relation the
 * third column needs — which space a piece of equipment is in — because `location_id` is a
 * club, so twenty bikes were at Khalda and in no particular studio.
 *
 * **No action, because the canvas draws none.** A capacity and a containment are stated when a
 * resource is registered: `sch_resources` grants `display_name` and the four retirement
 * columns and nothing more, so neither carries an UPDATE and both follow `quantity`'s own
 * arrangement. ADR-0018 says what that costs — a refit that re-rates a room needs a route that
 * does not exist — and the alternative was a grant no service writes, which is this build's
 * `cat_prices.effective_to` finding for the third time.
 *
 * **A capacity of null is unstated and the screen says so**, because a room nobody has
 * described does not bind a class and "holds 0" is a different fact — the one a reader would
 * act on.
 */
export default async function SchedulingResourcesPage({
  searchParams,
}: {
  searchParams: Promise<{ site?: string }>;
}) {
  const { locale } = await presentation();
  const numbering = await numerals();
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  const may = await gate("scheduling.schedule.read");
  if (!may.allowed) {
    const verdict = gateVerdict(may);
    return (
      <>
        <PageHeader title={text("rooms.heading")} />
        <Banner severity={verdict === "gate_failed" ? "critical" : "info"}>
          {text(gateMessage(may))}
        </Banner>
      </>
    );
  }

  // Listing the clubs is a different permission from reading the resources, which is the
  // schedule board's own rule: every row carries its own name and kind, so a session holding
  // only the schedule read gets the whole list and no picker.
  const maySites = await gate("tenancy.organization.read");
  const sites: Location[] | null = maySites.allowed
    ? await listLocations().catch(() => null)
    : null;

  const params = await searchParams;
  const site = isUuid(params.site) ? params.site : undefined;

  let listed: SchedulingResourceList | null = null;
  let failed: MessageKey | null = null;
  try {
    listed = await listSchedulingResources(site ? { location_id: site } : {});
  } catch (error) {
    failed = failureMessage(error);
  }

  if (listed === null) {
    return (
      <>
        <PageHeader title={text("rooms.heading")} />
        <Banner severity="critical">{text(failed ?? "error.unexpected")}</Banner>
      </>
    );
  }

  const spaces = listed.resources.filter(isSpace);
  const described = spaces.filter((one) => one.capacity !== null);

  return (
    <div className="stack">
      <PageHeader
        title={text("rooms.heading")}
        figures={
          <>
            {fill(locale, "rooms.count", { count: spaces.length }, numbering)}
            {" · "}
            {fill(locale, "rooms.described", { count: described.length }, numbering)}
          </>
        }
      />

      {/* The schedule's own view bar, so this is a fourth view rather than an orphan page:
          the canvas draws it as a card beside the week and the rota, and a route nothing
          links to is a route nobody finds. */}
      <nav aria-label={text("schedule.views")} className="ds-filter-bar">
        <Link href="/schedule" className="ds-filter-chip">{text("schedule.week")}</Link>
        <Link href="/rota" className="ds-filter-chip">{text("schedule.coaches")}</Link>
        <Link
          href="/schedule/resources"
          aria-current="page"
          className="ds-filter-chip"
        >
          {text("rooms.view")}
        </Link>
      </nav>

      {sites !== null && sites.length > 1 ? (
        <nav aria-label={text("rooms.filterSites")} className="ds-filter-bar">
          <Link
            href="/schedule/resources"
            aria-current={site === undefined ? "page" : undefined}
            className="ds-filter-chip"
          >
            {text("rooms.everyClub")}
          </Link>
          {sites.map((one) => (
            <Link
              key={one.location_id}
              href={`/schedule/resources?site=${one.location_id}`}
              aria-current={site === one.location_id ? "page" : undefined}
              className="ds-filter-chip"
            >
              {one.location_name}
            </Link>
          ))}
        </nav>
      ) : null}

      {/* **A panel, which is the design system's own shape for a titled block.** The first
          version wrote its own `ds-section-heading`, and the undefined-class sweep said that
          class styles nothing -- a heading rendered as body text, invisible to every layer
          that is not a screenshot. */}
      <section className="ds-panel" aria-labelledby="rooms-heading">
        <div className="ds-panel-head">
          <h2 id="rooms-heading" className="ds-panel-title">{text("rooms.spaces")}</h2>
        </div>
        <div className="ds-panel-body">
      {spaces.length === 0 ? (
        <Banner severity="info">{text("rooms.noSpaces")}</Banner>
      ) : (
        <DataGrid
          caption={text("rooms.spaces")}
          labelledBy="rooms-heading"
          rows={spaces}
          rowKey={(row) => row.resource_id}
          columns={[
            {
              header: text("rooms.colName"),
              kind: "text",
              priority: 1,
              render: (row: SchedulingResource) => (
                <>
                  <span>{row.display_name}</span>
                  <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
                    <span className="data" dir="ltr">{row.resource_code}</span>
                    {" · "}
                    {text(kindKey(row.resource_kind))}
                  </div>
                </>
              ),
            },
            {
              // **The canvas's middle column, and the one whose absence is the slice.** Null
              // is unstated rather than zero: a room nobody has described does not bind.
              header: text("rooms.colCapacity"),
              kind: "text",
              priority: 1,
              render: (row: SchedulingResource) =>
                row.capacity === null ? (
                  <span className="muted">{text("rooms.unstated")}</span>
                ) : (
                  <span className="data">
                    {fill(locale, "rooms.holds", { count: row.capacity }, numbering)}
                  </span>
                ),
            },
            {
              // **What is *in* the room, not what is at the club.** That distinction is the
              // relation `0035` adds, and it is what makes "20 bikes" a figure about this
              // space rather than about the building.
              header: text("rooms.colEquipment"),
              kind: "text",
              priority: 2,
              render: (row: SchedulingResource) => {
                const lines = equipmentLine(row);
                if (lines.length === 0) {
                  return <span className="muted">{text("rooms.nothingInIt")}</span>;
                }
                return (
                  <span className="data" dir="ltr">{lines.join(" · ")}</span>
                );
              },
            },
          ]}
        />
      )}
        </div>
      </section>

      <section className="ds-panel">
        <div className="ds-panel-head">
          <h2 className="ds-panel-title">{text("rooms.ceilingTitle")}</h2>
        </div>
        <div className="ds-panel-body">
          <ProseNote>{text("rooms.ceilingWhy")}</ProseNote>
        </div>
      </section>

      <section className="ds-panel">
        <div className="ds-panel-head">
          <h2 className="ds-panel-title">{text("rooms.notYet")}</h2>
        </div>
        <div className="ds-panel-body">
          <dl className="facts">
            <dt>{text("rooms.editTitle")}</dt>
            <dd style={{ margin: 0 }}><ProseNote>{text("rooms.editWhy")}</ProseNote></dd>
            <dt>{text("rooms.assignTitle")}</dt>
            <dd style={{ margin: 0 }}><ProseNote>{text("rooms.assignWhy")}</ProseNote></dd>
          </dl>
        </div>
      </section>
    </div>
  );
}

function kindKey(kind: string): MessageKey {
  switch (kind) {
    case "zone": return "rooms.kindZone";
    case "court": return "rooms.kindCourt";
    default: return "rooms.kindRoom";
  }
}

function isUuid(value: string | undefined): value is string {
  return (
    value !== undefined
    && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)
  );
}

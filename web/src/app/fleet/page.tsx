import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { DataGrid } from "@/components/ds/data-grid";
import { fill, formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { PageHeader } from "@/components/ds/page-header";
import { currentSession, gate, failureMessage, gateMessage } from "@/lib/api";
import { readEntries } from "@/lib/access";
import { readFleet, type FleetView } from "@/lib/fleet";
import { presentation } from "@/lib/preferences";
import { utcStamp } from "@/lib/time";

/**
 * MOD-021's fleet board: what is installed, what it can do, and what has gone quiet.
 *
 * **Two of the columns are derived at read time and the page says so.** `reachability` is
 * worked out from the last health report a device sent, not stored -- and **nothing in this
 * build polls on a schedule**, so a board that read as live would be claiming a freshness the
 * product does not have. It is "as of" the moment the page was built, which is the honest
 * framing and the one MOD-021's own gap list implies: a device nobody sweeps has its silence
 * reach no dashboard.
 *
 * **"Needs somebody" is not "unusual".** `blocks_operation` is `active` *and* `offline`
 * together: a device deliberately in maintenance is not an incident, and one nobody has
 * finished installing is not either. Listing those as problems is how an alert channel gets
 * muted.
 */
export default async function FleetPage() {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  const may = await gate("devices.device.read");
  if (!may.allowed) {
    return (
      <Shell locale={locale}>
        <Banner severity="info">
          {text(gateMessage(may))}
        </Banner>
      </Shell>
    );
  }

  let fleet: FleetView;
  try {
    fleet = await readFleet();
  } catch (error) {
    return (
      <Shell locale={locale}>
        <Banner severity="critical">
          {text(failureMessage(error))}
        </Banner>
      </Shell>
    );
  }

  const attention = new Set(fleet.needs_attention);
  // ADM-ACC-01's TODAY column, composed from MOD-022: a device knows nothing about doors,
  // and `acc_points` is the join MOD-021 deliberately did not make. A reader who may not
  // see the access plane gets the board without the column rather than a refusal.
  const entries = (await gate("access.zone.read")).allowed
    ? await readEntries().catch(() => null)
    : null;

  return (
    <Shell
      locale={locale}
      // **The title is the finding.** Every canvas in this design heads a board with what it
      // found -- "One reader is down", "Three things need you this morning" -- and puts the
      // noun on the rail. A heading that says "Devices" over a table of devices is the one
      // sentence on the screen that tells a reader nothing.
      title={
        attention.size === 0
          ? text("fleet.allAnswering")
          : fill(locale, "fleet.someDown", { count: attention.size })
      }
      // The board's own three answers, as figures: how many devices, how many need somebody,
      // and when the reachability was worked out. The last is the one a reader has to have:
      // nothing polls, so the board is "as of" when it loaded.
      figures={
        <>
          <span className="data">{formatInteger(fleet.devices.length, "latn")}</span>{" "}
          {text("fleet.counted")}
          {" \u00b7 "}
          <span className="data">{formatInteger(attention.size, "latn")}</span>{" "}
          {text("fleet.attention").toLocaleLowerCase(locale)}
          {" \u00b7 "}
          {text("fleet.asOf")}{" "}
          <span className="data" dir="ltr">{utcStamp(new Date().toISOString())}</span>
        </>
      }
    >
      <section className="page-section">
        {/* The grid's accessible name. Visible, it was the third "Devices" on a screen
            whose rail entry and title already said so -- and the title says what was found
            rather than what the table is. */}
        <h2 id="fleet-heading" className="ds-visually-hidden">{text("fleet.title")}</h2>
        {fleet.devices.length === 0 ? (
          <Banner severity="info">{text("fleet.empty")}</Banner>
        ) : (
          <DataGrid
            caption={text("fleet.title")}
labelledBy="fleet-heading"
            rows={fleet.devices}
            rowKey={(device) => device.device_id}
            // **The row-level roll-up, which the hand-rolled table had no way to carry.** The
            // edge-mark says at a glance which rows need somebody, and the badge below still
            // names the specific state -- "the same scale expressed at two granularities,
            // which is what stopped them reading as two independent signals".
            rowSeverity={(device) => (device.blocks_operation ? "attention" : null)}
            columns={[
              {
                header: text("fleet.device"),
                kind: "person",
                priority: 1,
                render: (device) => (
                  <>
                    <Link href={`/fleet/${device.device_id}`}>{device.display_name}</Link>
                    <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
                      {/* A serial number is an identifier: ASCII, never translated, and
                          reordered by the bidi algorithm inside an Arabic page without
                          `dir`. */}
                      <span className="data" dir="ltr">{device.serial_number}</span>
                    </div>
                  </>
                ),
              },
              {
                header: text("fleet.reachability"),
                kind: "status",
                // Priority 1: "which of these needs somebody" is the question this board
                // exists to answer, so it survives every width.
                priority: 1,
                render: (device) => (
                  <>
                    {text(`fleet.reach.${device.reachability}` as MessageKey)}
                    {device.blocks_operation ? (
                      <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
                        {text("fleet.attention")}
                      </div>
                    ) : null}
                  </>
                ),
              },
              {
                header: text("fleet.club"),
                kind: "text",
                // Priority 1: "Sweifieh main door stopped responding" is the sentence
                // ADM-ACC-01 is built around, and the club is half of it. A board of serial
                // numbers with no site on them is one nobody can act on.
                priority: 1,
                render: (device) => device.location_name,
              },
              {
                header: text("fleet.today"),
                kind: "text",
                priority: 2,
                render: (device) => {
                  if (entries === null) {
                    return <span className="muted">{text("fleet.entriesUnknown")}</span>;
                  }
                  const count = entries.by_device[device.device_id];
                  // **A device that is not a door counts nothing, which is not zero.** A
                  // scanner at no access point has no entries to have; rendering `0` would
                  // say people are not walking through a thing nobody walks through.
                  return count === undefined ? (
                    <span className="muted">{text("fleet.notADoor")}</span>
                  ) : (
                    <span className="data" dir="ltr">{formatInteger(count, "latn")}</span>
                  );
                },
              },
              {
                header: text("fleet.state"),
                kind: "status",
                priority: 2,
                render: (device) => device.state,
              },
              {
                header: text("fleet.lastSeen"),
                kind: "date",
                priority: 2,
                render: (device) =>
                  device.last_seen_at === null ? (
                    <span className="muted">{text("fleet.never")}</span>
                  ) : (
                    <span className="data" dir="ltr">{utcStamp(device.last_seen_at)}</span>
                  ),
              },
              {
                header: text("fleet.kind"),
                kind: "text",
                priority: 3,
                render: (device) => device.kind,
              },
            ]}
          />
        )}
        <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
          {text("fleet.asOf")}{" "}
          <span className="data" dir="ltr">
            {utcStamp(fleet.as_of)}
          </span>
          {" · "}
          <span className="data">{formatInteger(fleet.count, "latn")}</span>{" "}
          {text("fleet.counted")}
        </p>
      </section>

      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("fleet.attention")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("fleet.attentionDetail")}
        </p>
        {attention.size === 0 ? (
          <Banner severity="info">{text("fleet.allWell")}</Banner>
        ) : (
          <ul style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
            {fleet.devices
              .filter((device) => attention.has(device.device_id))
              .map((device) => (
                <li key={device.device_id}>
                  <Link href={`/fleet/${device.device_id}`}>{device.display_name}</Link>
                </li>
              ))}
          </ul>
        )}
      </section>
    </Shell>
  );
}

function Shell({
  locale,
  children,
  figures,
  title,
}: {
  locale: Locale;
  children: React.ReactNode;
  figures?: React.ReactNode;
  /** The finding. Absent on a failure path, where the screen's own name is all there is. */
  title?: string;
}) {
  return (
    <div className="stack">
      <PageHeader
        title={title ?? t(locale, "fleet.title")}
        {...(figures ? { figures } : {})}
      />
      {children}
      {/* The lead moved to the foot. It is a disclosure rather than a description --
          reachability is derived at read time and nothing polls -- so it answers a question
          here instead of delaying the board. See `PageHeader`. */}
      <p className="ds-screen-note">{t(locale, "fleet.lead")}</p>
    </div>
  );
}



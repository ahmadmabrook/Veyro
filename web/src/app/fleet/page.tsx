import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { DataGrid } from "@/components/ds/data-grid";
import { formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate } from "@/lib/api";
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
          {may.reachable ? text("gate.denied") : text("gate.unreachable")}
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
          {error instanceof ApiError && error.reason === "unreachable"
            ? text("error.network")
            : text("error.unexpected")}
        </Banner>
      </Shell>
    );
  }

  const attention = new Set(fleet.needs_attention);

  return (
    <Shell locale={locale}>
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

      <section className="page-section">
        <h2 id="fleet-heading" style={{ margin: 0 }}>
          {text("fleet.title")}
        </h2>
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
    </Shell>
  );
}

function Shell({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  return (
    <div className="stack">
      <h1 style={{ margin: 0 }}>{t(locale, "fleet.title")}</h1>
      <p className="muted" style={{ margin: 0 }}>
        {t(locale, "fleet.lead")}
      </p>
      {children}
    </div>
  );
}



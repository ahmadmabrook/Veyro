import Link from "next/link";
import { redirect } from "next/navigation";

import { Alert } from "@/components/controls";
import { formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate } from "@/lib/api";
import { readFleet, type FleetDevice, type FleetView } from "@/lib/fleet";
import { presentation } from "@/lib/preferences";

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
        <Alert tone="info">
          {may.reachable ? text("gate.denied") : text("gate.unreachable")}
        </Alert>
      </Shell>
    );
  }

  let fleet: FleetView;
  try {
    fleet = await readFleet();
  } catch (error) {
    return (
      <Shell locale={locale}>
        <Alert tone="error">
          {error instanceof ApiError && error.reason === "unreachable"
            ? text("error.network")
            : text("error.unexpected")}
        </Alert>
      </Shell>
    );
  }

  const attention = new Set(fleet.needs_attention);

  return (
    <Shell locale={locale}>
      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("fleet.attention")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("fleet.attentionDetail")}
        </p>
        {attention.size === 0 ? (
          <Alert tone="info">{text("fleet.allWell")}</Alert>
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

      <section className="panel stack">
        <h2 id="fleet-heading" style={{ margin: 0 }}>
          {text("fleet.title")}
        </h2>
        {fleet.devices.length === 0 ? (
          <Alert tone="info">{text("fleet.empty")}</Alert>
        ) : (
          <table
            aria-labelledby="fleet-heading"
            style={{ width: "100%", borderCollapse: "collapse" }}
          >
            <thead>
              <tr>
                <th scope="col" style={headCell}>{text("fleet.device")}</th>
                <th scope="col" style={headCell}>{text("fleet.kind")}</th>
                <th scope="col" style={headCell}>{text("fleet.state")}</th>
                <th scope="col" style={headCell}>{text("fleet.reachability")}</th>
                <th scope="col" style={headCell}>{text("fleet.lastSeen")}</th>
              </tr>
            </thead>
            <tbody>
              {fleet.devices.map((device) => (
                <Row key={device.device_id} device={device} locale={locale} />
              ))}
            </tbody>
          </table>
        )}
        <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
          {text("fleet.asOf")}{" "}
          <span className="data" dir="ltr">
            {fleet.as_of.slice(0, 16).replace("T", " ")}
          </span>
          {" · "}
          <span className="data">{formatInteger(fleet.count, "latn")}</span>
        </p>
      </section>
    </Shell>
  );
}

function Row({ device, locale }: { device: FleetDevice; locale: Locale }) {
  const text = (key: MessageKey) => t(locale, key);
  return (
    <tr>
      <td style={cell}>
        <Link href={`/fleet/${device.device_id}`}>{device.display_name}</Link>
        <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
          {/* A serial number is an identifier: ASCII, never translated, and reordered by the
              bidi algorithm inside an Arabic page without `dir`. */}
          <span className="data" dir="ltr">
            {device.serial_number}
          </span>
        </div>
      </td>
      <td style={cell}>{device.kind}</td>
      <td style={cell}>{device.state}</td>
      <td style={cell}>
        {text(`fleet.reach.${device.reachability}` as MessageKey)}
        {device.blocks_operation ? (
          <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
            {text("fleet.attention")}
          </div>
        ) : null}
      </td>
      <td style={cell}>
        {device.last_seen_at === null ? (
          <span className="muted">{text("fleet.never")}</span>
        ) : (
          <span className="data" dir="ltr">
            {device.last_seen_at.slice(0, 16).replace("T", " ")}
          </span>
        )}
      </td>
    </tr>
  );
}

function Shell({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  return (
    <div className="stack" style={{ padding: "var(--space-6)", maxWidth: "960px" }}>
      <h1 style={{ margin: 0 }}>{t(locale, "fleet.title")}</h1>
      <p className="muted" style={{ margin: 0 }}>
        {t(locale, "fleet.lead")}
      </p>
      {children}
    </div>
  );
}

const headCell: React.CSSProperties = {
  textAlign: "start",
  padding: "var(--space-2) var(--space-3)",
  borderBottom: "1px solid var(--color-border-default)",
  background: "var(--color-surface-sunken)",
  fontSize: "var(--type-label-size)",
  fontWeight: "var(--type-label-weight)",
};

const cell: React.CSSProperties = {
  textAlign: "start",
  verticalAlign: "top",
  padding: "var(--space-2) var(--space-3)",
  borderBottom: "1px solid var(--color-border-subtle)",
};

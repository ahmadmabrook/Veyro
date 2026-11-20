import Link from "next/link";
import { redirect } from "next/navigation";

import { Alert } from "@/components/controls";
import { formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate } from "@/lib/api";
import { listZones, type ZoneSummary } from "@/lib/access";
import { presentation } from "@/lib/preferences";

/**
 * The door board: every access zone, what it can see, and whether it decides anything.
 *
 * **The gate is asked before the data is fetched, and a refusal renders as a refusal** rather
 * than as an empty board. A page that caught the 403 and showed "no zones" would tell an
 * operator their building has no doors, which is a worse answer than "you may not see this".
 *
 * **A zone with no live policy is rendered in words, not as a blank.** `live_policy_version`
 * is null for a zone nobody has published terms for, and such a zone decides nothing -- it is
 * not a zone with permissive defaults. A board that left the cell empty would read as "no
 * restrictions", which is the opposite of what is true.
 */
export default async function DoorBoardPage() {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  const may = await gate("access.zone.read");
  if (!may.allowed) {
    return (
      <Shell locale={locale}>
        <Alert tone="info">
          {may.reachable
            ? text("gate.denied")
            : text("gate.unreachable")}
        </Alert>
      </Shell>
    );
  }

  let zones: ZoneSummary[];
  try {
    zones = (await listZones()).zones;
  } catch (error) {
    // The network and the server are different failures and the reader can act on only one
    // of them, so they are different messages.
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

  return (
    <Shell locale={locale}>
      {zones.length === 0 ? (
        <Alert tone="info">{text("access.empty")}</Alert>
      ) : (
        <table
          tabIndex={0}
          aria-labelledby="doors-heading"
          style={{ width: "100%", borderCollapse: "collapse" }}
        >
          <thead>
            <tr>
              <th scope="col" style={headCell}>
                {text("access.zone")}
              </th>
              <th scope="col" style={headCell}>
                {text("access.risk")}
              </th>
              <th scope="col" style={headCell}>
                {text("access.readers")}
              </th>
              <th scope="col" style={headCell}>
                {text("access.policy")}
              </th>
            </tr>
          </thead>
          <tbody>
            {zones.map((zone) => (
              <tr key={zone.zone_id}>
                <td style={cell}>
                  <Link href={`/access/${zone.zone_id}`}>{zone.display_name}</Link>
                  <div className="muted data" dir="ltr" style={{ fontSize: "var(--type-caption-size)" }}>
                    {zone.zone_key}
                  </div>
                </td>
                <td style={cell}>
                  {text(`access.risk.${zone.risk_class}` as MessageKey)}
                  <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
                    {text("access.offlineCeiling")}{" "}
                    <span className="data">
                      {formatInteger(Math.round(zone.snapshot_ceiling_seconds / 3600), "latn")}
                    </span>{" "}
                    {text("access.hours")}
                  </div>
                </td>
                <td style={cell}>
                  {/* Entry and exit counted separately, because they are different
                      guarantees: a zone with no exit reader cannot measure occupancy, and
                      one with no entry reader decides nothing at all. */}
                  <span className="data">{formatInteger(zone.entry_points, "latn")}</span>{" "}
                  {text("access.direction.entry")} ·{" "}
                  <span className="data">{formatInteger(zone.exit_points, "latn")}</span>{" "}
                  {text("access.direction.exit")}
                </td>
                <td style={cell}>
                  {zone.live_policy_version === null ? (
                    <span style={{ color: "var(--color-text-critical)" }}>
                      {text("access.noPolicy")}
                    </span>
                  ) : (
                    <>
                      {text("access.policyVersion")}{" "}
                      <span className="data">
                        {formatInteger(zone.live_policy_version, "latn")}
                      </span>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Shell>
  );
}

function Shell({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  return (
    <div className="stack" style={{ padding: "var(--space-6)", maxWidth: "960px" }}>
      <nav aria-label={t(locale, "nav.back")}>
        <Link href="/">{t(locale, "home.title")}</Link>
      </nav>
      <h1 id="doors-heading" style={{ margin: 0 }}>
        {t(locale, "access.title")}
      </h1>
      <section className="panel stack">{children}</section>
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

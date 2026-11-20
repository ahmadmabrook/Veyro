import Link from "next/link";
import { redirect } from "next/navigation";

import { Alert } from "@/components/controls";
import { formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate } from "@/lib/api";
import {
  commissioning,
  readCommandQueue,
  readDevice,
  type CommandQueue,
  type DeviceDetail,
} from "@/lib/fleet";
import { presentation } from "@/lib/preferences";

/**
 * One device: what it may do, whether it may be put into service, and what it last said.
 *
 * **The commissioning block is the one that matters and it is a block rather than a warning.**
 * Paragraph 4175: a door with a missing or failing commissioning test cannot be activated, and
 * MOD-021 refuses again at the row when an unlock is queued. So the page lists all seven tests
 * with which have a passing record -- a list of only the missing ones cannot be told from a
 * list of everything when nothing is missing, and the question being answered is "what is left
 * before this door can open", which needs the denominator.
 *
 * **The credential block says what the credential is not.** A certificate here is a fingerprint
 * and a reference to a secret this build cannot read; no signature is verified anywhere,
 * because there is no key vault. The device's identity is what somebody recorded, and MOD-022
 * opens doors on it -- which is why the disclosure is on the page rather than in a design note.
 */
export default async function DevicePage({
  params,
}: {
  params: Promise<{ deviceId: string }>;
}) {
  const { deviceId } = await params;
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

  let device: DeviceDetail;
  let queue: CommandQueue;
  try {
    [device, queue] = await Promise.all([readDevice(deviceId), readCommandQueue(deviceId)]);
  } catch (error) {
    // A malformed id and an unknown one are the same fact to somebody reading a page: they
    // followed a bad link. Rendering 422 as an unexpected error says the product is broken.
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) {
      return (
        <Shell locale={locale}>
          <Alert tone="info">{text("device.notFound")}</Alert>
        </Shell>
      );
    }
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

  const yesNo = (value: boolean) => text(value ? "device.yes" : "device.no");

  return (
    <Shell locale={locale} name={device.display_name}>
      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("device.capabilities")}</h2>
        <p style={{ margin: 0 }}>
          <span className="data" dir="ltr">
            {device.capabilities.join(", ")}
          </span>
        </p>
        <p className="muted" style={{ margin: 0 }}>
          {device.is_access_point ? text("device.isAccessPoint") : text("device.notAccessPoint")}
        </p>
        <dl className="facts">
          <dt className="muted">{text("fleet.state")}</dt>
          <dd style={{ margin: 0 }}>{device.state}</dd>
          <dt className="muted">{text("fleet.reachability")}</dt>
          <dd style={{ margin: 0 }}>
            {text(`fleet.reach.${device.reachability}` as MessageKey)}
          </dd>
          <dt className="muted">{text("fleet.device")}</dt>
          <dd style={{ margin: 0 }}>
            <span className="data" dir="ltr">
              {device.serial_number}
            </span>
          </dd>
        </dl>
      </section>

      {device.is_access_point ? (
        <section className="panel stack">
          <h2 style={{ margin: 0 }}>{text("device.safety")}</h2>
          {device.safety === null ? (
            <Alert tone="error">{text("device.noSafety")}</Alert>
          ) : (
            <dl className="facts">
              <dt className="muted">{text("device.profile")}</dt>
              <dd style={{ margin: 0 }}>
                <span className="data" dir="ltr">
                  {device.safety.profile}
                </span>
              </dd>
              <dt className="muted">{text("device.onEgress")}</dt>
              <dd style={{ margin: 0 }}>{yesNo(device.safety.on_egress_path)}</dd>
              <dt className="muted">{text("device.fireRelease")}</dt>
              <dd style={{ margin: 0 }}>
                {yesNo(device.safety.fire_release_is_independent)}
              </dd>
              <dt className="muted">{text("device.emergencyInput")}</dt>
              <dd style={{ margin: 0 }}>{yesNo(device.safety.local_emergency_input)}</dd>
            </dl>
          )}

          <h3 style={{ margin: 0 }}>{text("device.commissioning")}</h3>
          <p className="muted" style={{ margin: 0 }}>
            {text("device.commissioningLead")}
          </p>
          <dl className="facts">
            {commissioning(device.outstanding_tests).map(({ test, done }) => (
              <div key={test} style={{ display: "contents" }}>
                <dt className="muted">
                  <span className="data" dir="ltr">
                    {test}
                  </span>
                </dt>
                <dd style={{ margin: 0 }}>
                  {done ? (
                    text("device.testDone")
                  ) : (
                    /* Marked with a border rather than a colour alone: WCAG 1.4.1, and the
                       same marker the withheld fields use, because both mean "not here". */
                    <span className="withheld">{text("device.testOutstanding")}</span>
                  )}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("device.certificates")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("device.certificatesLead")}
        </p>
        {device.certificates.length === 0 ? (
          <Alert tone="info">{text("device.noCertificates")}</Alert>
        ) : (
          <ul style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
            {device.certificates.map((certificate) => (
              <li key={certificate.fingerprint}>
                <span className="data" dir="ltr">
                  {certificate.fingerprint.slice(0, 16)}…
                </span>
                {" · "}
                {certificate.state}
                {" · "}
                {certificate.usable ? text("device.usable") : text("device.unusable")}
                {certificate.due_for_rotation ? ` · ${text("device.dueForRotation")}` : null}
                {" · "}
                {text("device.expires")}{" "}
                <span className="data" dir="ltr">
                  {certificate.not_after.slice(0, 10)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("device.health")}</h2>
        {device.health === null ? (
          <Alert tone="info">{text("device.noHealth")}</Alert>
        ) : (
          <dl className="facts">
            <dt className="muted">{text("device.latency")}</dt>
            <dd style={{ margin: 0 }}>
              <span className="data">
                {formatInteger(device.health.latency_ms, "latn")}
              </span>{" "}
              ms
            </dd>
            <dt className="muted">{text("device.errors")}</dt>
            <dd style={{ margin: 0 }}>
              <span className="data">
                {formatInteger(device.health.error_count, "latn")}
              </span>
            </dd>
            <dt className="muted">{text("device.agent")}</dt>
            <dd style={{ margin: 0 }}>
              <span className="data" dir="ltr">
                {device.health.agent_version}
              </span>
            </dd>
          </dl>
        )}

        <h3 style={{ margin: 0 }}>{text("device.snapshot")}</h3>
        {device.snapshot === null ? (
          <p className="muted" style={{ margin: 0 }}>
            {text("device.noSnapshot")}
          </p>
        ) : (
          <p style={{ margin: 0 }}>
            {device.snapshot.behind_revocation
              ? text("device.snapshotBehind")
              : device.snapshot.stale
                ? text("device.snapshotStale")
                : `${text("device.snapshotLive")} ${device.snapshot.expires_at.slice(11, 16)} UTC`}
          </p>
        )}
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("device.commands")}</h2>
        {queue.commands.length === 0 ? (
          <Alert tone="info">{text("device.noCommands")}</Alert>
        ) : (
          <ul style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
            {queue.commands.map((command) => (
              <li key={command.command_id}>
                <span className="data" dir="ltr">
                  {command.action}
                </span>
                {" · "}
                {command.state}
                {command.expired ? ` · ${text("device.expired")}` : null}
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
  name,
  children,
}: {
  locale: Locale;
  name?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="stack" style={{ padding: "var(--space-6)", maxWidth: "960px" }}>
      <nav aria-label={t(locale, "fleet.title")}>
        <Link href="/fleet">{t(locale, "fleet.title")}</Link>
      </nav>
      <h1 style={{ margin: 0 }}>{name ?? t(locale, "device.title")}</h1>
      {children}
    </div>
  );
}


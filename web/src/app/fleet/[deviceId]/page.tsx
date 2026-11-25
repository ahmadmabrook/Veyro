import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { PageHeader } from "@/components/ds/page-header";
import { RecordHeader } from "@/components/ds/record-header";
import { formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate, failureMessage, gateMessage } from "@/lib/api";
import {
  commissioning,
  readCommandQueue,
  readDevice,
  type CommandQueue,
  type DeviceDetail,
} from "@/lib/fleet";
import { numerals } from "@/lib/display";
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
  // **The tenant's numerals** -- ADR-0015. Every quantity on this page follows
  // `localization.numerals`; an identifier does not, and neither does money. One read for the
  // whole render: `conventions()` is React's per-request memo and the layout starts it.
  const numbering = await numerals();
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
          <Banner severity="info">{text("device.notFound")}</Banner>
        </Shell>
      );
    }
    return (
      <Shell locale={locale}>
        <Banner severity="critical">
          {text(failureMessage(error))}
        </Banner>
      </Shell>
    );
  }

  const yesNo = (value: boolean) => text(value ? "device.yes" : "device.no");

  return (
    <Shell locale={locale} device={device}>
      <section className="ds-panel">
        <div className="ds-panel-head">
          <h2 className="ds-panel-title">{text("device.capabilities")}</h2>
        </div>
        <div className="ds-panel-body">
        <p style={{ margin: 0 }}>
          <span className="data" dir="ltr">
            {device.capabilities.join(", ")}
          </span>
        </p>
        {/* The state, the reachability and the serial are the header's sub-line now, where
            a reader meets them before anything else. Repeating them here was the first
            panel saying what the line above it had just said. */}
        </div>
      </section>

      {device.is_access_point ? (
        <section className="ds-panel">
          <div className="ds-panel-head">
            <h2 className="ds-panel-title">{text("device.safety")}</h2>
          </div>
          <div className="ds-panel-body">
          {device.safety === null ? (
            <Banner severity="critical">{text("device.noSafety")}</Banner>
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
          </div>
      </section>
      ) : null}

      <section className="ds-panel">
        <div className="ds-panel-head">
          <h2 className="ds-panel-title">{text("device.certificates")}</h2>
        </div>
        <div className="ds-panel-body">
        <p className="muted" style={{ margin: 0 }}>
          {text("device.certificatesLead")}
        </p>
        {device.certificates.length === 0 ? (
          <Banner severity="info">{text("device.noCertificates")}</Banner>
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
        </div>
      </section>

      <section className="ds-panel">
        <div className="ds-panel-head">
          <h2 className="ds-panel-title">{text("device.health")}</h2>
        </div>
        <div className="ds-panel-body">
        {device.health === null ? (
          <Banner severity="info">{text("device.noHealth")}</Banner>
        ) : (
          <dl className="facts">
            <dt className="muted">{text("device.latency")}</dt>
            <dd style={{ margin: 0 }}>
              <span className="data">
                {formatInteger(device.health.latency_ms, numbering)}
              </span>{" "}
              ms
            </dd>
            <dt className="muted">{text("device.errors")}</dt>
            <dd style={{ margin: 0 }}>
              <span className="data">
                {formatInteger(device.health.error_count, numbering)}
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
        </div>
      </section>

      <section className="ds-panel">
        <div className="ds-panel-head">
          <h2 className="ds-panel-title">{text("device.commands")}</h2>
        </div>
        <div className="ds-panel-body">
        {queue.commands.length === 0 ? (
          <Banner severity="info">{text("device.noCommands")}</Banner>
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
        </div>
      </section>
    </Shell>
  );
}

/**
 * The record shell.
 *
 * **No breadcrumb**: `Devices` is on the rail, and a link above the title repeating a rail
 * entry is the chrome saying the same thing twice. **And the header carries a band**, which
 * is what the other three record pages in this app now do: a device that is in service and
 * unreachable is the one fact somebody opening this page needs before any other.
 */
function Shell({
  locale,
  device,
  children,
}: {
  locale: Locale;
  device?: DeviceDetail;
  children: React.ReactNode;
}) {
  const text = (key: MessageKey) => t(locale, key);
  if (device === undefined) {
    return (
      <div className="ds-inspector-pane">
        <PageHeader title={text("device.title")} />
        <div className="ds-record-body">{children}</div>
      </div>
    );
  }
  return (
    <div className="ds-inspector-pane">
      <RecordHeader
        name={device.display_name}
        {...(device.blocks_operation
          ? { band: { text: text("fleet.attention"), tone: "critical" as const } }
          : {})}
        subline={
          <>
            {text(`fleet.reach.${device.reachability}` as MessageKey)}
            {" · "}
            {device.state}
            {" · "}
            <span className="data" dir="ltr">{device.serial_number}</span>
            {" · "}
            {device.is_access_point
              ? text("device.isAccessPoint")
              : text("device.notAccessPoint")}
          </>
        }
      />
      <div className="ds-record-body">{children}</div>
    </div>
  );
}


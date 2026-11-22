import { Banner } from "@/components/ds/banner";
import { fill, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, gate, gateMessage } from "@/lib/api";
import {
  allWell, fallbackFor, isDegraded, needsAttention, stripOrder, stripState,
} from "@/lib/device-strip";
import { readFleet, type FleetDevice, type FleetView } from "@/lib/fleet";
import { utcStamp } from "@/lib/time";

/**
 * FD-08 · DEVICE STRIP · ALWAYS VISIBLE.
 *
 * > "The card reader is down and the strip says **what to do instead**, not just that it
 * > failed. Every degraded state on this strip names its fallback. A strip rather than a
 * > screen — it sits above both Front Desk and POS at all times. Hardware failing silently is
 * > how a receptionist ends up apologising for something they could not see."
 *
 * **A component in the desk's layout, not a page**, which is what "always visible" means:
 * every `/desk` route renders it above its own content, so the one surface this build has
 * carries it the way the canvas says. There is no POS here, which is the other half of the
 * sentence and a gap rather than a decision.
 *
 * **It asks its own gate.** `devices.device.read` is not what a front desk needs to check
 * somebody in, so a receptionist may hold the roster and not the hardware -- and a strip that
 * rendered nothing in that case would be hardware failing silently with the silence built in.
 * It says it was refused.
 *
 * **It reads the fleet, which it can do without a location.** MOD-021's board is tenant-wide
 * and so is this; narrowing it to the desk's own club would need a location the surface does
 * not have, and showing a sister club's dead reader is noise rather than a lie. Named rather
 * than filtered.
 */
export async function DeviceStrip({ locale }: { locale: Locale }) {
  const text = (key: MessageKey) => t(locale, key);
  const may = await gate("devices.device.read");
  if (!may.allowed) {
    return (
      <aside className="ds-strip" aria-labelledby="strip-heading">
        <h2 id="strip-heading" className="ds-strip-title">{text("strip.title")}</h2>
        <p className="muted ds-strip-note">
          {text(gateMessage(may))} {text("strip.notPermitted")}
        </p>
      </aside>
    );
  }

  let fleet: FleetView | null = null;
  try {
    fleet = await readFleet();
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
  }
  if (fleet === null) {
    return (
      <aside className="ds-strip" aria-labelledby="strip-heading">
        <h2 id="strip-heading" className="ds-strip-title">{text("strip.title")}</h2>
        {/* **Said, not swallowed.** A strip that renders four green rows when it could not
            ask is the exact failure the canvas names -- hardware failing silently -- with
            the silence coming from this component rather than from the hardware. */}
        <Banner severity="attention">{text("strip.unread")}</Banner>
      </aside>
    );
  }

  const devices = stripOrder(fleet.devices);
  return (
    <aside
      className="ds-strip" aria-labelledby="strip-heading"
      // **Live only when something is wrong.** A strip of four working rows is chrome and a
      // screen reader should not hear it on every navigation; a dead reader is the reason
      // the component exists.
      aria-live={needsAttention(devices) ? "polite" : undefined}
      data-attention={needsAttention(devices) ? "yes" : undefined}
    >
      <h2 id="strip-heading" className="ds-strip-title">{text("strip.title")}</h2>
      {devices.length === 0 ? (
        <p className="muted ds-strip-note">{text("strip.nothingHere")}</p>
      ) : (
        <ul className="ds-strip-rows">
          {devices.map((device) => (
            <Row key={device.device_id} locale={locale} device={device} />
          ))}
        </ul>
      )}
      <p className="muted ds-strip-note">
        {allWell(devices) ? <>{text("strip.allWell")}{" "}</> : null}
        {fill(locale, "strip.asOf", { when: utcStamp(fleet.as_of) })}
        {" · "}
        {text("strip.whyNoPrinter")}
      </p>
    </aside>
  );
}

function Row({ locale, device }: { locale: Locale; device: FleetDevice }) {
  const state = stripState(device);
  const fallback = fallbackFor(device);
  return (
    <li className="ds-strip-row" data-state={state}>
      {/* The dot is decorative: the state is a word beside it, because a colour alone is
          not a state a colour-blind reader can read. */}
      <span className="ds-strip-dot" aria-hidden="true" />
      <span className="ds-strip-name">
        {device.display_name}
        <span className="muted ds-strip-meta">
          {device.location_name}
          {" · "}
          {device.last_seen_at === null
            ? t(locale, "strip.neverSeen")
            : fill(locale, "strip.lastSeen", { when: utcStamp(device.last_seen_at) })}
        </span>
      </span>
      <span className="ds-strip-state">
        {t(locale, `strip.state.${state}` as MessageKey)}
      </span>
      {/* **The requirement**: "every degraded state on this strip names its fallback", and
          where there is no honest one the strip says that instead of inventing advice a
          receptionist would follow into a second dead end. */}
      {isDegraded(device) ? (
        <span className="ds-strip-fallback">
          {fallback === null ? t(locale, "strip.noFallback") : t(locale, fallback)}
        </span>
      ) : null}
    </li>
  );
}

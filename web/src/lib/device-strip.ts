import type { FleetDevice } from "@/lib/fleet";
import type { MessageKey } from "@/i18n/locale";

/**
 * FD-08 · DEVICE STRIP · ALWAYS VISIBLE.
 *
 * > "The card reader is down and the strip says **what to do instead**, not just that it
 * > failed. Every degraded state on this strip names its fallback. A strip rather than a
 * > screen — it sits above both Front Desk and POS at all times. Hardware failing silently is
 * > how a receptionist ends up apologising for something they could not see."
 *
 * **Decisions only**, no import reaching `next/headers`: the strip is rendered on every
 * `/desk` page through a layout, and this is the half a component test can hold.
 *
 * **The fallback is the whole requirement, and it is the part a backend cannot answer.**
 * MOD-021 knows a device's kind, its state and whether it has reported recently; it does not
 * know what a receptionist should do instead, and there is no column where a tenant could
 * say. So the fallback is a map from kind to a sentence — and the discipline is that every
 * sentence names something this build can actually do. The canvas's own example, "type the
 * name instead", is **not** one of them: there is no member search in this product, so
 * telling somebody to type a name is advice that fails at the keyboard. What a desk can do
 * when a reader dies is find the member on the class they booked, which FD-06 renders.
 */

/** What the strip says about one device, in one word. */
export type StripState = "working" | "degraded" | "down" | "paused";

/**
 * **`blocks_operation` is the server's own judgement and the strip takes it**, rather than
 * re-deriving `active && offline` here. MOD-021 computes it because "a device in maintenance
 * is not an incident", and a second copy of that rule on a surface is the shape this build
 * keeps finding: two definitions that agree until one of them moves.
 */
/**
 * **A desk asks a different question from a dashboard, and the two answers differ.**
 * MOD-021's `blocks_operation` is `active` *and* `offline` -- what to page somebody about --
 * and it deliberately excludes a device that has *never* reported, because one that never
 * spoke has not gone quiet and nobody can be told when it stopped. For the fleet board that
 * is right. For a receptionist it is not the question: an in-service reader that has never
 * checked in is exactly as unusable as one that died this morning, so this strip calls both
 * of them degraded and names the fallback for each. The board's own test says so beside this
 * one, because a reader who saw the two screens disagree deserves to know it was deliberate.
 */
export function stripState(device: FleetDevice): StripState {
  // **First, and it is a guard rather than a shortcut.** MOD-021 guarantees
  // `blocks_operation` is `active` and `offline` together, so a maintenance device never
  // carries it and the branch below would answer anyway -- which is exactly why a case
  // passing `false` here proves nothing, as the mutation sweep found. It stays because the
  // one input that reaches it is a server disagreeing with itself, and the cost of that
  // would be this strip reporting a fault on a device somebody deliberately unplugged.
  if (device.state === "maintenance") return "paused";
  if (device.blocks_operation) return "down";
  if (device.state !== "active") return "paused";
  return device.reachability === "online" ? "working" : "degraded";
}

/** Whether this row is one a receptionist has to act on. */
export function isDegraded(device: FleetDevice): boolean {
  const state = stripState(device);
  return state === "down" || state === "degraded";
}

/**
 * What to do instead, per kind of device.
 *
 * **Every sentence names a screen this build has.** A fallback that pointed at a capability
 * the product lacks would be worse than none: a receptionist following it stops twice, once
 * at the broken hardware and once at the advice. Where there is no honest answer the kind is
 * absent from this map and the strip says it has no fallback to offer, which is a true
 * sentence and an uncomfortable one.
 */
export const FALLBACK: Partial<Record<string, MessageKey>> = {
  // A reader at a door: the member is still expected on a class, and FD-06 checks them in by
  // hand. **Not "type the name instead"**, which is the canvas's own words and which this
  // product cannot honour -- paragraph 4218's search is ENG-01's and unbuilt.
  scanner: "strip.fallback.scanner",
  // A turnstile that will not open is the gym's oldest manual process, and the design's own
  // handover note writes it: "Sweifieh reader still down -- admit manually and mention it."
  turnstile: "strip.fallback.turnstile",
  door_controller: "strip.fallback.doorController",
  // A biometric terminal is a credential reader with a different sensor.
  biometric_terminal: "strip.fallback.scanner",
};

export function fallbackFor(device: FleetDevice): MessageKey | null {
  return FALLBACK[device.kind] ?? null;
}

/**
 * The strip's rows, worst first.
 *
 * **Order is the whole point of a strip.** It is four rows above a working screen and a
 * receptionist reads the top one; a down reader sorted under three healthy devices is
 * hardware failing silently with extra steps. Within a group the server's order stands.
 */
const RANK: Record<StripState, number> = {
  down: 0, degraded: 1, paused: 2, working: 3,
};

export function stripOrder(devices: FleetDevice[]): FleetDevice[] {
  return [...devices].sort((a, b) => RANK[stripState(a)] - RANK[stripState(b)]);
}

/**
 * Whether the strip has anything worth interrupting for.
 *
 * A strip of green rows is chrome; a strip with a dead reader on it is the reason the
 * component exists. The difference decides whether the whole thing is announced.
 */
export function needsAttention(devices: FleetDevice[]): boolean {
  return devices.some(isDegraded);
}

/**
 * Whether the all-clear sentence is true.
 *
 * **Not the inverse of `needsAttention`**, and the difference was on screen: a device that
 * was registered and never activated is "out of service" rather than an incident -- MOD-021's
 * own judgement, which this strip takes rather than re-deriving -- so two out-of-service
 * readers raised no attention and the strip said "everything this desk needs is responding"
 * directly above both of them. One is a statement about whether to act; the other is a
 * statement about the hardware, and they are not opposites. Found by looking at the page.
 */
export function allWell(devices: FleetDevice[]): boolean {
  return devices.length > 0 && devices.every((d) => stripState(d) === "working");
}

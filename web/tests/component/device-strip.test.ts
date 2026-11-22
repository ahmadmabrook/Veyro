import { describe, expect, it } from "vitest";

import {
  FALLBACK, allWell, fallbackFor, isDegraded, needsAttention, stripOrder, stripState,
} from "@/lib/device-strip";
import { MESSAGE_KEYS } from "@/i18n/locale";
import type { FleetDevice } from "@/lib/fleet";

/**
 * FD-08's decisions: what a row says, what to do instead, and what order a strip is read in.
 *
 * **Decisions rather than rendered branches.** Three of the four states need a device the
 * browser fixture cannot produce on demand -- `offline` means half an hour of silence, and a
 * fixture cannot wait -- so the states are constructed here and the strip's rendering of them
 * is what the browser checks.
 */

const device = (over: Partial<FleetDevice> = {}): FleetDevice => ({
  device_id: "d-1",
  serial_number: "SN-1",
  display_name: "Reception scanner",
  state: "active",
  kind: "scanner",
  location_id: "l-1",
  location_name: "Downtown",
  reachability: "online",
  blocks_operation: false,
  last_seen_at: "2026-11-22T03:00:00Z",
  ...over,
});

describe("what a row says", () => {
  it("is working when it is in service and answering", () => {
    expect(stripState(device())).toBe("working");
  });

  it("is down when the server says it blocks operation", () => {
    // **The server's own judgement, not a second copy of it.** `blocks_operation` is
    // `active` and `offline` together, and MOD-021 computes it because "a device in
    // maintenance is not an incident" -- re-deriving that here is the two-definitions shape
    // this build keeps finding.
    expect(stripState(device({ reachability: "offline", blocks_operation: true })))
      .toBe("down");
  });

  it("is degraded for an in-service device that has never reported", () => {
    // **A desk asks a different question from a dashboard.** `never_seen` is not `offline`,
    // so the fleet board correctly refuses to page anybody about it -- nobody can say when
    // it stopped. A receptionist's question is whether the reader works now, and it does
    // not.
    expect(stripState(device({ reachability: "never_seen", last_seen_at: null })))
      .toBe("degraded");
    expect(stripState(device({ reachability: "late" }))).toBe("degraded");
  });

  it("calls anything not in service out of service rather than broken", () => {
    // Listing a half-installed device as a problem is how an alert channel gets muted.
    for (const state of ["registered", "provisioned", "quarantined", "retired"]) {
      expect(stripState(device({ state })), state).toBe("paused");
    }
    expect(stripState(device({ state: "maintenance" }))).toBe("paused");
  });

  it("calls a device in maintenance paused even if the server calls it blocking", () => {
    // **Maintenance is checked first, and the case has to be the one that makes it matter.**
    // MOD-021 guarantees `blocks_operation` is `active` *and* `offline`, so a maintenance
    // device never carries it -- which means a case passing `false` is answered by the
    // "not active is out of service" branch below and proves nothing about this one. The
    // mutation sweep said so by removing the branch and staying green.
    //
    // So the case is the contract being violated: a server that returned both would have
    // this strip reporting a fault on a device somebody unplugged. The branch exists for
    // the server that is not the current one, which is the same reason a trigger exists for
    // the writer that is not the service.
    expect(stripState(device({
      state: "maintenance", reachability: "offline", blocks_operation: true,
    }))).toBe("paused");
  });
});

describe("what to do instead", () => {
  it("names a fallback for every kind of device that reads a credential", () => {
    for (const kind of ["scanner", "turnstile", "door_controller", "biometric_terminal"]) {
      expect(fallbackFor(device({ kind })), kind).not.toBeNull();
    }
  });

  it("says there is none rather than inventing one", () => {
    // **A fallback that pointed at a capability this product lacks is worse than none**: a
    // receptionist following it stops twice, once at the hardware and once at the advice.
    for (const kind of ["kiosk", "pos", "equipment", "gateway"]) {
      expect(fallbackFor(device({ kind })), kind).toBeNull();
    }
  });

  it("every fallback it does name is a message that exists in both languages", () => {
    // The parity sweep compares the two catalogues against each other and is blind to a
    // string that never became a key, which is how an English sentence shipped onto an
    // Arabic page once already.
    for (const key of Object.values(FALLBACK)) {
      expect(MESSAGE_KEYS, key).toContain(key);
    }
  });
});

describe("what the strip interrupts for", () => {
  it("counts a down or degraded device and not an out-of-service one", () => {
    expect(isDegraded(device())).toBe(false);
    expect(isDegraded(device({ state: "registered" }))).toBe(false);
    expect(isDegraded(device({ reachability: "never_seen" }))).toBe(true);
    expect(isDegraded(device({ reachability: "offline", blocks_operation: true })))
      .toBe(true);
  });

  it("says all is well only when every device is working", () => {
    // **Not the inverse of `needsAttention`, and the difference was on screen.** Two
    // out-of-service readers raise no attention, and the strip said "everything this desk
    // needs is responding" directly above both of them. One statement is about whether to
    // act and the other is about the hardware.
    const out = device({ device_id: "d-2", state: "registered" });
    expect(needsAttention([device(), out])).toBe(false);
    expect(allWell([device(), out])).toBe(false);
    expect(allWell([device()])).toBe(true);
  });

  it("says nothing either way about an empty fleet", () => {
    // A tenant with no devices is not a tenant whose hardware is fine.
    expect(allWell([])).toBe(false);
    expect(needsAttention([])).toBe(false);
  });
});

describe("the order a strip is read in", () => {
  it("puts what is broken above what is fine", () => {
    // Four rows above a working screen, and a receptionist reads the top one: a dead reader
    // sorted under three healthy devices is hardware failing silently with extra steps.
    const rows = stripOrder([
      device({ device_id: "ok" }),
      device({ device_id: "paused", state: "registered" }),
      device({ device_id: "down", reachability: "offline", blocks_operation: true }),
      device({ device_id: "degraded", reachability: "never_seen" }),
    ]);
    expect(rows.map((d) => d.device_id))
      .toEqual(["down", "degraded", "paused", "ok"]);
  });

  it("does not reorder the caller's array", () => {
    const given = [device({ device_id: "ok" }),
                   device({ device_id: "down", blocks_operation: true })];
    stripOrder(given);
    expect(given.map((d) => d.device_id)).toEqual(["ok", "down"]);
  });
});

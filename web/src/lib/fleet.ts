import { api } from "@/lib/api";

/**
 * MOD-021's reads, typed.
 *
 * **Two of these fields are derived at read time and neither is stored**, which is the thing a
 * surface has to be careful with. `reachability` is computed from the last health report, so a
 * device that stopped reporting looks exactly like one that never did until the silence passes
 * a threshold -- and **nothing records it**, so the board only knows what it worked out when
 * it loaded. The worker's offline sweep does run on a schedule now, and it changes nothing
 * here: it publishes `device.offline` for a device in service that has gone quiet, and it
 * neither polls the device nor writes a reachability anybody can read back.
 * `blocks_operation` is `active` and `offline` together: a device deliberately in maintenance
 * is not an incident, and one nobody has finished installing is not either.
 */

export type Reachability = "never_seen" | "online" | "late" | "offline";

export type FleetDevice = {
  device_id: string;
  serial_number: string;
  display_name: string;
  state: string;
  kind: string;
  location_id: string;
  reachability: Reachability;
  /** Derived: `active` and `offline`. What to page on, rather than what is merely unusual. */
  blocks_operation: boolean;
  last_seen_at: string | null;
};

export type FleetView = {
  devices: FleetDevice[];
  count: number;
  needs_attention: string[];
  as_of: string;
};

export type SafetyProfile = {
  profile: string;
  on_egress_path: boolean;
  fire_release_is_independent: boolean;
  local_emergency_input: boolean;
};

export type Certificate = {
  fingerprint: string;
  state: string;
  usable: boolean;
  due_for_rotation: boolean;
  not_after: string;
};

export type DeviceHealth = {
  latency_ms: number;
  error_count: number;
  storage_free_bytes: number;
  agent_version: string;
  reported_at: string;
};

export type PolicySnapshot = {
  snapshot_id: string;
  revocation_epoch: number;
  issued_at: string;
  expires_at: string;
  stale: boolean;
  /** The device has revoked past this snapshot's epoch, so it must not be honoured. */
  behind_revocation: boolean;
};

export type DeviceDetail = {
  device_id: string;
  serial_number: string;
  display_name: string;
  state: string;
  kind: string;
  location_id: string;
  type_id: string;
  version: number;
  capabilities: string[];
  reachability: Reachability;
  blocks_operation: boolean;
  last_seen_at: string | null;
  revocation_epoch: number;
  /** It declares `access.actuate`, so it can move a barrier and the fire code applies. */
  is_access_point: boolean;
  safety: SafetyProfile | null;
  /**
   * Which of paragraph 4175's seven commissioning tests have no passing record.
   *
   * **Not a warning: a block.** MOD-021 refuses to activate a door with one outstanding and
   * the unlock trigger refuses again at the row, so an operator reading this list is reading
   * the reason the door cannot go into service -- which is why the surface names each test
   * rather than printing a count.
   */
  outstanding_tests: string[];
  certificates: Certificate[];
  health: DeviceHealth | null;
  snapshot: PolicySnapshot | null;
};

export type QueuedCommand = {
  command_id: string;
  action: string;
  state: string;
  issued_at: string;
  expires_at: string;
  payload_digest: string;
  expired: boolean;
};

export type CommandQueue = {
  device_id: string;
  commands: QueuedCommand[];
  count: number;
};

export function readFleet(): Promise<FleetView> {
  return api<FleetView>("/fleet");
}

export function readDevice(deviceId: string): Promise<DeviceDetail> {
  return api<DeviceDetail>(`/fleet/${encodeURIComponent(deviceId)}`);
}

export function readCommandQueue(deviceId: string): Promise<CommandQueue> {
  return api<CommandQueue>(`/fleet/${encodeURIComponent(deviceId)}/commands`);
}

/** Paragraph 4175's list, in the order MOD-021 declares it, so a reader sees a stable order. */
export const COMMISSIONING_TESTS: readonly string[] = [
  "power_loss",
  "edge_agent_crash",
  "controller_disconnect",
  "fire_alarm_input",
  "emergency_unlock",
  "recovery",
  "manual_override",
] as const;

/**
 * Each required test with whether it still has no passing record.
 *
 * **Both halves are rendered, which is the point.** A list of only what is missing cannot be
 * told from a list of everything when nothing is missing, and the question an operator is
 * answering is "what is left before this door can open" -- which needs the denominator.
 */
export function commissioning(outstanding: string[]): { test: string; done: boolean }[] {
  const missing = new Set(outstanding);
  return COMMISSIONING_TESTS.map((test) => ({ test, done: !missing.has(test) }));
}

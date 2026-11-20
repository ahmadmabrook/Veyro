import { api } from "@/lib/api";

/**
 * MOD-022's reads, typed.
 *
 * **Nothing here decides anything and nothing here is a write.** The surfaces this module
 * needs are a door board and a decision log: an operator looking at what the doors are doing.
 * The one action a front desk takes -- admitting somebody against the policy -- is a
 * stepped-up financial permission and goes through its own form, because an override is a
 * decision in its own right rather than a retry of a refusal.
 */

export type RiskClass = "standard" | "high_risk";
export type PointDirection = "entry" | "exit" | "both";

export type ZoneSummary = {
  zone_id: string;
  location_id: string;
  zone_key: string;
  display_name: string;
  risk_class: RiskClass;
  status: string;
  live_points: number;
  entry_points: number;
  exit_points: number;
  /** **`null` means no policy is live**, which is a zone that decides nothing. */
  live_policy_version: number | null;
  snapshot_ceiling_seconds: number;
};

export type ZonePolicy = {
  policy_id: string;
  version: number;
  opens_minute: number | null;
  closes_minute: number | null;
  requires_entitlement: boolean;
  max_balance_minor: number | null;
  min_age_years: number | null;
  anti_passback_seconds: number;
  capacity: number | null;
};

export type AccessPoint = {
  point_id: string;
  device_id: string;
  direction: PointDirection;
  display_name: string;
  status: string;
  decides_entry: boolean;
};

export type ZoneDetail = {
  zone_id: string;
  location_id: string;
  zone_key: string;
  display_name: string;
  risk_class: RiskClass;
  status: string;
  snapshot_ceiling_seconds: number;
  policy: ZonePolicy | null;
  points: AccessPoint[];
  access_gaps: string[];
};

export type Occupancy = {
  zone_id: string;
  inside: number;
  confidence: "measured" | "advisory";
  has_entry_reader: boolean;
  has_exit_reader: boolean;
  risk_class: RiskClass;
  /** Paragraph 4180's disclaimer. Rendered on every read, never summarised away. */
  detail: string;
};

export type AccessDecision = {
  bucket?: DecisionBucket;
  decision_id: string;
  point_id: string;
  zone_id: string;
  credential_id: string | null;
  person_id: string | null;
  granted: boolean;
  code: string;
  public_reason: string;
  /** **Null unless the caller holds `access.decision.read_reason`.** Never substituted. */
  private_reason: string | null;
  reason_withheld: boolean;
  policy_id: string | null;
  policy_version: number | null;
  device_mode: string;
  passback_scope: string;
  decided_at: string;
};

export type DecisionBucket = "granted" | "policy" | "fault";

export type DecisionPage = {
  /**
   * ADM-ACC-02's two filters, counted by the server.
   *
   * **The classification is MOD-022's, by reason code.** Twenty-seven expired memberships is
   * the product working and four reader failures is a maintenance job, and one count hides
   * the second inside the first -- which is the canvas's own argument for the split. Doing
   * it here would be a second definition of the same number.
   */
  counts?: Record<DecisionBucket, number>;
  decisions: AccessDecision[];
  /** Whether the private halves in this page are real, which the UI must not infer. */
  private_reasons_included: boolean;
};

export function listZones(): Promise<{ zones: ZoneSummary[] }> {
  return api<{ zones: ZoneSummary[] }>("/access/zones");
}

export function readZone(zoneId: string): Promise<ZoneDetail> {
  return api<ZoneDetail>(`/access/zones/${encodeURIComponent(zoneId)}`);
}

export function readOccupancy(zoneId: string): Promise<Occupancy> {
  return api<Occupancy>(`/access/zones/${encodeURIComponent(zoneId)}/occupancy`);
}

export function readDecisions(zoneId: string, limit = 25): Promise<DecisionPage> {
  return api<DecisionPage>(
    `/access/decisions?zone_id=${encodeURIComponent(zoneId)}&limit=${limit}`,
  );
}

/**
 * The reason codes a turnstile may display, and the ones it may not.
 *
 * **Mirrored from `app/access/policy.py`, and the mirror is checked by a test** rather than
 * trusted: a surface that treated a restricted code as public would undo paragraph 1944 in
 * the one place the member is standing in front of other people. The server already replaces
 * a restricted code's public half with the discreet line, so this list does not decide what
 * is shown -- it decides whether the interface marks a row as withheld, and a drift would
 * make that marking wrong rather than make the text leak.
 */
export const RESTRICTED_CODES: readonly string[] = [
  "membership_inactive",
  "no_entitlement",
  "outstanding_balance",
  "age_restricted",
  "safety_hold",
] as const;

/** What the member was shown. The same single line for every restricted code. */
export const DISCREET = "please see the front desk";

export function isRestricted(code: string): boolean {
  return RESTRICTED_CODES.includes(code);
}

/**
 * Today's entries per reader, keyed by the device behind it.
 *
 * ADM-ACC-01's TODAY column, composed onto the fleet board. **It lives in MOD-022 and not in
 * MOD-021's fleet read**: a device knows nothing about doors by design, and `acc_points` is
 * the join MOD-021 deliberately did not make -- so the board asks both modules through both
 * gates, the way the Member 360 composes MOD-014 and MOD-017.
 */
export type EntriesByPoint = {
  date: string;
  points: { point_id: string; device_id: string; entries: number }[];
  /** A device standing at more than one reader is summed. Absent means it is not a door. */
  by_device: Record<string, number>;
  entries: number;
};

export function readEntries(): Promise<EntriesByPoint> {
  return api("/access/entries");
}

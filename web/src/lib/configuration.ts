import { api } from "@/lib/api";

/**
 * MOD-005's reads, typed.
 *
 * **Every answer here carries why it is that answer**, which is the thing a surface has to
 * render rather than flatten. A resolved configuration value says which scope it came from --
 * the tenant's, a brand's or a site's -- so a reader can tell "nobody has set this" from "the
 * site overrides it". A flag evaluation says `kill_switch`, `disabled`, `rule:<id>` or
 * `default`, and those are four different facts with four different next actions: a kill
 * switch outranks every rule and is somebody's deliberate stop, `disabled` is a flag nobody
 * has turned on, a rule is a targeting decision, and `default` means no rule matched.
 *
 * **A flag's variant alone is the number that misleads.** "off" could be a kill switch, a flag
 * that was never enabled, or a rule that deliberately sent this subject to the control arm --
 * and an operator looking at an incident needs to know which. So the reason travels with it
 * everywhere in this module.
 */

export type ConfigDefinition = {
  definition_id: string;
  config_key: string;
  value_type: string;
  default_value: unknown;
  validation: Record<string, unknown>;
  owner_module: string;
  description: string | null;
};

/**
 * `scope_type` is where the winning value was set: `tenant`, `brand`, `location` -- or
 * `default`, which means nobody set it and the definition's own default is what you are
 * reading. **`version` is null in exactly that case**, because there is no published version
 * behind a default, and a surface that rendered it as 0 would be inventing one.
 */
export type ResolvedValue = {
  value: unknown;
  scope_type: string;
  version: number | null;
};

export type FlagDecision = {
  variant: string;
  /** `kill_switch`, `disabled`, `rule:<id>` or `default`. Four facts, not one. */
  reason: string;
  version: number;
};

export function listDefinitions(): Promise<ConfigDefinition[]> {
  return api<ConfigDefinition[]>("/config/definitions");
}

export function readResolved(): Promise<Record<string, ResolvedValue>> {
  return api<Record<string, ResolvedValue>>("/config/resolved");
}

export function evaluateFlags(subjectId: string): Promise<Record<string, FlagDecision>> {
  const query = new URLSearchParams({ subject_id: subjectId });
  return api<Record<string, FlagDecision>>(`/flags?${query.toString()}`);
}

/**
 * Which of the four reasons this is, as a closed set a surface can render.
 *
 * **`rule:<id>` carries the rule id and a surface must not show it as a reason.** A reader does
 * not know what `rule:0f3a…` means, and the number is not the answer to "why is this on" --
 * "a targeting rule matched" is. The id stays available for somebody debugging; the label is
 * what the page says.
 */
export type FlagReason = "kill_switch" | "disabled" | "rule" | "default";

export function flagReason(decision: FlagDecision): FlagReason {
  if (decision.reason === "kill_switch") return "kill_switch";
  if (decision.reason === "disabled") return "disabled";
  if (decision.reason.startsWith("rule:")) return "rule";
  return "default";
}

/**
 * Whether a value is the definition's default rather than anything a tenant set.
 *
 * **A default is not a setting**, and the distinction is what somebody is asking when they ask
 * what this tenant has configured: an unset key reads back as its default with scope `default`,
 * which is indistinguishable from a tenant that deliberately published the same value unless
 * the scope is rendered.
 */
export function isUnset(resolved: ResolvedValue): boolean {
  return resolved.scope_type === "default";
}

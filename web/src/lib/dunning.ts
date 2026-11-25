import { api } from "@/lib/api";

/**
 * ADM-PAY-06's dunning policy: the two figures a tenant sets, and the three it cannot.
 *
 * **Five settings on the canvas and two have readers**, which is the whole shape of this
 * screen. `retry_attempts` is what `collections.recovery_treatment` sorts ADM-PAY-05's
 * workspace by, and `access_grace_days` is the day the journey starts recommending that access
 * be restricted. The hour a retry runs needs a scheduled dunning run MOD-017 lists as undriven;
 * the drafted message held for approval needs a dispatcher MOD-013 does not have; the exception
 * threshold needs collections to write a MOD-026 case, which nothing does. Storing a value
 * nothing acts on is this build's most-repeated finding, and a control for one would be worse
 * than its absence -- a tenant would believe they had configured something.
 *
 * **The floor is not a setting**, and the canvas says so: "The NEVER block is not configurable
 * per-tenant -- it is the floor beneath every dunning policy." It comes down as codes rather
 * than sentences, because this application has two message catalogues and prose on the wire can
 * only be read by one of them.
 */

export type DunningStage = {
  stage: number;
  days_after_due: number;
  notification_key: string;
  access_recommendation: string;
};

export type DunningPolicy = {
  retry_attempts: number;
  access_grace_days: number;
  stages: DunningStage[];
  retry_attempts_band: [number, number];
  access_grace_days_band: [number, number];
  /** The keys this tenant has published. Empty means both figures above are defaults. */
  declared: string[];
  /** That `next_step`'s per-account `grace_days` is a different figure. Always true. */
  account_terms_are_separate: boolean;
  not_settable: { setting: string; waits_on: string }[];
  /** `enforced` is the half that is a property of the build rather than an intention. */
  floor: { rule: string; enforced: boolean }[];
};

export const RETRY_KEY = "dunning.retry_attempts";
export const GRACE_KEY = "dunning.access_grace_days";

export function readDunningPolicy(): Promise<DunningPolicy> {
  return api<DunningPolicy>("/finance/dunning-policy");
}

/**
 * Whether a figure is a decision somebody made or the value the journey falls back to.
 *
 * The same distinction MOD-005's board draws for `scope_type: "default"`: a tenant that has
 * configured nothing resolves to the journey this build already ran, and only one of the two is
 * something to change.
 */
export function isDefaulted(policy: DunningPolicy, key: string): boolean {
  return !policy.declared.includes(key);
}

/** The stage whose own offset the access grace sets, so the form can point at its date. */
export function restrictingStage(policy: DunningPolicy): DunningStage | undefined {
  return policy.stages.find((one) => one.access_recommendation === "restrict");
}

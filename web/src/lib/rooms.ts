import { api } from "@/lib/api";

/**
 * ADM-SCH-06's read. ADR-0018.
 *
 * **Its own module, beside `rota.ts`**, rather than appended to `scheduling.ts`: that file is
 * the schedule board's types and this is a different screen's read, and a module per screen is
 * what `rota.ts` already does. (It also sidesteps a stale dev-server module cache, which is
 * how the split got made -- but the shape is right for the reason above.)
 */
/**
 * ADM-SCH-06's three columns: a resource, how many people it holds, and what is in it.
 *
 * **Three different numbers, and only one of them existed before `0035`.** `quantity` is how
 * many of a thing there are -- twenty bikes are one row with a quantity of twenty -- `capacity`
 * is how many *people* a space holds, and a class's own places are on its policy. A screen
 * that rendered one as another would be the three-way confusion this slice exists to resolve.
 *
 * **A capacity of `null` is unstated and not zero**, which the surface has to say: a room
 * nobody has described does not bind a class, and "holds 0" is a different fact and the one a
 * reader would act on.
 */
export type SchedulingResource = {
  resource_id: string;
  resource_code: string;
  resource_kind: string;
  display_name: string;
  /** How many of the thing there are. For equipment; one for everything else. */
  quantity: number;
  /** How many people this space holds, or `null` where nobody has said. */
  capacity: number | null;
  /** The space this equipment is in, or `null` for anything that is not in one. */
  parent_resource_id: string | null;
  /** The equipment inside this space, summed per kind. Empty for anything that is not one. */
  contains: { resource_kind: string; resource_code: string; quantity: number }[];
  location_id: string | null;
  status: string;
};

export type SchedulingResourceList = {
  count: number;
  resources: SchedulingResource[];
  capacity_is_a_ceiling: string;
  contains_is_what_is_in_the_space: string;
};

/** The kinds that are places: the only ones that hold people or contain equipment. */
export const SPACE_KINDS = ["room", "zone", "court"] as const;

export function isSpace(resource: SchedulingResource): boolean {
  return (SPACE_KINDS as readonly string[]).includes(resource.resource_kind);
}

/**
 * What the canvas's third column says for one space.
 *
 * `{{ r.equip }}` is 96px of mono at 10.5px, so it is short by design: the kinds and their
 * totals rather than a list of codes. **Empty is its own answer** -- a room with nothing
 * recorded in it bounds a per-attendee class at nobody, which is the uncomfortable half of
 * the containment being a relation rather than a label.
 */
export function equipmentLine(resource: SchedulingResource): string[] {
  return resource.contains.map((one) => `${one.quantity} × ${one.resource_code}`);
}

export async function listSchedulingResources(
  params: { location_id?: string } = {},
): Promise<SchedulingResourceList> {
  const query = new URLSearchParams();
  if (params.location_id !== undefined) query.set("location_id", params.location_id);
  query.set("limit", "500");
  return api<SchedulingResourceList>(`/scheduling/resources?${query.toString()}`);
}

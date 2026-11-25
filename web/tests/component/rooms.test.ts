/**
 * ADM-SCH-06's decisions, where they are decided. ADR-0018.
 *
 * **The three numbers are the subject.** `quantity` is how many of a thing there are,
 * `capacity` is how many people a space holds, and a class's places are on its own policy —
 * and a screen that rendered one as another would be the three-way confusion the slice exists
 * to resolve. These assert the two the surface decides: which rows are spaces, and what the
 * third column says for one.
 */
import { describe, expect, it } from "vitest";

import {
  equipmentLine,
  isSpace,
  SPACE_KINDS,
  type SchedulingResource,
} from "@/lib/rooms";

function resource(over: Partial<SchedulingResource> = {}): SchedulingResource {
  return {
    resource_id: "r-1",
    resource_code: "STUDIO-A",
    resource_kind: "room",
    display_name: "Studio A",
    quantity: 1,
    capacity: 30,
    parent_resource_id: null,
    contains: [],
    location_id: "loc-1",
    status: "active",
    ...over,
  };
}

describe("which rows are spaces", () => {
  it("names the three kinds that are places", () => {
    expect([...SPACE_KINDS]).toEqual(["room", "zone", "court"]);
  });

  it("counts a room, a zone and a court as spaces", () => {
    for (const kind of SPACE_KINDS) {
      expect(isSpace(resource({ resource_kind: kind }))).toBe(true);
    }
  });

  it("counts nothing else, because only a place holds people", () => {
    for (const kind of ["staff", "equipment", "service", "composite"]) {
      expect(isSpace(resource({ resource_kind: kind }))).toBe(false);
    }
  });
});

describe("the equipment column", () => {
  it("says the quantity and the code, because a count of rows is not a count of bikes", () => {
    const line = equipmentLine(resource({
      contains: [{ resource_kind: "equipment", resource_code: "BIKES", quantity: 20 }],
    }));
    expect(line).toEqual(["20 × BIKES"]);
  });

  it("lists each kind, which is what the canvas's 96px column holds", () => {
    const line = equipmentLine(resource({
      contains: [
        { resource_kind: "equipment", resource_code: "BIKES", quantity: 20 },
        { resource_kind: "equipment", resource_code: "MATS", quantity: 12 },
      ],
    }));
    expect(line).toEqual(["20 × BIKES", "12 × MATS"]);
  });

  it("is empty for a room with nothing recorded in it, which is its own answer", () => {
    // Uncomfortable and correct: a format taking a bike each, in a room with no bikes in it,
    // holds nobody. Equipment at the club and in no room is in no room -- which is the reason
    // the containment is a relation rather than a label.
    expect(equipmentLine(resource({ contains: [] }))).toEqual([]);
  });

  it("is empty for anything that is not a space", () => {
    expect(equipmentLine(resource({ resource_kind: "staff", contains: [] }))).toEqual([]);
  });
});

describe("a capacity that nobody stated", () => {
  it("is null rather than zero, which the screen has to tell apart", () => {
    // ADR-0018 D1: a room nobody has described does not bind a class, and "holds 0" is a
    // different fact -- the one a reader would act on.
    expect(resource({ capacity: null }).capacity).toBeNull();
    expect(resource({ capacity: 0 }).capacity).toBe(0);
  });
});

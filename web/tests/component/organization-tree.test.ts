import { describe, expect, it } from "vitest";

import { composeTree, type Brand, type LegalEntity, type Location, type Organization } from "@/lib/organization";

/**
 * The hierarchy is composed by id, and a row whose parent is missing is kept.
 *
 * **This is a unit test rather than a browser one because the interesting inputs cannot be
 * provisioned.** An orphan -- a location whose brand is not in the brand list -- is a read
 * that raced a write or an isolation question, and there is no way to ask the API for one. A
 * browser suite can only ever see the well-formed case, so the behaviour that matters most
 * would be asserted by nothing.
 */
const organizations: Organization[] = [
  { organization_id: "org-1", legal_name: "Veyro Sites Ltd", country_code: "JO" },
  { organization_id: "org-2", legal_name: "Veyro Nordics", country_code: "IS" },
];
const brands: Brand[] = [
  { brand_id: "brand-1", organization_id: "org-1", brand_name: "City" },
  { brand_id: "brand-2", organization_id: "org-2", brand_name: "Harbour" },
  { brand_id: "brand-3", organization_id: "org-1", brand_name: "Suburb" },
];
const locations: Location[] = [
  { location_id: "loc-1", brand_id: "brand-2", location_name: "Reykjavik", timezone: "Atlantic/Reykjavik" },
  { location_id: "loc-2", brand_id: "brand-1", location_name: "Downtown", timezone: "Asia/Amman" },
];
const entities: LegalEntity[] = [
  { legal_entity_id: "le-1", organization_id: "org-2", registered_name: "Veyro Nordics hf", tax_number: null },
];

describe("composing the hierarchy", () => {
  it("nests by id, not by the order the lists arrive in", () => {
    // **The lists are deliberately not in matching order.** A composer that zipped them by
    // position would put Reykjavik under City and the whole page would be confidently wrong.
    const { tree } = composeTree(organizations, brands, locations, entities);
    const first = tree.find((node) => node.organization.organization_id === "org-1")!;
    expect(first.brands.map((b) => b.brand.brand_name)).toEqual(["City", "Suburb"]);
    expect(first.brands[0]!.locations.map((l) => l.location_name)).toEqual(["Downtown"]);
    // A brand with no sites is still a brand, and it keeps an empty list rather than being
    // dropped -- the page says "no sites under this brand yet", which is a different fact
    // from the brand not existing.
    expect(first.brands[1]!.locations).toEqual([]);

    const second = tree.find((node) => node.organization.organization_id === "org-2")!;
    expect(second.brands.map((b) => b.brand.brand_name)).toEqual(["Harbour"]);
    expect(second.entities.map((e) => e.registered_name)).toEqual(["Veyro Nordics hf"]);
    expect(first.entities).toEqual([]);
  });

  it("keeps a row whose parent is missing rather than dropping it", () => {
    const strays = composeTree(
      organizations,
      [...brands, { brand_id: "brand-x", organization_id: "org-gone", brand_name: "Ghost" }],
      [...locations, { location_id: "loc-x", brand_id: "brand-gone", location_name: "Nowhere", timezone: "UTC" }],
      entities,
    );
    expect(strays.orphanBrands.map((b) => b.brand_name)).toEqual(["Ghost"]);
    expect(strays.orphanLocations.map((l) => l.location_name)).toEqual(["Nowhere"]);
    // And the orphan is not also nested somewhere it does not belong.
    const nested = strays.tree.flatMap((node) => node.brands.map((b) => b.brand.brand_name));
    expect(nested).not.toContain("Ghost");
  });

  it("returns nothing at all for a tenant with no organization", () => {
    expect(composeTree([], [], [], [])).toEqual({
      tree: [],
      orphanBrands: [],
      orphanLocations: [],
    });
  });
});

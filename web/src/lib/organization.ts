import { api } from "@/lib/api";

/**
 * MOD-004's hierarchy, typed: the organization, its brands, the sites and who invoices.
 *
 * **Four reads behind one permission.** `tenancy.organization.read` covers all of them, which
 * is the server's decision rather than this module's -- the hierarchy is one fact and a
 * surface that could show the sites but not the brand they belong to would be showing a tree
 * with its middle removed.
 *
 * `GET /brands` did not exist until this surface needed it: `create_brand` had been there
 * since MOD-004 and nothing could list what it wrote, so a brand id was knowable only by
 * having just created one. That is the "a writer with no reader" shape, and the fix was a
 * route rather than a workaround here, because inferring brand names from the locations that
 * cite them would have invented a brand with no sites out of existence.
 */

export type Organization = {
  organization_id: string;
  legal_name: string;
  country_code: string;
};

export type Brand = {
  brand_id: string;
  organization_id: string;
  brand_name: string;
};

export type Location = {
  location_id: string;
  brand_id: string;
  location_name: string;
  /** An IANA zone. MOD-019 reads every rota window in it, so it is not decoration. */
  timezone: string;
};

export type LegalEntity = {
  legal_entity_id: string;
  organization_id: string;
  registered_name: string;
  tax_number: string | null;
};

export function listOrganizations(): Promise<Organization[]> {
  return api<Organization[]>("/organizations");
}

export function listBrands(): Promise<Brand[]> {
  return api<Brand[]>("/brands");
}

export function listLocations(): Promise<Location[]> {
  return api<Location[]>("/locations");
}

export function listLegalEntities(): Promise<LegalEntity[]> {
  return api<LegalEntity[]>("/legal-entities");
}

/**
 * The hierarchy as a tree, resolved by id rather than by position.
 *
 * A location names its brand and a brand names its organization, so the three lists compose
 * without a join on the server. **An orphan is kept and marked rather than dropped**: a
 * location whose brand is missing from the brand list is a tenant-isolation question or a
 * read that raced a write, and silently omitting it would make a site disappear from the only
 * page that lists sites.
 */
export type OrganizationTree = {
  organization: Organization;
  entities: LegalEntity[];
  brands: { brand: Brand; locations: Location[] }[];
};

export function composeTree(
  organizations: Organization[],
  brands: Brand[],
  locations: Location[],
  entities: LegalEntity[],
): { tree: OrganizationTree[]; orphanBrands: Brand[]; orphanLocations: Location[] } {
  const locationsByBrand = new Map<string, Location[]>();
  for (const location of locations) {
    const list = locationsByBrand.get(location.brand_id) ?? [];
    list.push(location);
    locationsByBrand.set(location.brand_id, list);
  }
  const brandIds = new Set(brands.map((brand) => brand.brand_id));
  const organizationIds = new Set(organizations.map((o) => o.organization_id));

  const tree = organizations.map((organization) => ({
    organization,
    entities: entities.filter((e) => e.organization_id === organization.organization_id),
    brands: brands
      .filter((brand) => brand.organization_id === organization.organization_id)
      .map((brand) => ({
        brand,
        locations: locationsByBrand.get(brand.brand_id) ?? [],
      })),
  }));

  return {
    tree,
    orphanBrands: brands.filter((brand) => !organizationIds.has(brand.organization_id)),
    orphanLocations: locations.filter((location) => !brandIds.has(location.brand_id)),
  };
}

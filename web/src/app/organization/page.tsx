import { redirect } from "next/navigation";

import { Alert } from "@/components/controls";
import { t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate } from "@/lib/api";
import {
  composeTree,
  listBrands,
  listLegalEntities,
  listLocations,
  listOrganizations,
  type OrganizationTree,
} from "@/lib/organization";
import { presentation } from "@/lib/preferences";

/**
 * MOD-004's hierarchy: the company, its brands, its sites and the entity that invoices.
 *
 * **Why this page exists before the busier ones.** Every other surface in the product is
 * scoped by something on it -- a zone stands at a location, a rota window is read in that
 * location's timezone, an invoice is numbered per legal entity, and a brand-scoped role covers
 * exactly the sites under one brand. Until a reader can see the tree, every one of those
 * screens shows an id.
 *
 * **One gate call, because the server gates all four reads on one permission.** Asking per
 * read would invent a distinction the server does not make and would render a tree with its
 * middle missing when one of the four answered 403.
 *
 * **Nothing here writes.** Creating an organization, a brand, a site or a legal entity is a
 * `tenancy.*.write` permission in the `financial` action class, which needs a stepped-up
 * session -- so those are forms of their own rather than an inline add on a read page, and
 * they are not built yet.
 */
export default async function OrganizationPage() {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  const may = await gate("tenancy.organization.read");
  if (!may.allowed) {
    return (
      <Shell locale={locale}>
        <Alert tone="info">
          {may.reachable ? text("gate.denied") : text("gate.unreachable")}
        </Alert>
      </Shell>
    );
  }

  let composed: ReturnType<typeof composeTree>;
  try {
    const [organizations, brands, locations, entities] = await Promise.all([
      listOrganizations(),
      listBrands(),
      listLocations(),
      listLegalEntities(),
    ]);
    composed = composeTree(organizations, brands, locations, entities);
  } catch (error) {
    return (
      <Shell locale={locale}>
        <Alert tone="error">
          {error instanceof ApiError && error.reason === "unreachable"
            ? text("error.network")
            : text("error.unexpected")}
        </Alert>
      </Shell>
    );
  }

  const { tree, orphanBrands, orphanLocations } = composed;

  return (
    <Shell locale={locale}>
      <p className="muted" style={{ margin: 0 }}>
        {text("org.lead")}
      </p>
      {tree.length === 0 ? (
        <Alert tone="info">{text("org.none")}</Alert>
      ) : (
        tree.map((node) => <OrganizationCard key={node.organization.organization_id} node={node} locale={locale} />)
      )}
      {/* **An orphan is shown, not dropped.** A row naming a parent this read did not return
          is either a read that raced a write or an isolation question, and a site that
          disappears from the only page listing sites is the worse failure. */}
      {orphanBrands.length + orphanLocations.length > 0 ? (
        <section className="stack">
          <h2 style={{ margin: 0 }}>{text("org.orphans")}</h2>
          <p className="muted" style={{ margin: 0 }}>
            {text("org.orphansDetail")}
          </p>
          <ul>
            {orphanBrands.map((brand) => (
              <li key={brand.brand_id}>
                {brand.brand_name} — <span className="data" dir="ltr">{brand.organization_id}</span>
              </li>
            ))}
            {orphanLocations.map((location) => (
              <li key={location.location_id}>
                {location.location_name} — <span className="data" dir="ltr">{location.brand_id}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </Shell>
  );
}

function OrganizationCard({ node, locale }: { node: OrganizationTree; locale: Locale }) {
  const text = (key: MessageKey) => t(locale, key);
  const { organization, brands, entities } = node;
  return (
    <section className="panel stack">
      <h2 style={{ margin: 0 }}>{organization.legal_name}</h2>
      <p className="muted" style={{ margin: 0 }}>
        {text("org.country")}:{" "}
        {/* An ISO country code is an identifier rather than prose, so it stays
            left-to-right inside an Arabic document. */}
        <span className="data" dir="ltr">
          {organization.country_code}
        </span>
      </p>

      <h3 style={{ margin: 0 }}>{text("org.entities")}</h3>
      {entities.length === 0 ? (
        <Alert tone="info">{text("org.noEntities")}</Alert>
      ) : (
        <ul>
          {entities.map((entity) => (
            <li key={entity.legal_entity_id}>
              {entity.registered_name} — {text("org.taxNumber")}:{" "}
              {entity.tax_number ? (
                <span className="data" dir="ltr">
                  {entity.tax_number}
                </span>
              ) : (
                <span className="muted">{text("org.noTaxNumber")}</span>
              )}
            </li>
          ))}
        </ul>
      )}

      <h3 style={{ margin: 0 }}>{text("org.brands")}</h3>
      {brands.length === 0 ? (
        <Alert tone="info">{text("org.noBrands")}</Alert>
      ) : (
        brands.map(({ brand, locations }) => (
          <div key={brand.brand_id} className="stack" style={{ gap: "var(--space-2)" }}>
            <h4 style={{ margin: 0 }}>{brand.brand_name}</h4>
            {locations.length === 0 ? (
              <p className="muted" style={{ margin: 0 }}>
                {text("org.noLocations")}
              </p>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <caption style={{ textAlign: "start", paddingBottom: "var(--space-2)" }}>
                  {text("org.locations")}
                </caption>
                <thead>
                  <tr>
                    <th scope="col" style={headCell}>
                      {text("org.locations")}
                    </th>
                    <th scope="col" style={headCell}>
                      {text("org.timezone")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {locations.map((location) => (
                    <tr key={location.location_id}>
                      <td style={cell}>{location.location_name}</td>
                      <td style={cell}>
                        {/* An IANA zone name is an identifier: it is ASCII, it is not
                            translated, and MOD-019 reads every rota window in it. */}
                        <span className="data" dir="ltr">
                          {location.timezone}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        ))
      )}
    </section>
  );
}

function Shell({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  return (
    <div className="stack" style={{ padding: "var(--space-6)", maxWidth: "960px" }}>
      <h1 style={{ margin: 0 }}>{t(locale, "org.title")}</h1>
      {children}
    </div>
  );
}

const headCell: React.CSSProperties = {
  textAlign: "start",
  padding: "var(--space-2) var(--space-3)",
  borderBottom: "1px solid var(--color-border-default)",
  background: "var(--color-surface-sunken)",
  fontSize: "var(--type-label-size)",
  fontWeight: "var(--type-label-weight)",
};

const cell: React.CSSProperties = {
  textAlign: "start",
  verticalAlign: "top",
  padding: "var(--space-2) var(--space-3)",
  borderBottom: "1px solid var(--color-border-subtle)",
};

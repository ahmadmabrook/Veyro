import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { PageHeader } from "@/components/ds/page-header";
import { DataGrid } from "@/components/ds/data-grid";
import { fill, t, type Locale, type MessageKey } from "@/i18n/locale";
import { currentSession, gate, failureMessage } from "@/lib/api";
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
        <Banner severity="info">
          {may.reachable ? text("gate.denied") : text("gate.unreachable")}
        </Banner>
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
        <Banner severity="critical">
          {text(failureMessage(error))}
        </Banner>
      </Shell>
    );
  }

  const { tree, orphanBrands, orphanLocations } = composed;

  return (
    <Shell
      locale={locale}
      figures={
        <>
          {fill(locale, "org.brandsCounted", { count: tree.reduce(
            (sum, node) => sum + node.brands.length, 0) })}
          {" \u00b7 "}
          {fill(locale, "org.sitesCounted", { count: tree.reduce((sum, node) =>
            sum + node.brands.reduce((n, brand) => n + brand.locations.length, 0), 0) })}
          {" \u00b7 "}
          {fill(locale, "org.entitiesCounted", { count: tree.reduce(
            (sum, node) => sum + node.entities.length, 0) })}
        </>
      }
    >
      {tree.length === 0 ? (
        <Banner severity="info">{text("org.none")}</Banner>
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
    <section className="page-section">
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
        <Banner severity="info">{text("org.noEntities")}</Banner>
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
        <Banner severity="info">{text("org.noBrands")}</Banner>
      ) : (
        brands.map(({ brand, locations }) => (
          <div key={brand.brand_id} className="stack" style={{ gap: "var(--space-2)" }}>
            <h4 id={`sites-${brand.brand_id}`} style={{ margin: 0 }}>{brand.brand_name}</h4>
            {locations.length === 0 ? (
              <p className="muted" style={{ margin: 0 }}>
                {text("org.noLocations")}
              </p>
            ) : (
              <DataGrid
                caption={text("org.locations")}
                labelledBy={`sites-${brand.brand_id}`}
                rows={locations}
                rowKey={(location) => location.location_id}
                columns={[
                  {
                    header: text("org.locations"),
                    kind: "text",
                    priority: 1,
                    render: (location) => location.location_name,
                  },
                  {
                    header: text("org.timezone"),
                    kind: "text",
                    // Priority 1: MOD-019 reads every rota window in this zone, so a site
                    // list without it is a list nobody can schedule from.
                    priority: 1,
                    // An IANA zone name is an identifier: it is ASCII, it is not translated,
                    // and the bidi algorithm would reorder it inside an Arabic page.
                    render: (location) => (
                      <span className="data" dir="ltr">{location.timezone}</span>
                    ),
                  },
                ]}
              />
            )}
          </div>
        ))
      )}
    </section>
  );
}

function Shell({
  locale,
  children,
  figures,
}: {
  locale: Locale;
  children: React.ReactNode;
  /**
   * The counts under the title.
   *
   * **The design's page header is a title and a line of figures, never a paragraph**, and
   * every drawn canvas does the same: "4,812 active · 312 expired · 68 frozen · all
   * locations". A board whose header carried only its own name made a reader scroll to find
   * out whether anything on it needed them.
   */
  figures?: React.ReactNode;
}) {
  return (
    <div className="stack">
      <PageHeader title={t(locale, "org.title")} {...(figures ? { figures } : {})} />
      {children}
      {/* The lead moved to the foot; see `PageHeader`. */}
      <p className="ds-screen-note">{t(locale, "org.lead")}</p>
    </div>
  );
}



import type { Metadata } from "next";

import { AppNav, type NavItem } from "@/components/nav";
import { AdminShell } from "@/components/ds/shell";
import { LocaleSwitch } from "@/components/locale-switch";
import { t } from "@/i18n/locale";
import { currentSession, gateAll } from "@/lib/api";
import { presentation } from "@/lib/preferences";

import "./globals.css";

export const metadata: Metadata = {
  title: "Veyro",
  description: "Veyro gym management.",
};

/**
 * The root layout sets `lang`, `dir` and `data-theme` on `<html>`, which is what makes RTL and
 * the dark mapping work at all.
 *
 * **All three come from one place and none is a prop.** `dir` is derived from the locale by
 * `direction()`, so a component cannot be rendered LTR inside an Arabic document by passing the
 * wrong value -- and CSS logical properties (`inset-inline-start`, `margin-inline`) then mirror
 * the whole interface without a single RTL-specific rule. The theme is read from a cookie on
 * the server rather than detected in the browser, because detecting it in the browser is the
 * flash of the wrong theme.
 */
export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const { locale, dir, theme } = await presentation();

  // **The navigation is built here because every page has one, and it is asked rather than
  // assumed.** A signed-out reader gets none: `currentSession()` answers null for a visitor
  // with no tenant cookie, which is the ordinary state of the sign-in page.
  const session = await currentSession();
  let items: NavItem[] = [];
  if (session) {
    // **One request for all thirteen.** The shell asks the gate about every section, and
    // asking separately cost thirteen round trips on every page in the app -- which, with
    // the Command Center's own six, put `/` at nineteen against MOD-011's 600-a-minute
    // per-identity budget. Same evaluator, same assurance weighing, one scope resolution.
    const [
      organization, people, access, permissions, devices, operations, schedule, configuration,
      finance, catalog, privacy, messages, integrations,
    ] = await gateAll([
      "tenancy.organization.read",
      "people.person.read",
      "access.zone.read",
      "authz.role.read",
      "devices.device.read",
      "events.event.read",
      "scheduling.schedule.read",
      "config.definition.read",
      "finance.ledger.read",
      "catalog.product.read",
      "privacy.dsar.read",
      "notifications.notification.read",
      "integrations.install.read",
    ] as const);
    items = [
      // **The Command Center needs no permission of its own**, and that is the design's
      // call rather than a convenience: ADM-CC-02 is "not a reduced Command Center -- a
      // differently prioritised one", so a club manager opens the same screen and sees the
      // panels their grants reach. Gating the page itself would make the first thing a
      // receptionist sees a refusal.
      { href: "/", label: "nav.overview", allowed: true },
      // **No gate.** Every route this page reads is scoped to the caller's own
      // identity and refuses any other subject with a 404, so there is nothing to
      // authorize -- which is why it is present for every signed-in reader.
      { href: "/account", label: "nav.account", allowed: true },
      { href: "/organization", label: "nav.organization", allowed: organization.allowed },
      // **Members before People.** ADM-MEM-05 is the members list an operator opens;
      // `/people` is the duplicate queue and the record behind it. Both need the same
      // permission, so they share a gate answer.
      { href: "/members", label: "nav.members", allowed: people.allowed },
      { href: "/people", label: "nav.people", allowed: people.allowed },
      { href: "/schedule", label: "nav.schedule", allowed: schedule.allowed },
      { href: "/access", label: "nav.access", allowed: access.allowed },
      { href: "/fleet", label: "nav.devices", allowed: devices.allowed },
      { href: "/permissions", label: "nav.permissions", allowed: permissions.allowed },
      { href: "/configuration", label: "nav.configuration", allowed: configuration.allowed },
      { href: "/catalog", label: "nav.catalog", allowed: catalog.allowed },
      { href: "/finance", label: "nav.finance", allowed: finance.allowed },
      { href: "/privacy", label: "nav.privacy", allowed: privacy.allowed },
      { href: "/notifications", label: "nav.notifications", allowed: messages.allowed },
      { href: "/integrations", label: "nav.integrations", allowed: integrations.allowed },
      { href: "/operations", label: "nav.operations", allowed: operations.allowed },
    ];
  }

  return (
    <html lang={locale} dir={dir} data-theme={theme}>
      <body>
        {/* First focusable thing on every page: a keyboard user should not tab the whole nav. */}
        <a className="skip-link" href="#main">
          {t(locale, "app.skipToContent")}
        </a>
        {/* **In the layout, so every page has it.** The first version put the language and
            theme controls on the landing page and the sign-in page, which left a reader who
            followed a link to a zone with no way back to their own language -- and made the
            direction of the whole document depend on which page they happened to enter by. */}
        {/* **The Admin shell**, per LAYOUTS: rail 240 expanded / 56 collapsed, content max
            1440, 24px gutter. A signed-out reader gets no rail and no shell -- the sign-in
            page is its own surface and wrapping it in an empty rail would be a frame around
            nothing. */}
        {items.length === 0 ? (
          <>
            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                padding: "var(--space-4) var(--space-4) 0",
              }}
            >
              <LocaleSwitch locale={locale} theme={theme} />
            </div>
            <main id="main">{children}</main>
          </>
        ) : (
          <AdminShell
            rail={
              <>
                <AppNav locale={locale} items={items} />
                {/* Global chrome. §21 names five things in it -- scope switcher, ⌘K, tasks,
                    alerts, account -- of which this build has the account (the rail's own
                    entry) and the language and theme controls. The other three are recorded
                    as gaps rather than drawn as controls that do nothing. */}
                <div className="ds-rail-chrome">
                  <LocaleSwitch locale={locale} theme={theme} />
                </div>
              </>
            }
          >
            <main id="main">{children}</main>
          </AdminShell>
        )}
      </body>
    </html>
  );
}

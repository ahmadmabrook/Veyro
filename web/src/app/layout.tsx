import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, IBM_Plex_Sans_Arabic } from "next/font/google";

import Link from "next/link";

import { AppNav, type NavItem } from "@/components/nav";
import { Chrome } from "@/components/ds/chrome";
import { AdminShell } from "@/components/ds/shell";
import { LocaleSwitch } from "@/components/locale-switch";
import { formatInteger, t } from "@/i18n/locale";
import { currentSession, gateAll } from "@/lib/api";
import { listMembers } from "@/lib/members-reads";
import { conventions } from "@/lib/display";
import { presentation } from "@/lib/preferences";

import "./globals.css";

/**
 * **The three faces the design is drawn in**, at exactly the weights it asks for.
 *
 * The design documents load them in their own preamble:
 *
 *     family=IBM+Plex+Sans:wght@400;450;500;600
 *     &family=IBM+Plex+Mono:wght@400;500
 *     &family=IBM+Plex+Sans+Arabic:wght@400;500;600
 *
 * **`globals.css` named them from the first commit and nothing ever loaded one**, so every
 * screen in this product rendered in the system face while the stylesheet said IBM Plex. A
 * font-family declaration for a font that is not there is not a typeface, it is a comment --
 * and no test could see it, because `getComputedStyle` reports the *declared* family whether
 * or not the browser found it.
 *
 * `next/font` self-hosts them at build time rather than linking to Google at runtime, which
 * is the same faces without a third party in every reader's request path -- and it is what
 * makes `font-display: swap` a flash of the right metrics rather than of the wrong font.
 *
 * **450 is requested by the design and not served.** Its preamble asks for `wght@400;450;500;600`
 * and Google answers with 400, 500 and 600 only -- so the design's own `font:450 12px` on nav
 * items and chips renders at 400 in the drawn documents too. Asking for it here would be
 * asking for a face that does not arrive; 400 is what the design actually looks like.
 */
const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-sans",
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex-mono",
  display: "swap",
});

const plexArabic = IBM_Plex_Sans_Arabic({
  subsets: ["arabic"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-arabic",
  display: "swap",
});

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
  // The canvas puts a count beside Members, Leads and Payments. This build can answer the
  // first: `GET /people` returns the tenant's total beside the page's match, which is the
  // same two numbers ADM-MEM-05's footer renders.
  let memberCount: string | undefined;
  if (session) {
    // **One request for all thirteen.** The shell asks the gate about every section, and
    // asking separately cost thirteen round trips on every page in the app -- which, with
    // the Command Center's own six, put `/` at nineteen against MOD-011's 600-a-minute
    // per-identity budget. Same evaluator, same assurance weighing, one scope resolution.
    const [
      organization, people, access, permissions, devices, operations, schedule, configuration,
      finance, catalog, privacy, messages, integrations, payments, tasks, leads, till,
      memberships, prices, localization,
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
      "finance.payment.read",
      "tasks.task.read",
      "crm.lead.read",
      "finance.cash.session",
      // **ADM-MSH-09 needs three and the rail asks for the two `catalog` does not cover.**
      // `/plans` reads the picker (product *and* membership), the prices and the per-plan
      // count, so an entry gated on the catalogue alone would be shown to a session the
      // page then refuses.
      "membership.record.read",
      "catalog.price.read",
      // **ADM-SET-07 has its own permission and the rail asks for it** -- ADR-0015 D1. It is
      // deliberately not `config.definition.read`: the whole point of a narrow read is that a
      // front desk can hold it, so a rail entry gated on the registry would hide the screen
      // from exactly the reader the permission was separated for.
      "config.display.read",
    ] as const);
    // **Grouped, iconed and counted, which is what the rail actually is.** The Command
    // Center canvas draws thirteen items under four headings -- OPERATE, PEOPLE, MONEY,
    // DELIVER -- each with an icon and some with a count, and a flat list of fifteen links
    // is not that. The group names are the design's own; the items are the sections this
    // build has, placed in the group the design puts their subject in.
    //
    // **The design's own thirteen do not all exist here**, and the absent ones are absent
    // rather than disabled: §21 says the rail is "generated, never a static tree with
    // disabled rows -- a receptionist and an accountant get different rails, not the same
    // rail greyed differently". Point of sale, Coaching, Automations and Help have no
    // screen in this build, and the Command Center's gaps list names them.
    //
    // **`Front desk` is the design's own OPERATE entry and this rail now has one screen of
    // it**, which is why that item is named for the screen rather than for the surface:
    // FD-01, the live check-in a receptionist starts a shift on, is unbuilt, and an entry
    // called "Front desk" would promise it. FD-06 and FD-03 are reached from a class and a
    // refusal, so the walk-in is the only `/desk` route reachable without an id -- and a
    // screen with no route to it is unreachable, which is the rail's job here as it is for
    // tasks. The day FD-01 lands this becomes `Front desk` and points at it.
    items = [
      // **The Command Center needs no permission of its own**, and that is the design's
      // call rather than a convenience: ADM-CC-02 is "not a reduced Command Center -- a
      // differently prioritised one", so a club manager opens the same screen and sees the
      // panels their grants reach. Gating the page itself would make the first thing a
      // receptionist sees a refusal.
      { href: "/", label: "nav.overview", allowed: true,
        group: "nav.groupOperate", icon: "command-center" },
      { href: "/schedule", label: "nav.schedule", allowed: schedule.allowed,
        group: "nav.groupOperate", icon: "scheduling" },
      { href: "/access", label: "nav.access", allowed: access.allowed,
        group: "nav.groupOperate", icon: "doors" },
      { href: "/fleet", label: "nav.devices", allowed: devices.allowed,
        group: "nav.groupOperate", icon: "devices" },
      // **Gated on the duplicate check rather than on the write**, which is the screen's own
      // judgement: without `people.person.read` there is nothing for the page to do, and the
      // five write permissions it needs are answered on the page with the step-up beside
      // them. Hiding the entry from a session that could step up would hide the offer too.
      // **First in the rail among the desk's screens, because it is the one a receptionist
      // starts from.** FD-01, the live check-in, is unbuilt; this is the lookup, and it is
      // gated on the person read because without it there is nothing to find.
      { href: "/desk/lookup", label: "nav.lookup", allowed: people.allowed,
        group: "nav.groupOperate", icon: "front-desk" },
      { href: "/desk/trial", label: "nav.walkInTrial", allowed: people.allowed,
        group: "nav.groupOperate", icon: "members" },
      // **Named for the screen rather than the surface**, as the walk-in is: FD-01 is unbuilt,
      // so an item called "Front desk" would promise a live check-in this build does not
      // have. Gated on the till permission, which is the one thing without which the page has
      // nothing to show -- and it is `configuration` with no financial class, so the entry is
      // not hiding a step-up.
      { href: "/desk/shift", label: "nav.shift", allowed: till.allowed,
        group: "nav.groupMoney", icon: "front-desk" },

      // **Members before People.** ADM-MEM-05 is the members list an operator opens;
      // `/people` is the duplicate queue and the record behind it. Both need the same
      // permission, so they share a gate answer.
      { href: "/members", label: "nav.members", allowed: people.allowed,
        group: "nav.groupPeople", icon: "members" },
      { href: "/people", label: "nav.people", allowed: people.allowed,
        group: "nav.groupPeople", icon: "staff" },
      // **`Leads` is the design's own third PEOPLE entry**, between Members and Staff in
      // ADM-CC-01's rail with a count beside it: `['Leads', 'ADM-CRM-01', '◎', '36']`. The
      // count is not rendered here, because the figure the canvas shows is the open-lead
      // total and the rail would be a second place it is computed -- the board's header is
      // where it belongs, and two of them can disagree.
      { href: "/leads", label: "nav.leads", allowed: leads.allowed,
        group: "nav.groupPeople", icon: "members" },
      // **The design's own "Staff & coaches", which this rail listed as absent until now.**
      // It shares `people.person.read` with the two above because a staff profile is one of
      // a person's profiles -- the permission's own description says so -- and the role and
      // login halves the page composes ask their own gates on the page itself.
      // **`allowed_anywhere`, because this is the one page that accepts a scoped caller** --
      // ADR-0014. Every other entry reads `allowed`, which is narrowed to "allowed *and*
      // tenant-wide" precisely so each keeps refusing a brand- or location-scoped role as it
      // did rather than offering a link to a read that answers 403. ADM-CC-02's canvas says
      // "the rail is generated from his role rather than greyed", and a rail of one entry is
      // what that sentence means in a build where one route has opted in.
      { href: "/staff", label: "nav.staffList", allowed: people.allowed_anywhere,
        group: "nav.groupPeople", icon: "staff" },
      { href: "/permissions", label: "nav.permissions", allowed: permissions.allowed,
        group: "nav.groupPeople", icon: "permissions" },

      // **Payments before the general ledger**, which is the canvas's own order and the
      // order of use: a manager opens the payments ledger every morning and an accountant
      // opens the general ledger at a month end. `MONEY · Payments · Point of sale ·
      // Reports` is what ADM-CC-01 draws, and `/finance` is the nearest thing this build
      // has to Reports.
      { href: "/payments", label: "nav.payments", allowed: payments.allowed,
        group: "nav.groupMoney", icon: "payments" },
      { href: "/finance", label: "nav.finance", allowed: finance.allowed,
        group: "nav.groupMoney", icon: "payments" },
      // **Reports is in the canvas's own MONEY group**, and the index gates itself: every
      // entry asks the gate about the report behind it, so a session with no report to open
      // still reaches a page that says which ones this build cannot produce at all. Gating
      // the rail entry on one report's permission would hide that from the reader who most
      // needs it.
      { href: "/reports", label: "nav.reports", allowed: true,
        group: "nav.groupMoney", icon: "reports" },
      // **ADM-MSH-09, beside the catalogue it prices.** The design calls it "Plans & pricing
      // · OWNER ONLY", which is a permission rather than a rail decision: `catalog.price.write`
      // is financial class, so a reader who can see the plans and not re-price them gets the
      // table and the sheet's own sentence instead of a button.
      { href: "/plans", label: "nav.plans",
        allowed: catalog.allowed && memberships.allowed && prices.allowed,
        group: "nav.groupMoney", icon: "payments" },
      { href: "/catalog", label: "nav.catalog", allowed: catalog.allowed,
        group: "nav.groupMoney", icon: "point-of-sale" },

      { href: "/notifications", label: "nav.notifications", allowed: messages.allowed,
        group: "nav.groupDeliver", icon: "messages" },
      // **The design's DELIVER group holds `Automations` (ADM-AUT-01), and this is the work
      // half of the same domain.** The sources call it "Automations & Work" and put four
      // screens in it, of which "Tasks, cases & approvals" is the only V1 one and the only
      // one this build has: the automation library, the workflow builder and the run history
      // are MOD-055's and unbuilt. So the rail points at the half that exists rather than at
      // nothing, which is this file's own rule -- "the items are the sections this build has,
      // placed in the group the design puts their subject in".
      //
      // **The design reaches tasks from an exception and from a notification rather than from
      // the rail**, and neither of those exists here: the Command Center's queue is computed
      // live rather than filed as cases, and nothing sends a notification. A screen with no
      // route to it is unreachable, so the rail is the route.
      { href: "/tasks", label: "nav.tasks", allowed: tasks.allowed,
        group: "nav.groupDeliver", icon: "automations" },
      { href: "/integrations", label: "nav.integrations", allowed: integrations.allowed,
        group: "nav.groupDeliver", icon: "integrations" },

      // Settings, which the canvas puts after the groups rather than in one. This build has
      // four screens where the design has one item with a second level, and §21 caps a
      // secondary nav at seven -- so they sit together under one heading.
      { href: "/organization", label: "nav.organization", allowed: organization.allowed,
        group: "nav.groupSettings", icon: "organization" },
      { href: "/configuration", label: "nav.configuration", allowed: configuration.allowed,
        group: "nav.groupSettings", icon: "configuration" },
      // **After the configuration board, because it is a slice of the same registry read
      // through its own permission.** ADM-SET-07's two keys are `cfg_values` rows like any
      // other; what makes the screen separate is that the design draws them as conventions a
      // reader checks rather than as keys an engineer configures.
      { href: "/localization", label: "nav.localization", allowed: localization.allowed,
        group: "nav.groupSettings", icon: "settings" },
      { href: "/privacy", label: "nav.privacy", allowed: privacy.allowed,
        group: "nav.groupSettings", icon: "privacy" },
      { href: "/operations", label: "nav.operations", allowed: operations.allowed,
        group: "nav.groupSettings", icon: "operations" },
      // **No gate.** Every route this page reads is scoped to the caller's own
      // identity and refuses any other subject with a 404, so there is nothing to
      // authorize -- which is why it is present for every signed-in reader.
      { href: "/account", label: "nav.account", allowed: true,
        group: "nav.groupSettings", icon: "account" },
    ];
  }

  // **One read for the whole render, started here.** ADR-0015 D7: `conventions()` is React's
  // per-request memo, so asking for it in the layout means every page and component that
  // renders a figure shares this call rather than making its own -- and starting it before
  // the count below means the two are in flight together rather than one after the other.
  // Only when there is a session: the sign-in page has no tenant to ask about, and a request
  // that could only fail is a request not worth making.
  const theirs = session ? conventions() : null;

  if (session && items.some((item) => item.href === "/members" && item.allowed)) {
    // **One extra read for the whole rail, and a failure costs the count rather than the
    // page.** A rail that refused to render because a count was unavailable would be a
    // navigation that depends on a figure, which is the wrong way round.
    //
    // **And the count follows the tenant's numerals**, which it did not until ADR-0015: a rail
    // figure left in Latin digits beside a page of Arabic-Indic ones is exactly the mixing
    // "one rule per tenant, never mixed and never decided per component" forbids, and the
    // rail is the figure a reader sees on every screen.
    const [page, numerals] = await Promise.all([
      listMembers({ limit: 1 }).catch(() => null),
      theirs,
    ]);
    memberCount = page === null
      ? undefined
      : formatInteger(page.total, numerals?.numerals ?? "latn");
    items = items.map((item) =>
      item.href === "/members" && memberCount !== undefined
        ? { ...item, count: memberCount }
        : item);
  }

  return (
    <html
      lang={locale}
      dir={dir}
      data-theme={theme}
      className={`${plexSans.variable} ${plexMono.variable} ${plexArabic.variable}`}
    >
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
            rail={<AppNav locale={locale} items={items} />}
            /* §21's first layer, above the rail and the content both. The canvas draws it
               at 48px with the mark, the tenant, the scope, the search, tasks, alerts and
               the account; what is here is the half that works, and `Chrome` says which
               three are absent and why. */
            chrome={
              <Chrome
                mark={t(locale, "app.mark")}
                organization={t(locale, "app.name")}
                scope={t(locale, "cc.scope")}
              >
                <LocaleSwitch locale={locale} theme={theme} />
                <Link className="ds-chrome-avatar" href="/account" aria-label={t(locale, "nav.account")}>
                  {t(locale, "app.mark")}
                </Link>
              </Chrome>
            }
          >
            <main id="main">{children}</main>
          </AdminShell>
        )}
      </body>
    </html>
  );
}

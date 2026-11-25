import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { DataGrid } from "@/components/ds/data-grid";
import { PageHeader } from "@/components/ds/page-header";
import { Prose, ProseNote } from "@/components/prose";
import { WithheldLink } from "@/components/withheld";
import { fill, t, type Locale, type MessageKey } from "@/i18n/locale";
import {
  currentSession, failureMessage, gateAll, gateMessage, gateVerdict,
} from "@/lib/api";
import type { Assignment } from "@/lib/authz";
import { listLocations, type Location } from "@/lib/organization";
import { isWithheld, withheldRemedy } from "@/lib/people";
import { presentation } from "@/lib/preferences";
import {
  accessFindings,
  readAssignments,
  readLastSeen,
  readStaff,
  reachOf,
  splitRole,
  standingName,
  standingOf,
  standingSeverity,
  stateName,
  type LastSeen,
  type StaffList,
  type StaffRow,
} from "@/lib/staff";
import { utcStamp } from "@/lib/time";

/**
 * ADM-STF-01 · STAFF LIST · COMPACT.
 *
 * The canvas, in full:
 *
 * > `Active · 14`  `Invited · 2`  `Left · 3`                           `[Invite]`
 * > NAME | ROLE | CLUBS | LAST SEEN
 * > ┌ **Dana's spin certification expires in 18 days.** Certifications inside 30 days raise a
 * > └ Command Center item — an uncertified coach taking a class is an insurance problem.
 * > A Club Manager sees only their own club's staff. Last seen exists so a departed employee
 * > with a live login is visible rather than discovered.
 *
 * **`ppl_staff_profiles` had no reader at all.** MOD-014 shipped `upsert_staff_profile` and
 * `end_staff_employment` and nothing that lists them, so a tenant's team was reachable only
 * by knowing a person id already — this build's recurring "a writer with no reader" shape,
 * now closed by `GET /staff`.
 *
 * **Four columns on three planes, which is why the page composes rather than joins.** The
 * profiles are MOD-014's under `veyro_cp_app`; ROLE is MOD-008's `iam.role_assignments` and
 * LAST SEEN is MOD-007's `iam.sessions`, both under `veyro_iam_app`, which holds nothing in
 * `plt01`. Three permissions, asked separately, because a reader may hold any subset — and a
 * refused half says it was refused rather than rendering an empty cell. Both role and
 * last-seen reads are **batched**: fifty rows asking one at a time is the round-trip problem
 * `/authz/checks` was added for, against a budget the browser suite has already tripped.
 *
 * **The warning box is a real finding and the design told us which one.** There are no
 * certifications anywhere in this build — no table, no expiry, nothing to read — so the
 * canvas's amber box has nothing behind it. What it *does* have behind it is the sentence
 * under the table: a departed employee with a live login. That is derivable from the two
 * halves this page already holds, it needs somebody today, and it is the stated purpose of
 * the column the design put beside it.
 *
 * **There is no Invite button.** ADM-STF-03 is unbuilt: no invitation table, no token, no
 * expiry and nothing that sends. A button answering 403 is worse than its absence, and a
 * third chip reading "Invited · 0" would say nobody has been invited rather than that nothing
 * can invite anybody.
 *
 * **"A Club Manager sees only their own club's staff" is not true here**, and the page says
 * so rather than letting its filter read as a boundary: `permit` resolves against the
 * tenant-wide default scope, which MOD-014 records as its own standing gap.
 */

export const dynamic = "force-dynamic";

export default async function StaffPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);
  const query = await searchParams;
  const only = typeof query.state === "string" ? query.state : undefined;

  if (!(await currentSession())) redirect("/login?next=/staff");

  const [mayStaff, mayRoles, mayLogins, maySites, mayNames] = await gateAll([
    "people.person.read",
    "authz.role.read",
    "identity.identity.read",
    "tenancy.organization.read",
    // **Not to decide the read -- to decide what the withheld banner may offer.** A legal
    // name is MOD-014's `identity` class and this is the permission that opens it, so the
    // answer is what says whether a step-up would lift the mask or whether this role simply
    // does not include reading identity fields. In the same batch because it is the same
    // question about the same session, and `/authz/checks` exists so a page costs one round
    // trip rather than five.
    "member.identity.read",
  ] as const);

  // **The raw answer, because this page filters** -- ADR-0014, and the only page in this app
  // that does so far. `allowed` is narrowed to "allowed *and* tenant-wide" for every other
  // page, so that each keeps refusing a brand- or location-scoped caller exactly as it did
  // rather than rendering as permitted over a read that answers 403. This one reads
  // `allowed_anywhere` and `GET /staff` bounds the list to the clubs the gate named.
  if (!mayStaff.allowed_anywhere) {
    return (
      <Shell locale={locale}>
        <Banner severity="info">{text(gateMessage(mayStaff))}</Banner>
        {mayStaff.step_up_required ? (
          <p className="ds-note">
            <Link href={`/step-up?for=financial&action=people.person.read&next=${
              encodeURIComponent("/staff")}`}>{text("member.raiseSession")}</Link>
          </p>
        ) : null}
      </Shell>
    );
  }

  let list: StaffList;
  try {
    list = await readStaff(only ? { employment_state: only } : {});
  } catch (error) {
    return (
      <Shell locale={locale}>
        <Banner severity="critical">{text(failureMessage(error))}</Banner>
      </Shell>
    );
  }

  const linked = list.staff.flatMap((row) => row.identity_id ? [row.identity_id] : []);
  // **A failed read is not an empty answer.** `null` means nobody asked or nobody could, and
  // `standingOf` turns that into `unknown` rather than into "no access" — which is the
  // difference between telling an owner a leaver has been checked and telling them nothing.
  const roles: Map<string, Assignment[]> | null = mayRoles.allowed
    ? await readAssignments(linked).catch(() => null)
    : null;
  const seen: Map<string, LastSeen> | null = mayLogins.allowed
    ? await readLastSeen(linked).catch(() => null)
    : null;
  const sites: Map<string, Location> | null = maySites.allowed
    ? await listLocations()
      .then((all) => new Map(all.map((one) => [one.location_id, one])))
      .catch(() => null)
    : null;

  // **The remedy, decided once, so the banner and every row say the same thing.** A legal
  // name is MOD-014's `identity` class; `member.identity.read` opens it and is `financial`,
  // so a step-up lifts the mask for a session that holds the grant and does nothing for a
  // role that does not. `WithheldLink` was built for exactly this -- its own docstring says
  // the reason is part of the rendering "because the two reasons a field is withheld here
  // have different remedies and they are different doors" -- and the app had been passing the
  // step-up key for a third case the component anticipated and nobody supplied.
  const remedy = withheldRemedy(gateVerdict(mayNames));
  const nameWithheld: MessageKey = remedy === "step_up"
    ? "member.withheldIdentity"
    : "member.withheldIdentityNoRemedy";

  const findings = accessFindings(list.staff, seen);
  const chips = list.states.map((state) => ({
    state,
    label: stateName(state),
    count: list.by_state[state] ?? 0,
  }));

  return (
    <Shell
      locale={locale}
      figures={
        // **Two numbers, because one of them read as the whole team.** The first version led
        // with the active count under the words "people on the team" while the grid's own
        // footer said four, so the page disagreed with itself by two. The members list makes
        // the same distinction for the same reason: a figure that reports only part of the
        // table invites the reader to look for the rest.
        <>
          {fill(locale, "staff.working", { count: list.by_state.active ?? 0 })}
          {" · "}
          {fill(locale, "staff.onRecord", { count: list.total })}
          {" · "}
          <span className="data" dir="ltr">{utcStamp(new Date().toISOString())}</span>
        </>
      }
    >
      {/* **The canvas's chip row, as links.** The same decision the members list makes: a
          filter that works without JavaScript, with the state in the URL so a filtered list
          can be sent to somebody. The count rides on the chip because the canvas puts it
          there, and it is the tenant's count rather than the page's. */}
      <nav className="ds-filter-bar" aria-label={text("staff.filterLabel")}>
        <Link
          href="/staff"
          className="ds-filter-chip"
          {...(only === undefined ? { "aria-current": "page" as const } : {})}
        >
          {text("staff.filterAll")}
        </Link>
        {chips.map((chip) => (
          <Link
            key={chip.state}
            href={`/staff?state=${chip.state}`}
            className="ds-filter-chip"
            {...(only === chip.state ? { "aria-current": "page" as const } : {})}
          >
            {`${chip.label === null ? chip.state : text(chip.label)} · ${chip.count}`}
          </Link>
        ))}
      </nav>

      {/* **ADR-0014: a bounded list says so.** The design's own note is "a club manager sees
          only their own club's staff", which was a sentence on this screen rather than a
          predicate until the gate could answer *where* -- such a caller was refused the read
          outright. Now the list can be the reader's clubs rather than the tenant, and a
          bounded list read as the whole team is a team that is not there. `null` is a
          tenant-wide reader, for whom nothing is bounded and this says nothing. */}
      {list.bounded_to_locations !== null ? (
        <Banner severity="info">
          {fill(locale, "staff.boundedToClubs",
            { count: list.bounded_to_locations.length })}
        </Banner>
      ) : null}

      {/* **The finding, where the canvas draws its certification warning.** Critical rather
          than amber: somebody who has left can still open the product. */}
      {findings.length > 0 ? (
        <Banner severity="critical">
          {fill(locale, "staff.stillHaveAccess", { count: findings.length })}{" "}
          {text("staff.stillHaveAccessWhy")}
        </Banner>
      ) : null}
      {seen === null && list.staff.some((row) => row.employment_state === "ended") ? (
        <Banner severity="info">{text("staff.accessCheckRefused")}</Banner>
      ) : null}

      {/* **The remedy has to match the cause, and for a scoped caller it did not.** This
          said "this session has not presented a second factor" to everybody and offered the
          step-up that lifts it -- true for a tenant-wide reader at AAL 1, false for a club
          manager, who holds `people.person.read` and nothing else and would present a
          recovery code to no effect. ADR-0014 is what made that reader reach this page at
          all, so the sentence was wrong for the first caller the gate's new answer admitted.
          `withheldRemedy` is the split and the gate is what decides it. */}
      {list.staff.some((row) => isWithheld(row.preferred_name ?? row.legal_name)) ? (
        <p className="ds-note">
          {remedy === "step_up" ? (
            <>
              {text("staff.namesWithheld")}{" "}
              <Link href={`/step-up?for=financial&action=member.identity.read&next=${
                encodeURIComponent("/staff")}`}>{text("member.raiseSession")}</Link>
            </>
          ) : remedy === "no_answer" ? (
            text("member.namesWithheldNoAnswer")
          ) : (
            text("member.namesWithheldNotHeld")
          )}
        </p>
      ) : null}

      <section className="page-section">
        <h2 id="staff-heading" style={{ margin: 0 }}>{text("staff.tableTitle")}</h2>
        <DataGrid
          caption={text("staff.tableTitle")}
          labelledBy="staff-heading"
          rows={list.staff}
          rowKey={(row) => row.person_id}
          rowSeverity={(row) => standingSeverity(
            standingOf(row, seen?.get(row.identity_id ?? "") ?? null))}
          countLabel={fill(locale, "staff.rowCount", { count: list.matching })}
          columns={[
            {
              header: text("staff.colName"),
              kind: "person",
              priority: 1,
              render: (row) => (
                <>
                  {isWithheld(row.preferred_name ?? row.legal_name) ? (
                    <WithheldLink
                      locale={locale}
                      reason={nameWithheld}
                      href={`/staff/${row.person_id}`}
                      label={fill(locale, "staff.openWithheld", {
                        what: [row.job_title, row.started_on]
                          .filter((one): one is string => one !== null).join(" · "),
                      })}
                    />
                  ) : (
                    <Link href={`/staff/${row.person_id}`}>
                      {row.preferred_name ?? row.legal_name}
                    </Link>
                  )}
                  <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
                    {row.job_title ?? text("staff.noTitle")}
                    {row.location_name === null ? null : ` · ${row.location_name}`}
                    {row.started_on === null ? null : (
                      <>
                        {" · "}
                        <span className="data" dir="ltr">{row.started_on}</span>
                      </>
                    )}
                  </div>
                </>
              ),
            },
            {
              header: text("staff.colRole"),
              kind: "text",
              priority: 2,
              restricted: () => roles === null,
              render: (row) => (
                <RoleCell locale={locale} row={row} roles={roles} />
              ),
            },
            {
              header: text("staff.colClubs"),
              kind: "text",
              priority: 3,
              restricted: () => roles === null,
              render: (row) => (
                <ReachCell locale={locale} row={row} roles={roles} sites={sites} />
              ),
            },
            {
              header: text("staff.colSeen"),
              kind: "text",
              priority: 2,
              render: (row) => (
                <SeenCell
                  locale={locale}
                  row={row}
                  seen={seen?.get(row.identity_id ?? "") ?? null}
                />
              ),
            },
          ]}
          state={list.staff.length === 0
            ? only === undefined
              ? { kind: "empty-first-use", explains: text("staff.emptyFirstUse") }
              : { kind: "empty-filtered", filters: [only] }
            : { kind: "ready" }}
          // **A refusal and a failure are different facts**, which is this app's own rule for
          // twenty-five gate sites and applies to a grid cell too: "not yours to see" is
          // about the reader, and a read that was permitted and did not answer is about the
          // product. A cell that said the first for the second would send somebody asking
          // for a grant they already hold.
          restrictedLabel={
            mayRoles.allowed ? text("staff.unanswered") : text("staff.restricted")}
        />
        <ProseNote>{text("staff.seenIsWhy")}</ProseNote>
      </section>

      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("staff.notYet")}</h2>
        <dl className="facts">
          <dt className="muted">{text("staff.inviteTitle")}</dt>
          <dd style={{ margin: 0 }}><Prose>{text("staff.inviteWhy")}</Prose></dd>
          <dt className="muted">{text("staff.certTitle")}</dt>
          <dd style={{ margin: 0 }}><Prose>{text("staff.certWhy")}</Prose></dd>
          <dt className="muted">{text("staff.scopeTitle")}</dt>
          <dd style={{ margin: 0 }}><Prose>{text("staff.scopeWhy")}</Prose></dd>
          <dt className="muted">{text("staff.writesTitle")}</dt>
          <dd style={{ margin: 0 }}><Prose>{text("staff.writesWhy")}</Prose></dd>
        </dl>
      </section>
    </Shell>
  );
}

/**
 * An em-dash with the reason behind it, for a cell whose question does not apply.
 *
 * Not a blank: "a column rendered empty reads as a fact about the person", which is the grid's
 * own rule and the reason `MoneyValue` has a `notApplicable` kind rather than rendering zero.
 * The mark is never alone -- a dash with nothing else is a glyph carrying meaning, which §15
 * forbids -- so the sentence is there for a screen reader and on hover.
 */
function NotApplicable({ locale }: { locale: Locale }) {
  // One sentence, once. `title` is both the hover affordance and -- with the dash hidden and
  // no other text in the cell -- the accessible name, so a visually-hidden span beside it
  // made a screen reader read the reason twice.
  return (
    <span className="muted" title={t(locale, "staff.notApplicableNoLogin")}>
      <span aria-hidden="true">—</span>
    </span>
  );
}

/** The primary role, with the count of what is beyond it. */
function RoleCell({
  locale, row, roles,
}: { locale: Locale; row: StaffRow; roles: Map<string, Assignment[]> | null }) {
  const text = (key: MessageKey) => t(locale, key);
  if (roles === null) return null;
  // **Not applicable rather than "no login" a second time.** A role is held by an identity,
  // so a person with no account has no role to show -- and the Access column already says
  // why. The first version printed "no login" here and "No login" there, which is the same
  // sentence twice in two columns answering different questions.
  if (row.identity_id === null) {
    return <NotApplicable locale={locale} />;
  }
  const { primary, beyond } = splitRole(roles.get(row.identity_id) ?? []);
  if (primary === null) return <span className="muted">{text("staff.noRole")}</span>;
  return (
    <>
      {primary.display_name ?? primary.role_key}
      {beyond.length === 0 ? null : (
        <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
          {fill(locale, "staff.plusGrants", { count: beyond.length })}
        </div>
      )}
    </>
  );
}

/**
 * Where a person's live assignments reach — not where they work.
 *
 * The staff profile's own location is in the NAME cell's second line, which is what the
 * canvas's profile header does with it ("Reception · Khalda · since Jan 2025"). This column
 * is the authority every gate decision is made against, and the two differ: a receptionist
 * based at Khalda with a tenant-wide role reaches every club.
 */
function ReachCell({
  locale, row, roles, sites,
}: {
  locale: Locale;
  row: StaffRow;
  roles: Map<string, Assignment[]> | null;
  sites: Map<string, Location> | null;
}) {
  const text = (key: MessageKey) => t(locale, key);
  if (roles === null) return null;
  // An empty cell reads as a fact about the person, which is the one thing this build's grids
  // forbid. There is no reach because there is no account.
  if (row.identity_id === null) return <NotApplicable locale={locale} />;
  const reach = reachOf(roles.get(row.identity_id) ?? []);
  if (reach.kind === "tenant") return <>{text("staff.reach.tenant")}</>;
  if (reach.kind === "none") return <span className="muted">{text("staff.reach.none")}</span>;
  const named = [
    ...reach.locations.map((id) => sites?.get(id)?.location_name ?? null),
    ...reach.brands.map(() => null),
  ];
  // A scope whose name this reader cannot resolve is counted rather than printed as an id:
  // "two sites" is a true sentence and a uuid is not a club.
  const resolved = named.filter((one): one is string => one !== null);
  const unnamed = named.length - resolved.length;
  return (
    <>
      {resolved.join(", ")}
      {unnamed > 0 ? (
        <span className="muted">
          {resolved.length > 0 ? " · " : ""}
          {fill(locale, "staff.reach.unnamed", { count: unnamed })}
        </span>
      ) : null}
    </>
  );
}

/** The standing, then the date. The sentence first, because the date alone decides nothing. */
function SeenCell({
  locale, row, seen,
}: { locale: Locale; row: StaffRow; seen: LastSeen | null }) {
  const standing = standingOf(row, seen);
  return (
    <>
      {t(locale, standingName(standing))}
      {seen?.last_seen_at == null ? null : (
        <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
          <span className="data" dir="ltr">{utcStamp(seen.last_seen_at)}</span>
        </div>
      )}
    </>
  );
}

function Shell({
  locale, children, figures,
}: { locale: Locale; children: React.ReactNode; figures?: React.ReactNode }) {
  return (
    <div className="stack">
      <PageHeader
        title={t(locale, "staff.heading")}
        {...(figures ? { figures } : {})}
      />
      {children}
    </div>
  );
}

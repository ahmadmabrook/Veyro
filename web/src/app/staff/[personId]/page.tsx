import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { PageHeader } from "@/components/ds/page-header";
import { RecordHeader } from "@/components/ds/record-header";
import { Prose, ProseNote } from "@/components/prose";
import { Withheld } from "@/components/withheld";
import { fill, t, type Locale, type MessageKey } from "@/i18n/locale";
import { currentSession, failureMessage, gateAll, gateMessage, gateVerdict } from "@/lib/api";
import { listRoles, readCatalog, simulate, type Assignment } from "@/lib/authz";
import { listLocations, type Location } from "@/lib/organization";
import { isWithheld, readPerson, withheldRemedy } from "@/lib/people";
import { numerals } from "@/lib/display";
import { presentation } from "@/lib/preferences";
import {
  NO_UNTICKED_ROWS,
  scopesToSimulate,
  readAssignments,
  readLastSeen,
  readStaffProfile,
  reachOf,
  sensitiveGrants,
  splitRole,
  standingName,
  standingOf,
  stateName,
  type LastSeen,
  type SensitiveGrant,
  type StaffProfile,
} from "@/lib/staff";
import { utcStamp } from "@/lib/time";

/**
 * ADM-STF-02 · STAFF PROFILE · TIER 4 CHANGES.
 *
 * The canvas, in full:
 *
 * > **Layla Mansour** · Reception · Khalda · since Jan 2025
 * > ROLE   `Reception ▾`
 * > CLUBS  `Khalda` `Abdoun` `Sweifieh`
 * > INDIVIDUAL GRANTS · BEYOND HER ROLE
 * > ☑ Issue refunds up to JOD 50.00 — Granted by Ziad · 4 Mar 2026
 * > ☐ Override access denials
 * > ☐ Export member data
 * > ┌ Changing any of this is **tier 4** — step-up authentication, a reason, and an audit
 * > └ entry naming both people. **You cannot grant a permission you do not hold yourself.**
 * > `[Save changes]` `[End access]`
 *
 * **The tier-4 notice is true here, which is why it is rendered rather than paraphrased.**
 * `authz.assignment.write` is `financial` class, so granting a role needs a stepped-up
 * session; `_refuse_escalation` is MOD-008's one rule applied in all three places a
 * permission can be handed out, and it is exactly "you cannot grant a permission you do not
 * hold yourself"; and MOD-008 writes `role.assigned` to the hash-chained audit log, which
 * names the grantor and the grantee. Three sentences of design copy, three mechanisms behind
 * them.
 *
 * **"BEYOND HER ROLE" needs a baseline, and this build's baseline is the role.** There are no
 * per-identity grants: a permission comes from a role and a role is held through an
 * assignment, so what is beyond somebody's role is their *additional* assignments — each of
 * which carries `granted_by` and `granted_at` by schema, which is the canvas's attribution
 * line exactly. `splitRole` decides which assignment is the job.
 *
 * **There are no unticked rows, and that is a refusal rather than an omission.** The canvas
 * draws two capabilities this person does not hold, which implies a known candidate set
 * somebody is measured against. There is none here: a permission exists if a role carries it,
 * every role is the tenant's own, and "the capabilities somebody could have" is the whole
 * two-hundred-entry catalogue. Choosing two of those as the interesting absences would be
 * inventing the product's own idea of a sensitive capability. What is rendered instead is
 * every sensitive permission this person *does* hold, from the catalogue's own `action_class`,
 * with what each costs to use — including the ones nobody in this build can exercise at all.
 *
 * **Neither button exists.** Both are stepped-up financial writes with no form in this app,
 * and "End access" is the more consequential: `revoke_assignment` takes a reason and the
 * audit entry is the only record there is.
 */

export const dynamic = "force-dynamic";

export default async function StaffProfilePage({
  params,
}: {
  params: Promise<{ personId: string }>;
}) {
  const { locale } = await presentation();
  // **The tenant's numerals** -- ADR-0015. Every quantity on this page follows
  // `localization.numerals`; an identifier does not, and neither does money. One read for the
  // whole render: `conventions()` is React's per-request memo and the layout starts it.
  const numbering = await numerals();
  const text = (key: MessageKey) => t(locale, key);
  const { personId } = await params;

  if (!(await currentSession())) redirect(`/login?next=/staff/${personId}`);

  const [mayStaff, mayRoles, mayLogins, maySites, mayNames] = await gateAll([
    "people.person.read",
    "authz.role.read",
    "identity.identity.read",
    "tenancy.organization.read",
    // For the withheld marker's remedy, not for any read. See `@/lib/mask`.
    "member.identity.read",
  ] as const);
  // **The remedy has to match the cause.** A legal name is MOD-014's `identity` class and
  // `member.identity.read` opens it; that permission is `financial`, so a step-up lifts the
  // mask for a session holding the grant at too low an assurance and does nothing for a role
  // that does not hold it. The row said "step up" to both until now. See `@/lib/mask`.
  const remedy = withheldRemedy(gateVerdict(mayNames));
  const nameWithheld: MessageKey = remedy === "step_up"
    ? "member.withheldIdentity"
    : "member.withheldIdentityNoRemedy";

  if (!mayStaff.allowed) {
    return (
      <Shell locale={locale}>
        <Banner severity="info">{text(gateMessage(mayStaff))}</Banner>
      </Shell>
    );
  }

  let profile: StaffProfile;
  try {
    profile = await readStaffProfile(personId);
  } catch (error) {
    return (
      <Shell locale={locale}>
        <Banner severity="critical">{text(failureMessage(error))}</Banner>
      </Shell>
    );
  }

  // The name is `GET /people/{id}`'s, which applies the gate's mask, this module's class mask
  // and the guardianship check. The staff read carries none, so there is one place the mask
  // has to be right.
  const person = await readPerson(personId).catch(() => null);
  const name = person === null
    ? null
    : person.preferred_name ?? person.legal_name;

  const identityId = profile.identity_id;
  const assignments: Assignment[] | null = mayRoles.allowed && identityId !== null
    ? await readAssignments([identityId])
      .then((all) => all.get(identityId) ?? [])
      .catch(() => null)
    : null;
  const seen: LastSeen | null = mayLogins.allowed && identityId !== null
    ? await readLastSeen([identityId]).then((all) => all.get(identityId) ?? null)
      .catch(() => null)
    : null;
  const sites: Map<string, Location> | null = maySites.allowed
    ? await listLocations()
      .then((all) => new Map(all.map((one) => [one.location_id, one])))
      .catch(() => null)
    : null;

  // The sensitive half needs three reads together: what this person effectively holds, what
  // the catalogue says each permission costs, and which role carries it.
  let grants: SensitiveGrant[] | null = null;
  if (mayRoles.allowed && identityId !== null && assignments !== null) {
    // **One simulation per scope the person actually holds a role at.** Asking only about the
    // tenant-wide default hides every narrowly scoped grant -- which is what "beyond their
    // role" usually is -- because a broad assignment covers a narrow scope and never the
    // reverse. The first version asked once and the fixture's own location-scoped refund
    // grant was missing from the block that exists to show it.
    const scopes = scopesToSimulate(assignments);
    const [catalog, roles, ...answers] = await Promise.all([
      readCatalog().catch(() => null),
      listRoles().catch(() => null),
      ...scopes.map((scope) => simulate(
        identityId, scope.kind === "location" ? scope.id ?? undefined : undefined,
        scope.kind === "brand" ? scope.id ?? undefined : undefined,
      ).catch(() => null)),
    ]);
    if (catalog !== null && roles !== null) {
      const heldByScope = scopes.flatMap((scope, at) => {
        const answer = answers[at];
        return answer ? [{ scope, permissions: answer.permissions }] : [];
      });
      grants = sensitiveGrants(
        heldByScope, catalog.permissions, catalog.reachable_aal, assignments, roles);
    }
  }

  const split = assignments === null ? null : splitRole(assignments);
  const reach = assignments === null ? null : reachOf(assignments);
  // **The permission, not the outcome.** A permitted read that failed leaves `seen` null and
  // `standingOf` answers `unknown` — which is the difference between telling an owner a
  // leaver has been checked and telling them nobody has.
  const standing = standingOf(
    { employment_state: profile.employment_state, identity_id: identityId }, seen);
  const state = stateName(profile.employment_state);

  return (
    // **No `PageHeader` here, and that is the record anatomy rather than an omission.** The
    // first version had both, which put two `h1`s on the page -- a page title and the
    // person's name -- and axe does not flag that while a screen reader reads two documents.
    // ADM-MEM-01's own component list opens with `Member360Header`, and `/people/{id}`
    // follows it: on a record the name *is* the title.
    <div className="stack">
      <RecordHeader
        avatar
        // **A withheld name still has to leave a heading.** The first version put only the
        // marker in the `h1`, so the one heading on the page read "Withheld" and a reader
        // arriving from a row had nothing to orient by. The job title is what identified the
        // row to them in the first place -- the name was masked there too -- so it leads, with
        // the marker beside it saying what is missing and why.
        name={
          name === null
            ? <span className="muted">{text("staff.nameUnread")}</span>
            : isWithheld(name)
              ? (
                <>
                  {profile.job_title ?? text("staff.noTitle")}{" "}
                  <Withheld locale={locale} reason={nameWithheld} />
                </>
              )
              : name
        }
        {...(profile.employment_state === "ended"
          ? { band: { text: text("staff.bandLeft"), tone: "critical" as const } }
          : profile.employment_state === "suspended"
            ? { band: { text: text("staff.bandSuspended"), tone: "warning" as const } }
            : {})}
        subline={
          <>
            {/* The job title leads the subline only when it is not already the heading --
                with the name withheld it is, and printing it twice is the sentence said
                twice, which is the rule the grid's caption learned. */}
            {name !== null && isWithheld(name)
              ? null
              : <>{profile.job_title ?? text("staff.noTitle")}{" · "}</>}
            {profile.location_name === null ? null : profile.location_name}
            {profile.started_on === null ? null : (
              <>
                {" · "}
                {fill(locale, "staff.since", { on: profile.started_on })}
              </>
            )}
            {profile.ended_on === null ? null : (
              <>
                {" · "}
                {fill(locale, "staff.until", { on: profile.ended_on })}
              </>
            )}
            {" · "}
            {state === null ? profile.employment_state : text(state)}
          </>
        }
      />

      {isWithheld(name ?? "") ? (
        <p className="ds-note">
          {remedy === "step_up" ? (
            <>
              {text("staff.nameWithheld")}{" "}
              <Link href={`/step-up?for=financial&action=member.identity.read&next=${
                encodeURIComponent(`/staff/${personId}`)}`}>
                {text("member.raiseSession")}
              </Link>
            </>
          ) : remedy === "no_answer" ? (
            text("member.namesWithheldNoAnswer")
          ) : (
            text("member.namesWithheldNotHeld")
          )}
        </p>
      ) : null}

      {/* **The access standing, which is this record's one live control.** A person whose
          employment ended and whose login still works is the finding ADM-STF-01's warning
          box leads with, and on the record it is the first thing to say. */}
      {standing === "endedWithAccess" ? (
        <Banner severity="critical">
          {text("staff.recordStillHasAccess")}
          {seen === null || seen.last_seen_at === null ? null : (
            <>
              {" "}
              <span className="data" dir="ltr">{utcStamp(seen.last_seen_at)}</span>
            </>
          )}
        </Banner>
      ) : null}

      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("staff.accessTitle")}</h2>
        <dl className="facts">
          <dt className="muted">{text("staff.colRole")}</dt>
          <dd style={{ margin: 0 }}>
            {assignments === null ? (
              <span className="muted">{text(gateMessage(mayRoles))}</span>
            ) : identityId === null ? (
              <span className="muted">{text("staff.noLogin")}</span>
            ) : split?.primary == null ? (
              <span className="muted">{text("staff.noRole")}</span>
            ) : (
              // The display name alone. Printing `role_key` beside it renders the stored
              // value next to its own label -- the mistake this repository made four times in
              // one pass, and here it put `publisher_1795251559775` on screen.
              <>{split.primary.display_name ?? split.primary.role_key}</>
            )}
          </dd>

          <dt className="muted">{text("staff.colClubs")}</dt>
          <dd style={{ margin: 0 }}>
            {reach === null ? (
              <span className="muted">{text(gateMessage(mayRoles))}</span>
            ) : reach.kind === "tenant" ? (
              text("staff.reach.tenant")
            ) : reach.kind === "none" ? (
              <span className="muted">{text("staff.reach.none")}</span>
            ) : (
              <>
                {reach.locations.map((id) => sites?.get(id)?.location_name ?? null)
                  .filter((one): one is string => one !== null).join(", ")}
                {reach.brands.length > 0 ? (
                  <span className="muted">
                    {" "}
                    {fill(locale, "staff.reach.brands", { count: reach.brands.length }, numbering)}
                  </span>
                ) : null}
              </>
            )}
            <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
              {text("staff.reachIsNotHome")}
            </div>
          </dd>

          <dt className="muted">{text("staff.colSeen")}</dt>
          <dd style={{ margin: 0 }}>
            {text(standingName(standing))}
            {seen?.last_seen_at == null ? null : (
              <>
                {" · "}
                <span className="data" dir="ltr">{utcStamp(seen.last_seen_at)}</span>
              </>
            )}
          </dd>
        </dl>
      </section>

      {/* **The canvas's grants block.** The additional assignments first, because those are
          literally "beyond her role" and carry the attribution the canvas draws. */}
      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("staff.beyondTitle")}</h2>
        {split === null ? (
          <Banner severity="info">{text(gateMessage(mayRoles))}</Banner>
        ) : split.beyond.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>{text("staff.beyondNone")}</p>
        ) : (
          <ul className="ds-evidence">
            {split.beyond.map((one) => (
              <li key={one.assignment_id} data-state="have">
                <span className="ds-evidence-mark" aria-hidden="true">☑</span>
                <span className="ds-evidence-what">
                  {one.display_name ?? one.role_key}
                  <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
                    {/* **Who granted it is recorded and not named here.** This printed
                        eight characters of the grantor's identity uuid, which is an
                        identifier rather than a person: the id is on the authorization
                        plane and naming it needs a people read keyed by identity, which no
                        route on this page makes. The date is the half this page can answer
                        honestly. */}
                    {fill(locale, "staff.grantedOn", { on: one.granted_at.slice(0, 10) })}
                    {one.expires_at === null ? null : (
                      <>
                        {" · "}
                        {fill(locale, "staff.expires", { on: one.expires_at.slice(0, 10) })}
                      </>
                    )}
                  </div>
                </span>
                <span className="ds-visually-hidden">{text("dispute.state.have")}</span>
              </li>
            ))}
          </ul>
        )}
        {split !== null && split.lapsed.length > 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            {fill(locale, "staff.lapsed", { count: split.lapsed.length }, numbering)}
          </p>
        ) : null}
        <ProseNote>{text("staff.attributionIsAnId")}</ProseNote>
      </section>

      <section className="page-section">
        <h2 id="staff-sensitive" style={{ margin: 0 }}>{text("staff.sensitiveTitle")}</h2>
        {grants === null ? (
          <Banner severity="info">{text(gateMessage(mayRoles))}</Banner>
        ) : grants.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>{text("staff.sensitiveNone")}</p>
        ) : (
          <ul className="ds-evidence">
            {grants.map((grant) => (
              <li
                key={grant.permission.name}
                data-state={grant.reach === "unreachable" ? "refused" : "have"}
              >
                <span className="ds-evidence-mark" aria-hidden="true">
                  {grant.reach === "unreachable" ? "☐" : "☑"}
                </span>
                <span className="ds-evidence-what">
                  {grant.permission.description}
                  <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
                    <span className="data" dir="ltr">{grant.permission.name}</span>
                    {" · "}
                    {text(`staff.grant.${grant.reach}` as MessageKey)}
                    {grant.carriers.length === 0 ? null : (
                      <>
                        {" · "}
                        {fill(locale, "staff.viaRole", {
                          role: grant.carriers
                            .map((one) => one.display_name ?? one.role_key).join(", "),
                        })}
                      </>
                    )}
                    {" · "}
                    {grant.scopes.some((one) => one.kind === "tenant")
                      ? text("staff.grantEverywhere")
                      : fill(locale, "staff.grantAt", {
                        where: grant.scopes
                          // A club the sites read did not cover is named as that rather
                          // than as its id: a reader can act on "a club this page cannot
                          // name" and cannot act on eight hex characters.
                          .map((one) => (one.id === null ? null
                            : sites?.get(one.id)?.location_name ?? t(locale, "staff.siteNotNamed")))
                          .filter((one): one is string => one !== null).join(", "),
                      })}
                  </div>
                </span>
                <span className="ds-visually-hidden">
                  {text(grant.reach === "unreachable"
                    ? "staff.srUnreachable" : "staff.srHeld")}
                </span>
              </li>
            ))}
          </ul>
        )}
        <ProseNote>{text(NO_UNTICKED_ROWS)}</ProseNote>
        {grants !== null && grants.length > 0 ? (
          <ProseNote>{text("staff.catalogueIsEnglish")}</ProseNote>
        ) : null}
        {grants?.some((one) => one.reach === "unreachable") ? (
          <ProseNote>{text("staff.aal3Unreachable")}</ProseNote>
        ) : null}
      </section>

      {/* The canvas's red notice, rendered because all three of its claims are true here. */}
      <Banner severity="critical">
        {text("staff.tierFour")} <strong>{text("staff.cannotGrantWhatYouLack")}</strong>
      </Banner>

      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("staff.notYet")}</h2>
        <dl className="facts">
          <dt className="muted">{text("staff.saveTitle")}</dt>
          <dd style={{ margin: 0 }}><Prose>{text("staff.saveWhy")}</Prose></dd>
          <dt className="muted">{text("staff.endTitle")}</dt>
          <dd style={{ margin: 0 }}><Prose>{text("staff.endWhy")}</Prose></dd>
        </dl>
        <p style={{ margin: 0 }}>
          <Link href={`/people/${personId}`}>{text("staff.openRecord")}</Link>
        </p>
      </section>
    </div>
  );
}

function Shell({
  locale, children,
}: { locale: Locale; children: React.ReactNode }) {
  return (
    <div className="stack">
      <PageHeader title={t(locale, "staff.profileHeading")} />
      {children}
    </div>
  );
}

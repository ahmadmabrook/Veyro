import Link from "next/link";

import { Banner } from "@/components/ds/banner";
import { Withheld } from "@/components/withheld";
import { DataGrid } from "@/components/ds/data-grid";
import { formatInteger, t, type MessageKey } from "@/i18n/locale";
import { ApiError, gate } from "@/lib/api";
import {
  LIFECYCLE_STATES,
  UNANSWERABLE,
  isLifecycleState,
  membershipsByPerson,
  stateCounts,
  type MembersPage,
  type MembershipRow,
} from "@/lib/members";
import { listMembers, listMemberships } from "@/lib/members-reads";
import { isWithheld } from "@/lib/people";
import { planName, stateName } from "@/lib/members";
import { presentation } from "@/lib/preferences";

/**
 * ADM-MEM-05 · MEMBERS LIST · CM, RECEP · COMPACT · 1440.
 *
 * **The first screen in this app built from its design rather than from a module's routes.**
 * The specification is in `src/design/screens.generated.json`, extracted from
 * `veyro-product-experience-design/` and pinned by digest, and it is specific: seven columns,
 * a search field, three quick filters with counts, a saved-view control, a bounded bulk
 * selection, an export behind an approval, 12 skeleton rows at 34px while loading, and a
 * scale rule — "There is no state where 4,812 rows render."
 *
 * What is built is what this product can answer, and the rest is **named rather than drawn**:
 *
 * - **MEMBER and STATE** are MOD-014's own, and come from `GET /people` — masked like every
 *   other read in that module, so a routine session sees `***` where the legal name is rather
 *   than a blank.
 * - **PLAN and RENEWS** are MOD-017's, composed from its own list route and indexed by person.
 *   One extra request for the page, not one per row: paragraph 1300 bars a cross-domain join,
 *   not a surface that asks twice, which is what the Member 360 already does.
 * - **CLUB, BALANCE and LAST VISIT** have no read in this build. They are listed under "what
 *   this screen does not do yet" rather than rendered as empty columns, because an empty cell
 *   reads as a fact about the member.
 * - **The search field, the quick filters, the saved views, the bulk bar and the export** are
 *   absent for the same reason, each with the product's own reason beside it. A control that
 *   does nothing is worse than one that is not there.
 *
 * **Compact density**, which the design states and which this app could not express until the
 * density modes were generated: 34px rows, the spacing scale one step down, the body type one
 * step down.
 */
export default async function MembersPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);
  const params = await searchParams;
  const wanted = typeof params.state === "string" ? params.state : undefined;
  const lifecycleState = isLifecycleState(wanted) ? wanted : undefined;

  const [mayPeople, mayMemberships] = await Promise.all([
    gate("people.person.read"),
    gate("membership.record.read"),
  ]);

  if (!mayPeople.allowed) {
    return (
      <Shell locale={locale}>
        <Banner severity="info">
          {mayPeople.reachable ? text("gate.denied") : text("gate.unreachable")}
        </Banner>
      </Shell>
    );
  }

  let page: MembersPage | null = null;
  let memberships: MembershipRow[] = [];
  let failed = false;
  try {
    // **Two reads, in parallel, and the second one is optional.** A reader who may see people
    // and not memberships gets the table without PLAN and RENEWS rather than a refusal: the
    // design's own restricted state is "a receptionist sees the table without the balance
    // column and without Export", which is the same shape.
    const [people, held] = await Promise.all([
      listMembers({ ...(lifecycleState ? { lifecycleState } : {}) }),
      mayMemberships.allowed
        ? listMemberships().catch(() => ({ memberships: [] }))
        : Promise.resolve({ memberships: [] }),
    ]);
    page = people;
    memberships = held.memberships;
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    failed = true;
  }

  if (failed || page === null) {
    return (
      <Shell locale={locale}>
        <Banner severity="critical">{text("error.unexpected")}</Banner>
      </Shell>
    );
  }

  const held = membershipsByPerson(memberships);
  const counts = stateCounts(page.by_state);

  return (
    <Shell locale={locale}>
      <section className="ds-page-section">
        <h2 id="members-heading" className="ds-visually-hidden">{text("members.title")}</h2>

        {/* **The design's own sub-line**: "4,812 active · 312 expired · 68 frozen · all
            locations". Counted over the tenant rather than over the loaded page -- the first
            version summed the fifty rows on screen and captioned the fact, which was honest
            and was still the wrong number in the place a manager reads the business. */}
        <p className="muted" style={{ margin: 0 }}>
          {counts.length === 0
            ? "\u2014"
            : counts.map(({ state, count }, index) => (
                <span key={state}>
                  {index > 0 ? " \u00b7 " : ""}
                  <span className="data">{formatInteger(count, "latn")}</span>{" "}
                  {state === "none"
                    ? text("members.noProfile")
                    : stateName(state) === null
                      ? state
                      : text(stateName(state) as MessageKey)}
                </span>
              ))}
          {" \u00b7 "}
          {text("members.scope")}
        </p>

        {/* The one filter this screen can really apply, because MOD-014 owns the state. It is
            a set of links rather than a form: a filter that works without JavaScript is the
            same decision the sign-in form makes, and the state belongs in the URL so a
            filtered list can be sent to somebody. */}
        <nav aria-label={text("members.filter")} className="ds-filter-bar">
          <FilterLink locale={locale} state={undefined} current={lifecycleState} />
          {LIFECYCLE_STATES.map((state) => (
            <FilterLink key={state} locale={locale} state={state} current={lifecycleState} />
          ))}
        </nav>

        {/* **A list of withheld names needs the remedy on the list.** Every row here is
            marked when the session cannot read identity fields, and the member *record*
            offers the step-up that lifts it -- so a reader on this page saw "Name withheld"
            against every member with nothing to act on, and had to open one record to find
            out there was a way. Found by an independent tester, who clicked the marker
            looking for one. The offer is the same link the record makes, with this page as
            the destination, and it is shown only when something is actually withheld. */}
        {page.people.some((row) => isWithheld(row.preferred_name ?? row.legal_name)) ? (
          <p className="ds-note">
            {text("members.namesWithheld")}{" "}
            <Link
              href={`/step-up?for=financial&action=member.identity.read&next=${
                encodeURIComponent("/members")}`}
            >
              {text("member.raiseSession")}
            </Link>
          </p>
        ) : null}

        {page.people.length === 0 ? (
          // "Empty search names the query and offers to clear filters, never 'no data'."
          <Banner severity="info">
            {lifecycleState ? text("members.empty") : text("members.emptyUnfiltered")}
          </Banner>
        ) : (
          <DataGrid
            caption={text("members.title")}
            labelledBy="members-heading"
            rows={page.people}
            rowKey={(row) => row.person_id}
            columns={[
              {
                header: text("members.member"),
                kind: "person",
                priority: 1,
                render: (row) => (
                  <>
                    {/* **A masked name is marked, not printed as `***`.** `MASK` is a value
                        MOD-014 returns at every depth, and a cell that rendered it raw would
                        show three asterisks where the member record shows a marked, explained
                        withholding -- the same fact, rendered as a glitch. The remedy differs
                        by reason, so the marker names which one it is. */}
                    {isWithheld(row.preferred_name ?? row.legal_name) ? (
                      <Withheld locale={locale} reason="member.withheldIdentity" />
                    ) : (
                      <Link href={`/people/${row.person_id}`}>
                        {row.preferred_name ?? row.legal_name}
                      </Link>
                    )}
                    <div className="muted" style={caption}>
                      {row.member_number === null ? (
                        text("members.noNumber")
                      ) : (
                        <span className="data" dir="ltr">{row.member_number}</span>
                      )}
                    </div>
                  </>
                ),
              },
              {
                header: text("members.state"),
                kind: "status",
                priority: 1,
                render: (row) => {
                  if (row.lifecycle_state === null) {
                    return <span className="muted">{text("members.noProfile")}</span>;
                  }
                  const named = stateName(row.lifecycle_state);
                  // A state the vocabulary does not know is shown as stored rather than as
                  // "other": this is the screen that filters by it.
                  return named ? text(named) : (
                    <span className="data" dir="ltr">{row.lifecycle_state}</span>
                  );
                },
              },
              {
                header: text("members.plan"),
                kind: "text",
                priority: 2,
                // The membership read is its own gate. A reader who holds the person read and
                // not the membership read is told the cell is withheld rather than shown an
                // empty one -- which is the restricted state the design names.
                restricted: () => !mayMemberships.allowed,
                render: (row) => {
                  const membership = held.get(row.person_id);
                  return membership === undefined ? (
                    <span className="muted">{text("members.noMembership")}</span>
                  ) : (
                    <>
                      {/* **Three more stored values that were rendered as labels.** Kind,
                          period and status are MOD-017's vocabulary, and printing them raw
                          put `recurring`, `monthly` and `active` in Latin letters in the
                          middle of an Arabic page -- the same defect as the lifecycle state
                          two columns over, found in the same look. */}
                      {planWord(membership.membership_kind, locale)}
                      <div className="muted" style={caption}>
                        {planWord(membership.billing_period, locale)}
                        {" \u00b7 "}
                        {planWord(membership.status, locale)}
                      </div>
                    </>
                  );
                },
              },
              {
                header: text("members.renews"),
                kind: "date",
                priority: 2,
                restricted: () => !mayMemberships.allowed,
                render: (row) => {
                  const membership = held.get(row.person_id);
                  const renews = membership?.current_period_end ?? null;
                  return renews === null ? (
                    <span className="muted">—</span>
                  ) : (
                    <span className="data" dir="ltr">{renews}</span>
                  );
                },
              },
              {
                header: text("members.joined"),
                kind: "date",
                priority: 3,
                render: (row) =>
                  row.joined_on === null ? (
                    <span className="muted">—</span>
                  ) : (
                    <span className="data" dir="ltr">{row.joined_on}</span>
                  ),
              },
            ]}
          />
        )}

        {/* "Showing 1-50 of 18 matching · 4,812 total" -- the design's own footer, and the
            difference between the two numbers is the point: a filtered list that reported
            only its own length would imply the records that did not match do not exist. */}
        <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
          {text("members.showing")}{" "}
          <span className="data">{formatInteger(page.people.length, "latn")}</span>{" "}
          {text("members.ofTotal")}{" "}
          <span className="data">{formatInteger(page.matching, "latn")}</span>{" "}
          {text("members.matching")}
          {" · "}
          <span className="data">{formatInteger(page.total, "latn")}</span>{" "}
          {text("members.totalLabel")}
        </p>
      </section>

      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("members.cannotYet")}</h2>
        <p className="muted" style={{ margin: 0 }}>{text("members.cannotLead")}</p>
        <dl className="facts">
          {/* **The server's own sentence is in the data and the reader gets the catalogue's.**
              `search_is_not_available_because` is the authority for *what* the gap is, and it
              is English by construction -- rendering it put an English paragraph under an
              Arabic heading. The key says the same thing in the reader's language. */}
          <Gap locale={locale} label="members.noSearch" why={UNANSWERABLE.search} />
          <Gap locale={locale} label="members.noQuickFilters" why={UNANSWERABLE.quickFilters} />
          <Gap locale={locale} label="members.missingColumns" why={UNANSWERABLE.columns} />
          <Gap locale={locale} label="members.noSavedViews" why={UNANSWERABLE.savedViews} />
          <Gap locale={locale} label="members.noBulk" why={UNANSWERABLE.bulkActions} />
          <Gap locale={locale} label="members.noExport" why={UNANSWERABLE.export} />
        </dl>
      </section>
    </Shell>
  );
}

function Gap({
  locale,
  label,
  why,
}: {
  locale: "en" | "ar";
  label: MessageKey;
  why: MessageKey;
}) {
  return (
    <>
      <dt className="muted">{t(locale, label)}</dt>
      <dd style={{ margin: 0 }}>{t(locale, why)}</dd>
    </>
  );
}

/**
 * A stored membership word, in the reader's language, or as stored when it is unknown.
 *
 * The same judgement as `stateName`: MOD-017's vocabulary may grow, and a word this app
 * does not recognise is shown rather than hidden behind "other".
 */
function planWord(stored: string, locale: "en" | "ar"): string {
  const key = planName(stored);
  return key === null ? stored : t(locale, key);
}

function FilterLink({
  locale,
  state,
  current,
}: {
  locale: "en" | "ar";
  state: string | undefined;
  current: string | undefined;
}) {
  const here = state === current;
  return (
    <Link
      href={state ? `/members?state=${state}` : "/members"}
      aria-current={here ? "page" : undefined}
      className="ds-filter-chip"
    >
      {state === undefined
        ? t(locale, "members.all")
        : stateName(state) === null
          ? state
          : t(locale, stateName(state) as MessageKey)}
    </Link>
  );
}

function Shell({
  locale,
  children,
}: {
  locale: "en" | "ar";
  children: React.ReactNode;
}) {
  // **Compact density, which the design states for this screen.** `data-density` redefines
  // the row height, the spacing step and the body type step and nothing else -- colour,
  // radius, anatomy and hierarchy are invariant, which is what makes a density a density
  // rather than a fifth theme.
  // **No explanatory lead.** The design's header is a title and a sub-line of figures; a
  // paragraph describing what the screen is belongs in this file's own comments, not above
  // the data. What the screen *cannot* do is still stated, at the bottom, where it answers a
  // question rather than delaying one.
  return (
    <div className="stack" data-density="compact">
      <div className="ds-page-head">
        <div className="ds-page-head-text">
          <h1 style={{ margin: 0 }}>{t(locale, "members.title")}</h1>
        </div>
      </div>
      {children}
    </div>
  );
}

const caption: React.CSSProperties = { fontSize: "var(--type-caption-size)" };

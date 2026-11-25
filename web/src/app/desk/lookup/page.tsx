import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { Field } from "@/components/ds/field";
import { NotYet, PageHeader } from "@/components/ds/page-header";
import { WithheldLink } from "@/components/withheld";
import { withheldRemedy } from "@/lib/mask";
import { fill, t, type MessageKey } from "@/i18n/locale";
import {
  currentSession, gate, gateAll, gateMessage, gateVerdict,
} from "@/lib/api";
import {
  checksFor, confirmable, metaParts, stateOf, type Lookup, type Match,
} from "@/lib/lookup";
import { readLookup } from "@/lib/lookup-reads";
import { listLocations } from "@/lib/organization";
import { numerals } from "@/lib/display";
import { presentation } from "@/lib/preferences";

/**
 * FD-02 · MEMBER LOOKUP.
 *
 * "Search by name, phone or partial. Results show photo, plan, club and state so the
 * receptionist confirms identity visually before acting. Ambiguous matches list side by side
 * rather than guessing. No-match offers guest entry or lead capture."
 *
 * **A form rather than a live fetch, and "SCAN OR TYPE" is the argument.** A barcode scanner
 * emits characters and an Enter, which is a submit — so the ordinary path through this screen
 * is a form, it works with JavaScript disabled for the reason the sign-in does, and there is
 * no debounce to get wrong. ADM-MEM-10 checks as a phone is typed because it is *interrupting*
 * somebody mid-form; this screen is the whole task.
 *
 * **A lookup, not a search** — ADR-0012. Paragraph 4218's permission-aware search index is
 * ENG-01's, and MOD-014's own gap list sends it there; what this reads is one entity inside one
 * tenant under forced RLS, from the table of record, bounded and masked.
 *
 * **The photo the canvas confirms identity by does not exist**, and that changes the sentence
 * rather than only the layout. "Check the photo before you let them through" cannot be said, a
 * 44px grey circle would read as a photo missing from the *record* rather than from the
 * product, and the check that is left is the one the canvas's own footnote calls the second:
 * "partial phone digits … because two members can share a name but not a number".
 */
export default async function LookupPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);
  // **The tenant's numerals rather than a constant** -- ADR-0015. Every count, date and time
  // on this page follows `localization.numerals`; money does not, and `MoneyValue` carries no
  // `numbering` prop at all so that exception is the component's rule rather than this page's
  // to remember. One read for the whole render: `conventions()` is React's per-request memo
  // and the layout starts it, so this costs no round trip of its own.
  const numbering = await numerals();
  const typed = (await searchParams).q ?? "";

  if (!(await currentSession())) redirect("/login");

  // **Batched, because two asks is two round trips** and `/authz/checks` exists for it.
  // `member.identity.read` is not for the read -- it is what says whether a withheld name's
  // remedy is a step-up or whether this role does not include identity fields at all.
  const [read, mayNames] = await gateAll([
    "people.person.read", "member.identity.read",
  ] as const);
  const nameWithheld: MessageKey = withheldRemedy(gateVerdict(mayNames)) === "step_up"
    ? "member.withheldIdentity"
    : "member.withheldIdentityNoRemedy";
  if (!read.allowed) {
    return (
      <>
        <PageHeader title={text("lookup.heading")} />
        <Banner severity="attention" title={text(gateMessage(read))}>
          {text("lookup.needsRead")}
          {gateVerdict(read) === "needs_step_up" ? (
            <>
              {" "}
              <Link href={
                "/step-up?for=financial&action=people.person.read&next=/desk/lookup"
              }>
                {text("member.raiseSession")}
              </Link>
            </>
          ) : null}
        </Banner>
      </>
    );
  }

  // **Refused rather than requested below two characters**, which is the server's rule and is
  // asked here so the field keeps what somebody typed instead of showing them a 422.
  const asked = typed.trim();
  const found: Lookup | null = asked.length >= 2
    ? await readLookup(asked, 10).catch(() => null)
    : null;
  const state = stateOf(typed, found);

  // **One hierarchy read for every match, not one each.** `location_id` is on the lookup row
  // and the club is its name; a request per match is the round-trip problem the staff list
  // paid for, and the plan is already three requests away (see `lookup-reads`).
  const maySites = await gate("tenancy.organization.read");
  const sites = maySites.allowed && found !== null && found.count > 0
    ? await listLocations().catch(() => [])
    : [];
  const clubOf = (match: Match): string | null => {
    if (match.location_id === null) return null;
    return sites.find((one) => one.location_id === match.location_id)
      ?.location_name ?? null;
  };

  return (
    <>
      <PageHeader title={text("lookup.heading")} figures={text("lookup.lead")} />

      {/* The canvas's field: one input, a submit, and a scanner's Enter does the same thing. */}
      <form method="get" action="/desk/lookup" className="ds-cash-form">
        <Field
          id="lookup-q" name="q" type="search"
          label={text("lookup.scanOrType")}
          defaultValue={typed}
          optionalLabel={text("field.optional")}
          message={state.kind === "tooShort"
            ? { kind: "error", text: text("lookup.tooShort") }
            : null}
        />
        <Button type="submit" variant="primary" size="lg"
          label={text("lookup.find")} />
      </form>

      {state.kind === "resting" ? (
        <p className="muted">{text("lookup.resting")}</p>
      ) : state.kind === "tooShort" ? (
        <p className="muted">{text("lookup.tooShortWhy")}</p>
      ) : state.kind === "none" ? (
        <NoMatch typed={state.typed} locale={locale} />
      ) : (
        <>
          {/* **The canvas's sentence, with the check it names replaced by the one that
              exists.** "Two members match. Check the photo before you let them through" --
              and there is no photo, so what a desk can check is the last four digits. */}
          <p data-testid="match-count">
            {state.kind === "several"
              ? fill(locale, "lookup.severalMatch", { count: state.count }, numbering)
              : text("lookup.oneMatch")}
            {" "}
            {text("lookup.checkTheDigits")}
          </p>

          <ul className="ds-desk-rows">
            {found?.people.map((match) => (
              <MatchRow key={match.person_id} match={match} nameWithheld={nameWithheld}
                club={clubOf(match)} locale={locale} />
            ))}
          </ul>

          {found?.more ? (
            <p className="muted">{text("lookup.more")}</p>
          ) : null}

          <NoMatch typed={state.typed} locale={locale} alsoNeither />
        </>
      )}

      <NotYet title={text("lookup.notYet")}>
        <dt>{text("lookup.gapPhoto")}</dt>
        <dd>{text("lookup.gapPhotoWhy")}</dd>
        <dt>{text("lookup.gapLetIn")}</dt>
        <dd>{text("lookup.gapLetInWhy")}</dd>
        <dt>{text("lookup.gapPlan")}</dt>
        <dd>{text("lookup.gapPlanWhy")}</dd>
        <dt>{text("lookup.gapPartialPhone")}</dt>
        <dd>{text("lookup.gapPartialPhoneWhy")}</dd>
      </NotYet>
    </>
  );
}

/** One match: who they are, what a desk can check them by, and their record. */
function MatchRow({
  match, club, locale, nameWithheld,
}: {
  match: Match;
  club: string | null;
  locale: Parameters<typeof t>[0];
  // Which sentence a withheld name gets: the page decides it from the gate's answer, because
  // only the page knows whether a step-up would lift the mask for this reader.
  nameWithheld: MessageKey;
}) {
  const text = (key: MessageKey) => t(locale, key);
  // The plan is null on purpose: it costs three requests per match, which `lookup-reads`
  // records. The club and the digits are what this row can say.
  const checks = checksFor(match);
  const parts = metaParts(match, { plan: null, club });

  return (
    <li className="ds-desk-row" data-testid="match">
      <div className="ds-desk-row-name">
        {/* **The record is what a lookup is for, and a withheld name is still a link.** The
            members list and the staff list were both dead ends until `WithheldLink` put the
            marker *inside* the link -- found by an outside tester twice, on the front desk's
            own credential, where every identity field is masked. */}
        {checks.name ? (
          <Link href={`/people/${match.person_id}`}>
            {match.preferred_name ?? match.legal_name}
          </Link>
        ) : (
          <WithheldLink
            locale={locale} reason={nameWithheld}
            href={`/people/${match.person_id}`}
            label={fill(locale, "lookup.openWithheld", {
              what: match.phone !== null && checks.digits
                ? `···${match.phone}`
                : text("lookup.noDigitsShort"),
            })}
          />
        )}
        <span className="muted ds-desk-row-context data" dir="ltr">
          {parts.length > 0 ? parts.join(" · ") : text("lookup.nothingToShow")}
        </span>
      </div>
      {!confirmable(match) ? (
        <span className="ds-desk-row-state">
          {text("lookup.cannotConfirm")}
        </span>
      ) : !checks.digits ? (
        <span className="ds-desk-row-state">
          {text("lookup.noDigits")}
        </span>
      ) : null}
    </li>
  );
}

/**
 * "Neither" — and one of the two things the registry line offers is built.
 *
 * "No-match offers guest entry or lead capture." Guest entry is FD-04, which takes a payment
 * at the door and is the first external blocker; lead capture is FD-05, which exists. So the
 * link is real and the absence is named rather than both being drawn as buttons.
 */
function NoMatch({
  typed, locale, alsoNeither = false,
}: {
  typed: string;
  locale: Parameters<typeof t>[0];
  alsoNeither?: boolean;
}) {
  const text = (key: MessageKey) => t(locale, key);
  return (
    <section data-testid="no-match">
      <p style={{ margin: 0 }}>
        {alsoNeither
          ? text("lookup.neither")
          : fill(locale, "lookup.nobodyMatches", { typed })}
      </p>
      <p className="ds-walk-in-actions">
        <Link href="/desk/trial" className="ds-filter-chip">
          {text("lookup.startATrial")}
        </Link>
      </p>
      <p className="muted" style={{ margin: 0 }}>{text("lookup.noGuestEntry")}</p>
    </section>
  );
}

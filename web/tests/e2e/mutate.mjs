#!/usr/bin/env node
/**
 * Break one protection at a time and check that the suite notices.
 *
 * **A test that still passes when you remove the thing it guards is not evidence.** That is the
 * backend's rule (`.claude/rules/backend/mod004-rls.md`) and there is no reason the browser half
 * should be held to a weaker one -- the web suite is newer, has no mutation history, and three
 * of its first thirty assertions failed for reasons that had nothing to do with the product.
 *
 * Each mutation edits a source file, runs only the test that names that protection, and expects
 * a FAILURE. A mutation whose test still passes is reported as a gap. The file is restored
 * afterwards whatever happens, including on a crash **and on a signal** -- the `finally` does
 * not run when the process is killed, and a sweep stopped halfway left a deleted line in
 * `access/[zoneId]/page.tsx` for an hour. What made it expensive to find is that the mutation
 * whose `to` is the empty string is a *deletion*, so searching the tree for the mutated text
 * cannot detect it: the next run of that one mutation reported "the anchor appears 0 times",
 * which is the only trace there was.
 *
 *   node tests/e2e/mutate.mjs            # all of them
 *   node tests/e2e/mutate.mjs focus      # only mutations whose id contains "focus"
 *
 * Needs the web app and the backend running, and `web/.env.e2e.local`.
 */

import { spawnSync } from "node:child_process";
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

/**
 * `file` is relative to `web/`. `from` must appear exactly once -- a mutation that matched
 * nothing, or matched twice, is reported rather than run, because "the statement did not apply"
 * recorded as a catch is the false green this whole exercise exists to prevent.
 *
 * `runner` is `"playwright"` unless stated. `"vitest"` is for a protection whose test is a
 * component test rather than a browser one -- the device-label parity, where the whole point
 * of the test is that it needs no browser and no fixture. `"node"` is the foundation layer,
 * `tests/unit/`, which runs on Node's own test runner: it had no runner here until a
 * mutation was pointed at one of its assertions and came back uncaught, because `vitest`
 * does not collect those files and so reported no failure rather than no test.
 */
const MUTATIONS = [
  // ------------------------------------------------- ADM-SCH-05, schedule PT (ADR-0019)
  {
    id: "pt-the-two-refusals-are-not-merged",
    why: "\"sell a package first\" and \"pick another hour\" are different remedies, so a"
      + " screen that said one for both would send a desk to the wrong one. The canvas draws"
      + " the zero-credit state explicitly and the busy coach is a separate fact",
    file: "src/lib/personal-session.ts",
    from: "  if (quote.needs_a_package && !quote.coach_is_free) return \"bothInTheWay\";\n"
      + "  if (quote.needs_a_package) return \"needsPackage\";",
    to: "  if (quote.needs_a_package) return \"coachBusy\";",
    // **The component runner, because the browser cannot see this one.** The two banners are
    // rendered from `needs_a_package` and `coach_is_free` directly -- deliberately, since a
    // screen deriving them from the summary state would lose the case where both are in the
    // way -- so the derived state's only reader is the button, whose own mutation is caught
    // below. A browser mutation against it came back uncaught, which is "the case exists and
    // the layer is wrong" rather than a redundant guard.
    runner: "vitest",
    grep: "the canvas's two refusals",
  },
  {
    id: "pt-the-answer-carries-the-proposal-it-was-about",
    why: "a quote is an answer about one coach at one hour, so an answer left over from a"
      + " previous choice is a figure a desk would act on -- ADM-SCH-07's own derivation,"
      + " and the reason the state carries its key rather than a separate 'have we asked'",
    file: "src/app/schedule/pt/book-form.tsx",
    from: "  const live = quote !== null && quote.for === proposal ? quote.answer : null;",
    to: "  const live = quote !== null ? quote.answer : null;",
    grep: "forgets an answer once the choice is no longer complete",
  },
  {
    id: "pt-the-button-is-held-until-both-halves-answer",
    why: "the canvas's button says what it costs, and offering it over a refusal the command"
      + " would make by name is worse than its absence -- FD-06's rule",
    file: "src/app/schedule/pt/book-form.tsx",
    from: "          state={pending || !mayBook || where !== \"ready\" ? \"disabled\" : \"default\"}",
    to: "          state={pending ? \"disabled\" : \"default\"}",
    grep: "a busy coach is a different sentence from a missing credit",
  },
  {
    id: "pt-a-personal-session-is-marked-apart-from-a-class",
    why: "the canvas draws PT against CLS on the coach's week and this build had one state"
      + " for both until 0036 -- the gap note that said so is deleted, and the sixth cell"
      + " state is what replaced it",
    file: "src/lib/rota.ts",
    from: "    return here.every((one) => one.session_kind === \"personal\")\n"
      + "      ? \"bookedPersonal\"\n      : \"booked\";",
    to: "    return \"booked\";",
    runner: "vitest",
    grep: "tells a personal session from a class",
  },
  {
    id: "pt-an-hour-is-read-in-the-clubs-own-zone",
    why: "the schedule board showed 15:00 under a heading promising Asia/Amman and four"
      + " layers of tests did not notice; a confirmation naming the wrong hour is the same"
      + " defect on the screen that books it",
    file: "src/lib/personal-session.ts",
    from: "    timeZone: timezone, numberingSystem: \"latn\",",
    to: "    numberingSystem: \"latn\",",
    runner: "vitest",
    grep: "renders the local wall clock rather than the instant",
  },
  {
    id: "pt-the-way-in-is-on-the-members-own-credits",
    why: "a route nothing links to is a route nobody finds, which ADM-MEM-05's missing Add"
      + " member and /rota's stale gap note each cost this app once -- and the credits table"
      + " is where a desk already is",
    file: "src/components/membership-panels.tsx",
    from: "      {page.grants.some((grant) => grant.entitlement_type === \"service_credit\") ? (",
    to: "      {false ? (",
    grep: "is reached from the member's own credits",
  },
  // ------------------------------------------------- ADM-SCH-06, rooms and resources
  {
    id: "rooms-an-unstated-capacity-is-not-zero",
    why: "a room nobody has described does not bind a class, and 'holds 0' is a different"
      + " fact -- the one a reader would act on. ADR-0018 D1, and the distinction the whole"
      + " middle column rests on",
    file: "src/app/schedule/resources/page.tsx",
    from: "                row.capacity === null ? (",
    to: "                false ? (",
    grep: "tells an unstated capacity from a room that holds nobody",
  },
  {
    id: "rooms-the-equipment-column-counts-bikes-not-rows",
    why: "twenty bikes are one row with a quantity of twenty, deliberately -- so a column"
      + " rendering the row count would say '1' about a room holding twenty",
    file: "src/lib/rooms.ts",
    from: "  return resource.contains.map((one) => `${one.quantity} × ${one.resource_code}`);",
    to: "  return resource.contains.map((one) => one.resource_code);",
    grep: "states what the spin room holds, and what is in it",
  },
  {
    id: "rooms-only-spaces-are-listed",
    why: "only a place holds people or contains equipment, so a table listing the coach and"
      + " the service would be three columns two of which are blank for most rows",
    file: "src/lib/rooms.ts",
    from: "  return (SPACE_KINDS as readonly string[]).includes(resource.resource_kind);",
    to: "  return true;",
    grep: "lists only spaces, because only a place holds people",
  },
  {
    id: "rooms-the-way-in-is-on-the-schedule-board",
    why: "'double-booking is impossible because ADM-SCH-03 reads this list' -- so the list a"
      + " scheduler is told the constraint lives in has to be reachable from the schedule,"
      + " and a route nothing links to is a route nobody finds",
    file: "src/app/schedule/page.tsx",
    from: "        <Link href={`/schedule/resources?site=${chosen}`} className=\"ds-filter-chip\">",
    to: "        <Link href={`/schedule?site=${chosen}`} className=\"ds-filter-chip\">",
    grep: "is on the schedule board, which is the list the canvas points at",
  },
  // ------------------------------------------------- ADM-STF-03, invite someone
  {
    id: "invite-the-form-is-reachable-by-a-reader-who-could-step-up",
    why: "`authz.assignment.write` is financial class, so `allowed` is false for every"
      + " password-only session -- gating the form on it would hide the step-up the form"
      + " itself offers, which is ADM-SCH-07's own finding one screen over",
    file: "src/app/staff/invite/page.tsx",
    from: "  const mayAsk = ![\"denied\", \"unreachable_level\"].includes(gateVerdict(mayInvite));",
    to: "  const mayAsk = mayInvite.allowed;",
    grep: "draws the canvas's three fields and no name",
  },
  {
    id: "invite-the-address-field-refuses-in-the-form-not-in-the-browser",
    why: "a native `required` or `type=email` refuses the submit itself, with the browser's"
      + " own bubble in the browser's own language -- so `invite.emailNeeded`, which the"
      + " design draws, becomes a branch nothing can render. ADM-MEM-10 paid for this once"
      + " and the browser suite found it again here",
    file: "src/app/staff/invite/invite-form.tsx",
    from: "          id=\"invite-email\" name=\"email\" type=\"text\" inputMode=\"email\" dir=\"ltr\"\n"
      + "          aria-required=\"true\"",
    to: "          id=\"invite-email\" name=\"email\" type=\"email\" inputMode=\"email\" dir=\"ltr\"\n"
      + "          required",
    grep: "refuses an address that is not one, before anything is sent",
  },
  {
    id: "invite-a-club-is-required-because-a-role-at-none-grants-nothing",
    why: "`permissions_of` lets a broad assignment cover a narrow scope and never the"
      + " reverse, so an assignment with no scope grants nothing at all -- the service's own"
      + " refusal, and one the screen can see for itself",
    file: "src/lib/invitations.ts",
    from: "  if (!tenantWide && clubs.length === 0) missing.clubs = true;",
    to: "  if (false) missing.clubs = true;",
    grep: "asks for a club rather than inviting somebody into none",
  },
  {
    id: "invite-the-step-up-is-offered-rather-than-the-refusal-printed",
    why: "a reader refused for assurance can fix it and one refused for a permission cannot,"
      + " so the offer is the half that matters -- sixteen marker sites in this app passed"
      + " the wrong remedy for exactly this reason",
    file: "src/app/staff/invite/invite-form.tsx",
    from: "          {state.error === \"invite.needsStepUp\" ? (",
    to: "          {false ? (",
    grep: "the only hold left on a complete form is the step-up it offers",
  },
  {
    id: "invite-a-pending-row-draws-the-address-the-link-went-to",
    why: "the canvas's pending list is `yasmin@nadi.jo · 2d left`, and the address is the"
      + " only thing identifying the row -- an invitation has no name and no profile",
    file: "src/app/staff/invite/page.tsx",
    from: "                    <span className=\"data\" dir=\"ltr\">{row.email}</span>",
    to: "                    <span className=\"data\" dir=\"ltr\">{\"\"}</span>",
    grep: "draws the address and nothing else in the who column",
  },
  {
    id: "invite-the-waiting-count-is-the-pending-ones",
    why: "an expired invitation is in the list and is not waiting -- the canvas draws"
      + " `PENDING · 2` over rows one of which reads `expired`, so a count of the rows would"
      + " be the members-list finding in a header",
    file: "src/lib/invitations.ts",
    from: "  return list.filter((one) => one.state === \"pending\").length;",
    to: "  return list.length;",
    // **The component layer, because the browser cannot reach the case.** Pointed at the
    // browser spec first and it came back UNCAUGHT, correctly: the fixture's list holds one
    // row and it is pending, so a count of the rows and a count of the waiting ones agree.
    // The row that separates them is an *expired* invitation, and nothing can write one --
    // `expires_at` is `now() + make_interval(days => N)` with a one-day floor, deliberately,
    // so that the window's two ends come from one clock. A hand-built row is the only place
    // the distinction exists, which is where its test is.
    runner: "vitest",
    grep: "counts the waiting ones and keeps the expired ones on screen",
  },
  // ------------------------------------------------- ADM-SCH-07, cancel a class
  {
    id: "cancel-class-the-sheet-is-reachable-by-a-reader-who-could-step-up",
    why: "`scheduling.session.change` is financial class, so `allowed` is false for every"
      + " password-only session -- gating the sheet on it made the step-up the sheet itself"
      + " offers unreachable, which is what ten browser tests reported on a page that"
      + " rendered correctly",
    file: "src/app/schedule/[sessionId]/page.tsx",
    from: "  const mayAsk = ![\"denied\", \"unreachable_level\"].includes(gateVerdict(mayChange));",
    to: "  const mayAsk = mayChange.allowed;",
    grep: "leads with the class, its counts and how much notice",
  },
  {
    id: "cancel-class-the-way-in-is-on-the-class",
    why: "a route nothing links to is a route nobody finds -- ADM-MEM-05 specified a button,"
      + " rendered none, and this app shipped that for as long as the screen existed",
    file: "src/app/schedule/[sessionId]/page.tsx",
    from: "        {...(session.status !== \"scheduled\" || !mayAsk",
    to: "        {...(true || session.status !== \"scheduled\" || !mayAsk",
    grep: "the way in is on the class itself",
  },
  {
    id: "cancel-class-the-consequence-is-about-the-choice-on-screen",
    why: "'6 places free · 12 would need to choose another' is a statement about one"
      + " destination, so an answer left behind from a previous choice is a figure a manager"
      + " would act on -- the race `@/lib/walk-in` needed a ref to catch",
    file: "src/app/schedule/[sessionId]/cancel-form.tsx",
    from: "    peek.previewFor !== null\n      && peek.previewFor.remedy === remedy\n"
      + "      && peek.previewFor.toSessionId === (remedy === \"move\" ? destination : \"\")\n"
      + "      ? peek.preview\n      : null;",
    to: "    peek.preview;",
    grep: "the consequence follows the choice rather than the previous one",
  },
  {
    id: "cancel-class-a-credit-states-its-own-window",
    why: "the credit's branch is what renders the canvas's 'usable on any class within 30"
      + " days', from the server's own figure rather than a constant here",
    file: "src/app/schedule/[sessionId]/cancel-form.tsx",
    from: "  if (answer.remedy === \"credit\") {",
    to: "  if (false) {",
    grep: "a credit states the window the canvas names",
  },
  {
    id: "cancel-class-finding-a-coach-is-named-rather-than-offered",
    why: "'never a locked control with no route' -- ADM-SCH-03's clash check is about a class"
      + " being created, and substituting an instructor on a published one has no form, so a"
      + " button here would answer nothing",
    file: "src/app/schedule/[sessionId]/cancel-form.tsx",
    from: "            {text(\"cancelClass.findACoach\")}",
    to: "            {\"\"}",
    grep: "names finding a coach instead rather than offering a dead control",
  },
  // ------------------------------------------------- ADM-MSH-06, downgrade
  {
    id: "downgrade-the-refusal-is-a-sentence-not-an-enum",
    why: "a vocabulary the backend stores is never a label -- the first version printed"
      + " `an_upgrade_takes_effect_inside_the_current_period` onto the page",
    file: "src/components/membership-panels.tsx",
    from: "          {refusal === null ? (quote.refused_because ?? \"\") : text(refusal)}",
    to: "          {quote.refused_because ?? \"\"}",
    grep: "names the server's refusal rather than offering a dead control",
  },
  {
    id: "downgrade-the-loss-comes-before-the-control",
    why: "the canvas's own note is the requirement -- 'the loss is stated before the saving'"
      + " -- and a sheet that put the confirmation first would satisfy every assertion about"
      + " the text and still be the order the note forbids",
    file: "src/components/membership-panels.tsx",
    from: "      {/* **The loss first**, which is the canvas's instruction rather than a layout",
    to: "      {false && /* **The loss first**, which is the canvas's instruction rather than a layout",
    grep: "puts the loss above the confirmation",
  },
  {
    id: "downgrade-excludes-the-current-plan",
    why: "`change_membership_plan` refuses an agreement on the same plan outright, so"
      + " offering it would be a control the server answers 409 to -- FD-06's rule",
    file: "src/lib/downgrade.ts",
    from: "    (one) => one.variant_id !== currentVariantId && !one.is_a_trial_product);",
    to: "    (one) => !one.is_a_trial_product);",
    grep: "excludes the plan they are on",
    runner: "vitest",
  },
  {
    id: "downgrade-excludes-a-trial",
    why: "ADR-0010 D7: a product declaring `trial_days` is what somebody converts *from*, so"
      + " moving a member onto one would be a downgrade into a seven-day clock",
    file: "src/lib/downgrade.ts",
    from: "    (one) => one.variant_id !== currentVariantId && !one.is_a_trial_product);",
    to: "    (one) => one.variant_id !== currentVariantId);",
    grep: "excludes a trial",
    runner: "vitest",
  },
  {
    id: "downgrade-two-silences-are-two-facts",
    why: "an empty loss panel is either a tenant that declares no plan rights or two plans"
      + " granting the same ones, and rendering both as 'nothing changes' is exactly the"
      + " quiet charge the canvas's own note is about",
    file: "src/lib/downgrade.ts",
    from: "  if (!move.the_leaving_plan_declares_rights && !move.the_joining_plan_declares_rights) {",
    to: "  if (false) {",
    grep: "says nothing is declared where neither plan declares",
    runner: "vitest",
  },
  {
    id: "downgrade-a-requantified-right-is-a-move",
    why: "four sessions becoming two is the half a member argues about, and leaving it out of"
      + " the loss count makes the panel say nothing changed",
    file: "src/lib/downgrade.ts",
    from: "  const moves = move.lost.length + move.gained.length + move.requantified.length;",
    to: "  const moves = move.lost.length + move.gained.length;",
    grep: "says there is a loss for each of the three kinds of move",
    runner: "vitest",
  },
  {
    id: "downgrade-a-booking-is-not-lost",
    why: "`reserve` is a negative ledger movement so the balance is already net of a hold --"
      + " a member told they lose four when one is a class they are in has been given the"
      + " wrong number in the direction the canvas's note is about",
    file: "src/lib/downgrade.ts",
    from: "    (one) => one.is_counted && (one.held ?? 0) > 0);",
    to: "    (one) => one.is_counted);",
    grep: "names the booked ones separately",
    runner: "vitest",
  },
  {
    id: "downgrade-the-keeps-it-reason-is-only-a-downgrades",
    why: "the canvas states the reason rather than the rule -- 'not today, she has paid for"
      + " August at the higher rate and keeps it' -- and that is false of an upgrade, which"
      + " charges the difference",
    file: "src/lib/downgrade.ts",
    from: "  return quote.kind === \"downgrade\"",
    to: "  return true",
    grep: "does not borrow that reason for a future upgrade",
    runner: "vitest",
  },
  {
    id: "downgrade-the-confirmation-is-the-plan-not-a-word",
    why: "on a downgrade the figure is zero, so a typed amount would be '0.00' to confirm"
      + " losing access to two clubs -- the canvas's button names the plan change",
    file: "src/lib/downgrade.ts",
    from: "  return fold(typed) !== \"\" && fold(typed) === fold(planName);",
    to: "  return fold(typed) !== \"\";",
    grep: "refuses a different plan, a word and nothing",
    runner: "vitest",
  },
  {
    id: "downgrade-the-refusal-comes-before-the-confirmation",
    why: "a reader asked to type a plan name into a form the server will refuse has been"
      + " given a control instead of a reason",
    file: "src/lib/downgrade.ts",
    from: "  if (!quote.may_change) {",
    to: "  if (false) {",
    grep: "names the refusal before asking for the confirmation",
    runner: "vitest",
  },
  // ------------------------------------------------- ADM-MSH-09, plans and pricing
  {
    id: "plans-dead-book-keeps-its-figure",
    why: "the amount was really written, so dropping it would hide the thing an owner has to"
      + " act on -- what is untrue of it is that a sale resolves to it, which is the marker's"
      + " job",
    file: "src/app/plans/page.tsx",
    from: "      {state.kind === \"deadBook\" ? (",
    to: "      {false ? (",
    grep: "says the book is not active",
    runner: "playwright",
  },
  {
    id: "plans-date-column-is-a-date",
    why: "`effective_from` is a timestamptz, so rendering it raw put"
      + " `2026-01-01T00:00:00+00:00` in a column the canvas draws as a date",
    file: "src/app/plans/page.tsx",
    from: "                      : utcDate(row.price.effective_from)}",
    to: "                      : row.price.effective_from}",
    grep: "renders the price date as a date",
    runner: "playwright",
  },
  {
    id: "plans-names-the-product-not-the-variant",
    why: "a variant is a term length and a product is the thing a member buys -- rendering the"
      + " variant alone put \"Monthly\" on six of eight rows, on the screen whose job is"
      + " choosing which plan to re-price",
    file: "src/lib/plans.ts",
    from: "    name: named ? (plan.product_name as string) : plan.product_key,",
    to: "    name: plan.display_name,",
    grep: "is the product, qualified by the variant",
    runner: "vitest",
  },
  {
    id: "plans-untranslated-falls-back-to-the-key",
    why: "`list_products`' own rule: a tenant that has not translated a product gets no name"
      + " rather than an English one, and a blank is the same absence as a null",
    file: "src/lib/plans.ts",
    from: "  const named = plan.product_name !== null && plan.product_name.trim() !== \"\";",
    to: "  const named = plan.product_name !== null;",
    grep: "treats a blank name as untranslated",
    runner: "vitest",
  },
  {
    id: "plans-priority-not-the-alphabet",
    why: "`list_prices` orders by book key, so taking the first in-window row would let the"
      + " alphabet choose which figure a plan reads as -- MOD-018's `chart_for` finding, where"
      + " an unordered lookup made the planner the author",
    file: "src/lib/plans.ts",
    from: "  if (one.price_book_priority !== held.price_book_priority) {",
    to: "  if (false) {",
    grep: "takes the higher priority, not the earlier book key",
    runner: "vitest",
  },
  {
    id: "plans-tie-breaks-on-the-book-key",
    why: "`choose_book` ends on the key because it is unique, 'so there is never a tie the"
      + " planner gets to break' -- two books at one priority priced from the same date is the"
      + " ordinary result of adding a seasonal book beside a standing one, and the fixture has"
      + " exactly that",
    file: "src/lib/plans.ts",
    from: "  if (one.price_book_key !== held.price_book_key) {",
    to: "  if (false) {",
    grep: "breaks a priority tie on the book key",
    runner: "vitest",
  },
  {
    id: "plans-active-book-beats-a-draft",
    why: "a book nobody activated matches no sale whatever its priority, so a draft book with"
      + " the highest priority would otherwise decide every figure on the screen",
    file: "src/lib/plans.ts",
    from: "  if (active(one) !== active(held)) return active(one) > active(held);",
    to: "  if (false) return active(one) > active(held);",
    grep: "prefers an active book over a draft one",
    runner: "vitest",
  },
  {
    id: "plans-dead-book-is-refused",
    why: "`create_price` never reads the book's status, so a version written into a retired"
      + " or draft book is accepted by the server and resolved by no sale -- a price change"
      + " that reports success and charges nobody",
    file: "src/lib/plans.ts",
    from: "  if (plan.price.price_book_status !== LIVE_BOOK) {",
    to: "  if (false) {",
    grep: "refuses a live price whose book was retired",
    runner: "vitest",
  },
  {
    id: "plans-out-of-window-is-not-a-price",
    why: "a superseded row is still a row, and treating it as the price in force would offer"
      + " to supersede something already superseded",
    file: "src/lib/plans.ts",
    from: "  if (plan.price === null || !plan.price.in_window) return { kind: \"noPrice\" };",
    to: "  if (plan.price === null) return { kind: \"noPrice\" };",
    grep: "has no price when the only row is outside its window",
    runner: "vitest",
  },
  {
    id: "plans-confirmation-is-an-amount",
    why: "comparing the typed string would refuse 58 for 58.00 -- a control about typography"
      + " rather than about the number, which teaches people to copy and paste",
    file: "src/lib/plans.ts",
    from: "  return parsed !== null && parsed === amountMinor;",
    to: "  return parsed !== null && typed.trim() === String(amountMinor);",
    grep: "accepts the same amount written shorter",
    runner: "vitest",
  },
  {
    id: "plans-unchanged-is-refused",
    why: "a new version charging the same still supersedes the row in force, so a reader who"
      + " mistyped and got the old figure back would have moved the price's history for"
      + " nothing",
    file: "src/lib/plans.ts",
    from: "  if (amountMinor === current.amount_minor) return { kind: \"unchanged\" };",
    to: "  if (false) return { kind: \"unchanged\" };",
    grep: "refuses the price it already is",
    runner: "vitest",
  },
  {
    id: "plans-past-date-is-refused",
    why: "MOD-016's own stated gap: a stored resolution is immutable so a receipt stands, but"
      + " a re-derivation of a historical order reads the price rows and would come back with"
      + " a figure nobody charged",
    file: "src/lib/plans.ts",
    from: "  if (effectiveFrom < today) return { kind: \"dateInThePast\" };",
    to: "  if (false) return { kind: \"dateInThePast\" };",
    grep: "refuses a date in the past and accepts today",
    runner: "vitest",
  },
  {
    id: "plans-confirmation-gates-ready",
    why: "the canvas's tier-3 control is `type 58.00 to confirm`; without it the write is"
      + " enabled by a figure and a date, which is every other write in Admin",
    file: "src/lib/plans.ts",
    from: "  if (!confirms(typedConfirmation, { amountMinor, currency: current.currency })) {",
    to: "  if (false) {",
    grep: "waits for the typed figure",
    runner: "vitest",
  },
  // ---------------------------------------------------------------- FD-02, member lookup
  {
    id: "lookup-one-character-is-refused",
    why: "one letter is every member whose name starts with it, in alphabetical order -- not"
      + " an ambiguous match a desk resolves by photo, and returning the first ten would read"
      + " as 'these are the matches'",
    file: "src/lib/lookup.ts",
    from: "  if (folded.length < MIN_QUERY) return { kind: \"tooShort\", typed: folded };",
    to: "  if (false) return { kind: \"tooShort\", typed: folded };",
    grep: "is too short at one character",
    runner: "vitest",
  },
  {
    id: "lookup-withheld-name-is-not-a-check",
    why: "a marker is not a name, so a desk confirming identity against `***` is confirming"
      + " nothing -- MOD-027's board paid for rendering the marker as though somebody were"
      + " called that",
    file: "src/lib/lookup.ts",
    from: "    name: match.legal_name !== null && !isWithheld(match.legal_name),",
    to: "    name: match.legal_name !== null,",
    grep: "counts a withheld name as no check",
    runner: "vitest",
  },
  {
    id: "lookup-a-row-says-when-it-can-confirm-nobody",
    why: "with the photo gone there are two checks and both can be withheld, so a row a desk"
      + " cannot check anybody by has to say so -- the alternative is letting somebody through"
      + " on a match nobody verified",
    file: "src/lib/lookup.ts",
    from: "  return checks.name || checks.digits;",
    to: "  return true;",
    grep: "says a row with neither cannot confirm anybody",
    runner: "vitest",
  },
  {
    id: "lookup-withheld-digits-are-not-printed",
    why: "`···***` would read as four digits somebody could ask for, which is a check that"
      + " does not exist dressed as one that does",
    file: "src/lib/lookup.ts",
    from: "  if (match.phone !== null && !isWithheld(match.phone)) {",
    to: "  if (match.phone !== null) {",
    grep: "leaves a withheld number out rather than printing the marker as digits",
    runner: "vitest",
  },
  {
    id: "lookup-the-sentence-names-the-check-that-exists",
    why: "the canvas says 'check the photo before you let them through' and there is no photo,"
      + " so the screen names the digits its own footnote calls the second check -- a sentence"
      + " pointing at a control that does not exist is worse than no sentence",
    file: "src/app/desk/lookup/page.tsx",
    from: "            {text(\"lookup.checkTheDigits\")}",
    to: "            {null}",
    grep: "finds two people who share the start of a name",
    runner: "playwright",
  },
  {
    id: "lookup-neither-offers-the-half-that-exists",
    why: "'no-match offers guest entry or lead capture' -- guest entry takes a payment at the"
      + " door and lead capture is built, so the link is real and dropping it leaves a desk"
      + " with a dead end for somebody standing in front of them",
    file: "src/app/desk/lookup/page.tsx",
    from: "        <Link href=\"/desk/trial\" className=\"ds-filter-chip\">",
    to: "        <Link href=\"/desk/lookup\" className=\"ds-filter-chip\">",
    grep: "offers the trial when nobody matches",
    runner: "playwright",
  },
  // ---------------------------------------------------------------- FD-07, the shift
  {
    id: "shift-handover-draws-nothing",
    why: "a drawer that already holds money is handed over rather than funded, so sending the"
      + " safe there is a field the command refuses -- and a form that sent it on every open"
      + " would make the handover unpressable, which is the defect this slice exists to close"
      + " arriving from the surface",
    file: "src/lib/shift.ts",
    from: '    ? { floatSource: safe, suspense: "" }\n    : { floatSource: "", suspense };',
    to: '    ? { floatSource: safe, suspense: "" }\n    : { floatSource: safe, suspense };',
    grep: "sends no account to draw from on a handover",
    runner: "vitest",
  },
  {
    id: "shift-act-is-derived",
    why: "which act a drawer is waiting for comes from its own balance, as the server derives"
      + " it. Treating every drawer as empty would label a handover 'count the float' and"
      + " send the safe with it",
    file: "src/lib/shift.ts",
    from: '  return drawer.expected_minor === 0 ? "fund" : "handover";',
    to: '  return "fund";',
    grep: "is a handover when the drawer still holds money",
    runner: "vitest",
  },
  {
    id: "shift-handover-case-emptied",
    why: "a drawer banked to nothing has nobody to name and no figure to quote, so printing"
      + " the canvas's 'Kareem left JOD 50.00' line for it would name a person and an amount"
      + " that are not there -- MOD-014's own Member 360 defect",
    file: "src/lib/shift.ts",
    from: '  if (drawer.expected_minor === 0) return { kind: "emptied" };',
    to: "  if (false) return { kind: \"emptied\" };",
    grep: "says the drawer was emptied when the last shift banked everything",
    runner: "vitest",
  },
  {
    id: "shift-short-handover-owes-a-reason",
    why: "the module refuses a short handover with nothing written, so a form that did not ask"
      + " would ask for the explanation after the submit had already failed",
    file: "src/lib/shift.ts",
    from: "  return { gap, needsReason: short, needsPosting: short };",
    to: "  return { gap, needsReason: false, needsPosting: short };",
    grep: "owes a reason and a posting when the count is short",
    runner: "vitest",
  },
  {
    id: "shift-funding-owes-no-reason",
    why: "funding an empty drawer is not a comparison -- the money is being put in -- and"
      + " demanding a reason there is exactly what the first draft of the migration's"
      + " constraint did, which refused every ordinary first open",
    file: "src/lib/shift.ts",
    from: "    return { gap: null, needsReason: false, needsPosting: countedMinor > 0 };",
    to: "    return { gap: null, needsReason: true, needsPosting: countedMinor > 0 };",
    grep: "owes a posting and no reason when a float is being drawn",
    runner: "vitest",
  },
  {
    id: "shift-withheld-name-is-not-a-name",
    why: "`GET /people/names` answers with a marker for a field this session cannot read, so"
      + " rendering it would put three asterisks where a person belongs -- MOD-027's board"
      + " paid for that once",
    file: "src/lib/shift.ts",
    from: "  return isWithheld(named.legal_name) ? null : named.legal_name;",
    to: "  return named.legal_name;",
    grep: "is nobody for a name this session may not read",
    runner: "vitest",
  },
  {
    id: "shift-close-asks-for-the-note",
    why: "the handover note is the point of FD-07 and the close is the only statement that may"
      + " set it, so a front desk that was not asked would have nothing to pass on",
    file: "src/app/desk/shift/page.tsx",
    from: "                back=\"/desk/shift\"\n                askForNote",
    to: "                back=\"/desk/shift\"",
    grep: "offers the close for a drawer with a shift open, with the note field",
    runner: "playwright",
  },
  {
    id: "task-meta-tenant-subject",
    why: "a task about the organization itself carries `subject_kind = \"tenant\"` by design --"
      + " its subject is the row's own tenant_id, which RLS already bounds -- so printing"
      + " \"This organization\" against every row is the canvas's two-part meta line padded"
      + " with noise",
    file: "src/lib/tasks.ts",
    from: '  if (subject !== null && task.subject_kind !== "tenant") parts.push(t(locale, subject));',
    to: "  if (subject !== null) parts.push(t(locale, subject));",
    grep: "leaves out the tenant subject",
    runner: "vitest",
  },
  {
    id: "task-meta-exception-reference",
    why: "`tasks.case.read` is a separate permission, so a reader without it must get the fact"
      + " that there is an exception rather than a uuid printed where a human reference belongs",
    file: "src/lib/tasks.ts",
    from: '          ? t(locale, "tasks.fromExceptionUnnamed")',
    to: '          ? task.case_id',
    grep: "names the exception without a reference",
    runner: "vitest",
  },
  {
    id: "task-overdue-zero-days",
    why: "\"overdue 0 days\" is not a sentence, and English's plural rules pick it for 0 -- so"
      + " the no-whole-days case needs its own message rather than the counted one",
    file: "src/lib/tasks.ts",
    from: "        ? t(locale, \"tasks.overdueToday\")",
    to: '        ? fill(locale, "tasks.overdueDays", { count: due.days })',
    grep: "renders all five due forms",
    runner: "vitest",
  },
  {
    id: "task-overdue-is-the-instant",
    why: "the server's overdue filter is `due_at < now()`, so a label that buckets by calendar"
      + " day reads \"due today\" at five in the afternoon on a task due at nine that morning --"
      + " one board with two definitions of late, which is what the browser layer caught",
    file: "src/lib/tasks.ts",
    from: "  if (at < now.getTime()) {",
    to: "  if (false && at < now.getTime()) {",
    grep: "calls a passed instant overdue",
    runner: "vitest",
  },
  {
    id: "task-duration-pad",
    why: "a column of durations is scanned vertically and `2h 4m` breaks the alignment that"
      + " makes the scan work -- the canvas's own fixture sets `2h 04m` beside `1h 20m`",
    file: "src/lib/tasks.ts",
    from: 'const pad = formatInteger(minutes % 60, numbering).padStart(2, "0");',
    to: "const pad = formatInteger(minutes % 60, numbering);",
    grep: "pads the minutes after an hour",
    runner: "vitest",
  },
  {
    id: "task-duration-floor",
    why: "`formatInteger` throws on a NaN and `fill` is how every figure on these pages is"
      + " rendered, so an unparseable instant in the sheet's age is a 500 on the screen rather"
      + " than a wrong number on it -- and the sweep is what showed that the obvious guards,"
      + " flooring the seconds and clamping them at zero, were both redundant",
    file: "src/lib/tasks.ts",
    from: "  if (!Number.isFinite(seconds) || seconds <= 0) return 0;",
    to: "  if (seconds <= 0) return 0;",
    grep: "never puts a fraction or a NaN",
    runner: "vitest",
  },
  {
    id: "task-duration-joiner",
    why: "English puts a space between two units and Arabic puts a conjunction, so a page"
      + " joining two plural phrases itself would put English structure into an Arabic line",
    file: "src/lib/tasks.ts",
    from: "  return fill(\n    locale, \"tasks.hoursAndMinutes\"",
    to: "  return `${hourWords} ${minuteWords(rest)}`; return fill(\n    locale, \"tasks.hoursAndMinutes\"",
    grep: "joins the two units with the conjunction",
    runner: "vitest",
  },
  {
    id: "task-sheet-handover",
    why: "ADM-CC-06: somebody else's item keeps every action visible but read-only, with a Take"
      + " over that records the handover -- so the handover is the one live control in the one"
      + " state that is otherwise inert, and without it the sheet is a dead end",
    file: "src/lib/tasks.ts",
    from: "      return { ...inert, takeOver: true };",
    to: "      return inert;",
    grep: "renders every action in every state",
    runner: "vitest",
  },
  {
    id: "task-sheet-return",
    why: "a routine permission whose every act is uncorrectable is MOD-013's rule from the other"
      + " side: a return date typed as next year would hide an exception for eleven months",
    file: "src/lib/tasks.ts",
    from: '      return { ...inert, live: true, returnToQueue: true, resolve: true };',
    to: "      return { ...inert, live: true, resolve: true };",
    grep: "offers the return a deferral needs",
    runner: "vitest",
  },
  {
    id: "task-view-closed-set",
    why: "a query string that could name a fourth view would be a filter nothing applies,"
      + " reported to the reader as the view they asked for",
    file: "src/lib/tasks.ts",
    from: "  return typeof value === \"string\" && (TASK_VIEWS as readonly string[]).includes(value);",
    to: "  return typeof value === \"string\";",
    grep: "refuse anything else",
    runner: "vitest",
  },
  {
    id: "task-overdue-whole-days",
    why: "the canvas's `overdue 2d` is a count of whole days, and a sub-day difference rounding"
      + " up reports a task due this evening as already a day late",
    file: "src/lib/tasks.ts",
    from: "  if (days === 1) return { kind: \"tomorrow\" };",
    to: "  if (days === 1) return { kind: \"days\", days };",
    grep: "reads today, tomorrow, a count, or a date",
    runner: "vitest",
  },
  {
    id: "task-vocabulary-fallthrough",
    why: "the set is MOD-026's and may grow, and these are the screens somebody filters and"
      + " acts on -- hiding an unrecognised state behind a catch-all would hide the row",
    file: "src/lib/tasks.ts",
    from: '  return SOURCE_WORDS[stored] ?? null;',
    to: '  return SOURCE_WORDS[stored] ?? "tasks.sourceManual";',
    grep: "returns null for a value it does not know",
    runner: "vitest",
  },
  {
    id: "dispute-rejected-filing",
    why: "an invoice whose fiscal filing was rejected has only half the evidence the canvas's"
      + " line names, and ticking both puts an accountant in front of a scheme expecting a"
      + " reference that does not exist",
    file: "src/lib/disputes.ts",
    from: '      note: dispute.fiscal_status === "rejected"\n'
      + '        ? "dispute.ev.filingRejected"\n'
      + '        : "dispute.ev.notFiled",',
    to: '      note: undefined,',
    grep: "does not tick a rejected fiscal filing",
    runner: "vitest",
  },
  {
    id: "dispute-refusal-as-absence",
    why: "a permission refusal rendered as an absence tells an accountant the gym cannot"
      + " prove attendance it can prove, which is the worst sentence this screen could say",
    file: "src/lib/disputes.ts",
    from: '    out.push({ key: "attendance", state: "refused", label: "dispute.ev.attendance",\n'
      + '               note: "dispute.ev.attendanceRefused" });',
    to: '    out.push({ key: "attendance", state: "missing", label: "dispute.ev.attendance",\n'
      + '               note: "dispute.ev.attendanceRefused" });',
    grep: "tells a refusal from an absence",
    runner: "vitest",
  },
  {
    id: "dispute-statement-ticked",
    why: "nothing in this build holds a written statement, and ticking the line would be a"
      + " piece of evidence claimed that does not exist",
    file: "src/lib/disputes.ts",
    from: '  out.push({ key: "statement", state: "missing", label: "dispute.ev.statement",\n'
      + '             note: "dispute.ev.statementIsYours" });',
    to: '  out.push({ key: "statement", state: "have", label: "dispute.ev.statement",\n'
      + '             note: "dispute.ev.statementIsYours" });',
    grep: "leaves the written statement to the operator",
  },
  {
    id: "recovery-unsorted",
    why: "the workspace's whole argument is that the set is sorted; a page that called every"
      + " case one decision would invite one batch action over rows it does the wrong thing to",
    file: "src/lib/recovery.ts",
    from: "  if (present.length === 1) {",
    to: "  if (present.length >= 1) {",
    grep: "says these are NOT one decision",
  },
  {
    id: "recovery-card-detail",
    why: "there is no card brand and no last four in this build, and a row implying one"
      + " would be the fabricated-evidence shape in the place paragraph 1597 is about",
    file: "src/app/payments/recovery/page.tsx",
    from: '{failure === null\n                            ? one.failure_code\n'
      + '                            : text(failure)}',
    to: '{"Card expired \u00b7 Visa \u00b7\u00b7\u00b74417"}',
    grep: "the card detail the canvas draws is absent",
  },
  {
    id: "recovery-rendered-preview",
    why: "the preview is the template as authored; a filled example would read as a message"
      + " that exists, and the one value this build cannot supply is the payment link",
    file: "src/app/payments/recovery/page.tsx",
    from: '        <p className="ds-message" dir="auto">{template.body}</p>',
    to: '        <p className="ds-message" dir="auto">'
      + '{template.body.replace(/\\{\\{ link \\}\\}/, "veyro.link/p/8k2m")}</p>',
    grep: "previews the real template",
  },
  {
    id: "form-method",
    why: "the sign-in form must be a POST so credentials cannot reach a query string",
    file: "src/app/login/login-form.tsx",
    from: "<form action={formAction} noValidate",
    to: '<form action="/login" method="get" noValidate',
    grep: "the form is a POST|the served form is a POST",
  },
  {
    id: "session-httponly",
    why: "the bearer token must be unreadable from client JavaScript",
    file: "src/app/login/actions.ts",
    from: 'jar.set(SESSION_COOKIE, token, { httpOnly: true, sameSite: "strict", secure, path: "/" });',
    to: 'jar.set(SESSION_COOKIE, token, { httpOnly: false, sameSite: "strict", secure, path: "/" });',
    grep: "sets an httpOnly session",
  },
  {
    id: "refusal-detail",
    why: "a refusal must not distinguish a wrong password from an unknown address",
    file: "src/i18n/locale.ts",
    from: '"login.failed": "Those details were not accepted.",',
    to: '"login.failed": "No such account was found.",',
    grep: "refused without saying why",
  },
  {
    id: "field-errors",
    why: "an empty submission must name every missing field",
    file: "src/app/login/actions.ts",
    from: "  if (missing.tenant || missing.identifier || missing.password || missing.recovery) {\n    return { error: null, missing, ...echo };\n  }",
    to: "  if (missing.tenant || missing.identifier || missing.password || missing.recovery) {\n    return { error: null, missing: { tenant: false, identifier: false, password: false, recovery: false }, ...echo };\n  }",
    grep: "names every missing field",
  },
  {
    id: "gate-order",
    why: "an unreachable assurance level must not be offered as a step-up",
    // **Repointed: the matrix moved to `/permissions` and kept its own short words.**
    // `describeGate` is the one that renders this cell -- `gateVerdict` in `@/lib/api`
    // answers the page-level banners -- and the order is load-bearing in both: an
    // insufficient assurance always sets `step_up_required`, and `reachable` is what tells
    // a level nobody can reach from one a stronger sign-in opens. Aiming at `api.ts`
    // reported this as a gap, which is the tell: a mutation whose test asserts the rendered
    // half while the mutation edits the other half.
    file: "src/app/permissions/page.tsx",
    from: '  if (!answer.reachable) return "gate.unreachable";\n  if (answer.step_up_required) return "gate.stepUp";',
    to: '  if (answer.step_up_required) return "gate.stepUp";\n  if (!answer.reachable) return "gate.unreachable";',
    grep: "names the passkey door rather than offering an impossible step-up",
  },
  {
    id: "bidi-isolation",
    why: "a Latin identifier inside Arabic text must carry its own direction",
    // Repointed: the gate table moved to `/permissions` with the design migration.
    file: "src/app/permissions/page.tsx",
    from: '              render: (answer) => <span className="data" dir="ltr">{answer.action}</span>,',
    to: '              render: (answer) => <span className="data">{answer.action}</span>,',
    grep: "renders left-to-right",
  },
  {
    id: "table-name",
    why: "the permissions table must have an accessible name",
    // **Repointed, and the protection moved layers with it.** The hand-rolled table became
    // a `DataGrid`, which renders its own visually-hidden caption -- so dropping
    // `labelledBy` no longer removes the name, it restores the duplication the prop exists
    // to prevent: the heading said twice, invisible to a sighted reader and heard in full
    // by a screen-reader user. What catches it is the usage sweep rather than the browser.
    file: "src/app/permissions/page.tsx",
    from: '          labelledBy="gate-heading"',
    to: "",
    runner: "node",
    grep: "points at it rather than repeating it",
  },
  {
    id: "dark-focus-ring",
    why: "the focus ring must be visible in dark mode (guardrail G4)",
    file: "src/design/tokens.generated.css",
    from: "  --color-border-focus: var(--p-accent-light);",
    to: "",
    grep: "focus ring is visible on a field in the dark theme",
  },
  {
    id: "dark-input-surface",
    why: "a form field must not render on the light surface in dark mode",
    file: "src/design/tokens.generated.css",
    from: "  --color-surface-input: var(--p-dark-950);",
    to: "",
    grep: "dark theme remaps the field",
  },
  {
    id: "touch-target",
    why: "lg is mandatory at Touch and Spacious density -- the source calls 44px the minimum "
      + "target, not a stylistic option",
    file: "src/components/ds/button.tsx",
    from: '  if ((TOUCH_DENSITIES as readonly string[]).includes(density)) return "lg";',
    to: '  if (false) return "lg";',
    runner: "vitest",
    grep: "forces lg at the densities",
  },
  {
    id: "label-association",
    why: "a validation message must be associated with its field, not merely adjacent -- the "
      + "contract says the error text is referenced by the field and read on focus",
    file: "src/components/ds/field.tsx",
    from: "              aria-describedby={messageId}\n              aria-invalid={invalid || undefined}\n              required={required}\n              className=\"ds-field-input\"\n            />\n          )\n        )}",
    to: "              aria-invalid={invalid || undefined}\n              required={required}\n              className=\"ds-field-input\"\n            />\n          )\n        )}",
    grep: "names every missing field",
  },
  {
    id: "muster-disclaimer",
    why: "paragraph 4180's disclaimer must be on every occupancy read",
    file: "src/app/access/[zoneId]/page.tsx",
    from: "      <Banner severity=\"info\">{occupancy.detail}</Banner>",
    to: "",
    grep: "disclaimer next to the number",
  },
  {
    id: "access-gaps-hidden",
    why: "a zone must say what it cannot do rather than reading as fully capable",
    file: "src/app/access/[zoneId]/page.tsx",
    // Repointed: the anchor went stale when the code around it moved.
    from: "      {zone.access_gaps.length > 0 ? (",
    to: "        {false ? (",
    grep: "names what the zone cannot do",
  },
  {
    id: "no-policy-reads-blank",
    why: "a zone with no live policy must say so, not render an empty cell",
    file: "src/app/access/page.tsx",
    // **Repointed: the anchor went stale when this board moved to `DataGrid`.** The sweep is
    // the only thing that notices, and it reports it as NOT RUN rather than as a catch --
    // which is the right way round, because a mutation that cannot apply is a protection
    // with no evidence rather than one that passed.
    from: "                zone.live_policy_version === null ? (",
    to: "                false ? (",
    grep: "says in words when a zone has no live policy",
  },
  {
    id: "withheld-unmarked",
    why: "a discreet line must be marked as withheld, or it reads as the real reason",
    file: "src/app/access/[zoneId]/page.tsx",
    from: "        {decision.public_reason === DISCREET || isRestricted(decision.code) ? (",
    to: "        {false ? (",
    grep: "shows the discreet line the member saw",
  },
  {
    id: "bidi-clock-range",
    why: "a clock range inside Arabic text must carry its own direction",
    file: "src/app/access/[zoneId]/page.tsx",
    from: "        <span className=\"data\" dir=\"ltr\">\n          {hhmm(policy.opens_minute)}",
    to: "        <span className=\"data\">\n          {hhmm(policy.opens_minute)}",
    grep: "mirrors in Arabic",
  },
  {
    id: "signed-in-redirect",
    why: "a signed-in caller must not be served the sign-in form again",
    file: "src/app/login/page.tsx",
    from: '  if (await currentSession()) redirect("/");',
    to: "",
    grep: "already-signed-in caller",
  },
  {
    id: "nav-gate",
    why: "a navigation entry must be present exactly when following it would work",
    file: "src/app/layout.tsx",
    // Repointed: the anchor went stale when the code around it moved.
    from: "{ href: \"/organization\", label: \"nav.organization\", allowed: organization.allowed,",
    to: "{ href: \"/organization\", label: \"nav.organization\", allowed: true },",
    grep: "gets no navigation entry",
  },
  {
    id: "org-empty-entity",
    why: "a tenant with no legal entity cannot be invoiced, so the page has to say so",
    file: "src/app/organization/page.tsx",
    from: "        <Banner severity=\"info\">{text(\"org.noEntities\")}</Banner>",
    to: "        <ul />",
    grep: "no legal entity rather than leaving a blank",
  },
  {
    id: "org-identifier-dir",
    why: "an IANA zone inside Arabic text reads as a different zone without dir=ltr",
    file: "src/app/organization/page.tsx",
    // Repointed: the anchor went stale when the code around it moved.
    from: "                      <span className=\"data\" dir=\"ltr\">{location.timezone}</span>",
    to: "                        <span className=\"data\">\n                          {location.timezone}",
    grep: "keeps the identifiers left-to-right",
  },
  {
    id: "org-tree-orphans",
    why: "a site whose brand is missing from the read must be shown, not dropped",
    file: "src/lib/organization.ts",
    from: "    orphanLocations: locations.filter((location) => !brandIds.has(location.brand_id)),",
    to: "    orphanLocations: [],",
    runner: "vitest",
    grep: "parent is missing",
  },
  {
    id: "member-mask-blank",
    why: "a withheld field must be marked, because a blank reads as 'there was nothing here'",
    file: "src/components/withheld.tsx",
    from: "        {t(locale, \"member.withheld\")}",
    to: "        {\"\"}",
    grep: "marks a masked identity field as withheld",
  },
  {
    id: "member-health-remedy",
    why: "a health field needs AAL 3, which nothing in this build reaches, so offering a "
      + "step-up would send somebody looking for a key the product cannot check",
    file: "src/app/people/[personId]/page.tsx",
    // Repointed: the anchor went stale when the code around it moved.
    from: "                        ? \"member.withheldHealth\"\n                        : \"member.withheldIdentity\"",
    to: "                        ? \"member.withheldIdentity\"\n                        : \"member.withheldIdentity\"",
    grep: "needs a level this screen cannot reach",
  },
  {
    id: "note-health-remedy",
    why: "a health note's body is unreadable by anybody in this build, like the field, and "
      + "the two branches are separate code with separate tests",
    file: "src/app/people/[personId]/page.tsx",
    from: "            ? \"member.withheldHealth\"\n            : \"member.withheldIdentity\"",
    to: "            ? \"member.withheldIdentity\"\n            : \"member.withheldIdentity\"",
    grep: "keeps a health note visible as a note",
  },
  {
    id: "member-sections-dropped",
    why: "a section with no module behind it must be named, not rendered as an empty list",
    file: "src/lib/people.ts",
    from: "    unavailable: entries\n      .filter(([, source]) => source.startsWith(\"unavailable:\"))",
    to: "    unavailable: ([] as [string, string][])\n      .filter(([, source]) => source.startsWith(\"unavailable:\"))",
    grep: "names the sections no module in this build can answer",
  },
  {
    id: "dedup-score-alone",
    why: "a duplicate score with no signals behind it is not something to destroy a record on",
    file: "src/app/people/page.tsx",
    // Repointed: the anchor went stale when the code around it moved.
    from: "                render: (candidate) => candidate.signals.join(\", \"),",
    to: "                    {\"\"}",
    grep: "score and the signals behind it",
  },
  {
    id: "stepup-cookie",
    why: "MOD-007 revokes the session it steps up from, so not replacing the cookie is a "
      + "sign-out dressed as a success",
    file: "src/app/step-up/actions.ts",
    from: "    jar.set(SESSION_COOKIE, token, {",
    to: "    void jar; void ((_unused) => _unused)({",
    grep: "keeps the reader signed in",
  },
  {
    id: "stepup-open-redirect",
    why: "a `next` arrives in a link, so following it anywhere is an open redirect on the one "
      + "page where somebody has just typed a credential",
    file: "src/lib/navigation.ts",
    from: '  if (candidate.startsWith("//") || candidate.startsWith("/\\\\")) return HOME;',
    to: "  // guard removed",
    grep: "never to another host",
  },
  {
    id: "stepup-factor",
    why: "a password session cannot raise itself with another password, so asking for one is a "
      + "refusal the reader cannot act on",
    file: "src/app/step-up/page.tsx",
    from: '      ? "recovery_code"\n      : "password";',
    to: '      ? "password"\n      : "password";',
    grep: "asks for a recovery code",
  },
  {
    id: "stepup-unreachable",
    why: "level 3 needs a passkey no page here enrols, so offering a field "
      + "sends somebody looking for a key the product cannot check",
    file: "src/app/step-up/page.tsx",
    from: "  if (!asked.reachable) {",
    to: "  if (false) {",
    grep: "a level nobody can reach",
  },
  {
    id: "member-stepup-offer",
    why: "naming a remedy and not offering it is the dead end MOD-007's own review records",
    file: "src/app/people/[personId]/page.tsx",
    from: "            {text(\"member.raiseSession\")}",
    to: "            {\"\"}",
    grep: "is offered where the refusal is",
  },
  {
    id: "perms-chain-caveat",
    why: "a hash chain that reports verified with no caveat is the more misleading of its two "
      + "answers: it detects editing, not truncation by somebody who moves the head",
    file: "src/app/permissions/page.tsx",
    from: "                {text(\"perms.chainCaveat\")}",
    to: "                {\"\"}",
    grep: "never without its caveat",
  },
  {
    id: "perms-audit-gate",
    why: "an empty audit table reads as 'nothing has been refused', which is a different fact "
      + "from 'you may not see what has been'",
    file: "src/app/permissions/page.tsx",
    from: "        {!mayAudit.allowed ? (",
    to: "        {false ? (",
    grep: "refused each block",
  },
  {
    id: "perms-permission-dir",
    why: "a permission name is an identifier, and the bidi algorithm reorders it inside an "
      + "Arabic page into a different string",
    file: "src/app/permissions/page.tsx",
    // Repointed: the anchor went stale when the code around it moved.
    from: "                      <span className=\"data\" dir=\"ltr\">{entry.action}</span>",
    to: "                      <span className=\"data\">{entry.action}</span>",
    grep: "left-to-right inside an Arabic document",
  },
  {
    id: "perms-grant-is-not-a-session",
    why: "a permission listed is still refused when the action needs a stronger sign-in, which "
      + "is MOD-014's 'a grant is not a session' finding on a page that lists grants",
    file: "src/app/permissions/page.tsx",
    from: "          {text(\"perms.mineLead\")}",
    to: "          {\"\"}",
    grep: "at the scope the server derived",
  },
  {
    id: "fleet-attention-rule",
    why: "'needs somebody' is a device in service that has gone quiet, not every device that "
      + "is not online -- listing the others is how an alert channel gets muted",
    file: "src/app/fleet/page.tsx",
    from: "  const attention = new Set(fleet.needs_attention);",
    to: "  const attention = new Set(fleet.devices.filter((d) => d.reachability !== \"online\").map((d) => d.device_id));",
    grep: "an incident",
  },
  {
    id: "fleet-commissioning-denominator",
    why: "a list of only the missing tests cannot be told from a list of everything when "
      + "nothing is missing, and the question is what is left before the door can open",
    file: "src/app/fleet/[deviceId]/page.tsx",
    from: "            {commissioning(device.outstanding_tests).map(({ test, done }) => (",
    to: "            {commissioning(device.outstanding_tests).filter((entry) => !entry.done).map(({ test, done }) => (",
    grep: "nothing outstanding",
  },
  {
    id: "device-credential-disclosure",
    why: "no signature is verified anywhere in this build, and MOD-022 opens doors on that "
      + "identity -- a page that omits it presents a fingerprint as a key",
    file: "src/app/fleet/[deviceId]/page.tsx",
    from: "          {text(\"device.certificatesLead\")}",
    to: "          {\"\"}",
    grep: "not a key anything checks",
  },
  {
    id: "device-not-found",
    why: "a malformed id in a URL is a bad link, not a broken product",
    file: "src/app/fleet/[deviceId]/page.tsx",
    from: "    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) {",
    to: "    if (error instanceof ApiError && error.status === 404) {",
    grep: "malformed device id",
  },
  {
    id: "ops-backlog-explained",
    why: "a delivery nobody handles accumulates by design, and a number rendered bare lets "
      + "somebody conclude a consumer is reading it",
    file: "src/app/operations/page.tsx",
    // **The branch the fixture actually renders.** It subscribes a consumer, so the page
    // takes the `backlogUnexpected` arm -- and a mutation aimed at the arm nobody renders
    // changes nothing a reader sees, which the sweep would rightly report as uncaught. The
    // same trap as the fetch-guard-versus-rendering-guard one recorded below.
    from: "                  : text(\"ops.backlogUnexpected\")}",
    to: "                  : \"\"}",
    grep: "a delivery nobody handles is expected",
  },
  {
    id: "ops-relay-verdict",
    why: "the relay running is what makes a pending event transient rather than a fault, and "
      + "a page that never says so leaves the reader to guess which it is",
    file: "src/app/operations/page.tsx",
    from: "              ) : relay === \"running\" ? (",
    to: "              ) : false ? (",
    grep: "says the relay is running",
  },
  // No mutation for `ops.noRuns`, deliberately: it renders only for a job with no runs, and
  // the fixture's last step runs the worker, so every job has one and the string is
  // unreachable in the browser. A mutation nothing can catch is a gap to name rather than to
  // hide -- the decision behind the label is `relayVerdict`, which has eight cases in
  // `tests/component/operations-worker.test.ts`, and the e2e asserts the other direction:
  // after a real tick, no job reads as never run.
  {
    id: "ops-worker-run-proves-what",
    why: "a run is recorded by the worker itself, so a board that does not say so lets a "
      + "reader take it as proof the job's effect reached something outside the database",
    file: "src/app/operations/page.tsx",
    from: "                {jobs.worker_gaps.map((gap) => (",
    to: "                {([] as string[]).map((gap) => (",
    grep: "says a burst of runs after a restart is expected",
  },
  {
    id: "ops-deadletter-gate",
    why: "an empty dead-letter table somebody may not see reads as 'nothing is quarantined', "
      + "which is a different fact",
    file: "src/app/operations/page.tsx",
    // **The rendering guard, not the fetch guard.** The first version of this mutation
    // removed the condition on the *request* -- which changes nothing a reader sees, because
    // `Gated` still refuses, so the sweep reported it uncaught and was right to.
    from: "  if (!gate.allowed) {",
    to: "  if (false) {",
    grep: "refused each block rather than shown four empty ones",
  },
  {
    id: "ops-objective-honesty",
    why: "an empty objective list is two different facts -- nobody set a threshold, or "
      + "nothing is watching -- and the worker turning the second into the first is exactly "
      + "why the page has to say which it is rather than printing the count alone",
    file: "src/i18n/locale.ts",
    from: "    \"ops.noObjectives\": \"No objective is defined. The worker now evaluates every live objective every five minutes and announces a breach once per the objective\u2019s own window, so an empty list here means nobody has set a threshold \u2014 not that nothing is watching.\",",
    to: "    \"ops.noObjectives\": \"No objective is defined.\",",
    grep: "says an empty objective list means nobody set a threshold",
  },
  {
    id: "schedule-reason-marked",
    why: "a withheld reason rendered as an empty cell is indistinguishable from one nobody "
      + "wrote, and an absent entry says nothing changed -- which is a different fact",
    file: "src/app/schedule/[sessionId]/page.tsx",
    from: "                  {change.reason_masked ? (",
    to: "                  {false ? (",
    grep: "sees a change's reason withheld rather than absent",
  },
  {
    id: "schedule-step-up-only-when-a-remedy",
    why: "offering a step-up to a session that does not hold the permission at any assurance "
      + "sends somebody looking for a second factor that would change nothing",
    file: "src/app/schedule/[sessionId]/page.tsx",
    from: "                {mayChange.step_up_required ? (",
    to: "                {true ? (",
    grep: "sees a change's reason withheld rather than absent",
  },
  {
    id: "schedule-held-is-not-a-counter",
    why: "there is no held_count anywhere in MOD-019 and the absence is swept for, so a "
      + "reader who takes these for stored counters is reasoning about a mechanism that "
      + "does not exist",
    file: "src/app/schedule/page.tsx",
    from: "            {text(\"schedule.heldExplained\")}",
    to: "            {\"\"}",
    grep: "says what Taken and Free are",
  },
  {
    id: "schedule-former-resources-kept-apart",
    why: "a substituted instructor's hold is kept rather than deleted, and one list with a "
      + "flag puts a coach who was sent home back on the roster",
    file: "src/app/schedule/[sessionId]/page.tsx",
    from: "            <Resources list={session.former_resources} timezone={session.timezone}",
    to: "            <Resources list={[]} timezone={session.timezone}",
    grep: "shows what a session used to hold",
  },
  {
    id: "member-two-reasons",
    why: "four of the sections named here belong to modules that have since been built, so a "
      + "reader who takes 'this projection does not read it' for 'the product does not have "
      + "it' has been told the wrong thing about their own build",
    file: "src/app/people/[personId]/page.tsx",
    // Repointed: the anchor went stale when the code around it moved.
    from: "            <p className=\"muted\" style={{ margin: 0 }}>{text(\"member.unavailableWhy\")}</p>",
    to: "            <p className=\"muted\" style={{ margin: 0 }}>{\"\"}</p>",
    grep: "does not call a module that exists one that was never built",
  },
  {
    id: "fleet-count-labelled",
    why: "a bare number after a timestamp reads as part of it, and the count is the only "
      + "thing on that line which is not a time",
    file: "src/app/fleet/page.tsx",
    // Repointed, and **the occurrence matters**: `fleet.counted` is on this page twice and
    // the footer's is the one the test reads, because the header's count has its own label
    // beside it. An anchor that matched both was reported as ambiguous rather than run,
    // which is the harness refusing to guess.
    from: "          <span className=\"data\">{formatInteger(fleet.count, \"latn\")}</span>{\" \"}\n          {text(\"fleet.counted\")}",
    to: "          <span className=\"data\">{formatInteger(fleet.count, \"latn\")}</span>{\" \"}\n          {\"\"}",
    grep: "labels the count and the clock",
  },
  {
    id: "utc-is-marked",
    why: "an instant with no zone was merely ambiguous while every screen rendered one that "
      + "way, and became misleading the day the schedule board started converting",
    file: "src/lib/time.ts",
    from: "  return `${instant.slice(0, 10)} ${instant.slice(11, 16)} UTC`;",
    to: "  return `${instant.slice(0, 10)} ${instant.slice(11, 16)}`;",
    grep: "labels the count and the clock",
  },
  {
    id: "schedule-local-time",
    why: "MOD-019 stores a UTC instant and the local facts it came from because neither is "
      + "derivable from the other, so slicing the ISO string shows a class at 18:00 in Amman "
      + "as 15:00 under a heading promising the site's own timezone",
    file: "src/lib/time.ts",
    from: "      time: new Intl.DateTimeFormat(\"en-GB\", {",
    to: "      time: ((x) => ({ format: () => instant.slice(11, 16) }))(new Intl.DateTimeFormat(\"en-GB\", {",
    grep: "renders every session in the site's timezone",
  },
  {
    id: "phone-table-scrolls-inside-itself",
    why: "a page that scrolls sideways hides its own right-hand edge, so a column a reader "
      + "cannot see reads as a column that does not exist",
    file: "src/app/globals.css",
    from: "  table {\n    display: block;",
    to: "  table.not-a-table {\n    display: block;",
    // **Re-pointed, because the document-level assertion stopped being able to prove this.**
    // Breaking the rule used to make seven surfaces overflow; it now makes none of them,
    // because every table here is either a `DataGrid` whose columns drop by priority until
    // it fits or a hand-rolled one at `width: 100%`. The rule is still correct and is
    // redundant on every page that exists, so the mutation came back uncaught -- a protection
    // nothing could prove. The collapse itself is directly measurable, so that is what is
    // measured now -- and it has to be measured on a *hand-rolled* table: a grid gets
    // `display: block` from the 599px collapse rule and the matrix is exempt, so pointing
    // this at a grid was still uncaught for a second reason.
    grep: "a hand-rolled table collapses as the design states",
  },
  {
    // **The live document-level protection, replacing one that nothing could prove.** This
    // slot held `.facts dd { overflow-wrap: anywhere }` against the same assertion, and that
    // came back uncaught for the reason one rule up plus one more: `contain: layout` on the
    // matrix's scroll wrapper now stops an overflowing descendant reaching the root at all,
    // so a value too wide for its track is contained before the document can see it. The
    // wrapper is what the assertion can still prove -- removing it overflows `/permissions`
    // by exactly the 125px the rules file records.
    id: "phone-matrix-overflow-is-contained",
    why: "the matrix scrolls inside its own wrapper and an overflowing descendant still "
      + "contributed to the document's scrollable area until `contain: layout` bounded it, "
      + "which is the one of the three containments that does not clip the focus ring",
    file: "src/app/globals.css",
    // Repointed: `contain: layout` is on two boxes now -- the matrix's scroll wrapper and
    // the week grid's, which learned the same lesson later. The anchor carries the line
    // after it so it names the matrix's.
    from: "  contain: layout;\n  border: 1px solid var(--color-border-default);",
    to: "  border: 1px solid var(--color-border-default);",
    grep: "the permissions page does not scroll sideways",
  },
  {
    // The matrix is the design's own exception -- "a column dropped from a matrix is a
    // comparison a reader gets wrong" -- so it keeps table layout where a grid collapses.
    // `display: block` on it is what let its sticky header escape to the document root.
    id: "phone-matrix-keeps-table-layout",
    why: "a matrix that collapsed like a grid would drop columns a reader is comparing, and "
      + "`display: block` on it is what used to send its sticky header to the document root",
    file: "src/app/globals.css",
    from: "  .ds-matrix {\n    display: table;",
    to: "  .ds-matrix {\n    display: block;",
    grep: "the capability matrix collapses as the design states",
  },
  {
    id: "phone-grid-cells-leave-table-layout",
    why: "a cell still in table layout is the collapse not having happened, and the priority "
      + "columns then render beside their own secondary fragment -- which is what every grid "
      + "in this app did below 600px for as long as the collapse existed",
    file: "src/app/globals.css",
    from: "  .ds-grid-table td {\n    display: block;",
    to: "  .ds-grid-table td.nope {\n    display: block;",
    grep: "its cells collapses as the design states",
  },
  {
    id: "config-unset-is-a-sentence",
    why: "an unset key reads back as its own default, which is indistinguishable from a "
      + "tenant that published the same value unless the scope is rendered",
    file: "src/app/configuration/page.tsx",
    // Repointed: the anchor went stale when the code around it moved.
    from: "                    return isUnset(entry) ? (",
    to: "                    return false ? (",
    grep: "says nobody set the key nobody set",
  },
  {
    id: "config-flag-reason",
    why: "`off` could be a kill switch, a flag nobody enabled, or a rule that sent this "
      + "subject to the control arm, and an operator in an incident needs to know which",
    file: "src/app/configuration/page.tsx",
    // Repointed: the anchor went stale when the code around it moved.
    from: "                  render: ([, decision]) => text(FLAG_REASON[flagReason(decision)]),",
    to: "                  render: () => \"\",",
    grep: "says why a flag is off",
  },
  {
    id: "config-kill-switch-marked",
    why: "a kill switch outranks every targeting rule and is somebody's deliberate stop, "
      + "which is the one flag state worth an alarm rather than a row",
    file: "src/app/configuration/page.tsx",
    from: "              <Banner severity=\"critical\">{text(\"config.killSwitchEngaged\")}</Banner>",
    to: "              <></>",
    grep: "marks a kill switch",
  },
  {
    id: "config-flags-are-per-subject",
    why: "there is no route that lists flags without evaluating them, so a flag missing from "
      + "the board is not a flag that is absent",
    file: "src/app/configuration/page.tsx",
    from: "              {text(\"config.noFlagList\")}",
    to: "              {\"\"}",
    grep: "no route that lists flags",
  },
  {
    id: "config-flag-block-gated-on-its-own",
    why: "the flag read is its own permission, so a reader may hold the registry read and "
      + "not it -- and an empty flag board reads as a tenant with no flags",
    file: "src/app/configuration/page.tsx",
    from: "        {!mayFlags.allowed ? (",
    to: "        {false ? (",
    grep: "is refused both blocks",
  },
  {
    id: "roster-gated-on-its-own",
    why: "the roster belongs to MOD-020 and the seats to MOD-019, so a reader may hold one "
      + "permission and not the other -- and 'nobody is booked' is a different fact from "
      + "'you may not see who is'",
    file: "src/app/schedule/[sessionId]/page.tsx",
    from: "        {!mayRoster.allowed ? (",
    to: "        {false ? (",
    grep: "is refused the roster, because it belongs to another module",
  },
  {
    id: "roster-seats-are-the-schedules",
    why: "there is no roster table and no cached total, so a reader who counted the rows "
      + "would disagree with the seat count the first time a hold had no booking behind it",
    file: "src/app/schedule/[sessionId]/page.tsx",
    from: "              {text(\"roster.capacityIsElsewhere\")}",
    to: "              {\"\"}",
    grep: "says whose seats they are",
  },
  {
    id: "roster-not-checked-in-is-a-sentence",
    why: "a check-in is recorded rather than performed, so a blank cell reads as a missing "
      + "value where the fact is that nobody has claimed one",
    file: "src/i18n/locale.ts",
    from: "    \"roster.notCheckedIn\": \"not yet\",",
    to: "    \"roster.notCheckedIn\": \"\",",
    grep: "says whose seats they are",
  },
  {
    id: "fleet-freshness-disclosure",
    why: "reachability is worked out when the page loads and nothing records it, so a board "
      + "that does not say so claims a freshness the product does not have",
    file: "src/i18n/locale.ts",
    from: "    \"fleet.lead\": \"Every device at this tenant, what it can do, and whether it is reachable. Reachability is worked out from the last report a device sent — nothing stores it and nothing asks a device for it, so this is what was true when the page was loaded. A scheduled sweep does announce a device in service that has gone quiet; it changes nothing on this board.\",",
    to: "    \"fleet.lead\": \"Every device at this tenant, what it can do, and whether it is reachable.\",",
    grep: "says reachability is worked out rather than stored",
  },
  {
    id: "members-mask-printed-raw",
    why: "a masked name is marked and explained, not printed as three asterisks -- the same "
      + "fact rendered as a glitch",
    file: "src/app/members/page.tsx",
    from: "                    {isWithheld(row.preferred_name ?? row.legal_name) ? (",
    to: "                    {false ? (",
    grep: "marks a withheld name",
  },
  {
    id: "members-total-is-the-match",
    why: "a filtered list that reports only its own length implies the records that did not "
      + "match do not exist",
    file: "src/app/members/page.tsx",
    from: '          <span className="data">{formatInteger(page.total, "latn")}</span>{" "}',
    to: '          <span className="data">{formatInteger(page.matching, "latn")}</span>{" "}',
    grep: "keeps the tenant's total",
  },
  {
    id: "account-own-revoke-leaves-a-dead-page",
    why: "revoking your own device ends the session that pressed the button, so a success "
      + "message returns to a page with no session to render it -- the reader sees nothing "
      + "and is thrown to sign-in later with no explanation",
    file: "src/app/account/actions.ts",
    from: "      signedOut: (await currentSession()) === null,",
    to: "      signedOut: false,",
    grep: "signs you out here",
  },
  {
    id: "account-this-browser-unmarked",
    why: "revoking the device you are reading the page in signs you out and locks this "
      + "browser out for good, so the one device that must be marked is that one",
    file: "src/lib/account.ts",
    from: "  const mine = sessions.find((s) => s.session_id === sessionId);",
    to: "  const mine = sessions.find(() => false);",
    grep: "marks the browser it is reading from",
  },
  {
    id: "account-revoke-warning-deleted",
    why: "a revoked device is refused at the next sign-in rather than challenged, in the same "
      + "words a wrong password gets -- so the cost has to be said before the button, because "
      + "nothing afterwards can say it",
    file: "src/app/account/account-view.tsx",
    from: "                    {text(\"account.revokingThisSignsYouOut\")}",
    to: "                    {null}",
    grep: "marks the browser it is reading from",
  },
  {
    id: "account-codes-need-a-step-up",
    why: "minting codes takes the current password or a stepped-up session and nothing else, "
      + "so a button offered to a level-1 session offers an action the server refuses",
    file: "src/lib/account.ts",
    from: "  return aal >= 2;",
    to: "  return true;",
    grep: "offers no reissue button",
  },
  {
    id: "account-session-is-live-needs-both",
    why: "a session is live only if it is neither revoked nor expired -- checking the flag "
      + "alone lists a fortnight-old session as still open",
    file: "src/lib/account.ts",
    from: "  return session.revoked_at === null && session.expires_at > nowIso;",
    to: "  return session.revoked_at === null;",
    runner: "vitest",
    grep: "not revoked, and not expired",
  },
  {
    id: "account-codes-are-shown-once",
    why: "only a hash is kept, so a batch exists in one HTTP response -- a page that did not "
      + "say so would imply they can be fetched again",
    file: "src/app/account/account-view.tsx",
    from: '            <Banner severity="attention">{text("account.codesShownOnce")}</Banner>',
    to: "            {null}",
    grep: "shows the batch once",
  },
  {
    id: "integrations-obligations-bind-critical",
    why: "the check was keyed on `live_critical`, which the column never holds, so every "
      + "install reported the written obligations did not apply -- including one carrying "
      + "traffic without its exit plan",
    file: "src/lib/integrations.ts",
    from: 'export const OBLIGED_CRITICALITY = "critical";',
    to: 'export const OBLIGED_CRITICALITY = "live_critical";',
    runner: "vitest",
    grep: "the value the column actually holds",
  },
  {
    id: "integrations-page-asks-the-library",
    why: "the page re-derived the criticality comparison for its own cell while the library "
      + "answered the banner, so fixing one left the other wrong -- the banner named an "
      + "install carrying traffic without its obligations while the row said they did not "
      + "apply",
    file: "src/app/integrations/page.tsx",
    // Repointed: the anchor went stale when the code around it moved.
    from: "                    return !obligationsApply(install) ? (",
    to: '                    return install.criticality !== "live_critical" ? (',
    grep: "names the critical install missing a written obligation",
  },
  {
    id: "integrations-counts-are-reported-not-observed",
    why: "nothing in this build calls a provider, so a record count is a caller's word -- "
      + "and a number with no caveat reads as data that moved",
    file: "src/lib/integrations.ts",
    from: "  return run.records_read > 0 || run.records_written > 0;",
    to: "  return false;",
    grep: "counts were reported rather than observed",
  },
  {
    id: "integrations-dead-run-needs-somebody",
    why: "a failed run retries itself; a dead one burned its budget and needs an attributed "
      + "release before it goes back in front of a provider",
    file: "src/lib/integrations.ts",
    from: '  return run.status === "dead";',
    to: '  return run.status === "failed";',
    runner: "vitest",
    grep: "dead and not merely failed",
  },
  {
    id: "notify-reason-is-a-sentence",
    why: "`no_preference_stops_it` tells a reader nothing they can act on -- 'a rule id is "
      + "not a reason', which MOD-005's board learned about flags",
    file: "src/lib/notifications.ts",
    from: "  return REASON_KEYS[reason] ?? null;",
    to: "  return null;",
    grep: "decision reason as a sentence",
  },
  {
    id: "notify-says-nothing-sends",
    why: "every notification sits at `requested` for ever because no dispatcher exists, and "
      + "a board rendering that as a queue making progress claims an outbound path there is "
      + "none of",
    file: "src/app/notifications/page.tsx",
    from: '        <Banner severity="attention">{text("notify.nothingSends")}</Banner>',
    to: "        {null}",
    grep: "leads with the fact that nothing sends",
  },
  {
    id: "notify-only-an-unsubscribe-can-be-lifted",
    why: "a bounce is the channel's judgement about deliverability, and a tenant that could "
      + "clear one would be choosing to keep sending to an address that rejected them",
    file: "src/lib/notifications.ts",
    from: '  return suppression.reason === "unsubscribed";',
    to: "  return true;",
    runner: "vitest",
    grep: "true only for an unsubscribe",
  },
  {
    id: "notify-suppressed-is-not-waiting",
    why: "a suppression is a decision the module made and recorded a reason for; counting it "
      + "as waiting would inflate the one number on the page that means nothing sends",
    file: "src/lib/notifications.ts",
    from: '  if (notification.status === "suppressed") return "decided";',
    to: '  if (notification.status === "suppressed") return "no_dispatcher";',
    runner: "vitest",
    grep: "suppressed message decided",
  },
  {
    id: "privacy-residue-is-grouped",
    why: "375 rows of column names is a wall rather than a disclosure, and the grouping is "
      + "what makes the shape of what survives legible at all",
    file: "src/lib/privacy.ts",
    from: "    const prefix = entry.table.includes(\"_\")",
    to: "    const prefix = false",
    runner: "playwright",
    grep: "groups the residue by area",
  },
  {
    id: "privacy-emphasis-is-not-asterisks",
    why: "the registry's reasons were written where `**` is emphasis, in a Python module a "
      + "developer reads -- printed literally they are punctuation nobody wrote for a reader",
    file: "src/components/prose.tsx",
    from: "        segment.kind === \"strong\" ? (",
    to: "        false ? (",
    grep: "emphasis as emphasis",
  },
  {
    id: "privacy-live-hold-is-told-from-a-released-one",
    why: "releasing a hold is the single act that un-blocks destruction of preserved "
      + "evidence, so a board that showed only live holds would hide the one with the most "
      + "consequence attached",
    file: "src/lib/privacy.ts",
    from: '  return api("/privacy/legal-holds?include_released=true");',
    to: '  return api("/privacy/legal-holds");',
    grep: "live legal hold from a released one",
  },
  {
    id: "privacy-queue-is-ordered-by-deadline",
    why: "a regulator-facing deadline is the one number on that screen with a consequence "
      + "attached, and a queue in insertion order buries the request already past it",
    file: "src/lib/privacy.ts",
    from: "    .sort((a, b) => a.due_at.localeCompare(b.due_at));",
    to: "    .sort((a, b) => b.due_at.localeCompare(a.due_at));",
    grep: "overdue request first",
  },
  {
    id: "privacy-says-nothing-sweeps",
    why: "the retention decision exists and no job calls it, so a list of policies with no "
      + "such sentence reads as a schedule that runs",
    file: "src/app/privacy/page.tsx",
    from: '            {text("privacy.nothingSweeps")}',
    to: "            {null}",
    grep: "nothing deletes on the retention schedule",
  },
  {
    id: "catalog-promotion-needs-window-and-status",
    why: "nothing retires a promotion when its window closes, so a board showing the status "
      + "alone says a campaign is running when it ended in February",
    file: "src/lib/catalog.ts",
    from: '  return promotion.status === "active" && promotion.in_window;',
    to: '  return promotion.status === "active";',
    runner: "vitest",
    grep: "needs both the status and the window",
  },
  {
    id: "catalog-percent-is-not-basis-points",
    why: "1000 basis points is ten percent, and rendering the stored number is off by a "
      + "hundred -- the units mistake this build's money rules exist to prevent",
    file: "src/lib/catalog.ts",
    from: "    return { kind: \"percent\", percent: promotion.percent_bp / 100 };",
    to: "    return { kind: \"percent\", percent: promotion.percent_bp };",
    runner: "vitest",
    grep: "converts basis points",
  },
  {
    id: "catalog-sellable-needs-an-active-book",
    why: "a price in its window in a book nobody activated prices nothing, so a published "
      + "product with only that price is a till that cannot sell it",
    file: "src/lib/catalog.ts",
    from: '      p.price_book_status === "active" &&',
    to: "",
    runner: "vitest",
    grep: "price whose book was never activated",
  },
  {
    id: "catalog-says-a-row-is-not-the-resolved-price",
    why: "three things decide what a sale costs and a stored row answers one -- a figure "
      + "without that sentence reads as a promise only the sale can make",
    file: "src/app/catalog/page.tsx",
    from: '              {text("catalog.notThePrice")}',
    to: "              {null}",
    grep: "is not the resolved price",
  },
  {
    id: "finance-closing-period-takes-no-trade",
    why: "`closing` is the state that surprises -- it admits the close's own entries and no "
      + "trade at all -- so a board reasoning from the status alone gets the one case that "
      + "matters wrong",
    file: "src/lib/ledger.ts",
    from: '  return periods.filter((p) => p.status === "closing" || p.status === "reopened");',
    to: '  return periods.filter((p) => p.status === "reopened");',
    runner: "vitest",
    grep: "names a closing period",
  },
  {
    id: "finance-unbalanced-is-lost-rows",
    why: "every journal balances by a constraint the database enforces, so a difference means "
      + "rows are missing rather than rounded -- a surface that said 'these columns differ' "
      + "would send somebody looking for the wrong thing",
    file: "src/lib/ledger.ts",
    // **The first version of this mutation was a no-op**, which the sweep reported as a gap:
    // it inserted a branch guarded by `difference_minor === 0`, and the test's own case has a
    // difference of -4500, so nothing changed. A mutation that changes nothing is not
    // evidence -- the trap the backend rules file names, met here in the web half.
    from: '    : { kind: "lost_rows", differenceMinor: balance.difference_minor };',
    to: '    : { kind: "balanced", differenceMinor: 0 };',
    runner: "vitest",
    grep: "calls an unbalanced ledger lost rows",
  },
  {
    id: "finance-names-the-legal-entity",
    why: "a trial balance is per legal entity and per currency, and the block's own sentence "
      + "says so -- rendering only the currency is the defect that sentence warns about",
    file: "src/app/finance/page.tsx",
    from: "                  ?.registered_name ?? (",
    to: "                  ?.nothing_here ?? (",
    grep: "names the legal entity",
  },
  {
    id: "finance-marks-a-retired-account",
    why: "a retired account stays on the trial balance because a retired account with a "
      + "balance is the row somebody needs to notice -- unmarked, it reads as a live one",
    file: "src/app/finance/page.tsx",
    // Repointed: the anchor went stale when the code around it moved.
    from: '                          {line.status === "active" ? "" : ` · ${text("finance.retired")}`}',
    to: '                          {line.status === "active" ? "" : ``}',
    grep: "marks a retired account",
  },
  {
    id: "finance-closing-is-named-as-needing-somebody",
    why: "an accountant who began a close has deliberately stopped that entity's postings, "
      + "and the banner is the only place the product says so",
    file: "src/app/finance/page.tsx",
    from: "        {attention.length > 0 ? (",
    to: "        {false ? (",
    grep: "middle of closing",
  },
  {
    id: "finance-absence-is-not-open",
    why: "the lock is enforced per period row, so a month with no row has never been opened "
      + "-- a board that implied the absent months were open would say the opposite of true",
    file: "src/app/finance/page.tsx",
    from: '            {text("finance.absenceMeansNeverOpened")}',
    to: "            {null}",
    grep: "has never been opened",
  },
  {
    id: "membership-blocks-ask-their-own-gate",
    why: "three permissions, three blocks -- a reader may hold the person read and none of "
      + "MOD-017, and 'this member has no invoices' is a different fact from 'you may not "
      + "see them'",
    file: "src/components/membership-panels.tsx",
    // Repointed: the anchor went stale when the code around it moved.
    from: "  if (answer.allowed) return <>{children}</>;",
    to: "  if (true) return <>{children}</>;",
    grep: "is told each block is refused",
  },
  {
    id: "membership-money-uses-the-currency-exponent",
    why: "an amount is an integer count of minor units and JOD has three of them, so a "
      + "hard-coded /100 renders 45.000 dinars as 450.00 -- and every assertion about the "
      + "word 'price' passes either way",
    // **Repointed: the membership price moved to `MoneyValue` and this still broke the
    // helper beside it.** `money()` is live on the Command Center and the cash board, so the
    // mutation applied cleanly and the row it is asserted against was rendered by something
    // else -- reported as UNCAUGHT, which reads as a gap and was a stale aim. That is this
    // file's own tell: a mutation whose test asserts the rendered half while the mutation
    // edits the other half.
    file: "src/components/ds/money-value.tsx",
    from: "  const { code, sign, major, minor } = rawParts(amountMinor, currency, numbering);",
    to: '  const code = currency, sign = amountMinor < 0 ? "-" : "",\n'
      + '    major = String(Math.trunc(Math.abs(amountMinor) / 100)),\n'
      + '    minor = `.${String(Math.abs(amountMinor) % 100).padStart(2, "0")}`;',
    grep: "renders the agreed price",
  },
  {
    id: "membership-credit-note-is-not-outstanding",
    why: "a credit note is stored positive and is a reduction, so counting one as outstanding "
      + "moves the total the wrong way by twice its value",
    file: "src/lib/membership.ts",
    from: '  return invoice.document_kind === "invoice" && !SETTLED.has(invoice.payment_status);',
    to: "  return !SETTLED.has(invoice.payment_status);",
    runner: "vitest",
    grep: "never counts a credit note",
  },
  {
    id: "membership-facts-are-label-and-value-rows",
    why: "`.facts` is a two-column grid whose items are the dt and dd themselves, so a div "
      + "around each pair is valid HTML that puts both labels on one row with their values "
      + "beneath -- a rendering defect no assertion about the text can see",
    file: "src/components/membership-panels.tsx",
    from: '        <dt className="muted">{text("membership.accounts")}</dt>',
    to: '        <div><dt className="muted">{text("membership.accounts")}</dt></div>\n'
      + '        <div><dt className="muted">{text("membership.outstanding")}</dt></div>',
    grep: "label and value, not side by side",
  },
  {
    id: "membership-two-numbers-disclosed",
    why: "two human-facing member numbers from two modules sit on one page with nothing "
      + "relating them, and a front desk asking for 'your membership number' can be handed "
      + "either",
    file: "src/components/membership-panels.tsx",
    from: '        {text("membership.twoNumbers")}',
    to: "        {null}",
    grep: "two member numbers on this page",
  },
  {
    id: "staff-unknown-is-not-no-access",
    why: "a reader who may not see logins, and a permitted read that answered nothing, are "
      + "both 'nobody looked' -- and 'checked and clean' is the one answer that is always "
      + "wrong about a departed employee's access",
    file: "src/lib/staff.ts",
    from: '  if (seen === null) return "unknown";',
    to: "",
    grep: "cannot see logins is told so",
  },
  {
    id: "staff-ended-with-access-is-the-finding",
    why: "an active identity is access whether or not a session is live -- the password "
      + "still works, so the next sign-in opens the product, and reading only the session "
      + "count would call a departed employee clean",
    file: "src/lib/staff.ts",
    from: '  const live = seen.live_sessions > 0 || seen.status === "active";',
    to: "  const live = seen.live_sessions > 0;",
    grep: "four standings apart",
  },
  {
    id: "staff-reach-is-not-the-home-club",
    why: "a tenant-scoped assignment already covers every named one, so rendering the named "
      + "scopes beside it understates what somebody can reach",
    file: "src/lib/staff.ts",
    from: '  if (live.some((one) => one.scope_type === "tenant")) return { kind: "tenant" };',
    to: "",
    grep: "clubs a role reaches",
  },
  {
    id: "staff-primary-role-is-the-broadest",
    why: "which assignment is the job decides both halves of ADM-STF-02, and an unordered "
      + "answer makes the planner the author -- the two halves would change between reads",
    file: "src/lib/staff.ts",
    from: "    const breadth = (SCOPE_BREADTH[b.scope_type] ?? 0) "
      + "- (SCOPE_BREADTH[a.scope_type] ?? 0);\n    if (breadth !== 0) return breadth;",
    to: "",
    runner: "vitest",
    grep: "broadest scope",
  },
  {
    id: "staff-lapsed-assignment-carries-nothing",
    why: "a revoked role must not be credited with the permission it used to carry, which "
      + "is what the whole sensitive-grants block is read for",
    file: "src/lib/staff.ts",
    from: "  const live = assignments.filter((one) => one.live);\n  return catalog",
    to: "  const live = assignments;\n  return catalog",
    runner: "vitest",
    grep: "lapsed assignment",
  },
  {
    id: "staff-unreachable-grant-is-marked",
    why: "a privileged permission needs assurance level 3, which nobody in this build can "
      + "reach, so drawing it as held says somebody can do something no session can",
    file: "src/lib/staff.ts",
    from: '  if (permission.required_aal > reachableAal) return "unreachable";',
    to: "",
    runner: "vitest",
    grep: "only a passkey sign-in can use",
  },
  {
    id: "rota-shows-both-a-booking-and-its-exception",
    why: "the canvas's own requirement and the reason the screen exists: a booking inside a "
      + "day off is flagged rather than silently honoured or silently dropped, because the "
      + "member on the other end has already been told a time",
    file: "src/lib/rota.ts",
    from: `    return here.some((one) => one.conflicts_with_availability)
      ? "bookedConflict"
      : "booked";`,
    to: '    return "booked";',
    runner: "vitest",
    grep: "shows BOTH where a booking sits inside an exception",
  },
  {
    id: "rota-an-exception-is-not-quietly-open",
    why: "an hour a break or a day off removes must not read as available, or the grid is "
      + "the rota lying about who is working",
    file: "src/lib/rota.ts",
    from: "  if (removed) return \"exception\";",
    to: "",
    runner: "vitest",
    grep: "is an exception where a break or a day off removes the time",
  },
  {
    id: "rota-a-cell-counts-only-its-own-day",
    why: "a session on Friday marking Tuesday's cell booked would make every column the "
      + "same, and the grid is addressed by day and hour together",
    file: "src/lib/rota.ts",
    from: "    (one) => one.local_date === day.date\n      && overlaps(",
    to: "    (one) => overlaps(",
    runner: "vitest",
    grep: "only counts sessions on that day",
  },
  {
    id: "rota-nothing-to-draw-is-not-a-grid",
    why: "twenty-four rows of \"not working\" for a room nobody wrote a rota for reads as a "
      + "studio that can never be booked, which is the opposite of true",
    file: "src/lib/rota.ts",
    from: "  if (edges.length === 0) return null;",
    to: "  if (edges.length === 0) return { first: 0, last: 23 };",
    runner: "vitest",
    grep: "is null where there is nothing at all to draw",
  },
  {
    id: "freeze-both-ends-of-the-span-are-counted",
    why: "`freeze_membership` stores `planned_ends_on = starts_on + days - 1`, so a freeze "
      + "from the first to the first is one day -- treating the pair as exclusive spends "
      + "somebody's annual allowance a day at a time, in the direction nobody checks",
    file: "src/lib/freeze.ts",
    from: "  return span + 1;",
    to: "  return span;",
    runner: "vitest",
    grep: "counts both ends",
  },
  {
    id: "freeze-the-start-window-is-named-before-the-allowance",
    why: "the order of refusals is the server's, so a form that checked the allowance first "
      + "would tell somebody to shorten a freeze whose date the server was going to refuse "
      + "anyway -- two wrong instructions for one mistake",
    file: "src/lib/freeze.ts",
    from: '  if (!startIsAllowed(from, allowance.may_start_between)) {\n    return "freeze.startOutsideWindow";\n  }',
    to: "",
    runner: "vitest",
    grep: "names the start window before the allowance",
  },
  {
    id: "freeze-a-step-up-is-offered-rather-than-a-button-that-fails",
    why: "every other write form in this app is absent because a button that answered 403 "
      + "is worse than its absence; what makes this one buildable is the offer, so a block "
      + "that rendered the form regardless would be the thing the whole rule is against",
    file: "src/components/membership-panels.tsx",
    from: '      ) : affordance === "form" ? (',
    to: '      ) : true ? (',
    runner: "playwright",
    grep: "offers the step-up rather than a button",
  },
  {
    id: "freeze-a-contract-that-forbids-it-gets-no-step-up",
    why: "a step-up cannot grant what `check_freeze` refuses outright, so offering one for a "
      + "contract with no allowance sends somebody to find a second factor that changes "
      + "nothing -- the member record's own rule about a health field, applied to a write",
    // **Moved from the component to the decision, because the branch was unreachable.**
    // The fixture's contract allows thirty days, so the component's no-allowance path never
    // rendered and deleting it passed a green suite. A decision is testable where a rendered
    // branch is not, which is the remedy the rules file states for this exact shape.
    file: "src/lib/freeze.ts",
    from: '  if (!allowance.allows_freezing) return "no_allowance";',
    to: "",
    runner: "vitest",
    grep: "offers neither where the contract forbids freezing",
  },
  {
    id: "cash-the-count-is-scaled-to-the-stored-minor-units",
    why: "JOD is stored in fils and shown with two decimals, so reading a 135.50 count as "
      + "13550 makes it 13.55 and posts a 121.95 shortfall to suspense -- on the one screen "
      + "whose entire job is the difference between two numbers",
    file: "src/lib/cash.ts",
    from: "  return shown * 10 ** (storageDigits - displayDigits);",
    to: "  return shown;",
    runner: "vitest",
    grep: "scales what is shown to what is stored",
  },
  {
    id: "cash-the-expected-figure-is-shown-before-the-count",
    why: "the canvas is explicit that this is an accuracy control rather than a fraud one, "
      + "and a screen that revealed the figure after the count would be a different control "
      + "with the same layout",
    file: "src/app/payments/cash/page.tsx",
    from: '          <dt className="ds-cash-total">{text("cash.expected")}</dt>',
    to: '          <dt className="ds-cash-total">{""}</dt>',
    runner: "playwright",
    grep: "shows the expected figure before anything is counted",
  },
  {
    id: "cash-a-difference-asks-for-a-sentence-before-the-submit",
    why: "the reason is a field somebody fills while looking at the difference, not a "
      + "refusal they discover by pressing a button -- and this build demands one for any "
      + "difference at all, which is stricter than the canvas's 2.00 threshold",
    file: "src/app/payments/cash/close-form.tsx",
    from: "  const out = gap !== null && gap !== 0;",
    to: "  const out = false;",
    runner: "playwright",
    grep: "the variance appears as the count is typed",
  },
  {
    id: "rota-the-form-is-gated-on-the-write-not-the-read",
    why: "every other write surface in this app is absent because a button that answered "
      + "403 is worse than its absence, so a form rendered for a reader who may not change "
      + "a rota is the thing that principle exists to prevent",
    file: "src/app/rota/page.tsx",
    from: '  const mayWrite = (await gate("scheduling.availability.write")).allowed;',
    to: "  const mayWrite = true;",
    runner: "playwright",
    grep: "a reader who may not change a rota is given no form at all",
  },
  {
    id: "rota-an-empty-field-is-named-by-the-server",
    why: "the browser refuses an empty required field first, so the server-side check is "
      + "reached only by a client that is not a browser -- and it is the one that matters, "
      + "because `window_kind = 'time_off'` carries a schema constraint that a missing "
      + "reason violates with a 500-shaped message rather than a named field",
    file: "src/app/rota/actions.ts",
    from: "  if (Object.keys(missing).length > 0) return { ...IDLE, missing, echo };",
    to: "",
    runner: "playwright",
    grep: "names the field it needs rather than refusing the whole form",
  },
  {
    id: "rota-a-write-the-page-does-not-show-is-a-reader-misled",
    why: "a write whose own page still shows the old rota tells a reader the product did "
      + "not work, and the next thing they do is write it again",
    file: "src/app/rota/actions.ts",
    from: '    revalidatePath("/rota");\n    return { ...IDLE, message: "rota.added" };',
    to: '    return { ...IDLE, message: "rota.added" };',
    runner: "playwright",
    grep: "writes a day off, shows it on the grid, and takes it back",
  },
  {
    id: "rota-the-week-grid-is-contained-not-pinned",
    why: "a scroller with `contain: layout` around a table pinned to its container reports "
      + "zero document overflow and has nothing to scroll, so the columns are clipped and "
      + "unreachable while every assertion about text still passes -- the state that shipped "
      + "on /permissions, and the reason this property is asserted from both sides",
    file: "src/app/globals.css",
    from: "  min-inline-size: 64rem;\n  table-layout: fixed;",
    to: "  table-layout: fixed;",
    runner: "playwright",
    grep: "the week grid really scrolls inside itself",
  },
  {
    id: "rota-the-week-grid-does-not-push-the-page-sideways",
    why: "a week grid is 64rem wide by design and a genuine scroll container's overflow still "
      + "reaches the document root, so without the containment boundary the page scrolled "
      + "sideways by 95px at phone width and hid its own right-hand edge",
    file: "src/app/globals.css",
    from: "at a time and re-measuring, not by reading the stylesheet. */\n  contain: layout;",
    to: "at a time and re-measuring, not by reading the stylesheet. */",
    runner: "playwright",
    // **The pair of properties is caught by a pair of tests, and this grep was first pointed
    // at the wrong one of them.** Removing the boundary leaves the region scrolling exactly as
    // before -- that test stayed green and the sweep reported a gap. The test that sees this is
    // the sideways sweep, which is the whole reason both sides are asserted.
    grep: "the availability grid does not scroll sideways",
  },
  {
    id: "attendance-hour-axis-is-a-clock",
    why: "the axis is the one place a 12-hour form would put \"6 AM\" under a heading whose "
      + "other end reads 22:00, and ADM-RPT-04's whole output is an hour",
    file: "src/lib/reports.ts",
    from: 'return `${String(hour).padStart(2, "0")}:00`;',
    to: "return `${hour}:00`;",
    runner: "vitest",
    grep: "padded 24-hour",
  },
  {
    id: "attendance-empty-hour-is-a-mark",
    why: "an hour nobody came in must be drawn at the baseline: an absent bar and a bar "
      + "nobody can see are the same to a reader, and \"nothing before seven\" is a reading "
      + "this chart exists for",
    file: "src/lib/reports.ts",
    from: "  return Math.max(2, Math.round((entries / peak) * 100));",
    to: "  return Math.round((entries / peak) * 100);",
    runner: "vitest",
    grep: "empty hour as a mark",
  },
  {
    id: "attendance-no-peak-is-not-zero-per-cent",
    why: "nobody came in at all is a club that was shut; rendering 0% would read as "
      + "\"this hour is quiet\", which is MOD-011's empty-window rule in a report",
    file: "src/lib/reports.ts",
    from: "  return bp === null ? null : Math.round(bp / 100);",
    to: "  return Math.round((bp ?? 0) / 100);",
    runner: "vitest",
    grep: "no percentage where there is no peak",
  },
  {
    id: "attendance-sunday-is-six",
    why: "0 is Monday in MOD-019's rota numbering, so a Sun-Thu range written as 0-4 is "
      + "Mon-Fri -- a whole day of the chart, silently",
    file: "src/lib/reports.ts",
    from: '{ key: "sun-thu", label: "attendanceReport.sunThu", days: [6, 0, 1, 2, 3] }',
    to: '{ key: "sun-thu", label: "attendanceReport.sunThu", days: [0, 1, 2, 3, 4] }',
    runner: "vitest",
    grep: "five days and differ",
  },
  {
    id: "device-label-parity",
    why: "the fixture's device label must equal the app's, or every sign-in is challenged and "
      + "the suite spends a single-use recovery code per run",
    file: "tests/e2e/device.mjs",
    from: 'return `web:${createHash("sha256")',
    to: 'return `browser:${createHash("sha256")',
    runner: "vitest",
    grep: "device label",
  },
  {
    id: "ds-button-href-underlined",
    why: "`href` renders a real anchor and the global `a` rule sets only the colour, so every "
      + "non-link button with one rendered underlined -- a button that looks like a link, "
      + "which the source forbids in as many words",
    file: "src/components/ds/button.tsx",
    from: '    textDecoration: "none",',
    to: "",
    runner: "vitest",
    grep: "not underlined when",
  },
  {
    id: "ds-field-mark-needs-a-message",
    why: "a control marked only by its message slot cannot be marked by a panel beside it, "
      + "so the sentence ends up rendered twice under one field",
    file: "src/components/ds/field.tsx",
    from: '      <div className="ds-field-control" data-message={marked ?? shown?.kind}>',
    to: '      <div className="ds-field-control" data-message={shown?.kind}>',
    runner: "vitest",
    grep: "marks the control and puts nothing",
  },
  {
    id: "strip-never-seen-is-not-degraded",
    why: "an in-service reader that has never reported is exactly as unusable as one that "
      + "died this morning, and the fleet board's `blocks_operation` deliberately excludes it "
      + "because nobody can be paged about when it stopped",
    file: "src/lib/device-strip.ts",
    from: '  return device.reachability === "online" ? "working" : "degraded";',
    to: '  return "working";',
    runner: "vitest",
    grep: "degraded for an in-service device that has never reported",
  },
  {
    id: "strip-maintenance-reads-as-broken",
    why: "somebody took it out of service, which is the reason it is silent, and reporting "
      + "that as a fault sends them to a device they unplugged",
    file: "src/lib/device-strip.ts",
    from: '  if (device.state === "maintenance") return "paused";',
    to: "",
    runner: "vitest",
    grep: "paused even if the server calls it blocking",
  },
  {
    id: "strip-all-well-is-the-inverse",
    why: "two out-of-service readers raise no attention, so a strip that inverted that said "
      + "'everything this desk needs is responding' directly above both of them",
    file: "src/lib/device-strip.ts",
    from: '  return devices.length > 0 && devices.every((d) => stripState(d) === "working");',
    to: "  return devices.length > 0 && !needsAttention(devices);",
    runner: "vitest",
    grep: "all is well only when every device is working",
  },
  {
    id: "strip-order-is-the-server-s",
    why: "four rows above a working screen and a receptionist reads the top one -- a dead "
      + "reader sorted under three healthy devices is hardware failing silently with steps",
    file: "src/lib/device-strip.ts",
    from: "  return [...devices].sort((a, b) => RANK[stripState(a)] - RANK[stripState(b)]);",
    to: "  return [...devices];",
    runner: "vitest",
    grep: "puts what is broken above what is fine",
  },
  {
    id: "strip-invents-a-fallback",
    why: "a fallback pointing at a capability this product lacks is worse than none: a "
      + "receptionist following it stops twice, once at the hardware and once at the advice",
    file: "src/lib/device-strip.ts",
    from: "  return FALLBACK[device.kind] ?? null;",
    to: '  return FALLBACK[device.kind] ?? "strip.fallback.scanner";',
    runner: "vitest",
    grep: "says there is none rather than inventing one",
  },
  {
    id: "strip-refusal-is-silence",
    why: "a strip that rendered nothing for a session without the device read is hardware "
      + "failing silently with the silence built into the product",
    file: "src/components/device-strip.tsx",
    from: "          {text(gateMessage(may))} {text(\"strip.notPermitted\")}",
    to: '          {""}',
    runner: "playwright",
    grep: "refused rather than silent",
  },
  {
    id: "desk-button-outside-the-window",
    why: "`may_check_in` refuses outside the check-in window, so a button offered for a class "
      + "tomorrow answers 409 -- a button that answered 403 is worse than its absence",
    file: "src/lib/desk.ts",
    from: '  return checkinWindow(booking, now) === "open";',
    to: "  return true;",
    runner: "vitest",
    grep: "withholds it outside the window",
  },
  {
    id: "desk-unreadable-window-reads-open",
    why: "failing toward offering a control the module will refuse is the direction the whole "
      + "function exists to avoid",
    file: "src/lib/desk.ts",
    from: '  if (Number.isNaN(opens) || Number.isNaN(closes)) return "closed";',
    to: '  if (false) return "closed";',
    runner: "vitest",
    grep: "treats a window it cannot read as closed",
  },
  {
    id: "desk-countdown-has-no-window",
    why: "'2,266 minutes to go' for a class tomorrow is arithmetic that is correct and a "
      + "sentence that is absurd, and only looking at the page can see it",
    file: "src/lib/desk.ts",
    from: "  if (minutes < 0 || minutes > COUNTDOWN_WINDOW_MINUTES) return null;",
    to: "  if (minutes < 0) return null;",
    runner: "vitest",
    grep: "says nothing about a class tomorrow",
  },
  {
    id: "desk-release-reads-as-absence",
    why: "MOD-020's worst shipped defect was exactly this collapse: every member of a "
      + "cancelled class recorded absent, with a fee and a strike",
    file: "src/lib/desk.ts",
    from: '  if (booking.state === "released" || booking.state === "session_cancelled") {\n    return "released";\n  }',
    to: '  if (false) {\n    return "released";\n  }',
    runner: "vitest",
    grep: "keeps a gym cancellation apart",
  },
  {
    id: "desk-order-is-booking-order",
    why: "four minutes from the start a receptionist is looking for who has not arrived, and "
      + "the rows they want out of the way are the ones already in the room",
    file: "src/lib/desk.ts",
    from: "    const byGroup = GROUP[rowState(a)] - GROUP[rowState(b)];",
    to: "    const byGroup = 0;",
    runner: "vitest",
    grep: "puts the people who have not arrived first",
  },
  {
    id: "desk-presence-counts-the-roster",
    why: "a class with six free seats is twelve of eighteen, not twelve of twelve -- the "
      + "denominator is MOD-019's capacity and the roster has no cached total",
    file: "src/lib/desk.ts",
    from: "    places: roster.places,",
    to: "    places: roster.bookings.length,",
    runner: "vitest",
    grep: "counts who is here against the session",
  },
  {
    id: "ds-touch-floor-scoped-to-root",
    why: "44px on Touch is the minimum target rather than a style, and a rule matching only "
      + "`<html>` leaves a screen that sets its own density with a 36px button",
    file: "src/app/globals.css",
    from: '[data-density="touch"] .ds-button,\n[data-density="spacious"] .ds-button {',
    to: ':root[data-density="touch"] .ds-button,\n:root[data-density="spacious"] .ds-button {',
    // **Not the browser test, which measures a button that is `lg` anyway.** `BUTTON_HEIGHT`
    // makes `lg` 44px by itself, so FD-06's control clears the floor whichever selector is
    // live -- the sweep said so by coming back uncaught, which is the right answer and not a
    // gap. The property this rule carries is that a *screen* can set the density at all, and
    // the structural assertion is what proves it.
    runner: "node",
    grep: "matches a screen.s own wrapper",
  },
  {
    id: "walk-in-stale-answer-lands",
    why: "a reply about a number the desk has already edited would mark a clear number as "
      + "duplicated, or clear a duplicated one -- the race the derivation exists to make "
      + "impossible rather than guard",
    file: "src/lib/walk-in.ts",
    from: '  if (answer === null || answer.value !== value) return { kind: "checking", value };',
    to: '  if (answer === null) return { kind: "checking", value };',
    runner: "vitest",
    grep: "checking until an answer about THIS value",
  },
  {
    id: "walk-in-failed-check-reads-as-clear",
    why: "a check the server could not be asked is not a check that passed, and treating the "
      + "two alike turns a network blip into a silent duplicate",
    file: "src/lib/walk-in.ts",
    from: '  if (state.kind === "failed") {\n    return isAbout(state, value) && acknowledgedValue === value;\n  }',
    to: "  if (state.kind === \"failed\") return true;",
    runner: "vitest",
    grep: "holds a check that could not run",
  },
  {
    id: "walk-in-dismissal-outlives-its-number",
    why: "'different person' answers one number, and a dismissal that survived an edit would "
      + "hide the interruption for whatever is typed next",
    file: "src/lib/walk-in.ts",
    from: "  if (acknowledgedValue === value) return null;",
    to: "  if (acknowledgedValue !== null) return null;",
    runner: "playwright",
    grep: "acknowledges one number and not the next one",
  },
  {
    id: "walk-in-field-is-not-marked",
    why: "the border is how the field itself says the number it holds is already somebody's, "
      + "and a panel below with an unmarked control above it leaves the eye in the wrong place",
    file: "src/app/members/new/walk-in-form.tsx",
    from: '        marked={duplicate !== null && !state.missing.phone ? "warning" : undefined}',
    to: "        marked={undefined}",
    runner: "playwright",
    grep: "acknowledges one number and not the next one",
  },
  {
    id: "walk-in-add-member-shown-to-a-denied-reader",
    why: "a button that answers 403 is worse than its absence, and gateVerdict is what tells "
      + "'a stronger sign-in would open this' from 'you may not'",
    file: "src/app/members/page.tsx",
    from: '  const addMember = gateVerdict(mayWrite) === "denied" ? undefined : (',
    to: "  const addMember = (",
    runner: "playwright",
    grep: "no Add member button at all",
  },
  {
    id: "denial-real-code-reaches-a-routine-reader",
    why: "the whole screen: a restricted refusal's real code is the fact paragraph 1944 "
      + "withholds, and `sayFor` is what turns it into a sentence -- falling back to the "
      + "public prose for every code would put the real reason on a password-only desk",
    file: "src/lib/denial.ts",
    from: "  return SAY[code] ?? null;",
    to: '  return SAY[code] ?? SAY["see_front_desk"]!;',
    runner: "vitest",
    grep: "says nothing rather than guessing at a code it does not know",
  },
  {
    id: "denial-override-offered-after-somebody-already-did",
    why: "offering the button again admits the same person twice in an insert-only log, and "
      + "the already-answered check has to come before the permission one or a step-up is "
      + "offered for work that is finished",
    file: "src/lib/denial.ts",
    from: "  if (alreadyOverridden) return \"already\";",
    to: "",
    runner: "playwright",
    grep: "says so rather than offering the button again",
  },
  {
    id: "denial-step-up-offered-where-it-would-not-help",
    why: "a step-up cannot grant a permission nobody holds, so offering one sends somebody "
      + "looking for a second factor that changes nothing",
    file: "src/lib/denial.ts",
    from: '  return gate.verdict === "needs_step_up" ? "step_up" : "denied";',
    to: '  return "step_up";',
    runner: "vitest",
    grep: "offers neither where the gate said no",
  },
  {
    id: "denial-override-key-is-not-the-refusal",
    why: "`override_access` answers a repeated key from the row it already wrote, so a key "
      + "that is the same tomorrow records no second admission: the desk is told it worked "
      + "and the access log shows one override for two",
    file: "src/lib/denial.ts",
    from: "  return `override-${decisionId}`;",
    to: "  return `override-by-hand`;",
    runner: "vitest",
    grep: "is a different key for a later refusal",
  },
  {
    id: "denial-badge-renders-the-english-enum",
    why: "`StatusBadge` takes a closed English vocabulary so an engineer cannot invent a "
      + "state, and rendering that enum puts a Latin word in the middle of an Arabic line -- "
      + "which the catalogue parity check is structurally blind to",
    file: "src/components/ds/status-badge.tsx",
    from: "      {abbreviated ?? label ?? status}",
    to: "      {abbreviated ?? status}",
    runner: "playwright",
    grep: "reads in Arabic, including the badge",
  },
  {
    id: "denial-badge-label-unswept",
    why: "the sweep is what stops the next screen shipping an English badge into an Arabic "
      + "page, and a usage check that passes vacuously is the thing it exists to prevent",
    file: "src/app/desk/denials/[personId]/page.tsx",
    from: '<StatusBadge status="Denied" label={text("denial.badge")} />',
    to: '<StatusBadge status="Denied" />',
    runner: "node",
    grep: "carries the word in the reader.s language",
  },
  {
    id: "denial-placeholder-renamed-across-the-catalogue",
    why: "this is the defect that found the check: renaming a placeholder to suit one new "
      + "message took six others with it, and the Command Center answered an error boundary "
      + "for every reader while four test layers stayed green",
    file: "src/i18n/locale.ts",
    from: '"cc.retentionTitle": { one: "{count} membership expires within {days} days",',
    to: '"cc.retentionTitle": { one: "{count} membership expires within {count} days",',
    // **The grep is the call-site half, and pointing it at the other half is what the sweep
    // found.** A rename in one plural form is invisible to a check that unions the forms --
    // which is how the first version of this test was written and how the real defect would
    // have survived it. `fill` picks one form, so the per-form call-site comparison is the
    // only thing that sees this.
    runner: "vitest",
    grep: "is honoured by every call site that passes a literal key",
  },
  {
    id: "denial-placeholder-only-in-one-language",
    why: "a form naming a value the other language's forms do not is a throw only that "
      + "language's readers get, and the catalogue parity check compares key sets rather "
      + "than text",
    file: "src/i18n/locale.ts",
    from: '"denial.beforeYouLead": "Worth asking whether something changed before you lead',
    to: '"denial.beforeYouLead": "Worth asking whether {who} changed before you lead',
    runner: "vitest",
    grep: "names the same values in both languages",
  },
  {
    id: "denial-fill-site-contract-unchecked",
    why: "the call-site half of the same check: a value with no placeholder throws at the "
      + "first render, and nothing static compared the two before this",
    file: "src/app/desk/denials/[personId]/page.tsx",
    from: "                ? text(\"denial.lastVisitToday\")",
    to: "                ? fill(locale, \"denial.lastVisit\", { days: 0 })",
    runner: "vitest",
    grep: "is honoured by every call site that passes a literal key",
  },
  {
    id: "passkey-listing-reads-the-flag-the-level-does-not-follow",
    why: "`BE` at 0x08 is set at creation and never changes, and `factor_for` reads it; `BS` "
      + "at 0x10 flips the first time a keychain syncs. Nothing updates the column after "
      + "enrolment, so reading BS lists an eligible-but-unsynced credential as device-bound "
      + "and reaching level 3 while the sign-in gives level 2",
    file: "src/lib/passkey.ts",
    from: "  return data.length > 32 && (data[32]! & 0x08) !== 0;",
    to: "  return data.length > 32 && (data[32]! & 0x10) !== 0;",
    runner: "vitest",
    grep: "reads backup eligibility from bit",
  },
  {
    id: "passkey-discoverable-not-required",
    why: "the sign-in ceremony deliberately sends no credential list, because allowCredentials "
      + "would name a person's credential ids to anybody who typed their address -- so a "
      + "credential that is not discoverable enrols and can never sign in",
    file: "src/lib/passkey.ts",
    from: '      residentKey: "required",',
    to: '      residentKey: "preferred",',
    runner: "vitest",
    grep: "requires a discoverable credential",
  },
  {
    id: "passkey-user-verification-not-required",
    why: "the backend refuses an assertion whose UV flag is unset, there being no factor name "
      + "for a device that was present with nobody checked -- so asking for it only when "
      + "convenient enrols a credential that can never sign in",
    file: "src/lib/passkey.ts",
    from: '      userVerification: "required",\n    },\n    // No attestation',
    to: '      userVerification: "preferred",\n    },\n    // No attestation',
    runner: "vitest",
    grep: "requires user verification",
  },
  {
    id: "passkey-unverifiable-key-enrolled-anyway",
    why: "`getPublicKey()` is why no CBOR is parsed anywhere here, so a browser without it "
      + "cannot produce a key the server can verify -- enrolling regardless stores a "
      + "credential that fails at every sign-in with nothing saying why",
    file: "src/lib/passkey.ts",
    from: "  if (typeof response.getPublicKey !== \"function\") return { unsupported: true };",
    to: "  if (typeof response.getPublicKey === \"function\" && false) return { unsupported: true };",
    runner: "vitest",
    grep: "says a browser cannot help",
  },
  {
    id: "passkey-level-three-called-unreachable",
    why: "the account page would tell the one session holding the strongest credential in the "
      + "product that its level is one nothing can reach -- the gap note outliving its gap, "
      + "in a sentence shown to the reader it is about",
    file: "src/lib/account.ts",
    from: '  if (aal >= 3) return "hardware";',
    to: "",
    runner: "playwright",
    grep: "reaches the level nothing else can",
  },
  {
    id: "passkey-session-told-it-has-a-fortnight",
    why: "SESSION_LIFETIME gives level 3 fifteen minutes, the shortest of the three, and the "
      + "caption read the password one for it -- so the strongest session was told it had a "
      + "fortnight",
    file: "src/app/account/account-view.tsx",
    from: '                  ? text("account.shortestWindow")',
    to: '                  ? text("account.longWindow")',
    runner: "playwright",
    grep: "reaches the level nothing else can",
  },
  {
    id: "passkey-withdrawal-says-nothing",
    why: "the row that withdraws itself unmounts the button, so a per-row result is a result "
      + "nobody sees -- MOD-007's `revokeDevice` shape, where the most consequential control "
      + "on the surface gave no feedback at all",
    file: "src/app/account/passkey-section.tsx",
    from: "      {withdrawn.message !== null ? (",
    to: "      {false ? (",
    runner: "playwright",
    grep: "is withdrawn by its owner",
  },
  {
    id: "passkey-button-offered-where-the-browser-cannot",
    why: "a control that cannot work is worse than its absence, and here a reader would have "
      + "no way to tell a missing passkey from a browser that cannot ask for one",
    file: "src/app/login/passkey-button.tsx",
    from: "  if (!canCeremony) return null;",
    to: "",
    runner: "playwright",
    grep: "is offered nothing rather than a control",
  },
  {
    id: "passkey-signin-without-an-identifier",
    why: "two fields are needed and only one is obvious, so pressing with nothing typed has "
      + "to say which -- a ceremony that ran and failed would read as a broken passkey",
    file: "src/app/login/passkey-button.tsx",
    from: '      setProblem("passkey.needIdentifier");',
    to: '      setProblem("passkey.signInFailed");',
    runner: "playwright",
    grep: "says which field it needs",
  },
  {
    id: "step-up-keyed-on-reachable-alone",
    why: "`reachable` says a factor in this build reaches the level; it does not say this "
      + "endpoint can. `/auth/step-up` takes a password or a recovery code and neither gets "
      + "past 2, so keying the page on `reachable` offers a credential prompt whose correct "
      + "answer is still refused -- which is worse than the refusal it replaced",
    file: "src/app/step-up/page.tsx",
    from: '  if (verdict === "needs_a_passkey_sign_in") {',
    to: "  if (!asked.reachable) {",
    runner: "playwright",
    grep: "a level this page cannot raise names the door that can",
  },
  {
    id: "step-up-ceiling-raised-past-what-it-accepts",
    why: "the ceiling is what `complete_step_up` accepts, so raising it past 2 makes the "
      + "page offer a field for a level no password and no recovery code can reach",
    file: "src/lib/step-up.ts",
    from: "  if (!asked.reachable || needed > STEP_UP_CEILING) return \"needs_a_passkey_sign_in\";",
    to: "  if (!asked.reachable) return \"needs_a_passkey_sign_in\";",
    runner: "vitest",
    grep: "names the passkey door for a level this endpoint cannot reach",
  },
  {
    id: "step-up-missing-level-fails-open",
    why: "a build that stopped sending `required_aal` would otherwise silently offer the "
      + "credential prompt for every class, which is the one failure this module exists to "
      + "prevent -- so an absent level is beyond this page rather than within it",
    file: "src/lib/step-up.ts",
    from: '  const needed = typeof asked.required_aal === "number" ? asked.required_aal : Infinity;',
    to: '  const needed = typeof asked.required_aal === "number" ? asked.required_aal : 0;',
    runner: "vitest",
    grep: "treats a missing required level as beyond this page",
  },
  {
    id: "passkey-recovery-sentence-keyed-the-wrong-way-round",
    why: "the two sentences are opposites -- one says codes are the only way back and one "
      + "says a passkey already is -- so a reader with no passkey would be told they cannot "
      + "be locked out, which is the one reading that makes spending the last code safe. "
      + "**A `passkeys.length > 0` mutation would not do**: the reader has none at all, so "
      + "both expressions agree and nothing would be proved, which is this file's own rule "
      + "that a weakening is caught only if it admits the row",
    file: "src/app/account/account-view.tsx",
    from: "          {text(hasUsableKey(passkeys)",
    to: "          {text(!hasUsableKey(passkeys)",
    runner: "playwright",
    grep: "say they are the only way back, which the lead used to get wrong",
  },
  {
    id: "cancel-term-sentence-for-everybody",
    why: "ADM-MSH-07's commitment line is true of its own member and false of three others:"
      + " a rolling contract has no commitment, a served term no longer binds, and a"
      + " contract with no buy-out cannot be left early at all. One sentence for all four"
      + " tells three members something untrue about what they are agreeing to",
    file: "src/lib/cancellation.ts",
    from: '  if (!quote.commitment.leaving_early) return "served";\n'
      + '  return quote.commitment.may_leave_early ? "leaving_early" : "held_to_term";',
    to: '  return "leaving_early";',
    grep: "says the term holds where the contract sells no way out of it",
    runner: "vitest",
  },
  {
    id: "cancel-zero-fee-line",
    why: "a line reading \"leaving the commitment early \u00b7 0.00\" states a price for"
      + " something that is not on offer, in a money column where a zero is a figure",
    file: "src/lib/cancellation.ts",
    from: "  if (quote.fee_parts.period_minor !== 0) {",
    to: "  if (true) {",
    grep: "leaves out a part that is not charged",
    runner: "vitest",
  },
  {
    id: "cancel-dormancy-from-absent-data",
    why: "`days_since` is null at a club with no readers as readily as for a member who"
      + " never came, so reading absence as dormancy tells a receptionist somebody stopped"
      + " attending on the strength of there being no turnstile -- MOD-014's rule that an"
      + " unknown birth date is not a minor, in the other direction",
    file: "src/lib/cancellation.ts",
    from: "    daysSinceLastVisit !== null && daysSinceLastVisit >= DORMANT_AFTER_DAYS;",
    to: "    daysSinceLastVisit === null || daysSinceLastVisit >= DORMANT_AFTER_DAYS;",
    grep: "treats an unknown last visit as not dormant",
    runner: "vitest",
  },
  {
    id: "cancel-freeze-offered-without-one",
    why: "offering a freeze on a contract that allows none points at a form that cannot"
      + " accept them, which is the freeze block's own `no_allowance` rule from the other"
      + " side",
    file: "src/lib/cancellation.ts",
    from: "  if (!quote.freeze_is_an_alternative) return null;",
    to: "  if (false) return null;",
    grep: "offers nothing where the contract allows no freezing",
    runner: "vitest",
  },
  {
    id: "cancel-step-up-for-an-impossible-act",
    why: "a membership already cancelled cannot be cancelled by anybody, so offering a"
      + " step-up sends somebody to find a second factor that changes nothing",
    file: "src/lib/cancellation.ts",
    from: '  if (!quote.may_cancel) return "cannot";',
    to: '  if (false) return "cannot";',
    grep: "says so where the membership cannot be cancelled by anybody",
    runner: "vitest",
  },
  {
    id: "commit-line-reads-the-wrong-flag",
    why: "this is the defect, restored: `leaving_early` is false for a member a contract"
      + " forbids leaving early, because the lifecycle pushes the effective date to the term"
      + " end -- so keyed on it, `held_to_term` is unreachable and a member nine months into"
      + " a twelve-month commitment is told it has been served",
    file: "src/lib/cancellation.ts",
    from: '  if (!quote.commitment.term_is_running) return "served";',
    to: '  if (!quote.commitment.leaving_early) return "served";',
    grep: "says the term holds where the contract sells no way out of it",
    runner: "vitest",
  },
  {
    id: "commit-freeze-offer-reads-the-wrong-flag",
    why: "the same flag one function over, where it withheld the freeze offer from the only"
      + " member whose commitment a freeze would preserve",
    file: "src/lib/cancellation.ts",
    from: "  const committed = quote.commitment.term_is_running;",
    to: "  const committed = quote.commitment.leaving_early;",
    grep: "keeps the commitment half for the member who is held to one",
    runner: "vitest",
  },
  {
    id: "commit-quote-admits-an-impossible-state",
    why: "the guard that would have caught the dead branch: without it a hand-written quote"
      + " can carry `leaving_early` beside `may_leave_early: false`, which the server cannot"
      + " emit, and a unit test then proves a branch nothing reaches",
    file: "tests/component/cancellation.test.ts",
    from: '  if (!c.may_leave_early && c.leaving_early) {\n'
      + '    throw new Error(',
    to: '  if (false) {\n'
      + '    throw new Error(',
    grep: "cannot be given a commitment the server would never send",
    runner: "vitest",
  },
  // ---- MOD-027's board and table (ADM-CRM-01, ADM-CRM-02) ----
  {
    id: "lead-masked-name-is-a-marker",
    why: "`GET /people/names` returns the *marker* for a field this session cannot read, not "
      + "a null -- so without `isWithheld` the board printed `***` as though somebody were "
      + "called that, and its own step-up offer never appeared because nothing looked "
      + "withheld. Found by the browser spec, which is the layer that sees a rendered value",
    file: "src/app/leads/page.tsx",
    from: "    return name !== null && !isWithheld(name) ? name : null;",
    to: "    return name;",
    runner: "playwright",
    grep: "step-up that lifts the names",
  },
  {
    id: "lead-board-column-order",
    why: "the five columns are the canvas's own sequence, and a board that drew Joined before "
      + "New would pass five separate visibility checks",
    file: "src/lib/leads.ts",
    from: 'export const BOARD_COLUMNS = ["new", "contacted", "toured", "on_trial", "joined"] as const;',
    to: 'export const BOARD_COLUMNS = ["joined", "on_trial", "toured", "contacted", "new"] as const;',
    runner: "playwright",
    grep: "five columns, in its order",
  },
  {
    id: "lost-list-has-a-chip",
    why: "`GET /crm/leads` took `lost=true` from the day slice 3 landed and nothing on "
      + "`/leads` sent it, so a refusal was reachable only from its own profile -- the "
      + "\"writer with no reader\" shape at the surface, which this app has recorded twice "
      + "and a tester found both times",
    file: "src/lib/leads-reads.ts",
    from: '  if (params.filter === "lost") query.set("lost", "true");',
    to: "",
    runner: "playwright",
    grep: "is in the table's own Lost list",
  },

  // ---- ADM-CRM-07, mark lost --------------------------------------------------------
  {
    id: "lost-says-the-stage-did-not-move",
    why: "the whole of ADR-0010 D8 is that a sixth stage value would need a backwards edge "
      + "on reopen, which would make `Toured · 6` a count nobody can reconstruct -- so the "
      + "screen says the stage stayed rather than leaving a reader to notice",
    file: "src/app/leads/[leadId]/page.tsx",
    from: "                  {fill(locale, \"lost.stageKept\", { stage })}",
    to: "                  {stage}",
    runner: "playwright",
    grep: "keeps its stage, and the screen says why that matters",
  },
  {
    id: "lost-offers-the-reopen",
    why: "a lost lead with no way back is a record that cannot be corrected, and reopening "
      + "is never gated on the ninety days -- locking it would make a lead marked lost by "
      + "mistake uncorrectable for a quarter on a routine permission",
    file: "src/app/leads/[leadId]/page.tsx",
    from: "                <ReopenForm locale={locale} leadId={leadId} />",
    to: "                {null}",
    runner: "playwright",
    grep: "offers the reopen",
  },
  {
    id: "lost-says-reopening-is-allowed-either-way",
    why: "the ninety days is advisory; a sentence that read as a refusal would send somebody "
      + "away from the one remedy a wrongly-lost lead has",
    file: "src/lib/lost.ts",
    from: '  return recontactable ? "lost.reopenable" : "lost.notYetReopenable";',
    to: '  return "lost.reopenable";',
    runner: "playwright",
    grep: "offers the reopen",
  },
  {
    id: "lost-refuses-with-its-own-sentence",
    why: "`aria-required` announces the reason without refusing the submit, so the server's "
      + "sentence is what a reader acts on -- the branch ADM-MEM-10's native `required` made "
      + "unreachable",
    file: "src/app/leads/[leadId]/actions.ts",
    from: '  if (reason.length === 0) return { ...IDLE, error: "lost.needsAReason" };',
    to: "  if (false) return { ...IDLE, error: \"lost.needsAReason\" };",
    runner: "playwright",
    grep: "refuses with its own sentence when no reason is chosen",
  },
  {
    id: "lost-offers-the-interest-withdrawal",
    why: "`0027` said slice 3 owed this remedy: until it existed, a tick on an interest was "
      + "permanent on a routine permission, which is MOD-013's rule",
    file: "src/app/leads/[leadId]/page.tsx",
    from: "            {lead.interests.map((one) => (\n              <WithdrawInterestForm",
    to: "            {[].map((one) => (\n              <WithdrawInterestForm",
    runner: "playwright",
    grep: "can be taken back, which it could not before this slice",
  },

  // ---- ADM-CRM-06, the conversion quote -------------------------------------------
  {
    id: "convert-discloses-the-list-and-the-discount",
    why: "a heading reading `JOD 49.50` over a plan a tenant prices at `JOD 55.00` is a "
      + "figure a member cannot reconcile, and the fixture's four automatic promotions are "
      + "the ordinary state of a catalogue rather than an edge case",
    file: "src/app/leads/[leadId]/convert/page.tsx",
    from: "            {quote.discount_minor > 0 ? (",
    to: "            {false ? (",
    runner: "playwright",
    grep: "draws the canvas's three money lines",
  },
  {
    id: "convert-claims-nothing-with-a-count-of-zero",
    why: "\"her four class attendances carry over\" is true of Rana and false of a lead who "
      + "has never booked anything; a line reading `0 class attendances` is the confident "
      + "wrong answer MOD-014's own Member 360 was bitten by",
    file: "src/lib/convert.ts",
    from: "  return items.filter((item) => item.count > 0);",
    to: "  return items;",
    runner: "playwright",
    grep: "names what carries over",
  },
  {
    id: "convert-is-reachable-from-the-lead-profile",
    why: "the canvas puts `Convert to member` on the trial card, and a page nothing links to "
      + "is the dead end this app has recorded twice -- on the members list and the staff "
      + "list, both found by an outside tester rather than by a spec",
    file: "src/app/leads/[leadId]/page.tsx",
    from: "            <Link href={`/leads/${leadId}/convert`}>{text(\"trial.convert\")}</Link>",
    to: "            {text(\"trial.convert\")}",
    runner: "playwright",
    grep: "is reachable from the lead profile",
  },
  {
    id: "convert-renders-the-stored-period-as-a-word",
    why: "a vocabulary the backend stores is never a label: `monthly` rendered raw is Latin "
      + "letters in the middle of an Arabic line, which this app has four recorded defects "
      + "from, and `MESSAGE_KEYS` is structurally blind to a string that never became a key",
    file: "src/app/leads/[leadId]/convert/page.tsx",
    from: "                  const key = planName(quote.plan.billing_period);\n"
      + "                  return key === null ? quote.plan.billing_period : text(key);",
    to: "                  return quote.plan.billing_period;",
    runner: "playwright",
    grep: "reads in Arabic, including the stored billing period",
  },
  {
    id: "convert-shape-follows-the-server",
    why: "a contract that does not prorate must not be given a pro-rata line: under the "
      + "`agreement_start` anchor the first period is whole and the figure equals the "
      + "recurring one, so printing it as a proration reads as a coincidence rather than a "
      + "rule",
    file: "src/lib/convert.ts",
    from: "  return quote.prorated ? \"prorated\" : \"full_period\";",
    to: "  return \"prorated\";",
    runner: "vitest",
    grep: "is a full period where the contract does not prorate",
  },

  // **`lead-on-trial-says-why` is deleted, and the harness's diagnosis of it was wrong.**
  // It mutated `columnNote` to return null, which ADR-0010 D7 made the production code: the
  // column is derived from MOD-017 now and carries no reason, so the protection it named does
  // not exist. The sweep reported NOT RUN with "the replacement text is present, so a previous
  // run was killed" -- a true observation and the wrong cause, which is the second reading of
  // that state: a protection retired *into* the mutation's own form looks exactly like a
  // leftover mutation. The message below now names both.
  {
    id: "lead-age-unit",
    why: "the canvas writes both units -- \"open day · 2d\" and \"instagram · 4h\" -- and a "
      + "board that said 48h where it means 2d is a figure a reader has to divide",
    file: "src/lib/leads.ts",
    from: "  if (hours < 24) return fill(locale, \"leads.sinceHours\", { count: hours });",
    to: "  if (hours < 1000) return fill(locale, \"leads.sinceHours\", { count: hours });",
    runner: "vitest",
    grep: "hours below a day and days above it",
  },
  {
    id: "lead-unattributed-source",
    why: "\"where did this come from\" is the question the source-effectiveness report is built "
      + "on, so an unattributed lead is the answer that matters most -- not a blank before a "
      + "separator",
    file: "src/lib/leads.ts",
    from: '  const source = lead.source ?? fill(locale, "leads.noSource", {});',
    to: "  const source = lead.source ?? \"\";",
    runner: "vitest",
    grep: "says so rather than leaving the line half-empty",
  },
  {
    id: "lead-mine-needs-a-person",
    why: "a reader whose sign-in is not linked to a person owns no leads, and an empty board "
      + "with no reason is indistinguishable from an empty queue -- two facts, one of them "
      + "not about the work at all",
    file: "src/app/leads/page.tsx",
    from: "  if (board?.mine_is_zero_without_a_person_record !== undefined) {",
    to: "  if (false) {",
    runner: "playwright",
    grep: "says the reader is nobody",
  },
  {
    id: "lead-stage-is-forward-only",
    why: "`toured` is the last sales stage and the two columns after it are what a membership "
      + "answers, so a backwards or an onward move from there is one the service refuses -- "
      + "\"a button the module will refuse is worse than no button\"",
    file: "src/lib/leads.ts",
    from: '  if (stage === "contacted") return "toured";\n  return null;',
    to: '  if (stage === "contacted") return "toured";\n  return "new";',
    runner: "playwright",
    grep: "no stage move, because the pipeline has no edge",
  },
  {
    id: "lead-owner-control-is-one",
    why: "assigning the owner a lead already has is a 409 -- a write that changed nothing "
      + "would bump the version and read as a handover somebody made -- so an owned lead is "
      + "offered the release and only the release",
    file: "src/app/leads/[leadId]/forms.tsx",
    from: '        label={text(owned ? "lead.formRelease" : "lead.formClaim")}',
    to: '        label={text("lead.formClaim")}',
    runner: "playwright",
    grep: "offered the release and not the claim",
  },
  {
    id: "lead-interest-already-held",
    why: "an interest already recorded cannot be withdrawn, so offering it again is a tick "
      + "that does nothing -- and the remaining one is what makes the form mean something",
    file: "src/app/leads/[leadId]/forms.tsx",
    from: "  const offer = options.filter((one) => !held.includes(one.value));",
    to: "  const offer = [...options];",
    runner: "playwright",
    grep: "already recorded is not offered again",
  },
  {
    id: "lead-empty-timeline-says-why",
    why: "an absent list reads as a lead nobody has spoken to *and* as a screen that failed "
      + "to load, and the first is the fact the cold rule is computed from",
    file: "src/app/leads/[leadId]/page.tsx",
    from: "      {lead.touchpoints.length === 0 ? (",
    to: "      {false ? (",
    runner: "playwright",
    grep: "clock runs from its creation",
  },
  {
    id: "new-lead-clear-panel",
    why: "the clear verdict is the state ADM-CRM-04's canvas actually draws -- \"No existing "
      + "record\" over the mechanism sentence -- so dropping it leaves the one screen whose "
      + "whole subject is a check saying nothing about having run one",
    file: "src/app/leads/new/lead-form.tsx",
    from: '        ) : detection.kind === "clear" && isAbout(detection, value) ? (',
    to: "        ) : false ? (",
    runner: "playwright",
    grep: "the state this canvas draws",
  },
  {
    id: "new-lead-use-person-skips-the-person-write",
    why: "\"that record would open instead of a second one being created\" is the canvas's "
      + "own behaviour, and it works by skipping the person write entirely -- falling through "
      + "creates the duplicate the screen exists to prevent",
    file: "src/app/leads/new/actions.ts",
    from: "  if (chosen.length > 0) return openAgainst(chosen, source, interests, echo);",
    to: "  if (false) return openAgainst(chosen, source, interests, echo);",
    runner: "playwright",
    grep: "opens the lead that already exists",
  },
  {
    id: "new-lead-existing-is-reported",
    why: "a form that said \"the lead is open\" for a record somebody else opened last week "
      + "would be telling a desk they did something they did not do",
    file: "src/app/leads/new/actions.ts",
    from: `    return {
      ...IDLE,
      createdLeadId: String(opened.lead_id),
      openedExisting: opened.existing === true,
    };
  } catch (error) {
    // No person was created here`,
    to: `    return {
      ...IDLE,
      createdLeadId: String(opened.lead_id),
      openedExisting: false,
    };
  } catch (error) {
    // No person was created here`,
    runner: "playwright",
    grep: "opens the lead that already exists",
  },
  {
    id: "new-lead-match-path-needs-its-own-permission",
    why: "opening a lead against an existing person is `crm.lead.write`, which a front desk "
      + "does not hold -- a button that answers 403 is worse than its absence",
    file: "src/app/leads/new/lead-form.tsx",
    from: "              {canOpenLead ? (",
    to: "              {true ? (",
    runner: "playwright",
    grep: "a front desk gets the check and neither write",
  },
  {
    id: "new-lead-board-button-is-gated",
    why: "`people.person.write` is financial class, so the verdict is what tells \"a stronger "
      + "sign-in would open this\" from \"you may not\" -- and a denied reader must get no "
      + "button at all",
    file: "src/app/leads/page.tsx",
    from: '  const addLead = gateVerdict(mayWrite) === "denied" ? undefined : (',
    to: "  const addLead = false ? undefined : (",
    runner: "playwright",
    grep: "no Add a lead button at all",
  },
  {
    id: "new-lead-no-native-constraint",
    why: "a native `required` makes the browser refuse the whole form, and this one has a "
      + "second submit that legitimately needs neither field -- and it also hides the app's "
      + "own sentence behind a bubble in a language this app did not choose",
    file: "src/app/leads/new/lead-form.tsx",
    from: '          id="new-lead-name" name="name" type="text" aria-required="true"',
    to: '          id="new-lead-name" name="name" type="text" required',
    runner: "playwright",
    grep: "opens the lead that already exists",
  },
  {
    id: "new-lead-hold-says-what-is-still-open",
    why: "the create is held for want of a financial permission and the match path is not, so "
      + "a sentence that stopped at \"needs a stronger sign-in\" would send a reader away "
      + "from the one control that works",
    file: "src/app/leads/new/lead-form.tsx",
    from: '            {canOpenLead ? <> {text("newLead.matchPathStillOpen")}</> : null}',
    to: "            {false ? null : null}",
    runner: "playwright",
    grep: "says the match path is still open",
  },
  {
    id: "new-lead-gym-only-stands-alone",
    why: "the server refuses `gym_only` beside the other two, and this app's validation "
      + "handler deliberately names no field -- so a reader who was not told loses the whole "
      + "submit to a 422 that explains nothing",
    file: "src/app/leads/new/lead-form.tsx",
    from: '        note={text("newLead.interestExclusive")}',
    to: "        note={undefined}",
    runner: "playwright",
    grep: "draws the canvas's two optional fields",
  },
  {
    id: "walk-in-no-native-constraint",
    why: "`missingFields` had no reader at all while the two fields carried a native "
      + "`required`: the browser refused the submit and showed its own bubble, so "
      + "`walkIn.nameNeeded` was a branch nothing could render",
    file: "src/app/members/new/walk-in-form.tsx",
    from: '          id="walk-in-name" name="name" type="text" aria-required="true"',
    to: '          id="walk-in-name" name="name" type="text" required',
    runner: "playwright",
    grep: "creates a person with a contact point",
  },
  {
    id: "contact-match-withheld-is-a-marker",
    why: "`GET /people/contact-match` returns the mask *string* for a field this session may "
      + "not read, so a line that printed it would read as somebody called `***` -- and the "
      + "panel would stop telling a desk that the name is withheld rather than absent",
    file: "src/components/contact-match-line.tsx",
    from: '  const withheld = shown === null || shown === "***";',
    to: "  const withheld = false;",
    runner: "playwright",
    grep: "offers three answers",
  },
  {
    id: "choice-chips-mark-shape",
    why: "the canvas draws `SOURCE \u00b7 OPTIONAL` and `INTEREST \u00b7 OPTIONAL` with one "
      + "treatment, and this rendered \"Interest optional\" beside \"Source (optional)\" "
      + "until somebody read the page -- two spellings of one meaning on one screen",
    file: "src/components/ds/choice-chips.tsx",
    from: "          <span className=\"ds-field-mark\">{` (${mark})`}</span>",
    to: '          <span className="ds-field-mark"> {mark}</span>',
    runner: "playwright",
    grep: "marks them as optional",
  },
  {
    id: "trial-band-outranks-the-cold-mark",
    why: "a trialist is not somebody nobody has rung, and `RecordHeader` draws one band -- so "
      + "a board that showed the cold mark on a running trial would hide the clock that "
      + "matters behind one that does not",
    file: "src/app/leads/[leadId]/page.tsx",
    from: "  const band = running !== null",
    to: "  const band = false",
    runner: "playwright",
    grep: "the band is the day of the trial",
  },
  {
    id: "trial-metric-row-is-the-trials-four",
    why: "ADM-CRM-05 draws four cells and they are not the sales four: a row that showed both "
      + "would be eight where the canvas draws four, and the stage and the last contact are "
      + "questions a trial has already answered",
    file: "src/app/leads/[leadId]/page.tsx",
    from: "      {running === null ? (\n        <section className=\"metrics\"",
    to: "      {true ? (\n        <section className=\"metrics\"",
    runner: "playwright",
    grep: "the metric row is the trial's four cells",
  },
  {
    id: "trial-engagement-is-a-word",
    why: "a vocabulary the backend stores is never a label, which this app has five recorded "
      + "defects from -- and the band is the one cell on this card whose value is an enum",
    file: "src/app/leads/[leadId]/page.tsx",
    from: "              const key = engagementWord(running.engagement);\n"
      + "              return key === null ? running.engagement : text(key);",
    to: "              return running.engagement;",
    runner: "playwright",
    grep: "four visits in six days reads as high use",
  },
  {
    id: "trial-urgency-says-which-of-three",
    why: "\"Her trial ends tomorrow\" is the canvas's own sentence and the day it ends is the "
      + "sharper of the two; a single countdown would read \"1 day left\" on the last day",
    file: "src/lib/trial.ts",
    from: '  if (card.ends_tomorrow) return "trial.endsTomorrow";',
    to: '  if (false) return "trial.endsTomorrow";',
    runner: "vitest",
    grep: "the urgency line has three states",
  },
  {
    id: "trial-nobody-in-is-its-own-sentence",
    why: "\"nobody has been in\" is a different conversation from \"they came once\", and the "
      + "softer sentence would have somebody ring a lead to ask how they found a gym they "
      + "have never walked into",
    file: "src/lib/trial.ts",
    from: '  if (card.engagement === "none") return "trial.notUsed";',
    to: '  if (false) return "trial.notUsed";',
    runner: "vitest",
    grep: "nobody having been in gets its own sentence",
  },
  // ---- FD-05 · WALK-IN TRIAL -----------------------------------------------------------
  {
    id: "walk-in-trial-plan-states",
    why: "a tenant can publish no trial, one, or several, and only the middle one is the "
      + "screen the canvas draws -- collapsing the first two renders a form whose own "
      + "contract refuses it, which is the button answering 403 this whole surface avoids",
    file: "src/lib/walk-in-trial.ts",
    from: '  if (first === undefined) return { kind: "none" };',
    to: '  if (false) return { kind: "none" };',
    runner: "vitest",
    grep: "three states, because a tenant can publish none",
  },
  {
    id: "walk-in-trial-heading-names-one-length",
    why: "with two plans of different lengths a heading naming one of them is naming "
      + "whichever sorted first, which is MOD-018's unordered lookup in a title",
    file: "src/lib/walk-in-trial.ts",
    from: '  if (choice.kind !== "one") return null;',
    to: '  if (false) return null;',
    runner: "vitest",
    grep: "names the trial's length in the heading only where there is one answer",
  },
  {
    id: "walk-in-trial-reads-the-servers-step",
    why: "a press that found a live trial started nothing, and reporting it as started would "
      + "tell a desk they put somebody on a trial they were already on",
    file: "src/lib/walk-in-trial.ts",
    from: '  return steps.trial !== "existing";',
    to: "  return true;",
    runner: "vitest",
    grep: "reads the server's own step rather than assuming",
  },
  {
    id: "walk-in-trial-acknowledgement-reaches-the-server",
    why: "this is the one screen where the *server* refuses a number somebody holds, so a "
      + "client-side release is a button that would be refused -- the field is what says a "
      + "human looked at the match",
    file: "src/app/desk/trial/trial-form.tsx",
    from: '        <input type="hidden" name="different_person" value="1" />',
    to: "        <input type=\"hidden\" name=\"nothing\" value=\"1\" />",
    runner: "playwright",
    grep: "starts a trial and reports day one of it",
  },
  // ---- ADM-SCH-03 · CREATE A CLASS ------------------------------------------------------
  {
    id: "new-class-answer-carries-its-proposal",
    why: "a reply about a proposal the reader has already changed is not the answer to the "
      + "one on screen -- without the key comparison a clear hour reads as booked, or worse, "
      + "a booked one reads as clear",
    file: "src/lib/new-class.ts",
    from: '  if (answer === null || answer.key !== key) return { kind: "asking" };',
    to: '  if (answer === null) return { kind: "asking" };',
    runner: "vitest",
    grep: "is the answer only where the answer is about this proposal",
  },
  {
    id: "new-class-override-needs-a-reason",
    why: "paragraph 1842 is permission *and* reason, so a clash with no reason written is the "
      + "one thing that holds this button -- without it the create is attempted and the "
      + "generation refuses every occurrence, which is the save-time error the canvas is "
      + "built to avoid",
    file: "src/lib/new-class.ts",
    from: "  if (check !== null && !check.clear && overrideReason.trim().length === 0) "
      + "return false;",
    to: "  if (false) return false;",
    runner: "vitest",
    grep: "is the written reason paragraph 1842 requires",
  },
  {
    id: "new-class-clash-is-a-word",
    why: "a vocabulary the backend stores is never a label, and this app has five recorded "
      + "defects from rendering one -- `double_booked` in the middle of an Arabic line",
    file: "src/lib/new-class.ts",
    from: '    case "double_booked": return "newClass.clashBooked";',
    to: '    case "double_booked": return null;',
    runner: "vitest",
    grep: "is a word from the catalogue and never the stored kind",
  },
  {
    id: "new-class-is-reachable",
    why: "the calendar is the only route to this screen, and a screen with no way to it is "
      + "unreachable -- which this app has recorded twice, both found by somebody looking "
      + "for the control rather than by a test",
    file: "src/app/schedule/page.tsx",
    from: '            label={text("schedule.createClass")}',
    to: '            label={text("schedule.site")}',
    runner: "playwright",
    grep: "is reachable from the calendar, which is the only route to it",
  },
  // **Not a mutation, because the client's gate check is not the control.** Removing it makes
  // the page attempt `GET /crm/leads/{id}/trial` for a reader who may not have it -- and the
  // route answers 403, the `.catch` returns null and the card is absent either way, so the
  // suite stayed green. That is the guard working as defence in depth rather than as the
  // thing being proved: the control is the route's three `permit` calls, and
  // `test_the_card_charges_all_three_permissions` is what proves them. A mutation that cannot
  // fail is evidence of nothing, which this repository has a rule for.
  {
    id: "withheld-remedy-offers-the-step-up-to-everybody",
    why: "a step-up lifts an identity mask only for a reader who holds the permission at too"
      + " low an assurance; offered to one who holds it at none, it costs a single-use"
      + " recovery code and lifts nothing -- which is what nineteen call sites did",
    file: "src/lib/mask.ts",
    // **Not a second `default:`** -- the switch already has one, so adding a clause makes
    // the file unparseable and vitest collects nothing: "Tests  no tests", which the harness
    // would read as a gap it created. The mutation is the default branch's own answer.
    from: '    default:\n      return "not_held";',
    to: '    default:\n      return "step_up";',
    grep: "says the role does not include it when the gate simply refused",
    runner: "vitest",
  },
  {
    id: "withheld-remedy-treats-a-dead-gate-as-a-refusal",
    why: "a transport failure is not a statement about the reader's access, which is the"
      + " whole reason `gateVerdict` has a verdict for it",
    file: "src/lib/mask.ts",
    // **Both of this pair's first drafts were ill-formed in the same way**, which is worth
    // the note: in a `switch` whose earlier clauses already decide, adding a label is either
    // a duplicate (unreachable -- the first match wins, so the sweep reports UNCAUGHT) or a
    // second `default:` (unparseable -- vitest collects nothing and reports "no tests").
    // The mutation of a branch is its own answer, never a clause beside it.
    from: '      return "no_answer";',
    to: '      return "not_held";',
    grep: "keeps a transport failure out of both",
    runner: "vitest",
  },
  {
    id: "staff-rows-keep-the-step-up-sentence",
    why: "the banner is one element and the rows are five, so fixing only the banner leaves"
      + " the false remedy on every row -- which is how the first version shipped",
    file: "src/app/staff/page.tsx",
    from: '  const nameWithheld: MessageKey = remedy === "step_up"\n'
      + '    ? "member.withheldIdentity"\n'
      + '    : "member.withheldIdentityNoRemedy";',
    to: '  const nameWithheld: MessageKey = "member.withheldIdentity";',
    grep: "can read the staff list at all, and is told it is bounded",
    runner: "playwright",
  },
  {
    id: "staff-banner-keeps-the-step-up-sentence",
    why: "the page-level sentence is the one a reader acts on, and the offer beside it is"
      + " what costs the recovery code",
    file: "src/app/staff/page.tsx",
    from: '          {remedy === "step_up" ? (',
    to: "          {true ? (",
    grep: "can read the staff list at all, and is told it is bounded",
    runner: "playwright",
  },

  // ------------------------------------------------- ADM-SET-07, localization
  // **The forced `-u-nu-latn` in `monthDay`'s tag has no mutation, and the reason is worth
  // more than the entry.** Removing it came back uncaught, correctly: `shapeDigits` is
  // *bidirectional* -- its `latn` branch converts U+0660-0669 back to ASCII -- so whatever
  // numbering `ar-JO` resolved to is normalised afterwards and the output is identical. The
  // guard is for a third locale, whose default digits `shapeDigits` would not know how to
  // undo, and this build has two. A permanently-uncaught entry is noise on every run, so the
  // rule is kept and documented where it is written and the premise it rests on -- that
  // `shapeDigits` normalises in both directions -- is asserted in `localization.test.ts`.
  {
    id: "localization-the-digits-are-shaped-by-the-tenants-rule",
    why: "without the shaping the month name is right and the digits are whatever the tag"
      + " happened to resolve, so an `arab` tenant reads `21 آب` -- the one pair that proves"
      + " the two halves are decided separately",
    file: "src/i18n/dates.ts",
    from: "  return shapeDigits(latin, numbering) as string;",
    to: "  return latin;",
    grep: "forces the numbering rather than letting the regional tag decide it",
    runner: "vitest",
  },
  {
    id: "localization-the-preview-is-arabic-where-arabic-is-offered",
    why: "an English-locale owner checking their tenant's Arabic rendering is the ordinary"
      + " case, and a sample in their own language shows them the one half they can already"
      + " read",
    file: "src/lib/display.ts",
    from: '  return conventions.languages_offered.includes("ar") ? "ar" : "en";',
    to: '  return "en";',
    grep: "is Arabic wherever Arabic is offered",
    runner: "vitest",
  },
  // **The preview's money/numerals split has no browser mutation, and the fixture is why.**
  // Passing `conventions.numerals` where the page passes `money_numerals` is a no-op while
  // the tenant publishes `latn`, because the two values are then equal -- so no browser
  // assertion could see it, and an entry here would report a gap on every run. The property
  // is proven where the two differ: `tests/component/localization.test.ts` builds the
  // sentence at `arab` and asserts the date shapes while `JOD 55.00` does not. That is the
  // cost of a `latn` fixture, taken deliberately -- see the note in `fixture.mjs`.
  {
    id: "localization-the-count-follows-the-setting",
    why: "the figure above the chips obeys the chip that is filled, which is the only thing on"
      + " this screen that shows the setting reaching a figure at all -- and passing a"
      + " constant is deciding it per component, which 'never mixed and never decided per"
      + " component' forbids",
    file: "src/app/localization/page.tsx",
    from: "                  { count: conventions.languages_offered.length }, conventions.numerals)}",
    to: '                  { count: conventions.languages_offered.length }, "arab")}',
    grep: "shapes its own count by the setting",
    runner: "playwright",
  },
  {
    id: "localization-the-setting-reaches-a-page",
    why: "**ADR-0015's second half, in one mutation.** Every quantity in the product goes"
      + " through this one reader, and the fixture publishes `latn` -- so flipping it turns"
      + " the door board's own `1 Entry` into `١ Entry`. If nothing fails, the setting"
      + " reaches nothing and the screen that displays it is a page about a value with no"
      + " consumer, which is the shape this whole slice exists to close",
    file: "src/lib/display.ts",
    from: "  return (await conventions()).numerals;",
    to: '  return "arab";',
    grep: "lists the seeded zone with its risk class and its readers",
    runner: "playwright",
  },
  {
    id: "localization-a-default-is-not-a-decision",
    why: "the sentence is about a tenant that has declared nothing, so rendering it for one"
      + " that has just chosen both would be telling an owner they had not set what they set",
    file: "src/lib/display.ts",
    from: "  return !conventions.declared.includes(key);",
    to: "  return true;",
    grep: "says nothing about defaults",
    runner: "playwright",
  },
  {
    id: "localization-the-in-force-value-says-so-in-words",
    why: "colour is never the only signal: a filled chip is the sighted reading and the word"
      + " is what a screen reader gets, so dropping it leaves two samples a reader cannot"
      + " tell apart",
    file: "src/components/ds/choice-chips.tsx",
    from: '              {one.on ? <span className="ds-visually-hidden">{` \u2014 ${inUse}`}</span> : null}',
    to: "              {null}",
    grep: "marks which numeral system is in force",
    runner: "playwright",
  },

  // ------------------------------------------------- ADM-PAY-06, dunning rules
  {
    id: "dunning-a-default-is-not-a-decision",
    why: "the figures a tenant has not set are the journey this build already ran, and a"
      + " screen that could not tell them from a decision would present its own constants as"
      + " somebody's choice -- MOD-005's board had to learn the same thing about"
      + " `scope_type: \"default\"`",
    file: "src/lib/dunning.ts",
    from: "  return !policy.declared.includes(key);",
    to: "  return false;",
    grep: "says the figures are defaults rather than a decision",
    runner: "playwright",
  },
  {
    id: "dunning-the-field-holds-the-figure-in-force",
    why: "a form whose boxes are empty is a form that saves nothing a reader meant: the two"
      + " figures are the policy in force, and typing over one is how it is changed",
    file: "src/app/payments/dunning/policy-form.tsx",
    from: "  const retry = state.echo.retry ?? String(retryAttempts);",
    to: '  const retry = state.echo.retry ?? "";',
    grep: "renders the two rules as sentences with the figures in them",
    runner: "playwright",
  },
  {
    id: "dunning-the-sentence-is-the-canvas-s",
    why: "**`Field`'s prefix and suffix are what make it sentence form**, which the canvas's"
      + " own note calls for -- 'sentence form, same as the automation builder'. Without them"
      + " it is a labelled number box, which is a different screen",
    file: "src/app/payments/dunning/policy-form.tsx",
    from: '        prefix={text("dunning.retryPrefix")}\n        suffix={text("dunning.retrySuffix")}',
    to: "",
    grep: "renders the two rules as sentences with the figures in them",
    runner: "playwright",
  },
  {
    id: "dunning-a-refused-write-offers-the-step-up",
    why: "a button that answered 403 is worse than its absence, and `finance.dunning.manage`"
      + " is financial class because the figures decide when a member's access is recommended"
      + " to be restricted -- so the page offers the step-up instead",
    file: "src/app/payments/dunning/page.tsx",
    from: "          canWrite={mayWrite.allowed}",
    to: "          canWrite={true}",
    grep: "offers the step-up rather than a button the gate would refuse",
    runner: "playwright",
  },
  {
    id: "dunning-the-floor-says-which-half-is-structural",
    why: "two of the four rules are properties of this build and two are intentions -- nothing"
      + " here sends or charges -- and a floor a reader cannot tell from an intention is a"
      + " floor they have to take on trust",
    file: "src/app/payments/dunning/page.tsx",
    from: '                {text(one.enforced ? "dunning.floorEnforced" : "dunning.floorIntended")}',
    to: '                {text("dunning.floorEnforced")}',
    grep: "renders the floor and says which half of it is structural",
    runner: "playwright",
  },
  {
    id: "dunning-is-reachable-from-the-workspace-it-sorts",
    why: "a screen with no route to it is unreachable, and the recovery workspace is the one"
      + " whose rows these figures decide the treatment of",
    file: "src/app/payments/recovery/page.tsx",
    from: '        <Link href="/payments/dunning">{text("recovery.rulesLink")}</Link>',
    to: "        {null}",
    grep: "is linked from the recovery workspace",
    runner: "playwright",
  },
];

const only = process.argv[2];
/**
 * Whether any test file this runner reads names a test matching the pattern.
 *
 * The pattern is a regex, because that is what both `-t` and `--test-name-pattern` take.
 */
function testsMention(runner, grep) {
  const dir = join(web, runner === "node" ? "tests/unit" : "tests/component");
  const pattern = new RegExp(grep);
  for (const entry of readdirSync(dir)) {
    if (!/\.(mjs|ts|tsx)$/.test(entry)) continue;
    if (pattern.test(readFileSync(join(dir, entry), "utf8"))) return true;
  }
  return false;
}

const chosen = only ? MUTATIONS.filter((m) => m.id.includes(only)) : MUTATIONS;

// Whatever is currently mutated, so a signal can put it back. One entry at a time, because
// the sweep is serial.
const inFlight = new Map();
function restoreEverything() {
  for (const [path, text] of inFlight) writeFileSync(path, text);
  inFlight.clear();
}
for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(signal, () => {
    restoreEverything();
    console.log(`\n${signal}: restored the tree and stopped`);
    process.exit(130);
  });
}
process.on("uncaughtException", (error) => {
  restoreEverything();
  throw error;
});

let caught = 0;
const gaps = [];
const notRun = [];

for (const mutation of chosen) {
  const path = join(web, mutation.file);
  const original = readFileSync(path, "utf8");
  const occurrences = original.split(mutation.from).length - 1;
  if (occurrences !== 1) {
    // **Is this a stale definition or a mutation a killed run left behind?** The handlers
    // above restore on SIGINT, SIGTERM and SIGHUP, and none of them can catch a SIGKILL --
    // so an interrupted sweep can leave a file mutated, and the only trace is this anchor
    // going missing. That reads as "somebody edited the component" and sent me looking in
    // the wrong place for ten minutes, with a red component suite in between.
    //
    // **And "the replacement text is present" has a second cause this message used to assert
    // away.** A protection can be *retired into* the mutation's own form -- ADR-0010 D7 made
    // `columnNote` return null, which is exactly what `lead-on-trial-says-why` mutated it to
    // -- and then the file is pristine and the mutation is stale. Both readings leave the
    // identical trace, so the message names both rather than sending somebody to `git
    // checkout` a file nothing has touched.
    const leftBehind = mutation.to !== "" && original.includes(mutation.to);
    const because = leftBehind
      ? `the replacement text is present. Either a killed run left this file mutated -- put `
        + `it back with: git checkout ${mutation.file} -- or the protection was retired INTO `
        + `this mutation's own form, in which case the mutation is stale and goes`
      : `the anchor appears ${occurrences} times, not once`;
    notRun.push(`${mutation.id}: ${because}`);
    console.log(`SKIP  ${mutation.id} (${leftBehind ? "LEFT MUTATED" : `anchor matched ${occurrences} times`})`);
    continue;
  }

  inFlight.set(path, original);
  writeFileSync(path, original.replace(mutation.from, mutation.to));
  try {
    const run = mutation.runner === "vitest"
      ? spawnSync("npx", ["vitest", "run", "-t", mutation.grep],
                  { cwd: web, encoding: "utf8", timeout: 180_000 })
      // **The foundation layer had no runner here at all**, so none of its assertions had
      // ever been mutation-proven through this harness -- found by pointing a mutation at
      // one and watching it come back uncaught, because `vitest` does not collect
      // `tests/unit/` and reported no failure rather than no test. `--test-name-pattern` is
      // Node's own `-t`.
      : mutation.runner === "node"
      ? spawnSync("node",
                  ["--test", "--test-name-pattern", mutation.grep, "tests/unit/"],
                  { cwd: web, encoding: "utf8", timeout: 180_000 })
      : spawnSync("npx",
                  ["playwright", "test", "--grep", mutation.grep, "--reporter", "line"],
                  { cwd: web, encoding: "utf8", timeout: 180_000 });
    const output = `${run.stdout ?? ""}${run.stderr ?? ""}`;
    // **No runner here can be asked whether its name pattern matched.** Node's runs every
    // file, filters every test out of each and reports `pass 9, fail 0`; vitest reports
    // `Tests 408 skipped` and exits 0. Both are indistinguishable from a real pass by the
    // exit code and from a real gap by the output -- a stale grep comes back UNCAUGHT, which
    // reads as a protection with no evidence and is in fact a mutation that was never
    // judged. It cost two rounds on a renamed test before the cause was obvious.
    //
    // So the grep gets the same static check the mutation text already gets: the pattern has
    // to occur in the tests that runner reads, or the mutation is reported as not run.
    // Playwright is the exception and needs none -- it says "No tests found" and exits
    // non-zero, which the output check below already catches.
    // **An absent `runner` is playwright**, which this file's own doc says and which the
    // first version of this guard forgot -- so ninety mutations whose runner was simply not
    // stated were checked against the component tests, found nothing and were reported as
    // not run. A guard that reports most of the suite as unjudged is louder than the thing
    // it guards against, which is the only reason it was obvious.
    const matched = (mutation.runner ?? "playwright") === "playwright"
      || testsMention(mutation.runner, mutation.grep);
    const ranSomething = matched
      && !/No tests found|No test files found/.test(output)
      && !/Tests {2}no tests/.test(output);
    if (!ranSomething) {
      notRun.push(`${mutation.id}: --grep "${mutation.grep}" matched no test`);
      console.log(`SKIP  ${mutation.id} (grep matched no test)`);
    } else if (run.status !== 0) {
      caught += 1;
      console.log(`ok    ${mutation.id} -- caught`);
    } else {
      gaps.push(`${mutation.id}: ${mutation.why}`);
      console.log(`GAP   ${mutation.id} -- the suite stayed green`);
    }
  } finally {
    writeFileSync(path, original);
    inFlight.delete(path);
  }
}

console.log(
  `\n${caught}/${chosen.length} mutations caught` +
    (gaps.length ? `\n\nUNCAUGHT:\n  ${gaps.join("\n  ")}` : "") +
    (notRun.length ? `\n\nNOT RUN:\n  ${notRun.join("\n  ")}` : ""),
);
process.exit(gaps.length === 0 && notRun.length === 0 ? 0 : 1);

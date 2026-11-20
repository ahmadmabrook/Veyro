# Veyro web

TypeScript / React / Next.js surfaces, per the Engineering Implementation Plan's repository
layout (`web/` TypeScript+React+Next.js, `mobile/` KMP+Compose, `edge/` Kotlin/JVM).

Surfaces this directory will own, from `contracts/ui/screen-contracts.yaml` (170 V1 screens):
Veyro Admin (85), Veyro Member (35), Veyro Coach (19), Front Desk & POS (16), Internal
Console (15).

## State

A running Next.js application: sign-in against MOD-007 including the device challenge it
raises and a step-up that actually raises a session's assurance, an admin landing page whose
every control's visibility comes from MOD-008's gate, a section navigation filtered by that
same gate, MOD-004's organization hierarchy, MOD-008's roles and audit chain, MOD-014's
duplicate queue and Member 360 with every masked field marked and MOD-017's membership,
entitlement and billing blocks composed onto it, MOD-009's privacy board where the registry of what an
erasure cannot reach is readable for the first time, MOD-012's integrations board which says a run's counts
were reported rather than observed, MOD-013's messages board which leads with the fact that
nothing sends, MOD-016's catalog board where a
promotion's window tells a live campaign from one that merely still says active, MOD-018's finance board where
the period lock is readable for the first time, MOD-021's fleet board and
device detail, MOD-022's door board and zone detail, MOD-019's schedule board and session
detail with MOD-020's roster on it, MOD-005's configuration and feature-flag board, an
operations board over MOD-010's event plane, MOD-011's objectives and the worker runtime's own
scheduled jobs, Arabic/English with full RTL, a dark theme, and four layers of tests that have
each been shown to fail when the thing they guard is removed.

| Layer | What it proves | Count | Command |
|---|---|---|---|
| Foundation (`tests/unit/`) | Tokens, contrast, type, theme coverage, backend parity, **the Admin shell against the design source's own sentence**, the density modes, every media query checked against a breakpoint boundary, and the sweep that stops a screen hand-rolling a component the system already approves. No dependencies, no DOM. | 70 | `npm run test:foundation` |
| Component (`tests/component/`) | Control semantics, the message catalogue in both directions, the sign-in form's four states, the device-label parity, the hierarchy composer, the mask marker, the redirect guard, the relay verdict, why a flag resolved as it did, reading an instant in a site's own timezone, what a member's money and entitlements mean, which periods need somebody and why an unbalanced ledger means lost rows, when a session is live, which device a session came from and whether it may mint new recovery codes, and **every design-system family against the contract sentence it implements** -- including that the money renderer is the one the receipt uses rather than a second one -- in jsdom. | 143 | `npm test` |
| End-to-end (`tests/e2e/*.spec.ts`) | A real browser against a real backend whose fixture ran the real worker, including 32 axe runs across both locales, both themes and phone width, twenty surfaces checked for horizontal scroll on a phone, the no-JavaScript sign-in replay, seven surfaces driven as a session that may not read them, a withheld field proved against a session that is actually masked, MOD-017's three blocks proved refused against a front desk that holds the person read and none of the money, a session raised from level 1 to level 2 for real, and the four writes on the account page driven end to end against a subject each test registers for itself -- a session revoked, a device trusted, a batch of recovery codes minted after a step-up, and a device revoked that signs the reader out and refuses the way back. | 246 + 3 setup | `npm run e2e` |
| Mutation sweep (`tests/e2e/mutate.mjs`) | Each protection above, broken on purpose, is caught by the test that names it. | 92/92 | `npm run e2e:mutate` |

### Running it

Three processes, in this order. The backend and the fixture are **deliberately not** started by
the Playwright config: a harness that silently provisions a database is a harness whose green run
proves less than it looks.

```bash
docker start veyro-pg && backend/scripts/verify_db.sh
```

```bash
cd web && npm run api
```

```bash
cd web && npm run fixture && npm run dev
```

`npm run fixture` provisions a synthetic tenant, an owner identity and the one-time authorization
bootstrap **over HTTP**, and writes the credentials to `web/.env.e2e.local` (mode 600, gitignored
by the root `.env.*` rule). It never prints the password. `backend/tests/support.py` builds an
owner through the service layer because the HTTP path costs a dozen scrypt hashes; here the
request path *is* what is under test, so the fixture goes through it.

## Decisions taken here

**Sign-in is a server action, and that is a security decision rather than a stylistic one.**
The first version was a client form calling `/api/auth/login`, and the whole of its protection
rested on `event.preventDefault()` having run. Driving it in a real browser produced
`?tenant_id=&identifier=&password=` in the address bar, immediately and by accident: Next's dev
server had blocked a cross-origin dev resource, the React tree never attached, and the form did
what an un-handled form does. The page looked identical and nothing errored. **A password in a
URL is in the address bar, in browser history, in the server's access log and in every proxy
between the two.** The dev-origin cause is fixed in `next.config.mjs`; the *shape* is the one
`CLAUDE.md` records for the backend over and over — a control that only works once something
else has happened is a control with a window, and here the window was every millisecond before
hydration on every page load. A server action closes it structurally: without JavaScript the
browser POSTs and the sign-in genuinely works, and there is no arrangement of failures that puts
a credential anywhere but a request body. `tests/e2e/no-js.spec.ts` is what says so: it drives Playwright's request context, which
is an HTTP client with no browser and no JavaScript at all.

**A `"use server"` module may export async functions and nothing else.** `SIGN_IN_IDLE` was a
constant beside the action. It compiled, type-checked, built, and arrived at the client as
`undefined`, so the form threw on its first render. A type-only export survives because it is
erased, which is what makes the mistake easy — the types line up perfectly and the value is
gone. State lives in `src/app/login/state.ts`.

**`currentSession()` fails closed, and on a sign-in page "closed" means anonymous.** A visitor
who has never signed in has no tenant cookie, so `api()` refuses before the network with
`no_tenant_selected`. Treating that as an error made `/login` — the one page whose entire
audience is signed-out people — answer 500 to every first-time visitor.

**The dark theme is swept, not listed.** The generator used to skip a dark declaration it could
not resolve and say nothing. Seven of twenty-nine semantic tokens had no dark value and silently
kept their light one: form fields rendered near-white on a near-black page, the primary button
stayed `ink.600` against it, and `color.border.focus` — which guardrail G4 makes system-owned
precisely so "a tenant cannot ship an unnavigable product" — was dark navy on near-black. Every
one of the seven named a value the source states *somewhere else* (`dark.950`, `accent.light`),
so `ds.json` now carries a `DARK_RAMP` whose every entry cites the row it was quoted from, the
generator **fails** on an unresolved reference, and `tests/unit/theme.test.mjs` sweeps the token
set in both directions. A per-token list would have to be edited whenever a token is added, and
that edit is the moment an unmapped one slips through.

**Inline style key order is load-bearing.** `Alert` set `borderInlineStart` before the `border`
shorthand, which resets it — so the severity mark, the one thing distinguishing an error from a
notice, was not on screen. The token was correct and the component read as finished. Found by
looking at a render.

**The gate's four answers render as four things, and the order of the checks matters.**
`reachable: false` is tested before `step_up_required`, because MOD-008 sets both for an AAL-3
action: it is true that a stronger sign-in is required and false that one is available. Reading
them the other way round offers a step-up that can never succeed and sends somebody looking for
a hardware key MOD-007 cannot verify.

**The browser never holds a bearer token.** MOD-007 stores a session only as a SHA-256 digest so
a stolen database cannot replay one; putting the token in client JavaScript would undo that by
handing it to any XSS instead. It is an httpOnly, `SameSite=strict` cookie, every API call is
made server-side, and an E2E test reads `document.cookie` to prove the browser cannot see it.

**`127.0.0.1` is in `allowedDevOrigins`.** Next 16 blocks cross-origin requests to its own dev
resources, and `localhost` and `127.0.0.1` are different origins to a browser — so visiting the
second one got the HTML and the chunks and then a 403 on the HMR socket, and the page never
hydrated. A Playwright run against `127.0.0.1` would have driven a dead page and reported green
for every assertion about server-rendered text.

**The design system is read, not invented.** `ds.json` is extracted from
`veyro-product-experience-design/project/Veyro DS Foundations.dc.html` — 22 primitive colours,
29 semantic tokens with light and dark mappings, a 12-token type scale, 4 density modes, 5
breakpoints, 9 Arabic rules, 9 contrast rows and 7 white-label guardrails. Anything this
directory needs that the DS does not state is a gap to raise, not a value to choose.

**Tokens are generated and the generator has a `--check`.** A hand-edited
`tokens.generated.css` fails `npm run tokens:check` — verified by appending a comment and
watching it report STALE. Same trade as the backend's definition pin: a legitimate change
fails until it is regenerated, which is the moment a human reads the diff.

**Layer discipline is enforced, not documented.** Primitives emit as `--p-*`, semantics as
`--color-*`, and a test asserts the dark block redefines no `--p-*` — because the foundations
say layer 2 "is the only colour layer components are allowed to consume" and a theme is a
remapping rather than a rewrite.

**Type resolution requires a script.** `resolveType(name, script)` has no single-argument
form. Arabic is not Latin in another font: five of the nine Arabic rules change the resolved
token (line-height +0.15, a 13px floor, weight up a step, tracking dropped, no mono), so a
function that answered without knowing the script would be wrong half the time. `type.eyebrow`
has no Arabic form and resolves through `type.label`, and the result reports `resolvedFrom` so
a caller can see the substitution rather than silently getting different values.

**Formatting is proven identical to the backend, by running both.** The Arabic rules require
numerals "applied identically on screen, receipt, export and PDF", and a screen is rendered
here while a receipt is rendered by `backend/app/l10n/conventions.py`. Two suites asserting
their own expectations would pass forever while drifting, so
`tests/unit/conventions-parity.test.mjs` spawns Python, runs both implementations over one
vector set and compares character by character — invisible bidi controls included. It skips
with a stated reason if no Python is on PATH rather than passing vacuously.

**Invisible controls are built from code points, never written as literals.** This file's
first version put ` ` in a regex literal; U+2028 is a JavaScript line terminator, so the
module did not parse. Every bidi and Arabic-numeral control is now `String.fromCodePoint`.

**The challenge form is proved by a component test, and that is a decision about what a
browser suite can prove.** MOD-007 challenges a login from a device it has not seen and then
*confirms* that device, so a browser is challenged exactly once per fixture -- which means an
end-to-end assertion about the challenge passes or fails depending on whether some earlier
test in the run happened to burn it. The sweep showed it: deleting the recovery-code field
left the E2E suite green, because by then the device was trusted. `tests/component/login-form.test.tsx`
renders the state the server returns and asserts what the reader is given, which is the half
that must never regress -- a form that says a recovery code is needed and offers nowhere to
type one is the dead end MOD-007's own review records one layer down. **And the password field
goes away when a challenge is in flight**, because asking for it again after a security prompt
is the habit a phishing page relies on.

**The fixture confirms this app's device, and the browser suite is never challenged.**
MOD-007 challenges a login from a device it has not seen and confirms that device permanently
when the challenge is answered -- and a recovery code is single-use. So a helper that answered
the challenge in the browser passed on the first run against a fresh fixture and failed on
every run after it: the second run found the code spent and every signing-in test timed out at
the recovery field, which is a suite whose green depends on how many times it has been run.
The fixture now logs in *as the browser's device* and answers the challenge itself, and
`tests/e2e/sign-in.ts` **throws** if a challenge appears, because one appearing means the
device label drifted or the fixture was not re-run. The formula lives in `src/lib/device.ts`
for the app and `tests/e2e/device.mjs` for the fixture -- two spellings of one rule, which is
why `tests/component/device-parity.test.ts` runs both over a vector set and compares, and why
the mutation sweep breaks one of them and checks that comparison fails.

`sign-in.ts` is also the only place a spec authenticates, so no spec has its own idea of what
signing in looks like, and it reports the assurance level, which is what lets a gate test
assert a step-up refusal rather than guessing at one.

**The access surface masks what the backend masks, and does not re-derive it.** MOD-022 returns
a public code and withholds the private reason unless the session holds the permission for it;
`src/lib/access.ts` carries `RESTRICTED_CODES` and renders a withheld reason as *visibly*
withheld rather than as absent. An empty cell is indistinguishable from "there was no reason",
and the sweep has a mutation for exactly that (`withheld-unmarked`). The list is a mirror of
the backend's and the point of mirroring it is the rendering decision, not the masking: the
decision about what may be said is the server's, and a surface that recomputed it would be a
second definition of the same control.

**A wrong-password test uses an address nobody registered.** The first version used the fixture's
own identity, and MOD-007's lockout is per identity -- so the refusal tests accumulated failures
against the account every other test signs in with, and the suite locked itself out partway
through. Using an unknown address is sound precisely because of MOD-007's own review finding:
every refusal costs one scrypt and returns the same 401, so an unregistered address and a wrong
password are indistinguishable by design, which is what makes the substitution faithful.

**The mutation harness restores on a signal, not only on an exception.** A sweep stopped
halfway left a deleted line in `src/app/access/[zoneId]/page.tsx` -- paragraph 4180's
disclaimer, the mutation whose `to` is the empty string -- because `finally` does not run when
the process is killed. Searching the tree for mutated text cannot find a *deletion*, so the
only trace was the next run reporting "the anchor appears 0 times", and in between a browser
run went green against a page that was missing the thing one of its tests is named after.
`mutate.mjs` now restores the file it is holding on SIGINT, SIGTERM and SIGHUP.

**The navigation is filtered by the gate, and the test for that needs a weaker session.**
The fixture's owner holds all 202 permissions, so signing in as the owner proves only the
allowed half of any gate -- a navigation that ignored the gate entirely would pass every
assertion a run as the owner can make. The fixture already created a second identity for
MOD-022's two-party policy publication, holding `access.zone.read` and not
`tenancy.organization.read`; it now confirms that identity's browser device too and writes its
credentials beside the owner's, and `organization.spec.ts` signs in as it to assert the entry
is **absent** rather than disabled, and that the page answers "not permitted" rather than an
empty tree. A disabled entry is a promise that something could be unlocked, and for a
`privileged` action in this build nothing can.

**`aria-current` is the one thing in the app that needs client JavaScript.** A server layout
does not know the pathname, so marking the current section means either every page repeating
the nav with its own `active` prop -- a control spread across every caller -- or one small
client component reading `usePathname()`. The second is 15 lines and costs only the marker when
JavaScript is off; the links are anchors and work regardless, and the sign-in path, the one
with credentials in it, has no client runtime at all.

**`npm run verify` prints a line when it passes, because a tail without one looks the same
either way.** A chained script exits non-zero when a step fails, and a reader skimming the last
few lines of a long run sees a plausible duration whether or not the step before it failed --
which is exactly how an untranslated message key (`"#"` is the same string in both locales, and
the catalogue guard correctly calls that untranslated) reached a red CI after a local run that
read as green. The check was working; the reading was not.

**Three times now a test has had a green that depends on how many times it has been run, and
the shape is one rule.** MOD-007 and MOD-011 keep budgets per identity, and a test that spends
one spends it for every later run against the same fixture:

- a **single-use recovery code**, spent answering the device challenge -- green on the first run
  against a fresh fixture and red on the second, fixed by having the fixture confirm the
  device;
- **thirty logins a minute**, spent by a `beforeEach` that signs in -- which put a cap on how
  many tests the suite could contain, fixed by signing in twice per run and adopting the cookie;
- **five recovery failures and the identity's recovery path is shut**, spent one per run by the
  test that submits a wrong recovery code. Nothing resets it, so the fifth run locked the owner
  and every step-up failed with "that was not accepted" -- for a code minted seconds earlier.

The rule: **a test that consumes a product budget must consume one nobody else depends on, or
provision its own.** The wrong-code test now spends the *reader's* recovery budget, which no
other test needs, and it stays correct once that budget is gone because MOD-007 makes a locked
refusal and a wrong code answer identically -- which is the same property the test is asserting.

None of the three is visible in a single run. `npm run e2e` **twice in a row** is what finds
them, and it is worth doing after any change to the fixture or to a test that presents a
credential.

**And a fixture identity is not always enough, which is the refinement the account spec
forced.** It got a fixture identity of its own for exactly this rule and was still green once
and red twice, because its writes are not merely expensive but *terminal*: a device can be
trusted only once, and revoking the one this app signs in from locks that subject out of the
product permanently. A per-fixture subject makes such a test a function of how many times the
suite has been run against one database. So each of those tests registers a subject of its own
through the open registration route -- three runs in a row against one fixture, all green --
and the fixture's fourth identity was deleted, because nothing used it afterwards.

**And the sibling of that rule: a test that asserts a freshness has to create it.** The fleet
board shows `Online` only while a device has reported within ten minutes, which is true
because the fixture's health report made it true -- so the assertion expires. CI provisions
immediately before the suite and is deterministic; a local run against a fixture seeded an
hour earlier reads `Late` and looks exactly like a product regression. The spec says so where
the failure appears, because that is where somebody will be reading. Found by running the
suite an hour after seeding, which is the only way to find it.

**The step-up replaces the session cookie, and that is the whole flow in one sentence.**
MOD-007 does not elevate a session in place: `_step_up_in_tx` revokes the one it came from with
`revoke_reason = 'stepped_up'` and opens a new one, because a session's lifetime follows what it
can do and a level-2 window is twelve hours rather than a fortnight. So **a step-up that does
not write the new token into the cookie signs the reader out** -- on the one path where they
have just proved who they are. The browser suite asserts the landing page afterwards and the
mutation sweep deletes the cookie write to prove the assertion bites.

Three more things the page gets from the server rather than assuming:

- **which factor can raise this session.** `policy.assurance_for` reads distinct *kinds*, so two
  passwords are one factor: a password session is raised by a recovery code and a
  recovery-code session by the password. The page reads `factors` off `/auth/session` and asks
  for the one that would work.
- **whether the level is reachable at all.** `biometric_sensitive` is level 3, which needs a
  hardware authenticator MOD-007 cannot verify, so the page says so instead of rendering a
  field. Offering one would send somebody looking for a key the product cannot check.
- **the challenge, fetched immediately before the post rather than rendered into a hidden
  field.** A nonce is one-use and bound to the session; a page that handed one to the reader
  would hand them a token that goes stale while they look for their recovery codes, and the
  failure would read as "that code was not accepted".

**`next` is validated as a shape, not against a list of hosts.** It arrives in a link, which is
the one thing a reader can be handed, and sign-in and step-up are the two pages where a redirect
to a lookalike host is worth the most. `safeNext` keeps a same-origin path and refuses the four
shapes that leave the origin -- protocol-relative `//host`, the backslash variant browsers
normalise, an absolute URL with or without a leading slash, and a control character. A refused
`next` is never an error the reader sees: being sent somewhere safe is the correct outcome, and
a message would only teach somebody which probe got through.

**A withheld value is marked, and the marker carries which of two reasons it is.** MOD-014 is
the only module whose read path applies `Decision.mask`, and it replaces a field the caller may
not read with `"***"` at every depth. Its own rule is that a redacted record still exists --
telling a coach a member has no health notes when they have three is worse than telling them
there are three they cannot read -- so the surface renders withheld rather than blank, with a
dashed border rather than a colour (WCAG 1.4.1), and names the reason: an identity field needs
a stronger sign-in, and a health field **cannot be read by anybody in this build**, because
`member.health.read` is `biometric_sensitive`, which is assurance level 3, which needs a
hardware authenticator MOD-007 cannot verify. Offering a step-up for the second would send
somebody looking for a key the product cannot check.

The fixture signs in with a password, so the session is assurance level 1 -- which is the
useful level to test at: `contact` opens on a routine permission and `identity` needs a
financial one, so one record shows a masked legal name beside an unmasked email address, and a
surface that masked everything or nothing would pass a test that only looked at one of them.

**Two of these mutations were uncaught the first time and the reason generalises.** A health
note and a health custom field are separate code with separate tests, and the first version of
the field assertion scoped to the section and took the last marker in it -- which a marker
belonging to a different field also satisfies. The mutation that pointed a health field at the
step-up message passed. Scoping to the `dl` that holds the field, asserting the marker count is
one, and asserting the reason it does *not* carry is what catches it. That is this
repository's "two controls refuse the same row" trap, in a browser.

**The suite signs in twice per run, and that is a rate-limit fix rather than a speed one.**
MOD-011's limiter allows 30 logins per minute per subject -- a real product control, bounding
the volume MOD-007's lockout cannot see -- and a `beforeEach` that signs in puts a hard cap on
how many tests the suite may contain. It crossed that cap at 53: the owner's thirty-first login
inside the window was refused, the sign-in helper waited for a page it was never going to get,
and the failure named a 30-second timeout rather than a limit. **A suite that cannot grow past
thirty tests is a problem for every surface still to be built**, so `auth.setup.ts` signs in
once as the owner and once as the reader, saves the cookies under `playwright/.auth`
(gitignored, it is a live session), and the specs adopt one. `signIn` is still what
`auth.spec.ts` and the no-JavaScript replay use, because those are about the form.

**And the browser specs were not typechecked at all.** `tsconfig.json` excluded `tests/e2e`,
so the only TypeScript in the repository nobody checked was the suite that drives the product
-- and a spec calling a helper it had not imported passed `npm run typecheck` and would have
surfaced at run time as a missing heading. They are in scope now; one real error came out of it.

**The hierarchy composer is unit-tested because its interesting inputs cannot be provisioned.**
A location whose brand is missing from the brand list is a read that raced a write or a
tenant-isolation question, and there is no way to ask the API for one -- so a browser suite can
only ever see the well-formed case. `composeTree` keeps an orphan and marks it rather than
dropping it, because a site that vanishes from the only page listing sites is the worse
failure, and `tests/component/organization-tree.test.ts` is what holds that.

**One screen was telling a staff member that the product does not have bookings.** The Member
360 lists the twelve areas PPL-01-R02 names and says where each comes from; five said "not
built in this repository", and four of those modules — MOD-017, MOD-018, MOD-019, MOD-020 —
have been built since the line was written. An e2e test was *asserting* the false string. They
say the module owns it and this projection is not wired to read it now, which is a different
and more useful fact, and the heading is "Not answered here" because the list holds two
reasons at once.

**Every instant outside the schedule is marked UTC**, which it did not need to be while every
screen rendered a bare wall time and does now that one of them converts: a reader with one
local-time screen reads the next one as local too. `src/lib/time.ts` holds both readings
together so the difference is a decision rather than one page's habit.

**And the message catalogue's parity check was one-directional.** `MESSAGE_KEYS` is the
English catalogue's own keys, so it saw an English key missing from Arabic and was blind to an
Arabic key missing from English — a translation nothing renders, which reads as a translated
interface to anything counting keys. Found by adding one by accident and watching the file
stay green. It checks both directions now, which is the rule the id sweep and the worker's
name list are built on, and it caught the stray key the moment it existed.

**Four layers of tests and 140 green assertions did not notice that the schedule board showed
the wrong time.** The rule says 18:00 and the site is `Asia/Amman`, so MOD-019 stores 15:00
UTC and the local facts beside it, because neither is derivable from the other. The board
sliced the ISO string and rendered `15:00` — under a heading promising the site's own
timezone. Every test passed, because every one of them asserted that the *name* of the
timezone was on the page rather than what the times said. It was found by opening the page and
looking at it, which until then nobody had done.

**The same look found that seven of thirteen surfaces scrolled sideways on a phone** — every
page with a table — so a reader on a phone could not see that `Free` and `Status` existed at
all. Neither defect is subtle; both are invisible to assertions about text and structure,
which is what every layer of this suite had been. There are now two more: `inZone` is tested
where it is decided, and `tests/e2e/phone.spec.ts` drives all twenty surfaces at 375px and
fails on a single pixel of horizontal scroll, with one axe run at that width because making a
table scroll is also what makes it a scrollable region that needs keyboard access.

**And the fleet board's `Online` assertion now creates the freshness it asserts**, instead of
inheriting it from a fixture that was seeded ten minutes ago. It reads the bearer token out of
the browser's own session cookie — `context.cookies()` can see an httpOnly cookie where page
JavaScript cannot — and posts a health report before it looks. That closes the third instance
of the rule two paragraphs down, and it was found the hard way: three separate runs failed on
it for a reason that had nothing to do with the product.

**The configuration board is four answers that look like two numbers.** A resolved value and
a flag's variant are the two things on that screen most likely to be read as something they are
not, so neither is rendered alone:

- **A default is not a setting.** An unset key reads back as its own default with scope
  `default` and no version, which is indistinguishable from a tenant that published the same
  value on purpose unless the scope is shown. The board says "nobody set it".
- **`off` is four different facts.** A kill switch somebody engaged, a flag nobody enabled, a
  targeting rule that sent this subject to the control arm, or no rule matching at all — and an
  operator in an incident needs to know which. The kill switch gets an alarm because it
  outranks every rule and is a deliberate stop rather than a rollout.
- **A rule id is not a reason.** `rule:0f3a…` tells a reader nothing; "a targeting rule
  matched" is the answer, and the id stays in the data for whoever is debugging.
- **A flag is evaluated per subject, and there is no route that lists flags without evaluating
  them.** So the board is "what these flags say for one subject" rather than "what flags
  exist", which it says — because otherwise a flag missing from it reads as a flag that is
  absent. The subject is the reader's own identity unless a link names another: derived, not
  accepted.

**The schedule board is the second place a withheld field reaches a reader, and the first
where the page has to say which of two refusals it is.** MOD-019 masks a session change's
`reason` for anybody who does not hold `scheduling.session.change`, after a reviewer read a
staged diagnosis out of that column holding only the routine schedule permission. So the page
marks the withholding rather than dropping the entry — an absent row says nothing changed,
which is a different and wrong fact — and then asks the gate *why*, because `reason_masked` is
one boolean over two situations with different remedies: a session too weak for a financial
action, which a step-up fixes, and an identity that does not hold the permission at all, which
it would not. Offering a step-up for the second sends somebody looking for a second factor
that changes nothing.

**The owner cannot read it either**, which is the finding worth carrying: `scheduling.session
.change` is financial class, so `held_permissions` filters it out of a password-only session
even for an identity holding all 202 permissions. That is MOD-014's "a grant is not a session"
showing up as product behaviour. Proving the *other* answer needed a session that is genuinely
masked, so the fixture's second identity now holds `scheduling.schedule.read` without
`scheduling.session.change` — signing in as the owner could only ever have proved the step-up
half.

**Two numbers on the board are explained because the module refuses to store them.** `Taken`
is a sum over the hold rows and `Free` is MOD-019's own answer rather than a subtraction: there
is no `held_count` anywhere in the module, so a surface that computed `places - held` would
render a negative number for a session whose overbooking was reduced after the holds were
taken. `dst_adjusted` is the one flag marked, because an occurrence stepped forward for a clock
change is a session whose members were told a time that is not when it happens — a full class
is ordinary and a cancelled one is a decision somebody made.

**The roster is on the session page and gated on its own**, because the module boundary
paragraph 4145 draws puts the occurrence and its capacity on the schedule's side and the
member's reservation on booking's. A reader may hold one permission and not the other, so the
block says "not permitted" rather than rendering an empty class — "nobody is booked" and "you
may not see who is" are different facts, and the first is the one a coach would act on. The
seats above it are the schedule's: there is no roster table and no cached total, so a surface
that counted the rows it was handed would disagree with the seat count the first time a hold
existed with no booking behind it, which an unanswered waitlist offer is.

**And listing the sites is a different permission from reading the schedule.** The calendar
carries the site's own name and timezone, so the board needs no hierarchy read; only the picker
does. Separating them is what let the masked-reason case be tested at all, and a session with
the schedule read alone is told to open the board from a link rather than shown an empty picker
that would read as "this tenant has no sites".

**The operations board was built to make the repository's most-repeated gap visible, and the
worker runtime then changed what it shows.** "Nothing drives this on a schedule" appeared in
fourteen module entries in `CLAUDE.md`, and the event outbox was where it became countable:
every module writes to it, the table has no DELETE grant, and nothing drained it — so the
number climbed whenever somebody used the product and the page's whole job was to stop that
reading as an incident.

**The relay now runs every fifteen seconds, so a pending event is a signal rather than a
standing condition.** One that persists means the worker is down, which is the first fault
this page can diagnose instead of excuse. A pending *delivery* is unchanged: no name in this
build has a handler behind it, so that half still accumulates whatever the relay does, and
`backlogIsExpected` is still the question for it.

**Telling those apart needs evidence the worker ran**, which the scheduled-jobs block carries
from `/ops/worker`. A zero there is a sentence rather than an absence — every job runs for
every schedulable tenant at least every five minutes, so no recorded run over a window of
hours is a stopped worker, while a count against an *expected* count is deliberately not
returned because every reading of it is wrong unless the worker was up for the whole window — and `relayVerdict` keeps `no_evidence` apart from `stopped`,
because a reader without `ops.metric.read` has learned nothing and a page that called that an
incident would be inventing one out of its own permissions. A dead letter stays apart from all
of it, because that one *is* a fault whatever else is true.

**And the fixture runs the real worker.** `python -m app.worker --once` is its last step, so
the board is asserted against rows a scheduled job actually wrote. The spec that used to
assert the pending count was *not* zero now asserts that it is — which is the clearest single
measure of what this change did.

Five blocks, five permissions, each gated on its own, because an empty dead-letter table
somebody may not see reads as "nothing is quarantined".

**A fleet board is three answers, and the fixture seeds all three.** One healthy turnstile
cannot show what the board is for: an operator has to tell a door that works from a door that
cannot be put into service because paragraph 4175's commissioning is incomplete, and both from
a device that is not a door at all. The fixture now seeds a commissioned and reporting
turnstile, one with four of the seven tests recorded, and a scanner that declares no
`access.actuate` -- so the assertions are about telling them apart rather than about rendering
a row.

Three things the pages say out loud because the product cannot do them:

- **reachability is worked out from the last report, not stored**, and nothing in this build
  polls on a schedule -- so the board is "as of" when it was loaded rather than live;
- **"needs somebody" is `active` *and* `offline` together.** A device deliberately in
  maintenance is not an incident and one nobody has finished installing is not either; listing
  them is how an alert channel gets muted, and the mutation sweep widens the rule to prove the
  assertion bites;
- **a credential is a fingerprint and a reference to a secret this build cannot read.** No
  signature is verified anywhere, so the device's identity is what somebody recorded -- and
  MOD-022 opens doors on that identity, which is why the disclosure is on the page rather than
  in a design note.

And the commissioning block lists **all seven tests** with which have a passing record, not
only the missing ones: a list of what is missing cannot be told from a list of everything when
nothing is missing, and the question being answered needs the denominator.

**A hash chain's green answer carries its caveat, or it is the more misleading of the two.**
MOD-008's audit chain detects editing and not truncation by somebody who also moves the head,
because every value the verifier compares lives in the database that actor already controls --
found by tamper-testing rather than reasoned about afterwards. So the permissions page prints
the caveat beside "the chain verifies" rather than under "it does not", and the mutation sweep
deletes the caveat to prove the assertion bites.

**And the log is described by what is in it.** The first version of that page said allowed
actions are never recorded. They mostly are not -- there is no row saying somebody read a
member's profile -- but MOD-008 records the acts that *hand out* access: a role created, a role
granted, an approval decided. The fixture's own log shows `role.assigned` with outcome
`recorded`, which is how the claim was caught. A surface that describes a log wrongly is worse
than one that does not describe it.

**The account page is the first screen in this app that writes, and the write is why it
exists.** Everything before it is a read -- deliberately, because every `tenancy.*`,
`config.*`, `catalog.*` and `finance.*` write is a stepped-up financial permission and a form
for one is a form whose first act is a step-up. MOD-007's own routes are the exception: they
are scoped to the caller's own identity by `owned`, which refuses any other subject with a 404,
so there is nothing to authorize and nothing to step up *for* -- which makes them the four
writes a member can be given without inventing an approval flow.

Four decisions carry it:

- **It is a client component, and the recovery codes are why.** MOD-007 stores only a hash of
  a code, so a fresh batch exists in exactly one HTTP response and nowhere else. A redirect
  would lose it; carrying it in a query string or a cookie to survive one would be writing
  permanent credentials into somewhere a browser keeps things. `useActionState` renders the
  batch in place, once, and the page says so -- because a reader who assumed they could fetch
  them again would write none of them down.
- **The button is offered only where the server would accept it.** `_issue_codes_in_tx` takes
  the current password or a stepped-up session and deliberately *not* the recovery allowance
  `set_password` has, because MOD-007's second review found a stolen recovery session minting
  ten fresh codes with no password and those codes surviving the owner's own reset. So
  `mayIssueRecoveryCodes` is `aal >= 2`, a level-1 session is told what it needs rather than
  shown a button that fails, and the mutation sweep returns `true` to prove the assertion bites.
- **A live session is two facts, not one.** Revoked is explicit and expired is a comparison,
  and a board that read only the flag would list a fortnight-old session as still open. The
  server filters and bounds the page -- `live_only=true&limit=20`, added for this -- and
  `sessionIsLive` is the belt that keeps a row out if the clock moved between the read and the
  render.
- **The decisions have no imports, and that is not tidiness.** The first version put them in
  `src/lib/account.ts` beside the fetchers, which reach `@/lib/api` and therefore
  `next/headers` -- and a client component that imports a module touching `next/headers` fails
  the build, so **the login page started answering 500**. The split into `account.ts`
  (decisions, importing nothing) and `account-reads.ts` (I/O) is the one the backend makes
  between `domain` and `service`, arrived at the hard way.

**And the most consequential button on it gave no feedback at all.** Revoking a device
revokes every session on it, so revoking the device you are reading the page in ends the
session that pressed the button -- and the action returned a success message to a page that
no longer had a session to render it on. Nothing appeared, the reader was left looking at a
stale screen, and the next navigation threw them to sign-in with no explanation. It now asks
the server whether it still has a session -- derived, rather than a hidden field saying "this
one is mine" -- clears the cookies and sends the reader to sign-in with the reason named. The
redirect has to happen **outside** the action's own catch, because `redirect` works by
throwing and the catch would have reported the navigation as a refusal.

That is also why the page says what revoking costs *before* the button. MOD-007 refuses a
revoked device at the next sign-in rather than challenging it -- `device.readmission_refused`,
answered as the same 401 a wrong password gets -- and the fingerprint is derived from the
tenant and the identifier, so the next attempt produces the same value. The copy said the
sign-in would be "challenged again", which is the one reading that lets somebody lock
themselves out believing they can get back in. Nothing in 2,089 backend tests covered that
refusal until this page needed it, although `revoke_device`'s own docstring records the
regression it closed.

**And the page was 13,542 pixels tall when it first rendered**, because it listed every
session an identity had ever opened beside a hundred authentication events. Both reads are
bounded at twenty now and it is 3,923 -- but the interesting half is that the bound had to go
on the *server*: a client that fetched everything and sliced would still have carried the whole
list across the wire, which for a session list is a page describing every device a member has
ever signed in from.

## Findings raised against the sources

**`ai.600`'s published contrast ratios do not match its published hex.** `ds.json`'s CONTRAST
row prints 9.31 / 8.40 / 7.75 on warm.0 / warm.100 / warm.150; `#4a3d7a` computes to
9.30 / 8.39 / 7.74 — high by exactly 0.01 on all three, which is systematic rather than
rounding. A search of the indigo neighbourhood finds no hex that yields the printed trio and
equals `#4a3d7a`, so the table was computed from a slightly darker shade than the one shipped.
**No accessibility consequence**: all three computed values clear AAA for small text, so every
claim the foundations make about the token holds. Pinned in
`tests/unit/contrast.test.mjs` as a named discrepancy rather than hidden behind a tolerance,
so correcting either the hex or the table fails the test and a human reads the diff. The
other 8 of 9 tokens recompute to the printed hundredth on all three surfaces.

## The design system, read at last

**`veyro-product-experience-design/` is the single authoritative source for frontend design**,
under the owner directive of 2026-11-20, and `ds.json` was never it. `ds.json` is Step 2 —
colour, type, density, breakpoints, Arabic rules, contrast, guardrails. Steps 3, 4 and 5 are
37 component families with published APIs, a state matrix and three contracts each; nine
domain families; ten patterns, four confirmation tiers and fourteen cross-cutting rules. None
of it had been opened, and neither had any of the 170 screen specifications. Fifteen screens
were built on the foundations alone, and every one of them invented its own components.

`src/design/extract.mjs` extracts the rest and pins every source file by SHA-256. It runs the
documents' own data declarations in a sandbox, because the tables are rendered from JavaScript
arrays and scraping the markup captures `{{ m.c0 }}` rather than the values. `npm run
design:check` fails on a stale extraction and CI runs it **before** `tokens:check`, because
the tokens are generated from the contracts — a stale extraction would regenerate tokens that
agree with the wrong source and the later check would pass.

`contracts/ui/design-compliance.md` is the ledger: every family, every pattern, every shell
requirement and every screen, in the five states the directive distinguishes — implemented,
functionally tested, spec verified, visually verified, blocked. **No screen in this repository
was spec verified before the directive**; every one was at most functionally tested.

**The shell had been specified, extracted and ignored.** `LAYOUTS` says Veyro Admin is a
12-column grid with a 24px gutter, a rail of 240 collapsing to 56, content capped at 1440 and
an inspector of 380 widening to 480, with split view as list-plus-inspector and never three
columns. What shipped was a horizontal strip of fifteen links over a single column capped at
960px. The numbers are now **parsed from the source's own sentence** rather than retyped — the
Foundations document records that four precision slips in the design project were all caused by
a number being copied rather than referenced — and `tests/unit/shell-tokens.test.mjs` asserts
each one, every density block, and every media query in the app against a breakpoint boundary,
which is the one place a design number has to be a literal because a media query cannot read a
custom property. Five mutations, all caught.

**The ad-hoc layer is deleted.** `src/components/controls.tsx` held a Button with two of seven
variants, a field that rendered a hint and an error at once, and an `Alert` — three components
duplicating approved families, which the directive forbids by name. 152 call sites moved to
`Banner`, with the source's own tone mapping: `error → critical`, `warning → attention`, and
**`success → neutral`, because "success is not a severity, it is the neutral case"**, so four
success banners lost their green. A shim named `Alert` forwarding to `Banner` was considered
and not written: that is the duplicate name the rule is about.

Two things that migration taught, both recorded in `.claude/rules/`:

- **The severity map was wrong, and a generated one caught it.** Written by hand from §30,
  whose Payment line names five states — Step 4 names *ten*, each with its own severity, and
  Retrying, Overdue, Disputed, Cash pending and Wallet applied exist only there. A payment row
  could not be marked overdue at all, which is the one payment state a members table exists to
  surface.
- **Replacing an ad-hoc component with the approved one can drop a contract the ad-hoc one
  happened to satisfy.** The old button hard-coded `minHeight: 44px` and met the touch floor by
  accident of one line; the design system's Button defaults to `md`, which is 36. The sign-in
  button — the one control a member must hit before anything else works — became 36px on a
  phone while becoming more compliant in every other respect. Only the browser suite could see
  it. The floor is in the component layer now, under `(pointer: coarse)`, which is where the
  source puts it.

**`tests/unit/ds-usage.test.mjs` keeps the backlog honest.** 18 screens still hand-roll a
`<table>` where `DataGrid` exists and 22 still group with a bare `.panel` where `Card` does;
both lists are swept in **both directions**, so a screen that quietly stops being migrated
fails and so does an exemption that is no longer true.

## What this does not yet cover

- **Twenty-one screens of a hundred and seventy.** `contracts/ui/screen-contracts.yaml` lists
  170 V1 screens across five surfaces; what exists is sign-in, the step-up, an admin landing
  page, the account page, MOD-004's organization hierarchy, MOD-005's configuration board,
  MOD-009's erasure disclosure, MOD-012's integrations board, MOD-013's messages board,
  MOD-014's duplicate queue and Member 360 (with MOD-017's three blocks composed onto it),
  MOD-016's catalog board and product page, MOD-018's finance board, MOD-019's schedule board
  and session detail (with MOD-020's roster on it), MOD-021's fleet board and device detail,
  MOD-022's door board and zone detail, MOD-008's permissions page and the operations board.
  **All but the account page are read-only**, because every write in the modules they cover is
  a stepped-up financial permission and no form is built; MOD-007's four writes are the
  exception, for the reason the account section above gives. The foundation, the controls, the
  gate wiring and the six test layers are built to carry the rest, and the per-module work is
  wiring each one's gate, its masked fields and its failure states the way MOD-022's are.
- **`color.action.pressed` has no dark value**, declared in `ds.json`'s `DARK_GAPS`. The source
  names `accent.pressed` on that token and gives it no value anywhere — not in the ramps, not in
  the semantic table, not in the dark-mode note — and inventing a hex would be inventing design.
  Nothing renders a pressed state yet, so the defect is latent; the day a component implements
  one, this is the value to ask for.
- **Signing out clears the cookie and does not revoke the session.** MOD-007 has no "revoke
  the one I am holding" route, and revoking *all* of them would sign a member out of their
  phone because they closed a browser tab. The token stays valid until it expires; it is
  simply unreachable from this browser. The account page closes the half that *is* reachable
  -- every **other** live session is listed with a revoke button -- which is the useful half
  anyway, because the session somebody wants gone is the one they are not holding.
- **No visual regression baseline.** The E2E suite asserts computed tokens and layout
  relationships rather than pixels, which catches the defects found so far and would not catch a
  spacing regression.
- **One browser.** Chromium only; no WebKit, no Firefox, no real device.
- `color.surface.raised` is `warm.0 + e1`, a primitive plus an elevation. The generator
  reports it as needing a composite rule rather than inventing a hex; the component layer owns
  it.
- Four of the nine Arabic rules cannot be enforced by token resolution and are named in a test
  as belonging elsewhere: no italics, containers sized for Arabic, numerals as a tenant setting
  and bidi isolation. The last two live in `src/i18n/conventions.mjs`; the first two are a
  component and review obligation.
- **The EIP's "screen contract lint" does not exist.** The ordinary ESLint gate does now:
  `next lint` was removed in Next 16 and ESLint 10 ignores `.eslintrc.json`, so `npm run lint`
  answered "Invalid project directory provided, no such directory: .../lint" and nothing called
  it. `eslint.config.mjs` is the flat-config migration, its first run found four unused imports
  and variables, and it is in `npm run verify` and in CI. The other gate it names — a
  localization/RTL resource and accessibility gate exercised in E2E — now runs in
  `.github/workflows/veyro-foundation-ci.yml`'s `web` job, which builds the database, starts
  the backend, installs Chromium and runs the browser suite against the real API. A mocked
  backend would have passed every one of the defects the real one caught, which is why the job
  is slow on purpose.
- **A step-up spends a recovery code, and nothing in this build mints more on its own.** TOTP
  and passkeys are implemented and cannot be verified here, so a recovery code is the only
  second factor -- which means ten step-ups per batch. The account page reissues them now,
  which needs a stepped-up session, so the batch that runs out pays for the step-up that
  mints the next one with its own last code. A member who spends all ten without reissuing
  has no way back from this surface.
- **The people and access surfaces are read-only.** MOD-022's writes — declaring a zone, commissioning a
  point, publishing a policy, issuing a credential, ordering an emergency release — all have
  routes and none has a form yet. The two that need the most care are the two with a second
  actor: publishing a policy and reviewing a release.

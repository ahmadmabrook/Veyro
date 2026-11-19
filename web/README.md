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
duplicate queue and Member 360 with every masked field marked, MOD-022's door board and zone
detail, Arabic/English with full RTL, a dark theme, and four layers of tests that have each
been shown to fail when the thing they guard is removed.

| Layer | What it proves | Count | Command |
|---|---|---|---|
| Foundation (`tests/unit/`) | Tokens, contrast, type, theme coverage, backend parity. No dependencies, no DOM. | 57 | `npm run test:foundation` |
| Component (`tests/component/`) | Control semantics, the message catalogue, the sign-in form's four states, the device-label parity, the hierarchy composer, the mask marker and the redirect guard, in jsdom. | 38 | `npm test` |
| End-to-end (`tests/e2e/*.spec.ts`) | A real browser against a real backend, including 17 axe runs across both locales and both themes, the no-JavaScript sign-in replay, three surfaces driven as a session that may not read them, and a session raised from level 1 to level 2 for real. | 86 + 2 setup | `npm run e2e` |
| Mutation sweep (`tests/e2e/mutate.mjs`) | Each protection above, broken on purpose, is caught by the test that names it. | 36/36 | `npm run e2e:mutate` |

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

## What this does not yet cover

- **Ten screens of a hundred and seventy.** `contracts/ui/screen-contracts.yaml` lists 170 V1
  screens across five surfaces; what exists is sign-in, an admin landing page, MOD-004's
  organization hierarchy, MOD-014's duplicate queue and Member 360, MOD-022's door board and
  zone detail, MOD-008's permissions page, and the step-up flow. The foundation, the controls, the gate wiring and the four test
  layers are built to carry the rest, and the per-module work is wiring each one's gate, its
  masked fields and its failure states the way MOD-022's are.
- **`color.action.pressed` has no dark value**, declared in `ds.json`'s `DARK_GAPS`. The source
  names `accent.pressed` on that token and gives it no value anywhere — not in the ramps, not in
  the semantic table, not in the dark-mode note — and inventing a hex would be inventing design.
  Nothing renders a pressed state yet, so the defect is latent; the day a component implements
  one, this is the value to ask for.
- **Signing out clears the cookie and does not revoke the session.** MOD-007 has
  `/identities/{id}/sessions` for listing and revoking, but no "revoke the one I am holding"
  route, and revoking *all* of them would sign a member out of their phone because they closed a
  browser tab. The token stays valid until it expires; it is simply unreachable from this browser.
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
  second factor -- which means ten step-ups per batch and a trip to
  `POST /identities/{id}/recovery-codes` after that. There is no screen for reissuing them.
- **The people and access surfaces are read-only.** MOD-022's writes — declaring a zone, commissioning a
  point, publishing a policy, issuing a credential, ordering an emergency release — all have
  routes and none has a form yet. The two that need the most care are the two with a second
  actor: publishing a policy and reviewing a release.

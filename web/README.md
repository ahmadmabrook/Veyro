# Veyro web

TypeScript / React / Next.js surfaces, per the Engineering Implementation Plan's repository
layout (`web/` TypeScript+React+Next.js, `mobile/` KMP+Compose, `edge/` Kotlin/JVM).

Surfaces this directory will own, from `contracts/ui/screen-contracts.yaml` (170 V1 screens):
Veyro Admin (85), Veyro Member (35), Veyro Coach (19), Front Desk & POS (16), Internal
Console (15).

## State

A running Next.js application: sign-in against MOD-007 including the device challenge it
raises, an admin landing page whose every control's visibility comes from MOD-008's gate,
MOD-022's door board and zone detail, Arabic/English with full RTL, a dark theme, and four
layers of tests that have each been shown to fail when the thing they guard is removed.

| Layer | What it proves | Count | Command |
|---|---|---|---|
| Foundation (`tests/unit/`) | Tokens, contrast, type, theme coverage, backend parity. No dependencies, no DOM. | 57 | `npm run test:foundation` |
| Component (`tests/component/`) | Control semantics, the message catalogue, the sign-in form's four states and the device-label parity, in jsdom. | 28 | `npm test` |
| End-to-end (`tests/e2e/*.spec.ts`) | A real browser against a real backend, including 10 axe runs across both locales and both themes, and the no-JavaScript sign-in replay. | 45 | `npm run e2e` |
| Mutation sweep (`tests/e2e/mutate.mjs`) | Each protection above, broken on purpose, is caught by the test that names it. | 18/18 | `npm run e2e:mutate` |

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

- **Four screens of a hundred and seventy.** `contracts/ui/screen-contracts.yaml` lists 170 V1
  screens across five surfaces; what exists is sign-in, an admin landing page and MOD-022's
  door board and zone detail. The foundation, the controls, the gate wiring and the four test
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
- **The EIP's "screen contract lint" does not exist.** The other gate it names — a
  localization/RTL resource and accessibility gate exercised in E2E — now runs in
  `.github/workflows/veyro-foundation-ci.yml`'s `web` job, which builds the database, starts
  the backend, installs Chromium and runs the browser suite against the real API. A mocked
  backend would have passed every one of the defects the real one caught, which is why the job
  is slow on purpose.
- **The access surfaces are read-only.** MOD-022's writes — declaring a zone, commissioning a
  point, publishing a policy, issuing a credential, ordering an emergency release — all have
  routes and none has a form yet. The two that need the most care are the two with a second
  actor: publishing a policy and reviewing a release.

# ADR-0015 — MOD-005: ADM-SET-07's numerals, and why a display convention has no cheap reader

- ID: ADR-0015
- Status: ACCEPTED
- Decision-Key: mod005-localization-display-conventions
- Covers: backend/app/configuration/, backend/app/authorization/catalog.py, backend/app/main.py, web/src/

**Dated 2026-11-25. Scope: ADM-SET-07.** Authority is
`knowledge/00-Decisions/OWNER-2026-11-13-full-engineering-delegation.md`, which delegates
ordinary product and architecture decisions. The source is the drawn canvas in
`veyro-product-experience-design/project/Veyro V1 Batch L Settings Search and Auth.dc.html`,
read in the batch file and not in `veyro-screen.js` — the prototype draws a different
ADM-SET-07, with a "Week starts · Saturday" field the deliverable does not have, and an earlier
version of this work was written from it.

## The canvas, verbatim

> **ADM-SET-07 · LOCALIZATION** — LANGUAGES OFFERED `English` `العربية` · NUMERALS `0123`
> `٠١٢٣` · "Arabic-Indic for counts, dates and times. Money keeps Latin digits with its code —
> JOD 41,280.00 — because that is the form on your invoices and JoFotara submissions. Applied
> identically on screen, receipt and export." · PREVIEW `تنتهي عضويتك في ٢١ آب · المبلغ JOD
> 55.00` · "One rule per tenant, never mixed and never decided per component." · "Month names
> follow the Levantine set — آب, تموز — because that is what Jordanian members read."

Four elements: a set of offered languages, one numeral choice, a preview that renders a real
sentence under it, and two rules. No control writes: the screen is read-only as drawn, which is
what MOD-005 can already answer.

## What already exists, and what does not

**The capability is built twice and selected nowhere.** `web/src/i18n/conventions.mjs` and
`backend/app/l10n/conventions.py` both implement `arab` in full — digit shaping, the Arabic
thousands separator and the Arabic decimal separator — and
`tests/unit/conventions-parity.test.mjs` spawns Python to compare them character for character,
because the canvas requires the rule "applied identically on screen, receipt and export" and a
receipt is rendered by the backend. **Nothing in the product ever passes `arab`**: seventeen
call sites hard-code `numbering = "latn" as const`, each with a comment saying the numeral
system is a tenant setting this build does not carry. That comment is the gap, and this is the
largest instance in the build of a capability with no caller — larger than `resolve_price`'s
`store` parameter, because two runtimes are kept in agreement by a test for a value nobody
chooses.

**The money half is already right, and the canvas says so rather than the reverse.** "Money
keeps Latin digits with its code" means the hard-coded `latn` on every money figure is the
design's own rule, honoured, not a workaround — which three comments in this repository
described as a limitation. What is missing is Arabic-Indic for the figures that are *not* money.

## The problem: there is no cheap reader

A tenant-wide display convention has to reach every rendered page. Three obvious routes are all
closed, and the reasons are structural rather than incidental:

- **`GET /config/resolved` is gated on `config.definition.read`.** That permission is routine,
  so no step-up is involved — but it means "see configuration definitions", the whole typed
  registry. Granting it to a receptionist so a page can choose its digits is MOD-013's
  `GET /notifications/channels` finding: "see notification templates" also bought "what every
  message costs the tenant".
- **`/auth/session` cannot read it.** Every page already calls `currentSession()`, so riding on
  that response would cost no round trip and need no gate — and `veyro_iam_app` holds nothing
  in `plt01` by design, so the identity plane physically cannot see `cfg_values`. The plane
  separation that makes a credential unreadable from a billing query also makes this
  unavailable.
- **`presentation()` is cookie-only.** It reads the locale, direction and theme from cookies
  with no request at all, which is why every page can call it. Resolving a tenant fact there
  means a request per page view, and MOD-011's budget is per identity — the rate-limit incident
  this repository records was a browser suite spending 600 requests a minute on gate calls.

## The decision

**D1 — Its own narrow read, with its own routine permission.** `config.display.read`,
`data_access` with no financial class, and `GET /config/display` returns exactly the tenant's
offered languages, its numeral system and the month-name set. It is a separate permission
rather than `config.definition.read` because the whole point is that a front desk holds it: a
read that costs the registry is a read a receptionist will not be granted, and then the page
falls back for the wrong reason.

**D2 — A refused or failed read falls back to `latn`, and the page does not say so.** A display
convention is not a fact a reader acts on, so a gate answer must not be able to break a page or
put a notice on one. `latn` is what every page renders today, so the fallback is exactly the
current behaviour — which makes this change inert for any reader who lacks the grant and
removes the risk that adding it changes what somebody sees without their asking.

**D3 — The conventions are not sensitive, and that is why D1 is a permission rather than
`UNGATED`.** A page rendering Arabic-Indic digits discloses the setting by rendering it, so the
read reveals nothing a reader cannot already see. But `UNGATED` is for routes that ask nothing
at all, and this one is per tenant; `GateCoverageTests`' own discipline is that adding to that
list should be uncomfortable, and a route with a tenant and a trivially grantable permission
does not need to be on it.

**D4 — One key per convention in MOD-005's typed registry, and the numeral system is a
`string` rather than a `json` blob.** "One rule per tenant, never mixed and never decided per
component" is the canvas's own sentence, so the value is a single key the registry validates
against a closed set of two. The offered languages are a `json` array because they are a set.

**D5 — The month-name set is derived, not configured.** The canvas states it ("Month names
follow the Levantine set — because that is what Jordanian members read") rather than drawing a
control, in the same way CON-04 derives the week start from the region: "Jordan sets data
residency, JOD as the currency, the JoFotara tax adapter, Arabic as an available language, and
a Sunday week start." So a second control would be a second place for the same fact to be
decided, which is this build's most-repeated finding.

**D6 — `formatMoney` is always called with `latn`, and that is checked rather than remembered.**
Every other figure takes the tenant's numbering; money does not, by the canvas's rule. A static
sweep over the call sites is what keeps it so, because the two differ by one argument and the
parity test cannot see which value a caller passed.

## What this does not decide

- **Writing any of it.** The canvas draws no control and MOD-005's value publication is
  `config.value.publish`, financial class — so the screen is a read, and a tenant changes its
  conventions the way it changes any other configuration value. That is MOD-005's standing gap
  about a read-only surface, not a new one.
- **The preview's own correctness beyond the two conventions it renders.** `تنتهي عضويتك في ٢١
  آب` needs Levantine month names, which `formatMonthDay` does not carry; that is part of this
  slice's work. The money half of the preview already renders correctly.
- **Whether the week start is displayed here.** The *inventory* row for ADM-SET-07 lists "week
  start" among its concerns and the drawn canvas does not show it. The drawn canvas is the
  deliverable, so it is not drawn; CON-04 is where the fact is stated and `availability.
  week_from` is where it is applied.
- **The seventeen call sites' own correctness.** Each currently passes `latn` and will pass the
  tenant's value; whether every figure on every screen *should* follow the tenant's numerals is
  the canvas's claim rather than this ADR's, and the one exception it names is money.

## Amendment, 2026-11-25 — what building it changed

Three things in the record above were wrong or understated, and the slice is recorded in
`CLAUDE.md` and in `contracts/ui/design-compliance.md`.

**`formatMonthDay` does not exist and never did.** "What this does not decide" says the preview
"needs Levantine month names, which `formatMonthDay` does not carry" — naming a function that
is in no file, which sends a reader looking for it. Nothing in this build renders a month name
at all. `web/src/i18n/dates.ts` is the new one, called `monthDay`, and it is web-only: it
cannot live in `conventions.mjs`, because that module is compared character for character
against `backend/app/l10n/conventions.py` and Python's standard library carries no CLDR month
names — a twin needs `babel`, which would be this repository's second dependency ever. The
canvas's rule is "applied identically on screen, receipt and export" and a receipt is rendered
by the backend, so the twin is owed the day one renders a date.

**The read returns the money rule as a token, not as the sentence D6 implies.** The first
implementation returned English prose, and this application has no fallback to English — so an
Arabic reader could never be shown that field, which means the screen words the rule itself and
the server's field is read by nothing. `money_numerals: "latn"` is the fact; the catalogue
words it; `formatMoney`'s callers get a value to pass rather than a constant to remember, which
is what D6 was reaching for.

**A regional tag carries a default numbering system, which D4 and D5 between them do not say.**
`ar-JO` resolves to `arab`, so taking the month name from the region would take the digits from
it too — the thing `formatInteger`'s own contract forbids. The tag is forced to `-u-nu-latn`
and `shapeDigits` decides the digits. Within this build's two locales that forcing is
*redundant*, because `shapeDigits` normalises in both directions; it is kept for a third
locale, whose default digits it would not know how to undo, and no mutation can catch it until
such a locale exists.

**What D1 to D6 got right, confirmed by building it**: the narrow permission (the fixture's own
tenant_admin went from 224 permissions to 225 and a reader without it is correctly refused);
the `latn` fallback, which is why a refused read breaks no page; one key per convention with the
numeral system as a validated `string`; the derived month set; and the money exception. **And
D1's premise held in a way worth recording**: adding the permission to the catalogue granted it
to nobody, because `authz.bootstrap` stores the list it computed when it ran — so the browser
fixture had to be re-provisioned before the screen could be exercised at all.

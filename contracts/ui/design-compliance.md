# Design compliance ledger

**Authority.** `veyro-product-experience-design/` is the single authoritative source for all
frontend design, under the owner directive of 2026-11-20. Design fidelity is mandatory; visual
improvisation is prohibited. Derived artefacts — `web/src/design/ds.json`,
`web/src/design/contracts.json`, `tokens.generated.css`, `contracts/ui/screen-contracts.yaml`,
this file — are evidence *about* the source, never a substitute for reading it.

**What this file is for.** The directive requires traceability between the design
specification, the implementation and the verification evidence, and a durable record that
survives context compression. This is that record. It is the answer to "is this screen done",
and a green CI run is not that answer.

## The five states

Every row below carries one of these, and nothing is promoted without the evidence named.

| State | Means | Evidence required |
| --- | --- | --- |
| `implemented` | Code exists and renders. | — |
| `functionally tested` | Its behaviour is asserted against the real backend. | A named test |
| `spec verified` | Every explicit contract, dimension, layout rule and state in the source is implemented and asserted. | A named test per contract |
| `visually verified` | Rendered output compared against an authoritative reference. | The reference, named |
| `fully verified` | All four above. | All four |
| `blocked` | The source does not resolve the question. | The unresolved requirement, stated |

**A baseline generated from the implementation is not an authoritative reference.** The source
files are specifications, not pixel comps, so `visually verified` means the explicit
dimensions and layout rules were measured in a browser — not that a screenshot matched a
screenshot this repository produced.

## Audit of 2026-11-20 — what the pre-directive frontend actually was

Fifteen screens were built against `ds.json` (Step 2: colour, type, density, breakpoints,
Arabic rules, contrast, guardrails) and nothing else. The component library, the patterns, the
domain components and all 170 screen specifications were never read. Stated plainly because
the directive requires deviations to be recorded rather than discovered:

| Area | Source | Status before this directive |
| --- | --- | --- |
| Colour, type, contrast, RTL rules, numerals | `Veyro DS Foundations.dc.html` | **Extracted and tested.** `ds.json`, the token generator, the contrast and parity suites. The one part that was genuinely followed. |
| 37 component families | `Veyro DS Core Components.dc.html` | **Not read.** `src/components/controls.tsx` held a Button with 2 of 7 variants and no size prop, an Input, and an Alert. Tables, label/value grids and panels were hand-rolled per page. |
| 10 patterns, 4 confirmation tiers, 14 cross-cutting rules | `Veyro DS Patterns.dc.html` | **Not read.** |
| 9 domain families | `Veyro DS Domain Components.dc.html` | **Not read.** |
| Application shell | `LAYOUTS` in Foundations | **Extracted into `ds.json` and not implemented.** The source states a 12-column grid, a 240px rail (56 collapsed), content capped at 1440 and an inspector of 380/480 with list-and-inspector split view. What existed was a horizontal nav strip over a single column capped at 960px, on every page. |
| 4 density modes | `DENSITY` in Foundations | **Extracted and not implemented.** No density mode is selectable or applied. |
| 170 V1 screens | `V1 Batch *` files, `Veyro Screen Registry` | **Not read.** The fifteen screens that exist were composed from what each backend module's routes can answer. |

**No screen in this repository was `spec verified` before this directive.** Every one was at
most `functionally tested`.

### The ad-hoc layer that is gone

`src/components/controls.tsx` held a Button with two of seven variants, a field that rendered
two messages at once, and an `Alert` — three ad-hoc components duplicating approved families,
which §8 of the directive forbids by name. It is deleted. 152 `Alert` call sites across 25
files became `Banner`, and the tone mapping is the source's: `error → critical`,
`warning → attention`, and **`success → neutral`, because "success is not a severity, it is
the neutral case"** — so the four success banners lost their green, which is the rule doing
its job rather than a regression.

A compatibility shim was considered and not written: a component named `Alert` forwarding to
`Banner` is exactly the duplicate name the directive rules out.

**The table migration is complete.** All 26 hand-rolled tables across 18 screens are on
`DataGrid`, and each gained what a table built by hand could not express: a column priority
that collapses the low ones into the primary cell instead of pushing them off the screen, and
a row-level severity edge-mark wherever the board has a row somebody must act on — a zone with
no live policy, a job that never ran, a dead letter, a critical install missing its written
obligations, an overdue data-subject request, a promotion that reads active and ended in
February. `tests/unit/ds-usage.test.mjs` has stopped being a backlog for tables and become an
absolute rule: the next raw `<table>` in a screen fails it.

**And the panel migration was not what it looked like.** The obvious correction was
`.panel` → `Card` on all 64 sections. The right one was to stop boxing them: §31 says a Card
is "meaningful grouping only", six kinds, and "a card that only draws a border around a
paragraph is deleted — 'cardification' of every screen is explicitly prohibited" — and six
bordered boxes stacked down a report page is that anti-pattern at the scale of a whole
surface. A page section is now a heading with a rule under it, its prose and its grid,
separated by the type scale and the shell's gutter. `.panel` is deleted from the stylesheet
and `Card` is kept for content that genuinely is one.

**One extension beyond what the source states**, recorded here rather than made quietly:
`DataGrid` takes a per-column `total`, rendered in a `<tfoot>` with the column's own priority.
§25's anatomy names a saved-view bar, a filter bar, a header, rows, a bulk-action bar,
pagination and column config, and no footer — but a trial balance's two totals are what a
month-end close is signed off against, and putting them outside the grid would align them
under nothing.

## Component families — 37

Status per family. `—` means not started. The state matrix (`contracts.json` → `matrix`) says
which states each family must ship; the three contracts (`→ contracts`) say what its
accessibility, RTL and responsive behaviour must be.

### Primitive · 17

| Family | State | Notes |
| --- | --- | --- |
| Button | implemented, spec verified | `ds/button.tsx`. 7 variants, 3 sizes read from the extraction, loading keeps the label, icon-only has a name, `href` renders an anchor, `requiredSize` enforces 44px at Touch and Spacious. 6 assertions. |
| IconButton | — | |
| Input | implemented, spec verified | `ds/field.tsx`. One shell, 18 types as control swaps, exactly one message with the stated priority, bidi isolation per type, numeric keyboards derived. 7 assertions. **`controls.tsx`'s field rendered a hint and an error at once**, which §23 rules out; that test became a test that one is shown. |
| Select | — | |
| Combobox | — | |
| Checkbox | — | |
| Radio | — | |
| Switch | — | |
| Textarea | — | |
| Chip | implemented | `ds/primitives.tsx`. Kept distinct from Badge: a badge states a status from a fixed vocabulary, a chip is a filter the reader can remove. |
| Badge | implemented, spec verified | `ds/status-badge.tsx`. Severity and vocabulary **generated** from the source, not transcribed: §30 names five payment states and Step 4 names ten with their own severity column. 6 assertions. |
| Avatar | implemented | Initials, not a photo: there is no object store, and a broken image is worse than initials. `aria-hidden` beside the name it derives from. |
| Icon | — | Mirroring is per-icon, from the icon manifest |
| Tooltip | implemented | `aria-describedby`, and the prop is named `supplementary` so the call site says out loud that nothing here is the only copy of that information. |
| Divider | implemented | |
| Skeleton | implemented | Height required, `aria-hidden`: a placeholder shorter than its content makes the layout jump. |
| Spinner | implemented | Takes a label, because the two places a spinner could go — a grid and a button — both rule out a bare one. |

### Composite · 14

| Family | State | Notes |
| --- | --- | --- |
| DataGrid | implemented (server subset), spec verified | `ds/data-grid.tsx`. Nine states, three distinct empties, restricted cells, priority 1–3 with the dropped value moving into the primary cell, one composite tab stop, money read with its kind, list form at bp.xs. 8 assertions. **Sorting, selection, the bulk bar and the inspector are interactive and not built** — they belong to a client subclass. |
| FilterBar | — | |
| SavedViewBar | — | |
| BulkActionBar | — | Partial-failure breakdown; never reports "done" |
| SearchField | — | |
| CommandPalette | — | 4 fixed result classes; actions never execute on ⏎ |
| Modal | — | |
| Drawer | — | Opens from the inline-end edge |
| Sheet | — | Mobile only; two levels maximum |
| Tabs | — | Five maximum |
| SegmentedControl | — | 2–4 exclusive options |
| Card | implemented, spec verified | `ds/card.tsx`. `kind` is required over the six; there is no default, so "cardification" has to be argued for at the call site. |
| Banner | implemented, spec verified | `ds/banner.tsx`. The role is the decision; `critical` refuses to be dismissible whatever the caller passes. 2 assertions. |
| Toast | implemented, spec verified | `ds/toast.tsx`. 30s window, one at a time, polite live region, undo keyboard-reachable for the full window. **No surface uses it yet** — the account page's four confirmations are the first candidates, and they are Banners today. |

### Date & time · 6

| Family | State | Notes |
| --- | --- | --- |
| Calendar | — | Days mirror, weeks do not; week start is a market token; Arabic grid is wider and that is correct |
| DatePicker | — | |
| DateRangePicker | — | Presets first; "From" keeps reading order in RTL |
| TimePicker | — | Stepped at the tenant's booking granularity, never free text |
| WeekView | — | |
| DayView | — | Front Desk default |

### Domain · 9 (Step 4)

| Family | State | Notes |
| --- | --- | --- |
| PersonRow | — | One component, four densities, four subjects |
| TimelineItem | — | Actor always named, including "Veyro" |
| MembershipCard | — | Renewal terms always visible; freeze allowance used-of-total |
| BookingCard | — | Waitlist position and honest odds |
| AccessPass | — | Renders offline from cache and says so |
| TaskRow | — | Every task names its provenance |
| PlanBuilderRow | — | Locked rows say why |
| ConsentBlock | — | Health and biometric are separate records |
| StaffAvailability | — | "Unqualified" is distinct from "unavailable" |

## Patterns — 10 (Step 5)

| Pattern | State |
| --- | --- |
| 01 Attention queue | — |
| 02 List → inspector | — |
| 03 Capture → resolve | — |
| 04 Guided sale | — |
| 05 Assisted create | — |
| 06 One-tap log | — |
| 07 Bulk act | — |
| 08 Ask → evidence → act | — |
| 09 Scoped compare | — |
| 10 Approval request | — |

## Shell and foundations

| Requirement | Source | State |
| --- | --- | --- |
| Admin: 12-column, 24px gutter | `LAYOUTS` | implemented, spec verified |
| Admin: rail 240 expanded / 56 collapsed | `LAYOUTS` | implemented, visually verified (measured at 1400px: rail exactly 240) |
| Admin: content max 1440 | `LAYOUTS` | implemented, spec verified |
| Admin: inspector 380 at bp.lg, 480 at bp.xl | `LAYOUTS` | implemented, spec verified. **No screen uses it yet** — the slot exists and the list-and-inspector pattern is not built. |
| Admin: split view is list + inspector, never three columns | `LAYOUTS` | implemented, spec verified (a third track fails the test) |
| A screen may set its own density | `LAYOUTS`, ADM-MEM-05 | implemented, spec verified. The generated selector was `:root[data-density=…]`, which matches only `<html>` — so a screen setting it on its own wrapper read as compact and rendered at the default row height. Found by measuring the rendered rows. |
| Four density modes | `DENSITY` | implemented, spec verified. The 44px button floor applies at Touch, Spacious and wherever the pointer is coarse. **No surface selects a mode yet**: `data-density` is honoured and nothing sets it per LAYOUTS (Front Desk Touch, Member Spacious, Console Compact). |
| Five breakpoints with declared per-surface behaviour | `BREAKPOINTS` | implemented, spec verified. Every media query in the app is asserted to sit on a breakpoint boundary. |
| Global chrome: scope switcher, ⌘K, tasks, alerts, account | §21 | partial. Account is a rail entry; language and theme are in the chrome slot. **Scope switcher, ⌘K and tasks/alerts are not built** — there is no scope concept on the client and no command palette. |
| Rail of eight, generated from role and scope | §21 | partial. The rail is generated from the gate per item, which is the role half; **the scope half does not exist** (every `permit` call is tenant-wide, which MOD-014 records as its own gap), so it renders every permitted section rather than a composed eight. A cut-off at eight would hide pages a reader can open. |
| Secondary nav capped at seven | §21 | — (no screen has a second level yet) |
| Light and dark themes | `THEMES` | implemented, spec verified |
| Arabic/English with RTL | `ARABIC_RULES` | implemented, spec verified |
| Contrast matrix | `CONTRAST` | implemented, spec verified |
| Numerals identical on screen and receipt | `ARABIC_RULES` | implemented, spec verified |

## The screen designs exist, and the registry is not them

**`screen-contracts.yaml` is an identity registry and says so**: every contract field is
`null` and the manifest reads "IDENTITY_ONLY - full screen contracts are UNRESOLVED". That is
true of the registry data file it was generated from. It was then read as true of the *design
folder*, which it is not.

The `V1 Batch *` documents carry screens **rendered**, with their exact copy, their column
sets, their quick filters, their bulk actions, their empty and error states, and an eyebrow
stating the roles, the density and the width each was drawn at. ADM-MEM-05 is the example
worth knowing:

> ADM-MEM-05 · MEMBERS LIST · CM, RECEP · COMPACT · 1440
> 4,812 rows, and the three you need
> … Owes money · 18 · Expiring · 14 · Not visited 30d · 214 · ＋ Filter · Save this view
> … 3 selected · Send message · Send payment links · Add to segment
> … Showing 1–50 of 18 matching · 4,812 total · Columns · Export · needs approval
> **There is no state where 4,812 rows render.**

Seven columns, three quick filters, a saved-view control, a bounded selection with an explicit
"select all 18 matching", an export behind an approval, and a stated scale rule. None of that
was in the registry, and none of it is in this app.

`web/src/design/screens.mjs` extracts all of it to `screens.generated.json`, pinned by
SHA-256 and checked by `npm run design:check` like the contracts.

### The first extraction found 37 screens and the design folder specifies 167

**That number was written into this file as a gap in the design source, and it was a gap in
the extraction.** The correction matters more than the arithmetic, because the wrong number is
what made composing a screen from backend routes look like the only option available.

The section boundary was matched inside a single CSS signature:

```
/letter-spacing:\.1em">([^<]{4,300})<\/div>/
```

which occurs in **nine of the forty-eight** design documents. The eyebrow in the others is set
at `.07em`, `.08em` or `.09em`, so every one of them was read as containing no screens:

| Missed | What is in it |
| --- | --- |
| `Veyro HF Command Center` | ADM-CC-01…05 — five canvases, 1440×900, the owner day, the branch-manager day, the critical exception, the quiet day and degraded data |
| `Veyro HF Member 360` | ADM-MEM-01…04 |
| `Veyro HF Front Desk and POS` | FD-01, POS-01 |
| `Veyro HF Coach` | CCH-01…03 |
| `Veyro HF Member App` | MBR-01, MBR-02 |
| `Veyro HF CRM and Console` | ADM-CRM-01, CON-01 |
| `Veyro HF Remaining Modules` | ADM-SCH-01, ADM-PAY-01/02, MBR-03, ADM-AUT-02, CON-02 |
| `V1 Batch M` … `Batch Q` | 12 screens each, and each announces that in its own header — "BATCH M · 12 SCREENS DRAWN · FD-02 → POS-07 · FRONT DESK & POS COMPLETE" |

So the boundary is now the **text** rather than its styling: a run beginning with one or more
screen ids and a middot, which is how all four generations of document in the folder title a
screen. The `HF` files title by role and state instead — `CANVAS 1 · OWNER · ALL LOCATIONS ·
NORMAL OPERATIONAL DAY · 1440×900` — and the registry's own `note` field is what names the id
for each (`ADM-CC-01` is "HF Command Center c1"), so those resolve through a declared mapping
that **fails the extraction if a note resolves to nothing**. That check caught its own first
version: the `V1 *` documents were listed in the mapping and title their screens by id, so
their canvas prefixes matched nothing.

**The real coverage, from the registry's own 178 V1 rows:**

| | |
| --- | --- |
| **Specified** — drawn, with copy, states and layout rules | **168** |
| `NO-UI` — the registry says the screen is not needed | 8 |
| **Genuinely unspecified** | **2** |

The two are `ADM-POS-02` (inventory and stock) and `MBR-33` (security and devices). Each has a
registry identity and a one-line note and no drawn screen anywhere in the folder; they are
named in `screens.generated.json → coverage.unspecified_ids` and nothing invents around them.

**It was three, and the third was drawn all along.** `ADM-CRM-05` read as unspecified because
Batch F titles one card **`ADM-CRM-03 · LEAD PROFILE · ADM-CRM-05 · TRIAL RUNNING`** — two
screens on one card, each with its own name — and the extractor took the ids *before the first
label*, so the second sat in the description and was never attributed. Its whole design was in
the file: a trial clock, four figures, a sentence and a button, indexed as a screen nobody had
drawn. The extractor now collects every `·`-separated segment that is **exactly** an id, which
is the shape of a co-label; an id mentioned inside prose ("ADM-MEM-11 exists because prevention
is never perfect") is still a cross-reference and still attributed to nobody. Exactly one
screen moved, which is what makes the fix surgical rather than a re-reading of the folder.

**And the registry's own `status` column is stale, which is why it is not the authority here.**
It marks 41 screens `DONE` and 129 `GAP`, while the batch documents drew 126 more after it was
last written — `FD-02` reads `GAP` in the registry and is drawn in full in `Batch M`. The
registry is authoritative for a screen's *identity*; the documents are authoritative for its
*design*.

`tests/unit/screen-coverage.test.mjs` is what stops this recurring. It pins the coverage count,
recomputes the set of documents that title a screen **independently of `screens.mjs`** and
compares both directions, asserts the seven `HF` files by name, and requires each `Batch M`–`Q`
document to contribute at least the twelve sections its own header claims. Mutation-proven: an
extraction narrowed to skip the batch documents drops coverage to 101 and fails four of its
seven assertions.

### And the existing surface does not follow the design's information architecture

This is the deepest fidelity gap and it is structural rather than visual. `web/` is organised
by **backend module**: a configuration board, a privacy board, an operations board, a fleet
board, an integrations board. The design is organised by **what an operator does**: Command,
CRM, Members, Membership, Payments, Scheduling, Staff, Settings, Reports, Comms, Automation,
Tasks, Access, POS admin.

Five of the existing screens have no screen contract at all, because no screen in the registry
corresponds to them. The others map loosely:

| Existing | Nearest design | Fidelity |
| --- | --- | --- |
| `/` | ADM-CC-01…05 Command Center | **built from the canvas** |
| `/members` | ADM-MEM-05 Members list | **built from the canvas**; its three absent columns and six absent controls are named on the screen, and its "Add member" button — specified, absent, and absent from the gap list too — now leads to ADM-MEM-10 |
| `/members/new` | ADM-MEM-10 Add member · manual | **built from the canvas, over a read that did not exist** — `find_duplicates` scores pairs that already exist, so the moment a duplicate is cheap to prevent had nothing to ask; the sale sheet, the emergency contact and the waiver are named as absent |
| `/people/{id}` | ADM-MEM-01/02 Member 360 | **rebuilt to the canvas** — pattern 02, the status band, five MetricCells, the tabs, the timeline spine |
| `/people/{id}?tab=billing` | ADM-MEM-06 Member · billing tab | **built** — the membership, the entitlements and the invoices composed from MOD-017 through three gates, each refusing separately |
| `/people/{id}?tab=membership` (freeze) | ADM-MSH-03 Membership · freeze | **built from the canvas, and the first stepped-up write form in this app** — the allowance reads routine, the act offers the step-up with `next` back here; the override at the limit and the thirty-second undo are named as absent |
| `/people/{id}?tab=membership&cancel=1` | ADM-MSH-07 Membership · cancel | **built from the canvas, and building it found that the design and the implementation disagreed about a money figure** — the canvas buys out a commitment for a two-month fee and the lifecycle held the member to the term, which nothing had noticed because no screen rendered the fee. The commitment line is four sentences, the fee is shown in parts, and the freeze the canvas offers instead is offered only where both halves of its argument hold. Drawn as a parameter on the tab rather than a side sheet, which this app has none of. **All four commitment sentences render now, and seeding them is what found that one of them could not**: `held_to_term` was keyed on whether access ends before the term, which is false for exactly the member a contract holds to it, so a member nine months into a twelve-month commitment was told it had been served |
| `/people/{id}?tab=notes` | ADM-MEM-09 Member · notes | **read built, write blocked** — `people.note.write` is financial class, because a note cannot be edited and will be read in a dispute; a redacted note is marked rather than dropped |
| `/integrations` | ADM-SET-05 Integrations index | **built** — the install, its criticality and its written obligations; nothing syncs and the board says so |
| `/schedule` | ADM-SCH-01 Class schedule · week grid | **built from the canvas** |
| `/rota` | ADM-SCH-04 Coach availability · week grid | **built from the canvas** — the schedule board's own missing third view, over a read that did not exist |
| `/desk/*` (layout) | FD-08 Device strip | **built from the canvas** — always visible above the Front Desk surface, worst row first, and every degraded row names what to do instead; the canvas's own "type the name instead" is replaced because this product has no member search, and the receipt printer and card terminal it draws are not kinds of device this build registers |
| `/desk/trial` | FD-05 Walk-in trial | **built from the canvas** — two fields and a button that creates a person, opens a lead, signs an agreement on the trial product and activates it in one request; the duplicate panel is borrowed from ADM-MEM-10 because this screen creates a `ppl_persons` row exactly as that one does, the heading names the plan's own `trial_days`, and the credential and the app invitation the canvas promises are each named as absent with what they wait on |
| `/desk/denials/{id}` | FD-03 Access denial resolution | **built from the canvas** — the discreet line a password-only desk gets and the real reason once stepped up, which is the screen's own thesis; the door is named from the zone the refusal cites, the override offers the step-up rather than a button that would be refused, and the renewal, the day pass, the photo and the canvas's own club-and-plan header line are each named as absent with a reason |
| `/desk/classes/{id}` | FD-06 Class check-in | **built from the canvas, and the first Front Desk screen** — Touch density, the roster composed with MOD-014's batched names, the only working write form here that is not behind a step-up; the automatic release and the waitlist notification the canvas promises are named as absent |
| `/schedule/{id}` | ADM-SCH-02 Class detail and roster | **rebuilt** — the band, four MetricCells, the roster; the three actions are stepped-up writes with no form |
| `/payments` | ADM-PAY-01 Payments ledger | **built from the canvas** — four kinds on one axis, signed; refund and export are named as absent |
| `/payments/cash` | ADM-PAY-09 Cash reconciliation · shift close | **built from the canvas** — the expected figure before the count, over a read that did not exist; the co-sign and the tolerance are named as absent, the second being stricter here than drawn |
| `/finance/invoices/{id}` | ADM-PAY-03 Invoice detail | **built from the canvas** — lines, the life, the filing; no edit at any permission, which is the canvas's own rule and this schema's property |
| `/fleet` | ADM-ACC-01 Access control dashboard | **rebuilt** — the finding as the title, CLUB and TODAY columns |
| `/access/{id}` | ADM-ACC-02 Access denial log | **rebuilt** — the policy/fault split, counted by MOD-022's own codes |
| `/permissions` | ADM-STF-04, ADM-SET-08 | **rebuilt** — the capability matrix, roles across the top |
| `/login` | ADM-AUTH-01 Admin sign-in | **rebuilt** — the lockup, the note box; the tenant field is a stated deviation |
| `/step-up` | ADM-AUTH-02 Sensitive action re-auth | **rebuilt** — names the action from MOD-008's catalogue; a page rather than an overlay |
| `/people` | ADM-MEM-11 Merge duplicate members (partially) | partial — the duplicate queue only |
| `/organization` | ADM-SET-01, ADM-SET-02 | the hierarchy, with a figures line; the opening hours and floor capacity ADM-SET-02 draws have no read |
| `/access` | **none** | a zone list, which the design has no canvas for |
| `/catalog` | ADM-POS-01, ADM-POS-03 | partial, and the three absent columns are named on the screen |
| `/finance` | **none** | MOD-018's general ledger. It was counted as ADM-PAY-01 and is a different subject; `/payments` is that screen now |
| `/notifications` | ADM-COM-02, ADM-COM-04 | partial, and both absences are named on the screen |
| `/configuration`, `/privacy`, `/operations`, `/fleet/{id}`, `/integrations` | **none** | module surfaces with no design |
| `/account` | MBR-33 Security and devices (Member surface) | the registry leaves MBR-33 unspecified; built to this app's own conventions |

**Every one of these now carries a figures line rather than a paragraph**, which is the
design's own page-header rule and was the single most widespread deviation: fifteen screens
led with prose where every drawn canvas leads with counts.

What remains is the ~145 specified screens with no route at all — the Member app, Front Desk,
POS, Coach and Console surfaces, which are whole products rather than screens.

## Screens — 178 V1, of which 167 are specified

**The inventory is `web/src/design/screens.generated.json`**, one entry per V1 screen with its
registry identity, its roles, its Arabic state and every design section that specifies it,
pinned by SHA-256 and regenerated by `npm run design:screens`. That file is the inventory §6
of the directive asks for; this section is the implementation column.

| | |
| --- | --- |
| V1 screens in the registry | 178 |
| Specified in the design folder | **167** |
| `NO-UI` — the registry says no screen is needed | 8 |
| Genuinely unspecified (`ADM-POS-02`, `MBR-33`) | 2 |
| **Routes in `web/`** | **24** |
| Of those, built or rebuilt from their design | **12** |

So the remaining frontend work is **implementing specified screens**, not inventing around a
registry — which is the correction at the top of this file, and it is per screen rather than
per module. The nineteen existing routes that were composed from backend capability are each
either a screen in the registry that needs correcting or a module surface with no screen at
all; the table below says which.

Tracked in `contracts/ui/screen-contracts.yaml` by identity. Every screen is `—` until its
authoritative specification has been read and its implementation matches. The fifteen that
exist are listed here as `implemented, functionally tested` and **not** design-compliant:

| Screen | Route | State |
| --- | --- | --- |
| **Command Center (ADM-CC-01…05)** | `/` | implemented, functionally tested, **spec verified in part** — see below |
| Sign-in | `/login` | implemented, functionally tested |
| Step-up | `/step-up` | implemented, functionally tested |
| Account | `/account` | implemented, functionally tested. Now also the home of the session facts the old landing page printed, and of Sign out — §21 puts it in the account chrome. **Enrols and withdraws a passkey**, the first WebAuthn ceremony on any surface here: `navigator.credentials.create`, the SPKI public key the server verifies assertions against, and the withdrawal that had to exist before the button that creates one. Proven against a real Chromium virtual authenticator |
| Members (ADM-MEM-05) | `/members` | implemented, functionally tested, **spec verified in part** — 4 of 7 columns, the two-number footer, Compact density; the search, quick filters, saved views, bulk bar and export are named as blocked with the product's reason |
| Overview | `/` | implemented, functionally tested |
| Organization | `/organization` | implemented, functionally tested |
| People / duplicates | `/people` | implemented, functionally tested |
| Member 360 | `/people/{id}` | implemented, functionally tested |
| **Schedule board (ADM-SCH-01)** | `/schedule` | implemented, functionally tested, **spec verified in part** — see below |
| Session detail | `/schedule/{id}` | implemented, functionally tested |
| Configuration | `/configuration` | implemented, functionally tested |
| Catalog | `/catalog` | implemented, functionally tested |
| Finance | `/finance` | implemented, functionally tested |
| Privacy | `/privacy` | implemented, functionally tested |
| Messages | `/notifications` | implemented, functionally tested |
| Integrations | `/integrations` | implemented, functionally tested |
| Door board | `/access` | implemented, functionally tested |
| Zone detail | `/access/{id}` | implemented, functionally tested |
| Permissions | `/permissions` | implemented, functionally tested |
| Fleet | `/fleet` | implemented, functionally tested |
| Device detail | `/fleet/{id}` | implemented, functionally tested |
| Operations | `/operations` | implemented, functionally tested |

## ADM-CC-01…05 — the Command Center

**The owner directive names this screen by example**, and it was right: `/` rendered the
caller's identity uuid, their assurance level and a six-row table of gate answers — a
developer's view of the authorization layer, at the product's front door, where the design
puts the screen a club owner opens at 08:40.

The diagnostic was not deleted, it moved. The gate table is on `/permissions`, beside the
roles it disagrees with and the audit chain it is about — and it earns its place there,
because `simulate` answers from role assignments while the gate weighs assurance too, which
is MOD-014's "a grant is not a session" made visible. The session's identity, assurance,
factors and expiry were already on `/account`; the landing page was duplicating them.

| The design | Here | State |
| --- | --- | --- |
| Collected MTD, vs the same point last month, with a pace | `GET /finance/collections` | built |
| Active members, net this month, joined and left | `GET /memberships/summary` | built |
| Visits today, against the usual for this weekday | `GET /access/visits` | built |
| Lead conversion · 30d | — | **blocked**: no CRM module. `freshness: unavailable`, with the reason |
| MONEY · payments in recovery | `GET /finance/dunning-cases` | built |
| COMPLIANCE · invoices the tax authority rejected | `GET /finance/invoices?fiscal_status=rejected` | built |
| RETENTION · memberships expiring, with renewal value | the membership summary | built |
| STAFFING · classes with no coach, and the places held | `GET /scheduling/unstaffed` | built |
| LEADS · uncontacted leads | — | **blocked**: same module |
| The interpretation panel | — | **withheld**, with the true reason |
| Collections by week, the partial week marked | the collections read | built |
| Collections **by location** | by legal entity | **blocked**: the money chain carries no location |
| The queue's primary actions | — | **blocked**: each is a stepped-up financial write with no form |
| Period toggle, resolved-today drawer, keyboard queue, 30s undo | — | **blocked**: interactions; this surface renders on the server |
| Scope switcher | — | **blocked**: every `permit` call in this build is tenant-wide |

**Six new backend reads, each in the module that owns the answer and behind its own
permission.** Not one composed endpoint: paragraph 1300 bars a cross-domain join, not a
surface that asks each module its own question, which is the call ADM-MEM-05 already made.
They are aggregates rather than list reads because the lists are bounded at 200 rows, and a
client that summed one would report the first page as the month.

**Two new permissions, and one of them is a product boundary the design states.** ADM-CC-02:
"What Ziad does not see: group revenue, cross-location comparison, the JoFotara queue, and the
payment-recovery workflow itself" — and "the rail is generated from his role rather than
greyed". So `finance.revenue.read` separates a club manager from the portfolio by **grant**,
not by step-up: an owner opens this page every morning and a second factor every morning
means nobody looks. `finance.dunning.read` is the read half of a journey whose writes stay
financial.

**Three components, each filed in the design rather than invented.** `MetricCell` with
`DS-CL-01`'s `freshness: live | stale | unavailable`; `AttentionRow` to §38's contract — an
`article` labelled by its headline, severity as edge-mark *and* category *and* wording, the
amount at the logical end, actions stacking below bp.sm; and `AITreatment`, whose border is
`color.semantic.ai` because G7 and `DS-CL-02` put that hue outside `brand.accent`: "A tenant
brand on an AI panel would make inference look like a first-party assertion."

**The `unavailable` freshness is the variant this build needed most**, and the design could
not have anticipated why: there is no lead in this product, so the fourth metric renders prose
where a figure goes. A zero or an em-dash would both read as a measurement.

### What looking at the page found

Nine defects, none of which an assertion about a label would have caught:

1. **`heading()` chose the right key and the JSX threw it away.** A session that could see
   three of the four feeds read "Nothing needs you right now" above a paragraph saying the
   opposite. "Nothing needs you" is a statement about the club; a page that cannot see a
   category cannot make it.
2. **"1 payments are in recovery."** The catalogue had no plural forms at all. It has CLDR
   categories now, mirroring `backend/app/l10n/messages.py`, with a cross-runtime parity test
   — and Arabic's six categories are the reason it is not an `n === 1` check: "2 أمور" wants
   the dual.
3. **An empty "Needs you now" heading with nothing under it**, which reads as a panel that
   failed to load. Canvas 4 has no such block: the quiet day is a heading, a sentence and the
   figures.
4. **"0 places are held across them"** — a sentence with nothing in it. The empty case has its
   own body now.
5. **ISO dates on a 12-bar axis**, wrapping onto two lines in the narrowest column on the page.
6. **`+0 0 joined, 0 left`**, with no separator.
7. **The app had no sign-out.** It was on the old landing page and went with it. §21 puts it
   in the account chrome, which is where it is now. Found by trying to use the app.
8. **The RETENTION and COMPLIANCE rows were unreachable in the fixture**, so every assertion
   about them would have passed vacuously — the "a fixture carries both members of the pair"
   rule, for the fifth time. The fixture now seeds all four queue classes.
9. **A fiscalize call never inserted**, because a second `str.replace` consumed the first's
   anchor. The queue looked right and one row was missing.

### And two findings larger than this screen

**`/authz/checks`.** The shell asks the gate about thirteen navigation entries and this page
about six reads, so rendering `/` cost nineteen round trips — each a scope resolution and an
evaluation — against MOD-011's 600-a-minute per-identity budget. The browser suite tripped it
and roughly seven tests failed per run, a different seven each time, each passing in
isolation. The batch runs the same `authz.check` per action with the same scope and the same
assurance weighing; it is **not** a permission list, because a client deciding from
`effective_permissions` is MOD-014's finding.

**The harness was loading the heaviest page in the app before every test.** `adopt()` landed
on `/` for a historical reason, which was free while `/` was a session diagnostic and is not
now. It lands on `/account`. The limiter was never at fault: 600 a minute is eighty-five
Command Center loads, which no person reaches.

### Still open on this screen

- The queue summarises each class as **one row**, where the design shows one row per
  condition. Nine items on a busy morning is the design's scale; a row per failed payment
  would be a list, and "9 open · 2 critical" would stop meaning anything. Revisit when the
  queue has a resolution workflow (ADM-CC-06) to hang per-item state on.
- **No `resolved today` drawer, no lower-priority collapse, no period toggle**, and the
  keyboard contract (`↑↓`, `⏎`, `S`, the 30-second undo, the "3 new" pill) is unbuilt. All
  are interactions on a server-rendered surface.
- **`pace` uses a basis the design does not state.** It renders "pace to 63.1k" against
  41,280 at the 19th of a 31-day month; straight-line gives 67,348. The method implemented is
  straight-line and the response names it, rather than reverse-engineering one illustration.

## Money renders at the design's precision now, and that is two tables rather than one

`CURRENCY_MINOR_UNITS` is the ISO 4217 **storage** exponent -- a JOD amount is a count of
fils, a thousandth -- and it was being used as the **display** precision as well. So every
money figure on every screen in this product read `JOD 52.200` where the design reads
`JOD 52.20`.

The design system states it, and the folder settles it: **206 JOD figures are drawn across
the design documents and all 206 use two decimals; none uses three.**

> Always three-letter code plus two decimals, tabular figures, end-aligned. JOD is three
> decimals in banking and two in retail — Veyro is a retail product and shows two everywhere,
> including exports, so a reconciliation never has to guess which convention a column used.

So `CURRENCY_DISPLAY_DIGITS` is its own table, in both runtimes, and the cross-runtime parity
suite gained the rounding boundaries: the half that rounds up, the half that rounds down, the
carry that reaches the major part, the carry that crosses a thousands separator, and both
signs. Storage precision is what makes a proration exact and a journal balance; display
precision is what a receipt and a screen agree on, and collapsing them in either direction
loses one.

**Two properties are disclosed rather than discovered.** Rounding is half away from zero,
which is `money.round_half_up`'s rule and therefore the only rounding rule in the build --
MOD-016 shipped a second one and a reviewer found it disagreeing with the first on ordinary
inputs. And a stored amount finer than two decimals is reachable, because proration divides
and `allocate` splits by largest remainder: 999 fils shows as `JOD 1.00` and one fil shows as
`JOD 0.00`. A column of shown line amounts therefore need not sum to the shown total, which
is the ordinary property of any rounded display. **The minor units are the record; this is
the rendering.**

## ADM-PAY-09 — cash reconciliation

**`open_cash_session` and `close_cash_session` had no reader, and the sixth instance of that
shape is the reason this screen did not exist.** A drawer could be opened and the only way to
learn what was in it was to close it and read the refusal. `GET /ledger/cash-sessions` is the
read, and it returns the expected figure for an *open* drawer — which is the canvas's own
decision rather than an oversight:

> The expected figure is shown **before** the count is entered. Hiding it would be a fraud
> control; showing it is an accuracy control, and accuracy is the more common problem.

So the breakdown sits above the input: the float, what came in, what went out, and what should
therefore be in the drawer. The figure is that account's own balance, derived from its
postings with no number any caller sent — which is what makes it safe to show — and the three
lines add up to it by construction, which is what makes it checkable by the person holding the
notes rather than one they have to trust.

**The variance appears as the count is typed**, so the reason is a field somebody fills while
looking at the difference rather than a refusal they discover by pressing a button. The server
computes the difference itself; the arithmetic here only says what is about to be submitted.

Four things the canvas draws that this build does not have, each stated on the screen:

- **A co-sign.** The design has a second person counter-sign a short drawer. MOD-008 has
  approvals with thresholds and separation of duties, and which permission approves a till,
  above what figure, and who may not approve their own are product decisions nobody has made.
  A button that recorded no second person would be worse than its absence.
- **A tolerance**, and this is the unusual direction: the canvas gates the note on a JOD 2.00
  threshold and MOD-018 states in as many words that a tenant's tolerance is a commercial
  decision the sources do not name. So the floor applies and *every* difference needs a
  sentence — **stricter than the design, not looser**.
- **The person's name in the heading.** The canvas reads "Closing Layla's shift"; a legal name
  is an identity-class field, so a routine AAL-1 session — the level a front desk actually
  holds — reads it as withheld. "Closing ✱✱✱'s shift" is worse than the drawer's own label,
  which is the tenant's name for that till and is always true. The name appears for a reader
  who may see it, composed from `/staff` the way the staff list composes identity and person.
- **A shift, not a drawer.** The figures are the drawer account's own postings, so takings a
  previous shift never banked are still in the drawer and still counted.

Three things the build settled:

- **Two exponents, and conflating them is a 121.95 error.** JOD is *stored* in fils and
  *shown* with two decimals; a count typed as 135.50 is 135500 minor units, and reading it as
  13550 would post the difference to suspense as a shortfall of 121.95 — on the one screen
  whose entire job is the difference between two numbers. `parseAmount` scales between the two
  tables and never multiplies a float, and nine component tests pin it.
- **The decisions live apart from the read**, because `@/lib/api` reaches `next/headers` and a
  client component importing it fails the whole app's build. The account page records the same
  lesson from the first time, when its own version made the *login* page answer 500.
- **The close test provisions its own session.** A close is one-way — correctly, since a till
  somebody signed off and then re-opened is a till nobody can account for — so a test that
  closed the fixture's drawer would pass once and fail ever after. The fixture seeds a till the
  suite opens a session on; a 409 from an interrupted run is treated as that run's drawer to
  finish rather than as a failure.

## ADM-SCH-04 — coach availability

**The schedule board's own gap note said this screen's read did not exist, and it was right
about the whole build.** That note: "`Coaches` is in the gaps below: it is a grid of rota rows
rather than of sessions, and nothing here reads a resource's availability." `set_availability`
has existed since MOD-019 was built and nothing in the product could show what it wrote — so a
rota could be set and the only way to learn what it said was to publish a template against it
and read the refusal. The fifth instance of this build's "a writer with no reader" shape, and
`GET /scheduling/availability` closes it. `/rota` is now the board's third view chip.

Six decisions carry the screen:

- **The rota is the background and the bookings are drawn on top**, which is the canvas's own
  structure. A session the rota now refuses is **drawn and flagged**, never dropped and never
  silently honoured — the canvas argues it: *"Reducing availability never deletes a booking —
  it surfaces the conflict for a person to resolve, because the member on the other end has
  already been told a time."* So `bookedConflict` is a cell state of its own, and the refused
  bookings are listed beneath the grid as well, because a marked cell in a grid of ninety is
  something somebody has to find.
- **Every time is the resource's own zone, never a session's.** That is the defect MOD-019
  shipped and a reviewer found — `Window.timezone` was declared, written from the resource's
  own location and read by nothing, so a London coach rostered 09:00–17:00 was available for
  an 09:00 class in Amman. A grid of somebody's week is where that error would be least
  questioned, so the zone is named on the page.
- **Open hours are no figure where no rota binds, not zero.** A room, a court and a bike have
  no rota in any meaningful sense and on the day a gym opens nobody has one, so the page says
  "unconstrained" and draws no grid rather than seven columns of "not working" — which would
  read as a studio nothing can be booked into. The fixture carries both members of that pair,
  and the first attempt got it wrong: the test was pointed at the stand-in, which **has** a
  rota, because a substitution is refused unless the replacement's week covers the class — so
  the assertion ran against a page showing 112 open hours and the branch had never rendered.
  A third staff resource with nothing written against it is the member that was missing.
- **`WeekGrid` is the design system's own component for this shape**, and hand-rolling a
  second one was caught by the usage sweep, which is what that sweep is for. Its rule —
  *severity is an edge-mark and never a fill* — holds here rather than conflicting with this
  canvas: that rule is about a *class* cell, where a week with three tinted classes reads as a
  week three-quarters wrong. These cells are states of availability and the fill is the
  information the legend names; the one severity on the grid is a booking the rota refuses,
  and the canvas marks that with a border, which is the edge-mark the rule asks for.
- **A time-off reason is masked unless the caller could have written one.** It is the one
  window kind the schema requires a reason on, and it is prose about why a person is away —
  MOD-017's rule that a health fact is a health fact whatever column it is in, and the same
  prose `sch_session_changes.reason` is already masked for one table over. **The exception
  itself is never hidden**: a grid that dropped it would be the rota lying about who is
  working.
- **The grid is hourly and the hours are rounded**, which is the attendance chart's split —
  a chart is for scanning and a number is for acting on — and the screen says which it is.
  `formatInteger` throws for a fraction because this app has one number-rendering path and a
  cross-runtime parity test behind it, so the figure is whole hours; across a week that is
  immaterial and below one it is not, and the exact minutes are on the route.
- **The week starts on Sunday, because the canvas draws SUN–SAT** and dates its sample week
  to a Sunday, which is the working week in this product's own market. `Window.weekday` is
  0-Monday and that is a *storage* convention — the rota rows are keyed by weekday number
  whichever day the grid begins on, so only the order of the seven dates moved.
  `availability.week_from` carries the reason. This is not a declaration of which days anybody
  works: `GET /reports/attendance` still refuses to label a day set "weekdays", because
  nothing in this build records one.

**Verified against the canvas by photographing both and comparing**, at 1400px, light, English
— and the comparison found four things no assertion in four layers could see:

| What the canvas does | What the screen did | Now |
| --- | --- | --- |
| Available, unbooked is a pale block; bookings are the dark marks | the resting state used `--color-border-strong`, a *border* token as a fill, so a week with one booking rendered as a wall of solid blocks and read as fully booked | a quiet surface, on a card |
| Prints `PT`, `CLS` or `OFF` in a cell | colour was the only visible channel | `Booked` and `Off`, blank in the quiet states, both in the message catalogue |
| Columns run SUN–SAT | ran MON–SUN | `week_from` starts on Sunday |
| States the week in one sub-line, with no metric row | added four metric cells repeating open, booked and conflicts | removed; the sub-line is the figure |

Four declarations the canvas uses and this screen does not, each with a reason: the canvas's
**second** booked tone (`warm.700` for personal training, 26 cells) — this build cannot tell a
class from a personal-training session, so the two tones the design draws are one mark and the
gap note says so; the **"Add an exception" button's** edge, which is the form above; and two
container-edge alphas between the semantic token's steps, which would need a hard-coded alpha
the design system forbids a component to write.

**TestSprite found the one thing none of this could**, which is the argument for a layer that
has not read the repository: the page opened on the current week and had **no way to leave
it**. `here({ from })` was defined in the page and nothing called it, and every spec here
navigates straight to `?from=`, so not one of them could notice. The screen answers "when can
this coach work", and the question is almost always about a week that is not this one — the
canvas's own example is an exception agreed three weeks before the day it covers, which is
exactly the shape the fixture seeds and exactly what was unreachable. Previous / this / next
are links now, and the journey passes 10 of 10.

**And correcting the weights broke the screen the other way first, which is worth recording.**
With the fills fixed but the grid still drawn straight onto the page ground, "available,
unbooked" *was* the ground and every working hour of the week became invisible — the same
defect as the one before it with the sign reversed. The canvas draws the grid inside a white
panel, and the quiet fill is defined against that panel; `.ds-week-scroll` carries the card
now, which is what `.ds-matrix-scroll` already does for the other wide scrollable table.

**"Add an exception" is built, and it is the first write in this app that is not a member
acting on their own account.** The design draws the button, and every other form here is
absent because "a button that answered 403 is worse than its absence" — every `tenancy.*`,
`catalog.*` and `finance.*` write is a stepped-up financial permission.
`scheduling.availability.write` is **not**: it is `configuration` with no financial class, and
the catalogue says exactly why — *"A rota is edited by the people who run the floor, and
refusing them a step-up every time somebody books a day off would make the rota wrong
instead."*

**What it needed first was the remedy, and that is the finding.**
`sch_availability_windows` carried `GRANT SELECT, INSERT` and nothing else, so a day off
entered on the wrong date, a shift typed as 06:00 instead of 16:00 or an absence written
against the wrong coach had no remedy anywhere in the product — a rota could only ever grow.
Invisible while the only writer was a seed script; decisive the moment somebody can press a
button, because a routine permission whose every act is uncorrectable is MOD-013's "an
irreversible act must not be declarable on a routine permission" from the other side.
`0017` adds a withdrawal — **not a delete**, because "was this coach marked off on the
fourteenth, and who said so" is asked precisely when somebody was turned away — with its
attribution constraint, a one-way trigger, and ten mutations against the pair.

It also **revoked** `UPDATE (starts_at, ends_at, reason)`, which `0013` granted to both
runtime roles and no service ever wrote: an unattributed retime of the three values the table
exists to state, with no column anywhere to record that they moved. MOD-016's
`cat_prices.effective_to` for the second time in this build.

Three smaller things the form settled:

- **No required marks.** The Field shell's rule is "required is marked, optional is not —
  whichever is rarer gets the mark", written against exactly this case. Every field here is
  required, so four asterisks would be four marks carrying no information — and they were in
  the accessible name, where a screen reader read "Day star".
- **A browser's native validation is not the server's control.** Every field is `required`,
  so an empty submit never reaches the server, which is right for a reader and proves
  nothing. The test that exercises the server's own check turns native validation off and
  submits as a client which is not a browser would.
- **A test that writes to a table with no delete puts the rota back.** A rota has no delete,
  so a spec that only added would leave one more absence on every run and the second run
  would assert against a different week — this repository's own rule about a suite that
  spends something the product keeps. It writes on a date no other spec looks at, proves the
  grid moved, withdraws it, and proves the grid moved back.

**ADM-SCH-06 (Rooms and resources) is not built, and two of its three columns are why.** The
canvas draws name, capacity and equipment, and says *"Capacity here is the ceiling every class
inherits."* `sch_resources` has `quantity` — how many of a thing there are — and capacity in
MOD-019 lives on a template's own `sch_capacity_policies`, per class. There is no equipment
column at all. So the screen as drawn would have one real column and two invented ones, and
rendering `quantity` under a heading reading "Capacity" would be the confident wrong answer in
the place a scheduler sets a class size. `GET /scheduling/resources` exists, so the screen is
blocked on the data rather than on a read.

## ADM-SCH-01 — the week grid

**It was a list and the design specifies a grid**, which this file carried as a fidelity gap
from the day the design folder was read properly. The canvas is `CANVAS 1 · SCHEDULING ·
KHALDA · WEEK OF 18 AUGUST`, and it names its own components:

> AdminShell · WeekGrid(7×4, horizontal scroll below bp.lg) · ClassCell ×13 (1 unstaffed,
> 1 full, 1 low-fill) · AttentionRow(condensed, footer-anchored) · Compact density ·
> **severity on the cell edge-mark only, never the cell fill**

A list and a grid answer different questions. "What is on at six o'clock on Thursday" is a
scan down a column in one and a search through forty rows in the other, and the design's own
heading — "The week, with one problem in it" — is a sentence only a grid can earn.

| The design | Here |
| --- | --- |
| Seven day columns, a row per local start time | built |
| "54 classes · 1 without a coach · 78% average fill" | built, all three exact |
| ClassCell: name · coach · fill | built — the calendar read now returns the live staff assignment |
| Severity on the cell edge-mark, never the fill | built, and asserted by measuring both |
| AttentionRow, condensed, footer-anchored | built |
| Week · Day | built — the same read over different spans |
| **Coaches** | **blocked**: a grid of rota rows rather than of sessions, and nothing reads a resource's availability |
| **Add a class** | **blocked**: a stepped-up permission with no form, like every other write in this app |

**The coach needed a backend change.** `schedule_for` returned no resources, so a grid would
have had to fetch one session read per cell — a week of classes as a week of requests. It
aggregates the live staff assignment now, and `superseded_at IS NULL` is what "has a coach"
means: a substitution supersedes the outgoing row and leaves it, so counting rows would show
a class whose coach went home ill as staffed.

**Two sanctioned horizontal scrolls now exist in this product and no others.** The design
names this one — seven columns of classes do not collapse the way a table's low-priority
columns do, because a Tuesday is not a lower-priority Monday — and the Command Center's metric
row is the other. Everywhere else a sideways-scrolling data region is the defect `DataGrid`'s
column priority exists to remove.

**Looking at it found two defects**, both already recorded elsewhere in this file as shapes:
the grid was captioned twice (a hidden caption *and* a hidden time-column header, both
carrying the page's title, so it announced "Schedule, Schedule" — the contract `DataGrid`
learned when eight grids gained it at once), and "0 places are held, so somebody is expecting
a class" is a sentence that contradicts itself, which is the Command Center's staffing body
one screen over.

## Unresolved design requirements

Recorded rather than invented, per §7 of the directive. Nothing here is a licence to improvise;
each is a question for the design source or its author.

| Requirement | Where | Why it is unresolved |
| --- | --- | --- |
| `color.action.pressed` has no dark value | `ds.json` `DARK_GAPS` | The source names `accent.pressed` on that token and gives it no value in the ramps, the semantic table or the dark-mode note. |
| `color.surface.raised` is a composite | Foundations | `warm.0 + e1` — a primitive plus an elevation, which the generator reports rather than resolving to a hex. |
| Icon manifest | §59, `CROSS` → RTL layout | "Mirroring is per-element, from the icon manifest." No icon manifest is present in the design folder. |
| Per-family state matrix beyond the 17 rows | §69 | The matrix names 17 rows for 37 families; several families are grouped (`Select · Combobox`, `Modal · Drawer · Sheet`). Grouped rows are applied to each member. |
| Screen-level layout detail | `V1 Batch *` | The batch files specify each screen in prose (pattern, intent, content rules) rather than measured layout. Compliance is against the stated pattern and its component contracts. |
| Density "type step" across registers | `DENSITY`, `TYPE_SCALE` | The scale is not one ladder — headings, body, label, caption, data and eyebrow are separate registers — so "+1 step" has exactly one unambiguous reading, the body ramp. Spacious is "+2 steps" and that ramp has one step above `type.body`; the scale's own usage note assigns `type.bodyLg` to "Member app body, coach prose", which is the surface LAYOUTS puts at Spacious, so the generator clamps to the top of the ramp. **An interpretation, not a value read off the page.** |

## The screen-by-screen pass — what looking at the pages found

The audit above was a reconciliation of the registry against the routes. This section is the
second half the directive asks for: **every screen opened in a browser at 1400×900 and
compared against its canvas**, which is the only thing that finds a rendering defect. It
found eleven, and nine of them were invisible to every test in the repository.

### Four screens had every fact and none of the anatomy

ADM-MEM-01 names its own components — `Member360Header · PersonRow ×6 · AttentionRow(inline)
· MetricCell ×5 · TimelineItem ×7 · MembershipCard · AccessPass · MoneyValue · Tabs` — and
what the page rendered was an `<h1>` and nine stacked `<dl>` blocks. ADM-SCH-02 wants a band,
four cells and a roster. ADM-ACC-02 wants the denial log split by policy and by fault, and
argues for the split: *"Twenty-seven expired memberships is the system working. Four reader
failures is a maintenance job. Mixing them in one count hides the second inside the first."*
ADM-STF-04 wants a matrix and got 4,300 pixels of comma-separated permission names.

Five backend reads existed nowhere and the screens needed them:

| Read | For | Why it is on this side of the line |
| --- | --- | --- |
| `GET /access/attendance` | ADM-MEM-01's LAST VISIT | Entries, not decisions: a failing card produces refused decisions for exactly the member somebody is checking. The rate is measured to the last visit, not to today, or every lapsed member reads as one who never came much. |
| `GET /access/credentials` | ADM-MEM-01's Access block | No digest: the stored value is a SHA-256 and is pseudonymous, so a listing carrying it would let anybody with a candidate card confirm whose it is. Asserted as an absence, mutation-proven. |
| `GET /access/entries` | ADM-ACC-01's TODAY column | MOD-021 knows nothing about doors by design, and `acc_points` is the join it deliberately did not make — so the board composes the two rather than MOD-021 learning to count entries. |
| `GET /authz/catalog` | ADM-STF-04's row headings | A statement about the software, like `/privacy/erasure-reach`: no pool, no tenant rows, identical bytes per tenant. |
| `GET /finance/payments` | **ADM-PAY-01, which had no screen at all** | See below. |

### ADM-PAY-01 existed nowhere and `/finance` was being counted as it

The payments ledger is the one Admin money screen with a drawn canvas and no implementation.
`/finance` is MOD-018's general ledger — the chart, the period lock, the trial balance — which
is what an accountant closes a month with; the payments ledger is what a manager opens every
morning. The ledger read unions four tables because the canvas's rule demands it: *"Refunds
carry a negative sign and the parenthetical original. A refund is never shown as a payment of
a different colour — it is a different sign on the same axis."* A failed charge is a row
rather than an absence, because a ledger of successes cannot be reconciled.

What it does not do is named on the screen: a refund is tier 3 **and** tier 4 in the design's
own scale — a typed amount and a second person — and `finance.refund.request` is a stepped-up
financial permission with no form in this build.

### Eleven defects, and what each one teaches

- **A gate naming a permission that does not exist renders as a refusal.** The Member 360's
  metric row asked for `finance.invoice.read`, which has never existed, and the OUTSTANDING
  cell told the tenant's owner they lacked a permission. `/authz/checks` refuses an undeclared
  action with a 422 now, and `tests/unit/permission-names.test.mjs` sweeps every `gate(…)` in
  the app against the catalogue. Mutation-proven: a structural check that passes vacuously is
  the thing it exists to prevent.
- **A TypeScript type is a claim about a response, not a check on it.** Two newly-added fields
  read as `undefined` against a server that predated them; `undefined / 100` is `NaN`, which
  `formatInteger` refuses, so one missing field answered 500 for a whole page.
- **The projection's gaps contradicted the tabs beside them.** MOD-014 says "MOD-017 owns this
  and nothing here reads it", which is true of the projection and false of the page: that line
  sat under a Membership tab full of memberships. The same stale-list defect this screen had
  already paid for, in the other direction.
- **One `Promise.all` over three reads loses all three.** The permission catalogue being
  unavailable took the roles and the session's own permissions down with it.
- **A metric row with a fixed four columns renders a fifth cell as a broken one.** ADM-CC-01
  draws four and ADM-MEM-01 draws five.
- **An avatar on a record that is not a person reads as a photograph that failed to load.**
  The circle is opt-in now.
- **A bulleted list of nineteen "level 2 · 17:11" rows is not something anybody can act on.**
  Revoking a session is destructive and the device is what tells two apart — and it was on
  every row of the response, dropped by the rendering.
- **"The rows the roles differ on" reduced nothing.** With one role holding everything, every
  permission differs from the roles that hold almost none. The rows had to be coarser, not
  fewer: a module summary with a third mark for "some of it".
- **A message catalogue can hold a translation nothing can select.** English has two CLDR
  categories, so a `zero:` form in the English catalogue is dead on arrival; three had one.
  And `payments.next.payment` was a key for a row that can never need action — the parity
  check caught it, because the em-dash was identical in both locales.
- **A test whose green depends on spec order.** `operations.spec` asserted zero pending
  events, which was true right after the fixture and false once `access.spec` had recorded a
  decision before it. It drains the outbox itself now: a test that asserts a freshness has to
  create it.
- **A column name taken from a module's prose rather than from its schema.**
  `rotating_window_seconds` does not exist on `acc_credentials`; `ruff` and `mypy` are both
  blind to a column name inside a SQL string, and the only thing that could catch it is a test
  that runs the query. Nothing did, and the page said "this figure could not be read".

### What the fixture had to grow

Three times, a screen could not demonstrate its own distinction because the fixture had one of
something: a payments ledger with one settled payment cannot show that a refund is a negative
number on the same axis, and a fleet board where no device is a door cannot show that "not a
door" is different from zero. The fixture now seeds a failed charge, a refund approved by a
second identity, and a dispute — **the rule this repository already records five times over:
the fixture carries both members of the pair the distinction is about.**


### What a screen cannot do is on the screen

Four boards now carry a "what this screen does not do yet" block, which the members list
established and the directive asks for in as many words: *record precise missing information
rather than inventing*. Each entry names the design's own requirement and the product reason
it is unmet, so a reader comparing a page with its canvas can tell a screen's gap from a
module's.

| Screen | Named | Why |
| --- | --- | --- |
| `/members` | search, quick filters, three columns, saved views, bulk actions, export | ENG-01's index, cross-module filters, and reads that do not exist |
| `/payments` | the refund, the export, by location | tier 3 *and* tier 4 with no form; an object store; a billing account has no location |
| `/catalog` | per-club stock, a tax figure, discount thresholds | MOD-016 is the catalogue and the price — no inventory, no rate, no tenant-wide threshold |
| `/notifications` | the per-event channel matrix, the language pair | MOD-013's preferences are per recipient; a template version is keyed on locale and enforces no pairing |

The Member 360 does the same thing from the other side: its foot names the areas MOD-014's
projection cannot read **and** says which of them this page answers itself on its own tabs,
because a gaps list that contradicts the tab beside it is the stale-list defect this screen
already paid for once.


### A read with no reader is the same gap as a writer with no reader

`GET /finance/invoices/{id}/history` was built with a docstring naming ADM-PAY-03 by id and
saying what it is for — *"ADM-PAY-03's middle section"* — and nothing had ever rendered it.
MOD-017's own record names the opposite shape (a module whose state cannot be observed is a
module nobody can check) and this is its mirror: **a read nobody renders is a read nobody
sized**, and every invoice in this product was a figure with no way in.

The screen is now `/finance/invoices/{id}`, linked from the member's billing tab. Four
defects came out of building it, every one found by opening the page:

- the heading printed twice, because the panel and the `Timeline` both carried it;
- a date-only instant rendered an empty clock above its day — `issued_on` is a `date`
  column, so there is no time of day, and `TimelineItem` now lets the day take the clock's
  place;
- `MoneyValue(aggregate)` split the decimals on a total sitting in a list of plain figures,
  so the sum read as a different kind of number from its parts;
- a permission name printed with its backticks.

And one place where two canvases disagree and both are right: ADM-PAY-03's state note is
*"Paid — status badge in success"* while ADM-MEM-01's is *"No green badges"*. The difference
is the subject. A member's record sits among records, where a green badge dilutes the overdue
one; an invoice's own state is what its screen is about and there is no row beside it. The
`success` tone exists, is documented as almost always wrong, and is used on exactly one
screen.

## The canvases render, so the comparison is mechanical — `web/tests/visual/visual.mjs`

The audit above compared routes against the registry and the screen-by-screen pass compared
pages against canvases by reading them. Neither is a measurement. The canvases in
`veyro-product-experience-design/project/` are **not flat mockups**: `support.js` is a design
runtime that resolves every `{{ }}` placeholder and `sc-for` loop against React 18 from
unpkg, so a canvas can be rendered in a real browser and a screen can be put beside its own
approved drawing.

The harness does two things and keeps them apart:

1. **It renders both sides and writes them out**, so somebody looks. Every rendering defect
   ever found in this surface was found by looking — a schedule board three hours wrong under
   a heading naming the right timezone, seven screens scrolling sideways at phone width, a
   metric value wrapping over two lines in Arabic. Four layers of green assertions saw none.
2. **It extracts a computed style inventory from each side and diffs the sets.** No
   element-to-element mapping is needed, and it catches the class a screenshot comparison
   argues about: a weight, a size, a leading, a colour, a radius, a border.

### It classifies rather than lists, and that is the whole difficulty

**A raw diff produces findings whose correction would undo the design system.** The canvases
are a sequence and the later ones correct the earlier ones. Two live cases, both from
ADM-CC-01:

| The canvas draws | The token tables say | Who is right |
| --- | --- | --- |
| page title at `500 24px/28.32px` | `type.h1` is "26 / 1.15 — Page title. One per screen." | the table; the app renders 26 |
| 27 small-text elements in `#85807a` | `warm.500` — "FAIL under 18.66px on every surface. Large text, disabled controls and decoration only." | the table; matching it ships a measured AA failure |
| body prose at weight `450` | `TYPE_SCALE` defines 400 and 500 | the table |

The design system says this about its own history, in VALIDATE-1: the first specimens used
light greys for member IDs, branch names and timestamps measuring 2.34:1 to 4.12:1, and *"had
they been adopted as drawn they would have propagated into every surface in the product —
precisely the retrofit-after-hi-fi failure that VALIDATE-1 exists to prevent."*

So an unmatched declaration is a **deviation** only when the token tables sanction it;
otherwise it is reported as **prototype drift** or as a pairing the **contrast matrix bars**.
Both stay visible and neither is silently dropped. Thirty-nine raw differences on ADM-CC-01
became sixteen worth reading.

A type declaration is matched as a whole step — weight, size and leading ratio together.
Matching on size alone calls an 11px glyph set at 11/11 the same thing as `type.caption` at
11/1.40, which is how a prototype's incidental line-height gets reported as a specification.

### What it found on ADM-CC-01, and what was fixed

- **The queue has two row heights and this had one.** The canvas's own component list is
  `AttentionRow ×5 (2 full, 2 condensed, 1 collapsed group)`. A condensed row is one line —
  chip, headline, owner, one action — and it is what the queue uses for an item that needs
  somebody but needs no explaining. The evidence sentence stays as the row's accessible
  description rather than vanishing.
- **Staffing escalated to `critical` and the canvas draws it `info`** — with eighteen members
  booked. The severity is about what the item *is*, not how many it touches. `info` existed
  in the scale and nothing used it.
- **A UUID is not a label.** The collections breakdown printed `legal_entity_id`, so the one
  figure naming a part of the business named it with 36 hex characters. Resolved through
  `tenancy.organization.read` where the reader holds it, the id shown where they do not —
  the same four lines `/finance` already uses.

**Still open on this screen**, and named rather than approximated: the collapsed group row
(*"Show 4 lower-priority items · inventory, document expiry, two coach notes"*), the resolved
drawer, the global search entry and Tasks/Alerts in the chrome, and the twelve-week
collections chart, which renders as a list of twelve rows rather than as bars.

## ADM-RPT-01 … 05 — reports

Built: the index and three reports. The reads behind the revenue and attendance reports were
both new.

- **ADM-RPT-01 · index** — `/reports`. Gated per entry, which is the canvas's own point: *"A
  Club Manager opening this screen sees four reports, not six. The two financial ones are
  absent — not listed and locked."* **An absent module is a different absence from a refused
  permission**, so Coaching, Leads and Tax are named with the module each needs rather than
  quietly missing — otherwise they read as three more grants to go and ask for, which is
  false. Attendance was in that list until it was built, and the component test that used to
  assert a count of four now asserts the property instead: every one of the canvas's six
  reports is either offered or explained. A hard-coded count went stale the hour the report
  landed.
- **ADM-RPT-02 · revenue** — `/reports/revenue`, over a new `GET /reports/revenue`. Four
  figures because the canvas argues for four: *"Collected and invoiced are separate columns
  because they are separate facts. A report showing one number labelled 'revenue' is the
  reason operators cannot reconcile their own books."*
- **ADM-RPT-03 · membership** — `/reports/membership`. Joins, leaves and net.
- **ADM-RPT-04 · attendance** — `/reports/attendance`, over a new `GET /reports/attendance`
  and a new pure module, `app/access/attendance.py`. A bar per local hour at one club, three
  heat tiers, and the conclusion written underneath in words — which is the canvas's own
  requirement rather than a styling note: *"The conclusion is written in words beneath the
  chart. A manager should not have to interpret a heat strip to find the actionable hour."*

Six decisions worth carrying:

- **BY SOURCE is COM-02-R01's own vocabulary, not a taxonomy invented here.** An invoice line
  carries a `variant_id`, a variant belongs to a product and a product has one of eight
  declared types — so the split is a join. A line with no variant is its own row rather than
  dropped or guessed at, which is what makes the sources add up. Classifying free-text
  descriptions would be MOD-016's "a control decided by matching words in prose" on a revenue
  report.
- **Outstanding carries no comparison and says why.** The other three are flows; outstanding
  is a position — what this month's invoices owe *now*. The comparable figure is a balance as
  it stood a month ago, which this read does not reconstruct.
- **ADM-RPT-03's churn chart is refused, twice over.** `mem_lifecycle_changes.reason` is free
  prose, not a coded reason, so the five named bars would mean classifying what somebody
  typed. And the prose is not shown either: MOD-017's own review rule is *"a health fact is a
  health fact whatever column it is in"* — a freeze's reason is masked for exactly that, and
  `membership.record.read` is routine and tenant-wide.

- **ADM-RPT-04 refuses the canvas's percentage of capacity, and says which claim it
  refuses.** The canvas writes *"18:00–20:00 runs at 94% of floor capacity"*, and a capacity
  figure does exist — `acc_policies.capacity`, the number a presentation is refused against.
  It is not this chart's denominator, for two independent reasons either of which would be
  enough. Entries in an hour are **arrivals, not people inside at a moment**: a hundred
  arrivals is a floor holding a hundred if everybody stays an hour and fifty if everybody
  stays half of one. And occupancy derived from access events is **advisory** unless a zone
  reads both directions — paragraph 4180 and `occupancy.confidence` behind it — so the honest
  version of the comparison is unavailable at exactly the single-turnstile clubs most tenants
  have. Nothing is lost from the canvas's reading, because every figure it draws is already
  relative: the bars are heights against the busiest hour and the three tones are tiers of the
  same ratio. The screen says so where a reader might otherwise take a share for a capacity.
  The canvas's second sentence — *"two more classes at 07:00 would move perhaps 30 people"* —
  is a recommendation with a headcount in it, and nothing here models what a new class would
  draw; the hour is named, which is the half the data supports.
- **"WEEKDAYS" is the reader's choice, because nothing in this build knows which days those
  are.** A working week is Sunday to Thursday in the market this product is built for and
  Monday to Friday in the one its design language comes from, and no table, constant or
  MOD-005 key declares either. So the route **refuses to default the set at all** — MOD-009's
  DSAR deadline and MOD-015's tax rate are the precedent — and the chips name *which days*,
  which is a fact, rather than what they mean to a business, which is not. A chip reading
  "Weekdays" would have been the surface inventing a market convention and presenting it as
  the product's own.
- **Class fill and capacity planning are named, not drawn.** The registry line for this screen
  is "peak hours, class fill, capacity planning" and the canvas draws the first of the three.
  A second chart this design does not have would be as much a deviation as a missing one, so
  the two absences are stated — with the place average fill already exists, which is the
  schedule board.
- **The scope line is the shell's, not the canvas's eyebrow.** The canvas is a card excerpt
  with no page header, so its single mono line — *"VISITS BY HOUR · KHALDA · WEEKDAYS"* — is
  both its title and its scope. On a page inside this app the title is "Attendance" and the
  scope sits in the sub-line beneath it with the filter chips, which is what the schedule
  board does (`{club} · {dates} · {timezone}`). Consistency with the shell beats transcribing
  a card, and the timezone is on that line because every hour on the page is that club's
  clock and no other screen may assume a reader knows which.
- **The chips are this app's convention, and the canvas has none.** A read-only report of one
  club on all days would make the canvas's own scope line meaningless, and every other board
  here filters with links rather than controls so a view survives being sent to somebody.
  Three rows at most: the clubs (plain links, as the schedule board does), the day range and
  the readers.
- **A plain denial names the permission; the other three gate verdicts do not.** Both sibling
  reports say *"This report needs <permission>"*, which is the sentence a reader can act on,
  and `gateMessage` cannot say it — its whole job is keeping a transport failure, an
  unreachable assurance level and a step-up apart from a denial. So the denial gets the
  report's own sentence and the other three keep theirs. Found by a browser test asserting
  the permission was named and getting the generic line.
- **A retired zone stays in the reader list, marked.** `retire_zone` says in as many words
  that "the decisions and events recorded here stay", so a club that closed a studio still
  has its entries in the histogram — and a reader list filtered to live zones left those
  entries in the chart and in no row beneath it, which is a total a reader cannot reconcile
  against the breakdown. MOD-018's trial balance makes the same choice for a retired account
  and for the same reason. **The browser fixture has no retired zone**, so the rendering of
  that marker is covered by a component assertion on the message and by two HTTP tests on
  the server rather than by a rendered page: seeding one needs a fourth activated turnstile,
  and the three e2e specs that count this fixture's devices and its attention queue would
  move for a chip suffix. Stated rather than left to be discovered.

**ADM-RPT-05, the export gate, is not built and the screen says why.** The canvas puts a
tier-4 gate in front of every export of personal or financial data: a written reason recorded
and visible to the tenant, an option to leave contact details out, and step-up before the file
is produced. Nothing here exports anything, so the gate has nothing to stand in front of — and
a button producing a file without that record would be the control removed rather than the
feature added.

**And building it found the phone sweep's two CSS mutations had gone stale.** Running them
returned 0/2 caught, and nothing was broken: both name rules that are still correct and had
stopped being provable, because two earlier fixes made them redundant on every page that
exists. `table { display: block }` is now reachable only on the four hand-rolled tables in
`membership-panels.tsx` — a grid takes `display: block` from the 599px collapse rule and the
matrix is exempt — and **those two tabs were not swept at phone width at all**, which is the
coverage gap the stale mutation was hiding. `.facts dd { overflow-wrap: anywhere }` was
unprovable for that reason plus `contain: layout`, which stops an overflowing descendant
reaching the root before the document can see it. The collapse is directly measurable, so it
is measured now: a grid's table and cells compute `block` (or `none` for a dropped column, the
other half of the collapse) and the matrix computes `table`. Four mutations are caught where
two were not, and the detail is in the rules file.

### What building them found elsewhere

- **The billing tab rendered every money figure as a plain string.** §39 is explicit — *"never
  a bare number in a money column"* — and the kind is what carries the meaning: `owed` sets
  the outstanding figure in the critical ink, `aggregate` de-emphasises the minor units so a
  column aligns on the major, `notApplicable` renders the em-dash for a member with no
  account rather than a zero that reads as "nothing owed". Found by a test looking for
  `.ds-money` on that tab and finding none.
- **`DataGrid` rendered a bare numeral under every grid in the app.** §25: *"the count always
  states what is selected."* "2" under a table is a stray character to a reader who has not
  been told what it counts. The component now takes the phrase; **33 call sites still pass
  none and fall back to the number**, which is this ledger's open item rather than a default
  worth keeping.
- **`Prose` is a fragment of inline spans**, so four of them at the top level of a page became
  one paragraph: *"...add up to the invoiced total.The design breaks this down by club."*
  `ProseNote` is the block form, so the next page cannot make the same mistake.
- **Two e2e tests asserted the seed rather than the product.** Adding one invoice to the
  fixture broke a trial-balance figure and an outstanding figure while both pages were right.
  `finance.spec.ts` already carried that lesson in its own comment about totals and had left
  three amounts beside it pinned. Both are relationships now — revenue exceeds clearing
  because revenue is earned at issue and clearing moves only on payment — with the exact
  postings proved against a real database on the backend.

## TestSprite — the independent layer, and what it found

The CLI is installed and authenticated against the owner's own workspace (Starter, 400
credits a month, local tunnel available), and this repository already carries one run under
`qa/testsprite/` from 2026-10-15. `qa/testsprite/plans.mjs` generates four journeys from the
live fixture and creates them; `testsprite test run <id> --local 3000` opens a tunnel for a
run and points the cloud runner at this machine's loopback.

**The value is that it has not read this repository.** A Playwright spec and the page it
tests were written by the same hand on the same day, against the same assumptions; these
plans are English sentences about what a person would do, and the agent executing them has
never seen a selector, a fixture or an argument from this codebase. It does not replace the
browser suite, the component tests or the visual comparison — a TestSprite pass says a
journey works, not that a screen matches its canvas.

| Journey | Result |
| --- | --- |
| Signing in reaches the Command Center, not a session diagnostic | passed 6/6 |
| A report this session cannot open is absent, not locked | passed |
| The revenue report separates collected from invoiced | passed 8/8 |
| A withheld field is marked, never blank | found a defect (below), then passed |

**The finding, and it is a good one.** The fourth plan asserted that the member's own name
was readable. It is not — an identity field needs a stepped-up session and a name is one, so
every row of `/members` reads "Name withheld". The plan was wrong about the product. What
the tester did next is the finding: **it clicked the withheld marker looking for a way
through, and on the list there was none.** The step-up that lifts the mask was offered on a
member's *record* only, so a reader of the list saw a withheld name against every member with
nothing on the page to act on. The offer is on the list now, pointing back at the list.

The other failure was mine: a run was in flight while the production bundle was being
rebuilt under it. Re-run clean, it passes.

**Two bounds worth stating.** A frontend run reaches this machine through a tunnel and signs
in with the fixture's synthetic credentials — `admin@veyro.invalid`, a constant in
`fixture.mjs`, for a throwaway local tenant. And a test created from a plan carries that
tenant's id for ever, because a plan is static text on TestSprite's side: **re-running the
fixture invalidates every test already created**, which then fails at a sign-in form for a
tenant that no longer exists and looks exactly like a product defect. Regenerate and create
again after any fixture run.

## ADM-PAY-07 — wallet and credits

Built onto the member's billing tab, over a new `GET /ledger/wallets/{id}/statements`.

**The read beside it takes a currency and a member's record does not have one.** A wallet is
one row per (person, currency); a till settling a sale knows which currency it is in, and a
screen does not. A page that guessed — the tenant's first billing account, say — would show
one wallet and silently omit the rest, and a member holding value in a currency it did not
ask about would be told they hold nothing. A person with no wallet gets an empty list rather
than a 404, because this read is asked what somebody *holds* and "nothing" is a true answer.

**Four balances, not the canvas's one.** Paragraph 1686, which MOD-018 calls a Critical
Control: a member holding cash they paid in and value the tenant gave away holds two
different things, and only the first is money the tenant owes. The total leads and the kinds
sit under it; summing them would erase the distinction that decides whether a refund is even
possible.

**A credit's kind is where it came from; a debit's is which pocket it came out of**, and the
same word cannot do both. The first version captioned a spend "Given away" — the balance
label — so "Water and a protein bar · Given away" read as though the gym had given away a
protein bar. A spend now says which pocket it was taken from, which is worth saying, because
`plan_debit` chooses that pocket in the member's interest: promotional first, since it
expires and is worth nothing lapsed. Found by reading the rendered statement.

Not built, and the screen says so: Top up and Add credit are both writes behind a stepped-up
financial permission with no form in this build.


## Arabic: three kinds of English on an Arabic page

Switching the language and looking at `/members` found three, and they are three different
mistakes rather than one repeated:

- **A stored value rendered as a label.** `lifecycle_state` printed `lead` in Latin letters
  on the filter chips and in every row; `membership_kind`, `billing_period` and `status`
  printed `recurring`, `monthly` and `active` in the next column. `stateName` and `planName`
  map them, and an unknown value falls through to its stored form rather than to "other" —
  this is the screen that *filters* by it, so hiding which one it is would be worse than an
  untranslated word.
- **English prose in a library.** `members.UNANSWERABLE` held six English sentences and the
  page rendered them straight, so the Arabic build carried six English paragraphs under
  Arabic headings. The Command Center's own `UNANSWERABLE` was already message keys; the
  members module was the odd one out, and is now consistent with it.
- **A server disclosure rendered verbatim.** `search_is_not_available_because` is the
  backend's own sentence about what it cannot do. It is the authority for *what* the gap is
  and it is English by construction, so the reader gets the catalogue's version of the same
  statement and the server's stays in the data.

**None of these is visible to the catalogue parity check**, which compares the two catalogues
against each other and is structurally blind to a string that never became a key. That is the
rule this ledger already recorded for MOD-013's decision reasons, recurring twice in one page.
The durable answer is the one that rule names: a test per module asserting that every key
*that module maps to* exists in both catalogues — `tests/component/members.test.ts` has it
for `stateName`, `planName` and `UNANSWERABLE` now.

**And the members list had no way through its own mask.** Every name reads "Name withheld" at
AAL 1, and the step-up that lifts it was offered on a member's record only — so a reader of
the list had a withheld name against every member and nothing on the page to act on. Found by
TestSprite, which clicked the marker looking for one.


## Round 2, and the defect only CI could find

The directive asks for two complete verification rounds, the second from a clean build. Round
2: `.next` removed, a fresh fixture, a fresh production bundle, then every layer again — 334
browser tests, 95 backend access and structural tests, `npm run verify`, and the four
TestSprite journeys re-created against the new tenant and re-run through a tunnel.

**Between the rounds, CI failed on something no local run had hit.** ADM-CC-01's third metric
is "VISITS TODAY", and its read filtered on each club's *local* date while comparing it
against `datetime.now(UTC).date()`. The two frames agree for most of the day. In the hours
after a club's local date has turned over — 23:17 UTC at a UTC+3 club — the day's count read
zero, **the location dropped out of the response altogether**, and the member record's LAST
VISIT cell was fed `days_since: -1`.

Both reads' own docstrings already stated the rule they broke. The regression test uses two
clubs, `Pacific/Kiritimati` (UTC+14) and `Etc/GMT+12` (UTC−12), whose windows of disagreement
with UTC cover the clock between them — a single zone would make the test as flaky as the bug.
Mutation-proven.

It is worth naming what caught it: not the visual comparison, not TestSprite, not 334 browser
tests. A scheduled run at an hour I had not run at.


## A refusal and a failure are different facts, and 21 pages tell the first story about both

**Correction, and it matters more than the finding.** This section first said TestSprite had
caught this. It had not. The journey that kept failing was failing for a different reason --
my own plan was wrong, and that is written up below -- and I diagnosed a plausible cause
without reproducing it, fixed that, and wrote the fix up as the answer. The journey failed
again on the next run, which is the only reason the mistake surfaced. **A theory that explains
a failure is not the cause of it**, and the cheap check was the one I skipped: sign in the way
the failing run signed in, and look at the page.

The distinction below is real and worth having -- `/finance` already makes it, and this
codebase's own rule is that a refusal and a failure are different facts -- but it came from
reading `gateAll` while looking for something else, not from a test.

`gateAll` **fails closed**: an unreachable gate is not permission, which is correct for access
and must not change. But a transport failure and a refusal then arrive at a page in the same
shape, and the index's empty state said *"No report here is open to this session. That is
about your own access."* When the gate simply did not answer, that is a confident wrong
answer in the one place a reader decides whether to go and ask for a grant.

`UNREACHED` is the distinction — `forbidden` and `step_up_required` are the gate speaking,
everything else is the request failing before it got an answer — and the index now has a
message of its own for it, asserted different from the other in both languages.

**This is a cross-board finding and only `/reports` is fixed.** Twenty-one pages call `gate`
or `gateAll`, and a page that renders "Not permitted" when the backend is down teaches
somebody they lack access they have. `/finance` already distinguishes the two for its trial
balance (`balanceUnreadable` against `noEntity`); the rest do not. That sweep is the next
task, and it wants the same shape: a page may fail closed and still say which of the two
happened.

**Nothing has exercised the unreachable branch.** Four local layers and the visual comparison
all run against a backend that is up, so it never executes, and the component test asserts the
distinction in `UNREACHED` rather than the page's behaviour under a dead gate. That is a gap,
not evidence.

## The plan was wrong, three runs in a row, about a product that was right

`A report this session cannot open is absent, not locked` failed in round 1, in round 2 and on
a re-run. Each time the tester reported the Revenue report missing for an owner holding every
permission in the catalogue. Reproducing it settled it in one command: the same tenant, the
same owner, a fresh form sign-in, and the page lists Revenue.

**The fault was the plan's `description`**, which quoted the canvas --

> A Club Manager opening this screen sees four reports, not six. The two financial ones are
> absent — not listed and locked.

-- while the steps signed in as the **owner**. The agent did exactly what the description
said: it checked the financial reports were absent, found Revenue present, and failed. It was
right to.

**A plan's description is not a comment.** The whole point of writing these in English is that
the agent reads them as the specification, and a description that describes a different
session from the one the steps open is a plan contradicting itself. The journey is now the two
halves it should always have been: the front desk, which holds the person read and nothing of
the money modules, must not see Revenue listed *or* listed-and-disabled; and the owner must
see both reports as links.

**And the cost of the misdiagnosis is worth recording**: a commit attributed its fix to this
failure. The fix stands on its own merits; the attribution was wrong, and is corrected above.


## The refusal sweep: 25 sites, four states, one word between them

`/reports` was fixed alone; this is the rest. Twenty-five places rendered a gate refusal and
the app had words for two of the four things one can mean:

| verdict | what happened | what the reader can do |
| --- | --- | --- |
| `gate_failed` | the request got no answer | try again; this is a fault here |
| `unreachable_level` | the action needs an assurance nobody can reach in this build | nothing |
| `needs_step_up` | a stronger sign-in would open it | sign in more strongly |
| `denied` | the gate said no | ask for the permission |

`gateVerdict` and `gateMessage` are the distinction, mutation-proven: collapsing the failure
case fails four of the six tests.

Three shapes had to be fixed by hand rather than swept. `/access/[zoneId]` discarded the
answer inline (`if (!(await gate(…)).allowed)`), and `operations` and `membership-panels`
both took `{ allowed, reachable }` instead of the answer — **a narrowed shape cannot tell
four states apart**, which is how each of them reported a failed request as "Not permitted".

**And the sweep itself introduced one, immediately caught.** The permissions matrix is a
dense grid whose status cells are labels — "Needs a stronger sign-in" — and `gateMessage`
returns the page-level banners' sentences. Swapping one for the other put a full stop in a
table cell. The matrix keeps its own short words and gets `gate.noAnswer` for the new state.
A shared helper inherits a contract from each call site it replaces, which this ledger
already records for `DataGrid` and the design system's Button.

## ADM-MEM-07 — the attendance tab, whose read was built a session before it

This page's own notes listed attendance among five tabs that "need a module or a read this
build does not have", while `GET /access/attendance` was already feeding the LAST VISIT
metric cell above them. **A claim about what a product cannot do goes stale the moment
somebody builds it** — the defect MOD-014's 360 record already carries, where five sections
said "not built in this repository" and four of those modules had been built since.

The read gained what the canvas needs: a lifetime count (which is what makes the other two
figures mean anything — a fortnight's gap reads differently against two hundred visits than
six), twelve weekly buckets, and the recent visits. Each row is converted in **its own club's
zone**, because a member who trains in two cities experienced each visit on that city's day.

Three things the screen decides:

- **The empty weeks are drawn, and a zero is a mark.** The canvas's own reading is "three
  weeks at zero", which means nothing unless the zeros are there; a series that omitted them
  — what a `GROUP BY` returns if nobody fills the gaps — draws a member who trained steadily.
  The first version rendered a zero as a 0%-height bar, which is the same as no bar at all to
  a reader. Found by opening the tab for a member with no visits.
- **The canvas's sparkline, not a list.** A row per week was the same data at three times the
  height on a tab that is one of six. Each bar carries its week and count as text, because a
  bar is a colour-and-length signal.
- **No reading of the chart is offered.** The canvas prints "the drop starts the week after
  his last PT session, not the week his payment failed". Relating a gap to a cause needs a
  module that reasons about it, and a plausible sentence written by the page would be the
  Command Center's withheld interpretation panel in a worse place.

**Two kinds of attendance, and only one is unavailable.** The 360's `attendance` section said
"MOD-020 owns this and nothing here reads it" — true of *class* attendance, who was marked
present at a session. Door entries are MOD-022's and this tab reads them directly. Left
undistinguished, that sentence is a flat contradiction under a tab showing somebody their
visits, so it now names which attendance it cannot answer.

**And the third stored-value-as-label in one pass**: a visit read `nfc_card`, which is the
column's value and not a word anybody says — Latin letters in the middle of an Arabic line,
invisible to the catalogue parity check. After `lifecycle_state`, the membership plan words
and the wallet's value kinds, this is now a pattern worth stating: **a vocabulary the backend
stores is never a label, and the check that would catch it cannot.**

The fixture seeds fourteen door entries across the chart's own window with a gap in the
middle, because a member with none renders four empty states and twelve blank columns.


## ADM-ACC-03 — the member's credentials, and the last-four this build never had

The Access tab showed each credential's kind, state and expiry. The canvas draws a second
line — "Card ··· 8841 · Issued 4 Mar 2024 · 214 uses", "App pass · Rotating QR · last used
31 Jul" — and **that line is what makes the row actionable**: `state` reads `active` for a
card used this morning and for one nobody has presented in two years, and only the use count
and the date tell them apart. Both are counted from entries rather than decisions, which is
MOD-022's own separation: a granted decision nobody walked through is not a use.

**Never presented is said, not counted as zero.** A card issued today and one issued two
years ago both read 0 uses; only `last_used_at` being null distinguishes a new card from a
dead one.

**The last-four is the interesting absence.** The canvas draws `Card ··· 8841`; this build
stores a SHA-256 of the presented secret and never held a partial card number, which is the
stronger position rather than a gap. It is now said on the screen, because a reader looking
for the number and finding a kind would otherwise assume the page lost it.

Issuing a card and reporting one lost are the canvas's two actions. Both are writes behind a
stepped-up permission with no form in this build, and the screen says so rather than drawing
a button that answers "not permitted".


## ADM-PAY-05 — the recovery workspace, and the sort that makes it one

The canvas's own argument for this screen is its closing note: *"the six are one decision,
not six. Reviewing each individually is available but is the slower path, and the batch
action is the default because the recommended treatment is identical for all six."*

**That sentence is a claim, and nothing in the build could establish it.** The dunning
listing returns a stage, an attempt count and an access recommendation; whether a case wants
a payment link or a person depends on *why* the charge failed and *where the member stands*,
and neither was in any read. A batch mixing a member who needs a new card with a member
whose membership ended is six decisions wearing one button — so the sort is the screen, and
it needed backend work rather than a client-side guess.

What was added:

- **`collections.recovery_treatment`** — the decision, pure, beside the retry budget and the
  failure classes it already uses. Three treatments (`retry`, `link`, `review`), eight
  reasons, and the ordering is the content: a permanent failure is reviewed before anything
  else is asked, because `may_retry` refuses a stolen card before it looks at the attempt
  count and a "pay here" link is the same act by another route. It calls `may_retry` rather
  than re-deriving it — two retry curves in one repository drift — and reads
  `lifecycle.TERMINAL` rather than listing the ended statuses again.
- **`GET /finance/recovery`** — the same cases as the listing beside it, on the same
  permission, paired with the failure that opened each and the membership its invoice cites.
- **`GET /notifications/templates/published`** — the body had no reader anywhere. The
  listing omits it deliberately, so a template could be drafted, approved and published and
  the only way to see what it said was to send a message with it. This repository's "a
  writer with no reader" shape, closed for MOD-004's brands, MOD-017's memberships and
  MOD-018's chart, and open in MOD-013 until now.

Three judgements worth carrying:

- **The membership is the one the invoice cites, never the payer's latest.**
  `fin_invoices.membership_id` is the debt's own reference; "the newest membership this
  person has" answers about a different agreement whenever somebody has two, and makes the
  planner the author when they have two starting on one day. The fixture proves it from the
  other side: a payer with a live membership whose invoice cites none reads
  `no_membership_cited`, not `member_action_needed`.
- **The retry budget counts charges presented, not the case's attempts and not one intent's
  column.** A retry in this build is a *new* intent — a settled one does not settle again —
  so an intent's `attempts` sits at one however many times the card has been tried, and
  reading it would make `may_retry` answer "there is budget left" for ever. The case's own
  `attempts` counts dunning *steps*, and a notice is not a charge.
- **The failure's code is returned and its text is not.** MOD-017's own header says a
  decision branches on the code and never on the prose; the same holds for what a read hands
  out. `failure_detail` is unbounded free text a provider supplied, on a tenant-wide money
  permission, and adds nothing a reader can act on.

**Four things the canvas draws that this build does not have**, each disclosed on the screen
rather than drawn as though it worked:

- `Send all 6 links` has no writer — nothing in this build sends. The row **checkboxes** go
  with it: a selection control for an action that does not exist is worse than its absence.
- `veyro.link/p/8k2m` does not exist. No table holds a single-use member-specific URL, which
  is why the preview shows the template's own `{{ link }}` placeholder instead of an address.
- `Visa ···4417` does not exist anywhere. Paragraph 1597 keeps card data out of Veyro, so the
  instrument's *kind* is the whole of what a row can say.
- "Two of the six have withdrawn marketing consent" is a count this page does not make — it
  needs a consent read per payer, behind a different permission. **The rule the count
  illustrates is rendered instead**, from the template's own category: only `coaching` and
  `marketing` may be muted by a recipient preference, by a CHECK on `ntf_preferences` rather
  than by convention, so a service message reaches somebody who opted out of marketing. That
  is the sentence the design is actually making, and it is enforced rather than asserted.

**The preview is the real template, unrendered.** `templates.render` refuses a variable the
template did not declare and requires a value for every one it did, so a preview with no
values cannot render at all — and a hand-written example sentence would be the
fabricated-evidence shape. The authored body with its placeholders visible is the truthful
thing, and the placeholders are exactly what say which values a sender does not have.

**The banner's verdict moved into the lib**, because no single fixture can render both
branches. "These are one decision" and "these are not" are different sentences with
different severities, and a page that computed the comparison inline would have one branch
proved and the other vacuous — the surface-branch vacuity this repository has now shipped
four times. `batchVerdict` is tested on both sides; the fixture seeds one case of each half
so the mixed branch is what the browser suite asserts.

**The second case is on a second member**, which the canvas implies (its six are six
people) and which the suite forced: putting both halves on one payer also put a second
invoice on that member's billing tab, where two assertions locate "the settled one" by its
figure — and the membership price is the same number, so the locator matched both. That spec's
own comment already records the previous rung of this, where `INV-` matched two documents.

**The Command Center's MONEY row pointed at `/finance`.** That is MOD-018's trial balance —
an accountant closes a month there and nobody chases a failed card. `veyro-screen.js` wires
that attention item to ADM-PAY-05 by id and labels the button "Open the recovery workspace";
both are now what the build does.

**And the payments ledger's failed rows now go somewhere.** The `NEXT` cell read "Retry or
ask for a new card" and offered no way to do either — the same shape an independent tester
found on the members list, where every row said "Name withheld" and the remedy was one
screen away with nothing pointing at it. A failed charge is exactly what ADM-PAY-05 is the
workspace for, so the cell is a link to it.

**Verified in both themes and both locales**, at 1280 and at 375. The Arabic page translates
every vocabulary the backend stores — the treatment, its reason, the failure code and the
instrument — which is the class of defect `MESSAGE_KEYS` is structurally blind to and this
app shipped four of in one pass. The message preview stays English on the Arabic page, which
is correct rather than a miss: it is the *published* template, and the note beside it says
the member's own language is a different published row with no fallback chain.


## ADM-PAY-10 — the dispute, and the evidence it is answered with

> The check-in record is the strongest evidence a gym has and Veyro assembles it
> automatically. Accepting the loss is a real option and is recorded as a decision, not a
> lapse.

**"Veyro assembles it automatically" is a claim, and nothing was assembling anything.** The
module had three dispute writers and no reader at all — `record_dispute`,
`respond_to_dispute` and `settle_dispute` were each reachable and a chargeback existed only
for whoever had just written it. This build's recurring "a writer with no reader" shape, now
closed for the fourth time after MOD-004's brands, MOD-017's memberships and MOD-018's chart.

What was added:

- **`GET /finance/disputes`**, which also computes the deadline. `collections.evidence_window`
  already decides it — including letting `days_remaining` go negative rather than clamping,
  because a dispute whose window closed is the one somebody most needs to see — so a surface
  subtracting two dates would be a second definition of the one figure the screen is about.
- **`GET /access/attendance/window`**, which did not exist. `person_attendance` answers how
  often somebody *was* coming, measured over the weeks before their last visit; a chargeback
  is answered with a different question — did they come during the period this invoice
  billed for. Counted from entries and never from decisions, because a card failing at the
  door produces refused decisions for exactly the member whose attendance is being proved,
  and each visit is dated in the timezone of the club whose door it was.
- **`finance.dispute.read`, routine**, beside the financial `finance.dispute.manage`. This
  is MOD-018's own rule applied: *"a trial balance is how somebody finds out that something
  is wrong, and a read behind a step-up is a read nobody does until the month-end panic."* A
  chargeback is worse than a wrong balance because the response window expires, so putting
  the board behind the write permission would mean an accountant steps up before they can
  discover that seven days are left. The writes stay financial — answering a scheme and
  accepting a loss are money decisions and the second cannot be undone.

**Three evidence states, where the canvas has two.** ☑ and ☐ assume a reader who can see
everything; this build has gates, so a third is needed. Rendering a refused
`access.decision.read` as ☐ would tell an accountant the gym cannot prove attendance it can
prove, which is the worst sentence this screen could say. The classification lives in
`evidenceFrom` rather than inline in the page precisely so all three are provable — a
fixture renders one case, and two of the three would otherwise be reachable only by signing
in as somebody the fixture does not have.

**A rejected fiscal filing is not a reference, and the first version ticked it as one.**
The canvas's line is "Invoice and JoFotara reference" and the two halves are different
evidence: the document is the gym's own record, the acknowledgement is a tax authority
confirming it was filed. The fixture's invoice had been rejected and the row showed a tick.
**Found by looking at the page**, which is now three screens running.

**Neither button exists**, and the second is the interesting one: the canvas itself calls
accepting the loss "a decision, not a lapse", which is an argument for recording who made
it — `settle_dispute` does, and it is a stepped-up financial write with no form here.

**The fixture seeds two disputes**, four days and ten, because the deadline box has two
states and the canvas draws only the urgent one. One dispute renders one branch and leaves
the other proved by nothing, which is the surface-branch vacuity this repository has now
shipped four times.

## ADM-STF-01 · ADM-STF-02 — the team, and who can still open the product

**The canvas.** ADM-STF-01 is three chips (`Active · 14`, `Invited · 2`, `Left · 3`), an
`[Invite]` button, a four-column table — NAME, ROLE, CLUBS, LAST SEEN — an amber box reading
*"Dana's spin certification expires in 18 days"*, and a footnote: *"A Club Manager sees only
their own club's staff. Last seen exists so a departed employee with a live login is visible
rather than discovered."* ADM-STF-02 is one person's header, a `ROLE ▾` select, three CLUBS
chips, `INDIVIDUAL GRANTS · BEYOND HER ROLE` with one ticked row carrying *"Granted by Ziad ·
4 Mar 2026"* and two unticked, a red tier-4 notice, and `[Save changes] [End access]`.

**`ppl_staff_profiles` had no reader at all.** MOD-014 shipped `upsert_staff_profile` and
`end_staff_employment` fourteen modules ago and nothing that lists them, so a tenant's team was
reachable only by already knowing a person id. Fourth instance of this build's "a writer with
no reader" shape, after `GET /brands`, MOD-017's five listings and MOD-018's chart, and closed
the same way: a route on the server rather than inference in the client.

### Four columns, three planes, and why the page composes

| Column | Owner | Permission |
| --- | --- | --- |
| NAME, the home club, since | MOD-014 `plt01.ppl_staff_profiles` under `veyro_cp_app` | `people.person.read` |
| ROLE, and what is beyond it | MOD-008 `iam.role_assignments` under `veyro_iam_app` | `authz.role.read` |
| CLUBS they reach | the same assignments' scopes | `authz.role.read` |
| LAST SEEN | MOD-007 `iam.sessions` under `veyro_iam_app` | `identity.identity.read` |

No query can answer all four: the roles hold nothing in each other's schemas and are members of
no role, which is the separation MOD-007 exists to keep. So three reads through three gates, the
Member 360's own pattern — and for the stronger reason that a reader may hold any subset. A
refused half says it was refused.

**Two of the three reads are new and both are batched.** `GET /authz/assignments` and
`GET /identities/last-seen` take the identity ids repeated; asking per row is fifty round trips
against the 600-a-minute `api.request` budget the browser suite has already tripped once, which
is why `/authz/checks` exists. `require_uuids` is the list-shaped validator the id sweep needs:
a comprehension calling `require_uuid` per element passes the loop variable, so the structural
sweep — which reads names — would have reported the parameter unwrapped, correctly.

**`GET /identities/last-seen` is deliberately much less than `list_sessions`.** One timestamp,
one live-session count and the identity's status. No device, no factor, no assurance, no
address. A column on a list must not buy the page describing every device somebody has signed
in from, which is the bound `list_sessions` had to grow the moment something rendered it.

**`granted_by` had never been read.** The schema calls it "the whole delegation record" and
nothing selected it until ADM-STF-02's attribution line needed it. It stays an identity id:
resolving it to a name needs `people.person.read` and the identity link, so the attribution
degrades to eight hex characters for a reader who may not see names rather than leaking one
under `authz.role.read`.

### The defect the screen found: nothing in this build could offboard anybody

**`iam.identities.status` was read by four controls and written by nothing.** The column admits
`active`, `suspended` and `deactivated`; `authenticate`, the risk challenge, `recover_with_code`
and `_session_by_token` each refuse an identity that is not `active` — four independent
controls, each correct — and no service function, route or job ever set it. Two of three
declared states were unreachable. That is MOD-012's "a column implying a control nobody
implemented" and MOD-020's "a declared state nothing writes", in the module whose subject is
who may sign in.

It surfaced because the board puts the two halves together: an owner could be shown that a
departed employee can still sign in, and the product offered no way to act on it. Revoking a
role assignment stops what somebody may *do*, not that they may sign in.

Closed by `POST /identities/{id}/status`, `identity.identity.write` (financial, so stepped up),
and `migrations/product/0003_identity_status.sql` — because `iam.auth_events.kind` is a closed
set and the act could not be recorded at all without being named there. Four decisions:

- **Suspending revokes every live session in the same transaction.** It does not have to —
  `_session_by_token` reads the status, so a bearer token stops working the moment the column
  moves — but the revocation rows are the evidence an operator means by "I ended their access",
  and a session reading `live` beside a suspended identity is a row two readers would disagree
  about.
- **A session cannot suspend the identity it is using.** There is no platform identity here and
  nothing reinstates one from outside the tenant, so a self-suspension would end a tenant's
  administration with no remedy anywhere in the product. The refusal is recoverable; the act
  would not be.
- **The actor gets its own `auth_events` row** under the same correlation id, because the table
  records the identity an event is *about* and has no column for the one that caused it. The log
  is insert-only, so neither row can be edited to disagree with the other. Seventh module
  running for "evidence with nobody's name on it answers nothing".
- **Reinstatement exists**, because an accidental suspension with no way back would be worse
  than the gap it closed.

### Three deliberate deviations

- **No `[Invite]` button and no third chip.** There is no invitation in this build at all: no
  table, no token, no expiry, nothing that sends. A chip reading `Invited · 0` would say nobody
  has been invited rather than that nothing can invite anybody — and a button answering 403 is
  worse than its absence. ADM-STF-03 is unbuilt rather than empty. The third chip rendered
  instead is `Suspended`, which is a real state of the table and which the design has none for.
- **The amber box is a different finding.** No table here holds a coach certification or its
  expiry, so the design's thirty-day warning has nothing to read. What is drawn in its place is
  the finding the design's *own footnote* names, with real data behind it: *N people whose
  employment has ended can still sign in.* Same shape, same urgency, and actionable now that
  the status writer exists.
- **No unticked grant rows, and that is a refusal.** The canvas draws two capabilities this
  person does not hold, which implies a known candidate set somebody is measured against. There
  is none here: a permission exists if a role carries it, every role is the tenant's own, and
  "what somebody could have" is the whole 207-entry catalogue. Choosing two of those as the
  interesting absences would be inventing the product's own idea of a sensitive capability. What
  is rendered is every `financial`- and `privileged`-class permission the person *does* hold,
  from `catalog.action_class`, with what each costs — including the ones nobody in this build
  can exercise at all, which are marked rather than drawn as held.

### What is faithful, and surprisingly so

**The tier-4 notice is true, so it is rendered rather than paraphrased.** All three of its
claims hold: `authz.assignment.write` is `financial` class and needs a stepped-up session;
`_refuse_escalation` is MOD-008's one rule applied in all three places a permission can be
handed out, and it is exactly *"you cannot grant a permission you do not hold yourself"*; and
`role.assigned` is written to the hash-chained audit log naming both identities. Three sentences
of design copy, three mechanisms behind them.

**"BEYOND HER ROLE" maps onto something real.** There are no per-identity grants here — a
permission comes from a role and a role is held through an assignment — so what is beyond
somebody's role is their *additional* assignments, each carrying `granted_by` and `granted_at`
by schema. `splitRole` picks the primary as the broadest scope, earliest granted, with the
assignment id as a final tie-break so the ordering is total: an unordered answer makes the
planner the author and the screen's two halves would change between reads.

**CLUBS is the reach, not the home club.** The staff profile carries one `location_id` and says
in its own response that it is where somebody works; what they may *reach* is their assignments'
scopes, which is the authority every gate decision is made against. The two differ whenever a
receptionist based at one site holds a tenant-wide role, which is the fixture's own case. The
home club is on the NAME cell's second line, which is what the canvas's profile header does
with it.

### Six standings, because the column is a pair

`standingOf` is pure for the reason this repository has now paid for four times: a fixture
renders a branch and demonstrates nothing. `working`, `workingNeverUsed` (a stalled onboarding,
which reads identically to a working account on a column showing only a date),
`workingNoLogin` (ordinary — a cleaner on the payroll needs no account), `endedWithAccess` (the
finding), `ended` (the only clean exit) and `unknown`.

**`unknown` is the one that matters most.** A reader holding `people.person.read` and not
`identity.identity.read` must not be told a leaver has no access: nobody looked. The same answer
is given when a permitted read came back with no row, because `ppl_identity_links` carries no
foreign key into `iam` and a stale link answers nothing.

**The fixture carries all four of the reachable ones**, one person each, because a board with
one member of each pair cannot be shown to tell them apart. `ended` was *unreachable* before
`set_identity_status` existed — every departed employee was `endedWithAccess`, so the good state
was a surface branch no fixture could reach.

### Five defects found by reading the rendered page, not by a failing test

Every one of these was in a green tree: the component tests passed, the typecheck passed, the
build passed, and the page was wrong. Four of them are in the shapes this file already records.

- **The simulator was asked about one scope and the block was about several.**
  `authz.permissions_of` lets a broad assignment cover a narrow scope and never the reverse, so
  a location-scoped role contributes *nothing* at the tenant-wide default — and a narrow grant
  is exactly what "beyond their role" means. The page asked `simulate` once, at the default,
  so every narrowly scoped grant was invisible in the block built to show it. It now asks once
  per distinct scope among the person's live assignments and each grant says where it applies,
  so a tenant-wide one reads "everywhere" and a narrow one names the site. MOD-014's standing
  gap — a narrowly scoped role cannot use that module at all — is this same finding one module
  over.

  **And my first evidence for it was wrong, which is worth recording.** What I saw on the page
  was the fixture's location-scoped grant missing from the list, and I wrote that up as the
  scope defect. It was missing because `finance.refund.request` is `routine`, so the block
  filtered it correctly — a right answer for a different reason. The mechanism *is* broken as
  described, and what establishes that is two backend tests
  (`SimulatorScopeTests`) asserting both directions at the route, plus a fixture whose narrow
  role now carries a `financial` permission the wide role does not hold. "A theory that
  explains a failure is not the cause of it" — this file's own rule, met again, and the cheap
  fix was to assert the mechanism instead of reasoning about it.
- **Two level-1 headings.** `PageHeader` drew a page title and `RecordHeader` drew the person's
  name. Axe does not flag a duplicate `h1`, so the accessibility assertion passed while a
  screen reader read two documents; `/people/{id}` has used `RecordHeader` alone from the start,
  because on a record the name *is* the title.
- **The header disagreed with the table under it by two.** The figures line led with the active
  count under the words "people on the team" while the grid's own footer said four. Both
  numbers now — the distinction the members list makes, for the same reason: a figure that
  reports part of the table invites the reader to look for the rest.
- **A stored value beside its own label.** The role cell printed the display name and then
  `role_key`, which put `publisher_1795251559775` on screen. "A vocabulary the backend stores
  is never a label", fifth instance.
- **An explanation that always rendered.** The level-3 note — "a permission marked unusable
  needs assurance level 3" — was gated on `reachableAal < 3`, which is always true here, so it
  explained a row that was usually absent. It renders only where a grant is actually
  unreachable now. Same vacuity as a surface branch no fixture can reach, inverted.

And one found by a test I had just written: `scopesToSimulate`'s first comparator answered `1`
for both `compare(brand, location)` and `compare(location, brand)`, which is not a comparator
and whose result depends on the engine's sort. By rank now.

### Evidence

- 41 backend HTTP tests (`backend/tests/test_staff_api.py`): the list, the profile read, the
  batched assignments, the last-seen read, eleven for the status writer -- including that
  another tenant's identity is not answered for at either new batch route -- and two for the
  simulator's scope behaviour, which the grants block rests on.
- 28 component tests (`web/tests/component/staff.test.ts`): all six standings, the three
  severities, `splitRole`'s total ordering, `reachOf`'s three kinds, `scopesToSimulate`'s
  ordering and deduplication, the grant held only at one site, the sensitive filter, the
  unreachable mark, and the key-parity check run from the side `MESSAGE_KEYS` cannot see.
- 28 browser tests (`web/tests/e2e/staff.spec.ts`), including the desk session that holds the
  person read and neither of the other two — which is the subset that proves `unknown` renders
  as "Not checked" rather than as a clean exit.
- Three more in `phone.spec.ts`, asserting on three grids that a dropped column is actually
  dropped — the property `DataGrid`'s docstring claims and which was false below 600px.
- Both pages in the 375px sweep; both locales asserted from the rendered page.
- Six browser mutations, 6/6 caught — and the first run caught four, which is the sweep
  earning its place twice over. One mutation **did not apply at all** (two spaces of
  indentation in the anchor, not four), so a protection the list claimed to cover had no
  evidence behind it and the harness said so rather than counting it. Another was **uncaught
  and correct to be**: the `mayReadLogins` guard it removed was subsumed by the `seen ===
  null` line under it, because a caller who may not look passes no `seen` either. Deleted
  rather than tested harder, which is this repository's own judgement for a subsumed control,
  and the parameter went with it — a parameter the function cannot act on is a claim its
  signature makes and does not keep.
- And the last gap was the **"a weakening is caught only if it admits the row"** trap, in a
  fixture: dropping `|| seen.status === "active"` from the access rule changed nothing,
  because the seeded leaver *has* a live session and so is caught by the half that remained.
  The fixture grew a fifth staff member for it — a leaver who never signed in, so no session,
  whose identity is still `active` because nothing in this build had suspended it. That is
  the commonest real shape and the only row that falls on the other side of the weakening.
- `backend/scripts/verify_db.sh` after the migration: tenant isolation 111/111, audit chain
  linked, contiguous, anchored, head agrees.

### TestSprite, and the dead end an independent tester walked into

Two journeys, written in English against what a person would do and executed by an agent that
has not read this repository. The first — *"somebody who has left the company but can still
sign in is visible on the staff list"* — **passed, 7 of 7 steps**: it read the warning, found
the two rows that differ in their access, and confirmed there is no Invite button and that the
club-manager sentence is disclaimed.

The second was **blocked, and that is the finding.** Told to open the Reception person's
record by clicking their row, it could not: **a row whose name is withheld had no link at
all.** The cell rendered the marker *instead of* the link, so on an ordinary sign-in — the
front desk's own credential, where every identity field is masked — the members list and the
staff list were both dead ends, and not one row on either could be opened. The agent went
looking for another way through, found the step-up offer, and was stopped by a recovery code
it had none of.

That is the second time the same reader behaviour against the same cell has found something:
an earlier run clicked the withheld marker looking for a way through and found the members
list had no step-up offer at all. `WithheldLink` is the fix — the marker goes inside the link,
with an accessible name built from what is *not* withheld (a member number, a job title and a
start date), because a link whose only text is "Withheld" is one a screen-reader user cannot
tell from the next. **The name is what the mask withholds; the row's identity is not secret,
and the record behind it is the page that explains the withholding and offers the step-up.**

### And looking at the rendered pages found four more, one of them build-wide

**Every grid in the app rendered every droppable value twice at phone width.** `DataGrid`'s
own docstring says "a droppable value is in the DOM twice and visible once ... the stylesheet
shows exactly one at any width", and below 600px that was false:
`.ds-col-p2 { display: none }` is specificity (0,1,0) and the `.ds-grid-table td
{ display: block }` rule that turns the table into a list is (0,1,1) and comes after it, so
the block rule won. 21 duplicated values on the members list, 21 on the payments ledger, 12 on
the staff list — the whole priority-collapse mechanism, inoperative at the one width it exists
for. **Four layers of tests could not see it**: an assertion about text matches either copy,
and the phone sweep measures horizontal scroll, which a duplicate does not cause. Found by
taking a screenshot at 375px and reading it; `phone.spec.ts` asserts the property on three
grids now.

Three smaller ones on the staff record, all from the same screenshot pass:

- **The only heading read "Withheld".** Dropping `PageHeader` left `RecordHeader`'s name as
  the page's one `h1`, and at AAL 1 that name is a marker chip — so a reader arriving from a
  row had nothing to orient by. The job title leads now, which is what identified the row to
  them in the first place, with the marker beside it. And the subline stops repeating it,
  because the sentence said twice is the caption rule one component over.
- **The tier-4 notice was drawn in the wrong ink.** The canvas uses `#8a5a1f` for
  ADM-STF-01's warning box and `#8a3b1f` for this one: two inks, two meanings, and the design
  means the stronger. `critical`, not `attention`.
- **The permission descriptions are English on an Arabic page.** They come from
  `GET /authz/catalog`, which is the software's own vocabulary — two hundred strings written
  where each permission is declared, identical for every tenant. Translating them in the
  client would be a second copy that drifts from the one the server enforces, so the block
  says they are published in English only. `/permissions` has the same condition and has never
  disclosed it.

### And the phone sweep caught a latent defect in the design system

Adding one role to the fixture — the narrow assignment ADM-STF-02's grants block needs — made
`/permissions` overflow by 125px at phone width. **The matrix's width is a count rather than a
layout**: one column per role, so it was always going to cross 375px at some tenant's role
count, and the sweep found it the day a fixture crossed it.

Two causes, both needing a fix, and both established by measuring rather than by reading:

- **The table box was pinned to the container and its columns overflowed it.**
  `.ds-matrix { inline-size: 100% }` plus the global phone rule's `max-width: 100%` meant the
  box was 341px with 535px of content, so `.ds-matrix-scroll` saw a 341px child and had
  nothing to scroll. The table has to be allowed to *grow* — `min-inline-size: 100%` so a
  two-role matrix still fills the box, `inline-size: max-content` beyond that — and the global
  `table { display: block }` rule has to be overridden for it, because `display: block` turns
  `thead` into a block box whose row sits in an anonymous table wrapper the scroll box does not
  constrain. Bisected to the `thead` by hiding it and re-measuring; nothing else in the subtree
  moved the number.
- **A real scroll container still contributed to the root's scrollable area.** With the table
  free to grow the box was 343 over 535 with `overflow-x: auto`, and
  `document.documentElement.scrollWidth` was still 535. `contain: layout` is the boundary that
  stops it — and it is the right one of three: `paint` would clip the focus ring the box draws
  two rules below, and `inline-size` does not help.

The matrix is the one table in the app that scrolls rather than collapsing its columns, and
that is the design's own exception: "horizontal scrolling of a data table on a phone is never
the answer" is about a data grid, where a dropped column moves into the primary cell. A column
dropped from a matrix is a comparison a reader gets wrong.

### Known gaps

- **"A Club Manager sees only their own club's staff" is not true here**, and the page says so
  rather than letting its filter read as a boundary. Every `permit` call resolves against the
  tenant-wide default scope, which MOD-014 already records as its own standing gap; nothing
  derives a reader's own club.
- **`[Save changes]` and `[End access]` have no forms**, which is this app's consistent state:
  every stepped-up financial write is built on the server and none has a form. `End access` is
  now *possible* — the status writer exists and is tested — and still has no control here,
  because revoking an assignment takes a written reason and a form that collects one is a
  different piece of work from a button.
- **The `ROLE ▾` select is a value, not a control.** Changing it is `authz.assignment.write`.
- **No certifications anywhere**, so the Command Center item the design's amber box feeds has
  nothing behind it either.
- **A brand-scoped reach renders as a count, not a name.** `GET /brands` would resolve it and
  the page already asks three gates; a fourth read for a case the fixture does not produce
  would be a branch nothing exercises.

## ADM-TSK-01 · ADM-CC-06 · ADM-CC-07 — work, the exception it came from, and the record of it

**The canvases.** ADM-TSK-01 is three chips (`Mine · 4`, `Team · 11`, `Overdue · 2`), rows of a
checkbox over a title and a meta line (*"From exception EXC-8804 · due today"*, *"From
automation · due in 18d"*, *"Assigned by Rania · due Friday"*), bulk complete, and two
footnotes: *"Tasks born from an exception link back to it. Completing the task does not resolve
the exception — the work and the record of the work are separate"* and *"Three sources:
assigned by a person, generated by an automation, or suggested by Veyro. The source is always
named — a task nobody can account for gets ignored."* ADM-CC-06 is a side sheet over the
Command Center: a category band, a reference and an age, a headline with an amount, four facts
(OWNER, AGE, AFFECTED, SOURCE), six affected records each linking to its member, *"WHAT VEYRO
HAS ALREADY DONE"* as a timeline, four actions, and five states — unassigned, assigned to me,
assigned to someone else (every action visible but read-only, plus a Take over), resolved
(outcome, resolver, elapsed, Reopen), snoozed (reason and return date). ADM-CC-07 is the same
grid scoped to 24 hours — ITEM, RESOLVER, TOOK, OUTCOME — with *"7 resolved today · Median 41
minutes · all locations"* and *"Read-only for every role, including Owner. There is no
un-resolve."*

**Every MOD-026 permission is routine, which is why these are the first screens in this app
with a full set of working write forms.** `tasks.task.write` and `tasks.case.write` are
`data_access` with no financial class, and the catalogue argues for it: *"Raising, assigning and
settling a task is the ordinary work of a shift."* Everywhere else here a write form is absent
because its permission is a stepped-up financial one and a button that answered 403 is worse
than its absence; none of these is.

- **ADM-TSK-01 · task list** — `/tasks`, over `GET /tasks` and `GET /tasks/workload`, with
  `GET /tasks/queues` and `GET /tasks/cases` composed for the queue's name and the exception's
  reference. Bulk completion is a Server Action over `POST /tasks/{id}/status`.
- **ADM-CC-06 · attention item** — `/tasks/cases/{case_id}`, over
  `GET /tasks/cases/{id}/attention`, with `GET /people/names` composed for the affected
  members' names and `GET /tasks/workload` for whether this reader is anybody. Five writes:
  assign, release, take over, snooze and return to the queue, plus the resolution.
- **ADM-CC-07 · resolved today** — `/tasks/resolved`, over `GET /tasks/resolved`. No write of
  any kind, which is the canvas's own line rather than this screen's restraint.

### The three things a browser had to settle

**`Mine` and "Assign to me" are not expressible in a client, and two routes gained a flag.** A
session carries an `identity_id`; the link to a person is MOD-014's through
`ppl_identity_links`. So a browser has no person id for its own reader — a client-side "mine"
filter cannot be written at all, and sending one would let a reader ask the question as somebody
else, which is MOD-020's four caller-supplied person ids in one route. `GET /tasks` takes
`mine=true` and `POST /tasks/cases/{id}/assign` takes `to_self`, both derived through
`actor_person_id`, which is what `/tasks/workload` already did for the count the chip shows.
Refusing `to_self` beside a named person is the same discipline: a request carrying both is a
caller that does not know which it meant. **An identity with no person record gets an empty
answer rather than everybody's work**, and `mine_is_zero_without_a_person_record` is how the
screen says why — staff hold permissions and do not have to be anybody in particular.

**The board had two definitions of "open" and the screen showed both.** The chips count work in
hand and the unfiltered list showed every status, so it read `Team · 7` over a table of eight
rows, one of them already done. `in_hand` is the filter that makes them one figure, and the
screen says what the list is. Found by rendering the page and reading it.

**"Overdue" is an instant and "due today" is a calendar day, and the label disagreed with the
filter.** The server's filter is `due_at < now()`; `dueState` bucketed by date on both sides, so
a task due at nine this morning read *"due today"* at five in the afternoon while the Overdue
chip counted it. `dueState` compares instants for lateness and dates for everything ahead of
it, and zero days late is its own message because *"overdue 0 days"* is not a sentence. Found by
the browser layer asserting that every row in the overdue view says so.

### Deviations, each with the product's reason

- **ADM-CC-06 is a page, not a side sheet.** `SideSheet` is named in Batch F's component list
  and nothing in the sources gives its anatomy or measurements, so building one would be
  inventing the missing part of the design rather than implementing the present part. And
  **nothing routes into it from the Command Center**: that queue is computed live from MOD-017's
  collections, MOD-019's staffing and MOD-022's doors rather than filed as `tsk_cases` rows, so
  there is no originating row for an Esc to return focus to and the canvas's keyboard contract
  has nothing to bind. Deciding which computed item becomes a case is a product decision about
  what an exception *is*, and this slice does not settle it.
- **A task's meta line names its source where the canvas names a person.** `tsk_tasks` carries
  an assignee and no assigner, so *"Assigned by Rania"* is unanswerable: "who has what" is a
  question this build answers and "who gave it to them" is not.
- **ADM-TSK-01's far due dates read as a date rather than a weekday.** The canvas writes *"due
  Friday"* and *"due 25 Aug"*; past a fortnight a day count stops being placeable and a weekday
  name is ambiguous about which week it means, so the forms are a count up to fourteen days and
  a date beyond.
- **The resolver is a sign-in, not a name.** `resolved_by` is the identity that settled the
  item, and the link runs from a person to their sign-in rather than back — so a name there
  needs a read that does not exist. Said on the screen.
- **No Reopen on a resolved item.** A reopening is a new case citing this one and its reference
  is the tenant's own; nothing in this build mints a case number, and a form asking a reader to
  type one would be asking them to do the product's job. The resolved list already carries the
  canvas's *"there is no un-resolve"*, so the two agree.
- **No 30-second undo.** A resolution is forward-only by trigger, so there is nothing to undo
  with — which is also what makes ADM-CC-07 a record rather than a state.
- **No "Send 6 payment links".** MOD-013 authors a message, claims it and settles it, and sends
  nothing: a button would report work that did not happen. The canvas's other secondary route,
  *"Open recovery workspace"*, exists and is linked.
- **No club scoping.** `permit` resolves tenant-wide, so a club manager sees every queue. The
  standing scope gap, said on the screen rather than implied by a filter.
- **The affected records carry no reason or amount.** The canvas prints *"Card expired ·
  55.00"*; nothing relates an affected record to the charge it is about. The names beside them
  are composed through `people.person.read` and are withheld where that permission is.
- **No count under the resolved grid.** §25 asks a grid to state its count and the canvas states
  it in the sub-line above, so a count beneath would be the same sentence twice — the rule the
  `DataGrid` caption and the field shell's message slot both already carry.

### What the fixture can and cannot show

**Every elapsed time is under a minute, and that is the fixture rather than the screen.**
`tsk_cases.opened_at` is `now()` and no route backdates it, which is right for the product — a
case is opened when it is opened. So `TOOK` and the median are honest and uninformative here,
and the *format* is proven against the canvas's own `12m` / `1h 20m` / `2h 04m` in
`web/tests/component/tasks.test.ts`. The empty-window branch, where the median is absent rather
than zero, has no browser fixture for the same reason.

**The fixture seeds a reader who is somebody.** Both `Mine` and "assigned to me" need a session
whose identity is linked to a person, and the owner is nobody in this tenant. So a duty manager
is seeded, linked, and granted only the MOD-026 reads and writes — and the owner then reads the
same item as *somebody else's*, which is the one state ADM-CC-06 is most specific about. Both
halves have a fixture rather than only a component test, which is this repository's own "a
surface branch no fixture can reach" trap, paid for four times.

**Nothing in the browser suite presses a destructive control.** Resolving is one-way and
assigning writes a timeline entry nothing removes, so a spec that pressed either would pass on
the first run against a fresh fixture and fail on every run after it. What the browser asserts
is which controls are offered, which are inert and what each state says; the writes are proven
by `backend/tests/test_tasks_api.py` and by nine mutations over the decisions.

## ADM-CRM-01 · ADM-CRM-02 — the pipeline, as a board and as a table

**The canvases.** ADM-CRM-01 is a header (*"36 open leads · 7 going cold"* over *"Khalda · 31%
converted over 30 days, up 4 points"*), an `Add a lead` button, and five columns — New 12,
Contacted 9, Toured 6, On trial 7, Joined 11 this month — each a stack of cards carrying a name
and one meta line (*"open day · 2d"*, *"instagram · 4h"*, *"called · 1d"*, *"Mon 17:00"*, *"day
6 of 7"*) with a `+10 more` overflow. Its COMPONENTS line names `PipelineColumn ×5 · LeadCard ·
Member360Header(lead variant) · AITreatment(ai.600) · StatusBadge(no-contact)`. ADM-CRM-02 is
the same rows as a grid — LEAD, SOURCE, OWNER, AGE, NEXT ACTION — with three chips (*"No contact
48h · 7"*, *"Trial ending · 4"*, *"Mine · 12"*), a `Board view` toggle, and the note that fixes
the whole screen: *"Same grid component as the members list at the same 34px. Sales sees their
own leads by default with a Mine toggle; a Club Manager sees the team. Age is the sortable
column that matters — a lead's value decays by the hour, so it carries colour where the others
do not."*

**Every MOD-027 permission is routine**, as MOD-026's are and for the same reason: raising,
claiming and writing up a lead is the ordinary work of a sales shift, and a step-up on every
logged phone call would make the pipeline wrong instead. So nothing on these two screens is
absent for want of a step-up.

- **ADM-CRM-01 · lead pipeline** — `/leads`, over `GET /crm/board` for the five counts and the
  header's two figures, `GET /crm/leads` for the cards, and `GET /people/names` composed in one
  batch for the names. `PipelineColumn` and `LeadCard` are new design-system components, built
  from the canvas's drawing because the COMPONENTS line names them and nothing else specifies
  them.
- **ADM-CRM-02 · lead table** — `/leads?view=table`, the same reads through `DataGrid`, with
  `rowSeverity` carrying the cold mark the canvas asks for by name.
- **ADM-CRM-03 · lead profile** — `/leads/{lead_id}`, over `GET /crm/leads/{id}` with
  `GET /people/names` composed for the name and the owner's. `RecordHeader` with the cold band,
  four `MetricCell`s, a `Timeline` of touchpoints, and **five working forms**: a touchpoint, a
  stage move, the ownership, the next action and the interests.

### The four things this screen had to settle

**A lead has no name, so the board composes one.** MOD-027 holds no name, number or address —
ADM-CRM-01 makes it structural, *"a lead, a trialist and a member are one record at three
stages"* — so every name on these two screens comes from `GET /people/names` in a single batch,
masked by MOD-014's rules rather than this screen's. Not one request per row: a board of fifty
is the round-trip problem the staff list paid for once. The owner column rides in the same
batch, because a second request for the second column would be two round trips for one table.

**The counts are the tenant's and the cards are a page.** A column can read 12 over two cards
and a `+10 more` line, which is the canvas's own shape: the board read counts every lead and the
card list is a bounded page. A chip figure taken from the fifty rows loaded would be the
members-list finding, where summing the page was honest and still the wrong number in the place
a manager reads the business.

**The cold mark is `rowSeverity` and an edge-mark, never a fill.** *"Age is the sortable column
that matters … so it carries colour where the others do not"*, and a pipeline stage is not a
severity: painting the five columns would make the board read as a problem list. A lead in `new`
is not worse than one in `toured`.

**`Mine` is a flag on the request.** A session carries an `identity_id` and the link to a person
is MOD-014's, so a client-side "mine" filter is not expressible — the same finding ADM-TSK-01
paid for, and the same remedy: `GET /crm/leads?mine=true` and `GET /crm/board?mine=true` derive
it. A reader whose sign-in is not linked to a person gets the reason rather than an empty board,
because staff hold permissions and do not have to be anybody in particular.

### What is drawn and empty, and what is not drawn at all

**`On trial` is drawn with its reason on the column.** Nothing in this build marks a product as
a trial — neither `cat_products.product_type` nor `mem_membership_terms.membership_kind` has
such a value — so no lead can be on one and the column is always empty. Hiding it would make
the board read as four stages, which is a different product from the one the design draws.

**Two things on the canvas are absent and named on the screen.** The *"VEYRO SUGGESTS · YOU SEND
IT"* block needs a model nobody here has an account with; its permission exists and is
`privileged`, which needs a hardware sign-in. And *"31% converted over 30 days, up 4 points"*
needs a conversion to count, which needs the trial — the same gap as the column above.

**The third chip is not offered.** *"Trial ending · 4"* is slice 2's, and a chip that filtered
to nothing would read as a club with no trials ending rather than as a build with no trials.

## ADM-CRM-05 — the trial running, as a state of the lead profile

**The canvas.** One card titled `ADM-CRM-03 · LEAD PROFILE · ADM-CRM-05 · TRIAL RUNNING`:
`DAY 6 OF 7` as a band over the name, **"Her trial ends tomorrow"** with *"Four visits, four
classes, all spin. She has used the trial more than most — this is a conversion, not a
chase"*, a `Convert to member` button, and four cells — `4 VISITS · 4 CLASSES · 2 DAYS LEFT ·
High ENGAGEMENT`.

- **ADM-CRM-05 · trial running** — the trial state of `/leads/{lead_id}`, over
  `GET /crm/leads/{id}/trial`. Not a route of its own: the card's title names both screens, so
  the band, the metric row and one section change and everything else stays.

### The six things this screen had to settle

**It describes use and refuses to predict.** The drawn canvas's fourth cell is `ENGAGEMENT`;
the prototype runtime calls the same cell `CONVERSION LIKELIHOOD`, which is a prediction about
a person — and MOD-020 refuses exactly that for the no-show score, because *"paragraph 1889's
'must not discriminate unlawfully' is a property of a population under a model rather than of
an expression, so no function can promise it"*. The drawn canvas is the deliverable and the
same reasoning holds, so the cell says how much of the trial has been used. That is also what
the canvas's own prose argues from.

**Every figure is inclusive of the day it is counted on**, because the canvas's three date
numbers only agree that way: `DAY 6 OF 7` beside `2 DAYS LEFT` beside "ends tomorrow" is a
seven-day trial on its sixth day with today and tomorrow left. One unit test pins all three
against one window, because an exclusive count gets two of the three right and a reader would
not notice which.

**The band measures visits over the days *elapsed*, not over the trial.** On day two of seven,
two visits is somebody who has come every day; measured against seven it is 0.29 and reads as
light — so a band keyed on the whole trial would improve as the trial ran out, which is useless
on the day it matters. And `none` is its own band rather than the bottom of a scale: "nobody has
been in" is a different conversation from "they came once".

**A visit and a class are different facts and the screen says so.** A visit is MOD-022's entry
event — somebody came through a door — and a class is a MOD-020 booking settled `attended`, so
a member who trains in the gym four times has four visits and no classes. The canvas draws both
cells for that reason, and `attended` rather than `booked` because a booking nobody turned up
to is a `no_show`.

**Three permissions, because the card carries three modules' facts.** The window is MOD-017's,
the visits are MOD-022's and the classes are MOD-020's — so a reader holding only the lead read
would otherwise get the other two modules' figures out of a CRM route, which is MOD-010's
`events.event.read` finding. All three rather than a partial card: the canvas draws four cells
together and three of them is not the card.

**And the figures are the server's, which is the opposite of the Member 360's judgement.** That
screen composes per block and renders a refused one as refused; this one is a single read,
because every figure on it is an arithmetic over today and a browser comparing dates against
its own clock counts in the wrong frame — which this app has three recorded defects from. A
surface handed four counts and asked to work out "day 6 of 7" would be the fourth.

**What is named rather than drawn.** The canvas's `Convert to member` button: converting is a
plan change onto the membership being sold, which needs a stepped-up financial permission and a
price, and the payment behind that button is the provider. The arithmetic is built —
`/memberships/{id}/plan-change-preview` prorates the days left on this product against the one
being moved to — so what is missing is the form and the charge, both named on the screen. And
*"all spin"*: nothing here counts classes by what they were, and naming a class the read did
not identify would be the confident wrong answer MOD-014's own 360 was bitten by.

### Two records this screen corrected

**`ADM-CRM-05` was listed as one of three genuinely unspecified screens, and its design was in
the folder all along.** The extractor's title pattern is *one or more ids, then the
description*, so a card labelled with two ids lost the second — see the coverage table above
for the fix and what it moved.

**And the lead profile's own gap note said "nothing in this build marks a trial product"**,
which ADR-0010 D7 made false the day it landed. Found by a browser assertion written against
the *metric row* matching that sentence at the foot of the page, which is the third stale gap
note this surface has rendered.

## ADM-CRM-07 — mark lost, and the stage that does not move

**The canvas.** `ADM-CRM-07 · MARK LOST`: **"Why did Omar Zaid not join?"** over four reasons
— `Too expensive` / `Joined somewhere else` / `Location or hours` / `No longer responding` —
then "Which gym, if he said…", a `Mark lost` button, and the footnote the whole design rests
on: *"Not deleted. Reopenable, and re-contact after 90 days is a supported flow rather than a
fresh record. The reason feeds source effectiveness in ADM-RPT-03."*

- **ADM-CRM-07 · mark lost** — `/leads/{lead_id}?lost=1`, over
  `POST /crm/leads/{id}/lost`, `/reopen` and `/interests/withdraw`. A side sheet in the design
  and a query parameter here, which is ADM-MSH-07's judgement: this app has no side sheet, and
  the parameter keeps the lead's context on screen while giving "Keep it open" somewhere to go.

### The decision this screen exists to make visible

**`lost` is a fact beside the stage, not a sixth value in it — and that corrects a prediction
the repository made about itself.** ADR-0010's slice-1 note and `CLAUDE.md` both said the stage
domain admits three "because a declared value nothing writes is this build's most-repeated
finding and slice 3 is what writes it", assuming a stage value. ADR-0010 D3 rules it out one
section earlier: the pipeline runs forward only, because "a tour that fell through is a
touchpoint saying so" and a backwards move "would make `Toured · 6` a count nobody can
reconstruct" — and a lost lead that reopens needs exactly that edge. So the screen says **"Still
at Toured, because the stage does not move when a lead is lost"**, which is the sentence that
makes the decision legible rather than implicit.

### The four things it settled

**The reason is a closed four and there is no "Other".** A group-by needs a closed set, and
free text would make any such report a group-by over typos. `no_longer_responding` absorbs a
lead who simply stopped, and the free-text detail is where a salesperson writes what they
learned. A fifth is a product decision rather than a migration.

**And the report the footnote names is not that report, which building this found.** It sends
the reason to "source effectiveness in ADM-RPT-03", and ADM-RPT-03 is the *membership* report
— its own canvas draws `WHY THE 23 LEFT` and states "Reasons come from ADM-MSH-07's required
field", so its subject is members cancelling rather than leads who never joined. ADR-0010's
build order named ADM-RPT-06 for the same read, and the registry has no ADM-RPT-06 at all. So
**no drawn screen consumes a lost-lead reason** and the vocabulary stands on the group-by
rather than on a destination. What ADM-RPT-03 does want is this same shape one module over: its
chart is blocked because `mem_lifecycle_changes.reason` is free prose, which that screen already
records, so a structured cancellation reason on MOD-017 is the work that unblocks it.

**Ninety days is advisory and both sentences say reopening is allowed.** The canvas's emphasis
is on *"rather than a fresh record"* — re-contact does not duplicate the person, which the
one-lead-per-person index already enforces. Locking the write for a quarter would make a lead
marked lost by mistake uncorrectable on a routine permission, which is MOD-013's rule; so the
read says which are worth another try and the button works either way.

**`ReasonPicker` is `ChoiceChips` in single mode, not a second component.** Its canvas draws
four chips in exactly the shape ADM-CRM-04 draws three interests in, and a lead is lost for one
reason — so the control becomes `<input type="radio">` and the group keeps the semantics the
appearance implies. Two components for one appearance is the duplication-by-divergence that
file's own mark note already records.

**The interest withdrawal landed with it, because `0027` said slice 3 owed it.** Each held
interest has a `Take back`, and the section's "an interest cannot be taken back yet" note is
deleted with the gap. Until this existed `crm.lead.write` was a routine permission whose every
act on an interest was permanent.

### The chip, and why it is a filter rather than a view

**`Lost` sits beside `Going cold` on the table and nowhere on the board.** It is a filter
because this is one list of one thing — the board's five columns and the table are the live
pipeline, and a lead who said no is the same record with a reason on it; two routes would be
two definitions of what a lead is. And it is table-only because ADM-CRM-01 draws five stages
and ADM-CRM-07 is a side sheet, so a chip on the board would ask for a list the board cannot
draw, and one that changed the view under the reader would be worse than one that is absent.

**Without it a refusal was reachable only from its own profile.** `GET /crm/leads` took
`lost=true` from the hour the read landed and nothing on `/leads` sent it, so a salesperson
reviewing why people did not join had no list at all — the "writer with no reader" shape at
the surface, which this app has recorded twice on the members and staff lists and which an
independent tester found both times rather than a spec.

**And the test for it was vacuous in both directions before it was fixed.** It asserted the
lost lead's *name*, and every name on these screens is withheld at an ordinary sign-in —
`legal_name` is an identity-class field — so "Rami Odeh" is absent from the live list and from
the lost one alike. The row's own `href` is what is rendered and unambiguous.

## ADM-CRM-06 — convert a trial, and the quote that did not exist

**The canvas.** `ADM-CRM-06 · CONVERT`: **"Rana becomes a member"** over three money lines —
`Club · monthly · JOD 55.00` / **`Pro-rata to 31 Aug · JOD 21.29`** / `Then 55.00 from 1 Sep`
— then *"Her four class attendances, her credential and Yasmin's notes all carry over. Nothing
is re-entered."*, two buttons `Take 21.29` and `Send link`, and the footnote *"Same record, new
state. The lead ID becomes the member ID — this is the duplicate-entry fix from the UX review,
enforced structurally rather than by discipline."*

- **ADM-CRM-06 · convert** — `/leads/{lead_id}/convert`, over `GET /memberships/plans` for the
  plan pick and `GET /crm/leads/{id}/conversion-quote` for the figures. Its own route rather
  than a state of the profile: this canvas is a card with its own id, and the plan pick is a
  selection the profile has nowhere to put.

### What the figure cost to produce

**21.29 is `55.00 × 12/31` and this build could not express it.** `renewal_period` tiled from
the previous period's end, so a membership sold on the twentieth billed 20 Aug–19 Sep and the
boundary the canvas states — 31 August, with the recurring charge from the first — was
unreachable. That is ADR-0011, and the arithmetic now reproduces the card exactly.

**And the recurring figure had no reader that was not a sale.** `resolve_price` stores the
explanation insert-only and redeems the coupon it applies, so calling it to put a number on a
screen would write a receipt for somebody who has agreed to nothing; `list_prices` says in as
many words that a row in its own window is not the resolved price. The quote took no new
arithmetic: `resolve_price` has carried `store: bool = True` since MOD-016 was built, with the
receipt and the redemption both inside its `if store:` block, and **nothing had ever passed
`store=False`** — a parameter with no reader, implementing the read `catalog.price.read` is
described as granting.

### The five things this screen had to settle

**Neither of the canvas's buttons is drawn, and the reason is not the usual one.** Every other
absent form in this app is a stepped-up financial permission and is absent because "a button
that answered 403 is worse than its absence". `Take 21.29` is the payment provider and
`Send link` is the messaging one — two of the seven things this build waits on from outside —
so the screen names each with its own cause rather than letting a reader conclude they need a
stronger sign-in and go and get one for nothing.

**A third absence is named with them, and it is a judgement rather than a blocker.**
`change_membership_plan` is built and is what ADM-MSH-05 rests on, so writing the superseding
agreement is available — and it issues no invoice, so a button that converted without charging
would leave a member with access nobody has paid for. Converting and charging are one act at
this door and half of it is worse than neither.

**Nothing with a count of zero is claimed.** *"Her four class attendances ... carry over"* is
true of Rana and false of a lead who has never booked anything, and a line reading `0 class
attendances` is the confident wrong answer MOD-014's own Member 360 was bitten by. The
structural sentence is shown either way, because that one is true of everybody: there is one
person row, so a conversion moves nothing. **The credential is in the sentence and not in the
list**, because what somebody can present at a door is MOD-022's own read behind its own
permission and the quote carries no count — claiming it for a member who has none would be the
same wrong answer in the other direction.

**The plan pick is links, not a control**, so a chosen plan survives being sent to somebody and
works with no JavaScript — the members list's, the schedule board's and the attendance report's
decision. And the picker carries **no figure**: a price needs `catalog.price.read` and only a
quote may name it, so "see the catalog" must not buy "see what every sale costs".

**Seven gates, and five of them are the quote's.** The figures are MOD-016's resolution and
MOD-017's contract, the window is MOD-017's row, the attendance is MOD-020's and the visits are
MOD-022's; the picker is MOD-016's catalogue and the name is MOD-014's. Without any one of the
five the server refuses the whole card rather than returning part of it, so the screen says so
rather than drawing a figure it cannot complete.

### What this screen found outside itself

**The lead profile's "Convert to member" was a gap entry**, reading *"it is a form this screen
does not have yet"* — so closing the gap meant deleting the note in the same change, and the
control is a link now. **The profile's own docstring had a second stale paragraph**, claiming
the canvas's four trial figures "are not drawn" because "nothing in this build marks a product
as one"; ADR-0010 D7 settled that and ADM-CRM-05 drew them.

**And the trial card was a lateral read path.** `GET /crm/leads/{id}/trial` charged three
permissions and its own docstring named MOD-017's window as one of the three facts, while
`membership.record.read` — "See a membership, its history and its terms" — was not among them.
The card returns a membership id, a start, an end and the terms' `trial_days`. It is routine
and AAL 1, so a salesperson holds it anyway and nothing real is refused by adding it; what is
closed is a sales permission reaching a membership row.

**The fixture had no plan this screen could use.** Every plan it seeded was called "Monthly"
and sat on the `agreement_start` anchor, so the picker was a row of identical chips and the
canvas's pro-rata line could never render in a browser — this repository's "a surface branch
no fixture can reach" trap for the fifth time. A Club plan on the `calendar` anchor is seeded
for it.

## ADM-CRM-04 — add a lead, and the duplicate the door prevents

**The canvas.** *"New lead · Name and phone are enough. Everything else can wait."* Two fields,
a detection panel reading **"No existing record"** over *"Checked as you typed against members
and leads. If this number already existed, that record would open instead of a second one being
created"*, then `SOURCE · OPTIONAL` as a dropdown and `INTEREST · OPTIONAL` as three chips with
`Classes` and `PT` filled and `Gym only` outlined, and one button: **Save lead**.

- **ADM-CRM-04 · add lead** — `/leads/new`, over `GET /people/contact-match` for the check as
  you type, `GET /crm/sources` for the dropdown, then `POST /people` and `POST /crm/leads`.
  `ChoiceChips` is a new design-system component: §23 names eighteen field types and
  `multiselect` is one of them, nothing provided it, so the drawing is the specification.
- **ADM-CRM-01's own "Add a lead"** — the live screen draws `prim('Add a lead')` in its header
  row and `/leads` rendered nothing there. The same shape as ADM-MEM-05's missing *Add member*,
  with the same consequence: this screen is the only way to open a lead from a cold start and
  nothing led to it.

### The six things this screen had to settle

**The state this canvas draws is the *clear* one, and that is what makes the panel a detection
region rather than a warning.** ADM-MEM-10 draws the same panel — same border, same title ink,
same `warning.600` — saying *"This number already has a record"*; this one draws it saying
nothing was found. So the treatment is not a severity signal in the design's own usage, and
painting the clear verdict in green or in neutral ink would be two components where the design
has one. It is rendered as drawn, in `--color-semantic-warning`, in all three states.

**The match state is borrowed from ADM-MEM-10, because this canvas does not draw one.** It is
the same check over the same read, so the nearest authority for the shape is the sibling screen,
and that is where *"Different person"* comes from. Without that escape a desk could never record
a second sibling on a shared family line — which is the ordinary case paragraph 10200 requires a
human for rather than a threshold — and nothing else in this build creates a lead.

**And the canvas's sentence is a third action, which only this screen can offer.** *"That record
would open instead of a second one being created"* is a statement about what happens, and for a
lead it is literally available: `POST /crm/leads` takes a `person_id`, so a match becomes a lead
against *that* person with one write and no second record — and if they already have one the
server returns theirs, which is the sentence exactly. ADM-MEM-10 cannot do this, because a
member is one command against a person who does not exist yet. Until this screen did it,
`POST /crm/leads` had no caller for an existing person anywhere in the product.

**It is also the one control here a routine session can use.** Creating a person is
`people.person.write`, financial class and a step-up; opening a lead against one is
`crm.lead.write`, routine; the dropdown needs `crm.source.read`, which is a third. So the page
asks three write-side questions rather than one, and the hold under the button says the match
path is still open to a session that cannot create a person — because it is.

**Two writes, so there is a window, and the form reports what is in it.** Nothing makes two HTTP
writes atomic from a browser, so a person created with no lead is a real outcome. A reader told
only *"that was refused"* would type the name again and be stopped by their own duplicate check,
which is the worst of the three available answers; the state carries the person's id and the
banner offers to open it.

**The sub-line is rendered, and this is the one screen where that is not the prose `PageHeader`
bans.** Its rule — *the design's header is a title and a line of figures, never a paragraph* —
was derived from the data canvases, and ADM-MEM-10's canvas obeys it with a title and nothing
under it. This canvas draws *"Name and phone are enough. Everything else can wait."* in the
secondary ink, and that sentence is not a description of the screen: it is the form's own
instruction, telling a receptionist they may stop after two fields. A form has nothing to count,
so the slot is free.

**What is named rather than drawn**, each with the product's reason: assigning an owner (the
route takes a person id and this screen has no staff list; the profile assigns it), starting a
trial (nothing marks a product as a trial, which is the first thing slice 2 decides), one
command for both writes, and an email address — which the canvas leaves out in as many words.

### What the two screens now share

**One check, one panel line, one set of decisions.** `@/lib/walk-in` holds the detection, the
stale-answer derivation, the acknowledgement rule and the hold; `@/lib/contact-check` is the
request; `ContactMatchLine` is the matched record's own line. A lead *is* a person, so a number
already on a record is already on a record — and two copies of any of that would be two
definitions of *does this number exist*, which on the day they disagreed would have one screen
create the duplicate the other prevents. The line was a copy for about an hour, differing only
in which catalogue key spelled *joined*; it is one component with one pair of keys now, because
a line that must say the same thing in two places drifts the first time either is edited.

### A design-system defect this screen found

**The field shell's optional mark was hard-coded English.** `rarer="optional"` on a field that is
not required rendered a literal `" (optional)"`, which is Latin letters in the middle of an
Arabic line — live on the account page, for as long as that field has existed. Neither message
check could see it: `MESSAGE_KEYS` compares the two catalogues against each other and a string
that never became a key is in neither. `StatusBadge` is the precedent — *the enum is the state
and `label` is the word* — so the shell takes `optionalLabel`, renders no mark without it, and
`tests/unit/ds-usage.test.mjs` requires it wherever the branch is reachable. Mutation-proven
against the one existing call site.

### ADM-CRM-03's own five decisions

**Five working forms, because every MOD-027 permission is routine.** A touchpoint, a stage
move, the ownership, the next action and the interests — all `data_access` or `configuration`
with no financial class. This is the second module in this app with a full set, after MOD-026,
and for the same reason: *"raising, claiming and writing up a lead is the ordinary work of a
sales shift"*, and a step-up on every logged phone call would make the pipeline wrong instead.

**No button where the pipeline has no edge.** `toured` is the last sales stage — the two
columns after it are what a membership answers — so a toured lead is offered the sentence
rather than a move the service would refuse. FD-06's *"a button the module will refuse is worse
than no button"*.

**One ownership control, because the server refuses a no-op.** Assigning the owner a lead
already has is a 409: a write that changed nothing would bump the version and read as a
handover somebody made. So an owned lead is offered the release and an unowned one the claim,
and which act a claim turns out to be — a claim or a handover — is the server's to name from
what the column held.

**The interests form says the set cannot shrink, before the tick rather than after it.** There
is no UPDATE and no DELETE grant on `crm_lead_interests`, so an interest recorded by mistake is
uncorrectable until the slice that adds `lost` adds the withdrawal. An interest already
recorded is not offered again, which is what makes the remaining checkbox mean something.

**Four of the canvas's figures are the trial's and are named rather than drawn.** `4 VISITS`,
`4 CLASSES`, `2 DAYS LEFT` and `High ENGAGEMENT` all need a trial, and nothing in this build
marks a product as one. A metric cell reading `0 VISITS` for a member who has been four times
is the confident wrong answer MOD-014's own 360 was bitten by, so the metric row carries the
stage, the last contact, the touchpoint count and the next action — four figures this slice can
answer — and the gap list names the other four. The phone number in the canvas's subline is a
contact point behind its own permission and is named too, as is WhatsApp, which nothing here
can send.

**And an empty timeline is a sentence rather than a list of one.** `Timeline` renders an `<ol>`
and an `<ol>` may hold only `<li>`, so a banner inside it is an accessibility violation — which
the profile's own axe scan caught. The empty state replaces the component rather than sitting
in it.

## FD-05 — the walk-in trial, and the two promises the canvas makes that this build cannot

The canvas is the shortest in the inventory: `NAME`, `PHONE`, **Start her trial now**, and
three sentences under it.

> Creates a lead already in trial with the clock running, a credential, and an app invitation
> by text. Yasmin picks it up on her pipeline within the minute.
>
> A person standing at a desk will not complete a six-field form. Two fields captured beats
> eight fields abandoned, and the record is the same record she converts on.

`/desk/trial` is it, and the registry's own one-line spec is what the server had to grow:
"creates a lead already in trial state with the clock running. Everything else is captured
later by the sales team." Seven decisions carry it, and three are refusals.

**One press, one request, four writes — resumable rather than atomic.** ADR-0010 D12 argues it
at length and the short form is that none of the four is a control over another's state: a
person with no lead is what ADM-MEM-10 produces, a lead at `new` is the board's first column,
and a signed agreement nobody activated is `activate_membership`'s own retry path. What makes a
second press converge is that every step keys on the person. So the screen reports what the
server performed, step by step, rather than claiming to be atomic — and unlike ADM-CRM-04,
which makes two HTTP writes and tells the reader when the first landed and the second did not,
there is no browser-side window to report at all.

**The duplicate panel is borrowed, because the canvas does not draw one and the screen needs
it.** This is the third door in the product that creates a `ppl_persons` row, and leaving the
check out would make it the one where a duplicate is cheap — in the screen whose own footnote
says "the record is the same record she converts on". Every decision behind it is
`@/lib/walk-in`'s and the request is `@/lib/contact-check`'s, imported rather than re-decided:
a lead *is* a person, so a number already on a record is already on a record, and a second copy
would be two definitions of "does this number exist".

**The acknowledgement is sent to the server, which is the difference from the other two
screens.** There "Different person" releases a client-side hold; here the *command* refuses a
number somebody holds — MOD-014's `AUTO_MERGE_THRESHOLD` is `None` because two siblings at one
address with one family line is the ordinary case — so the field is what says a human looked at
the match and decided.

**"Start the trial for them" is the sentence ADM-MEM-10 can only link to.** The command takes a
`person_id`, so a match becomes a trial on *that* record with no second person. It still needs
the step-up, because the agreement and the activation are financial class whoever they are for
— which is where it differs from ADM-CRM-04's equivalent, whose match path is routine.

**The heading names the trial's length because the canvas's does.** "Start a 7-day trial" is a
figure, so it comes from the published plan's own `trial_days`; with two plans of different
lengths there is no single answer until one is chosen, and a heading naming one of them would
be naming whichever sorted first. That case gets a third field — the one control the canvas
does not draw — which is `/rota`'s "no rota binds" judgement rather than a deviation: a state
the drawing does not have, rendered honestly. A tenant publishing **no** trial gets the form
withdrawn and the reason, because a gym that sells no trial cannot use this screen at all.

**Nothing is marked on any field, which is the shell's rule rather than an omission.** The mark
goes on the rarer side and a form with no optional field has no rarer side — ADM-CRM-04's own
setting for the two fields its canvas leaves bare. And `aria-required` rather than `required`,
for that screen's reason: the native constraint makes the browser refuse the whole form, and
this one has a second submit that legitimately needs neither field.

**Two of the canvas's three promises are not kept, and both are on the screen.** A credential
needs somewhere for the member to show it, and this build has no mobile client and nothing that
could send one; the app invitation is the messaging provider. Neither is a reason to withhold
the trial, which is the part a desk is standing there to do — and a screen that implied a text
had gone would be telling a receptionist something that did not happen.

**It is also the first `/desk` route reachable without an id**, which is why it is the first in
the rail. FD-01, the live check-in a receptionist starts a shift on, is unbuilt; FD-06 and FD-03
are reached from a class and a refusal. The rail entry is therefore named for the screen rather
than for the surface, because an item called "Front desk" would promise FD-01.

**What is still owed**, each named on the screen: the credential and the invitation above; an
owner, because the form has no list of staff to choose from and an unowned lead on the board is
what "Yasmin picks it up within the minute" means; and a membership number the club chose,
which this build has no scheme for — the handle is derived from the agreement instead, stable
across a retry, and said to be a handle rather than printed as a number.

Proven: 15 Python mutations against the command, all caught; 12 HTTP tests; 9 component tests
over the plan states and the confirmation's wording; 7 browser tests, two of which step up and
one of which starts a real trial; and the phone sweep carries the route.

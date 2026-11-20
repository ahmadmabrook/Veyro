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
| **Specified** — drawn, with copy, states and layout rules | **167** |
| `NO-UI` — the registry says the screen is not needed | 8 |
| **Genuinely unspecified** | **3** |

The three are `ADM-CRM-05` (trial in progress · day N of 7), `ADM-POS-02` (inventory and
stock) and `MBR-33` (security and devices). Each has a registry identity and a one-line note
and no drawn screen anywhere in the folder; they are named in
`screens.generated.json → coverage.unspecified_ids` and nothing invents around them.

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
| `/members` | ADM-MEM-05 Members list | **built from the canvas**; its three absent columns and six absent controls are named on the screen |
| `/people/{id}` | ADM-MEM-01/02 Member 360 | **rebuilt to the canvas** — pattern 02, the status band, five MetricCells, the tabs, the timeline spine |
| `/schedule` | ADM-SCH-01 Class schedule · week grid | **built from the canvas** |
| `/schedule/{id}` | ADM-SCH-02 Class detail and roster | **rebuilt** — the band, four MetricCells, the roster; the three actions are stepped-up writes with no form |
| `/payments` | ADM-PAY-01 Payments ledger | **built from the canvas** — four kinds on one axis, signed; refund and export are named as absent |
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
| Genuinely unspecified (`ADM-CRM-05`, `ADM-POS-02`, `MBR-33`) | 3 |
| **Routes in `web/`** | **23** |
| Of those, built or rebuilt from their design | **11** |

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
| Account | `/account` | implemented, functionally tested. Now also the home of the session facts the old landing page printed, and of Sign out — §21 puts it in the account chrome |
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

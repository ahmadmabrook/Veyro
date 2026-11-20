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

**Still ad-hoc and not yet migrated**, tracked so the number can only go down: 31 raw
`<table>` elements across the boards (DataGrid exists and no screen uses it yet) and 67
`.panel` sections where `Card` applies. `tests/unit/ds-usage.test.mjs` is the sweep that
keeps that list honest in both directions.

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
| Four density modes | `DENSITY` | implemented, spec verified. The 44px button floor applies at Touch, Spacious and wherever the pointer is coarse. **No surface selects a mode yet**: `data-density` is honoured and nothing sets it per LAYOUTS (Front Desk Touch, Member Spacious, Console Compact). |
| Five breakpoints with declared per-surface behaviour | `BREAKPOINTS` | implemented, spec verified. Every media query in the app is asserted to sit on a breakpoint boundary. |
| Global chrome: scope switcher, ⌘K, tasks, alerts, account | §21 | partial. Account is a rail entry; language and theme are in the chrome slot. **Scope switcher, ⌘K and tasks/alerts are not built** — there is no scope concept on the client and no command palette. |
| Rail of eight, generated from role and scope | §21 | partial. The rail is generated from the gate per item, which is the role half; **the scope half does not exist** (every `permit` call is tenant-wide, which MOD-014 records as its own gap), so it renders every permitted section rather than a composed eight. A cut-off at eight would hide pages a reader can open. |
| Secondary nav capped at seven | §21 | — (no screen has a second level yet) |
| Light and dark themes | `THEMES` | implemented, spec verified |
| Arabic/English with RTL | `ARABIC_RULES` | implemented, spec verified |
| Contrast matrix | `CONTRAST` | implemented, spec verified |
| Numerals identical on screen and receipt | `ARABIC_RULES` | implemented, spec verified |

## Screens — 170

Tracked in `contracts/ui/screen-contracts.yaml` by identity. Every screen is `—` until its
authoritative specification has been read and its implementation matches. The fifteen that
exist are listed here as `implemented, functionally tested` and **not** design-compliant:

| Screen | Route | State |
| --- | --- | --- |
| Sign-in | `/login` | implemented, functionally tested |
| Step-up | `/step-up` | implemented, functionally tested |
| Account | `/account` | implemented, functionally tested |
| Overview | `/` | implemented, functionally tested |
| Organization | `/organization` | implemented, functionally tested |
| People / duplicates | `/people` | implemented, functionally tested |
| Member 360 | `/people/{id}` | implemented, functionally tested |
| Schedule board | `/schedule` | implemented, functionally tested |
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

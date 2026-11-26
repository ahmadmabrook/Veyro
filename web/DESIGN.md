---
name: Veyro Admin
description: Gym operations software with the confidence of a club identity programme — flat saturated fields, a bilingual lockup, and the quantity set like the number on the back of a shirt.
colors:
  bone-0: "#ffffff"
  bone-50: "#faf7fa"
  bone-100: "#f3eef3"
  bone-150: "#eae2ea"
  bone-200: "#ddd1dd"
  ink-900: "#110d11"
  ink-800: "#1e171e"
  ink-700: "#382c38"
  ink-600: "#544554"
  ink-500: "#6d5b6d"
  ink-400: "#998799"
  plum-950: "#1d071b"
  plum-900: "#2c0c29"
  plum-800: "#3e143b"
  plum-700: "#581d54"
  plum-600: "#72276c"
  plum-500: "#91338a"
  plum-400: "#b342aa"
  plum-300: "#d685d0"
  plum-200: "#ebb7e7"
  plum-100: "#f8e2f6"
  crimson-600: "#7c161d"
  crimson-500: "#a3212a"
  crimson-100: "#fae1e2"
  gold-600: "#855d00"
  gold-500: "#c98f05"
  gold-400: "#e8ab1f"
  gold-100: "#fbeec9"
  steel-600: "#1d6e8c"
  steel-100: "#dcecf3"
  turf-600: "#0e6845"
  turf-300: "#7fc9a9"
  turf-100: "#d6efe3"
  ai-600: "#3b49a0"
  ai-50: "#e8eaf7"
  aubergine-950: "#120f15"
  aubergine-900: "#1a161e"
  aubergine-800: "#26202c"
  aubergine-700: "#342c3c"
  mauve-200: "#dfd3e3"
  mauve-300: "#c3afca"
  crimson-light: "#e9838a"
  gold-light: "#f0bf52"
  steel-light: "#7fc0da"
  turf-light: "#7fc9a9"
  ai-light: "#a0a9e4"
typography:
  figure:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "72px"
    fontWeight: 700
    lineHeight: 0.9
    letterSpacing: "-0.035em"
  figure-sm:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "44px"
    fontWeight: 700
    lineHeight: 0.95
    letterSpacing: "-0.03em"
  display:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "40px"
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: "-0.025em"
  h1:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "28px"
    fontWeight: 700
    lineHeight: 1.14
    letterSpacing: "-0.02em"
  h2:
    fontFamily: "Barlow, system-ui, sans-serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.012em"
  body:
    fontFamily: "Barlow, system-ui, sans-serif"
    fontSize: "14.5px"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "0em"
  label:
    fontFamily: "Barlow, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "0.02em"
  data:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "13.5px"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "0em"
  arabic-body:
    fontFamily: "Cairo, system-ui, sans-serif"
    fontSize: "14.5px"
    fontWeight: 400
    lineHeight: 1.75
    letterSpacing: "0em"
rounded:
  card: "2px"
  button: "6px"
spacing:
  "05": "2px"
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "20px"
  "6": "24px"
  "8": "32px"
  "10": "40px"
  "12": "48px"
  "16": "64px"
components:
  button-primary:
    backgroundColor: "{colors.ink-900}"
    textColor: "{colors.bone-0}"
    rounded: "{rounded.button}"
    padding: "8px 16px"
  button-primary-pressed:
    backgroundColor: "{colors.ink-700}"
    textColor: "{colors.bone-0}"
    rounded: "{rounded.button}"
  rail:
    backgroundColor: "{colors.plum-800}"
    textColor: "{colors.bone-50}"
    width: "240px"
  rail-item-current:
    backgroundColor: "{colors.plum-600}"
    textColor: "{colors.bone-0}"
    padding: "7px 16px"
  badge-critical:
    backgroundColor: "{colors.crimson-500}"
    textColor: "{colors.bone-0}"
    rounded: "{rounded.card}"
    padding: "2px 8px"
  badge-attention:
    backgroundColor: "{colors.gold-400}"
    textColor: "{colors.ink-900}"
    rounded: "{rounded.card}"
    padding: "2px 8px"
  badge-info:
    backgroundColor: "{colors.steel-600}"
    textColor: "{colors.bone-0}"
    rounded: "{rounded.card}"
    padding: "2px 8px"
  badge-neutral:
    backgroundColor: "{colors.bone-50}"
    textColor: "{colors.ink-600}"
    rounded: "{rounded.card}"
    padding: "2px 8px"
---

# Veyro Admin — design system

## Overview

Veyro is multi-tenant gym management software. The people who open it are a gym owner wanting
to know whether the business is healthy, a club manager answering the day's exceptions, and a
receptionist standing at a counter with a member mid-sentence. The surface is **Operate**: the
reader is completing a task, so scanability, consistency and standard controls outrank
expression, and the brand lives in precise details rather than in ornament.

The world is the graphic tradition of Levantine football-club identity: flat fully-saturated
colour used as whole fields rather than accents, a bilingual lockup that sets Arabic and Latin
as equals, and the numeral on the back of a shirt. It lends this product **four things and
only four — type, palette, density, and one signature move.** It does not lend the layout, the
navigation model or the controls, which stay standard web components. There is no crest, no
stripe, no mascot and no shirt texture: those are the costume, and the grammar is what ships.

**The signature move is the monumental numeral.** Every quantity the operator reads first is
set in Archivo on a baseline, with its unit and its provenance beneath it in text, never
inside a bordered tile. A figure is the content, not an ornament on it, and a border around a
number is a substitute for having decided that it matters.

**Two registers, and which one applies is arithmetic rather than taste.** `type.figure` (72px)
is for a surface that leads with *one* figure. A row of four peers sits at `type.figureSm`
(44px), because the Admin content area at 1440 is 1152px and four columns come out at 264 --
and "JOD 41,280.00" at 72px is about 515px wide. Four monumental figures do not fit across
that row. 44px against 14.5px body is still a 3x step, and twice the 21px the retired row
used. A hero figure at 72 with three secondary beneath it is the better composition and is
recorded as the next step rather than claimed here.

This replaced a direction of warm paper, hairline rules and monospace numerals. The product
truth it was built on is unchanged — see `PRODUCT.md` — and the direction contract, its
weighing and its honest risk are in `.impeccable/surfaces/admin.md`.

**The system is generated, not transcribed.** `src/design/ds.json` is the authority;
`src/design/generate.mjs` emits `tokens.generated.css` and `tokens.generated.mjs`, and
`npm run tokens:check` fails CI on a hand-edit. The generator refuses to ship a semantic token
with no dark value, which is how seven silently-light dark tokens were once found.

## Colors

Three layers. **Layer 1** is the primitive ramps above, `--p-*` in CSS. **Layer 2** is the
semantic tokens every component consumes, `--color-*`. A theme is a remapping of layer 2 onto
layer 1, never a rewrite of layer 1 — so a component that reaches for a `--p-*` directly
breaks theming, and `npm run design:check` refuses one.

**Colour does real jobs and nothing else.** A grey screen with one accent is the category
default without the category's polish, not restraint — so the shell is a committed field. But
colour is also quarantined: it appears only inside a region doing a job, never scattered as
decoration.

| Job | Light | Dark |
| --- | --- | --- |
| Shell field (rail and chrome) | `plum-800` | `aubergine-950` |
| Working ground | `bone-100` | `aubergine-900` |
| Panels and table bodies | `bone-0` | `aubergine-800` — **#26202C** |
| Primary action | `plum-500` — **#91338A** | `plum-400` |
| Money category | `gold-400` | `gold-light` |
| Compliance category | `steel-600` | `steel-light` |
| Retention category | `crimson-500` | `crimson-light` |
| Staffing category | `turf-600` | `turf-light` |

**The action colour is the primary, and guardrail G2 is what makes that possible.** G2
requires the action to sit a perceptual distance from success, warning and error. The retired
palette put the shell field and the success state on the same green, so an action in that
family would have made "you may press this" and "this succeeded" the same signal -- which is
why the action had to be ink, a colour with no hue at all. #91338A shares a hue with nothing
here: 51 degrees from error, 73 from AI, 97 from warning, 108 from info, 148 from success. So
the shell field and the one pressable thing on the page are the same colour, which is what the
brief asked for and what the old palette could not have given. A disabled action loses it.

**Green survives in exactly one job: success.** It is a status rather than an identity -- a
paid invoice rendered in the brand colour would be a state the eye reads as a highlight -- so
`turf` carries success and the staffing category and nothing else.

**Every text token clears AA on all three light grounds**, including the darkest — the CONTRAST
table in `ds.json` publishes the measured ratio per token per surface and
`tests/unit/contrast.test.mjs` recomputes all thirty-six from the hexes. There is no excluded
pairing and no documented discrepancy. `ink-400` is the one entry that fails, declared for
disabled controls and decoration only; placeholders use `ink-500`.

Two surfaces the published table cannot cover are checked separately, because both are
composited or saturated: the translucent selected row in each theme, and the shell field. The
field check caught a real failure — the current rail item first took `color.text.inverse`,
which was near-black in dark, giving **1.94:1** on the selected ground. The action fill is a
plum in both themes now, so `color.text.inverse` is bone in both and that particular
demonstration no longer runs -- the hazard is still in the dark ramp, where its own darkest
member on its own selected ground is 1.42:1, and the test asserts it there.

**Light is primary; dark is a true theme.** A back office with the lights on, read for hours;
dark for early and late work, where the ground is **#26202C** rather than a neutral black --
the owner's own dark primary, placed on the panels and table bodies that cover most of a dark
screen rather than on one accent. The canvas beneath it and the rail above it are the same
family, so the dark theme is one colour scheme rather than a second theme that happens to
coexist with the first.

## Typography

Three self-hosted faces, loaded by `next/font` at build time. **Archivo** sets every quantity —
the signature move needs a grotesque with flat, confident figures that hold at 72px and still
align in a table at 13.5. **Barlow** sets Latin text, a workhorse with the slightly condensed
set width a dense operations screen wants. **Cairo** sets Arabic, a Kufi-influenced grotesque
that sits beside both without a seam and is credible in this product's own region.

**There is no monospace.** The retired system set every figure in a mono face; monospace is for
code, not for "technical", and tabular alignment is `font-variant-numeric: tabular-nums`, which
both faces ship. `design:check` refuses a monospace family anywhere in the system.

**There is no eyebrow register.** A small tracked label above a heading is a kicker, which is
banned outright. Where a figure has a unit and a period, that label sits *beneath* the figure,
because the figure is the heading and the label is what it is of.

Arabic is not a translation layer. At any size it takes +0.15 line-height, never takes
tracking (which breaks the joins), steps emphasis weights up one (Cairo reads optically
lighter), floors at 13px, and has no italic path. Containers are dimensioned against the
Arabic string, which runs 15–30% longer. `src/design/type.mjs` resolves a token per script and
`tests/unit/type.test.mjs` asserts each rule.

## Layout

A 12-column grid, 24px gutter, content capped at 1440 and centred. The rail is 240 expanded
and 56 collapsed; an inspector is 380 at bp.lg and 480 at bp.xl. Split view is list plus
inspector, never three columns.

Five breakpoints. At bp.xs the surface collapses to the single next decision with its figure
monumental: the metric row stacks, figures drop to the 44px register, tables become
drill-down lists rather than shrunken grids, and the rail becomes one bottom strip that
scrolls inside itself rather than widening the page.

Four density modes change three things and nothing else — row height, spacing step and type
step. Compact (34px rows) is for grids where scanning is the job; Touch (48px, 44px targets)
is the front desk and is never user-selectable there.

**Columns never move.** Data changes inside a stable grid, a row that reranks keeps its
identity, and a row that changed holds its marker until it has been seen. A layout that
reflows under new data is a layout the operator has to re-read.

## Elevation & Depth

**Flat. Screenprint, not glass.** No gradient, no blur, no glow, no coloured halo. Depth comes
from a solid field and a 2px rule in ink (`--shell-rule`, `--color-border-strong`), not from a
shadow. The one shadow in the system belongs to an overlay and carries a real offset and blur;
a zero-offset coloured halo is decoration, not depth.

The field is what separates the shell from the content: the rail and the chrome are one
saturated colour and need no border against the canvas.

## Shapes

Sharp where the data is, rounded where the hand is. `rounded.card` is 2px — containers, badges
and anything that is a label. `rounded.button` is 6px, for anything pressable. A badge takes
the card radius deliberately: it is a label, not something to press.

Rules are 2px and in ink, not hairlines. A group of figures is closed by one rule beneath it;
a list of rows is bounded top and bottom by one and divided inside it.

The focus ring is system-owned in both themes (guardrail G4, non-configurable): 2px with a
2px offset, so it survives on a filled action where a ring in the action's own colour would
vanish.

## Components

- **Rail.** The committed field. Navigation grouped by what the operator is trying to do, with
  the current item marked by a tint and a weight — never by a bar down one side. Group
  headings are tinted from the field's own hue rather than grey, which is what a coloured
  surface requires.
- **MetricCell / MetricRow.** The signature move, at the four-up register (see Typography).
  Figures share a baseline in the open, separated by space, closed by a rule. No tile, no
  kicker, no severity: "48 people in the building is a fact, not a problem." Three states —
  live, stale, unavailable — and an unavailable figure carries a reason in the operator's
  language where the number would be, never a zero or an em-dash.
- **AttentionRow / AttentionQueue.** The reason the Command Center exists. Rows in a bounded
  list, each led by a solid category field naming its kind in words, the amount at the logical
  end, and one standard link to the record. Severity is the field *and* the word *and* the
  headline, never colour alone.
- **StatusBadge.** A closed vocabulary over four severities, each a solid field. Neutral is
  not a colour event — "'success' is not a severity, it is the neutral case" — so it stays a
  quiet ground with a full border. The label names the state in the reader's language; the
  enum is never the label.
- **DataGrid.** Columns drop by priority as width shrinks; a droppable value is in the DOM
  twice and visible exactly once at any width. Money and numeric columns end-align on the
  logical end so they mirror.
- **Button.** Ink fill for primary, and it is the only solid ink block on a page. An `href`
  renders a real anchor, so the base style neutralises the user-agent underline: a link styled
  as a button, or the inverse, is a defect.

## Motion

One authored moment per surface, not an entrance on every section. On Admin it is the queue: a
row that reranks travels to its new position and keeps its identity while it goes. Everything
animates from an already-visible default — content never fades in from nothing, because a page
that assembles itself is a page the operator waits for. 120ms for a control's own feedback,
200ms for a surface change, 320ms for a row travelling, and nothing slower on a working
screen. Under `prefers-reduced-motion` travel and cross-fades go and state changes are
instant; nothing is lost, because a change marker is always a colour and a rule rather than
only a movement.

## Do's and Don'ts

**Do**

- Set the quantity the reader came for at the top of the scale, on a baseline, with its unit
  beneath it.
- Commit colour as a field. The shell is saturated; a category is a solid block.
- Keep colour inside a region that is doing a job, and keep the action colour for what can be
  acted on.
- State what the product does not know, in one line, in the operator's own language, where the
  figure would have been.
- Theme the browser's own surfaces — selection, caret, scrollbar, focus ring, tabular figures.
  It is the cheapest signal a page was built rather than assembled.
- Measure a new colour pairing before shipping it, and add it to CONTRAST if a reader will see
  text on it.

**Don't**

- Put a kicker above a heading. The heading carries its own weight.
- Draw a bar down one side of a rounded box, in any colour or for any state. Use a full
  border, a tint, or a leading label.
- Box a figure. A border around a number is a substitute for deciding it matters.
- Use monospace for "technical". It is for code; alignment is a font feature.
- Reach for a `--p-*` primitive from a component, or invent a length outside the spacing
  scale.
- Put a module id, a table name, a UUID or a gap note written for an engineer on an operator's
  screen. Those records belong in the repository.
- Render a control that would answer 403. Offer the step-up it needs, or show the state and no
  control.

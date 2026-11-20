#!/usr/bin/env node
/**
 * Extract the authoritative design contracts from `veyro-product-experience-design/`.
 *
 * **`ds.json` was never the design system, and treating it as one is the defect this file
 * exists to close.** It carries Step 2 — colour, type, density, breakpoints, Arabic rules,
 * contrast, guardrails — and nothing from Step 3 (37 component families with APIs, a state
 * matrix and three contracts each), Step 4 (nine domain families), or Step 5 (ten patterns,
 * four confirmation tiers, fourteen cross-cutting requirements). Fifteen screens were built
 * against the foundations alone and every one of them invented its own components.
 *
 * The source files are HTML documents that render their tables from JavaScript arrays. The
 * prose lives in the markup and the contracts live in those arrays, so the extractor runs the
 * declarations in a sandbox and reads the constants out rather than scraping rendered text —
 * a regex over the markup would capture the `{{ m.c0 }}` placeholders, not the values.
 *
 * **Every source file is pinned by SHA-256.** `--check` re-extracts and compares, so a design
 * file that changes under us fails the build rather than silently redefining what compliance
 * means; the same trade as `tokens:check` and the backend's definition pins. A legitimate
 * design revision fails until it is re-extracted, which is the moment a human reads the diff.
 *
 *     node src/design/extract.mjs          # write contracts.json
 *     node src/design/extract.mjs --check  # fail if it is stale
 */
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createContext, runInContext } from "node:vm";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "../../..");
const SOURCE = join(REPO, "veyro-product-experience-design", "project");
const OUT = join(HERE, "contracts.json");

/**
 * Which arrays to take from which file.
 *
 * Named explicitly rather than "every const in the file", because a file that gains an array
 * we do not understand should be a visible failure rather than a silent new key — and because
 * the names are part of the pin: a renamed array is a changed contract.
 */
const SOURCES = [
  {
    file: "Veyro DS Core Components.dc.html",
    step: "Step 3 — core components",
    arrays: {
      GRID_STATES: ["state", "treatment"],
      OVERLAYS: ["name", "when", "rules"],
      MATRIX: [
        "family", "default", "hover", "active", "selected", "focus", "disabled",
        "loading", "error", "warning", "empty", "readonly",
      ],
      CONTRACTS: ["family", "accessibility", "rtl", "responsive"],
      DOCS: ["section", "requirement"],
    },
  },
  {
    file: "Veyro DS Patterns.dc.html",
    step: "Step 5 — patterns",
    arrays: {
      PATTERNS: ["number", "name", "components", "rule"],
      TIERS: ["tier", "mechanism", "applies_to", "why"],
      CROSS: ["requirement", "rule", "where"],
      PLATFORM: ["concern", "web", "ios", "android"],
    },
  },
  {
    file: "Veyro DS Domain Components.dc.html",
    step: "Step 4 — domain components",
    arrays: {
      PAY_STATES: ["state", "severity", "copy"],
      FAMILIES: ["name", "anatomy", "decision"],
      JORDAN: ["system", "state", "copy"],
    },
  },
  {
    file: "Veyro DS Foundations.dc.html",
    step: "Step 2 — foundations",
    arrays: {
      CHARACTER: null,
      SEMANTIC: null,
      THEMES: null,
      TYPE_SCALE: null,
      ARABIC_RULES: null,
      CONTRAST: null,
      DENSITY: ["mode", "row_and_control", "type_step"],
      BREAKPOINTS: ["name", "range", "behaviour"],
      LAYOUTS: ["surface", "specification"],
      BRANDABLE: null,
      GUARDRAILS: null,
    },
  },
];

/**
 * The taxonomy, which is prose in the source and a closed set everywhere else.
 *
 * Taken from §67 verbatim. It is here rather than scraped because the markup renders it as a
 * single dot-separated run of text, and a split on "·" would be a parser that silently
 * succeeds when the separator changes.
 */
const TAXONOMY = {
  primitive: [
    "Button", "IconButton", "Input", "Select", "Combobox", "Checkbox", "Radio", "Switch",
    "Textarea", "Chip", "Badge", "Avatar", "Icon", "Tooltip", "Divider", "Skeleton", "Spinner",
  ],
  composite: [
    "DataGrid", "FilterBar", "SavedViewBar", "BulkActionBar", "SearchField", "CommandPalette",
    "Modal", "Drawer", "Sheet", "Tabs", "SegmentedControl", "Card", "Banner", "Toast",
  ],
  dateTime: [
    "Calendar", "DatePicker", "DateRangePicker", "TimePicker", "WeekView", "DayView",
  ],
};

/**
 * Component APIs stated in the source as code blocks rather than as data.
 *
 * §22's Button API is the only one written out in full; the rest of each family's API is
 * implied by its anatomy and its state matrix row. Recorded here so the implementation has a
 * single place to answer "what does the source actually say", and marked so nothing reads an
 * absence as permission to invent one.
 */
const STATED_APIS = {
  Button: {
    variant: ["primary", "secondary", "tertiary", "ghost", "destructive", "icon", "link"],
    size: ["sm", "md", "lg"],
    state: ["default", "loading", "disabled"],
    icon: "IconName?",
    iconSide: ["start", "end"],
    label: "string (required, verb-first)",
    fullWidth: "boolean?",
    sizes_px: { sm: 28, md: 36, lg: 44 },
    rules: [
      "lg (44px) is mandatory in Touch and Spacious density -- the minimum target, not a style.",
      "sm is Compact-only and never appears on Coach, Member, Front Desk or Kiosk.",
      "One primary per view. Not per card, per view.",
      "Destructive is never adjacent to primary.",
      "Label is verb first, object second, no gerunds. Amounts belong in destructive and "
        + "financial labels so the confirm reads the consequence.",
    ],
  },
  Input: {
    field_types: [
      "text", "number", "currency", "phone", "email", "password", "search", "textarea",
      "select", "multiselect", "combobox", "autocomplete", "date", "time", "daterange",
      "stepper", "slider", "switch",
    ],
    shell: ["label", "control", "description", "message", "prefix", "suffix", "contextual action"],
    rules: [
      "One shell for all eighteen field types; a new type is a control swap, not a component.",
      "The message slot holds exactly one message: error > warning > success > description.",
      "Validate on blur, never on keystroke; re-validate on submit.",
      "Required is marked, optional is not -- whichever is rarer gets the mark.",
      "Financial forms state the consequence above the submit, not in a dialog after it.",
    ],
  },
  StatusBadge: {
    severity: ["neutral", "info", "attention", "critical"],
    vocabularies: {
      membership: ["Active", "Trial", "Frozen", "Expiring", "Expired", "Cancelled"],
      payment: ["Paid", "Pending", "Failed", "Refunded", "Partially refunded"],
      booking: ["Confirmed", "Waitlisted", "Cancelled", "No-show"],
      access: ["Granted", "Denied", "Restricted"],
    },
    rules: [
      "Four severities, not five: success is not a severity, it is the neutral case.",
      "The component takes an enum, not a string, so an engineer cannot invent a status.",
      "Never colour alone -- every badge carries its label; icon-only status is a defect.",
      "The edge-mark carries the row-level roll-up; the badge names the specific state.",
    ],
  },
};

/** Mistakes the source carries as a checklist, so a lint rule can read them from one place. */
const COMMON_MISTAKES = [
  "Two primaries in one view",
  "A status rendered by colour alone",
  "A shadow on a table row",
  "A dialog on a one-step-undoable action",
  "A disabled control a role can never enable",
  "Icon-only tabs",
  "A bare number with no money kind",
  "Tracking applied to Arabic",
  "A bulk action reporting “done”",
];

function sandboxConstants(file, wanted) {
  const html = readFileSync(join(SOURCE, file), "utf8");
  const scripts = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi)].map((m) => m[1]);
  const body = scripts.sort((a, b) => b.length - a.length)[0] ?? "";
  // Everything before the class declaration is the data. Running the class would need the
  // document's own framework, which is not here and is not what we want.
  const declarations = body.slice(0, body.indexOf("class Component"));
  // **A trailing object literal, not a read of the context afterwards.** `const` is lexical,
  // so the declarations never become properties of the sandbox's global object and reading
  // them back gives `undefined` for every one -- which the first version reported as "the
  // source shape changed" while the source was fine.
  const names = Object.keys(wanted);
  const expression = `${declarations}\n;({ ${names.join(", ")} })`;
  const context = createContext({});
  const evaluated = runInContext(expression, context, { timeout: 5_000 });
  const out = {};
  for (const name of names) {
    const value = evaluated[name];
    if (!Array.isArray(value)) {
      throw new Error(`${file}: ${name} is not an array -- the source shape changed`);
    }
    out[name] = value;
  }
  return { html, rows: out };
}

function named(rows, keys) {
  if (keys === null) return rows;
  return rows.map((row) => Object.fromEntries(keys.map((k, i) => [k, row[i]])));
}

function extract() {
  const contracts = {
    manifest: "veyro-design-contracts",
    note:
      "Extracted from the authoritative design source. Generated; do not edit by hand. "
      + "Regenerate with: npm run design:extract",
    authority:
      "veyro-product-experience-design/ is the single authoritative source for frontend "
      + "design. ds.json carries Step 2 only; this file carries Steps 3, 4 and 5.",
    sources: [],
    taxonomy: TAXONOMY,
    stated_apis: STATED_APIS,
    common_mistakes: COMMON_MISTAKES,
  };

  for (const { file, step, arrays } of SOURCES) {
    const { html, rows } = sandboxConstants(file, arrays);
    contracts.sources.push({
      file: `veyro-product-experience-design/project/${file}`,
      step,
      sha256: createHash("sha256").update(readFileSync(join(SOURCE, file))).digest("hex"),
      bytes: html.length,
    });
    for (const [name, keys] of Object.entries(arrays)) {
      const key = name.toLowerCase();
      if (key in contracts) throw new Error(`duplicate contract key: ${key}`);
      contracts[key] = named(rows[name], keys);
    }
  }

  // The family count the source states, checked rather than copied.
  const families =
    TAXONOMY.primitive.length + TAXONOMY.composite.length + TAXONOMY.dateTime.length;
  if (families !== 37) {
    throw new Error(`taxonomy holds ${families} families; the source states 37`);
  }
  contracts.family_count = families;
  return contracts;
}

/**
 * The small module components import, generated from the same extraction.
 *
 * **`contracts.json` is 60KB and most of it is prose.** A component importing it would carry
 * every contract sentence into the browser bundle to read one severity. This emits only the
 * values the component layer needs, with the same provenance — so `StatusBadge`'s severity map
 * is the design source's own column rather than a developer's reading of §30, which is how the
 * first version came to be missing five payment states the source states outright.
 */
function buildModule(contracts) {
  // **Two payment lists exist in the source and they are not the same length.** §30's
  // "Payment" vocabulary names five states; Step 4's PAY_STATES names ten, each with its own
  // severity column — Retrying, Overdue, Disputed, Cash pending and Wallet applied are only
  // in the second. The §30 list is a subset, so the union is the vocabulary and PAY_STATES is
  // the authority on severity. The check below fails if that stops being true.
  const payment = contracts.pay_states.map((p) => p.state);
  const fromSection30 = ["Paid", "Pending", "Failed", "Refunded", "Partially refunded"];
  for (const state of fromSection30) {
    if (!payment.includes(state)) {
      throw new Error(`§30 names payment state "${state}" and PAY_STATES does not`);
    }
  }

  const severity = {};
  for (const row of contracts.pay_states) severity[row.state] = row.severity;
  // The other three vocabularies carry no severity column in the source, so each is mapped
  // from §30's own four definitions: neutral is "a fact" (Active, Confirmed, Granted);
  // info is "worth knowing, no action" (Trial, Waitlisted); attention is "needs a human soon"
  // (Expiring, Frozen, Restricted, and a No-show, which is a person a human will ask about);
  // critical is "blocking or losing money" (Expired, Denied). Cancelled is a fact about a
  // record that is over, which is the neutral case.
  Object.assign(severity, {
    Active: "neutral", Trial: "info", Frozen: "attention", Expiring: "attention",
    Expired: "critical", Cancelled: "neutral",
    Confirmed: "neutral", Waitlisted: "info", "No-show": "attention",
    Granted: "neutral", Denied: "critical", Restricted: "attention",
  });

  const vocabulary = {
    membership: ["Active", "Trial", "Frozen", "Expiring", "Expired", "Cancelled"],
    payment,
    booking: ["Confirmed", "Waitlisted", "Cancelled", "No-show"],
    access: ["Granted", "Denied", "Restricted"],
  };
  for (const [domain, states] of Object.entries(vocabulary)) {
    for (const state of states) {
      if (!severity[state]) throw new Error(`${domain}: "${state}" has no severity`);
    }
  }

  return (
    "// GENERATED by src/design/extract.mjs. Do not edit; run `npm run design:extract`.\n"
    + "//\n"
    + "// The subset of the design contracts the component layer consumes. The full extraction,\n"
    + "// including every contract sentence and the source digests, is in contracts.json.\n\n"
    + `export const VOCABULARY = ${JSON.stringify(vocabulary, null, 2)} as const;\n\n`
    + `export const SEVERITY: Record<string, "neutral" | "info" | "attention" | "critical"> =\n`
    + `  ${JSON.stringify(severity, null, 2)};\n\n`
    + "/** Payment states carry a copy rule each; the component shows the label and a surface\n"
    + " * renders the rest. Kept so a page can look up what the source says to say. */\n"
    + `export const PAYMENT_COPY: Record<string, string> = ${JSON.stringify(
      Object.fromEntries(contracts.pay_states.map((p) => [p.state, p.copy])), null, 2)};\n\n`
    + `export const BUTTON_SIZES = ${JSON.stringify(contracts.stated_apis.Button.sizes_px)} as const;\n\n`
    + `export const BUTTON_VARIANTS = ${JSON.stringify(contracts.stated_apis.Button.variant)} as const;\n`
  );
}

const want = extract();
const serialised = `${JSON.stringify(want, null, 2)}\n`;
const generatedModule = buildModule(want);
const MODULE_OUT = join(HERE, "contracts.generated.ts");

if (process.argv.includes("--check")) {
  let current = "";
  try {
    current = readFileSync(OUT, "utf8");
  } catch {
    console.error("contracts.json is missing. Run: npm run design:extract");
    process.exit(1);
  }
  if (current !== serialised) {
    console.error(
      "STALE: contracts.json disagrees with the design source.\n"
      + "Either the design files changed or the file was edited by hand. "
      + "Run: npm run design:extract, and read the diff.",
    );
    process.exit(1);
  }
  let currentModule = "";
  try {
    currentModule = readFileSync(MODULE_OUT, "utf8");
  } catch {
    console.error("contracts.generated.ts is missing. Run: npm run design:extract");
    process.exit(1);
  }
  if (currentModule !== generatedModule) {
    console.error("STALE: contracts.generated.ts disagrees. Run: npm run design:extract");
    process.exit(1);
  }
  console.log(`design:check ok -- ${want.sources.length} source files, ${want.family_count} families`);
} else {
  writeFileSync(OUT, serialised);
  writeFileSync(MODULE_OUT, generatedModule);
  console.log(`wrote ${OUT}`);
  console.log(`wrote ${MODULE_OUT}`);
  for (const s of want.sources) console.log(`  ${s.sha256.slice(0, 12)}  ${s.file}`);
}

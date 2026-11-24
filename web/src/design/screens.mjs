#!/usr/bin/env node
/**
 * Extract the screen specifications from `veyro-product-experience-design/`.
 *
 * **The design folder specifies 167 of the 178 V1 screens, and the first version of this
 * file found 37.** That gap is the reason fifteen screens in `web/` were composed from
 * whatever a backend module's routes could answer, and it had one cause: the section
 * boundary was matched inside a single CSS signature,
 *
 *     /letter-spacing:\.1em">([^<]{4,300})<\/div>/
 *
 * which exists in nine of the forty-eight design documents. Every `HF` file -- where the
 * Command Center, the Member 360, the Front Desk, the POS, the Coach surface and the Member
 * app are drawn at high fidelity -- and every `V1 Batch M` through `Q` file -- which each
 * announce "12 SCREENS DRAWN" in their own header -- were read as containing no screens at
 * all. The eyebrow in those files is set at `.07em`, `.08em` or `.09em`.
 *
 * So the boundary here is the *text*, not its styling: a run that begins with one or more
 * screen ids followed by a middot. That is how every document in the folder titles a screen,
 * and it is stable across the four generations of document in there.
 *
 * ## Two kinds of section, because the folder has two kinds of document
 *
 * **Screen sections.** `V1 Batch *` and `V1 Admin *` title each screen with its own id:
 *
 *     FD-03 · ACCESS DENIED · WHAT TO SAY AND DO
 *     POS-03 · SPLIT PAYMENT · MID-FLOW
 *     ADM-MEM-05 · MEMBERS LIST · CM, RECEP · COMPACT · 1440
 *
 * **Canvas sections.** The `HF` files title by role and state instead, because one screen is
 * drawn five times:
 *
 *     CANVAS 1 · OWNER · ALL LOCATIONS · NORMAL OPERATIONAL DAY · 1440×900
 *     CANVAS 4 & 5 · THE QUIET DAY, AND DEGRADED DATA
 *
 * The id lives in the registry instead, whose `note` field names the file and the canvas:
 * `ADM-CC-01` is "HF Command Center c1". `CANVAS_OF` resolves those note prefixes to files,
 * and **a note that does not resolve fails the extraction** rather than dropping the screen
 * silently -- which is the failure this file exists to correct, so it is checked in both
 * directions: every note resolves to a file that exists, and every file named is used.
 *
 * ## What it writes
 *
 * `screens.generated.json`: one entry per V1 screen, carrying the registry's own identity
 * (module, name, roles, Arabic state) and every design section that specifies it, with the
 * file each came from. A screen being built has its specification at hand and the compliance
 * ledger can cite it. Every source is pinned by SHA-256 and `--check` fails on a stale
 * extraction, like the component contracts.
 *
 *     node src/design/screens.mjs          # write screens.generated.json
 *     node src/design/screens.mjs --check  # fail if it is stale
 */
import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = resolve(HERE, "../../../veyro-product-experience-design/project");
const OUT = join(HERE, "screens.generated.json");
const REGISTRY = join(SOURCE, "veyro-registry-data.js");

/**
 * A screen id: `FD-03`, `MBR-23`, `ADM-MEM-05`. Two shapes, because the admin surface is
 * subdivided by module and the other four are not.
 */
const ID = /\b([A-Z]{2,5}-(?:[A-Z]{2,6}-)?\d{1,3})\b/g;

/** A section title: one or more ids, middot, then what the section is. */
const SCREEN_SECTION =
  /^((?:[A-Z]{2,5}-(?:[A-Z]{2,6}-)?\d{1,3})(?:\s*·\s*(?:[A-Z]{2,5}-(?:[A-Z]{2,6}-)?\d{1,3}))*)\s*·\s*(.{3,180})$/;

/** `CANVAS 1 · …`, `CANVAS 4 & 5 · …`, `CANVAS 2, 3 & 4 · …`. */
const CANVAS_SECTION = /^CANVAS\s+([\d\s,&]+?)\s*·\s*(.{3,180})$/i;

/**
 * The registry's `note` prefixes for the **high-fidelity** documents, resolved to the file
 * each names, and asserted in both directions below so a new note cannot resolve to nothing.
 *
 * Only the `HF` files need this. The `V1 Batch *` and `V1 Admin *` documents title each
 * screen with its own id, so their screens resolve as screen sections and their notes
 * ("V1 Admin Members c1 · 34px rows, saved views, bulk bar") are prose about where in the
 * batch the canvas sits rather than the only handle on it. Listing them here was the first
 * version's mistake and the both-direction check is what said so.
 */
const CANVAS_OF = {
  "HF Command Center": "Veyro HF Command Center.dc.html",
  "HF Member 360": "Veyro HF Member 360.dc.html",
  "HF CRM and Console": "Veyro HF CRM and Console.dc.html",
  "HF Remaining Modules": "Veyro HF Remaining Modules.dc.html",
  "HF Front Desk and POS": "Veyro HF Front Desk and POS.dc.html",
  "HF Coach": "Veyro HF Coach.dc.html",
  "HF Member App": "Veyro HF Member App.dc.html",
};

/**
 * The Arabic RTL builds. They are canvases in Arabic rather than screen sections, and the
 * registry's `ar` column says per screen whether one exists -- so they are carried per file
 * and a screen's Arabic reference is the file for its surface. `ARABIC_RULES` in the
 * foundations governs the behaviour; these are the drawn references for it.
 */
const ARABIC_OF = {
  "Veyro HF Command Center AR.dc.html": ["ADM-CC"],
  "Veyro HF Member 360 AR.dc.html": ["ADM-MEM"],
  "Veyro HF Coach and Member AR.dc.html": ["CCH", "MBR"],
  "Veyro HF Front Desk and POS AR.dc.html": ["FD", "POS"],
};

function unescape(text) {
  return text
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&rsquo;/g, "’")
    .replace(/&mdash;/g, "—")
    .replace(/&times;/g, "×");
}

/**
 * The readable lines of a document, in order, each with the offset it started at.
 *
 * The template placeholders are left visible: `{{ t.title }}` in a repeated row says the
 * design specifies a list whose items share a shape, which is information a reader of the
 * specification needs. Scripts, styles and the font preamble are dropped.
 */
function lines(markup) {
  const cleaned = markup
    .replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1>/gi, (m) => " ".repeat(m.length))
    .replace(/<helmet[\s\S]*?<\/helmet>/gi, (m) => " ".repeat(m.length));
  const out = [];
  // Offsets are preserved by replacing tags with an equal run of newlines, so a section's
  // body can be sliced out of the original text by the offset of the next section's title.
  let at = 0;
  for (const part of cleaned.split(/(<[^>]+>)/)) {
    if (!part.startsWith("<")) {
      const text = unescape(part).replace(/\s+/g, " ").trim();
      if (text) out.push({ text, at });
    }
    at += part.length;
  }
  return out;
}

/** A section's body: every readable line from its title to the next section's. */
function body(all, from, to) {
  return all
    .filter((line) => line.at >= from && line.at < to)
    .map((line) => line.text)
    .join("\n");
}

function readRegistry() {
  const source = readFileSync(REGISTRY, "utf8");
  const rows = [
    ...source.matchAll(
      /^\['([^']*)','([^']*)','([^']*)','([^']*)','([^']*)','([^']*)','([^']*)','([^']*)'\],?\s*$/gm,
    ),
  ];
  if (rows.length < 150) {
    throw new Error(`the registry parsed to ${rows.length} rows, which cannot be right`);
  }
  return rows.map((r) => ({
    id: r[1],
    module: r[2],
    name: r[3],
    phase: r[4],
    status: r[5],
    roles: r[6],
    arabic: r[7],
    note: r[8],
  }));
}

/** The surface a screen belongs to, derived from its id as the registry's header says. */
function surfaceOf(id) {
  if (id.startsWith("ADM-POS")) return "POS admin";
  if (id.startsWith("ADM-")) return "Admin";
  if (id.startsWith("MBR-")) return "Member";
  if (id.startsWith("FD-")) return "Front desk";
  if (id.startsWith("POS-")) return "POS";
  if (id.startsWith("CCH-")) return "Coach";
  if (id.startsWith("CON-")) return "Console";
  if (id.startsWith("SYS-")) return "System";
  return "Unknown";
}

function extract() {
  const registry = readRegistry();

  // Every note prefix resolves to a file that exists. A note naming a file that is not there
  // is the silent-drop this extraction exists to prevent, so it is an error.
  for (const [prefix, file] of Object.entries(CANVAS_OF)) {
    if (!existsSync(join(SOURCE, file))) {
      throw new Error(`CANVAS_OF["${prefix}"] names ${file}, which is not in the design folder`);
    }
  }
  for (const file of Object.keys(ARABIC_OF)) {
    if (!existsSync(join(SOURCE, file))) {
      throw new Error(`ARABIC_OF names ${file}, which is not in the design folder`);
    }
  }

  const sections = [];
  const sources = [];
  const usedPrefixes = new Set();

  for (const name of readdirSync(SOURCE).sort()) {
    if (!name.endsWith(".dc.html")) continue;
    const raw = readFileSync(join(SOURCE, name));
    const all = lines(raw.toString("utf8"));
    const file = `veyro-product-experience-design/project/${name}`;

    const marks = [];
    for (const line of all) {
      const screen = SCREEN_SECTION.exec(line.text);
      if (screen) {
        // **Every `·`-separated segment that is exactly an id**, not only the ones before the
        // first label. Batch F titles one card `ADM-CRM-03 · LEAD PROFILE · ADM-CRM-05 ·
        // TRIAL RUNNING` -- two screens on one card, each with its own name -- and the
        // leading-ids group stops at `LEAD PROFILE`, so `ADM-CRM-05` sat in the description
        // and read as **unspecified while its entire design was in the file**: a trial clock,
        // four figures, a sentence and a button, indexed as a screen nobody had drawn.
        //
        // **Exactly an id, rather than any id in the description.** A description may
        // cross-reference another screen in prose ("ADM-MEM-11 exists because prevention is
        // never perfect"), and attributing that card to the screen it mentions would be the
        // opposite error. A segment that is nothing but an id is a co-label.
        const ids = line.text.split("·").map((part) => part.trim())
          .filter((part) => new RegExp(`^${ID.source.slice(2, -2)}$`).test(part));
        marks.push({ kind: "screen", ids, canvases: [], title: line.text, at: line.at });
        continue;
      }
      const canvas = CANVAS_SECTION.exec(line.text);
      if (canvas) {
        const numbers = [...canvas[1].matchAll(/\d+/g)].map((m) => Number(m[0]));
        marks.push({ kind: "canvas", ids: [], canvases: numbers, title: line.text, at: line.at });
      }
    }
    if (marks.length === 0) continue;

    sources.push({
      file,
      sha256: createHash("sha256").update(raw).digest("hex"),
      sections: marks.length,
    });

    for (let i = 0; i < marks.length; i += 1) {
      const to = i + 1 < marks.length ? marks[i + 1].at : Number.MAX_SAFE_INTEGER;
      let ids = marks[i].ids;
      if (marks[i].kind === "canvas") {
        // A canvas carries no id, so the registry's note is what names it. Every screen whose
        // note points at this file and one of this section's canvas numbers is specified here.
        const resolved = [];
        for (const [prefix, target] of Object.entries(CANVAS_OF)) {
          if (target !== name) continue;
          for (const row of registry) {
            if (!row.note.startsWith(`${prefix} c`)) continue;
            const number = Number(row.note.slice(prefix.length + 2).match(/^\d+/)?.[0]);
            if (marks[i].canvases.includes(number)) {
              resolved.push(row.id);
              usedPrefixes.add(prefix);
            }
          }
        }
        ids = [...new Set(resolved)];
      }
      sections.push({
        kind: marks[i].kind,
        ids,
        canvases: marks[i].canvases,
        title: marks[i].title,
        file,
        text: body(all, marks[i].at, to),
      });
    }
  }

  // And in the other direction: a prefix that resolved nothing is a mapping gone stale.
  for (const prefix of Object.keys(CANVAS_OF)) {
    const named = registry.some((row) => row.note.startsWith(`${prefix} c`));
    if (named && !usedPrefixes.has(prefix)) {
      throw new Error(
        `CANVAS_OF["${prefix}"] is named by the registry and matched no canvas in `
        + `${CANVAS_OF[prefix]} -- the canvas numbering has changed`,
      );
    }
  }

  const arabic = new Map();
  for (const [file, prefixes] of Object.entries(ARABIC_OF)) {
    for (const prefix of prefixes) arabic.set(prefix, file);
  }

  const v1 = registry.filter((row) => row.phase === "V1");
  const screens = v1.map((row) => {
    const specs = sections.filter((section) => section.ids.includes(row.id));
    const arabicFile = [...arabic.entries()].find(([prefix]) => row.id.startsWith(prefix))?.[1];
    return {
      id: row.id,
      surface: surfaceOf(row.id),
      module: row.module,
      name: row.name,
      roles: row.roles,
      /** The registry's own word on whether an Arabic build is drawn, contracted or needed. */
      arabic: row.arabic,
      arabic_reference: row.arabic === "N/A" || !arabicFile
        ? null
        : `veyro-product-experience-design/project/${arabicFile}`,
      /** `NO-UI` means the registry says this needs no screen. */
      registry_status: row.status,
      registry_note: row.note,
      specified: specs.length > 0,
      sections: specs.map((section) => ({
        kind: section.kind,
        title: section.title,
        file: section.file,
        text: section.text,
      })),
    };
  });

  // A screen whose note names an HF canvas and that resolved to no section means the canvas
  // numbering moved under us. The prefix check above cannot see it, because one prefix
  // covers several canvases and matching any of them satisfies it.
  for (const screen of screens) {
    const prefix = Object.keys(CANVAS_OF).find((p) => screen.registry_note.startsWith(`${p} c`));
    if (prefix && screen.sections.length === 0) {
      throw new Error(
        `${screen.id} is drawn at "${screen.registry_note}" and resolved to no canvas in `
        + `${CANVAS_OF[prefix]}`,
      );
    }
  }

  const specified = screens.filter((s) => s.specified);
  const noUi = screens.filter((s) => !s.specified && s.registry_status === "NO-UI");
  const unspecified = screens.filter((s) => !s.specified && s.registry_status !== "NO-UI");

  return {
    manifest: "veyro-screen-designs",
    note:
      "Extracted from the authoritative design source. Generated; do not edit by hand. "
      + "Regenerate with: npm run design:screens",
    authority:
      "These are the screen designs. contracts/ui/screen-contracts.yaml is the identity "
      + "registry and carries no layout; this carries what each screen actually specifies.",
    coverage: {
      v1_screens: screens.length,
      specified: specified.length,
      no_ui: noUi.length,
      unspecified: unspecified.length,
      unspecified_ids: unspecified.map((s) => s.id),
    },
    sources,
    screens,
  };
}

const want = extract();
const serialised = `${JSON.stringify(want, null, 2)}\n`;

if (process.argv.includes("--check")) {
  let current = "";
  try {
    current = readFileSync(OUT, "utf8");
  } catch {
    console.error("screens.generated.json is missing. Run: npm run design:screens");
    process.exit(1);
  }
  if (current !== serialised) {
    console.error("STALE: screens.generated.json disagrees with the design source.");
    process.exit(1);
  }
  const { v1_screens, specified, no_ui, unspecified } = want.coverage;
  console.log(
    `design:screens ok -- ${specified}/${v1_screens} V1 screens specified `
    + `(${no_ui} need no screen, ${unspecified} unspecified) from ${want.sources.length} files`,
  );
} else {
  writeFileSync(OUT, serialised);
  console.log(`wrote ${OUT}`);
  console.log(
    `  ${want.coverage.specified}/${want.coverage.v1_screens} V1 screens specified, `
    + `${want.coverage.unspecified} unspecified: ${want.coverage.unspecified_ids.join(", ")}`,
  );
}

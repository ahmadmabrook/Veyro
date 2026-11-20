#!/usr/bin/env node
/**
 * Extract the screen specifications from `veyro-product-experience-design/`.
 *
 * **These are designs, not a registry.** `contracts/ui/screen-contracts.yaml` carries 170
 * screen *identities* — id, surface, name, ux group — and says so: every contract field is
 * `null` and the manifest reads "IDENTITY_ONLY - full screen contracts are UNRESOLVED". That
 * is true of the registry data file it was generated from, and it was read as true of the
 * design folder, which it is not: the batch documents carry each screen rendered, with its
 * exact copy, its column set, its quick filters, its bulk actions, its empty and error
 * states, and an eyebrow that states the roles, the density and the width it was drawn at.
 *
 * ADM-MEM-05 is the example worth knowing: "MEMBERS LIST · CM, RECEP · COMPACT · 1440", a
 * seven-column grid with three quick filters, a saved-view control, a bounded selection and
 * the sentence "There is no state where 4,812 rows render." None of that was in the registry
 * and none of it was in this app.
 *
 * This writes `screens.generated.json` — one entry per screen section, with the file it came
 * from, its eyebrow fields and its text — so a screen being built has its specification at
 * hand and the compliance ledger can cite it. Every source file is pinned by SHA-256 and
 * `--check` fails on a stale extraction, like the contracts.
 *
 *     node src/design/screens.mjs          # write screens.generated.json
 *     node src/design/screens.mjs --check  # fail if it is stale
 */
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = resolve(HERE, "../../../veyro-product-experience-design/project");
const OUT = join(HERE, "screens.generated.json");

/** The eyebrow above each screen section: `ID · NAME · ROLES · DENSITY · WIDTH`, loosely. */
const EYEBROW = /letter-spacing:\.1em">([^<]{4,300})<\/div>/g;
const IS_SCREEN = /^[A-Z]{2,5}-[A-Z]+-\d+\s*·/;

/** Ids named anywhere in the eyebrow, since several sections cover a run of screens. */
const SCREEN_ID = /\b([A-Z]{2,5}-[A-Z]+-\d+)\b/g;

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

/** The readable text of a markup run, with the template placeholders left visible. */
function plain(markup) {
  const withoutScripts = markup.replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1>/gi, " ");
  const broken = withoutScripts.replace(/<\/(p|div|section|tr|li|h[1-6]|td|th)>/gi, "\n");
  return unescape(broken.replace(/<[^>]+>/g, " "))
    .replace(/[ \t]+/g, " ")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .join("\n");
}

function extract() {
  const screens = [];
  const sources = [];
  for (const name of readdirSync(SOURCE).sort()) {
    if (!name.endsWith(".dc.html")) continue;
    const raw = readFileSync(join(SOURCE, name));
    const text = raw.toString("utf8");
    const marks = [];
    for (const match of text.matchAll(EYEBROW)) {
      const label = unescape(match[1]).trim();
      if (IS_SCREEN.test(label)) marks.push({ label, at: match.index });
    }
    if (marks.length === 0) continue;
    sources.push({
      file: `veyro-product-experience-design/project/${name}`,
      sha256: createHash("sha256").update(raw).digest("hex"),
      sections: marks.length,
    });
    for (let i = 0; i < marks.length; i += 1) {
      const from = marks[i].at;
      const to = i + 1 < marks.length ? marks[i + 1].at : text.length;
      const body = plain(text.slice(from, to));
      const ids = [...marks[i].label.matchAll(SCREEN_ID)].map((m) => m[1]);
      // The eyebrow's trailing fields: roles, density and the width it was drawn at. They are
      // separated by the same middot as the ids, so anything after the last id is taken as
      // context rather than parsed into named fields the source does not promise.
      const tail = marks[i].label.split("·").map((part) => part.trim()).filter(Boolean);
      screens.push({
        ids,
        eyebrow: marks[i].label,
        context: tail.filter((part) => !SCREEN_ID.test(part) || part.length > 12),
        file: `veyro-product-experience-design/project/${name}`,
        /** The section's own text. The design is prose plus a rendered example, not a comp. */
        text: body,
      });
    }
  }
  return {
    manifest: "veyro-screen-designs",
    note:
      "Extracted from the authoritative design source. Generated; do not edit by hand. "
      + "Regenerate with: npm run design:screens",
    authority:
      "These are the screen designs. contracts/ui/screen-contracts.yaml is the identity "
      + "registry and carries no layout; this carries what each screen actually specifies.",
    sources,
    screen_ids: [...new Set(screens.flatMap((s) => s.ids))].sort(),
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
  console.log(
    `design:screens ok -- ${want.screens.length} sections, `
    + `${want.screen_ids.length} screen ids, ${want.sources.length} files`,
  );
} else {
  writeFileSync(OUT, serialised);
  console.log(`wrote ${OUT}`);
  console.log(`  ${want.screens.length} sections, ${want.screen_ids.length} screen ids`);
}

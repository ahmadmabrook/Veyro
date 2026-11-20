import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";

/**
 * The extraction reads the whole design folder, and this is what says so.
 *
 * **The first version of `screens.mjs` found 37 of 178 screens and the compliance ledger
 * recorded "133 have identity only" as a gap in the design source.** It was not a gap in the
 * source. The extraction matched its section boundary inside one CSS signature —
 * `letter-spacing:.1em` — which exists in nine of the forty-eight design documents, so every
 * high-fidelity file and every `V1 Batch M`–`Q` file was read as containing no screens. The
 * Command Center, the Member 360, the Front Desk, the POS, the Coach surface and the Member
 * app are all drawn in those files. Fifteen screens were then composed from whatever a
 * backend module's routes could answer, on the understanding that there was nothing to build
 * from.
 *
 * Nothing failed. The extraction reported a number, the ledger wrote it down, and the number
 * was wrong by a factor of four and a half.
 *
 * So these are the assertions that would have caught it, and each is written against the
 * specific thing that went unnoticed:
 *
 *  - **The coverage count, pinned.** A change that stops reading a file drops `specified`,
 *    and the pin fails rather than the ledger quietly recording a smaller number.
 *  - **Every document that titles a screen is a source.** Computed here from the folder
 *    independently of `screens.mjs`, so a boundary rule that narrows is caught by the
 *    disagreement rather than by its own output looking self-consistent.
 *  - **Named by file.** The seven `HF` documents are asserted by name, because those are the
 *    ones that were missing and a count alone would be satisfied by reading seven others.
 *  - **Both directions**, which is this repository's standing rule: a source that is listed
 *    and contains no screen title is as much a defect as one that is missing.
 */

const HERE = dirname(fileURLToPath(import.meta.url));
const DESIGN = resolve(HERE, "../../../veyro-product-experience-design/project");
const generated = JSON.parse(
  readFileSync(resolve(HERE, "../../src/design/screens.generated.json"), "utf8"),
);

/** The readable text lines of a design document, tags dropped. */
function lines(path) {
  const raw = readFileSync(path, "utf8")
    .replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1>/gi, " ")
    .replace(/<helmet[\s\S]*?<\/helmet>/gi, " ");
  return raw
    .replace(/<[^>]+>/g, "\n")
    .split("\n")
    .map((line) =>
      line
        .replace(/&nbsp;/g, " ")
        .replace(/&amp;/g, "&")
        .replace(/&#39;/g, "'")
        .replace(/\s+/g, " ")
        .trim())
    .filter(Boolean);
}

const TITLE =
  /^(?:[A-Z]{2,5}-(?:[A-Z]{2,6}-)?\d{1,3})(?:\s*·\s*(?:[A-Z]{2,5}-(?:[A-Z]{2,6}-)?\d{1,3}))*\s*·\s*.{3,}$/;
const CANVAS = /^CANVAS\s+[\d\s,&]+·/i;

/** Documents that title at least one screen or canvas, found without consulting the output. */
function documentsThatTitleScreens() {
  const found = [];
  for (const name of readdirSync(DESIGN).sort()) {
    if (!name.endsWith(".dc.html")) continue;
    const titles = lines(join(DESIGN, name)).filter(
      (line) => TITLE.test(line) || CANVAS.test(line));
    if (titles.length > 0) found.push(name);
  }
  return found;
}

test("the extraction covers 167 of the 178 V1 screens", () => {
  const { v1_screens, specified, no_ui, unspecified } = generated.coverage;
  assert.equal(v1_screens, 178, "the registry's V1 count moved");
  // Pinned. A narrowed boundary rule drops this and fails here rather than being written into
  // the compliance ledger as a gap in the design.
  assert.equal(specified, 167);
  assert.equal(no_ui, 8);
  assert.equal(unspecified, 3);
  assert.equal(specified + no_ui + unspecified, v1_screens);
});

test("the three unspecified screens are named, not counted", () => {
  // §5 of the directive: record the precise missing information rather than inventing a design
  // or certifying compliance. These three have a registry identity and a one-line note and no
  // drawn screen anywhere in the folder.
  assert.deepEqual(generated.coverage.unspecified_ids.slice().sort(), [
    "ADM-CRM-05",
    "ADM-POS-02",
    "MBR-33",
  ]);
});

test("every design document that titles a screen is a pinned source", () => {
  const titled = documentsThatTitleScreens();
  const listed = new Set(generated.sources.map((s) => s.file.split("/").pop()));
  const missing = titled.filter((name) => !listed.has(name));
  assert.deepEqual(missing, [], `design documents read by nothing: ${missing.join(", ")}`);
  // And the other direction: a pinned source that titles no screen is a stale entry.
  const spurious = [...listed].filter((name) => !titled.includes(name));
  assert.deepEqual(spurious, [], `sources that title no screen: ${spurious.join(", ")}`);
});

test("the high-fidelity documents are read, by name", () => {
  // The seven files the first extraction missed. Asserted by name because a count is satisfied
  // by reading seven other documents, and these are where the five surfaces are drawn.
  const listed = generated.sources.map((s) => s.file).join("\n");
  for (const name of [
    "Veyro HF Command Center.dc.html",
    "Veyro HF Member 360.dc.html",
    "Veyro HF CRM and Console.dc.html",
    "Veyro HF Remaining Modules.dc.html",
    "Veyro HF Front Desk and POS.dc.html",
    "Veyro HF Coach.dc.html",
    "Veyro HF Member App.dc.html",
  ]) {
    assert.ok(listed.includes(name), `${name} is not a source`);
  }
});

test("the five V1 batch documents that each draw twelve screens are read", () => {
  // Each of these announces its own count in its header — "BATCH M · 12 SCREENS DRAWN" — and
  // each was read as empty.
  const byFile = new Map(generated.sources.map((s) => [s.file.split("/").pop(), s.sections]));
  for (const letter of ["M", "N", "O", "P", "Q"]) {
    const name = readdirSync(DESIGN).find(
      (f) => f.startsWith(`Veyro V1 Batch ${letter} `) && f.endsWith(".dc.html"));
    assert.ok(name, `no V1 Batch ${letter} document`);
    assert.ok((byFile.get(name) ?? 0) >= 12,
      `${name} contributed ${byFile.get(name)} sections, and its header says 12 screens drawn`);
  }
});

test("a specified screen carries text, not just a title", () => {
  // A section that matched its boundary and sliced an empty body would count as specified and
  // tell a reader nothing. Every screen the extraction calls specified has real content.
  const thin = generated.screens
    .filter((s) => s.specified)
    .filter((s) => s.sections.reduce((n, x) => n + x.text.length, 0) < 120)
    .map((s) => s.id);
  assert.deepEqual(thin, [], `specified with almost no text: ${thin.join(", ")}`);
});

test("every screen the registry marks drawn in an HF canvas resolved to one", () => {
  // `screens.mjs` throws on this, so the assertion here is that the output agrees — the check
  // and the data cannot drift apart without one of them failing.
  const unresolved = generated.screens
    .filter((s) => /^HF .+ c\d+/.test(s.registry_note) && s.sections.length === 0)
    .map((s) => s.id);
  assert.deepEqual(unresolved, []);
});

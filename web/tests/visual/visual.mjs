/**
 * **DEPRECATED on 2026-11-26, and it must not be used to judge the current design.**
 *
 * This harness renders `veyro-product-experience-design/project/*.dc.html` and puts the
 * implementation beside it. That design was replaced wholesale by owner directive: it is
 * evidence of what the product used to look like and an anti-reference, not an authority. A
 * difference this tool reports between the canvases and the build is now the *intent*, so
 * acting on its output would walk the new system back toward the retired one -- which is the
 * single most likely way this redesign gets quietly undone.
 *
 * It is kept rather than deleted because the extraction logic and the canvas-rendering runtime
 * are the only record of how those documents were read, and because `screens.generated.json`
 * is still product data. It has no npm script and is in no CI job.
 *
 * What replaced it: `src/design/system-check.mjs` (npm run design:check) for the system's
 * structural properties, the contrast suite for every pairing a reader sees, and the Playwright
 * suites for the rendered result. `DESIGN.md` is the authority for what the product should
 * look like.
 */
/**
 * The visual comparison harness: the approved canvas and the running screen, side by side,
 * plus a mechanical diff of the properties a screenshot cannot be trusted to show.
 *
 * **Why this exists, and why it is not a pixel-diff percentage.** The authoritative design in
 * `veyro-product-experience-design/project/*.dc.html` is not a flat mockup: each canvas is an
 * annotated page that draws a screen at its own declared width with explanatory panels beside
 * it. A pixel diff of that against a running app would be almost entirely noise -- different
 * widths, the annotation column, real data where the canvas has sample data -- and the one
 * thing worse than no visual check is a tolerance loosened until the noise passes, which is
 * then quoted as a fidelity number.
 *
 * So the harness does two separate things, and keeps them separate:
 *
 *   1. **It renders both and writes them side by side**, so somebody looks. Every rendering
 *      defect ever found in this surface was found by looking: the schedule board three hours
 *      wrong under a heading naming the right timezone, seven screens scrolling sideways at
 *      phone width, a metric value wrapping over two lines in Arabic. Four layers of green
 *      assertions saw none of them.
 *   2. **It extracts a style inventory from each side and diffs the sets.** This is the
 *      mechanical half and it needs no element-to-element mapping: the canvas's computed
 *      typography, colours, radii and borders are the specification, so a declaration the
 *      design uses and the implementation never produces is a deviation with a number on it.
 *      `font: 500 12.5px/1.45 'IBM Plex Sans'` against `500 13px/1.5` is exactly the class of
 *      difference the owner raised and exactly what a screenshot comparison argues about.
 *
 * **The canvases render for real.** `support.js` is the design runtime; it resolves every
 * `{{ }}` placeholder and `sc-for` loop and pulls React 18 UMD from unpkg, so rendering needs
 * network. A canvas that renders with placeholders left in it is a canvas that did not run,
 * and `shootDesign` refuses rather than photographing the template -- a reference built from a
 * half-rendered page is a reference that proves whatever the implementation happens to do.
 *
 * Subcommands:
 *   design  <canvas-file> <screen-id>   the approved drawing and its inventory
 *   impl    <route> <name>              the running screen and its inventory
 *   compare <design-json> <impl-json>   the declarations one has and the other lacks
 */

import { createServer } from "node:http";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { chromium } from "@playwright/test";

const DESIGN_ROOT = new URL("../../../veyro-product-experience-design/project/", import.meta.url)
  .pathname;
const OUT = process.env.VISUAL_OUT ?? new URL("../../.visual/", import.meta.url).pathname;
const APP = process.env.VISUAL_APP ?? "http://localhost:3000";

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css",
  ".json": "application/json",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
};

/** Serve the design directory, so `./support.js` and `./uploads/*` resolve as the canvas expects. */
async function serveDesign() {
  const server = createServer(async (req, res) => {
    try {
      const path = decodeURIComponent(new URL(req.url, "http://x").pathname);
      const file = join(DESIGN_ROOT, normalize(path).replace(/^(\.\.[/\\])+/, ""));
      const body = await readFile(file);
      res.writeHead(200, { "content-type": MIME[extname(file).toLowerCase()] ?? "application/octet-stream" });
      res.end(body);
    } catch {
      res.writeHead(404, { "content-type": "text/plain" }).end("not in the design directory");
    }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  return { server, port: server.address().port };
}

/**
 * The style inventory of one subtree: what this drawing actually asks for, resolved to pixels.
 *
 * Collected from **computed** styles rather than the inline `style` attributes, because a
 * canvas writes `font:500 12.5px/1.45 'IBM Plex Sans'` as a shorthand and the implementation
 * writes four custom properties through a stylesheet. Comparing the declarations as authored
 * would compare two notations; comparing what the browser resolved compares the design.
 *
 * Each entry carries how many elements used it and one example of their text, so a deviation
 * can be found on the page rather than merely counted.
 */
function inventoryScript() {
  return (rootSelector) => {
    const roots = [...document.querySelectorAll(rootSelector || "body")];
    if (!roots.length) return null;
    const type = new Map();
    const fill = new Map();
    const edge = new Map();
    const bump = (map, key, text) => {
      const seen = map.get(key);
      if (seen) {
        seen.n += 1;
        if (seen.examples.length < 3 && text && !seen.examples.includes(text)) seen.examples.push(text);
      } else {
        map.set(key, { n: 1, examples: text ? [text] : [] });
      }
    };
    const px = (v) => (v === "normal" ? "normal" : `${Math.round(parseFloat(v) * 100) / 100}px`);
    const family = (v) => (v.split(",")[0] ?? "").replace(/["']/g, "").trim();

    for (const el of roots.flatMap((r) => [...r.querySelectorAll("*")])) {
      const box = el.getBoundingClientRect();
      if (box.width === 0 || box.height === 0) continue;
      const s = getComputedStyle(el);
      // Only elements that render text of their own contribute typography: a wrapper
      // inherits a font it never uses, and counting those buries the real set.
      const own = [...el.childNodes]
        .filter((n) => n.nodeType === 3 && n.textContent.trim())
        .map((n) => n.textContent.trim())
        .join(" ")
        .slice(0, 48);
      if (own) {
        bump(type, `${s.fontWeight} ${px(s.fontSize)}/${px(s.lineHeight)} ${family(s.fontFamily)}`, own);
        bump(fill, `color ${s.color}`, own);
      }
      if (s.backgroundColor !== "rgba(0, 0, 0, 0)") bump(fill, `background ${s.backgroundColor}`, own);
      if (s.borderTopWidth !== "0px" || s.borderBottomWidth !== "0px") {
        bump(edge, `border ${px(s.borderTopWidth)} ${s.borderTopColor}`, own);
      }
      if (s.borderTopLeftRadius !== "0px") bump(edge, `radius ${px(s.borderTopLeftRadius)}`, own);
    }
    const out = (map) =>
      [...map.entries()]
        .sort((a, b) => b[1].n - a[1].n)
        .map(([key, v]) => ({ key, n: v.n, examples: v.examples }));
    return { type: out(type), fill: out(fill), edge: out(edge) };
  };
}

/**
 * Find the canvas section that draws a screen.
 *
 * **The index is `screens.generated.json`, not a guess from the label.** Some canvases open a
 * section with the ids it draws -- `ADM-RPT-01 · 02 · 03 · 04 · 05` -- and some open with the
 * canvas number instead, `CANVAS 1 · OWNER · ALL LOCATIONS · NORMAL OPERATIONAL DAY · 1440×900`,
 * which names no screen at all. The pinned extraction already resolved that mapping for all
 * 178 screens and is the authority the rest of this app reads, so the harness asks it for the
 * section titles rather than re-deriving a rule that is wrong for half the canvases. The
 * id-in-the-label match stays as a fallback for a section the extraction did not attribute.
 */
function sectionScript() {
  return ({ id, titles, headings }) => {
    const sections = [...document.querySelectorAll("section")];
    const firstLine = (s) => (s.innerText || "").split("\n")[0].trim();
    const squash = (t) => t.replace(/\s+/g, " ").trim().toLowerCase();
    const wanted = titles.map(squash);
    const allHeadings = new Set(headings.map(squash));

    let at = wanted.length ? sections.findIndex((s) => wanted.includes(squash(firstLine(s)))) : -1;
    if (at === -1 && wanted.length) {
      at = sections.findIndex((s) => wanted.some((t) => squash(firstLine(s)).startsWith(t.slice(0, 40))));
    }
    if (at === -1) {
      const [, prefix, number] = /^([A-Z]+-[A-Z]+)-(\d+)$/.exec(id) ?? [];
      at = sections.findIndex((s) => {
        const label = (s.innerText || "").split("\n").slice(0, 2).join(" ");
        if (label.includes(id)) return true;
        // `ADM-RPT-01 · 02 · 03` -- the prefix once, then bare numbers.
        return Boolean(prefix) && label.includes(prefix) && new RegExp(`[·,]\\s*0*${Number(number)}\\b`).test(label);
      });
    }
    if (at === -1) {
      return { found: false, labels: sections.map((s) => firstLine(s).slice(0, 100)) };
    }

    // **A labelled heading and the drawing under it are separate sections.** The HF canvases
    // open with `CANVAS 1 · OWNER · ALL LOCATIONS · 1440×900` in a section 119px tall and draw
    // the screen in the next one. So the screen is the heading plus every section after it up
    // to the next heading -- shooting only the matched section photographs the caption.
    const isHeading = (s) => {
      const line = squash(firstLine(s));
      return allHeadings.has(line) || /^(canvas|responsive|design system|[a-z]{2,4}-[a-z]{2,4}-\d)/.test(line);
    };
    const span = [sections[at]];
    for (let i = at + 1; i < sections.length && !isHeading(sections[i]); i += 1) span.push(sections[i]);

    for (const s of span) s.setAttribute("data-visual-span", "1");
    const boxes = span.map((s) => s.getBoundingClientRect());
    const scrollY = window.scrollY;
    const left = Math.min(...boxes.map((b) => b.left));
    const top = Math.min(...boxes.map((b) => b.top)) + scrollY;
    const right = Math.max(...boxes.map((b) => b.right));
    const bottom = Math.max(...boxes.map((b) => b.bottom)) + scrollY;
    return {
      found: true,
      label: firstLine(sections[at]).slice(0, 140),
      sections: span.length,
      clip: {
        x: Math.max(0, Math.round(left)),
        y: Math.max(0, Math.round(top)),
        width: Math.round(right - left),
        height: Math.round(bottom - top),
      },
      width: Math.round(right - left),
      height: Math.round(bottom - top),
    };
  };
}

/** Every section title the extraction attributes to any screen in this canvas file. */
async function headingsIn(canvasFile) {
  const generated = JSON.parse(
    await readFile(new URL("../../src/design/screens.generated.json", import.meta.url).pathname, "utf8"),
  );
  const titles = new Set();
  for (const screen of generated.screens) {
    for (const section of screen.sections) {
      if (section.file.endsWith(canvasFile)) titles.add(section.title);
    }
  }
  return [...titles];
}

/** The section titles the pinned extraction attributes to this screen within this canvas. */
async function sectionTitlesFor(screenId, canvasFile) {
  const generated = JSON.parse(
    await readFile(new URL("../../src/design/screens.generated.json", import.meta.url).pathname, "utf8"),
  );
  const screen = generated.screens.find((s) => s.id === screenId);
  if (!screen) throw new Error(`${screenId} is not in the extracted screen designs`);
  return screen.sections.filter((s) => s.file.endsWith(canvasFile)).map((s) => s.title);
}

async function shootDesign(canvasFile, screenId) {
  const { server, port } = await serveDesign();
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
    const failures = [];
    page.on("pageerror", (e) => failures.push(String(e)));
    await page.goto(`http://127.0.0.1:${port}/${encodeURIComponent(canvasFile)}`, {
      waitUntil: "networkidle",
      timeout: 60_000,
    });
    await page.waitForFunction(() => !document.body.innerText.includes("{{"), null, { timeout: 30_000 })
      .catch(() => {});

    const left = await page.evaluate(() => (document.body.innerText.match(/\{\{/g) || []).length);
    if (left > 0) {
      throw new Error(
        `${canvasFile} rendered with ${left} unresolved placeholders -- the design runtime did not run, ` +
          `and photographing the template would make a reference that proves nothing. Check network access to unpkg.`,
      );
    }
    if (failures.length) throw new Error(`${canvasFile} raised: ${failures[0]}`);

    const titles = await sectionTitlesFor(screenId, canvasFile);
    const headings = await headingsIn(canvasFile);
    const found = await page.evaluate(sectionScript(), { id: screenId, titles, headings });
    if (!found.found) {
      throw new Error(
        `${screenId} is not drawn in ${canvasFile}.\n` +
          `  the extraction attributes: ${titles.length ? titles.join(" | ") : "(nothing in this file)"}\n` +
          `  the canvas draws:\n    ${found.labels.join("\n    ")}`,
      );
    }
    await mkdir(OUT, { recursive: true });
    const png = join(OUT, `${screenId}.design.png`);
    await page.screenshot({ path: png, fullPage: true, clip: found.clip });
    const inventory = await page.evaluate(inventoryScript(), "[data-visual-span]");
    const json = join(OUT, `${screenId}.design.json`);
    await writeFile(json, JSON.stringify({ screenId, canvasFile, ...found, inventory }, null, 2));
    console.log(`design  ${screenId}  ${found.width}x${found.height}  ${found.label}`);
    console.log(`        ${png}`);
    return { png, json };
  } finally {
    await browser.close();
    server.close();
  }
}

/** Sign in through the real form, the way `look.mjs` does, so the screen is the gated one. */
async function signIn(page) {
  const envFile = new URL("../../.env.e2e.local", import.meta.url).pathname;
  const env = Object.fromEntries(
    (await readFile(envFile, "utf8"))
      .split("\n")
      .filter((line) => line.includes("=") && !line.startsWith("#"))
      .map((line) => [line.slice(0, line.indexOf("=")), line.slice(line.indexOf("=") + 1)]),
  );
  await page.goto(`${APP}/login`);
  await page.getByLabel("Tenant ID").fill(env.VEYRO_E2E_TENANT_ID);
  await page.getByLabel("Email or phone").fill(env.VEYRO_E2E_EMAIL);
  await page.getByLabel("Password").fill(env.VEYRO_E2E_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 20_000 });
  return env;
}

async function shootImpl(route, name) {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({
      viewport: { width: Number(process.env.VISUAL_WIDTH ?? 1440), height: 900 },
      deviceScaleFactor: 2,
    });
    const env = await signIn(page);
    if (process.env.LOCALE === "ar") {
      await page.getByRole("button", { name: "العربية" }).click();
      await page.waitForTimeout(600);
    }
    const url = route
      .replace("ID_HERE", env.VEYRO_E2E_PERSON_ID)
      .replace("ZONE_HERE", env.VEYRO_E2E_ZONE_ID)
      .replace("DEVICE_HERE", env.VEYRO_E2E_DEVICE_ID)
      .replace("SESSION_HERE", env.VEYRO_E2E_SESSION_ID)
      .replace("INVOICE_HERE", env.VEYRO_E2E_INVOICE_ID);
    await page.goto(APP + url, { waitUntil: "networkidle" });
    await mkdir(OUT, { recursive: true });
    const png = join(OUT, `${name}.impl.png`);
    await page.screenshot({ path: png, fullPage: true });
    const inventory = await page.evaluate(inventoryScript(), "body");
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    const json = join(OUT, `${name}.impl.json`);
    await writeFile(json, JSON.stringify({ name, route: url, overflow, inventory }, null, 2));
    console.log(`impl    ${name}  overflow ${overflow}`);
    console.log(`        ${png}`);
    return { png, json };
  } finally {
    await browser.close();
  }
}

/**
 * The design-system tables, which are what an unmatched declaration has to be judged against.
 *
 * **The canvases are a sequence, and the later ones correct the earlier ones.** The HF
 * prototypes were drawn before the token tables existed, and the design system says so about
 * its own history in as many words: the first specimens used light greys for member IDs,
 * branch names and timestamps measuring 2.34:1 to 4.12:1, and "had they been adopted as drawn
 * they would have propagated into every surface in the product -- precisely the
 * retrofit-after-hi-fi failure that VALIDATE-1 exists to prevent."
 *
 * So a raw diff of an HF canvas against the running app produces findings whose correction
 * would *undo* the design system. Two concrete cases, both live:
 *
 *   - the HF Command Center draws its page title at 24px; `TYPE_SCALE` fixes `type.h1` at
 *     "26 / 1.15 -- Page title. One per screen." The implementation renders 26px, and
 *     "fixing" it to 24 would leave the product disagreeing with its own token table.
 *   - that canvas sets 27 small-text elements in `#85807a`; the `CONTRAST` matrix rates it
 *     "FAIL under 18.66px on every surface. Large text, disabled controls and decoration
 *     only." Matching it would ship a measured accessibility failure.
 *
 * Hence three buckets rather than one list. A declaration is a **deviation** only when the
 * design value is one the token tables sanction; otherwise it is reported as prototype drift
 * or as a pairing the contrast matrix bars, so it stays visible and is not silently dropped.
 */
async function tokenTables() {
  const ds = JSON.parse(await readFile(new URL("../../src/design/ds.json", import.meta.url).pathname, "utf8"));
  // A step is weight + size + the leading ratio together. Matching on size alone calls an
  // 11px glyph set at 11/11 the same thing as `type.caption` at 11/1.40, which is how a
  // prototype's incidental line-height gets reported as a specification.
  const steps = ds.TYPE_SCALE.map(([name, scale, weight]) => {
    const [size, ratio] = String(scale).split("/").map((part) => Number(part.trim()));
    return { name, size, ratio, weight: String(weight).trim() };
  });
  const barred = new Map();
  for (const row of ds.CONTRAST) {
    const [name, hex, , , , note] = row;
    if (hex && /FAIL/i.test(note ?? "")) barred.set(String(hex).toLowerCase(), `${name} -- ${note}`);
  }
  const primitives = new Map(ds.PRIMITIVES.map(([name, hex]) => [String(hex).toLowerCase(), name]));
  // Which primitives a semantic token actually binds. A palette entry with no semantic role
  // is a colour the canvas reached for directly, which the system does not sanction.
  const bound = new Set();
  for (const [token, light] of ds.SEMANTIC) {
    const ref = String(light).split("+")[0].trim();
    const hex = /^#/.test(ref) ? ref.toLowerCase() : [...primitives].find(([, n]) => n === ref)?.[0];
    if (hex) bound.add(`${hex}`);
    if (token) continue;
  }
  return { steps, barred, primitives, bound };
}

const toHex = (rgb) => {
  const m = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(rgb);
  if (!m) return null;
  return `#${[1, 2, 3].map((i) => Number(m[i]).toString(16).padStart(2, "0")).join("")}`;
};

/**
 * What the design asks for that the implementation never produces.
 *
 * Reported as unmatched **declarations**, not as a similarity score. A typographic style the
 * canvas uses on eleven elements and the running screen uses nowhere is a finding; a score
 * would average it away against the hundred that match.
 *
 * Typography is compared on weight, size and leading **to the nearest half-pixel in size**,
 * because the canvases are authored in halves (`12.5px`, `10.5px`) and a browser resolves a
 * rem-based token to three decimals. A tolerance wider than that would stop seeing the
 * difference between 12.5 and 13, which is the difference being looked for.
 */
async function compare(designJson, implJson) {
  const design = JSON.parse(await readFile(designJson, "utf8"));
  const impl = JSON.parse(await readFile(implJson, "utf8"));
  const tables = await tokenTables();
  const near = (a, b) => {
    const pa = /^(\d+) ([\d.]+)px\/([\d.]+|normal)px? (.+)$/.exec(a);
    const pb = /^(\d+) ([\d.]+)px\/([\d.]+|normal)px? (.+)$/.exec(b);
    if (!pa || !pb) return a === b;
    return (
      pa[1] === pb[1] &&
      Math.abs(Number(pa[2]) - Number(pb[2])) <= 0.5 &&
      pa[4] === pb[4] &&
      (pa[3] === pb[3] || Math.abs(Number(pa[3]) - Number(pb[3])) <= 1.5)
    );
  };
  /** Which bucket an unmatched declaration belongs in, and why, in the tables' own words. */
  const classify = (group, entry) => {
    if (group === "type") {
      const m = /^(\d+) ([\d.]+)px\/([\d.]+|normal)/.exec(entry.key);
      if (!m) return { bucket: "deviation", why: "" };
      const [, weight, size, line] = m;
      const ratio = line === "normal" ? null : Number(line) / Number(size);
      const step = tables.steps.find(
        (s) =>
          s.weight === weight &&
          Math.abs(s.size - Number(size)) <= 0.26 &&
          (ratio === null || Math.abs(s.ratio - ratio) <= 0.06),
      );
      if (!step) {
        return {
          bucket: "drift",
          why: `${weight} ${size}px${ratio ? `/${ratio.toFixed(2)}` : ""} matches no TYPE_SCALE step`,
        };
      }
      return { bucket: "deviation", why: `${step.name} (${step.size}/${step.ratio}, ${step.weight})` };
    }
    const hex = toHex(entry.key.replace(/^(color|background|border [\d.]+px) /, ""));
    const barred = hex && tables.barred.get(hex);
    if (barred && entry.key.startsWith("color ")) return { bucket: "barred", why: barred };
    if (hex && !tables.primitives.has(hex)) {
      return { bucket: "drift", why: `${hex} is not in PRIMITIVES` };
    }
    if (hex && !tables.bound.has(hex)) {
      return { bucket: "drift", why: `${hex} is ${tables.primitives.get(hex)}, which no SEMANTIC token binds` };
    }
    return { bucket: "deviation", why: hex ? `${tables.primitives.get(hex)}` : "" };
  };

  const report = { screenId: design.screenId, deviation: [], drift: [], barred: [] };
  for (const group of ["type", "fill", "edge"]) {
    const have = impl.inventory[group].map((e) => e.key);
    for (const entry of design.inventory[group]) {
      if (have.some((key) => (group === "type" ? near(entry.key, key) : key === entry.key))) continue;
      const { bucket, why } = classify(group, entry);
      report[bucket].push({ group, key: entry.key, n: entry.n, why, examples: entry.examples });
    }
  }
  const show = (title, list, lead) => {
    console.log(`\n${title}  (${list.length})`);
    if (lead && list.length) console.log(`  ${lead}`);
    for (const e of list.slice(0, 16)) {
      console.log(`  ${String(e.n).padStart(3)}x  ${e.group.padEnd(4)} ${e.key}`);
      if (e.why) console.log(`        ${e.why}`);
      if (e.examples.length) console.log(`        e.g. ${e.examples.join(" | ").slice(0, 100)}`);
    }
    if (list.length > 16) console.log(`  ... and ${list.length - 16} more`);
  };
  console.log(`\n${design.screenId} vs ${impl.name}`);
  show("DEVIATION -- the token tables sanction this and the screen does not use it", report.deviation);
  show(
    "PROTOTYPE DRIFT -- in the canvas, not in the token tables",
    report.drift,
    "The HF canvases predate the token tables; matching these would put the product at odds with its own design system.",
  );
  show(
    "BARRED BY THE CONTRAST MATRIX -- the design system rates this pairing a failure",
    report.barred,
    "Matching these would ship a measured accessibility failure. Reported so the difference stays visible.",
  );
  await writeFile(join(OUT, `${design.screenId}.compare.json`), JSON.stringify(report, null, 2));
  return report;
}

const [command, ...rest] = process.argv.slice(2);
if (command === "design") await shootDesign(rest[0], rest[1]);
else if (command === "impl") await shootImpl(rest[0], rest[1]);
else if (command === "compare") await compare(rest[0], rest[1]);
else {
  console.error("usage: visual.mjs design <canvas.dc.html> <SCREEN-ID>");
  console.error("       visual.mjs impl <route> <name>");
  console.error("       visual.mjs compare <design.json> <impl.json>");
  process.exit(2);
}

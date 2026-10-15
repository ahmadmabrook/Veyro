#!/usr/bin/env node
// MOD-001 canonical-screen binding: generator and validator (Node >= 18, no dependencies).
//
//   node tools/screen_contracts/screen_contracts.mjs generate        rewrite contracts/ui/screen-contracts.yaml
//   node tools/screen_contracts/screen_contracts.mjs check-identity  source identity only (CI gate)
//   node tools/screen_contracts/screen_contracts.mjs check-complete  full-contract gate (fails while fields are UNRESOLVED)
//
// The retained UX registry (veyro-registry-data.js, its resolve()) is the only source of IDs.
// Nothing here invents routes, modules, commands or permissions.

import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve as resolvePath } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolvePath(dirname(fileURLToPath(import.meta.url)), '..', '..');
const SOURCE_REL = 'veyro-product-experience-design/project/veyro-registry-data.js';
const OUTPUT_REL = 'contracts/ui/screen-contracts.yaml';

const EXPECTED_SOURCE_ROWS = 186;
const EXPECTED_V1_ROWS = 178;
const EXPECTED_BACKEND_ROWS = 8;
const EXPECTED_UI_ROWS = 170;
const EXPECTED_SURFACE_COUNTS = {
  'Veyro Admin': 85,
  'Front Desk & POS': 16,
  'Veyro Coach': 19,
  'Veyro Member': 35,
  'Internal Console': 15,
};
const BACKEND_SURFACE = 'Backend / no UI';

// Contract fields the registry does not supply. Each is emitted as null per screen.
const UNRESOLVED_FIELDS = [
  'route',
  'owning_module',
  'read_model',
  'commands',
  'permissions',
  'realtime',
  'masking',
  'offline',
  'error_contract',
];

const fail = (msg) => {
  console.error(`FAIL: ${msg}`);
  process.exit(1);
};

async function loadSource() {
  const bytes = readFileSync(resolvePath(ROOT, SOURCE_REL));
  const sha256 = createHash('sha256').update(bytes).digest('hex');
  // The file is an ES module; import it from its own bytes so no package.json "type" is needed.
  const mod = await import(`data:text/javascript;base64,${bytes.toString('base64')}`);
  return { sha256, rows: mod.resolve() };
}

function checkSourceRows(rows) {
  if (rows.length !== EXPECTED_SOURCE_ROWS) fail(`source resolve() rows: ${rows.length}, expected ${EXPECTED_SOURCE_ROWS}`);
  const v1 = rows.filter((r) => r.isV1);
  if (v1.length !== EXPECTED_V1_ROWS) fail(`V1 rows: ${v1.length}, expected ${EXPECTED_V1_ROWS}`);
  const ids = rows.map((r) => r.id);
  const dupes = ids.filter((id, i) => ids.indexOf(id) !== i);
  if (dupes.length) fail(`duplicate source IDs: ${[...new Set(dupes)].join(', ')}`);
  const backend = v1.filter((r) => r.surface === BACKEND_SURFACE);
  if (backend.length !== EXPECTED_BACKEND_ROWS) fail(`backend/no-UI rows: ${backend.length}, expected ${EXPECTED_BACKEND_ROWS}`);
  const ui = v1.filter((r) => r.surface !== BACKEND_SURFACE);
  if (ui.length !== EXPECTED_UI_ROWS) fail(`V1 UI rows: ${ui.length}, expected ${EXPECTED_UI_ROWS}`);
  checkSurfaceCounts(ui.map((r) => r.surface), 'source');
  return ui;
}

function checkSurfaceCounts(surfaces, label) {
  const got = {};
  for (const s of surfaces) got[s] = (got[s] || 0) + 1;
  const want = EXPECTED_SURFACE_COUNTS;
  const keys = new Set([...Object.keys(got), ...Object.keys(want)]);
  for (const k of keys) {
    if ((got[k] || 0) !== (want[k] || 0)) fail(`${label} surface "${k}": ${got[k] || 0}, expected ${want[k] || 0}`);
  }
}

function buildManifest(sha256, uiRows) {
  const contract = Object.fromEntries(UNRESOLVED_FIELDS.map((f) => [f, null]));
  return {
    manifest: 'veyro-screen-contracts',
    format_note:
      'JSON text, which is valid YAML 1.2 (JSON is a YAML 1.2 subset). Generated; do not edit by hand. ' +
      'Regenerate with: node tools/screen_contracts/screen_contracts.mjs generate',
    status: 'IDENTITY_ONLY - full screen contracts are UNRESOLVED',
    source: {
      path: SOURCE_REL,
      sha256,
      selection: 'resolve() rows with isV1 true and surface other than "Backend / no UI"',
      excluded_backend_no_ui_rows: EXPECTED_BACKEND_ROWS,
    },
    counts: { v1_ui_screens: uiRows.length, by_surface: EXPECTED_SURFACE_COUNTS },
    unresolved_policy:
      'A null contract field means the source registry does not supply it. Null is not PASS. ' +
      'No route, owning implementation module, read model, command, permission, realtime, masking, offline or error ' +
      'contract has been inferred. ux_group and source_roles are registry labels, not implementation modules or permissions.',
    unresolved_fields: UNRESOLVED_FIELDS,
    screens: uiRows.map((r) => ({
      id: r.id,
      surface: r.surface,
      name: r.name,
      phase: r.phase,
      ux_group: r.module,
      source_status: r.status,
      source_roles: r.roles,
      contract: { ...contract },
    })),
  };
}

const render = (manifest) => `${JSON.stringify(manifest, null, 2)}\n`;

function readOutput() {
  const text = readFileSync(resolvePath(ROOT, OUTPUT_REL), 'utf8');
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (e) {
    fail(`${OUTPUT_REL} is not parseable as JSON: ${e.message}`);
  }
  return { text, parsed };
}

async function checkIdentity() {
  const { sha256, rows } = await loadSource();
  const ui = checkSourceRows(rows);
  const expected = buildManifest(sha256, ui);
  const { text, parsed } = readOutput();

  if (parsed.source?.sha256 !== sha256) fail(`source hash mismatch: manifest ${parsed.source?.sha256}, actual ${sha256}`);
  const got = (parsed.screens || []).map((s) => s.id);
  const dupes = got.filter((id, i) => got.indexOf(id) !== i);
  if (dupes.length) fail(`duplicate manifest IDs: ${[...new Set(dupes)].join(', ')}`);
  if (got.length !== EXPECTED_UI_ROWS) fail(`manifest screens: ${got.length}, expected ${EXPECTED_UI_ROWS}`);
  checkSurfaceCounts(parsed.screens.map((s) => s.surface), 'manifest');
  const want = new Set(ui.map((r) => r.id));
  const missing = [...want].filter((id) => !got.includes(id));
  const extra = got.filter((id) => !want.has(id));
  if (missing.length || extra.length) fail(`ID set differs; missing: [${missing}] extra: [${extra}]`);
  if (text !== render(expected)) fail(`${OUTPUT_REL} differs from deterministic regeneration; run "generate"`);

  console.log(
    `PASS (identity only): ${got.length} V1 UI IDs, source sha256 ${sha256.slice(0, 12)}, ` +
      'output matches deterministic regeneration. This is NOT a full-contract PASS.',
  );
}

async function checkComplete() {
  await checkIdentity();
  const { parsed } = readOutput();
  const perField = Object.fromEntries(UNRESOLVED_FIELDS.map((f) => [f, 0]));
  let total = 0;
  for (const s of parsed.screens) {
    for (const f of UNRESOLVED_FIELDS) {
      const v = s.contract?.[f];
      if (v === null || v === undefined || v === 'UNRESOLVED') {
        perField[f]++;
        total++;
      }
    }
  }
  if (total > 0) {
    const detail = Object.entries(perField).map(([f, n]) => `${f}=${n}`).join(' ');
    fail(`full-contract gate: ${total} unresolved fields across ${parsed.screens.length} screens (${detail}); ` +
      'the source registry does not supply them');
  }
  console.log(`PASS (complete): all contract fields resolved for ${parsed.screens.length} screens`);
}

async function generate() {
  const { sha256, rows } = await loadSource();
  const ui = checkSourceRows(rows);
  writeFileSync(resolvePath(ROOT, OUTPUT_REL), render(buildManifest(sha256, ui)));
  console.log(`wrote ${OUTPUT_REL}: ${ui.length} screens, source sha256 ${sha256}`);
}

const commands = { generate, 'check-identity': checkIdentity, 'check-complete': checkComplete };
const cmd = commands[process.argv[2]];
if (!cmd) fail(`usage: screen_contracts.mjs <${Object.keys(commands).join('|')}>`);
await cmd();

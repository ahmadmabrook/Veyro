/**
 * The web and the backend must format identically, and this proves it by running both.
 *
 * **Why a cross-runtime test rather than two test suites.** The design system's Arabic rules
 * require numerals "applied identically on screen, receipt, export and PDF", and money on a
 * screen comes from this JavaScript while money on a receipt comes from
 * `backend/app/l10n/conventions.py`. Two suites that each assert their own expectations pass
 * forever while drifting apart; the only thing that catches drift is comparing the two
 * outputs. So this spawns Python, feeds both implementations one vector set, and compares the
 * strings character for character -- including the invisible bidi controls, which is where a
 * difference would actually hide.
 *
 * It skips rather than fails when no Python 3 is on PATH, and says so: a skipped parity check
 * is an honest gap, while a silently-passing one would be the vacuous evidence this repository
 * has been bitten by repeatedly.
 */

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { test } from "node:test";

import {
  direction,
  formatInteger,
  formatMoney,
  isolate,
  sanitizeUntrusted,
  shapeDigits,
  pluralCategory,
} from "../../src/i18n/conventions.mjs";

const BACKEND = new URL("../../../backend", import.meta.url).pathname;

/**
 * One vector set, exercised by both runtimes.
 *
 * The money cases are chosen for the places an implementation diverges: JOD's three minor
 * digits against USD's two, a zero minor part that has to keep its padding, a negative where
 * the sign must sit outside the isolate, a value that needs thousands grouping in both numeral
 * systems, and the Arabic locale where the whole run is LTR-isolated.
 */
const MONEY = [
  [45000, "JOD", "latn", "en"],
  [45000, "JOD", "latn", "ar"],
  [45000, "JOD", "arab", "ar"],
  [1, "JOD", "latn", "en"],
  [1, "JOD", "arab", "ar"],
  [-45500, "JOD", "latn", "en"],
  [-45500, "JOD", "arab", "ar"],
  [0, "JOD", "latn", "en"],
  [0, "JOD", "arab", "ar"],
  [1234567, "USD", "latn", "en"],
  [1234567, "USD", "arab", "ar"],
  [999, "USD", "latn", "ar"],
  [100000000, "USD", "arab", "ar"],
];

const INTEGERS = [
  [0, "latn", true],
  [0, "arab", true],
  [7, "arab", true],
  [1000, "latn", true],
  [1000, "arab", true],
  [1234567, "latn", true],
  [1234567, "arab", true],
  [1234567, "latn", false],
  [1234567, "arab", false],
  [-1000, "latn", true],
  [-1000, "arab", true],
];

const DIGITS = [
  ["2026-11-18", "arab"],
  ["١٢٣", "latn"],
  ["no digits here", "arab"],
  ["JOD 45.000", "arab"],
];

const ISOLATES = [
  ["Jane Doe", "ltr"],
  ["جين", "rtl"],
  ["0790 123 456", "ltr"],
  ["Lift A", "auto"],
];

const SANITIZE = ["Jane Doe", "جين Doe", `Jane${"‮"}Doe`, "ends with space "];

/**
 * Counts chosen for the boundaries of Arabic's six CLDR categories, which is where two
 * implementations diverge: the four exact values, both ends of `few` and `many`, the wrap
 * past 100 that puts 103 back into `few`, and a round hundred that is `other`.
 */
const COUNTS = [0, 1, 2, 3, 10, 11, 99, 100, 101, 102, 103, 110, 200, 203, 1000];

function runPython() {
  // **The vectors travel as JSON and are parsed, not interpolated as Python source.** The
  // first version pasted `JSON.stringify(...)` straight into the script, where JavaScript's
  // `true` is not Python's `True` -- so the booleans in the grouping column raised NameError.
  // Parsing also means a vector can hold any string without quoting hazards.
  const vectors = JSON.stringify(
    JSON.stringify({ MONEY, INTEGERS, DIGITS, ISOLATES, SANITIZE, COUNTS }),
  );
  const script = `
import json, sys
sys.path.insert(0, ${JSON.stringify(BACKEND)})
from app.l10n import conventions as c
v = json.loads(${vectors})
money = [c.format_money(a, cur, n, loc) for a, cur, n, loc in v["MONEY"]]
ints = [c.format_integer(val, n, g) for val, n, g in v["INTEGERS"]]
digits = [c.shape_digits(t, n) for t, n in v["DIGITS"]]
isolates = [c.isolate(t, d) for t, d in v["ISOLATES"]]
sanitized = [c.sanitize_untrusted(t) for t in v["SANITIZE"]]
dirs = [c.direction(loc) for loc in ["ar", "en"]]
from app.l10n.messages import plural_category
plurals = [plural_category(loc, n) for loc in ["ar", "en"] for n in v["COUNTS"]]
print(json.dumps({"money": money, "ints": ints, "digits": digits,
                  "isolates": isolates, "sanitized": sanitized, "dirs": dirs,
                  "plurals": plurals}))
`;
  for (const exe of ["python3", "python"]) {
    const r = spawnSync(exe, ["-I", "-c", script], { encoding: "utf8" });
    if (r.status === 0 && r.stdout) return JSON.parse(r.stdout);
    if (r.status !== null && r.stderr) {
      throw new Error(`${exe} failed running the backend conventions:\n${r.stderr}`);
    }
  }
  return null;
}

const python = runPython();

test("the backend implementation is reachable, or the gap is named", { skip: !python }, () => {
  assert.ok(python, "python3 with the backend on sys.path is needed for a real parity check");
});

test("money formats identically in both runtimes", { skip: !python }, () => {
  MONEY.forEach(([amount, currency, numbering, locale], i) => {
    const mine = formatMoney(amount, currency, numbering, locale);
    assert.equal(
      mine,
      python.money[i],
      `${amount} ${currency} ${numbering}/${locale}: web ${JSON.stringify(mine)} vs ` +
        `backend ${JSON.stringify(python.money[i])}`,
    );
  });
});

test("integers format identically, grouping separators included", { skip: !python }, () => {
  INTEGERS.forEach(([value, numbering, grouping], i) => {
    assert.equal(
      formatInteger(value, numbering, grouping),
      python.ints[i],
      `${value} ${numbering} grouping=${grouping}`,
    );
  });
});

test("digit shaping agrees in both directions", { skip: !python }, () => {
  DIGITS.forEach(([text, numbering], i) => {
    assert.equal(shapeDigits(text, numbering), python.digits[i], `${text} -> ${numbering}`);
  });
});

test("isolates agree, controls and all", { skip: !python }, () => {
  ISOLATES.forEach(([text, dir], i) => {
    assert.equal(isolate(text, dir), python.isolates[i], `${text} ${dir}`);
  });
});

test("sanitising untrusted text agrees", { skip: !python }, () => {
  SANITIZE.forEach((text, i) => {
    assert.equal(sanitizeUntrusted(text), python.sanitized[i], JSON.stringify(text));
  });
});

test("direction agrees", { skip: !python }, () => {
  assert.deepEqual([direction("ar"), direction("en")], python.dirs);
});

// ---------------------------------------------------------------- properties, no Python needed

test("an Arabic-locale amount is wrapped in an LTR isolate that is closed", () => {
  const formatted = formatMoney(45000, "JOD", "latn", "ar");
  assert.ok(formatted.startsWith("⁦"), "must open an LTR isolate");
  assert.ok(formatted.endsWith("⁩"), "must close it");
  // The isolate is what stops JOD jumping to the wrong side of its amount.
  assert.equal(formatted, "⁦JOD 45.000⁩");
});

test("an English amount carries no bidi control at all", () => {
  const formatted = formatMoney(45000, "JOD", "latn", "en");
  assert.equal(formatted, "JOD 45.000");
  assert.ok(!/[‪-‮⁦-⁩]/u.test(formatted));
});

test("JOD keeps three minor digits and USD two", () => {
  assert.equal(formatMoney(1, "JOD", "latn", "en"), "JOD 0.001");
  assert.equal(formatMoney(1, "USD", "latn", "en"), "USD 0.01");
});

test("a negative sign sits with the amount, inside the isolate", () => {
  assert.equal(formatMoney(-45500, "JOD", "latn", "ar"), "⁦JOD -45.500⁩");
});

test("untrusted text cannot close an isolate this code opened", () => {
  // A member name carrying PDI would otherwise terminate the run and re-order what follows.
  const hostile = `Jane${"⁩"}${"‮"}Doe`;
  const wrapped = isolate(hostile, "ltr");
  assert.equal(wrapped, "⁦JaneDoe⁩");
  assert.equal((wrapped.match(/⁩/gu) ?? []).length, 1, "exactly one closing PDI");
});

test("a paragraph separator is rejected rather than stripped, and not echoed", () => {
  for (const control of ["\n", "\r", " ", " ", "\u0085", "\t"]) {
    assert.throws(
      () => sanitizeUntrusted(`Jane${control}Doe`),
      (e) => e.message === "text contains a control character" && !e.message.includes("Jane"),
      JSON.stringify(control),
    );
  }
});

test("numbering is never derived from the locale", () => {
  // An Arabic-locale tenant on Latin numerals must get Latin numerals: the choice is the
  // tenant's, made once, and not a property of the string's language.
  assert.equal(formatMoney(45000, "JOD", "latn", "ar"), "⁦JOD 45.000⁩");
  assert.ok(!/[٠-٩]/u.test(formatMoney(45000, "JOD", "latn", "ar")));
});

test("an unknown locale or currency fails closed", () => {
  assert.throws(() => formatMoney(1, "EUR", "latn", "en"), /unsupported currency/);
  assert.throws(() => formatMoney(1, "JOD", "latn", "fr"), /unsupported locale/);
  assert.throws(() => formatMoney(1, "JOD", "hindi", "en"), /unsupported numbering/);
});

test("the plural category agrees in both runtimes", { skip: !python }, () => {
  // **Arabic has six categories and English two**, so a message rendered with the wrong one
  // is wrong in a way an English-speaking author cannot see. The web catalogue grew plural
  // forms for ADM-CC-01's counted headings; this is what stops the two implementations
  // drifting, which is the same argument the money vectors above carry.
  const want = [];
  for (const locale of ["ar", "en"]) {
    for (const count of COUNTS) want.push(pluralCategory(locale, count));
  }
  assert.deepEqual(want, python.plurals);
});

test("a plural category refuses a count it cannot classify", () => {
  assert.throws(() => pluralCategory("en", -1), /must not be negative/);
  assert.throws(() => pluralCategory("en", 1.5), /must be an integer/);
  assert.throws(() => pluralCategory("fr", 1), /unsupported locale/);
});

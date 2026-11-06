"""Derive the measured figures about cite_check.py, rather than typing them.

Review found the same defect in the companion document repeatedly: a corpus
figure written into prose, correct when written and stale by the time it was
read -- because the scan that produced it had excluded part of the tree, or
because a test fixture added to cite_check.py changed the corpus the figure
counted. The assertion total, the one figure printed by the code rather than
typed beside it, was never found wrong. So nothing here is typed: run it and
read the output. No round count is given, in either direction: reviews of this
tool leave no artifact, so a count would be a figure the repository cannot
support.

Four measurements, each independent of the others:

  reverts   the enumerated single-edit reverts of guards in cite_check.py,
            each applied to a copy and run against --self-check. A revert that
            leaves the suite green is a guard nothing watches. The list is
            hand-written and is NOT every possible single-edit revert. Six
            edits are known to survive it and are deliberately outside: four
            change only report attribution or the advisory class -- widening
            MARKED_REGION's character class, making the held separator
            last-wins instead of first-wins, turning the label-cell test from
            all() to any(), and perturbing the summary arithmetic -- one drops
            the provenance line from the output, and one, dropping .strip()
            from the span, weakens the blank-paragraph guard so that a
            whitespace-only paragraph would stop being a hard failure. That
            last one is inert on the pinned baselines, neither of which has
            such a paragraph, which is why it is listed rather than fixed. No
            claim is made beyond the set below.
  chars     every assigned non-surrogate code point that the tool's own
            `invisible` or `suspect` predicate claims, inserted at twelve
            positions in a citation, checking that none produces a silent
            downgrade. Reports the subset where the inserted character alone
            decides the verdict, since the rest cannot fail.
  census    the separator and marker-bounded regions the code actually
            produces across every tracked file in the repository.
  pairs     every two-character visible-ASCII separator, reported or missed.

stdlib only. Nothing in CI runs this, and nothing imports it.
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import contextlib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata

TOOL = pathlib.Path(__file__).with_name("cite_check.py")


def load():
    spec = importlib.util.spec_from_file_location("cite_check", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Every revert is (id, label, exact bytes to replace, replacement). The id is
# for referring to one in review; it carries no other meaning, and the list is
# the enumeration -- the companion document deliberately does not repeat it.
R = [
 (1, "overlap test read as first-paragraph-only",
  "            if touches_overlap(lo, hi):", "            if lo in OVERLAP:"),
 (2, "overlap test as endpoint membership",
  "    return min(lo, hi) <= OVERLAP[-1] and max(lo, hi) >= OVERLAP[0]",
  "    return lo in OVERLAP or hi in OVERLAP"),
 (3, "low window edge moved by one",
  "OVERLAP = range(741, 784)", "OVERLAP = range(742, 784)"),
 (4, "high window edge moved by one",
  "OVERLAP = range(741, 784)", "OVERLAP = range(741, 783)"),
 (5, "malformed-span guard dropped", "        if hi < lo:", "        if False:"),
 (6, "bare-in-overlap hard failure made a no-op",
  "            if touches_overlap(lo, hi):",
  "            if False and touches_overlap(lo, hi):"),
 (7, "dash class replaced by a typed hyphen",
  'DASH = f"[{re.escape(DASH_CHARS)}]"', 'DASH = "-"'),
 (8, "dash derivation bound narrowed to U+3000",
  "DASH_SCAN_BOUND = 0x11000", "DASH_SCAN_BOUND = 0x3000"),
 (9, "minus sign removed from the dash class",
  ') + "\\u2212"  # minus sign: Sm, not Pd, but a real dash', ')'),
 (10, "lower half of the existence test dropped",
  "        if lo < 1 or hi > len(src[which]):", "        if hi > len(src[which]):"),
 (11, "upper half of the existence test dropped",
  "        if lo < 1 or hi > len(src[which]):", "        if lo < 1:"),
 (12, "whole existence guard dropped",
  "        if lo < 1 or hi > len(src[which]):", "        if False:"),
 (13, "paragraph span collapsed to its first paragraph",
  "range(lo, hi + 1)", "range(lo, lo + 1)"),
 (14, "paragraphs() made to drop blank w:p",
  '    return ["".join(t.text or "" for t in p.iter(W + "t")) for p in root.iter(W + "p")]',
  '    return [s for s in ["".join(t.text or "" for t in p.iter(W + "t"))\n'
  '            for p in root.iter(W + "p")] if s.strip()]'),
 (15, "label threshold set to 0", "SHORT = 24", "SHORT = 0"),
 (16, "label threshold set to 7", "SHORT = 24", "SHORT = 7"),
 (17, "hash comparison truncated to four characters",
  "        if got != expect:", "        if got[:4] != expect[:4]:"),
 (18, "hash comparison reduced to its last character",
  "        if got != expect:", "        if got[-1:] != expect[-1:]:"),
 (19, "hash comparison reduced to its first character",
  "        if got != expect:", "        if got[:1] != expect[:1]:"),
 (20, "hash comparison dropped entirely",
  "        if got != expect:", "        if False:"),
 (21, "missing-argument exit dropped", "    if missing:", "    if False:"),
 (22, "blank-paragraph check dropped", "            if not para:", "            if False:"),
 (23, "foreign-character scan dropped",
  "    for line, col, cp, why in foreign_in_citations(text):",
  "    for line, col, cp, why in []:"),
 (24, "prefix inheritance reintroduced",
  "            if m.group(1):\n"
  "                yield n, m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))\n"
  "            else:\n"
  "                lo = int(m.group(4))\n"
  "                yield n, None, lo, int(m.group(5) or lo)",
  "            if m.group(1):\n"
  "                citations.last = m.group(1)\n"
  "                yield n, m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))\n"
  "            else:\n"
  "                lo = int(m.group(4))\n"
  '                yield n, getattr(citations, "last", None), lo, int(m.group(5) or lo)'),
 (25, "invisible() stripped of its printability test",
  "    if not ch.isprintable():\n        return True",
  "    if False:\n        return True"),
 (26, "invisible() stripped of its Mn arm",
  '    if unicodedata.category(ch) in {"Mn", "Me"}:',
  '    if unicodedata.category(ch) in {"Me"}:'),
 (27, "invisible() stripped of its Me arm",
  '    if unicodedata.category(ch) in {"Mn", "Me"}:',
  '    if unicodedata.category(ch) in {"Mn"}:'),
 (28, "U+3164 removed from the zero-width tail",
  '    return ch in "\\u3164\\u115f\\u1160\\uffa0\\u2800"',
  '    return ch in "\\u115f\\u1160\\uffa0\\u2800"'),
 (29, "U+115F removed from the zero-width tail",
  '    return ch in "\\u3164\\u115f\\u1160\\uffa0\\u2800"',
  '    return ch in "\\u3164\\u1160\\uffa0\\u2800"'),
 (30, "U+1160 removed from the zero-width tail",
  '    return ch in "\\u3164\\u115f\\u1160\\uffa0\\u2800"',
  '    return ch in "\\u3164\\u115f\\uffa0\\u2800"'),
 (31, "U+FFA0 removed from the zero-width tail",
  '    return ch in "\\u3164\\u115f\\u1160\\uffa0\\u2800"',
  '    return ch in "\\u3164\\u115f\\u1160\\u2800"'),
 (32, "U+2800 removed from the zero-width tail",
  '    return ch in "\\u3164\\u115f\\u1160\\uffa0\\u2800"',
  '    return ch in "\\u3164\\u115f\\u1160\\uffa0"'),
 (33, "suspect() stripped of its Nd arm",
  '    return (unicodedata.category(ch) in {"Nd", "No", "Nl"}',
  '    return (unicodedata.category(ch) in {"No", "Nl"}'),
 (34, "suspect() stripped of its No arm",
  '    return (unicodedata.category(ch) in {"Nd", "No", "Nl"}',
  '    return (unicodedata.category(ch) in {"Nd", "Nl"}'),
 (35, "suspect() stripped of its Nl arm",
  '    return (unicodedata.category(ch) in {"Nd", "No", "Nl"}',
  '    return (unicodedata.category(ch) in {"Nd", "No"}'),
 (36, "separator region re-bounded to six characters",
  'SEPARATOR_REGION = re.compile(r"([^0-9\\u00b6\\u00a7]*)[0-9]")',
  'SEPARATOR_REGION = re.compile(r"([^0-9\\u00b6\\u00a7]{0,6})[0-9]")'),
 (37, "purity rule dropped from admissible()",
  "    pure = all(c.isspace() or suspect(c) or c in DASH_CHARS for c in chars)\n"
  "    return pure or not any(c.isspace() for c in chars)",
  "    return True"),
 (57, "the dash arm dropped from the purity rule",
  "    pure = all(c.isspace() or suspect(c) or c in DASH_CHARS for c in chars)",
  "    pure = all(c.isspace() or suspect(c) for c in chars)"),
 (58, "the dash-before-a-marker report dropped",
  "                marked = MARKED_REGION.match(after)",
  "                marked = None"),
 (59, "the dash-before-a-marker report fired for any character",
  "                    if ch in DASH_CHARS:",
  "                    if True:"),
 (60, "the marker-bounded region admitted without the admission test",
  "                if marked is None or not admissible(marked.group(1)):",
  "                if marked is None:"),
 (38, "vanished-citation check dropped for a numeral inside the run",
  '                if any(unicodedata.category(c) in {"Nd", "No", "Nl"} for c in run):',
  "                if False:"),
 (39, "vanished-citation check dropped for a readable digit just past it",
  '                elif k and k < len(rest) and "0" <= rest[k] <= "9":',
  "                elif False:"),
 (40, "str.splitlines() restored in the scan",
  '    for n, line in enumerate(text.split("\\n"), 1):\n'
  '        for m in re.finditer("\\u00b6", line):',
  "    for n, line in enumerate(text.splitlines(), 1):\n"
  '        for m in re.finditer("\\u00b6", line):'),
 (41, "str.splitlines() restored in citations()",
  '    # split("\\n"), not splitlines(): see foreign_in_citations.\n'
  '    for n, line in enumerate(text.split("\\n"), 1):',
  '    # split("\\n"), not splitlines(): see foreign_in_citations.\n'
  "    for n, line in enumerate(text.splitlines(), 1):"),
 (42, "reported column made zero-based",
  '        hard.append(f"{doc.name}:{line}  col {col + 1}  {what}"',
  '        hard.append(f"{doc.name}:{line}  col {col}  {what}"'),
 (43, "hard/advisory split collapsed to advisory",
  "        hard.append(f\"{doc.name}:{line}  col {col + 1}  {what}\"",
  "        advisory.append(f\"{doc.name}:{line}  col {col + 1}  {what}\""),
 (44, "word boundary removed from the prefix pattern",
  'CITE = re.compile(rf"\\b(EIP|TSD)', 'CITE = re.compile(rf"(EIP|TSD)'),
 (45, "CITE leading digit run widened to \\d",
  'CITE = re.compile(rf"\\b(EIP|TSD)\\s+¶([0-9]+){SPAN}|¶([0-9]+){SPAN}")',
  'CITE = re.compile(rf"\\b(EIP|TSD)\\s+¶(\\d+){SPAN}|¶(\\d+){SPAN}")'),
 (46, "SPAN digit run widened to \\d",
  'SPAN = rf"(?:\\s*{DASH}\\s*([0-9]+))?"', 'SPAN = rf"(?:\\s*{DASH}\\s*(\\d+))?"'),
 (47, "unspaced-region rule dropped from admissible()",
  "    return pure or not any(c.isspace() for c in chars)",
  "    return pure"),
 (55, "unspaced-region rule narrowed back to a single character",
  "    return pure or not any(c.isspace() for c in chars)",
  "    return pure or len(chars) == 1"),
 (56, "the section sign removed from the region's terminators",
  'SEPARATOR_REGION = re.compile(r"([^0-9\\u00b6\\u00a7]*)[0-9]")',
  'SEPARATOR_REGION = re.compile(r"([^0-9\\u00b6]*)[0-9]")'),
 (49, "held-separator report dropped",
  "            if held is not None and not reported:",
  "            if False:"),
 (50, "held-separator report fired even when displaced",
  "            if held is not None and not reported:",
  "            if held is not None:"),
 (51, "the space arm of the held separator dropped",
  "                if ch in DASH_CHARS or ch == \" \":",
  "                if ch in DASH_CHARS:"),
 (52, "the dash arm of the held separator dropped",
  "                if ch in DASH_CHARS or ch == \" \":",
  "                if ch == \" \":"),
 (53, "the region extent re-bounded to thirty characters",
  'SEPARATOR_REGION = re.compile(r"([^0-9\\u00b6\\u00a7]*)[0-9]")',
  'SEPARATOR_REGION = re.compile(r"([^0-9\\u00b6\\u00a7]{0,30})[0-9]")'),
 (54, "the ASCII-letter exclusion restored to the region extent",
  'SEPARATOR_REGION = re.compile(r"([^0-9\\u00b6\\u00a7]*)[0-9]")',
  'SEPARATOR_REGION = re.compile(r"([^0-9A-Za-z\\u00b6\\u00a7]*)[0-9]")'),
 (61, "the marker-bounded region's extent re-bounded to three characters",
  'MARKED_REGION = re.compile(r"([^0-9\\u00b6\\u00a7]*)[\\u00b6\\u00a7]")',
  'MARKED_REGION = re.compile(r"([^0-9\\u00b6\\u00a7]{0,3})[\\u00b6\\u00a7]")'),
 (62, "the one-report-per-marked-region break dropped",
  "                        break\n", "\n"),
 (48, "CITE_TAIL digit run widened to \\d",
  'CITE_TAIL = re.compile(rf"([0-9]+){SPAN}")',
  'CITE_TAIL = re.compile(rf"(\\d+){SPAN}")'),
]


def reverts() -> int:
    src = TOOL.read_text()
    bad, by_raise, survived = [], [], []
    for num, label, old, new in R:
        if src.count(old) != 1:
            bad.append(num)
            print(f"  ANCHOR  ({num}) {label}: {src.count(old)} matches")
            continue
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "mutant.py")
            pathlib.Path(p).write_text(src.replace(old, new))
            r = subprocess.run([sys.executable, "-I", p, "--self-check"],
                               capture_output=True, text=True)
            if r.returncode == 0:
                survived.append(num)
                print(f"  SURVIVED ({num}) {label}")
            else:
                tail = (r.stderr or "").strip().splitlines()
                if tail and not tail[-1].startswith("AssertionError"):
                    by_raise.append(num)
        finally:
            shutil.rmtree(d)
    print(f"reverts   {len(R)} applied, {len(survived)} survived {survived}, "
          f"{len(R) - len(survived) - len(by_raise)} died on an assertion, "
          f"{len(by_raise)} by raising inside the code under test {by_raise}")
    if bad:
        print(f"          {len(bad)} anchors no longer match: {bad}")
    return 1 if survived or bad else 0


TEMPLATES = [
    "see \u00b6{}756 there", "see \u00b67{}56 there", "see \u00b675{}6 there",
    "see \u00b6756{} there", "see \u00b6{}735-745 there", "see \u00b67{}35-745 there",
    "see \u00b6735{}-745 there", "see \u00b6735-{}745 there",
    "see \u00b6735-74{}5 there", "see \u00b6735-745{} there",
    "see \u00b67" + "\u00ad" * 3 + "{}" + "\u00ad" * 4 + "56 there",
    "see \u00b6735 {} 745 there",
]


def chars() -> int:
    cc = load()

    def scan(text):
        return any(True for _ in cc.foreign_in_citations(text))

    def parse(text):
        for _, which, lo, hi in cc.citations(text):
            if hi < lo or (which is None and cc.touches_overlap(lo, hi)):
                return True
        return False

    inv, num = [], []
    for cp in range(0x110000):
        ch = chr(cp)
        cat = unicodedata.category(ch)
        if cat in ("Cn", "Cs") or cp in (0x0A, 0x0D):
            continue
        if cc.invisible(ch):
            inv.append(ch)
        elif cat in ("Nd", "No", "Nl") and not ("0" <= ch <= "9"):
            num.append(ch)
    pop = inv + num
    total = down = strict = strict_down = masked = vacuous = 0
    for tpl in TEMPLATES:
        base = scan(tpl.format(""))
        for ch in pop:
            s = tpl.format(ch)
            total += 1
            sc, pa = scan(s), parse(s)
            if not (sc or pa):
                down += 1
            if base:
                masked += 1
            elif pa:
                vacuous += 1
            else:
                strict += 1
                if not sc:
                    strict_down += 1
    print(f"chars     population {len(inv)} invisible + {len(num)} non-ASCII "
          f"numerals = {len(pop)}, assigned and non-surrogate, less U+000A/U+000D")
    print(f"          {len(TEMPLATES)} positions, {total} cases, {down} downgrades")
    print(f"          {vacuous} vacuous (the parse is hard whatever is inserted), "
          f"{masked} masked (the scan fires with nothing inserted)")
    print(f"          {strict} where the inserted character alone decides, "
          f"{strict_down} downgrades")
    # The predicate above reimplements check()'s hard set; bound the drift.
    paras = ["para %d with enough text to clear the label threshold" % i
             for i in range(1, 900)]
    paras[499], paras[600], paras[700] = "", "R", "Critical"
    src = {"EIP": list(paras), "TSD": list(paras)}
    import random
    rng = random.Random(0)
    dis = 0
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "x.md"
        for _ in range(3000):
            s = rng.choice(TEMPLATES).format(rng.choice(pop))
            p.write_text(s, encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                code = cc.check(p, src, False)
            if (code == 1) != (scan(s) or parse(s)):
                dis += 1
    print(f"          3000 of them re-run through check() itself, "
          f"{dis} disagreements with that predicate")
    return 1 if down or strict_down or dis else 0


def census() -> int:
    cc = load()
    files = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                           cwd=TOOL.parent.parent.parent).stdout.split()
    root = TOOL.parent.parent.parent
    sep, marked_adm, marked_dash = [], [], []
    unspaced = {}
    for f in files:
        try:
            text = (root / f).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for ln, line in enumerate(text.split("\n"), 1):
            for m in re.finditer("\u00b6", line):
                rest = line[m.end():]
                tail = cc.CITE_TAIL.match(rest)
                if tail is None:
                    continue
                after = rest[tail.end():]
                region = cc.SEPARATOR_REGION.match(after)
                if region is not None:
                    sep.append((f, ln, region.group(1)))
                    if region.group(1) and not any(c.isspace() for c in region.group(1)):
                        unspaced[f] = unspaced.get(f, 0) + 1
                    continue
                mk = cc.MARKED_REGION.match(after)
                if mk is None or not mk.group(1):
                    continue
                if cc.admissible(mk.group(1)):
                    marked_adm.append((f, ln, mk.group(1)))
                elif any(c in cc.DASH_CHARS for c in mk.group(1)):
                    marked_dash.append((f, ln, mk.group(1)))
    per = {}
    for f, _, _ in sep:
        per[f] = per.get(f, 0) + 1
    print(f"census    {len(sep)} separator regions across {len(per)} files, "
          f"{sum(unspaced.values())} of them unspaced {unspaced or '{}'}")
    for doc in ("knowledge/03-Modules/MOD-004/SCENARIOS.md",
                "knowledge/03-Modules/MOD-004/MOD-004.md"):
        print(f"            {per.get(doc, 0):4d} in {doc}")
    dashes = [r for r in marked_adm if any(c in cc.DASH_CHARS for c in r[2])]
    print(f"          {len(marked_adm)} admissible marker-bounded regions: "
          f"{len(marked_adm) - len(dashes)} holding no dash, {len(dashes)} holding one")
    for f, ln, reg in marked_adm:
        print(f"            {f}:{ln} {reg!r}")
    cnt = {}
    for _, _, reg in marked_dash:
        for c in reg:
            if c in cc.DASH_CHARS:
                cnt[c] = cnt.get(c, 0) + 1
    print(f"          {len(marked_dash)} inadmissible marker-bounded regions hold a "
          f"dash; census " + ", ".join(f"U+{ord(k):04X} x{v}" for k, v in sorted(cnt.items())))
    hyphenated = sum(1 for _, _, r in marked_dash
                     if re.search(r"[A-Za-z]-[A-Za-z]", r))
    print(f"          {hyphenated} of those hold a hyphen between two letters")
    return 0


def pairs() -> int:
    cc = load()
    vis = [chr(c) for c in range(0x21, 0x7F)]

    def scan(text):
        return any(True for _ in cc.foreign_in_citations(text))

    tpl = "see \u00b6735{}{}745 there"
    missed = [(a, b) for a in vis for b in vis if not scan(tpl.format(a, b))]
    dd = sum(1 for a, b in missed if a.isdigit() and b.isdigit())
    dashd = sum(1 for a, b in missed
                if (a in cc.DASH_CHARS and b.isdigit())
                or (a.isdigit() and b in cc.DASH_CHARS))
    print(f"pairs     {len(vis) ** 2} two-character visible-ASCII separators, "
          f"{len(vis) ** 2 - len(missed)} reported by the scan, {len(missed)} missed")
    print(f"          {dd} digit-digit, {dashd} dash-plus-digit, "
          f"{len(missed) - dd - dashd} other")
    return 1 if len(missed) - dd - dashd else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("what", nargs="*", default=["reverts", "chars", "census", "pairs"],
                    choices=["reverts", "chars", "census", "pairs"])
    a = ap.parse_args()
    rc = 0
    for name in a.what:
        rc |= {"reverts": reverts, "chars": chars,
               "census": census, "pairs": pairs}[name]()
    return rc


if __name__ == "__main__":
    sys.exit(main())

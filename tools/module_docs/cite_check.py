"""Check the paragraph citations in a Veyro module document against the pinned
baselines, and print the citation-to-source evidence listing a reviewer needs
to judge topic match.

Both baselines number paragraphs 741-783, and there the two texts are
unrelated: EIP 746-773 is the Definition of Ready table while TSD 741-772 is
the data-isolation model, so EIP 756 is the Scenario Review gate and TSD 756
is cache key prefixing. A citation in that window that carries no explicit
`EIP`/`TSD` prefix is therefore a latent defect: reflowing a table cell or
inserting a row above it silently re-points it, with nothing visible changing.
That is the one thing this tool hard-fails on, and it tests the whole cited
span rather than its first paragraph.

Deliberately NOT done: this tool does not guess which baseline a bare citation
means. Inheriting the nearest preceding prefix sounds helpful and is wrong --
it leaks across list items, headings and table rows, and a confident wrong
resolution is worse than an honest unresolved one. Bare citations outside the
window are reported, not resolved; the document's own declared ranges settle
them. Topic match needs human judgement, which is what --table is for.

stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
# 1-based document-order w:p including blanks, descendant w:t concatenated:
# the extraction the pinned source extracts declare.
# An editor reflowing a table may autocorrect the hyphen to an en dash or
# space it out. Reading "¶735–745" as the single paragraph 735 would silently
# downgrade a span that enters the overlap, so every dash spelling is taken.
DASH = r"[-‐‑‒–—―−]"
SPAN = rf"(?:\s*{DASH}\s*(\d+))?"
CITE = re.compile(rf"\b(EIP|TSD)\s+¶(\d+){SPAN}|¶(\d+){SPAN}")
OVERLAP = range(741, 784)
SHORT = 24  # a span shorter than this is a table label, not a rule


def paragraphs(docx: Path) -> list[str]:
    with zipfile.ZipFile(docx) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    return ["".join(t.text or "" for t in p.iter(W + "t")) for p in root.iter(W + "p")]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def citations(text: str):
    """Yield (line, doc_or_None, first, last). doc is None when the citation
    carries no explicit prefix; no prefix is ever inherited."""
    for n, line in enumerate(text.splitlines(), 1):
        for m in CITE.finditer(line):
            if m.group(1):
                yield n, m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))
            else:
                lo = int(m.group(4))
                yield n, None, lo, int(m.group(5) or lo)


def touches_overlap(lo: int, hi: int) -> bool:
    """True when the span meets 741-783. Tests endpoints rather than iterating,
    so a reversed span cannot read as empty and a huge one cannot hang."""
    return min(lo, hi) <= OVERLAP[-1] and max(lo, hi) >= OVERLAP[0]


def check(doc: Path, src: dict[str, list[str]], table: bool) -> int:
    hard: list[str] = []
    advisory: list[str] = []
    rows: list[tuple[int, str, int, str]] = []
    total = bare = resolved = 0

    for line, which, lo, hi in citations(doc.read_text(encoding="utf-8")):
        total += 1
        if hi < lo:
            hard.append(f"{doc.name}:{line}  ¶{lo}-{hi}  MALFORMED_SPAN  "
                        f"end precedes start")
            continue
        if which is None:
            bare += 1
            if touches_overlap(lo, hi):
                hard.append(f"{doc.name}:{line}  ¶{lo}-{hi}  BARE_IN_OVERLAP  "
                            f"span touches 741-783, where both baselines differ")
            else:
                advisory.append(f"{doc.name}:{line}  ¶{lo}-{hi}  BARE_UNRESOLVED  "
                                f"settled by the document's declared ranges, not here")
            continue
        if lo < 1 or hi > len(src[which]):
            hard.append(f"{doc.name}:{line}  {which} ¶{lo}-{hi}  OUT_OF_RANGE")
            continue
        resolved += 1
        span = [src[which][p - 1].strip() for p in range(lo, hi + 1)]
        for offset, body in enumerate(span):
            if not body:
                hard.append(f"{doc.name}:{line}  {which} ¶{lo + offset}  BLANK_PARAGRAPH")
            rows.append((line, which, lo + offset, body))
        if all(len(b) < SHORT for b in span):
            advisory.append(f"{doc.name}:{line}  {which} ¶{lo}-{hi}  LABEL_CELLS  "
                            f"{' / '.join(span)[:60]}")

    print(f"doc {doc.name} sha256 {sha256(doc)}")
    print(f"{total} citations: {resolved} explicitly prefixed and resolved, "
          f"{bare} bare and not resolved here, "
          f"{total - resolved - bare} malformed or out of range")
    print(f"{len(hard)} hard, {len(advisory)} advisory")
    for m in hard:
        print(f"  HARD      {m}")
    for m in advisory:
        print(f"  advisory  {m}")
    if table:
        print("\n| doc:line | citation | source paragraph |")
        print("|---|---|---|")
        for line, which, n, body in rows:
            print(f"| {doc.name}:{line} | {which} ¶{n} | "
                  f"{body.replace('|', chr(92) + '|')[:140]} |")
    return 1 if hard else 0


def self_check() -> int:
    """The span hole this tool exists to not have. Run: --self-check."""
    src = {"EIP": [f"eip para {i}" * 4 for i in range(1, 900)],
           "TSD": [f"tsd para {i}" * 4 for i in range(1, 900)]}
    import io
    import contextlib

    import tempfile

    def run(text: str) -> int:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d) / "selfcheck.md"
            tmp.write_text(text, encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                return check(tmp, src, False)

    # A bare span entering the overlap from below must fail, not just one whose
    # first paragraph is inside it.
    assert run("see ¶735-745 there") == 1, "bare span entering overlap must fail"
    assert run("see ¶780-790 there") == 1, "bare span leaving overlap must fail"
    assert run("see ¶750 there") == 1, "bare single inside overlap must fail"
    # No prefix is inherited: a preceding explicit prefix must not rescue it.
    assert run("TSD ¶800 and then ¶750") == 1, "prefix must not be inherited"
    # Outside the window a bare citation is advisory, not a failure.
    assert run("see ¶1200 there") == 0, "bare outside overlap is advisory"
    # Explicit prefixes resolve and pass.
    assert run("EIP ¶750 and TSD ¶756") == 0, "explicit prefixes must pass"
    # Out-of-range is a hard failure.
    assert run("EIP ¶9999") == 1, "out-of-range must fail"
    # Round seven found both of these failing open.
    assert run("see ¶783-741 there") == 1, "reversed span touching overlap must fail"
    assert run("see ¶735–745 there") == 1, "en-dash span entering overlap must fail"
    # Round eight: the two assertions above use a BARE reversed span, which
    # touches_overlap rejects on its own, so neither pinned the hi<lo guard --
    # dropping it left all nine green. This one exercises the guard directly:
    # the prefixed form is the half that reported a false `resolved` count.
    assert run("EIP ¶745-735") == 1, "prefixed reversed span must be malformed, not resolved"
    print("self-check: 10 assertions passed")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", type=Path)
    ap.add_argument("--eip", type=Path)
    ap.add_argument("--tsd", type=Path)
    # Pins are mandatory for a real run: a check that can be invoked without
    # them is a check that reports confidence it has not earned.
    ap.add_argument("--eip-sha256")
    ap.add_argument("--tsd-sha256")
    ap.add_argument("--table", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args()

    if a.self_check:
        return self_check()
    missing = [n for n, v in (("--doc", a.doc), ("--eip", a.eip), ("--tsd", a.tsd),
                              ("--eip-sha256", a.eip_sha256),
                              ("--tsd-sha256", a.tsd_sha256)) if not v]
    if missing:
        print(f"MISSING_ARGUMENTS {' '.join(missing)}")
        return 2
    for path, expect in ((a.eip, a.eip_sha256), (a.tsd, a.tsd_sha256)):
        got = sha256(path)
        if got != expect:
            print(f"BASELINE_MISMATCH {path}: {got} != {expect}")
            return 2
    return check(a.doc, {"EIP": paragraphs(a.eip), "TSD": paragraphs(a.tsd)}, a.table)


if __name__ == "__main__":
    sys.exit(main())

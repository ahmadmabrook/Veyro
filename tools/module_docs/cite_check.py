"""Check the paragraph citations in a Veyro module document against the pinned
baselines, and print the citation-to-source evidence listing a reviewer needs
to judge topic match.

Both baselines number paragraphs 741-783, and there the two texts are
unrelated: EIP 746-773 is the Definition of Ready table while TSD 741-772 is
the data-isolation model, so EIP 756 is the Scenario Review gate and TSD 756
is cache key prefixing. A citation in that window that carries no explicit
`EIP`/`TSD` prefix is therefore a latent defect: reflowing a table cell or
inserting a row above it silently re-points it, with nothing visible changing.
That is the defect this tool exists for, and it tests the whole cited span
rather than its first paragraph. Five other classes are hard failures too, and
they divide in two. TWO could hide a bare-in-overlap citation and exist for
that reason: a character inside a citation that makes the parser read something
other than what is written, and a separator the parser did not read as part of
a span -- a dash it declined, or whitespace splitting the digits. THREE cannot.
A citation outside the source's paragraph count and a cited blank paragraph are
reachable only through an explicitly prefixed citation, which the overlap rule
never examines. The malformed-span guard looks as though it belongs with the
first two and does not: check() reports it and continues BEFORE the bare
branch, and touches_overlap tests min and max, so dropping the guard turns a
reversed bare span into a BARE_IN_OVERLAP rather than into silence. Most such
spans do fall from hard to advisory when it is dropped; none is lost, which is
the claim. What it actually protects is a PREFIXED reversed span, which would
otherwise resolve to an empty paragraph set, so it belongs in the second group.
Two earlier versions of this paragraph were wrong here: the first claimed all
five guarded the bare-in-overlap case, the second moved only two out.

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
import unicodedata
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
# 1-based document-order w:p including blanks, descendant w:t concatenated:
# the extraction the pinned source extracts declare.
# An editor reflowing a table may autocorrect the hyphen to an en dash or space
# it out, and reading "¶735–745" as the single paragraph 735 would silently
# downgrade a span that enters the overlap. The class below is therefore derived
# from every Unicode dash-punctuation (Pd) character below the scan bound, plus
# exactly one dash-like character outside that category: the minus sign (U+2212,
# Sm). The soft hyphen is deliberately NOT here -- it is Cf, not a dash, and
# treating it as one is what made a substituted soft hyphen parse as a span;
# foreign_in_citations reports it instead. Deriving the list rather than typing
# it is what makes U+FF0D, U+FE63, U+2E3A and U+2E3B fall in without being
# named. The bound is a block boundary above the highest Pd code point known at
# writing (U+10EAD YEZIDI HYPHENATION MARK), not one past it, so a dash added
# above U+10FFF would need it raised. The self-check pins the breadth only up to
# U+FF0D: a bound lowered to U+FF0E or above still passes.
DASH_SCAN_BOUND = 0x11000
DASH_CHARS = "".join(
    chr(c) for c in range(DASH_SCAN_BOUND)
    if unicodedata.category(chr(c)) == "Pd"
) + "\u2212"  # minus sign: Sm, not Pd, but a real dash
DASH = f"[{re.escape(DASH_CHARS)}]"
# The digit run is ASCII-only on purpose. `\d` matches any Nd, so an
# Arabic-Indic or fullwidth digit would be absorbed into the number and change
# the paragraph VALUE with nothing reported -- a reader sees a plausible figure
# and the parser reads a different one. Restricting the run to [0-9] turns such
# a character into a separator, where foreign_in_citations reports it.
SPAN = rf"(?:\s*{DASH}\s*([0-9]+))?"
CITE = re.compile(rf"\b(EIP|TSD)\s+¶([0-9]+){SPAN}|¶([0-9]+){SPAN}")
# The four reasons a citation's text is not what the parser reads. They are
# constants rather than literals at the yield sites so the reported reason
# cannot drift from the branch that found it. An earlier version said three
# and had four, having gained SPLIT_RUN without the count being touched.
NO_DIGITS = "digits do not immediately follow"
NOT_A_DASH = "separator between the digits is not a dash"
UNUSED_DASH = "the parser did not read this dash as a span separator"
SPLIT_RUN = "whitespace splits the digits; the parser read only the first run"
OVERLAP = range(741, 784)
SHORT = 24  # every paragraph of the span shorter than this: a label, not a rule


def paragraphs(docx: Path) -> list[str]:
    with zipfile.ZipFile(docx) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    return ["".join(t.text or "" for t in p.iter(W + "t")) for p in root.iter(W + "p")]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def citations(text: str):
    """Yield (line, doc_or_None, first, last). doc is None when the citation
    carries no explicit prefix; no prefix is ever inherited."""
    # split("\n"), not splitlines(): see foreign_in_citations.
    for n, line in enumerate(text.split("\n"), 1):
        for m in CITE.finditer(line):
            if m.group(1):
                yield n, m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))
            else:
                lo = int(m.group(4))
                yield n, None, lo, int(m.group(5) or lo)


# A hand-typed terminator set was the wrong boundary: it disagreed with the
# regex that parses the token, so a tab or a space between the digits ended the
# scan early while the parser read straight past it. The boundary is now derived
# from the parser's own grammar instead. CITE_TAIL is exactly the tail of CITE.
CITE_TAIL = re.compile(rf"([0-9]+){SPAN}")
# The whole region between one digit run and the next, unbounded in length,
# because the parser's own separator is unbounded: a hand-typed cap of six
# characters let seven characters of padding hide a soft hyphen completely.
# A pilcrow or a section sign ends the region, because each starts a DIFFERENT
# reference, so the number after it belongs to that reference and not to this
# citation: "\u00b61211-1212, \u00b61244", and ADR-0002's "EIP \u00a78 \u00b6749-755/\u00a721.5", where
# the region "/\u00a7" carries no whitespace and was reported until the section sign
# was added here. Only these two markers are terminators; no other character
# introduces a reference in this corpus. An ASCII letter used to end the region
# too, described as "precision only".
# That was false: it made a single ASCII letter in the dash position silent
# while a single letter in any other script was a hard failure. Prose is kept
# out by the purity rule below -- a letter makes a region impure wherever it
# appears -- not by the region's extent, so the exclusion is gone.
SEPARATOR_REGION = re.compile(r"([^0-9\u00b6\u00a7]*)[0-9]")
# The same span of text, bounded by a reference marker instead of a digit.
MARKED_REGION = re.compile(r"([^0-9\u00b6\u00a7]*)[\u00b6\u00a7]")


def invisible(ch: str) -> bool:
    """True for a character a reader cannot see.

    str.isprintable() does the bulk of the work and does more than it looks:
    it is False for Cc, Cf, Cs, Co, Cn, Zl, Zp **and every Zs except the ASCII
    space**. So the tab, the soft hyphen, the zero-width characters, the line
    and paragraph separators and the non-ASCII spaces are all covered by it,
    and the ordinary space is the one Zs it admits -- which is what we want,
    since a space is the legitimate separator. An earlier version listed Zs
    separately and then had to exclude the ASCII space again; the two
    cancelled, and both are gone.

    What it does not cover: combining and enclosing marks (Mn, Me), which
    render on the preceding character rather than as themselves, and a short
    tail of printable characters that render as nothing at all.
    """
    if not ch.isprintable():
        return True
    if unicodedata.category(ch) in {"Mn", "Me"}:
        return True
    return ch in "\u3164\u115f\u1160\uffa0\u2800"


def suspect(ch: str) -> bool:
    """True for a character that must not appear inside a citation.

    Two kinds. Invisible, which is what makes a misparse silent. And a digit
    that is not an ASCII digit -- a superscript, a circled number, an
    Arabic-Indic or fullwidth digit -- which reads to a human as part of the
    figure while the parser stops at it or absorbs it, so the paragraph number
    the reader sees is not the one resolved.
    """
    if invisible(ch):
        return True
    return (unicodedata.category(ch) in {"Nd", "No", "Nl"}
            and not ("0" <= ch <= "9"))


def foreign_in_citations(text: str):
    """Yield (line, column, codepoint_or_None, why) for citations whose text is
    not what the parser will read it as. Every report is a hard failure, and
    the converse does NOT hold -- this is not every such citation. The scope
    paragraph below says what it does not reach; "\u00b6735 ~745" is one it misses.

    Two shapes:

    * A separator between the digits that is not a legal dash. A soft hyphen
      between the digits of 756 leaves the parser reading the bare citation 7,
      and would make it read the span 7-56 if the soft hyphen were treated as a
      dash -- either way a hard failure becomes an advisory. Reading such a
      character as a dash fixes the case where it was substituted for one and
      breaks the case where it was inserted; removing it does the reverse.
      Neither is inferred -- it is reported, and the meaning stays the
      author's.

    * A pilcrow followed by something that is meant as a number and is not one
      the parser can read: "\u00b6 756", or Arabic-Indic or fullwidth digits.
      Such a citation vanishes from the count altogether rather than failing.

    **Scope, stated exactly, because four earlier versions of this comment
    overstated it.** There are THREE reporting branches, not the two the
    "Two shapes" list above once covered, and TWO regions, not one. The
    regions both start at the end of the citation's digit run; they differ in
    what ends them. SEPARATOR_REGION ends at the next ASCII digit -- two
    numbers with something between them. MARKED_REGION ends at the next
    reference marker, and is tried only when no ASCII digit bounds the text,
    so there may be no second number at all ("\u00b6700-\u00b6" at end of line is
    reported). Both are admitted by the same two grounds, which are no longer
    in this function: they are admissible(), one copy, because the same rule
    stated twice drifted. The grounds, for reference:

    * PURE: every character in it is whitespace, suspect **or a dash**. The
      dash belongs to the rule rather than to the yield loop, because a region
      of dashes and spaces ("\u00b6700- -800") is admitted by nothing else. One
      ordinary printable character of real width drops a SPACED region, which
      is what keeps prose out: an earlier version stopped only at an ASCII
      letter, so it ran straight through Arabic text, which contains none, and
      hard-failed the prose between the two numbers. No character count is
      given -- the one written here three times was not reproducible from any
      version of the code, since a held space is never one of the characters
      reported.

    * UNSPACED: the region holds no whitespace, which makes it the separator
      position. This ground does NOT ask whether the characters are ordinary,
      so a comma, a colon, a per-cent sign, a letter in any script or a run
      such as ".." or "->" jammed between two digit runs IS reported. An
      earlier version tested LENGTH here and admitted one character only. That
      caught "~" and missed "..", which is this project's own range notation
      ("ADR-0001..0005"), so the defect this tool exists for was unreported in
      the house idiom. Whitespace is the discriminator because a prose
      separator between two numbers carries a space and a run jammed between
      the digits does not.

    So a directional mark or a joiner is legal in prose where ordinary
    punctuation or a word separates it from the numbers, which
    `SCN-MOD-004-091` needs, and is reported where it stands alone between two
    numbers, because that is indistinguishable from a tampered span separator
    and the tool declines to infer which was meant.

    Lines are split on "\n" alone, never str.splitlines(), which consumes
    U+000B, U+000C, U+000D, U+001C-001E, U+0085, U+2028 and U+2029 as line
    boundaries -- a vertical tab dropped mid-number would vanish before any
    scan could see it, and a carriage return is caught for the same reason:
    "\u00b67\r56" is reported. split("\n") honours U+000A and nothing else, which
    is the point: U+000D is one of the characters splitlines() consumes and
    the split does not, so a carriage return dropped mid-number is reported
    rather than swallowed. A span broken across a U+000A is not -- the scan
    runs per line, so the two halves are never seen together.
    """
    for n, line in enumerate(text.split("\n"), 1):
        for m in re.finditer("\u00b6", line):
            rest = line[m.end():]
            tail = CITE_TAIL.match(rest)
            if tail is None:
                # A pilcrow whose number the parser cannot read. Step over
                # whitespace and suspect characters; if a numeral of any kind
                # is behind them, the citation was meant and has vanished.
                k = 0
                while k < len(rest) and (rest[k].isspace() or suspect(rest[k])):
                    k += 1
                run = rest[:k]
                # A numeral inside the run means the number itself was written
                # in digits the parser cannot read ("\u00b6\u0667\u0665\u0666");
                # a readable digit just past the run means it was pushed out of
                # reach ("\u00b6 756"). Either way the citation was meant and
                # has vanished from the count.
                if any(unicodedata.category(c) in {"Nd", "No", "Nl"} for c in run):
                    yield n, m.end(), None, NO_DIGITS
                elif k and k < len(rest) and "0" <= rest[k] <= "9":
                    yield n, m.end(), None, NO_DIGITS
                continue
            after = rest[tail.end():]
            region = SEPARATOR_REGION.match(after)
            if region is None:
                # No following ASCII digit, so there is no second number for
                # this citation to be separated from -- unless a reference
                # marker is what stands in the way. A dash stranded before one
                # is a span the parser declined: "\u00b6700-\u00b6800" reads to a human
                # as a span straddling the overlap and parses as the bare
                # citation 700, both endpoints outside it, nothing reported.
                #
                # ONLY a dash counts here. A marker means the next number
                # belongs to a different reference, so a separator before one
                # is a list rather than a collapse: "\u00b6750/\u00b6773",
                # "\u00b61208/\u00b61969", "\u00b61206/\u00b61241", "\u00b61237/\u00b61206" and
                # "\u00b6749-755/\u00a721.5" are all live notation in this repository,
                # and all of them "/".
                #
                # The restriction is established on the whole corpus rather
                # than argued from those, by `measure.py census`, which
                # enumerates every marker-bounded region the code produces and
                # prints each admissible one with its file, line and content.
                # NO COUNT IS TYPED HERE. Three were, in one earlier draft of
                # this comment, and two of the three were wrong before it was
                # ever committed, because a fixture added to the suite below
                # changed the corpus being counted -- the exact failure
                # measure.py exists to end. Run it; the shape of its output is
                # the argument: the admissible regions are those "/" citations
                # plus this suite's own fixtures, and every other dash-bearing
                # region is spaced prose, far more often a hyphen inside a
                # hyphenated word ("read-only", "break-glass") than a dash
                # between two numbers.
                #
                # The cost of "only a dash", stated rather than implied: every
                # OTHER character in this position is silent, so "\u00b6700~\u00b6800"
                # draws nothing while "\u00b6700~800" is a hard failure. No live
                # instance exists; the asymmetry is a context distinction, not
                # a character one -- a marker introduces the next number as its
                # own reference, so there is no span to collapse -- but it is
                # wider than the "/" evidence on its own would carry. An
                # invisible character before a marker is silent too; it hides
                # no span, since the parser and a reader both read the first
                # number and nothing is misread.
                marked = MARKED_REGION.match(after)
                if marked is None or not admissible(marked.group(1)):
                    continue
                for offset, ch in enumerate(marked.group(1)):
                    if ch in DASH_CHARS:
                        yield (n,
                               m.end() + tail.end() + marked.start(1) + offset,
                               ord(ch), UNUSED_DASH)
                        break
                continue
            chars = region.group(1)
            # Two reasons to examine the region, and nothing else is examined.
            #
            # Pure: every character is whitespace, suspect or a dash. This is
            # what keeps prose out -- one ordinary character with real width
            # means the following number is a separate thing.
            #
            # Unspaced: the region holds no whitespace at all, so it is the
            # separator position. A non-dash there collapses a span silently:
            # "\u00b6735~745" and "\u00b6735..745" both read to a human as spans into
            # the overlap and both parse as the bare citation 735.
            #
            # Whitespace is the discriminator, not length. A separator written
            # in prose between two numbers carries a space -- "\u00b6500, 600",
            # "\u00b6500 (600)", "\u00b6735 to 745" -- while a run jammed between the
            # digits does not. An earlier version tested length instead and
            # admitted one character only, which caught "~" and missed "..",
            # ".." being this project's own range notation ("ADR-0001..0005",
            # "MOD-000..003"): the defect this tool exists for, written in the
            # house idiom, unreported. The length test had no more basis than
            # the ASCII-letter asymmetry removed above.
            if not admissible(chars):
                continue
            held = None
            reported = False
            for offset, ch in enumerate(chars):
                col = m.end() + tail.end() + region.start(1) + offset
                if ch in DASH_CHARS or ch == " ":
                    # A dash or a space here is one the parser did NOT read as
                    # part of a span separator: a region exists at all only
                    # because SPAN failed between the two digit runs, and SPAN
                    # consumes "\\s*DASH\\s*", so a legal spaced dash leaves no
                    # region behind at all. Held rather than yielded, because
                    # where an intruder is also present ("¶735-­745") that
                    # character is the report and the dash is the legitimate
                    # separator it displaced.
                    if held is None:
                        held = (n, col, ord(ch),
                                UNUSED_DASH if ch in DASH_CHARS else SPLIT_RUN)
                    continue
                # Every character that reaches here is either suspect or is
                # occupying the dash position, so every report is hard. An
                # earlier version had an advisory arm for a "visible,
                # non-deceptive separator". In that version only the purity
                # rule admitted a region, so any such character made the region
                # impure and the arm was reachable by zero of the 1,112,064
                # code points. The tight rule reaches that position, so the arm
                # would now be live -- and a visible non-dash wedged between two
                # digit runs is a silent span collapse, which is a hard failure
                # and not an advisory. The arm is gone rather than revived.
                reported = True
                yield n, col, ord(ch), NOT_A_DASH
            if held is not None and not reported:
                # Nothing else explains the failed span, so the held character
                # does. Two shapes: "¶735--745" reads to a human as a span into
                # the overlap and parses as the bare citation 735, and "¶7 56"
                # reads as 756, parses as 7, and prints paragraph 7 as the
                # reviewer's evidence row. Neither shape is reachable by the
                # character sweep in measure.py -- a dash and a space are both
                # visible and non-numeric, so neither is in either population,
                # and both defects were found by reading the code instead.
                yield held


def admissible(chars: str) -> bool:
    """True when the text between two numbers is examined at all. Two grounds,
    and nothing else:

    * PURE: every character is whitespace, suspect **or a dash**. The dash arm
      is load-bearing, not decoration -- a region of dashes and spaces
      ("\u00b6700- -800") is admitted by nothing else. In a SPACED region one
      ordinary printable character of real width means the following number is
      a separate thing, which is what keeps prose out.

    * UNSPACED: no whitespace at all, which makes it the separator position.
      This ground does not ask whether the characters are ordinary, so ".." and
      "->" are examined. A prose separator between two numbers carries a space;
      a run jammed between the digits does not.

    One function, used by both region shapes, because the same rule stated
    twice drifted: a mutation enumeration described it as "wholly
    whitespace-or-suspect" and dropped the dash arm from the wording while the
    code had it.
    """
    pure = all(c.isspace() or suspect(c) or c in DASH_CHARS for c in chars)
    return pure or not any(c.isspace() for c in chars)


def touches_overlap(lo: int, hi: int) -> bool:
    """True when the span meets 741-783. Tests endpoints rather than iterating,
    so a huge span cannot hang, and uses min/max so a reversed one cannot read
    as empty -- though check() reports MALFORMED_SPAN and continues before this
    is reached, so the reversed case is defence in depth rather than a path any
    input takes today. An earlier version of this line claimed it as live."""
    return min(lo, hi) <= OVERLAP[-1] and max(lo, hi) >= OVERLAP[0]


def check(doc: Path, src: dict[str, list[str]], table: bool) -> int:
    hard: list[str] = []
    advisory: list[str] = []
    rows: list[tuple[int, str, int, str]] = []
    total = bare = resolved = 0

    text = doc.read_text(encoding="utf-8")
    # Every report from this scan is hard. There is no advisory arm; the
    # removed-arm note in foreign_in_citations() says why.
    for line, col, cp, why in foreign_in_citations(text):
        what = f"U+{cp:04X}  " if cp is not None else ""
        hard.append(f"{doc.name}:{line}  col {col + 1}  {what}"
                    f"FOREIGN_IN_CITATION  {why}; what the citation means is "
                    f"not inferred")
    for line, which, lo, hi in citations(text):
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
        for offset, para in enumerate(span):
            if not para:
                hard.append(f"{doc.name}:{line}  {which} ¶{lo + offset}  BLANK_PARAGRAPH")
            rows.append((line, which, lo + offset, para))
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
    """Make a revert of a guard redden this suite.

    No claim is made here that every guard is covered, nor that each dies on
    its own assertion. Every version of that claim written here was found
    false, so no figure and no measured set is stated in this docstring: both
    live in measure.py, which derives them. What is true
    of this suite, without restating any count: the reverts that paragraph
    enumerates were mutation-tested and each reddened it, some by raising
    inside the code under test rather than by failing an assertion, which is
    detection and not a clean failure. Reverts outside the measured set do
    survive, which is why nothing universal is claimed. SHORT is pinned only
    to a range, not to its value. A return code cannot distinguish an advisory
    from a clean run, so the cases needing that inspect the printed output.
    """
    import contextlib
    import io
    import tempfile

    paras = ["para %d with enough text to clear the label threshold" % i
             for i in range(1, 900)]
    paras[499] = ""          # a cited blank paragraph is a hard failure
    paras[600] = "R"         # a one-character label cell is an advisory
    paras[700] = "Critical"  # an eight-character label cell, to bound SHORT
    src = {"EIP": list(paras), "TSD": list(paras)}

    def run(text):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d) / "selfcheck.md"
            tmp.write_text(text, encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = check(tmp, src, False)
            return code, buf.getvalue()

    def rc(text):
        return run(text)[0]

    def run_table(text):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d) / "selfcheck.md"
            tmp.write_text(text, encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                check(tmp, src, True)
            return buf.getvalue()

    # --- the overlap guard, every way a span can meet the window ---
    assert rc("see ¶735-745 there") == 1, "span entering the overlap must fail"
    assert rc("see ¶780-790 there") == 1, "span leaving the overlap must fail"
    assert rc("see ¶700-800 there") == 1, "span straddling the overlap must fail"
    assert rc("see ¶750 there") == 1, "single paragraph inside the overlap must fail"
    assert rc("see ¶783-741 there") == 1, "reversed span touching the overlap must fail"
    assert rc("EIP ¶745-735") == 1, "prefixed reversed span must be malformed, not resolved"
    # --- both window edges, so neither bound can move by one unnoticed ---
    assert rc("see ¶741 there") == 1, "low edge of the overlap must fail"
    assert rc("see ¶783 there") == 1, "high edge of the overlap must fail"
    assert rc("see ¶740 there") == 0, "just below the overlap is advisory"
    assert rc("see ¶784 there") == 0, "just above the overlap is advisory"
    # --- dash spellings, including the invisible one and two above U+3000 ---
    assert rc("see ¶735–745 there") == 1, "en-dash span must fail"
    assert rc("see ¶735\u00ad745 there") == 1, (
        "a soft hyphen substituted for the dash must be reported, not read as one")
    assert rc("see ¶735−745 there") == 1, "minus-sign span must fail"
    assert rc("see ¶735－745 there") == 1, "fullwidth hyphen-minus span must fail"
    assert rc("see ¶735﹣745 there") == 1, "small hyphen-minus span must fail"
    assert rc("see ¶735 - 745 there") == 1, "spaced hyphen span must fail"
    # --- no prefix is ever inherited ---
    assert rc("TSD ¶800 and then ¶750") == 1, "prefix must not be inherited on a line"
    assert rc("TSD ¶800\nand then ¶750") == 1, "prefix must not be inherited across lines"
    # Insertion, not substitution: an invisible Cf character anywhere inside a
    # citation must not turn a hard failure into an advisory.
    assert rc("see ¶735-\u00ad745 there") == 1, "soft hyphen after the dash must not downgrade"
    assert rc("see ¶735\u00ad-745 there") == 1, "soft hyphen before the dash must not downgrade"
    assert rc("see ¶7\u00ad35-745 there") == 1, "soft hyphen inside a number must not downgrade"
    assert rc("see ¶7\u00ad56 there") == 1, "soft hyphen inside a bare in-overlap citation must not downgrade"
    assert rc("see ¶7\u200b56 there") == 1, "zero-width space inside a citation must not downgrade"
    # The characters a Unicode-category test on Cf missed. U+000B is what a Word
    # manual line break becomes and U+000C a page break, and both are eaten by
    # str.splitlines() -- so these also pin the choice of split("\n").
    assert rc("see ¶7\u000b56 there") == 1, "vertical tab inside a citation must not downgrade"
    assert rc("see ¶7\u000c56 there") == 1, "form feed inside a citation must not downgrade"
    assert rc("see ¶7\u0085 56 there") == 1, "next-line inside a citation must not downgrade"
    assert rc("see ¶7\u2028 56 there") == 1, "line separator inside a citation must not downgrade"
    assert rc("see ¶7\u00a056 there") == 1, "no-break space inside a citation must not downgrade"
    assert rc("see ¶7\u316456 there") == 1, "Hangul filler inside a citation must not downgrade"
    assert rc("see ¶7\ufe0056 there") == 1, "variation selector inside a citation must not downgrade"
    assert rc("see ¶7\u280056 there") == 1, "braille blank inside a citation must not downgrade"
    # A directional mark in prose is legitimate and must NOT fail: the RTL
    # scenario this catalog owns needs them.
    assert rc("text \u200e and ¶1200 there") == 0, (
        "a directional mark outside a citation must not fail")
    # With the foreign scan in place, a dash spelling outside the class is
    # reported rather than silently downgraded, so the class's breadth no longer
    # carries safety. It still carries parse quality: a real dash must read as a
    # dash, not as a foreign character. That is what this pins.
    ff_code, ff_out = run("see ¶735\uff0d745 there")
    assert ff_code == 1 and "BARE_IN_OVERLAP" in ff_out and "FOREIGN" not in ff_out, (
        "a fullwidth hyphen-minus must read as a dash, not as a foreign character")
    # Four evasions, each of which slipped past a hand-typed terminator set;
    # the boundary is now the parser's own grammar.
    assert rc("see ¶7\t56 there") == 1, "a tab inside the digits must not downgrade"
    assert rc("see ¶735 \u00ad 745 there") == 1, (
        "a spaced invisible separator must not downgrade")
    assert rc("see ¶735\t\u00ad\t745 there") == 1, (
        "a tab-wrapped invisible separator must not downgrade")
    assert rc("see ¶7\u00b256 there") == 1, (
        "a superscript digit reads as part of the figure and must not downgrade")
    assert rc("see ¶7\u246056 there") == 1, (
        "a circled number must not downgrade")
    assert rc("see ¶ 756 there") == 1, (
        "a pilcrow with digits near but not adjacent must not vanish")
    assert rc("see ¶\t756 there") == 1, "the same with a tab must not vanish"
    # Both of these bounds were found hand-typed where the parser's own
    # separator is unbounded: seven characters of padding, or three spaces
    # after the pilcrow, defeated the scan entirely.
    assert rc("see ¶7" + "\u00ad" * 7 + "56 there") == 1, (
        "padding must not hide an invisible separator at seven characters")
    assert rc("see ¶7" + "\u00ad" * 30 + "56 there") == 1, (
        "nor at thirty")
    # The region is unbounded in the code, but a {0,30} cap survived the suite
    # while thirty was the longest fixture, so the claim was only ever as long
    # as the longest case. Two hundred is where it is pinned now.
    assert rc("see ¶7" + "\u00ad" * 200 + "56 there") == 1, (
        "nor at two hundred, which is as far as any fixture goes")
    assert rc("see ¶   756 there") == 1, (
        "a pilcrow with digits three spaces away must not vanish")
    # A digit that is not an ASCII digit changes the paragraph VALUE rather than
    # truncating the citation, so a reader sees a plausible figure and the
    # parser reads a different one. `\d` would have absorbed it silently.
    assert rc("see ¶7\u066056 there") == 1, (
        "an Arabic-Indic digit must not be absorbed into the number")
    assert rc("see ¶7\uff1156 there") == 1, (
        "nor a fullwidth digit")
    assert rc("see ¶7\U0001d7ce56 there") == 1, (
        "nor an astral-plane mathematical digit")
    # Three arms were found unpinned, each a real downgrade: a Roman numeral
    # (Nl), an enclosing mark (Me), and the word boundary that stops "fooEIP"
    # being read as a prefix.
    assert rc("see ¶7\u216056 there") == 1, "a Roman numeral separator must not downgrade"
    assert rc("see ¶7\u20dd56 there") == 1, "an enclosing mark must not downgrade"
    # Each of the single-character cases above is now ALSO admitted by the
    # tight rule, which examines the dash position whatever sits in it -- so
    # since that rule landed they no longer pin the suspect predicate: stripping
    # its Mn/Me arm, its zero-width tail, its No arm or its Nl arm left every
    # one of them passing. The spaced form restores the pin, because a
    # three-character region is not tight and only purity can admit it. Both
    # numbers sit outside the overlap so the return code carries the scan's
    # verdict alone. One revert per character, since each is separately
    # removable.
    for ch, label in (("\u0301", "combining acute (Mn)"),
                      ("\u20dd", "enclosing circle (Me)"),
                      ("\u3164", "Hangul filler"),
                      ("\u115f", "Hangul choseong filler"),
                      ("\u1160", "Hangul jungseong filler"),
                      ("\uffa0", "halfwidth Hangul filler"),
                      ("\u2800", "braille blank"),
                      ("\u00b2", "superscript two (No)"),
                      ("\u2160", "Roman numeral one (Nl)")):
        assert rc(f"see ¶800 {ch} 900 there") == 1, (
            f"a spaced {label} between two numbers must be reported")
    assert rc("see ¶800 x 900 there") == 0, (
        "while an ordinary letter there is prose and must not be")
    bd_code, bd_out = run("see fooEIP ¶750 there")
    assert bd_code == 1 and "BARE_IN_OVERLAP" in bd_out, (
        "a prefix glued to a preceding word must not count as a prefix")
    # The digits themselves written in a script the parser cannot read: the
    # citation vanishes from the count rather than failing, which is worse than
    # a downgrade.
    assert rc("see ¶\u0667\u0665\u0666 there") == 1, (
        "Arabic-Indic digits must not make a citation vanish")
    assert rc("see ¶\uff17\uff15\uff16 there") == 1, "nor fullwidth digits"
    # The three assertions above check only the return code, which stays 1
    # because the separator report fires either way -- so they could not tell
    # that CITE had absorbed the digit into the VALUE. These check the value.
    for digit, label in (("\u0660", "Arabic-Indic"), ("\uff11", "fullwidth"),
                         ("\U0001d7ce", "astral mathematical")):
        tbl = run_table(f"EIP ¶7{digit}56")
        assert "EIP ¶7 |" in tbl, (
            f"a {label} digit must not be absorbed into the paragraph number")
    # Prose legality is pinned as a PAIR, so the punctuation cannot stand in
    # for the character: the same mark with a comma before it passes, alone
    # between two numbers it is reported. An earlier version asserted only the
    # first half and claimed the second.
    for mark, label in (("\u200e", "directional mark"), ("\u200d", "joiner"),
                        ("\u00a0", "no-break space")):
        assert rc(f"see ¶1200, {mark} 300 rows") == 0, (
            f"a {label} separated from the numbers by punctuation is prose")
        assert rc(f"see ¶1200 {mark} 300 rows") == 1, (
            f"a {label} standing alone between two numbers is reported")
    # The SPAN digit run is pinned by value the same way. int() accepts any
    # Unicode decimal digit, so under `\d` the span below would read 800-805
    # and resolve; under [0-9] the run stops at 80 and the span is malformed.
    # A return code cannot tell those apart -- both are 1 -- so this reads the
    # resolved rows.
    tbl = run_table("EIP ¶800-80\u0665")
    assert "MALFORMED_SPAN" in tbl, "a span whose end is unreadable is malformed"
    assert "EIP ¶805 |" not in tbl, (
        "an Arabic-Indic digit must not be absorbed into a span's end")
    # Whitespace between two digit runs. A space is the legitimate separator
    # inside a span the parser DID read, and SPAN consumes "\s*DASH\s*", so a
    # region holding only spaces means no span was read: "¶7 56" reads as 756,
    # parses as 7, and prints paragraph 7 as the reviewer's evidence row with
    # nothing reported. Held like a dash, for the same reason.
    sp_code, sp_out = run("see ¶7 56 there")
    assert sp_code == 1 and SPLIT_RUN in sp_out, (
        "whitespace splitting the digits must be reported")
    assert rc("see ¶7   56 there") == 1, "at any width"
    assert rc("TSD ¶7 56 is cache key prefixing") == 1, (
        "including where a prefix makes the wrong paragraph resolve and print")
    # The region's own extent stops at a digit or a pilcrow, and at nothing
    # else. An earlier version also stopped at an ASCII letter and called that
    # "precision only"; it was not -- it made a single ASCII letter in the dash
    # position silent while a single letter in any other script was a hard
    # failure, an asymmetry nothing pinned and nothing justified.
    assert rc("see ¶800x900 there") == 1, (
        "an ASCII letter in the dash position must be reported")
    assert rc("see ¶1200\u0628300 rows") == 1, "as a letter in any other script is"
    assert rc("see ¶500 in table 3 there") == 0, (
        "while a letter in a wider region is prose and keeps the region impure")
    assert rc("see ¶500, 600 and 700") == 0, "as does ordinary punctuation"
    # The pilcrow terminator is load-bearing on the live corpus: dropping it
    # makes false positives of "¶750/¶773" and "¶1237/¶1206", live notation
    # in MOD-004.md. No count is typed here, because nothing derives it; the
    # two cases below are the pin and they redden when it is dropped. The
    # section sign's evidence is NOT the same: removing \u00a7 changes nothing on
    # either document this tool is run against, and its only instance is in
    # ADR-0002, which it is not. The fixture below does not show the pilcrow
    # case either, and the mechanism is worth stating because it is not the
    # obvious one. With the
    # terminator in place SEPARATOR_REGION does not match past the pilcrow, so
    # the MARKED_REGION branch takes it instead -- admissible() IS called, on
    # ", ", and rejects it on the comma. Without the terminator the region runs
    # to the next digit and the comma rejects it there. Silent either way, so a
    # non-pin; the two cases after it are the discriminating ones.
    assert rc("¶1211-1212, ¶1244") == 0, "a following citation ends the region"
    # 750 and 773 are themselves inside the overlap, so MOD-004.md's own
    # instance is hard for an unrelated reason; these use numbers outside it so
    # the scan's silence is what the return code shows.
    assert rc("see ¶850/¶873 and more") == 0, (
        "a slash between two citations is a list, not a collapsed span")
    assert rc("see ¶1237/¶1206 there") == 0, (
        "as MOD-004.md writes this shape at two lines, this spelling at one")
    # But a DASH stranded before a marker is a span the parser declined. Both
    # endpoints sit outside the overlap, so only the scan can carry this.
    md_code, md_out = run("see ¶700-¶800 there")
    assert md_code == 1 and UNUSED_DASH in md_out, (
        "a dash before a reference marker is a span that did not parse")
    assert rc("see ¶735 - ¶790 there") == 1, "spaced the same way"
    # The admission test governs this branch too, and prose reaches it: many
    # marker-bounded regions in the tracked corpus hold a dash, and all of them
    # are spaced and hold ordinary characters, so all are inadmissible. Run
    # `measure.py census` for the current count and contents -- no figure is
    # typed here, because two earlier ones went stale, one of them because a
    # fixture in this very suite changed the corpus it was counting. Without
    # the test every such region would be reported, and nothing in this suite
    # noticed until this case was added.
    assert rc("see ¶850 (VAL) — Required by the EIP ¶881") == 0, (
        "an em dash inside prose before a citation is not a declined span")
    assert rc("see ¶850 — engineering decision, not ¶881") == 0, (
        "as MOD-004.md and this document both write it")
    assert rc("see ¶735-\u00a7790 there") == 1, "and before a section sign"
    # MARKED_REGION is unbounded in the code like SEPARATOR_REGION, and was
    # pinned only to three characters -- a {0,3} cap passed this suite, which
    # is 67 times looser than the bound the other region carries. Padded to
    # two hundred, as that one is.
    assert rc("see ¶735" + "\u00ad" * 200 + "-¶790 there") == 1, (
        "a padded marker-bounded region must not hide the declined dash")
    # One report per marked region. The digit-bounded branch yields one per
    # offending character ("\u00b6735..745" reports twice) and one for a run of
    # dashes, which is the case this parallels; dropping the break gave a
    # report per dash here and nothing noticed.
    mm_code, mm_out = run("see ¶700---¶800 there")
    assert mm_code == 1 and mm_out.count("FOREIGN_IN_CITATION") == 1, (
        "several dashes before a marker are one declined span, not three")
    # The separator position is any region with no whitespace, not just one
    # character. ".." is this project's own range notation ("ADR-0001..0005",
    # "MOD-000..003"), so a citation written that way is the defect this tool
    # exists for in the house idiom; the earlier length test missed it.
    for sep, label in (("..", "a doubled full stop"), ("...", "an ellipsis"),
                       ("~~", "a doubled tilde"), ("->", "an arrow"),
                       ("=>", "a fat arrow"), ("\u2192", "an arrow glyph")):
        assert rc(f"see ¶735{sep}745 there") == 1, (
            f"{label} between two digit runs collapses a span silently")
    # And prose keeps its space, which is what the rule turns on.
    for sep, label in ((", ", "a list comma"), (" (", "an opening bracket"),
                       (" to ", "a word"), (" ~ ", "a spaced tilde"),
                       (" x ", "a spaced letter")):
        assert rc(f"see ¶500{sep}600 rows") == 0, (
            f"{label} carries a space, so the following number is a separate "
            f"thing")
    # Two dashes between the digit runs. SPAN reads neither, so the span
    # collapses to its first paragraph: "¶700--800" reads to a human as a
    # span straddling the window and parsed as the bare citation 700, which is
    # outside it. Neither endpoint is in the overlap on its own, so the return
    # code here carries the dash report alone. The sweep below cannot reach
    # this -- a dash is neither invisible nor a numeral.
    dd_code, dd_out = run("see ¶700--800 there")
    assert dd_code == 1 and UNUSED_DASH in dd_out, (
        "a dash the parser did not read as a span separator must be reported")
    assert rc("see ¶700- -800 there") == 1, "the same spaced apart"
    assert rc("see ¶700\u2013\u2014800 there") == 1, "and in two spellings"
    # The dash is held rather than yielded, so where an intruder displaced it
    # that character is the report and the dash is not blamed as well.
    di_code, di_out = run("see ¶735-\u00ad745 there")
    assert di_code == 1 and "U+00AD" in di_out and UNUSED_DASH not in di_out, (
        "a displaced dash must not be reported alongside the character that "
        "displaced it")
    # The dash position: one visible character wedged between two digit runs
    # collapses a span into the overlap silently.
    assert rc("see ¶735~745 there") == 1, (
        "a non-dash in the dash position must not collapse a span silently")
    assert rc("see ¶700\u2500800 there") == 1, "nor a box-drawing character"
    assert rc("see ¶735.745 there") == 1, "nor a full stop"
    # Prose must stay legal. An earlier region stopped only at an ASCII letter,
    # so it ran through Arabic text, which has none, and hard-failed the prose
    # between the numbers. These are the cases that caught that.
    assert rc("see ¶1200 \u0627\u0644\u0641\u064e\u0635\u0644 3 there") == 0, (
        "Arabic prose after a citation must not fail")
    assert rc("see ¶1200, \u200e 300 rows") == 0, (
        "a directional mark in prose must not fail")
    assert rc("see ¶1200 (\u00a0300 rows)") == 0, (
        "a no-break space after a parenthesis must not fail")
    assert rc("see ¶1200: \u200d 300") == 0, "nor a joiner in prose"
    assert rc("see ¶p756 there") == 0, (
        "a pilcrow followed by a letter is prose, not a vanished citation")
    # A visible non-dash SEPARATED from the numbers is not reported, and there
    # is no advisory arm. This fixture does NOT pin the purity rule, though not
    # for the reason two earlier comments gave: \u00a7 is a region terminator, so
    # the MARKED_REGION branch takes it, admissible() is called on " " and
    # admits it, and the loop then finds no dash, so nothing is yielded. The
    # purity rule is pinned by the spaced-suspect cases above, not here.
    assert rc("see ¶1245 \u00a727 there") == 0, (
        "a section reference after a citation is never a separator")
    assert rc("see ¶735\u00a7745 there") == 0, (
        "not even jammed between two digit runs, where a tilde would report")
    sg_code, sg_out = run("see ¶735~745 there")
    assert sg_code == 1 and NOT_A_DASH in sg_out, (
        "which is the asymmetry the terminator buys, pinned so it is visible")
    # The section sign is not a separator at all, spaced or not: it starts a
    # section reference, so the number after it is that section's, exactly as
    # after a pilcrow. ADR-0002 writes "EIP \u00a78 \u00b6749-755/\u00a721.5", whose region
    # "/\u00a7" holds no whitespace and was reported until \u00a7 became a terminator.
    assert rc("see ¶1245/\u00a721.5 there") == 0, (
        "a section reference after a citation is not a collapsed span")
    assert rc("EIP ¶849-855/\u00a721.5 and the rest") == 0, (
        "which is the shape ADR-0002 writes, outside the overlap")
    # ADR-0002's own line is "EIP \u00a78 ¶749-755/\u00a721.5". Its \u00a7 is now a
    # terminator, so the scan is silent on it -- but CITE requires the prefix
    # immediately before the pilcrow, so "\u00a78 " between them leaves the citation
    # bare and inside the overlap. That is a real BARE_IN_OVERLAP in a file
    # this tool is not run against, not a false positive of the terminator.
    adr_code, adr_out = run("EIP \u00a78 ¶749-755/\u00a721.5 and the rest")
    assert adr_code == 1 and "BARE_IN_OVERLAP" in adr_out and "FOREIGN" not in adr_out, (
        "a prefix separated from its pilcrow is bare, and the section sign is "
        "still not reported")
    assert rc("the `¶` glyph and ¶1200 there") == 0, (
        "a pilcrow with no digits near it is prose, not a citation")
    # The minus sign is the one character hand-added to the dash class, so its
    # membership needs its own parse-quality pin, as U+FF0D has.
    mn_code, mn_out = run("see ¶735\u2212745 there")
    assert mn_code == 1 and "BARE_IN_OVERLAP" in mn_out and "FOREIGN" not in mn_out, (
        "a minus sign must read as a dash, not as a foreign character")
    # citations() must not use splitlines() either. Both call sites need their
    # own case, because a revert of one is not a revert of the other. No revert
    # number is cited here: the enumeration lives in measure.py, and a number
    # copied out of it drifts silently.
    # The fixture must contain a character str.splitlines() treats as a line
    # boundary and split("\n") does not, or the two are indistinguishable and
    # the assertion pins nothing. U+000B is such a character.
    cl_code, cl_out = run("a\u000bsee ¶750 there")
    assert cl_code == 1 and "selfcheck.md:1" in cl_out and "selfcheck.md:2" not in cl_out, (
        "citations() must split on newline alone, not str.splitlines()")
    # A letter between two numbers is prose, not a citation separator, and must
    # draw no report at all.
    pr_code, pr_out = run("see ¶1200 x 1201 there")
    assert pr_code == 0 and "FOREIGN" not in pr_out, (
        "a letter between numbers must not be read as a separator")
    # Line attribution, which a return code cannot show.
    line_code, line_out = run("clean line\nsee ¶7\u00ad56 there\nmore")
    # "see ¶7<SH>56" -- the soft hyphen is the 7th character, 1-based.
    assert line_code == 1 and "selfcheck.md:2  col 7  U+00AD" in line_out, (
        "a foreign character must be reported at its own line and column")
    # --- ordinary passing cases ---
    assert rc("see ¶1200 there") == 0, "bare citation outside the overlap is advisory"
    assert rc("EIP ¶750 and TSD ¶756") == 0, "explicit prefixes must pass"
    # --- existence guards, both bounds ---
    # One past the fixture's last paragraph, so an off-by-one in the bound dies
    # too; 9999 would have left `len(...) + 1` passing.
    assert rc("EIP ¶900") == 1, "paragraph above the document must fail"
    assert rc("EIP ¶0") == 1, "paragraph below 1 must fail, not index from the end"
    assert rc("EIP ¶500") == 1, "citation of a blank paragraph must fail"
    # The blank is the SECOND paragraph of this span, so a resolution collapsed
    # to the span's first paragraph would miss it. This is what pins the span
    # iteration, and with it every --table evidence row after the first.
    assert rc("EIP ¶499-501") == 1, (
        "a blank inside a span must fail, so the whole span is resolved")
    # --- the label-cell advisory, which a return code cannot show ---
    label_code, label_out = run("EIP ¶601")
    assert label_code == 0 and "LABEL_CELLS" in label_out, (
        "a one-character label cell must raise the LABEL_CELLS advisory")
    long_code, long_out = run("EIP ¶701")
    assert long_code == 0 and "LABEL_CELLS" in long_out, (
        "an eight-character label cell must still raise it, so SHORT > 8")
    # A span of three real paragraphs must produce three evidence rows, not one.
    rows = [l for l in run_table("EIP ¶100-102").splitlines()
            if l.startswith("| selfcheck.md:")]
    assert len(rows) == 3, "a three-paragraph span must emit three table rows"

    # --- the guards around check(), reached only through main() ---
    def main_with(argv):
        saved = sys.argv
        sys.argv = ["cite_check.py"] + argv
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                return main(), buf.getvalue()
        finally:
            sys.argv = saved

    none_code, none_out = main_with([])
    assert none_code == 2 and "MISSING_ARGUMENTS" in none_out, (
        "no arguments must print MISSING_ARGUMENTS and exit 2")
    part_code, part_out = main_with(["--doc", "x.md"])
    assert part_code == 2 and "MISSING_ARGUMENTS" in part_out, (
        "partial arguments must print MISSING_ARGUMENTS and exit 2")

    with tempfile.TemporaryDirectory() as d:
        fake = Path(d) / "fake.docx"
        # Three paragraphs, the middle one blank. This pins the paragraphs()
        # include-blanks contract: filtering blanks would shift the numbering
        # and leave no paragraph 3 for the document below to resolve.
        body = ('<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxm'
                'lformats.org/wordprocessingml/2006/main"><w:body>'
                '<w:p><w:r><w:t>synthetic paragraph one, long enough to be a rule'
                '</w:t></w:r></w:p><w:p/>'
                '<w:p><w:r><w:t>synthetic paragraph three, also long enough'
                '</w:t></w:r></w:p></w:body></w:document>')
        with zipfile.ZipFile(fake, "w") as z:
            z.writestr("word/document.xml", body)
        good = sha256(fake)
        near_last = good[:-1] + ("0" if good[-1] != "0" else "1")
        near_first = ("0" if good[0] != "0" else "1") + good[1:]
        doc = Path(d) / "d.md"
        doc.write_text("EIP ¶3\n", encoding="utf-8")
        args = ["--doc", str(doc), "--eip", str(fake), "--tsd", str(fake)]

        mm_code, mm_out = main_with(args + ["--eip-sha256", near_last,
                                           "--tsd-sha256", good])
        assert mm_code == 2 and "BASELINE_MISMATCH" in mm_out, (
            "a hash differing in its last character must fail closed")
        assert main_with(args + ["--eip-sha256", near_first,
                                 "--tsd-sha256", good])[0] == 2, (
            "a hash differing in its first character must fail closed")
        assert main_with(args + ["--eip-sha256", good,
                                 "--tsd-sha256", near_last])[0] == 2, (
            "a wrong TSD hash must fail closed")
        assert main_with(args + ["--eip-sha256", good,
                                 "--tsd-sha256", good])[0] == 0, (
            "correct hashes must reach check(), and a blank w:p must still count")

    # Counted from this file rather than typed, so the figure cannot go stale
    # when an assertion is added or removed.
    import ast
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "self_check")
    total = sum(1 for n in ast.walk(fn) if isinstance(n, ast.Assert))
    print(f"self-check: {total} assert statements passed")
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

"""
UI-foundations fixture lint (MOD-001, GOV-01-R03 — localization and
accessibility tooling foundations; SCN-MOD001-039 and SCN-MOD001-040).

No frontend or mobile source exists in this repository yet, so this is a
foundation for future UI-bearing modules, exercised only against synthetic
HTML fixtures. It is deliberately minimal and stdlib-only (`html.parser`);
it is not an accessibility engine and makes no claim about real screen-reader
or device behaviour.

Two rules, both evaluated per fixture file:

  * `RTL_TEXT_NOT_RTL` (SCN-039) - a text node containing Arabic/Hebrew
    (strong right-to-left) characters must have an effective direction of
    RTL: the nearest ancestor-or-self element carrying a `dir` attribute
    must say `rtl`, or say `auto` with a first-strong character (in that
    element's own text, skipping nested `dir` elements) that is RTL. No
    `dir` anywhere, `dir="ltr"`, `dir="auto"` resolving to LTR, or an
    invalid value is flagged. Text with no RTL characters is never flagged.
  * `MISSING_ARIA_LABEL` (SCN-040) - an interactive element (button,
    select, textarea, non-hidden input, `a[href]`, or an element with an
    interactive ARIA role) must have an accessible name: a non-empty
    `aria-label`/`aria-labelledby`, or - for `button`, `a[href]` and ARIA
    roles that name from content - non-blank child text. Child text is not
    a name source for `input`/`select`/`textarea` or name-from-author roles
    such as `textbox`/`slider`. Image `alt` text inside a control is not
    inspected (such a control needs an explicit label).

Fail-closed rule: "cannot inspect" resolves to deny. An unreadable or
undecodable file, a missing path, malformed markup (mismatched or unclosed
tags), an empty fixture, or having nothing at all to inspect is a problem,
never a silent pass.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

RTL_TEXT_NOT_RTL = "RTL_TEXT_NOT_RTL"
MISSING_ARIA_LABEL = "MISSING_ARIA_LABEL"
MALFORMED_FIXTURE = "MALFORMED_FIXTURE"
EMPTY_FIXTURE = "EMPTY_FIXTURE"
UNREADABLE_FIXTURE_FILE = "UNREADABLE_FIXTURE_FILE"
MISSING_FIXTURE_PATH = "MISSING_FIXTURE_PATH"
NO_FIXTURE_FILES = "NO_FIXTURE_FILES"

FIXTURE_SUFFIXES = (".html", ".htm")

# Hebrew, Arabic, Syriac, Thaana, NKo, Arabic extended/presentation forms.
_RTL_CHAR = re.compile("[֐-ࣿיִ-﷿ﹰ-﻿]")

_VOID_TAGS = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "source", "track", "wbr",
    }
)  # fmt: skip
_RAW_TEXT_TAGS = frozenset({"script", "style"})
_INTERACTIVE_TAGS = frozenset({"button", "select", "textarea"})
_INTERACTIVE_ROLES = frozenset(
    {
        "button", "link", "checkbox", "radio", "switch", "tab", "menuitem",
        "textbox", "combobox", "slider", "spinbutton", "searchbox", "option",
    }
)  # fmt: skip
# ARIA roles whose accessible name may be computed from content (WAI-ARIA 1.2).
_NAME_FROM_CONTENT_ROLES = frozenset(
    {"button", "link", "checkbox", "radio", "switch", "tab", "menuitem", "option"}
)
_NO_CONTENT_NAME_TAGS = frozenset({"input", "select", "textarea"})


@dataclass(frozen=True)
class Finding:
    code: str
    source: str
    line: int
    detail: str

    def __str__(self) -> str:
        return f"{self.source}:{self.line}: {self.code}: {self.detail}"


@dataclass
class _Open:
    tag: str
    dir: str | None
    name_line: int | None = None  # set while an unnamed, content-named control is open
    has_text: bool = False
    first_strong: str | None = None  # "rtl" / "ltr", tracked for dir="auto"


def _first_strong(text: str) -> str | None:
    for ch in text:
        bidi = unicodedata.bidirectional(ch)
        if bidi == "L":
            return "ltr"
        if bidi in ("R", "AL"):
            return "rtl"
    return None


class _FixtureParser(HTMLParser):
    def __init__(self, name: str) -> None:
        super().__init__(convert_charrefs=True)
        self.name = name
        self.findings: list[Finding] = []
        self.elements = 0
        self._stack: list[_Open] = []

    def _add(self, code: str, detail: str, line: int | None = None) -> None:
        self.findings.append(Finding(code, self.name, line or self.getpos()[0], detail))

    def _open(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> tuple[dict[str, str], int | None]:
        """Return the attributes and, if the name may still come from content, the line."""
        self.elements += 1
        attr = {k.lower(): (v or "") for k, v in attrs}
        if not self._is_interactive(tag, attr) or (
            attr.get("aria-label", "").strip() or attr.get("aria-labelledby", "").strip()
        ):
            return attr, None
        if self._names_from_content(tag, attr):
            return attr, self.getpos()[0]
        self._add(MISSING_ARIA_LABEL, f"<{tag}> has no aria-label/aria-labelledby")
        return attr, None

    @staticmethod
    def _names_from_content(tag: str, attr: dict[str, str]) -> bool:
        if tag in _NO_CONTENT_NAME_TAGS:
            return False
        return tag in ("button", "a") or (
            attr.get("role", "").strip().lower() in _NAME_FROM_CONTENT_ROLES
        )

    @staticmethod
    def _is_interactive(tag: str, attr: dict[str, str]) -> bool:
        if tag == "input":
            return attr.get("type", "text").strip().lower() != "hidden"
        if tag == "a":
            return "href" in attr
        if tag in _INTERACTIVE_TAGS:
            return True
        return attr.get("role", "").strip().lower() in _INTERACTIVE_ROLES

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr, name_line = self._open(tag, attrs)
        if tag in _VOID_TAGS:
            return
        direction = attr["dir"].strip().lower() if "dir" in attr else None
        self._stack.append(_Open(tag, direction, name_line))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        _, name_line = self._open(tag, attrs)
        if name_line is not None:  # self-closed: no content can ever name it
            self._add(MISSING_ARIA_LABEL, f"<{tag}> has no aria-label/aria-labelledby", name_line)

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID_TAGS:
            return
        if not self._stack or self._stack[-1].tag != tag:
            self._add(MALFORMED_FIXTURE, f"unexpected closing tag </{tag}>")
            return
        node = self._stack.pop()
        if node.name_line is not None and not node.has_text:
            self._add(
                MISSING_ARIA_LABEL,
                f"<{tag}> has no aria-label/aria-labelledby or text content",
                node.name_line,
            )

    def handle_data(self, data: str) -> None:
        if any(n.tag in _RAW_TEXT_TAGS for n in self._stack):
            return
        if data.strip():
            for node in self._stack:
                node.has_text = True
        if not _RTL_CHAR.search(data):
            self._note_first_strong(data)
            return
        governing = next((n for n in reversed(self._stack) if n.dir is not None), None)
        if governing is not None and governing.dir == "auto":
            self._note_first_strong(data)
            if governing.first_strong == "rtl":
                return
            effective = f"auto (first strong: {governing.first_strong or 'none'})"
        else:
            effective = None if governing is None else governing.dir
            if effective == "rtl":
                return
        shown = "none" if effective is None else repr(effective)
        self._add(RTL_TEXT_NOT_RTL, f"RTL-script text with effective dir={shown}, expected 'rtl'")

    def _note_first_strong(self, data: str) -> None:
        governing = next((n for n in reversed(self._stack) if n.dir is not None), None)
        if governing is not None and governing.dir == "auto" and governing.first_strong is None:
            governing.first_strong = _first_strong(data)

    def finish(self) -> None:
        self.close()
        for node in self._stack:
            self._add(MALFORMED_FIXTURE, f"unclosed <{node.tag}>")
        if self.elements == 0:
            self._add(EMPTY_FIXTURE, "fixture contains no elements")


def evaluate_html_text(text: str, name: str = "<fixture>") -> list[Finding]:
    parser = _FixtureParser(name)
    try:
        parser.feed(text)
        parser.finish()
    except (AssertionError, ValueError, RecursionError) as exc:  # deny, never crash/pass
        parser.findings.append(Finding(MALFORMED_FIXTURE, name, 0, f"parse error: {exc}"))
    return parser.findings


def validate_file(path: Path) -> list[Finding]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [Finding(UNREADABLE_FIXTURE_FILE, str(path), 0, f"cannot read: {exc}")]
    return evaluate_html_text(text, name=str(path))


def _collect(targets: list[Path]) -> tuple[list[Path], list[Finding]]:
    files: list[Path] = []
    problems: list[Finding] = []
    for target in targets:
        if target.is_dir():
            files.extend(
                sorted(p for p in target.rglob("*") if p.suffix.lower() in FIXTURE_SUFFIXES)
            )
        elif target.is_file():
            files.append(target)
        else:
            problems.append(Finding(MISSING_FIXTURE_PATH, str(target), 0, "path does not exist"))
    return files, problems


def run_validation(targets: list[Path]) -> tuple[int, list[Finding]]:
    files, problems = _collect(targets)
    for file in files:
        problems.extend(validate_file(file))
    if not files and not problems:
        problems.append(Finding(NO_FIXTURE_FILES, "<targets>", 0, "no fixture files to inspect"))
    return len(files), problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic HTML RTL/a11y fixture lint.")
    parser.add_argument("targets", nargs="*", type=Path, help="fixture files or directories")
    args = parser.parse_args(argv)
    checked, problems = run_validation(args.targets)

    print("=" * 70)
    print("MOD-001 UI-FOUNDATIONS FIXTURE LINT (GOV-01-R03, SCN-MOD001-039/040)")
    print("=" * 70)
    print(f"Files checked: {checked}")
    if problems:
        print(f"\nDENY: {len(problems)} problem(s) found:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nPASS - RTL text has effective dir=rtl and interactive elements are labelled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

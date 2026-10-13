"""
Unit tests for tools/validate_ui_foundations.py (MOD-001, GOV-01-R03;
SCN-MOD001-039 RTL/bidi lint, SCN-MOD001-040 a11y lint).

Synthetic HTML fixtures only; no real screen, device or member data.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validate_ui_foundations import (
    EMPTY_FIXTURE,
    MALFORMED_FIXTURE,
    MISSING_ARIA_LABEL,
    MISSING_FIXTURE_PATH,
    NO_FIXTURE_FILES,
    RTL_TEXT_NOT_RTL,
    UNREADABLE_FIXTURE_FILE,
    evaluate_html_text,
    main,
    run_validation,
)

SCRIPT = Path(__file__).resolve().parent.parent / "validate_ui_foundations.py"
ARABIC = "مرحبا"

GOOD_RTL = f'<div dir="rtl"><p>{ARABIC}</p></div>'
BAD_RTL = f"<div><p>{ARABIC}</p></div>"
LABELLED = '<button aria-label="Save">x</button>'
UNLABELLED = "<button></button>"


def _codes(html: str) -> list[str]:
    return [f.code for f in evaluate_html_text(html)]


def test_arabic_with_explicit_rtl_passes() -> None:
    assert _codes(GOOD_RTL) == []


def test_arabic_without_dir_is_flagged() -> None:
    assert _codes(BAD_RTL) == [RTL_TEXT_NOT_RTL]


def test_mixed_fixture_flags_only_incorrect_case() -> None:
    findings = evaluate_html_text(f"{GOOD_RTL}\n{BAD_RTL}")
    assert [f.code for f in findings] == [RTL_TEXT_NOT_RTL]
    assert findings[0].line == 2


@pytest.mark.parametrize("value", ["ltr", "bogus"])
def test_non_rtl_effective_dir_is_flagged(value: str) -> None:
    assert _codes(f'<p dir="{value}">{ARABIC}</p>') == [RTL_TEXT_NOT_RTL]


def test_nearest_dir_wins_over_ancestor() -> None:
    assert _codes(f'<div dir="rtl"><p dir="ltr">{ARABIC}</p></div>') == [RTL_TEXT_NOT_RTL]
    assert _codes(f'<div dir="ltr"><p dir="rtl">{ARABIC}</p></div>') == []


def test_latin_text_is_never_flagged() -> None:
    assert _codes("<p>hello</p>") == []


def test_script_content_is_ignored() -> None:
    assert _codes(f"<div><script>var s = '{ARABIC}';</script></div>") == []


def test_unlabelled_interactive_is_flagged_and_labelled_passes() -> None:
    assert _codes(UNLABELLED) == [MISSING_ARIA_LABEL]
    assert _codes(LABELLED) == []
    assert _codes(f"<div>{LABELLED}{UNLABELLED}</div>") == [MISSING_ARIA_LABEL]


def test_blank_aria_label_is_flagged() -> None:
    assert _codes('<button aria-label="  "></button>') == [MISSING_ARIA_LABEL]
    assert _codes('<button aria-label="  ">Save</button>') == []  # blank label falls to content


def test_aria_labelledby_is_accepted() -> None:
    assert _codes('<span id="a">t</span><input aria-labelledby="a">') == []


def test_other_interactive_forms() -> None:
    assert _codes("<input type='text'>") == [MISSING_ARIA_LABEL]
    assert _codes("<input type='hidden'><div></div>") == []
    assert _codes("<a href='#'></a>") == [MISSING_ARIA_LABEL]
    assert _codes("<a name='anchor'>go</a>") == []
    assert _codes("<div role='button'></div>") == [MISSING_ARIA_LABEL]
    assert _codes("<div role='button' aria-label='Go'>x</div>") == []


def test_button_and_link_text_content_is_a_valid_name() -> None:
    assert _codes("<button>Save</button>") == []
    assert _codes('<a href="/">Home</a>') == []
    assert _codes("<button><span>Save</span></button>") == []
    assert _codes("<div role='button'>Go</div>") == []
    assert _codes("<div role='tab'>Overview</div>") == []


def test_nameless_controls_still_flagged_despite_markup() -> None:
    assert _codes("<button>   </button>") == [MISSING_ARIA_LABEL]
    assert _codes("<button><span></span></button>") == [MISSING_ARIA_LABEL]
    assert _codes('<a href="/"><script>var x = "t";</script></a>') == [MISSING_ARIA_LABEL]
    assert _codes("<button/>") == [MISSING_ARIA_LABEL]
    # text belonging to a sibling is not the control's name
    assert _codes("<div>Save<button></button></div>") == [MISSING_ARIA_LABEL]


def test_text_is_not_a_name_for_form_fields_or_author_named_roles() -> None:
    assert _codes("<select>Choose</select>") == [MISSING_ARIA_LABEL]
    assert _codes("<textarea>draft</textarea>") == [MISSING_ARIA_LABEL]
    assert _codes("<div role='textbox'>draft</div>") == [MISSING_ARIA_LABEL]
    assert _codes("<div role='slider'>5</div>") == [MISSING_ARIA_LABEL]


def test_nameless_control_finding_reports_its_own_line() -> None:
    findings = evaluate_html_text("<p>x</p>\n<button>\n</button>")
    assert [(f.code, f.line) for f in findings] == [(MISSING_ARIA_LABEL, 2)]


def test_dir_auto_accepted_only_when_first_strong_is_rtl() -> None:
    assert _codes(f'<div dir="auto">{ARABIC}</div>') == []
    assert _codes(f'<div dir="auto">123 <b>{ARABIC}</b></div>') == []
    assert _codes(f'<div dir="auto"><p>{ARABIC}</p></div>') == []
    assert _codes(f'<div dir="auto">hello {ARABIC}</div>') == [RTL_TEXT_NOT_RTL]
    assert _codes(f'<div dir="auto">hello <b>x</b></div><p dir="auto">{ARABIC}</p>') == []
    # nested explicit dir governs; the auto ancestor's first-strong is irrelevant
    assert _codes(f'<div dir="auto">{ARABIC}<p dir="ltr">{ARABIC}</p></div>') == [RTL_TEXT_NOT_RTL]
    assert _codes(f'<div dir="auto"><p dir="rtl">{ARABIC}</p></div>') == []


def test_dir_auto_ignores_script_text_for_first_strong() -> None:
    assert _codes(f'<div dir="auto"><script>var a;</script>{ARABIC}</div>') == []


def test_both_rules_report_independently() -> None:
    assert sorted(_codes(f"<div>{BAD_RTL}{UNLABELLED}</div>")) == [
        MISSING_ARIA_LABEL,
        RTL_TEXT_NOT_RTL,
    ]


@pytest.mark.parametrize(
    "html",
    ["<div><p>x</div>", "<div>x</span></div>", "<div>x"],
)
def test_malformed_markup_fails_closed(html: str) -> None:
    assert MALFORMED_FIXTURE in _codes(html)


def test_empty_fixture_fails_closed() -> None:
    assert _codes("") == [EMPTY_FIXTURE]
    assert _codes("just text") == [EMPTY_FIXTURE]


def test_void_and_self_closing_tags_are_well_formed() -> None:
    assert _codes("<div><br><img src='a.png' alt=''><input type='hidden'/></div>") == []


def test_unreadable_and_missing_inputs_fail_closed(tmp_path: Path) -> None:
    bad = tmp_path / "bad.html"
    bad.write_bytes(b"\xff\xfe\x00<div></div>")
    _, problems = run_validation([bad, tmp_path / "missing.html"])
    assert {p.code for p in problems} == {UNREADABLE_FIXTURE_FILE, MISSING_FIXTURE_PATH}


def test_no_targets_and_empty_directory_fail_closed(tmp_path: Path) -> None:
    assert [p.code for p in run_validation([])[1]] == [NO_FIXTURE_FILES]
    assert [p.code for p in run_validation([tmp_path])[1]] == [NO_FIXTURE_FILES]


def test_directory_scan_finds_html_fixtures(tmp_path: Path) -> None:
    (tmp_path / "ok.html").write_text(GOOD_RTL, encoding="utf-8")
    (tmp_path / "bad.htm").write_text(BAD_RTL, encoding="utf-8")
    checked, problems = run_validation([tmp_path])
    assert checked == 2
    assert [p.code for p in problems] == [RTL_TEXT_NOT_RTL]


def test_main_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ok = tmp_path / "ok.html"
    ok.write_text(f"{GOOD_RTL}{LABELLED}", encoding="utf-8")
    bad = tmp_path / "bad.html"
    bad.write_text(f"{BAD_RTL}{UNLABELLED}", encoding="utf-8")
    assert main([str(ok)]) == 0
    assert main([str(bad)]) == 1
    out = capsys.readouterr().out
    assert RTL_TEXT_NOT_RTL in out and MISSING_ARIA_LABEL in out
    assert main([]) == 1


def test_cli_subprocess_exit_codes(tmp_path: Path) -> None:
    ok = tmp_path / "ok.html"
    ok.write_text(f"{GOOD_RTL}{LABELLED}", encoding="utf-8")
    bad = tmp_path / "bad.html"
    bad.write_text(UNLABELLED, encoding="utf-8")

    def run(p: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(p)], capture_output=True, text=True, check=False
        )

    assert run(ok).returncode == 0
    assert run(bad).returncode == 1
    assert run(tmp_path / "nope.html").returncode == 1

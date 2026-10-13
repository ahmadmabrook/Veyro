"""GOV-01-R02 six-domain scaffold inventory check — SCN-MOD001-132.

Runs every domain's own `tests/test_scaffold_live.py` placeholder (via a
real, isolated pytest subprocess sharing one disposable Postgres through
`app/modules/conftest.py`) and asserts all six collected and passed by
name. This is a test-level inventory check, not a new architecture gate:
Scenario Review round 11 (`SCENARIOS.md` SCN-MOD001-132) rejected routing
this through `validate_architecture_gates.py --gate module-deps`, since
that gate is cross-domain import/SQL detection only, not domain-scaffold
presence.

Negative case (independently verified in a throwaway copy, not committed
here — deleting or breaking a domain's own scaffold is not something this
suite should do to itself): deleting a domain's file makes
`test_all_six_domain_scaffold_paths_exist` name that domain as missing. A
collection error (deleted/renamed/syntax-broken file) or an assertion
failure both make `test_all_six_domain_scaffolds_pass` fail, but neither
reliably names only the broken domain in that second test's own message
— a collection error reports every domain as not confirmed clean (fail
closed: it never claims a domain passed when nothing could prove it),
and only an assertion failure (not a collection error) names exactly one
domain. The first test is what actually pinpoints a missing file by
name.

Only a testcase literally named `test_scaffold_live` counts per domain,
and exactly one must exist — a passing, differently-named sibling test
defined after a skipped/failed `test_scaffold_live` in the same file
must not mask it (independently verified in a throwaway copy: without
this, junit parsing order let a later passing sibling overwrite an
earlier skip/failure for the same domain).

Known limitation (NF-7, disclosed not fixed): this checks outcomes by
name, not content. A hollow test body, a domain-level `conftest.py` that
fakes `scaffold_db`, or an edit to this file's own `DOMAINS` tuple all
stay green — any test-level check has this limit when its own files can
be edited.

**R15-3 (round 15):** this file's own two guard functions below had the
same unprotected gap `test_financial_invariant_scaffold.py`'s R15-1
found — skipping or rebinding both of them left a genuinely broken
domain (`access`, broken) reported as `2 skipped` or, worse, an
affirmative `2 passed`, in both cases with `mypy --strict` clean. Closed
by importing this project's shared execution-suppression guard (see
`_execution_suppression_guard.py`) and calling it eagerly at this file's
own module level, below — the same mechanism, not a second
independently-written implementation that could itself diverge or be
buggy. See BUG-050's round-15 remediation section for the reproduction
evidence (`d3`/`d4`).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from tests.contract._execution_suppression_guard import assert_execution_not_suppressed

DOMAINS = ("membership", "booking", "payment", "ledger", "pos", "access")

_GUARD_NAMES = frozenset(
    {"test_all_six_domain_scaffold_paths_exist", "test_all_six_domain_scaffolds_pass"}
)

assert_execution_not_suppressed(Path(__file__), _GUARD_NAMES)

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _domain_scaffold_path(domain: str) -> Path:
    return _BACKEND_ROOT / "app" / "modules" / domain / "tests" / "test_scaffold_live.py"


def test_all_six_domain_scaffold_paths_exist() -> None:
    missing = [d for d in DOMAINS if not _domain_scaffold_path(d).is_file()]
    assert not missing, f"missing domain scaffold(s): {missing}"


def test_all_six_domain_scaffolds_pass() -> None:
    with tempfile.TemporaryDirectory(prefix="veyro-scaffold-inventory-") as tmp:
        junit_path = Path(tmp) / "junit.xml"
        paths = [str(_domain_scaffold_path(domain)) for domain in DOMAINS]
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", f"--junitxml={junit_path}", *paths],
            cwd=_BACKEND_ROOT,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        _assert_inventory_clean(result, junit_path)


def _assert_inventory_clean(result: subprocess.CompletedProcess[str], junit_path: Path) -> None:
    report = _parse_junit(junit_path) if junit_path.is_file() else {}
    not_clean = {
        domain: report.get(domain, "NOT_COLLECTED")
        for domain in DOMAINS
        if report.get(domain) != "passed"
    }
    if not_clean or result.returncode != 0:
        raise AssertionError(
            f"domain scaffold inventory not clean (exit={result.returncode}): {not_clean}\n"
            f"{result.stdout[-4000:]}"
        )


def _parse_junit(junit_path: Path) -> dict[str, str]:
    """Map each domain to 'passed', or a status/count string if its own
    `test_scaffold_live` testcase (and only that testcase, by name) wasn't
    found exactly once and clean. Never last-write-wins across testcases —
    see NF-3, a later differently-named passing sibling must not overwrite
    an earlier skip/failure for the same domain."""
    root = ET.parse(junit_path).getroot()
    statuses: dict[str, list[str]] = {domain: [] for domain in DOMAINS}
    for testcase in root.iter("testcase"):
        if testcase.get("name") != "test_scaffold_live":
            continue
        classname = testcase.get("classname", "")
        domain = next((d for d in DOMAINS if f".{d}." in f".{classname}."), None)
        if domain is None:
            continue
        if testcase.find("failure") is not None:
            statuses[domain].append("failed")
        elif testcase.find("error") is not None:
            statuses[domain].append("error")
        elif testcase.find("skipped") is not None:
            statuses[domain].append("skipped")
        else:
            statuses[domain].append("passed")
    return {
        domain: found[0] if len(found) == 1 else f"EXPECTED_EXACTLY_ONE_GOT_{len(found)}:{found}"
        for domain, found in statuses.items()
    }

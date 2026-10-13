#!/usr/bin/env python3
"""
Focused tests for tools/scan_dependency_advisories.py (MOD-001,
GOV-01-R03/R04, input to SCN-MOD001-094).

Stdlib `unittest` only — same convention as
`tools/tests/test_assert_ci_python313.py`. pytest (CAP-011) and Ruff
(CAP-010) are both registered DRAFT/QUALIFIED-not-APPROVED with "no
reliance of any kind permitted", so this file is deliberately runnable by
the interpreter alone: `python -I -m unittest`.

**No live network and no real lock file.** Every advisory response is an
injected fixture; the module's one network path (`_urllib_fetcher`) is never
called, which `NoLiveRequestTests` asserts structurally. Each lock fixture is
a throwaway file in a `tempfile` directory, written in the exact shape
`tools/generate_requirements_lock.py` emits. No package is installed.

**All advisory identifiers here are synthetic and deliberately impossible:**
`CVE-1900-0001` (CVE IDs do not predate 1999) and `GHSA-aaaa-bbbb-cccc`.
No real CVE is invented or asserted. SCN-MOD001-094's live execution needs a
genuine long-since-fixed historical CVE chosen from the advisory source at
execution time; that remains an unexecuted dependency, recorded in this
operation's evidence note rather than guessed at here.
"""

import contextlib
import inspect
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import scan_dependency_advisories as mod  # noqa: E402

CLEAN_PKG = "veyro-synthetic-clean"
VULN_PKG = "veyro-synthetic-vulnerable"
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64

SYNTHETIC_CVE = "CVE-1900-0001"
SYNTHETIC_GHSA = "GHSA-aaaa-bbbb-cccc"
SENTINEL = "veyro-untrusted-sentinel-must-not-be-echoed"

VULNERABLE_RESPONSE = {
    "vulns": [
        {
            "id": SYNTHETIC_GHSA,
            "aliases": [SYNTHETIC_CVE, "PYSEC-1900-0001"],
            "summary": SENTINEL,
            "details": SENTINEL,
            "affected": [{"package": {"name": SENTINEL}}],
        }
    ]
}


def lock_text(*entries: tuple[str, str, str]) -> str:
    """The generated lock shape: `name==version \\` then one sha256 line."""
    lines = ["# throwaway synthetic fixture — not a real lock", ""]
    for name, version, digest in entries:
        lines.append(f"{name}=={version} \\")
        lines.append(f"    --hash=sha256:{digest}")
    return "\n".join(lines) + "\n"


def responder(mapping, status=200):
    """Fetcher returning a canned JSON body per package name. Records calls."""
    calls: list[tuple[str, dict, float]] = []

    def fetch(url, payload, timeout):
        request = json.loads(payload.decode("utf-8"))
        calls.append((url, request, timeout))
        name = request["package"]["name"]
        body = mapping[name]
        if isinstance(body, BaseException):
            raise body
        if isinstance(body, bytes):
            return mod.FetchResult(status, body)
        return mod.FetchResult(status, json.dumps(body).encode("utf-8"))

    fetch.calls = calls
    return fetch


class LockFixtureCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="veyro-advisory-fixture-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.out: list[str] = []

    def write_lock(self, text, name="requirements-throwaway.lock.txt"):
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return path

    def scan(self, path, fetcher, **kwargs):
        return mod.run_scan(path, fetcher=fetcher, emit=self.out.append, **kwargs)

    def joined(self):
        return "\n".join(self.out)


class ParserTests(LockFixtureCase):
    def test_parses_generated_shape_deterministically(self):
        path = self.write_lock(
            lock_text((VULN_PKG, "1.2.3", DIGEST_B), (CLEAN_PKG, "4.5.6", DIGEST_A))
        )
        entries, problems = mod.parse_lock(path)
        self.assertEqual(problems, [])
        self.assertEqual(
            entries,
            [
                mod.LockEntry(CLEAN_PKG, "4.5.6", DIGEST_A),
                mod.LockEntry(VULN_PKG, "1.2.3", DIGEST_B),
            ],
        )

    def test_absent_lock_denies(self):
        entries, problems = mod.parse_lock(self.tmp / "does-not-exist.txt")
        self.assertEqual(entries, [])
        self.assertIn("MISSING_LOCK", problems[0])

    def test_unreadable_lock_denies(self):
        path = self.write_lock("")
        path.write_bytes(b"\xff\xfe not utf-8 \xff")
        entries, problems = mod.parse_lock(path)
        self.assertEqual(entries, [])
        self.assertIn("UNREADABLE_LOCK", problems[0])

    def test_empty_lock_denies(self):
        path = self.write_lock("# only a comment\n\n")
        entries, problems = mod.parse_lock(path)
        self.assertEqual(entries, [])
        self.assertIn("EMPTY_LOCK", problems[0])

    def test_directory_as_lock_denies(self):
        entries, problems = mod.parse_lock(self.tmp)
        self.assertEqual(entries, [])
        self.assertIn("UNREADABLE_LOCK", problems[0])

    def test_unpinned_entry_denies(self):
        for line in (
            f"{CLEAN_PKG}>=4.5.6",
            f"{CLEAN_PKG}~=4.5",
            CLEAN_PKG,
            f"{CLEAN_PKG}==4.5.6; python_version < '3.13'",
            f"{CLEAN_PKG}[extra]==4.5.6",
            f"{CLEAN_PKG}==*",
        ):
            with self.subTest(line=line):
                path = self.write_lock(f"{line} \\\n    --hash=sha256:{DIGEST_A}\n")
                entries, problems = mod.parse_lock(path)
                self.assertEqual(entries, [])
                self.assertTrue(any("UNPINNED_LOCK_ENTRY" in p for p in problems), problems)

    def test_pip_directive_denies(self):
        path = self.write_lock("-r other-requirements.txt\n--index-url https://example.invalid\n")
        entries, problems = mod.parse_lock(path)
        self.assertEqual(entries, [])
        self.assertEqual(len(problems), 2)
        self.assertTrue(all("MALFORMED_LOCK_ENTRY" in p for p in problems))

    def test_missing_hash_line_denies(self):
        path = self.write_lock(f"{CLEAN_PKG}==4.5.6\n")
        entries, problems = mod.parse_lock(path)
        self.assertEqual(entries, [])
        self.assertIn("MALFORMED_LOCK_ENTRY", problems[0])

    def test_malformed_hash_denies(self):
        for bad in ("sha256:" + "a" * 63, "sha256:" + "A" * 64, "md5:" + "a" * 32):
            with self.subTest(bad=bad):
                path = self.write_lock(f"{CLEAN_PKG}==4.5.6 \\\n    --hash={bad}\n")
                entries, problems = mod.parse_lock(path)
                self.assertEqual(entries, [])
                self.assertIn("MALFORMED_LOCK_ENTRY", problems[0])

    def test_orphan_hash_line_denies(self):
        path = self.write_lock(f"    --hash=sha256:{DIGEST_A}\n")
        entries, problems = mod.parse_lock(path)
        self.assertEqual(entries, [])
        self.assertIn("MALFORMED_LOCK_ENTRY", problems[0])

    def test_second_hash_line_denies(self):
        path = self.write_lock(
            f"{CLEAN_PKG}==4.5.6 \\\n    --hash=sha256:{DIGEST_A} \\\n"
            f"    --hash=sha256:{DIGEST_B}\n"
        )
        entries, problems = mod.parse_lock(path)
        self.assertEqual(entries, [])
        self.assertIn("MALFORMED_LOCK_ENTRY", problems[0])

    def test_duplicate_entry_denies(self):
        path = self.write_lock(
            lock_text((CLEAN_PKG, "4.5.6", DIGEST_A), (CLEAN_PKG, "4.5.7", DIGEST_B))
        )
        _entries, problems = mod.parse_lock(path)
        self.assertTrue(any("DUPLICATE_LOCK_ENTRY" in p for p in problems), problems)

    def test_real_project_lock_shape_parses(self):
        """Parses a copy of the generated project lock's own shape — copied
        into the throwaway directory, never scanned in place and never queried."""
        source = TOOLS.parent / "backend" / "requirements-dev.lock.txt"
        path = self.write_lock(source.read_text(encoding="utf-8"), name="copied-shape.txt")
        entries, problems = mod.parse_lock(path)
        self.assertEqual(problems, [])
        self.assertGreater(len(entries), 1)
        self.assertEqual(entries, sorted(entries))


class AdvisoryResponseTests(LockFixtureCase):
    def setUp(self):
        super().setUp()
        self.one_pkg = self.write_lock(lock_text((VULN_PKG, "1.2.3", DIGEST_B)))
        self.two_pkg = self.write_lock(
            lock_text((VULN_PKG, "1.2.3", DIGEST_B), (CLEAN_PKG, "4.5.6", DIGEST_A)),
            name="two.lock.txt",
        )

    def test_known_vulnerable_response_denies_citing_cve(self):
        fetch = responder({VULN_PKG: VULNERABLE_RESPONSE})
        self.assertEqual(self.scan(self.one_pkg, fetch), 1)
        report = self.joined()
        self.assertIn("VULNERABILITY_ADVISORY_PRESENT", report)
        self.assertIn(SYNTHETIC_GHSA, report)
        self.assertIn(SYNTHETIC_CVE, report)
        self.assertIn("RESULT: DENY", report)

    def test_cve_as_primary_id_is_cited(self):
        fetch = responder({VULN_PKG: {"vulns": [{"id": SYNTHETIC_CVE}]}})
        self.assertEqual(self.scan(self.one_pkg, fetch), 1)
        self.assertIn(SYNTHETIC_CVE, self.joined())

    def test_advisory_without_cve_alias_still_denies(self):
        fetch = responder({VULN_PKG: {"vulns": [{"id": SYNTHETIC_GHSA, "aliases": []}]}})
        self.assertEqual(self.scan(self.one_pkg, fetch), 1)
        self.assertIn("no CVE alias", self.joined())

    def test_patched_clean_response_allows(self):
        # An absent 'vulns' key (OSV's own shape for "no advisories") and an
        # empty list are the only clean shapes; an explicit null is not — see
        # test_null_vulns_denies_as_malformed.
        for clean in ({}, {"vulns": []}):
            with self.subTest(clean=clean):
                self.out = []
                fetch = responder({VULN_PKG: clean})
                self.assertEqual(self.scan(self.one_pkg, fetch), 0)
                self.assertIn("RESULT: ALLOW", self.joined())

    def test_null_vulns_denies_as_malformed(self):
        fetch = responder({VULN_PKG: {"vulns": None}})
        self.assertEqual(self.scan(self.one_pkg, fetch), 2)
        report = self.joined()
        self.assertIn("MALFORMED_ADVISORY_RESPONSE", report)
        self.assertNotIn("RESULT: ALLOW", report)

    def test_one_vulnerable_package_is_not_masked_by_a_clean_one(self):
        fetch = responder({VULN_PKG: VULNERABLE_RESPONSE, CLEAN_PKG: {}})
        self.assertEqual(self.scan(self.two_pkg, fetch), 1)
        report = self.joined()
        self.assertIn(f"{CLEAN_PKG}==4.5.6: CLEAN", report)
        self.assertIn(SYNTHETIC_CVE, report)

    def test_unreachable_source_denies(self):
        fetch = responder({VULN_PKG: urllib.error.URLError("unreachable")})
        self.assertEqual(self.scan(self.one_pkg, fetch), 2)
        self.assertIn("ADVISORY_SOURCE_UNREACHABLE", self.joined())

    def test_timeout_denies(self):
        fetch = responder({VULN_PKG: TimeoutError("timed out")})
        self.assertEqual(self.scan(self.one_pkg, fetch), 2)
        self.assertIn("ADVISORY_SOURCE_UNREACHABLE", self.joined())

    def test_unexpected_exception_denies(self):
        fetch = responder({VULN_PKG: RuntimeError("boom")})
        self.assertEqual(self.scan(self.one_pkg, fetch), 2)
        self.assertIn("ADVISORY_SOURCE_UNREACHABLE", self.joined())

    def test_http_error_denies(self):
        fetch = responder(
            {VULN_PKG: urllib.error.HTTPError(mod.OSV_QUERY_URL, 503, "nope", {}, None)}
        )
        self.assertEqual(self.scan(self.one_pkg, fetch), 2)
        report = self.joined()
        self.assertIn("ADVISORY_SOURCE_HTTP_STATUS", report)
        self.assertIn("503", report)

    def test_non_200_status_denies(self):
        fetch = responder({VULN_PKG: {}}, status=204)
        self.assertEqual(self.scan(self.one_pkg, fetch), 2)
        self.assertIn("ADVISORY_SOURCE_HTTP_STATUS", self.joined())

    def test_oversized_response_denies_unparsed(self):
        oversized = b'{"vulns": []' + b" " * (mod.MAX_RESPONSE_BYTES + 1) + b"}"
        fetch = responder({VULN_PKG: oversized})
        self.assertEqual(self.scan(self.one_pkg, fetch), 2)
        self.assertIn("ADVISORY_RESPONSE_TOO_LARGE", self.joined())

    def test_at_size_limit_response_is_still_parsed(self):
        padding = mod.MAX_RESPONSE_BYTES - len(b'{"vulns": []}')
        fetch = responder({VULN_PKG: b'{"vulns": []' + b" " * padding + b"}"})
        self.assertEqual(self.scan(self.one_pkg, fetch), 0)

    def test_malformed_response_bodies_deny(self):
        bodies = {
            "not json": b"<html>not json</html>",
            "json array": b"[]",
            "json scalar": b"42",
            "vulns not list": b'{"vulns": {"id": "GHSA-aaaa-bbbb-cccc"}}',
            "vuln not object": b'{"vulns": ["GHSA-aaaa-bbbb-cccc"]}',
            "aliases not list": b'{"vulns": [{"id": "GHSA-aaaa-bbbb-cccc", "aliases": 7}]}',
            "alias not string": b'{"vulns": [{"id": "GHSA-aaaa-bbbb-cccc", "aliases": [7]}]}',
            "not utf-8": b'{"vulns": [{"id": "\xff\xfe"}]}',
        }
        for label, body in bodies.items():
            with self.subTest(case=label):
                self.out = []
                fetch = responder({VULN_PKG: body})
                self.assertEqual(self.scan(self.one_pkg, fetch), 2)
                self.assertIn("MALFORMED_ADVISORY_RESPONSE", self.joined())

    def test_missing_or_invalid_advisory_id_denies(self):
        for bad in (None, "", "lower-case-1234", "x" * 200, 7, {"id": "nested"}):
            with self.subTest(bad=bad):
                self.out = []
                vuln = {} if bad is None else {"id": bad}
                fetch = responder({VULN_PKG: {"vulns": [vuln]}})
                self.assertEqual(self.scan(self.one_pkg, fetch), 2)
                self.assertIn("INVALID_ADVISORY_ID", self.joined())

    def test_too_many_advisories_denies(self):
        vulns = [{"id": f"GHSA-aaaa-bbbb-{index:04d}"} for index in range(300)]
        fetch = responder({VULN_PKG: {"vulns": vulns}})
        self.assertEqual(self.scan(self.one_pkg, fetch), 2)
        self.assertIn("MALFORMED_ADVISORY_RESPONSE", self.joined())

    def test_lock_problem_short_circuits_before_any_query(self):
        path = self.write_lock("# nothing here\n", name="empty.lock.txt")
        fetch = responder({})
        self.assertEqual(self.scan(path, fetch), 2)
        self.assertEqual(fetch.calls, [])


class ReportHygieneTests(LockFixtureCase):
    def setUp(self):
        super().setUp()
        self.one_pkg = self.write_lock(lock_text((VULN_PKG, "1.2.3", DIGEST_B)))

    def test_untrusted_response_fields_are_not_echoed(self):
        fetch = responder({VULN_PKG: VULNERABLE_RESPONSE})
        self.assertEqual(self.scan(self.one_pkg, fetch), 1)
        self.assertNotIn(SENTINEL, self.joined())

    def test_rejected_advisory_id_value_is_not_echoed(self):
        fetch = responder({VULN_PKG: {"vulns": [{"id": SENTINEL}]}})
        self.assertEqual(self.scan(self.one_pkg, fetch), 2)
        self.assertNotIn(SENTINEL, self.joined())

    def test_non_cve_aliases_are_counted_not_echoed(self):
        fetch = responder(
            {VULN_PKG: {"vulns": [{"id": SYNTHETIC_GHSA, "aliases": [SENTINEL, SENTINEL]}]}}
        )
        self.assertEqual(self.scan(self.one_pkg, fetch), 1)
        report = self.joined()
        self.assertNotIn(SENTINEL, report)
        self.assertIn("2 non-CVE alias value(s) ignored", report)

    def test_duplicate_advisories_and_aliases_are_deduplicated(self):
        duplicated = {
            "vulns": [
                {"id": SYNTHETIC_GHSA, "aliases": [SYNTHETIC_CVE, SYNTHETIC_CVE]},
                {"id": SYNTHETIC_GHSA, "aliases": [SYNTHETIC_CVE]},
            ]
        }
        fetch = responder({VULN_PKG: duplicated})
        self.assertEqual(self.scan(self.one_pkg, fetch), 1)
        findings = [line for line in self.out if line.startswith("finding:")]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].count(SYNTHETIC_CVE), 1)

    def test_output_is_stable_across_runs(self):
        first, second = [], []
        for sink in (first, second):
            fetch = responder({VULN_PKG: VULNERABLE_RESPONSE})
            self.assertEqual(
                mod.run_scan(self.one_pkg, fetcher=fetch, emit=sink.append), 1
            )
        self.assertEqual(first, second)


class VerdictTests(unittest.TestCase):
    def test_allow_requires_a_clean_result_for_every_package(self):
        self.assertEqual(mod.decide(2, 2, [], [])[0], 0)

    def test_short_clean_count_is_incomplete_coverage_not_a_pass(self):
        code, verdict = mod.decide(2, 1, [], [])
        self.assertEqual(code, 2)
        self.assertIn("INCOMPLETE_ADVISORY_COVERAGE", verdict)

    def test_zero_packages_is_never_a_pass(self):
        self.assertEqual(mod.decide(0, 0, [], [])[0], 2)

    def test_finding_takes_precedence_over_error(self):
        self.assertEqual(mod.decide(2, 0, ["f"], ["e"])[0], 1)

    def test_error_alone_denies(self):
        self.assertEqual(mod.decide(1, 0, [], ["e"])[0], 2)


class TimeoutBoundTests(LockFixtureCase):
    def setUp(self):
        super().setUp()
        self.one_pkg = self.write_lock(lock_text((CLEAN_PKG, "4.5.6", DIGEST_A)))

    def test_timeout_is_passed_to_every_query(self):
        fetch = responder({CLEAN_PKG: {}})
        self.assertEqual(self.scan(self.one_pkg, fetch, timeout=2.5), 0)
        self.assertEqual([call[2] for call in fetch.calls], [2.5])

    def test_default_timeout_is_bounded(self):
        self.assertGreater(mod.DEFAULT_TIMEOUT_SECONDS, 0)
        self.assertLessEqual(mod.DEFAULT_TIMEOUT_SECONDS, mod.MAX_TIMEOUT_SECONDS)

    def test_invalid_timeout_denies_without_querying(self):
        for bad in (0, -1.0, mod.MAX_TIMEOUT_SECONDS + 1, float("nan")):
            with self.subTest(bad=bad):
                self.out = []
                fetch = responder({CLEAN_PKG: {}})
                self.assertEqual(self.scan(self.one_pkg, fetch, timeout=bad), 2)
                self.assertIn("INVALID_TIMEOUT", self.joined())
                self.assertEqual(fetch.calls, [])


class NoLiveRequestTests(LockFixtureCase):
    def test_queries_exactly_the_locked_pins_and_nothing_else(self):
        path = self.write_lock(
            lock_text((VULN_PKG, "1.2.3", DIGEST_B), (CLEAN_PKG, "4.5.6", DIGEST_A))
        )
        fetch = responder({VULN_PKG: {}, CLEAN_PKG: {}})
        self.assertEqual(self.scan(path, fetch), 0)
        self.assertEqual(
            [(call[1]["package"]["name"], call[1]["version"]) for call in fetch.calls],
            [(CLEAN_PKG, "4.5.6"), (VULN_PKG, "1.2.3")],
        )
        self.assertEqual({call[1]["package"]["ecosystem"] for call in fetch.calls}, {"PyPI"})
        self.assertEqual({call[0] for call in fetch.calls}, {mod.OSV_QUERY_URL})

    def test_network_path_is_injectable_so_no_test_can_reach_it(self):
        """Structural guard: `main` and `run_scan` both accept the fetcher as a
        parameter whose only default is the single network implementation, so a
        test reaches the network only by explicitly asking for it — never by
        forgetting to patch a module global."""
        for function in (mod.main, mod.run_scan):
            with self.subTest(function=function.__name__):
                default = inspect.signature(function).parameters["fetcher"].default
                self.assertIs(default, mod._urllib_fetcher)
        path = self.write_lock(lock_text((CLEAN_PKG, "4.5.6", DIGEST_A)))
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            code = mod.main([str(path)], fetcher=responder({CLEAN_PKG: {}}))
        self.assertEqual(code, 0)
        self.assertIn("RESULT: ALLOW", captured.getvalue())

    def test_cli_requires_an_explicit_lockfile_path(self):
        with self.assertRaises(SystemExit) as raised:
            mod.parse_args([])
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

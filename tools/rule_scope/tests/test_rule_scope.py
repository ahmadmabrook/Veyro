"""Deterministic tests for the MOD-004 Rule path-scope qualification harness.
Run: python3 -m unittest discover -s tools/rule_scope/tests -t tools/rule_scope

Every test either builds its own temporary tree or reads the real repository read-only; nothing is
written inside the repository, and no rule file is modified (qualification is not modification).

The negative controls matter as much as the positives here. A path-scope corpus that only ever
asserts what *does* match would be satisfied by a glob of `**`, and one that only asserts what
does not would be satisfied by an empty glob set. `TestCorpusIsNotVacuous` substitutes a
match-everything and a match-nothing matcher and requires the corpus to BLOCK for both.
"""
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import rule_scope as rs  # noqa: E402

REPO = HERE.parent.parent.parent
CORPUS = HERE.parent / rs.CORPUS
RLS_RULE = ".claude/rules/backend/mod004-rls.md"
CONSOLE_RULE = ".claude/rules/admin/mod004-privileged-console.md"

FRONT_MATTER = """---
description: a test rule
paths:
  - "backend/app/tenancy/**"
---

# body
"""


class TestGlobSemantics(unittest.TestCase):
    """The semantics the module docstring states, pinned so they cannot drift silently."""

    def test_double_star_crosses_separators(self):
        self.assertTrue(rs.matches("backend/app/tenancy/**", "backend/app/tenancy/a/b/c.py"))

    def test_double_star_requires_the_separator_before_it(self):
        # The prefix near-miss a startswith() implementation gets wrong, and the specific one that
        # keeps the published S0 slice outside RULE-001.
        self.assertFalse(rs.matches("backend/app/tenancy/**", "backend/app/tenancy_s0.py"))
        self.assertFalse(rs.matches("backend/app/tenancy/**", "backend/app/tenancyx/c.py"))

    def test_trailing_double_star_excludes_the_directory_itself(self):
        self.assertFalse(rs.matches("backend/migrations/**", "backend/migrations"))

    def test_pattern_is_anchored_at_the_start(self):
        self.assertFalse(rs.matches("infra/db/**", "xinfra/db/init.sql"))
        self.assertFalse(rs.matches("infra/db/**", "vendor/infra/db/init.sql"))

    def test_single_star_does_not_cross_a_separator(self):
        self.assertTrue(rs.matches("backend/*.txt", "backend/requirements.txt"))
        self.assertFalse(rs.matches("backend/*.txt", "backend/app/requirements.txt"))

    def test_question_mark_matches_one_non_separator(self):
        self.assertTrue(rs.matches("a/?.sql", "a/1.sql"))
        self.assertFalse(rs.matches("a/?.sql", "a/12.sql"))
        self.assertFalse(rs.matches("a/?.sql", "a//.sql"))

    def test_matching_is_case_sensitive(self):
        self.assertFalse(rs.matches("backend/app/tenancy/**", "Backend/app/tenancy/c.py"))

    def test_dots_are_literal_not_wildcards(self):
        self.assertTrue(rs.matches("infra/db/init.sql", "infra/db/init.sql"))
        self.assertFalse(rs.matches("infra/db/init.sql", "infra/db/initxsql"))

    def test_known_divergences_from_gitignore_are_deliberate(self):
        # Documented in the module docstring. Pinned so they stay deliberate rather than drifting
        # into accidents. Neither rule being qualified uses a non-trailing `**` or a bracket, but a
        # third rule that did would need the matcher corrected first.
        self.assertFalse(rs.matches("**/x.py", "x.py"))        # gitignore would match
        self.assertTrue(rs.matches("**/x.py", "a/b/x.py"))
        self.assertFalse(rs.matches("a/**/b", "a/b"))          # gitignore would match
        self.assertTrue(rs.matches("a/**/b", "a/mid/b"))
        self.assertTrue(rs.matches("a[b]/**", "a[b]/c.py"))    # literal, not a character class
        self.assertFalse(rs.matches("a[b]/**", "ab/c.py"))
        self.assertFalse(rs.matches("backend/app/tenancy/**", "./backend/app/tenancy/x.py"))

    def test_regex_metacharacters_in_a_glob_are_literal(self):
        for glob, path in (("a+b/**", "a+b/c.py"), ("a(b)/**", "a(b)/c.py")):
            self.assertTrue(rs.matches(glob, path), glob)
        self.assertFalse(rs.matches("a.b/**", "axb/c.py"))

    def test_absolute_and_backslash_globs_are_refused(self):
        for bad in ("/backend/**", "backend\\app\\**", ""):
            with self.assertRaises(rs.Malformed, msg=bad):
                rs.compile_glob(bad)


class TestParseRuleFailsClosed(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def write(self, text):
        path = self.tmp / "rule.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_parses_a_well_formed_rule(self):
        rule = rs.parse_rule(self.write(FRONT_MATTER))
        self.assertEqual(rule["paths"], ["backend/app/tenancy/**"])
        self.assertEqual(rule["description"], "a test rule")

    def test_comments_and_blank_lines_are_skipped(self):
        text = FRONT_MATTER.replace('paths:\n', 'paths:\n# a comment\n\n')
        self.assertEqual(rs.parse_rule(self.write(text))["paths"], ["backend/app/tenancy/**"])

    def test_missing_front_matter(self):
        with self.assertRaises(rs.Malformed):
            rs.parse_rule(self.write("# just a body\n"))

    def test_unclosed_front_matter(self):
        with self.assertRaises(rs.Malformed):
            rs.parse_rule(self.write("---\ndescription: x\npaths:\n  - \"a/**\"\n"))

    def test_no_paths_declared(self):
        with self.assertRaises(rs.Malformed):
            rs.parse_rule(self.write("---\ndescription: x\n---\n"))

    def test_unrecognised_front_matter_line_is_an_error_not_a_skip(self):
        # A rule whose front matter changes shape must fail loudly rather than qualify with an
        # empty or truncated glob set.
        with self.assertRaises(rs.Malformed):
            rs.parse_rule(self.write("---\ndescription: x\npaths:\n  nonsense\n---\n"))

    def test_bad_glob_inside_valid_front_matter(self):
        with self.assertRaises(rs.Malformed):
            rs.parse_rule(self.write("---\npaths:\n  - \"/absolute/**\"\n---\n"))

    def test_missing_file(self):
        with self.assertRaises(rs.Malformed):
            rs.parse_rule(self.tmp / "absent.md")


class TestTheRealRules(unittest.TestCase):
    """Read the two rule files as they stand. No rule file is written by any test."""

    def test_rls_rule_declares_exactly_the_s1_paths(self):
        rule = rs.parse_rule(REPO / RLS_RULE)
        self.assertEqual(rule["paths"], [
            "backend/app/tenancy/**",
            "backend/migrations/**",
            "backend/tests/integration/tenancy/**",
            "infra/db/**",
        ])

    def test_console_rule_declares_exactly_one_placeholder_glob(self):
        rule = rs.parse_rule(REPO / CONSOLE_RULE)
        self.assertEqual(rule["paths"], ["frontend/console/con-04-tenant-provisioning/**"])

    def test_published_s0_slice_is_outside_both_rules(self):
        # contracts/engineering/mod004-s0-capability.json asserts this; here it is re-derived from
        # the rule files rather than restated.
        s0 = ("backend/app/tenancy_s0.py", "backend/tests/test_tenancy_s0.py")
        for rule_rel in (RLS_RULE, CONSOLE_RULE):
            rule = rs.parse_rule(REPO / rule_rel)
            for path in s0:
                hits = [g for g in rule["paths"] if rs.matches(g, path)]
                self.assertEqual(hits, [], f"{rule_rel} reaches {path}")

    def test_neither_rule_matches_any_file_in_the_repository_today(self):
        # Recorded as a fact about the current tree, not as a requirement: both rules are
        # forward-looking declarations, so nothing exercises either of them yet.
        report = rs.check(REPO)
        for entry in report["rules"]:
            self.assertEqual(entry["matched_files_in_repository"], [], entry["rule"])

    def test_check_reports_each_rule_file_hash(self):
        # Both RULE records carry the rule file's hash as NOT_COMPUTED with "runner must verify
        # externally", and the runner is retired. This makes it computable here.
        import hashlib
        report = rs.check(REPO)
        for entry in report["rules"]:
            expected = hashlib.sha256(Path(entry["rule"]).read_bytes()).hexdigest()
            self.assertEqual(entry["sha256"], expected)
            self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")

    def test_check_reports_the_absent_declared_directories(self):
        report = rs.check(REPO)
        absent = {d for e in report["rules"] for d in e["declared_directories_absent"]}
        self.assertEqual(absent, {
            "backend/app/tenancy/**",
            "backend/migrations/**",
            "backend/tests/integration/tenancy/**",
            "infra/db/**",
            "frontend/console/con-04-tenant-provisioning/**",
        })

    def test_s0_capability_declaration_pins_the_correct_rule_hashes(self):
        """The S0 declaration pins both rule files by SHA-256; verify rather than trust.

        `contracts/engineering/mod004-s0-capability.json` lists them under
        `out_of_scope_existing_rules` to support its claim that the S0 paths fall outside both rule
        globs. Those hashes had never been checked against the files: RULE-001 and RULE-002 both
        record the rule-file hash as `NOT_COMPUTED in the authoring session (no hashing tool);
        runner must verify externally`, and the runner is retired. If this test ever fails, either
        a rule file changed or the declaration is stale -- and in the first case the glob
        assertions above need rechecking too.
        """
        import hashlib
        declaration = json.loads(
            (REPO / "contracts/engineering/mod004-s0-capability.json").read_text(encoding="utf-8"))
        pinned = declaration["out_of_scope_existing_rules"]
        self.assertEqual({entry["path"] for entry in pinned}, {RLS_RULE, CONSOLE_RULE})
        for entry in pinned:
            actual = hashlib.sha256((REPO / entry["path"]).read_bytes()).hexdigest()
            self.assertEqual(entry["sha256"], actual, entry["path"])

    def test_every_rule_file_has_a_corpus_entry(self):
        data = json.loads(CORPUS.read_text(encoding="utf-8"))
        covered = {entry["rule"] for entry in data["rules"]}
        found = {p.relative_to(REPO).as_posix() for p in rs.find_rules(REPO)}
        self.assertEqual(covered, found)


class TestCorpus(unittest.TestCase):
    def test_corpus_passes(self):
        self.assertEqual(rs.run_corpus(REPO, CORPUS), [])

    def test_corpus_pins_each_rule_declared_paths(self):
        data = json.loads(CORPUS.read_text(encoding="utf-8"))
        for entry in data["rules"]:
            self.assertIn("declared_paths", entry, entry["rule"])
            self.assertTrue(entry["must_match"])
            self.assertTrue(entry["must_not_match"])


class TestCorpusIsNotVacuous(unittest.TestCase):
    """Substitute a broken matcher; the corpus must BLOCK. Without these a PASS proves nothing."""

    def test_a_matcher_that_matches_everything_fails(self):
        with mock.patch.object(rs, "matches", return_value=True):
            failures = rs.run_corpus(REPO, CORPUS)
        self.assertTrue(failures)
        self.assertTrue(any("must not match" in f["detail"] for f in failures))

    def test_a_matcher_that_matches_nothing_fails(self):
        with mock.patch.object(rs, "matches", return_value=False):
            failures = rs.run_corpus(REPO, CORPUS)
        self.assertTrue(failures)
        self.assertTrue(any("must match" in f["detail"] for f in failures))

    def test_a_widened_rule_glob_fails_the_pinned_declaration(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        shutil.copytree(REPO / ".claude", tmp / ".claude")
        widened = tmp / RLS_RULE
        widened.write_text(
            widened.read_text(encoding="utf-8").replace(
                '  - "infra/db/**"', '  - "infra/db/**"\n  - "backend/**"'),
            encoding="utf-8")
        failures = rs.run_corpus(tmp, CORPUS)
        self.assertTrue(any("declared paths changed" in f["detail"] for f in failures))
        self.assertTrue(any("must not match" in f["detail"] for f in failures))

    def test_a_corpus_entry_with_only_positives_is_malformed(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        data = json.loads(CORPUS.read_text(encoding="utf-8"))
        data["rules"][0]["must_not_match"] = []
        path = tmp / "corpus.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(rs.Malformed):
            rs.run_corpus(REPO, path)

    def test_an_uncovered_rule_file_is_a_failure(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        shutil.copytree(REPO / ".claude", tmp / ".claude")
        extra = tmp / ".claude" / "rules" / "backend" / "mod004-extra.md"
        extra.write_text(FRONT_MATTER, encoding="utf-8")
        failures = rs.run_corpus(tmp, CORPUS)
        self.assertTrue(any("no corpus entry" in f["detail"] for f in failures))

    def test_wrong_corpus_schema_is_malformed(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        path = tmp / "corpus.json"
        path.write_text(json.dumps({"schema": 99, "rules": []}), encoding="utf-8")
        with self.assertRaises(rs.Malformed):
            rs.run_corpus(REPO, path)


class TestCli(unittest.TestCase):
    def run_main(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = rs.main(argv)
        return code, json.loads(buf.getvalue())

    def test_corpus_exits_zero(self):
        code, out = self.run_main(["corpus", "--root", str(REPO), "--corpus", str(CORPUS)])
        self.assertEqual((code, out["result"]), (0, "PASS"))

    def test_check_exits_zero(self):
        code, out = self.run_main(["check", "--root", str(REPO)])
        self.assertEqual((code, out["result"]), (0, "PASS"))
        self.assertEqual(len(out["rules"]), 2)

    def test_scope_classifies_paths(self):
        code, out = self.run_main(["scope", "--rule", str(REPO / RLS_RULE),
                                   "backend/app/tenancy/context.py", "backend/app/tenancy_s0.py"])
        self.assertEqual(code, 0)
        self.assertEqual(out["classified"]["backend/app/tenancy/context.py"],
                         ["backend/app/tenancy/**"])
        self.assertEqual(out["classified"]["backend/app/tenancy_s0.py"], [])

    def test_missing_root_is_malformed(self):
        code, out = self.run_main(["check", "--root", "/nonexistent-veyro-root"])
        self.assertEqual((code, out["result"]), (2, "MALFORMED"))

    def test_missing_corpus_is_malformed(self):
        code, out = self.run_main(["corpus", "--root", str(REPO), "--corpus", "/absent.json"])
        self.assertEqual((code, out["result"]), (2, "MALFORMED"))

    def test_every_result_states_the_declared_scope_limit(self):
        for argv in (["check", "--root", str(REPO)],
                     ["corpus", "--root", str(REPO), "--corpus", str(CORPUS)]):
            _, out = self.run_main(argv)
            self.assertIn("rule matcher is not exercised", out["declared_scope_only"])
            self.assertIn("no RULE evidence ID follows", out["declared_scope_only"])


if __name__ == "__main__":
    unittest.main()

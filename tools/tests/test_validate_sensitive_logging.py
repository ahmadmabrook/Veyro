"""
Unit tests for tools/validate_sensitive_logging.py (MOD-001, GOV-01-R03/R04
— the card's mandatory Security-scope baseline control "sensitive logging";
SCN-MOD001-122).

The scenario's own steps drive tests 1-4: run the lint against a synthetic
log statement containing a secret-shaped pattern (an API-key-shaped string)
and a PII-shaped pattern (an email address) interpolated directly into log
text, expect both denied citing the exact file/line and pattern class, and
expect the companion positive (a pre-redacted placeholder) to pass.

  1. test_secret_shaped_literal_in_log_is_denied - an API-key-shaped string
     interpolated into log text -> DENY, pattern_class=SECRET_SHAPED.
  2. test_email_literal_in_log_is_denied - an email address interpolated
     into log text -> DENY, pattern_class=PII_SHAPED.
  3. test_both_pattern_classes_in_one_statement_are_both_reported - the
     scenario's exact negative step, both shapes in one log statement ->
     two findings, both classes named, both citing the same file/line.
  4. test_pre_redacted_placeholder_passes - the scenario's companion
     positive: a log statement carrying only `[REDACTED]`/`<redacted>`
     placeholders -> ALLOW.
  5. test_redaction_wrapper_call_passes - `redact(user.email)` -> ALLOW;
     the wrapper's whole argument subtree is skipped.
  6. test_redaction_marked_identifier_passes - `{email_hash}` -> ALLOW;
     the redaction marker is checked before the sensitive-name rules.
  7. test_lazy_percent_formatting_identifier_is_denied - the lazy-logging
     form `logger.warning("... %s", user.email)` -> DENY (PII), proving the
     check is not f-string-specific.
  8. test_camel_case_credential_identifier_is_denied - `{apiKey}` ->
     DENY (SECRET), proving identifier normalization, not a snake_case-only
     rule.
  9. test_keyword_argument_is_inspected - structured logging
     `extra={"actor": user.ssn}` -> DENY; keyword values are arguments too.
  10. test_non_log_call_is_not_inspected - the decisive distinction from
      SCN-029 secret-scanning: the same secret and email in a module
      assignment, a `print()` and an HTTP-client call -> ALLOW. This lint
      scans log statements, not arbitrary file contents.
  11. test_docstring_secret_is_not_inspected - the same shapes inside a
      module docstring -> ALLOW (same reason as 10).
  12. test_getlogger_receiver_chain_is_recognized -
      `logging.getLogger(__name__).info(...)` -> DENY; the receiver chain
      resolves through a call, not just a bare name.
  13. test_self_log_attribute_receiver_is_recognized - `self.log.error(...)`
      -> DENY; the receiver chain resolves through an attribute.
  14. test_file_and_line_are_reported - the diagnostic opens with
      `<file>:<line>:` naming the offending line, which is
      `IMPLEMENTATION.md` §3's required output shape.
  15. test_diagnostic_does_not_echo_the_matched_secret - the report masks
      every literal match; a denial must not republish the credential it
      found into a CI log.
  16. test_explicitly_fake_placeholder_and_opaque_token_boundary -
      `EXAMPLE_NOT_A_REAL_KEY` (the `.claude/rules/infra/secrets.md`
      placeholder convention) -> ALLOW, while a real opaque mixed
      letter/digit token of the same length -> DENY.
  17. test_unparseable_source_fails_closed - invalid Python ->
      UNPARSEABLE_SOURCE_FILE, not a zero-problem pass.
  18. test_unreadable_file_fails_closed - a path that does not exist ->
      UNREADABLE_SOURCE_FILE.
  19. test_missing_named_target_fails_closed - a named target that does not
      exist -> MISSING_SOURCE_PATH.
  20. test_empty_file_set_fails_closed - a directory with no *.py file ->
      NO_SOURCE_FILES, never a vacuous pass over nothing.
  21. test_require_log_statements_flag_converts_vacuous_pass_to_denial -
      zero log statements found: notice-only pass by default,
      NO_LOG_STATEMENTS_INSPECTED under the flag.
  22. test_current_repo_source_tree_passes - the real regression: the live
      default roots (which contain zero log statements today) produce zero
      problems, so this lint does not flag existing MOD-001 source.
  23. test_cli_exit_code_matches_verdict - `main()` driven as a real
      subprocess: exit 1 on an offending fixture, exit 0 on a clean one.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validate_sensitive_logging import (
    DEFAULT_SOURCE_ROOTS,
    PATTERN_CLASS_PII,
    PATTERN_CLASS_SECRET,
    evaluate_source_text,
    run_validation,
    validate_file,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VALIDATOR_SCRIPT = REPO_ROOT / "tools" / "validate_sensitive_logging.py"

# Synthetic, never-real fixture values. Both are deliberately
# self-labeling rather than plausible-looking, per
# `.claude/rules/infra/secrets.md` control 1 ("an explicitly-fake,
# clearly-labeled placeholder ... never a plausible-looking real-shaped
# value") — they still match the lint's rules, because what the
# `sk_prefixed_api_key` rule keys on is the vendor prefix, not entropy.
# `example.test` is a reserved test TLD, so no real member data is involved
# either (owner-reserved restriction 2).
FAKE_API_KEY = "sk-test-NOT-A-REAL-KEY-000000"
FAKE_EMAIL = "member@example.test"

LOGGER_PREAMBLE = "import logging\nlogger = logging.getLogger(__name__)\n"


def _problems(text: str, name: str = "fixture.py") -> list[str]:
    problems, _ = evaluate_source_text(text, name=name)
    return problems


def _inspected(text: str) -> int:
    _, inspected = evaluate_source_text(text, name="fixture.py")
    return inspected


def _assert_allowed(problems: list[str]) -> None:
    assert problems == [], problems


def _assert_denied(problems: list[str], pattern_class: str, rule: str) -> None:
    assert problems, "expected a denial, got a clean pass"
    matching = [
        p for p in problems if f"pattern_class={pattern_class}" in p and f"rule={rule}" in p
    ]
    assert matching, problems
    for problem in matching:
        assert "SENSITIVE_DATA_IN_LOG_STATEMENT" in problem, problem


def test_secret_shaped_literal_in_log_is_denied():
    text = LOGGER_PREAMBLE + f'logger.info(f"provisioned key {FAKE_API_KEY}")\n'
    problems = _problems(text)
    _assert_denied(problems, PATTERN_CLASS_SECRET, "sk_prefixed_api_key")


def test_email_literal_in_log_is_denied():
    text = LOGGER_PREAMBLE + f'logger.info("welcome mail sent to {FAKE_EMAIL}")\n'
    problems = _problems(text)
    _assert_denied(problems, PATTERN_CLASS_PII, "email_address")


def test_both_pattern_classes_in_one_statement_are_both_reported():
    text = LOGGER_PREAMBLE + (f'logger.info(f"provisioned {FAKE_API_KEY} for {FAKE_EMAIL}")\n')
    problems = _problems(text)
    _assert_denied(problems, PATTERN_CLASS_SECRET, "sk_prefixed_api_key")
    _assert_denied(problems, PATTERN_CLASS_PII, "email_address")
    assert len(problems) == 2, problems
    # Both findings cite the same exact file/line (the log statement's line 3).
    for problem in problems:
        assert problem.startswith("fixture.py:3:"), problem
        assert "logger.info() at line 3" in problem, problem


def test_pre_redacted_placeholder_passes():
    text = LOGGER_PREAMBLE + ('logger.info("provisioned key [REDACTED] for user <redacted>")\n')
    _assert_allowed(_problems(text))
    assert _inspected(text) == 1


def test_redaction_wrapper_call_passes():
    text = LOGGER_PREAMBLE + (
        'def handler(user, redact):\n    logger.info("contact %s", redact(user.email))\n'
    )
    _assert_allowed(_problems(text))


def test_redaction_marked_identifier_passes():
    text = LOGGER_PREAMBLE + (
        "def handler(email_hash, masked_phone, token_fingerprint):\n"
        '    logger.info(f"{email_hash} {masked_phone} {token_fingerprint}")\n'
    )
    _assert_allowed(_problems(text))


def test_lazy_percent_formatting_identifier_is_denied():
    text = LOGGER_PREAMBLE + (
        'def handler(user):\n    logger.warning("login failed for %s", user.email)\n'
    )
    _assert_denied(_problems(text), PATTERN_CLASS_PII, "email_identifier")


def test_camel_case_credential_identifier_is_denied():
    text = LOGGER_PREAMBLE + ('def handler(apiKey):\n    logger.error(f"auth failed: {apiKey}")\n')
    _assert_denied(_problems(text), PATTERN_CLASS_SECRET, "key_identifier")


def test_keyword_argument_is_inspected():
    text = LOGGER_PREAMBLE + (
        'def handler(user):\n    logger.info("member.verified", extra={"actor": user.ssn})\n'
    )
    _assert_denied(_problems(text), PATTERN_CLASS_PII, "government_id_identifier")


def test_non_log_call_is_not_inspected():
    """The distinction from SCN-029 secret-scanning, which this lint must not
    duplicate: identical shapes outside a log statement are not its business."""
    text = LOGGER_PREAMBLE + (
        f'API_KEY = "{FAKE_API_KEY}"\n'
        f'MEMBER_EMAIL = "{FAKE_EMAIL}"\n'
        'print(f"{API_KEY} {MEMBER_EMAIL}")\n'
        "def handler(session):\n"
        '    session.post("https://example.test", data={"password": API_KEY})\n'
        '    logger.info("provisioning complete")\n'
    )
    _assert_allowed(_problems(text))
    assert _inspected(text) == 1


def test_docstring_secret_is_not_inspected():
    text = (
        f'"""Module docstring mentioning {FAKE_API_KEY} and {FAKE_EMAIL}."""\n'
        + LOGGER_PREAMBLE
        + 'logger.info("started")\n'
    )
    _assert_allowed(_problems(text))


def test_getlogger_receiver_chain_is_recognized():
    text = (
        "import logging\n"
        "def handler(password):\n"
        '    logging.getLogger(__name__).info(f"pw={password}")\n'
    )
    _assert_denied(_problems(text), PATTERN_CLASS_SECRET, "password_identifier")


def test_self_log_attribute_receiver_is_recognized():
    text = (
        "class Handler:\n"
        "    def run(self):\n"
        '        self.log.error("login failed for %s", self.user_email)\n'
    )
    _assert_denied(_problems(text), PATTERN_CLASS_PII, "email_identifier")


def test_file_and_line_are_reported():
    text = (
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        "\n"
        "\n"
        "def handler(user):\n"
        '    logger.info("contact %s", user.email)\n'
    )
    problems = _problems(text, name="backend/app/handler.py")
    assert len(problems) == 1, problems
    assert problems[0].startswith("backend/app/handler.py:6:"), problems[0]


def test_diagnostic_does_not_echo_the_matched_secret():
    text = LOGGER_PREAMBLE + (f'logger.info(f"provisioned {FAKE_API_KEY} for {FAKE_EMAIL}")\n')
    problems = _problems(text)
    assert problems, problems
    joined = "\n".join(problems)
    assert FAKE_API_KEY not in joined, joined
    assert FAKE_EMAIL not in joined, joined
    assert "(len=" in joined, joined


def test_explicitly_fake_placeholder_and_opaque_token_boundary():
    """The generic opaque-token rule keys on an *unbroken* run of 20+
    alphanumerics mixing letters and digits, which is precisely why the
    underscore-separated `EXAMPLE_NOT_A_REAL_KEY` convention passes."""
    placeholder = LOGGER_PREAMBLE + 'logger.info("key=EXAMPLE_NOT_A_REAL_KEY")\n'
    _assert_allowed(_problems(placeholder))

    opaque = LOGGER_PREAMBLE + 'logger.info("key=NOTAREALCREDENTIAL0000")\n'
    _assert_denied(_problems(opaque), PATTERN_CLASS_SECRET, "opaque_credential_token")


def test_unparseable_source_fails_closed():
    problems = _problems("def broken(:\n    pass\n")
    assert len(problems) == 1, problems
    assert "UNPARSEABLE_SOURCE_FILE" in problems[0], problems[0]


def test_unreadable_file_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        problems, inspected = validate_file(Path(tmp) / "does_not_exist.py")
    assert len(problems) == 1, problems
    assert "UNREADABLE_SOURCE_FILE" in problems[0], problems[0]
    assert inspected == 0


def test_missing_named_target_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        outcome = run_validation([Path(tmp) / "no_such_dir"])
    assert any("MISSING_SOURCE_PATH" in p for p in outcome.problems), outcome.problems


def test_empty_file_set_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        outcome = run_validation([Path(tmp)])
    assert any("NO_SOURCE_FILES" in p for p in outcome.problems), outcome.problems


def test_require_log_statements_flag_converts_vacuous_pass_to_denial():
    with tempfile.TemporaryDirectory() as tmp:
        clean = Path(tmp) / "clean.py"
        clean.write_text("VALUE = 1\n", encoding="utf-8")

        permissive = run_validation([Path(tmp)])
        assert permissive.problems == [], permissive.problems
        assert permissive.notice is not None
        assert permissive.log_statements_inspected == 0

        strict = run_validation([Path(tmp)], require_log_statements=True)
        assert any("NO_LOG_STATEMENTS_INSPECTED" in p for p in strict.problems), strict.problems


def test_current_repo_source_tree_passes():
    outcome = run_validation(list(DEFAULT_SOURCE_ROOTS))
    assert outcome.problems == [], outcome.problems
    assert outcome.files_checked > 0


def test_cli_exit_code_matches_verdict():
    with tempfile.TemporaryDirectory() as tmp:
        offending = Path(tmp) / "offending.py"
        offending.write_text(
            LOGGER_PREAMBLE + f'logger.info(f"provisioned {FAKE_API_KEY} for {FAKE_EMAIL}")\n',
            encoding="utf-8",
        )
        clean = Path(tmp) / "clean.py"
        clean.write_text(
            LOGGER_PREAMBLE + 'logger.info("provisioned key [REDACTED]")\n',
            encoding="utf-8",
        )

        denied = subprocess.run(
            [sys.executable, str(VALIDATOR_SCRIPT), str(offending)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert denied.returncode == 1, denied.stdout + denied.stderr
        assert "SENSITIVE_DATA_IN_LOG_STATEMENT" in denied.stdout
        assert f"pattern_class={PATTERN_CLASS_SECRET}" in denied.stdout
        assert f"pattern_class={PATTERN_CLASS_PII}" in denied.stdout
        assert FAKE_API_KEY not in denied.stdout

        allowed = subprocess.run(
            [sys.executable, str(VALIDATOR_SCRIPT), str(clean), "--require-log-statements"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert allowed.returncode == 0, allowed.stdout + allowed.stderr
        assert "PASS" in allowed.stdout

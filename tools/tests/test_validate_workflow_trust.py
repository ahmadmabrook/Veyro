"""
Unit tests for tools/validate_workflow_trust.py (MOD-001, GOV-01-R04 /
gate-3 P2-4 standing workflow-trust lint).

Each test targets one leg of the hazard predicate (deny a workflow that
simultaneously has a `pull_request_target` trigger, a non-`GITHUB_TOKEN`
`secrets.` reference, and a checkout/execution of
`github.event.pull_request.head.*` or an equivalent fork-head reference),
plus the evasive-formatting and fail-closed cases the finding's own
wording calls for:

  1. test_full_hazardous_conjunction_is_denied - all three legs present,
     literal form -> DENY, naming trigger/secrets/forkhead_refs.
  2. test_missing_trigger_leg_is_allowed - `pull_request` (not `_target`)
     with the other two legs present -> ALLOW.
  3. test_missing_secret_leg_is_allowed - pull_request_target + fork-head
     reference, zero secrets. references at all -> ALLOW.
  4. test_github_token_only_is_allowed - pull_request_target + fork-head
     reference + `secrets.GITHUB_TOKEN` only (the one carve-out) ->
     ALLOW.
  5. test_missing_forkhead_leg_is_allowed - pull_request_target +
     secrets.DEPLOY_KEY, base-branch-only checkout -> ALLOW.
  6. test_bracket_notation_secret_is_denied - `secrets['DEPLOY_KEY']`
     instead of dot access -> DENY (evasive formatting).
  7. test_flow_array_trigger_is_denied - `on: [push, pull_request_target]`
     -> DENY (evasive formatting, trigger as a flow sequence).
  8. test_quoted_scalar_trigger_is_denied - `on: "pull_request_target"`
     -> DENY (evasive formatting, quoted bare scalar).
  9. test_folded_block_scalar_trigger_is_denied - `on: >` folding the
     trigger name onto a following line -> DENY (evasive formatting,
     multi-line trigger).
  10. test_split_across_lines_via_env_indirection_is_denied - the secret
      and the fork-head expression are each captured into an `env:` var
      and only *used* indirectly in a later `run:` step -> DENY (the
      literal `${{ ... }}` expression text is still present once, in the
      `env:` block, which this lint's whole-file scan still finds).
  11. test_comment_only_mentions_do_not_trigger_false_positive - the
      hazard strings appear only inside a YAML comment, with a safe
      trigger and no real secrets/fork-head usage -> ALLOW (proves
      comment-stripping, not just regex presence, drives the verdict).
  12. test_hash_inside_quoted_string_is_not_treated_as_comment - a `#`
      glued inside a double-quoted shell string is not stripped, so a
      hazard expression placed after it in the same quoted string is
      still seen -> DENY.
  13. test_nested_flow_mapping_trigger_is_uninspectable - `on:
      {pull_request_target: {types: [x]}}` (nested flow collection) ->
      UNINSPECTABLE_TRIGGER_DECLARATION, fail-closed rather than guessed.
  14. test_unreadable_file_fails_closed - a path that does not exist ->
      UNREADABLE_WORKFLOW_FILE, not a silent empty-problems pass.
  15. test_clean_trusted_workflow_fixture_is_allowed - the real,
      currently-trusted
      `.github/workflows/scn020-trusted-event-contract.yml` (which does
      reference `github.event.pull_request.head.sha`, but carries zero
      `secrets.` references) -> ALLOW. The decisive regression: proves
      this lint does not flag the one workflow P2-4's own review already
      verified safe.
  16. test_cli_exit_code_matches_verdict - `main()` driven as a real
      subprocess: exit 1 on a hazardous fixture, exit 0 on a clean one.
  17. test_nonliteral_bracket_secret_index_is_denied - gate-3 R1 P2-4
      bracket-expression false-green #1
      (GATE3-R1-P2-4-BRACKET-EXPRESSION-ROOT-CAUSE-2026-10-09.md):
      `secrets[format('DEPLOY_KEY')]` alongside
      `github.event.pull_request.head.sha` -> DENY, failing closed on the
      dynamic/nonliteral secrets index rather than silently ALLOW-ing.
  18. test_bracket_forkhead_reference_is_denied - the same root-cause
      doc's false-green #2: `github.event.pull_request['head'].sha`
      alongside `secrets.DEPLOY_KEY` -> DENY, recognizing bracket-indexed
      access into the PR-head context.
  19. test_fully_indexed_forkhead_reference_is_denied - gate-3 R1 P2-4
      full-index false-green
      (GATE3-R1-P2-4-FULL-INDEX-RESIDUAL-2026-10-09.md):
      `${{ github['event']['pull_request']['head']['sha'] }}` alongside
      `${{ secrets.DEPLOY_KEY }}` -> DENY. Every segment (including
      `github` itself accessed via `['event']`) is literal-bracket form,
      which the narrow dot-anchored regex previously missed entirely.
  20. test_mixed_dot_and_index_forkhead_reference_is_denied - a form
      mixing dot and bracket access across segments
      (`github.event['pull_request'].head.sha`) -> DENY, proving the fix
      is a per-segment normalization and not a special case of only the
      fully-dot or fully-bracket shapes.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validate_workflow_trust import evaluate_workflow_text, validate_file

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TRUSTED_FIXTURE = REPO_ROOT / '.github' / 'workflows' / 'scn020-trusted-event-contract.yml'
VALIDATOR_SCRIPT = REPO_ROOT / 'tools' / 'validate_workflow_trust.py'


def _assert_denied(problems: list[str], code: str) -> None:
    assert len(problems) == 1, problems
    assert code in problems[0], problems


def _assert_allowed(problems: list[str]) -> None:
    assert problems == [], problems


def test_full_hazardous_conjunction_is_denied():
    text = """\
on:
  pull_request_target:
    branches: [main]
jobs:
  build:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@abc123
        with:
          ref: ${{ github.event.pull_request.head.sha }}
      - run: curl -H "Authorization: Bearer ${{ secrets.DEPLOY_KEY }}" https://example.test
"""
    problems = evaluate_workflow_text(text, name='fixture')
    _assert_denied(problems, 'PULL_REQUEST_TARGET_SECRET_FORKHEAD_HAZARD')
    assert 'DEPLOY_KEY' in problems[0]
    assert 'github.event.pull_request.head.*' in problems[0]


def test_missing_trigger_leg_is_allowed():
    text = """\
on:
  pull_request:
    branches: [main]
jobs:
  build:
    steps:
      - run: echo ${{ github.event.pull_request.head.sha }}
      - run: echo ${{ secrets.DEPLOY_KEY }}
"""
    _assert_allowed(evaluate_workflow_text(text))


def test_missing_secret_leg_is_allowed():
    text = """\
on:
  pull_request_target:
    branches: [main]
jobs:
  build:
    steps:
      - run: echo ${{ github.event.pull_request.head.sha }}
"""
    _assert_allowed(evaluate_workflow_text(text))


def test_github_token_only_is_allowed():
    text = """\
on:
  pull_request_target:
    branches: [main]
jobs:
  build:
    steps:
      - run: echo ${{ github.event.pull_request.head.sha }}
      - run: echo ${{ secrets.GITHUB_TOKEN }}
"""
    _assert_allowed(evaluate_workflow_text(text))


def test_missing_forkhead_leg_is_allowed():
    text = """\
on:
  pull_request_target:
    branches: [main]
jobs:
  build:
    steps:
      - run: echo ${{ secrets.DEPLOY_KEY }}
      - run: echo ${{ github.event.pull_request.base.sha }}
"""
    _assert_allowed(evaluate_workflow_text(text))


def test_bracket_notation_secret_is_denied():
    text = """\
on:
  pull_request_target:
    branches: [main]
jobs:
  build:
    steps:
      - run: echo ${{ github.event.pull_request.head.sha }}
      - run: echo ${{ secrets['DEPLOY_KEY'] }}
"""
    problems = evaluate_workflow_text(text)
    _assert_denied(problems, 'PULL_REQUEST_TARGET_SECRET_FORKHEAD_HAZARD')
    assert 'DEPLOY_KEY' in problems[0]


def test_flow_array_trigger_is_denied():
    text = """\
on: [push, pull_request_target]
jobs:
  build:
    steps:
      - run: echo ${{ github.event.pull_request.head.sha }}
      - run: echo ${{ secrets.DEPLOY_KEY }}
"""
    problems = evaluate_workflow_text(text)
    _assert_denied(problems, 'PULL_REQUEST_TARGET_SECRET_FORKHEAD_HAZARD')


def test_quoted_scalar_trigger_is_denied():
    text = """\
on: "pull_request_target"
jobs:
  build:
    steps:
      - run: echo ${{ github.event.pull_request.head.sha }}
      - run: echo ${{ secrets.DEPLOY_KEY }}
"""
    problems = evaluate_workflow_text(text)
    _assert_denied(problems, 'PULL_REQUEST_TARGET_SECRET_FORKHEAD_HAZARD')


def test_quoted_on_key_is_denied():
    text = """\
"on":
  pull_request_target:
    branches: [main]
jobs:
  build:
    steps:
      - run: echo ${{ github.event.pull_request.head.sha }}
      - run: echo ${{ secrets.DEPLOY_KEY }}
"""
    _assert_denied(evaluate_workflow_text(text), 'PULL_REQUEST_TARGET_SECRET_FORKHEAD_HAZARD')


def test_folded_block_scalar_trigger_is_denied():
    text = """\
on: >
  pull_request_target
jobs:
  build:
    steps:
      - run: echo ${{ github.event.pull_request.head.sha }}
      - run: echo ${{ secrets.DEPLOY_KEY }}
"""
    problems = evaluate_workflow_text(text)
    _assert_denied(problems, 'PULL_REQUEST_TARGET_SECRET_FORKHEAD_HAZARD')


def test_split_across_lines_via_env_indirection_is_denied():
    text = """\
on:
  pull_request_target:
    branches: [main]
jobs:
  build:
    env:
      H: ${{ github.event.pull_request.head.sha }}
      S: ${{ secrets.DEPLOY_KEY }}
    steps:
      - run: git checkout "$H"
      - run: curl -H "Authorization: Bearer $S" https://example.test
"""
    problems = evaluate_workflow_text(text)
    _assert_denied(problems, 'PULL_REQUEST_TARGET_SECRET_FORKHEAD_HAZARD')


def test_comment_only_mentions_do_not_trigger_false_positive():
    text = """\
on:
  pull_request_target:
    branches: [main]
# This workflow does NOT use secrets.DEPLOY_KEY or
# github.event.pull_request.head.sha - this comment exists only to prove
# the lint does not pattern-match inside comments.
jobs:
  build:
    steps:
      - run: echo "hello"  # secrets.ALSO_NOT_REAL github.event.pull_request.head.ref
"""
    _assert_allowed(evaluate_workflow_text(text))


def test_hash_inside_quoted_string_is_not_treated_as_comment():
    text = """\
on:
  pull_request_target:
    branches: [main]
jobs:
  build:
    steps:
      - run: echo "value # ${{ github.event.pull_request.head.sha }}"
      - run: echo "value # ${{ secrets.DEPLOY_KEY }}"
"""
    problems = evaluate_workflow_text(text)
    _assert_denied(problems, 'PULL_REQUEST_TARGET_SECRET_FORKHEAD_HAZARD')


def test_nested_flow_mapping_trigger_is_uninspectable():
    text = """\
on: {pull_request_target: {types: [opened]}}
jobs:
  build:
    steps:
      - run: echo hi
"""
    problems = evaluate_workflow_text(text)
    _assert_denied(problems, 'UNINSPECTABLE_TRIGGER_DECLARATION')


def test_unreadable_file_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / 'does-not-exist.yml'
        problems = validate_file(missing)
        _assert_denied(problems, 'UNREADABLE_WORKFLOW_FILE')


def test_clean_trusted_workflow_fixture_is_allowed():
    assert TRUSTED_FIXTURE.is_file(), f"fixture missing: {TRUSTED_FIXTURE}"
    text = TRUSTED_FIXTURE.read_text(encoding='utf-8')
    # The decisive regression: the real trusted workflow DOES reference
    # the fork head (to screen candidate objects as inert data), but it
    # must carry zero secrets. references for this to stay an ALLOW.
    assert 'github.event.pull_request.head' in text
    assert 'secrets.' not in text
    _assert_allowed(evaluate_workflow_text(text, name=str(TRUSTED_FIXTURE)))


def test_nonliteral_bracket_secret_index_is_denied():
    text = """\
on:
  pull_request_target:
    branches: [main]
jobs:
  build:
    steps:
      - run: echo ${{ github.event.pull_request.head.sha }}
      - run: echo ${{ secrets[format('DEPLOY_KEY')] }}
"""
    problems = evaluate_workflow_text(text)
    _assert_denied(problems, 'PULL_REQUEST_TARGET_SECRET_FORKHEAD_HAZARD')
    assert 'nonliteral-secrets-index' in problems[0]


def test_bracket_forkhead_reference_is_denied():
    text = """\
on:
  pull_request_target:
    branches: [main]
jobs:
  build:
    steps:
      - run: echo ${{ github.event.pull_request['head'].sha }}
      - run: echo ${{ secrets.DEPLOY_KEY }}
"""
    problems = evaluate_workflow_text(text)
    _assert_denied(problems, 'PULL_REQUEST_TARGET_SECRET_FORKHEAD_HAZARD')
    assert 'DEPLOY_KEY' in problems[0]


def test_fully_indexed_forkhead_reference_is_denied():
    text = """\
on:
  pull_request_target:
    branches: [main]
jobs:
  build:
    steps:
      - run: echo ${{ github['event']['pull_request']['head']['sha'] }}
      - run: echo ${{ secrets.DEPLOY_KEY }}
"""
    problems = evaluate_workflow_text(text)
    _assert_denied(problems, 'PULL_REQUEST_TARGET_SECRET_FORKHEAD_HAZARD')
    assert 'DEPLOY_KEY' in problems[0]


def test_mixed_dot_and_index_forkhead_reference_is_denied():
    text = """\
on:
  pull_request_target:
    branches: [main]
jobs:
  build:
    steps:
      - run: echo ${{ github.event['pull_request'].head.sha }}
      - run: echo ${{ secrets.DEPLOY_KEY }}
"""
    problems = evaluate_workflow_text(text)
    _assert_denied(problems, 'PULL_REQUEST_TARGET_SECRET_FORKHEAD_HAZARD')
    assert 'DEPLOY_KEY' in problems[0]


def test_cli_exit_code_matches_verdict():
    with tempfile.TemporaryDirectory() as tmp:
        hazardous = Path(tmp) / 'hazardous.yml'
        hazardous.write_text(
            "on:\n"
            "  pull_request_target:\n"
            "    branches: [main]\n"
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - run: echo ${{ github.event.pull_request.head.sha }}\n"
            "      - run: echo ${{ secrets.DEPLOY_KEY }}\n",
            encoding='utf-8',
        )
        clean = Path(tmp) / 'clean.yml'
        clean.write_text(
            "on:\n  pull_request:\n    branches: [main]\n"
            "jobs:\n  build:\n    steps:\n      - run: echo hi\n",
            encoding='utf-8',
        )

        denied = subprocess.run(
            [sys.executable, str(VALIDATOR_SCRIPT), str(hazardous)],
            capture_output=True, text=True, check=False,
        )
        assert denied.returncode == 1, denied.stdout + denied.stderr
        assert 'PULL_REQUEST_TARGET_SECRET_FORKHEAD_HAZARD' in denied.stdout

        allowed = subprocess.run(
            [sys.executable, str(VALIDATOR_SCRIPT), str(clean)],
            capture_output=True, text=True, check=False,
        )
        assert allowed.returncode == 0, allowed.stdout + allowed.stderr
        assert 'PASS' in allowed.stdout

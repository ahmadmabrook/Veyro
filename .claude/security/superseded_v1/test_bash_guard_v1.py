#!/usr/bin/env python3
"""Test suite for .claude/security/bash_guard.py.

Runs the guard as a real subprocess fed the exact PreToolUse JSON
payload shape (verified in
knowledge/03-Modules/MOD-000/evidence/security/HOOK_CONTRACT_VERIFICATION_2026-09-06.md),
so this test exercises the actual hook entry point, not just internal
functions. Every fixture is asserted individually — none are skipped.

Run directly: `python3 .claude/security/tests/test_bash_guard.py`
"""
import json
import pathlib
import subprocess
import sys
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


class DenyFixtures(unittest.TestCase):
    """Every command here MUST be denied. Each is its own test method
    so a failure names the exact bypassed fixture."""

    # -- BUG-013: recursive delete bypasses -----------------------------
    def test_rm_bare_r(self):
        self.assert_denied("rm -r /tmp/scratch/dir")

    def test_rm_bare_R(self):
        self.assert_denied("rm -R /tmp/scratch/dir")

    def test_rm_rf(self):
        self.assert_denied("rm -rf /tmp/scratch/dir")

    def test_rm_fr(self):
        self.assert_denied("rm -fr /tmp/scratch/dir")

    def test_rm_r_f_separate(self):
        self.assert_denied("rm -r -f /tmp/scratch/dir")

    def test_rm_f_r_separate(self):
        self.assert_denied("rm -f -r /tmp/scratch/dir")

    def test_rm_rv(self):
        self.assert_denied("rm -rv /tmp/scratch/dir")

    def test_rm_vr(self):
        self.assert_denied("rm -vr /tmp/scratch/dir")

    def test_rm_Rv(self):
        self.assert_denied("rm -Rv /tmp/scratch/dir")

    def test_rm_v_r_separate(self):
        self.assert_denied("rm -v -r /tmp/scratch/dir")

    def test_rm_long_recursive(self):
        self.assert_denied("rm --recursive /tmp/scratch/dir")

    def test_rm_long_recursive_force(self):
        self.assert_denied("rm --recursive --force /tmp/scratch/dir")

    def test_rm_flag_after_path(self):
        self.assert_denied("rm /tmp/scratch/dir -r")

    def test_find_delete(self):
        self.assert_denied("find /tmp/scratch -name '*.tmp' -delete")

    def test_find_exec_rm(self):
        self.assert_denied("find /tmp/scratch -type f -exec rm {} \\;")

    def test_find_exec_rm_plus_form(self):
        self.assert_denied("find /tmp/scratch -type f -exec rm {} +")

    def test_rm_recursive_via_semicolon_chain(self):
        self.assert_denied("echo hi; rm -rf /tmp/scratch/dir")

    def test_rm_recursive_via_and_chain(self):
        self.assert_denied("cd /tmp/scratch && rm -rf dir")

    def test_rm_recursive_inside_command_substitution_dollar(self):
        self.assert_denied("echo $(rm -rf /tmp/scratch/dir)")

    def test_rm_recursive_inside_backticks(self):
        self.assert_denied("echo `rm -rf /tmp/scratch/dir`")

    # -- RR-1 fixes: reserved words / grouping punctuation (P0-2) --------
    def test_rm_recursive_inside_paren_group(self):
        self.assert_denied("(rm -rf /tmp/scratch/dir)")

    def test_rm_recursive_inside_brace_group(self):
        self.assert_denied("{ rm -rf /tmp/scratch/dir; }")

    def test_rm_recursive_inside_if_block(self):
        self.assert_denied("if true; then rm -rf /tmp/scratch/dir; fi")

    def test_rm_recursive_inside_for_loop(self):
        self.assert_denied("for d in /tmp/scratch/dir; do rm -rf $d; done")

    def test_bare_reserved_word_history_negation(self):
        self.assert_denied("! rm -rf /tmp/scratch/dir")

    # -- RR-1 fixes: multi-line / continuation (P0-1, P0-4) ---------------
    def test_newline_separated_rm_after_benign_line(self):
        self.assert_denied("echo hi\nrm -rf /tmp/scratch/dir")

    def test_newline_separated_git_reset_after_benign_line(self):
        self.assert_denied("git status\nrm -rf .claude/rules")

    def test_backslash_continuation_rm(self):
        self.assert_denied("rm \\\n -rf /tmp/scratch/dir")

    def test_backslash_continuation_git_reset(self):
        self.assert_denied("git \\\n reset --hard")

    # -- RR-1 fixes: interpreter/wrapper delegation (P0-3) -----------------
    def test_bash_c_wrapper(self):
        self.assert_denied("bash -c 'rm -rf /tmp/scratch/dir'")

    def test_sh_c_wrapper(self):
        self.assert_denied("sh -c 'echo x > .claude/settings.json'")

    def test_eval_wrapper(self):
        self.assert_denied("eval 'git reset --hard'")

    def test_xargs_wrapper(self):
        self.assert_denied("echo /tmp/scratch/dir | xargs rm -rf")

    def test_sudo_wrapper(self):
        self.assert_denied("sudo rm -rf /tmp/scratch/dir")

    def test_timeout_wrapper(self):
        self.assert_denied("timeout 60 rm -rf /tmp/scratch/dir")

    def test_env_dash_S_wrapper(self):
        self.assert_denied("env -S 'rm -rf /tmp/scratch/dir'")

    def test_source_wrapper(self):
        self.assert_denied("source /tmp/scratch/script.sh")

    def test_dot_source_wrapper(self):
        self.assert_denied(". /tmp/scratch/script.sh")

    # -- RR-1 fixes: cd-then-relative-path (P0-5) ---------------------------
    def test_cd_then_redirect_settings_json(self):
        self.assert_denied("cd .claude && echo TAMPERED > settings.json")

    def test_cd_then_rm_relative_protected(self):
        self.assert_denied("cd .claude/rules && rm -f owner-reserved-restrictions.md")

    def test_cd_then_sed_relative_protected(self):
        self.assert_denied("cd .claude/rules && sed -i '' -e 's/a/b/' owner-reserved-restrictions.md")

    # -- RR-1 fixes: broader redirection operators (P1-1) -------------------
    def test_redirect_clobber_settings_json(self):
        self.assert_denied("echo x >| .claude/settings.json")

    def test_redirect_and_settings_json(self):
        self.assert_denied("echo x &> .claude/settings.json")

    # -- RR-1 fixes: perl in-place edit (P1-2) -------------------------------
    def test_perl_pi_settings_json(self):
        self.assert_denied("perl -pi -e 's/deny/allow/' .claude/settings.json")

    def test_perl_i_settings_json(self):
        self.assert_denied("perl -i.bak -e 's/deny/allow/' .claude/settings.json")

    # -- RR-1 fixes: glob/brace path evasion (P1-3) --------------------------
    def test_glob_evasion_rules_dir(self):
        self.assert_denied("rm -rf .claude/rul*")

    def test_brace_evasion_settings_json(self):
        self.assert_denied("rm -f .claude/{settings.json,foo.txt}")

    # -- RR-1 fixes: git gaps (P1-4) ------------------------------------------
    def test_git_alias_shell_escape(self):
        self.assert_denied("git -c alias.zap=!rm\\ -rf\\ /tmp/scratch/dir zap")

    def test_git_push_delete_branch(self):
        self.assert_denied("git push origin --delete main")

    def test_git_push_colon_refspec_delete(self):
        self.assert_denied("git push origin :main")

    def test_git_rm_recursive_cached(self):
        self.assert_denied("git rm -r --cached .")

    def test_git_branch_bundled_D_flag(self):
        self.assert_denied("git branch -Dq somebranch")

    # -- RR-1 fixes: heredoc no longer false-positives on apostrophes -------
    # (see SafeFixtures.test_heredoc_with_apostrophe_is_allowed for the
    # matching must-not-deny assertion; this one is a should-be-denied
    # heredoc whose *command line* targets a protected path)
    def test_heredoc_command_line_protected_path(self):
        self.assert_denied("cat <<'EOF' > .claude/settings.json\nharmless prose\nEOF")

    # -- RR-2 fixes: wrapper denylist gaps (P0-1) ----------------------------
    def test_nice_wrapper(self):
        self.assert_denied("nice rm -rf /tmp/scratch/dir")

    def test_setsid_wrapper(self):
        self.assert_denied("setsid git reset --hard")

    def test_su_wrapper(self):
        self.assert_denied("su -c 'rm -rf /tmp/scratch/dir'")

    def test_awk_system_wrapper(self):
        self.assert_denied('awk \'BEGIN{system("rm -rf /tmp/scratch/dir")}\'')

    def test_ssh_wrapper(self):
        self.assert_denied("ssh localhost 'rm -rf /tmp/scratch/dir'")

    def test_pushd_wrapper(self):
        self.assert_denied("pushd .claude")

    # -- RR-2 fixes: $VAR command name now fails closed (P0-2) --------------
    def test_dollar_shell_variable_command(self):
        self.assert_denied("$SHELL -c 'rm -rf /tmp/scratch/dir'")

    def test_braced_dollar_shell_variable_command(self):
        self.assert_denied("${SHELL} -c 'rm -rf /tmp/scratch/dir'")

    # -- RR-2 fixes: find -exec now fully recurses (P0-3) --------------------
    def test_find_exec_sh_c(self):
        self.assert_denied("find . -type f -exec sh -c 'rm -rf /tmp/scratch/dir' \\;")

    def test_find_exec_bash_c_redirect(self):
        self.assert_denied("find . -type f -exec bash -c 'echo x > .claude/settings.json' \\;")

    def test_find_exec_mv(self):
        self.assert_denied("find /tmp/scratch -type f -exec mv {} /tmp/gone \\;")

    # -- RR-2 fixes: case-insensitive protected paths (P0-4) -----------------
    def test_case_insensitive_settings_json(self):
        self.assert_denied("rm -f .Claude/settings.json")

    def test_case_insensitive_rules_dir(self):
        self.assert_denied("rm -f .CLAUDE/rules/owner-reserved-restrictions.md")

    # -- RR-2 fixes: cd flag handling (P0-5) ----------------------------------
    def test_cd_dash_P_flag_then_redirect(self):
        self.assert_denied("cd -P .claude && echo TAMPERED > settings.json")

    def test_cd_dash_dash_then_redirect(self):
        self.assert_denied("cd -- .claude && echo TAMPERED > settings.json")

    # -- RR-2 fixes: interpreter stdin/heredoc feeding (P1-1) -----------------
    def test_python_heredoc_stdin_code(self):
        self.assert_denied("python3 <<'EOF'\nimport os\nos.remove('.claude/settings.json')\nEOF")

    def test_python_herestring_stdin_code(self):
        self.assert_denied('python3 <<< "import os; os.remove(\'.claude/settings.json\')"')

    def test_python_bare_no_args_stdin(self):
        self.assert_denied("python3")

    # -- RR-2 fixes: expanded write-primitive set (P1-2) ----------------------
    def test_ln_onto_settings_json(self):
        self.assert_denied("ln -sf /dev/null .claude/settings.json")

    def test_rsync_onto_settings_json(self):
        self.assert_denied("rsync /tmp/fake.json .claude/settings.json")

    def test_shred_settings_json(self):
        self.assert_denied("shred .claude/settings.json")

    # -- RR-2 fixes: git checkout/restore path-arg protection (P1-3) --------
    def test_git_checkout_head_dash_dash_protected_path(self):
        self.assert_denied("git checkout HEAD -- .claude/settings.json")

    def test_git_restore_source_protected_path(self):
        self.assert_denied("git restore --source=HEAD .claude/settings.json")

    # -- RR-2 fixes: guard protects its own files (P1-5) ----------------------
    def test_rm_bash_guard_itself(self):
        self.assert_denied("rm -f .claude/security/bash_guard.py")

    def test_redirect_onto_bash_guard(self):
        self.assert_denied("echo '' > .claude/security/bash_guard.py")

    # -- RR-2 fixes: persistent git alias shell escape (P1-6) -----------------
    def test_git_config_alias_shell_escape(self):
        self.assert_denied("git config alias.zap '!rm -rf /tmp/scratch/dir'")

    # -- RR-3 fixes: leading redirection hides the command name (P0-1) ------
    def test_leading_redirect_rm(self):
        self.assert_denied(">/dev/null rm -rf /tmp/scratch/dir")

    def test_leading_fd_redirect_rm(self):
        self.assert_denied("2>/dev/null rm -rf /tmp/scratch/dir")

    def test_leading_redirect_with_space_rm(self):
        self.assert_denied("> /tmp/out rm -rf /tmp/scratch/dir")

    def test_leading_redirect_git_reset(self):
        self.assert_denied(">/dev/null git reset --hard")

    def test_leading_assignment_and_redirect_rm(self):
        self.assert_denied("FOO=bar >/dev/null rm -rf /tmp/scratch/dir")

    # -- RR-3 fixes: redirect run swallowing the trailing chain op (P0-2) ---
    def test_redirect_then_pipe_to_rm(self):
        self.assert_denied("echo hi >&2|rm -rf /tmp/scratch/dir")

    def test_redirect_then_and_to_rm(self):
        self.assert_denied("echo hi >&2&&rm -rf /tmp/scratch/dir")

    def test_redirect_then_or_to_rm(self):
        self.assert_denied("echo hi >&2||rm -rf /tmp/scratch/dir")

    def test_redirect_then_pipe_to_tee_settings(self):
        self.assert_denied("echo hi >&2|tee .claude/settings.json")

    # -- RR-3 fixes: zsh precommand modifiers / dialect gaps (P0-4) ---------
    def test_noglob_wrapper(self):
        self.assert_denied("noglob rm -rf /tmp/scratch/dir")

    def test_nocorrect_wrapper(self):
        self.assert_denied("nocorrect rm -rf /tmp/scratch/dir")

    def test_repeat_wrapper(self):
        self.assert_denied("repeat 1 rm -rf /tmp/scratch/dir")

    def test_coproc_wrapper(self):
        self.assert_denied("coproc rm -rf /tmp/scratch/dir")

    # -- RR-3 fixes: parallel wrapper/reserved-word list drift on `time` (P1-4)
    def test_absolute_path_time_wrapper(self):
        self.assert_denied("/usr/bin/time rm -rf /tmp/scratch/dir")

    def test_command_wrapped_time(self):
        self.assert_denied("command time rm -rf /tmp/scratch/dir")

    def test_env_wrapped_time(self):
        self.assert_denied("env time rm -rf /tmp/scratch/dir")

    # -- RR-3 fixes: git config/-c shell-executing keys beyond alias (P1-1) -
    def test_git_c_diff_external(self):
        self.assert_denied("git -c diff.external=rm\\ -rf\\ /tmp/scratch/dir diff")

    def test_git_config_diff_external(self):
        self.assert_denied("git config diff.external 'rm -rf /tmp/scratch/dir'")

    def test_git_c_core_sshcommand(self):
        self.assert_denied("git -c core.sshCommand=rm\\ -rf\\ /tmp/scratch/dir fetch")

    # -- RR-3 fixes: git -C feeding checkout/restore path resolution (P1-3) -
    def test_git_dash_C_checkout_protected_path(self):
        self.assert_denied("git -C .claude checkout HEAD -- settings.json")

    def test_git_dash_C_restore_protected_path(self):
        self.assert_denied("git -C .claude restore settings.json")

    # -- RR-3 fixes: scp as a wrapper/write vector -----------------------
    def test_scp_onto_settings_json(self):
        self.assert_denied("scp /tmp/fake.json .claude/settings.json")

    def test_scp_proxycommand_wrapper(self):
        self.assert_denied("scp -o ProxyCommand=rm\\ -rf\\ /tmp/scratch/dir a b")

    # -- RR-4 fixes: case-insensitive command names (P0-N2) -----------------
    def test_uppercase_rm(self):
        self.assert_denied("RM -rf /tmp/scratch/dir")

    def test_mixed_case_rm(self):
        self.assert_denied("Rm -rf /tmp/scratch/dir")

    def test_uppercase_git_reset(self):
        self.assert_denied("GIT reset --hard")

    def test_uppercase_bash_wrapper(self):
        self.assert_denied("Bash -c 'rm -rf /tmp/scratch/dir'")

    # -- RR-4 fixes: `builtin` precommand modifier (P0-N3) -------------------
    def test_builtin_eval_wrapper(self):
        self.assert_denied("builtin eval 'rm -rf /tmp/scratch/dir'")

    def test_command_builtin_eval_wrapper(self):
        self.assert_denied("command builtin eval 'rm -rf /tmp/scratch/dir'")

    # -- BUG-022: absolute-path / wrapper bypasses -----------------------
    def test_absolute_path_rm_rf(self):
        self.assert_denied("/bin/rm -rf /tmp/scratch/dir")

    def test_absolute_path_git_reset_hard(self):
        self.assert_denied("/usr/bin/git reset --hard")

    def test_absolute_path_git_branch_D(self):
        self.assert_denied("/usr/bin/git branch -D somebranch")

    def test_env_wrapped_git_reset_hard(self):
        self.assert_denied("env git reset --hard")

    def test_command_wrapped_git_reset_hard(self):
        self.assert_denied("command git reset --hard")

    def test_env_wrapped_rm_rf(self):
        self.assert_denied("env rm -rf /tmp/scratch/dir")

    def test_command_wrapped_rm_rf(self):
        self.assert_denied("command rm -rf /tmp/scratch/dir")

    def test_git_c_global_flag_injection_reset(self):
        self.assert_denied("git -c core.pager=cat reset --hard")

    def test_git_C_global_flag_injection_reset(self):
        self.assert_denied("git -C /tmp/scratch/repo reset --hard")

    def test_git_no_pager_reset(self):
        self.assert_denied("git --no-pager reset --hard")

    def test_git_combined_global_opts_reset(self):
        self.assert_denied("git -c core.pager=cat -C /tmp/scratch/repo --no-pager reset --hard")

    def test_git_c_global_flag_injection_push_force(self):
        self.assert_denied("git -c core.pager=cat push origin main --force")

    def test_git_c_global_flag_injection_branch_D(self):
        self.assert_denied("git -c core.pager=cat branch -D somebranch")

    def test_absolute_path_git_with_c_injection(self):
        self.assert_denied("/usr/bin/git -c core.pager=cat reset --hard")

    def test_env_git_with_C_injection(self):
        self.assert_denied("env git -C /tmp/scratch/repo reset --hard")

    # -- BUG-023: redirection / alternate write primitives ---------------
    def test_redirect_overwrite_settings_json(self):
        self.assert_denied("echo TAMPERED > .claude/settings.json")

    def test_redirect_append_settings_json(self):
        self.assert_denied("echo TAMPERED >> .claude/settings.json")

    def test_redirect_overwrite_baseline_docx(self):
        self.assert_denied(
            "echo TAMPERED > Gym_OS_Master_Product_Blueprint_v1_English.docx"
        )

    def test_tee_settings_json(self):
        self.assert_denied("echo TAMPERED | tee .claude/settings.json")

    def test_cp_onto_baseline(self):
        self.assert_denied("cp /tmp/fake.docx Gym_OS_Master_Product_Blueprint_v1_English.docx")

    def test_cp_baseline_as_source(self):
        self.assert_denied(
            "cp Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx /tmp/exfil.docx"
        )

    def test_mv_onto_settings_json(self):
        self.assert_denied("mv /tmp/fake.json .claude/settings.json")

    def test_truncate_settings_json(self):
        self.assert_denied("truncate -s 0 .claude/settings.json")

    def test_dd_onto_settings_json(self):
        self.assert_denied("dd if=/dev/null of=.claude/settings.json")

    def test_sed_i_settings_json(self):
        self.assert_denied("sed -i '' -e 's/deny/allow/' .claude/settings.json")

    def test_python_write_settings_json(self):
        self.assert_denied(
            "python3 -c \"open('.claude/settings.json','w').write('x')\""
        )

    def test_python_write_baseline_docx(self):
        self.assert_denied(
            "python3 -c \"open('Gym_OS_Master_Product_Blueprint_v1_English.docx','w').write('x')\""
        )

    def test_python_c_benign_content_still_denied(self):
        # Confirms the interpreter-eval policy (RR-1 fix) is a blanket
        # deny on the -c flag itself, not a content heuristic — see
        # SafeFixtures.test_python_script_file_is_allowed for the
        # matching "script file is fine" counterpart.
        self.assert_denied("python3 -c \"print('hello')\"")

    def test_rm_baseline_docx_non_recursive(self):
        self.assert_denied("rm Gym_OS_Master_Product_Blueprint_v1_English.docx")

    def test_rm_rules_dir(self):
        self.assert_denied("rm -rf .claude/rules")

    def test_redirect_onto_agents_dir_file(self):
        self.assert_denied("echo x > .claude/agents/veyro-lead.md")

    def test_tee_onto_design_bundle(self):
        self.assert_denied("echo x | tee veyro-product-experience-design/foo.html")

    # -- Existing preserved restrictions ----------------------------------
    def test_production_keyword(self):
        self.assert_denied("echo deploying to production")

    def test_prod_flag(self):
        self.assert_denied("some-cli run --prod")

    def test_testsprite_test_run(self):
        self.assert_denied("testsprite test run")

    def test_testsprite_test_rerun(self):
        self.assert_denied("npx testsprite test rerun 123")

    def test_testsprite_testlist_run(self):
        self.assert_denied("testsprite testlist run")

    # -- Fail-closed on unparseable input ----------------------------------
    def test_unbalanced_quote_fails_closed(self):
        code, decision, reason = run_guard("echo 'unterminated")
        self.assertEqual(decision, "deny")
        self.assertIn("PARSE_FAILURE_FAIL_CLOSED", reason)

    def assert_denied(self, command):
        code, decision, reason = run_guard(command)
        self.assertEqual(
            decision, "deny", f"expected DENY for {command!r}, got decision={decision!r} reason={reason!r}"
        )
        self.assertTrue(reason and reason.startswith("BLOCKED:"), f"missing/bad reason for {command!r}: {reason!r}")


class SafeFixtures(unittest.TestCase):
    """Every command here MUST be allowed (no decision from the guard —
    it must print nothing and defer to the existing permission flow)."""

    def assert_allowed(self, command):
        code, decision, reason = run_guard(command)
        self.assertIsNone(
            decision, f"expected no decision (ALLOW/deferred) for {command!r}, got decision={decision!r} reason={reason!r}"
        )

    def test_git_status(self):
        self.assert_allowed("git status")

    def test_git_status_short(self):
        self.assert_allowed("git status --short")

    def test_git_log(self):
        self.assert_allowed("git log --oneline -5")

    def test_git_diff(self):
        self.assert_allowed("git diff --stat")

    def test_git_show(self):
        self.assert_allowed("git show HEAD")

    def test_git_add(self):
        self.assert_allowed("git add file.txt")

    def test_git_commit_no_amend(self):
        self.assert_allowed('git commit -m "a normal commit"')

    def test_git_push_no_force(self):
        self.assert_allowed("git push origin main")

    def test_git_branch_list(self):
        self.assert_allowed("git branch")

    def test_git_branch_create(self):
        self.assert_allowed("git branch new-feature")

    def test_git_checkout_branch(self):
        self.assert_allowed("git checkout -b new-feature")

    def test_git_worktree_add(self):
        self.assert_allowed("git worktree add /tmp/wt -b feature")

    def test_git_stash_list(self):
        self.assert_allowed("git stash list")

    def test_git_stash_pop(self):
        self.assert_allowed("git stash pop")

    def test_git_with_c_but_safe_subcommand(self):
        self.assert_allowed("git -c core.pager=cat log --oneline")

    def test_git_C_but_safe_subcommand(self):
        self.assert_allowed("git -C /some/repo status")

    def test_git_gc_no_prune(self):
        self.assert_allowed("git gc")

    def test_rm_single_file_no_flags(self):
        self.assert_allowed("rm /tmp/scratch/onefile.txt")

    def test_rm_multiple_files_no_flags(self):
        self.assert_allowed("rm /tmp/scratch/a.txt /tmp/scratch/b.txt")

    def test_find_plain_search(self):
        self.assert_allowed("find . -name '*.py'")

    def test_find_print(self):
        self.assert_allowed("find . -type f -print")

    def test_find_exec_grep_is_not_destructive(self):
        # Reviewer P2-2: -exec is only dangerous when the executed
        # command itself is destructive (rm/shred/truncate/dd/find).
        self.assert_allowed("find . -name '*.py' -exec grep -l foo {} +")

    def test_quoted_greater_than_not_a_redirect(self):
        # Reviewer P2-1: a quoted '>' must not be misread as redirection.
        self.assert_allowed("grep -n '>' .claude/settings.json")

    def test_cp_backup_of_settings_json_is_deliberately_denied(self):
        # Documented deliberate choice (reviewer P2-3): cp/mv/sed/tee
        # deny a protected path as EITHER source or destination, to
        # also close the exfiltration-copy vector BUG-022 proved live.
        # This is intentionally in DenyFixtures, not here — see
        # test_cp_baseline_as_source above. This stub documents the
        # decision at the point a reviewer would look for a safe-backup
        # counter-example.
        pass

    def test_heredoc_with_apostrophe_is_allowed(self):
        # Reviewer P1-5: heredoc bodies must not be tokenized as shell
        # code (prose apostrophes previously tripped PARSE_FAILURE).
        self.assert_allowed("cat <<'EOF' > /tmp/scratch/notes.md\nit's a note\nEOF")

    def test_multiline_safe_script(self):
        self.assert_allowed("echo line one\necho line two\ngit status")

    def test_find_with_braces_no_space(self):
        self.assert_allowed("find . -type f -name '*.txt' -print0")

    # -- RR-2 fixes: reserved words in quoted/argument position (P1-4) ------
    def test_grep_for_quoted_reserved_word(self):
        self.assert_allowed("grep -rn 'function' src/")

    def test_grep_for_if_quoted(self):
        self.assert_allowed("grep -n 'if' README.md")

    def test_echo_done_as_argument(self):
        self.assert_allowed("echo done")

    def test_commit_message_containing_reserved_word(self):
        self.assert_allowed('git commit -m "done"')

    def test_find_name_done(self):
        self.assert_allowed("find . -name done")

    # -- RR-2 fixes: find -exec with a non-destructive command still allowed
    def test_find_exec_grep_still_allowed_after_recursion_fix(self):
        self.assert_allowed("find . -name '*.py' -exec grep -l foo {} +")

    # -- RR-2 fixes: parameter expansion ${VAR} is not brace-grouping --------
    def test_param_expansion_home(self):
        self.assert_allowed("echo ${HOME}")

    def test_param_expansion_in_path(self):
        self.assert_allowed("ls ${HOME}/Desktop")

    # -- RR-2 fixes: cd with a real flag then a safe relative op ------------
    def test_cd_dash_P_then_safe_command(self):
        self.assert_allowed("cd -P /tmp/scratch && ls")

    def test_ls(self):
        self.assert_allowed("ls -la")

    def test_cat(self):
        self.assert_allowed("cat README.md")

    def test_echo_plain(self):
        self.assert_allowed("echo hello world")

    def test_redirect_to_scratch_file(self):
        self.assert_allowed("echo hello > /tmp/scratch/output.txt")

    def test_tee_to_scratch_file(self):
        self.assert_allowed("echo hello | tee /tmp/scratch/output.txt")

    def test_cp_unrelated_files(self):
        self.assert_allowed("cp /tmp/a.txt /tmp/b.txt")

    def test_mv_unrelated_files(self):
        self.assert_allowed("mv /tmp/a.txt /tmp/b.txt")

    def test_sed_unrelated_file(self):
        self.assert_allowed("sed -i '' -e 's/a/b/' /tmp/scratch/file.txt")

    def test_python_script_file_is_allowed(self):
        # Blanket interpreter policy (RR-1 fix for P0-3/P1-2) denies any
        # -c/-e/--eval inline code evaluation for python/node/ruby and
        # any -c/-e/-p*/-n*/-i* flag cluster for perl, unconditionally —
        # see the module's HONEST SCOPE LIMITS. Running a script FILE
        # (no eval flag) is not blocked; what that file does is outside
        # this guard's reach, by design.
        self.assert_allowed("python3 /tmp/scratch/some_script.py")

    def test_node_script_file_is_allowed(self):
        self.assert_allowed("node /tmp/scratch/some_script.js")

    def test_shasum(self):
        self.assert_allowed("shasum -a 256 somefile.txt")

    def test_pipeline_grep(self):
        self.assert_allowed("git log --oneline | grep fix")

    def test_var_assignment_prefix_safe(self):
        self.assert_allowed("FOO=bar git status")

    def test_env_wrapped_safe_command(self):
        self.assert_allowed("env git status")

    def test_command_wrapped_safe_command(self):
        self.assert_allowed("command git status")

    def test_quoted_string_with_apostrophe(self):
        self.assert_allowed('echo "it'"'"'s fine"')

    def test_testsprite_doctor(self):
        self.assert_allowed("testsprite doctor")

    def test_testsprite_lint(self):
        self.assert_allowed("testsprite test lint")


if __name__ == "__main__":
    unittest.main(verbosity=2)

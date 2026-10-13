# P2-4 bracket correction — transport pre-execution failure

Date: 2026-10-09. Runner operation `2fec064b-d19b-4333-b17a-5ee8cfda3185`.

The one guarded ACPX implementation dispatch for `GATE3-R1-P2-4-BRACKET-EXPRESSION-FAIL-CLOSED` exited 1 before Claude started: `acpx claude exec` rejected `--format` as an unknown option. Its own usage states `exec [-f|--file <path>] [prompt...]`. `ACTIVE_OPERATION.json` records `INTERRUPTED`, zero material-progress checkpoints, and no changed source or test. The local prompt remains at `/tmp/veyro-p2-4-bracket-prompt.txt`; do not treat its presence as a completed implementation. No second guarded dispatch was attempted this runner turn.

Independent unchanged-state checks: existing focused tests 17/17 PASS and Ruff PASS, but the two bracket-expression false greens in `GATE3-R1-P2-4-BRACKET-EXPRESSION-ROOT-CAUSE-2026-10-09.md` remain. No GitHub mutation, review, scenario promotion, or new finding closure occurred. Next legal action is one fresh bounded implementation turn after current-operation reconciliation, invoking the guard with the supported `claude exec --file /tmp/veyro-p2-4-bracket-prompt.txt` form (or equivalent prompt argument), then verifying actual edits and controls. Do not replay this failed invocation with `--format`.

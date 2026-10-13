---
doc: BUG-053
module: MOD-001
status: OPEN
priority: P0
requirement: GOV-01-R04
scenarios: SCN-MOD001-006, SCN-MOD001-007, SCN-MOD001-095, SCN-MOD001-096
---

# BUG-053 — Partial SQL table extraction can falsely PASS

The independent gate-2 round-2 review found R2-N01: a statement containing one cleanly extracted own-domain table and an unextracted cross-domain table can return exit-0 PASS. Confirmed forms include comma-separated `FROM` elements, `REFERENCES`, `USING`, and `ONLY`. This is a P0 recurrence of the cross-domain false-clean invariant, distinct from BUG-052's original qualified/cased forms. The round-2 verdict is BLOCKED (P0=1/P1=1/P2=2/P3=2), not a scenario PASS. Source and reproducer: `knowledge/03-Modules/MOD-001/evidence/code-review/GATE2-MODULE-DEPS-CODE-REVIEW-ROUND2-2026-10-06.md` §R2-N01.

The qualified `veyro-lead` decision upheld R2-N02 as the contract root cause and amended ADR-011 with binding D6.7 extraction-totality and per-position fail-closed rules. See `knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R2-N01-N02-QUALIFIED-ROOT-CAUSE-2026-10-06.md` and `knowledge/04-Decisions/ADR-011-gate2-module-deps-input-contract.md` §D6.7.

**Status: OPEN.** The first D6.7 `FROM` comma-list subcase is locally verified, but the remaining source/test remediation and independent post-remediation assurance are not. Next: reconcile the changed-strategy guard after this bounded increment, then address the remaining prescribed negative, positive, and mutation controls. Do not re-run the completed R2 review, promote the four scenarios, or wire live CTE state 3 under the standing U1/U2 B HOLD.

**2026-10-06 bounded progress:** The first `FROM` comma-list subcase was implemented and locally verified (471/471 architecture-gate tests, Ruff and compile PASS), but the guarded Sonnet operation stopped at its soft no-progress budget before a final response. The runner independently reconciled the source/test hashes and wrote `knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R2-N01-D6.7-FROM-LIST-FIRST-SUBCASE-2026-10-06.md`. This is a partial fix only; R2-N01 and BUG-053 remain OPEN, with the remaining D6.7 positions and corpus unverified.

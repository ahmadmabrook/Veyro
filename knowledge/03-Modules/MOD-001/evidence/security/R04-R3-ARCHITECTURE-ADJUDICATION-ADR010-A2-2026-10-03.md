---
doc: R04_R3_ARCHITECTURE_ADJUDICATION
module: MOD-001
scope: GOV-01-R04 (TSD §24.1 RLS lint + permission lint; ADR-005 Decision 1 slice 3)
date: 2026-10-03
decided_by: fresh veyro-lead (Opus, Task subagent ab5b62eb296d4578e), dispatched by fresh parent session 7c774fbc-d164-497d-887e-42060f7a302d (no implementation or R3 context reused)
decision_record: knowledge/04-Decisions/ADR-010-rls-gate-runtime-envelope-manifest-predicate.md, Amendment A2 (append-only)
status: DECIDED (architecture only). R04 BLOCKED; SCN-067 BLOCKED; nothing approved, promoted, implemented, committed or pushed
---

# R04 R3 architecture adjudication → ADR-010 Amendment A2

## Inputs and boundary

- **Input:** `R04-CRITICAL-SLICE-SECURITY-REVIEW-R3-2026-10-03.md`. This
  review is BLOCKED and incomplete: it stopped on a classifier stop, and its
  findings are code-reading hypotheses.
- **What the adjudication used:** only that report's text, plus read-only
  analysis of code and design.
- **What was not used:**
  - R3's raw transcript was not read.
  - Withheld classifier content was not reconstructed.
- **What was not done:** no database, Docker or Colima probe, and no test run.

## Model route (orchestrator-run)

`backend/.venv/bin/python knowledge/05-QA/tools/mr_verify.py <transcript> opus veyro-lead`
returned **PASS: 20 turns, 100% `claude-opus-5-5`** (exit 0).

- **Transcript:** `~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/7c774fbc-d164-497d-887e-42060f7a302d/subagents/agent-ab5b62eb296d4578e.jsonl`
- **Transcript sha256:** `d700d112f8a7f290d677102c013bd23131849efe6c39657f34a04985d0f31b35`
- **meta.json:** `agentType: veyro-lead`, `model: opus`, foreground, non-interactive.

## Pre/post integrity (parent)

- `verify_baselines.py` returned PASS 4/4.
- Gate `tools/validate_architecture_gates.py` sha256 is
  `34aa8461c2280828a6a0b18b9139ddb18ee35ee331b5ecf58f882b89c629e91b`. This
  is the file R3 reviewed, and it is unchanged.
- `git diff` sha256 was `827cbaa1…c7aec7a1` before and after the lead ran.
  This is identical to R3's record.
- `git status --short` sha256 was `06aa71fd…a6f20b` before and after the
  lead ran. It differs from R3's `09813406…` only because R3's own evidence
  file was added after R3's hash was taken.
- **Parent writes:**
  - the ADR-010 A2 append, plus the `amended:` front-matter line;
  - this file;
  - one `CURRENT_STATE.md` checkpoint line.

## Dispositions (decided; full rationale in ADR-010 A2.1–A2.8)

| R3 | Class | Sev | Decision |
|---|---|---|---|
| P1-1 `pg_init_privs` forges system status | A, ADR gap | P1 | A2.2: system means a system namespace **and** oid < 16384. A captured stock object gets the token `SYSTEM_OBJECT_EXTENSION_MEMBER`. |
| P1-2 SECURITY DEFINER review only if executable | A | P1 | A2.3: unconditional, per TSD §7.3. |
| P1-3 EXECUTE regardless of language | A | P1 | A2.4: languages must be stock-trusted (`sql`/`plpgsql`), and aggregate components are checked. |
| P2-a rewrite rules | A | **P1 (raised)** | A2.5: every non-stock, non-`_RETURN` rule FAILs. |
| P2-b case-sensitive `app.` | B, implementation | P2 | A2.8, fixture N42 |
| P2-c function `proconfig` tenant context | A | P2 | A2.6 |
| P2-d first-`.` identity split | B, implementation | P2 | A2.8, fixture N43 |
| P3-a substring approval match | A | P3 | A2.7: token-bounded match. |
| P3-b `oauth2.flows` contents | D, deferred | P3 | Deferred to the contract-validation scope. D5.2 is met, and there is no permission-lint false PASS. |

There are no false positives, and no owner-reserved matter is involved.
Admitting any extension, including `pg_trgm`, needs a later superseding ADR;
that is an engineering matter, not an owner matter.

The decision text has a known cross-reference slip: its Status line and
A2.10 cite "A2.9" for the owner determination, which is actually in A2.10.
This is noted in A2.12; the decision text was not altered.

## Decided vs still requiring execution

**Decided (design):**

- every classification and severity above;
- the A2.2–A2.7 rules and their tokens;
- the threat-model boundary in A2.0;
- the P3-b deferral;
- the acceptance rows N33–N45 and P11–P13.

**Still unexecuted.** Every premise is still unexecuted, which covers:

- the `ALTER EXTENSION … ADD` capture and today's false PASS (N33–N36,
  including whether PG16 refuses to capture a stock object);
- the trigger and event-trigger definer bypass (N37);
- the `internal`/`c`/untrusted-PL wrapper (N38);
- aggregate-owner EXECUTE (N39);
- rule owner-rights RLS bypass (N40);
- the `proconfig` override (N41);
- mixed-case `setconfig` (N42);
- the `"harness.x"` scope escape (N43);
- that a clean PG16 has zero A2 hits (P11).

The A2.11 residuals, including the server-invoked stock-function slots, are
left for R4 to probe.

## Next bounded instruction: SAME retained `veyro-critical-engineer` implementation session

1. Implement ADR-010 Amendment A2 exactly, within ADR-010's existing
   in-scope files only:
   - **A2.2:** in `tools/validate_architecture_gates.py`, remove
     `pg_init_privs` from the system classification (L643, and the definer
     query at L605–607). Add the extension-capture flag and the token
     `SYSTEM_OBJECT_EXTENSION_MEMBER`, and extend the A1.7 exclusivity.
   - **A2.3:** drop the EXECUTE `EXISTS` at L608–610.
   - **A2.4:** add the language rule and the aggregate-component query.
   - **A2.5:** add the `pg_rewrite` rule.
   - **A2.6:** add the `proconfig` tenant-context rule.
   - **A2.7:** make `resolve_approval` token-bounded (L406, L414).
   - **A2.8:** apply the fixes at L668 (lower-case) and L796–798 / L818
     (separate schema field).
   - Update the docstring at L77–79 and the System-objects paragraph.
2. Add N33–N44 as executed fixtures:
   - integration tests in `backend/tests/integration/test_architecture_gate_rls.py`
     on CAP-008 Colima PG16;
   - N44 as a unit test in `tools/tests/test_validate_architecture_gates.py`;
   - assert the behavioural leak wherever a row specifies one;
   - pre-assert the `pg_init_privs` row for N33–N35.

   Then add P11–P13, and the N45 kill-check with one killed mutant per A2
   rule and the real tool's SHA-256 unchanged.
3. Re-run, for real:
   - all existing N1–N32 (including N31a/b) and P1–P10;
   - the gate unit suite;
   - the Colima RLS integration suite;
   - the full backend suite;
   - Ruff and mypy;
   - `verify_baselines.py`.

   Record raw output under `knowledge/03-Modules/MOD-001/evidence/security/`
   as `R04-ADR010-A2-IMPLEMENTATION-RAW-<date>.txt`.
4. If PostgreSQL contradicts any A2 premise, record the raw behaviour and
   report it; do **not** redesign. For example, if PG16 refuses N36, commit
   the raw refusal and substitute the unit verdict case that A2.9 allows.
   Design questions go back to a fresh `veyro-lead`.
5. **Do not:**
   - promote or edit any scenario (SCN-004/005/010/011/067);
   - edit `STATUS.md`, `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`, the
     harness or CI;
   - commit or push;
   - self-review or self-approve.

   The orchestrator independently re-runs the suites and attests the
   session with `mr_verify.py`.

**After that, as separate governed steps:**

1. A fresh `veyro-security-reviewer` R4, mr_verify-attested, on a
   disposable CAP-008 PG16. It must:
   - execute N33–N43 adversarially;
   - execute the probes R3 skipped: adversarial policy predicates, and at
     least one privilege path outside D1.4 and A2;
   - probe the A2.11 server-invoked slots.
2. A distinct fresh `veyro-code-reviewer`.
3. Only then, the governed SCN-067 and SCN-004/005/010/011 promotion step.

R04 and SCN-067 remain **BLOCKED** until those steps are complete.

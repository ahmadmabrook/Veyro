# RULE-001 — MOD-004 tenant isolation (RLS) rule record

**PROVISIONAL. Not gate-eligible.** Documentation record only. Claims no ACTIVE lifecycle, Module Ready, Scenario PASS, security PASS or S1 authorization. Fields follow EIP Appendix H RULE schema (¶11773; zero-based paragraph index) from the extract `mod004-capability-governance-source-supplement-20261018.md` (claimed SHA-256 `2de22c1774d43be381276dcba8143d3ea1e8e7e0ae626de5faed19f8b3f57b8a`; rehash not computed in the authoring session, runner to verify externally).

| Field (¶11773) | Value |
|---|---|
| rule path | `.claude/rules/backend/mod004-rls.md` (exists; promoted). File SHA-256: NOT_COMPUTED in the authoring session (no hashing tool); runner must verify externally. |
| paths glob | `backend/app/tenancy/**`, `backend/migrations/**`, `backend/tests/integration/tenancy/**`, `infra/db/**` |
| source requirement / TSD anchor | ADR-0002 D1-D6 (`knowledge/00-Decisions/ADR-0002-mod004-control-plane-isolation.md`), D11, D12; TSD §7.3, TSD ¶743, ¶747, ¶1208, ¶1240; INV-PLT-01 (¶10557); EIP Appendix H ¶11780 (backend rule standard), ¶11758. |
| conflicts checked | Read against ADR-0002 and the rule's own authority clause (ADR wins on disagreement). No independent conflict check against higher-precedence global rules is recorded. Status: NOT independently checked. |
| positive/negative validation | OUTSTANDING (see below). None recorded. |
| supersedes | none |
| lifecycle status | null (no ACTIVE/DEPRECATED/REVOKED claim) |
| last reviewed at | null |
| next review due | null |
| rollback target/procedure | PROVISIONAL: revert the rule file's promotion commit or remove this record; no runtime effect. Formal procedure to be set at registration. |

Candidate operational status: null.

## Outstanding qualification (EIP ¶11816, ¶11818)

1. **Path-scope test (¶11818):** not run. Needs representative matching paths (for example `backend/app/tenancy/x.py`, `backend/migrations/0001.sql`, `backend/tests/integration/tenancy/t.py`, `infra/db/init.sql`) and non-matching paths (for example `backend/app/other/x.py`, `frontend/**`, `knowledge/**`) to show scoping is correct and does not pollute unrelated contexts.
2. **Runtime-negative qualification:** not run. Per the rule's own "Verification evidence required", both are obligations and not recorded today:
   - Role-privilege test: the runtime role is not a table owner and has no BYPASSRLS or role-membership escape.
   - Transaction-pool reuse test: `app.*` context does not leak between transactions on a reused pooled connection.
3. **Independent review (¶11774):** not done. The rule may not lower higher-precedence constraints.
4. **Security-sensitive extras (¶11816):** abuse and permission-negative tests not run.

## Blockers

- Missing CAP: PostgreSQL 17, psycopg, psycopg_pool and a free local runtime. No CAP record or supply-chain evidence exists; running the runtime tests above depends on them (ADR-0002 D11, D12.3).
- Missing SKL: migration-lint (ADR-0002 D5). No SKL record, eval or mutation-corpus qualification.
- No qualified ACTIVE manifest row exists (`contracts/engineering/module-capabilities.yaml` is PROVISIONAL).

Until these are resolved this record is `BLOCKED: CAPABILITY_GAP` for the Capability / Rules / Skills gate.

## Open source ambiguities

- EIP §18 ¶1167 prior-module dependency: the owner decision `knowledge/00-Decisions/OWNER-2026-10-18-mod004-foundation-dependency.md` is published and attested at `6311ab38f548c789c026baac791b546ead1a992e` with exact-head CI run `39107717468`. It records owner YES, scoped solely to MOD-004's dependency edge on MOD-001/MOD-002 (the FOUNDATION ONLY certificates satisfy it, subject to verification at time of use). It does not make MOD-004 Ready, does not make anything ACTIVE, is not a Scenario PASS and authorizes no code; none of those is inferred here.
- ADR-0002 D12 still carries stale "interpretation pending" wording for this item. It has not been updated here (out of scope for this edit) and should be reconciled separately.
- D4.3 driver, database and version are PROPOSALS, not accepted; this record does not select them.

# RULE-002 — MOD-004 CON-04 privileged-console rule record

**PROVISIONAL. Not gate-eligible.** Documentation record only. Claims no ACTIVE lifecycle, Module Ready, Scenario PASS, security PASS or S1 authorization. Fields follow EIP Appendix H RULE schema (¶11773; zero-based paragraph index) from the extract `mod004-capability-governance-source-supplement-20261018.md` (claimed SHA-256 `2de22c1774d43be381276dcba8143d3ea1e8e7e0ae626de5faed19f8b3f57b8a`; rehash not computed in the authoring session, runner to verify externally).

| Field (¶11773) | Value |
|---|---|
| rule path | `.claude/rules/admin/mod004-privileged-console.md` (exists; promoted). File SHA-256: NOT_COMPUTED in the authoring session (no hashing tool); runner must verify externally. |
| paths glob | `frontend/console/con-04-tenant-provisioning/**` — a non-operative provisional placeholder that matches no existing repository path; not an implementation path or a claim that a UI exists. |
| source requirement / TSD anchor | ADR-0002 D6, D11, D12, D14; EIP Appendix H ¶11758 and ¶11781 (admin/privileged-console family for Internal SaaS Console), MOD-029 card ¶2853 applied to MOD-004 by ADR-0002 D11 [INFERENCE]; Appendix F ¶8740 (CON-04 primary mutation `ProvisionTenant`); INV-PLT-01 (¶10557). |
| conflicts checked | Read against ADR-0002 and the rule's own authority clause (ADR wins on disagreement). No independent conflict check against higher-precedence rules is recorded. Status: NOT independently checked. |
| positive/negative validation | OUTSTANDING (see below). None recorded. |
| supersedes | none |
| lifecycle status | null (no ACTIVE/DEPRECATED/REVOKED claim) |
| last reviewed at | null |
| next review due | null |
| rollback target/procedure | PROVISIONAL: revert the rule file's promotion commit or remove this record; no runtime effect. Formal procedure to be set at registration. |

Candidate operational status: null.

## Outstanding qualification (EIP ¶11816, ¶11818)

1. **Path-scope test (¶11818):** not run. Needs matching paths under `frontend/console/con-04-tenant-provisioning/` and non-matching paths (for example `frontend/console/con-01-*/**`, `frontend/admin/**`, `backend/app/tenancy/**`). No matching real path exists today.
2. **Runtime-negative qualification:** not run; no UI exists to exercise. Permission-negative and abuse tests (no impersonation, break-glass or destructive paths; no cross-tenant access without a D6.3 allowlisted function) are outstanding.
3. **Independent review (¶11774):** not done.

## Explicit CON-04 privileged-console-review: BLOCKED

The `privileged-console-review` check (EIP ¶11758) for CON-04 is **blocked**:

- No CON-04 UI or implementation path exists; the single glob is a placeholder.
- The D14 screen-ownership mapping is an unreviewed engineering decision outside ADR-0002's accepted scope; no CON-04 route/permission/masking contract exists.
- Prerequisites unmet: MOD-007/008 authn/authz and audit, D6.7 transport/caller binding, owner-reserved region choice, OWNER-Q2 (Scenario Review timing).
- The manifest row binding is PROVISIONAL only, not a qualified ACTIVE row.

## Other blockers

- Missing CAP: PostgreSQL 17, psycopg, psycopg_pool and a free local runtime (inherited from RULE-001; tenant isolation mechanics live in `mod004-rls.md`).
- Missing SKL: migration-lint.

Until these are resolved this record is `BLOCKED: CAPABILITY_GAP` for the Capability / Rules / Skills gate.

## Open source ambiguities

- Whether the privileged-console binding for MOD-004 is a source requirement or an inference: EIP ¶11758 mandates it explicitly only for MOD-029; ADR-0002 D11 extends it to MOD-004 as an [INFERENCE]. Recorded as inference, not resolved.

---
doc: PERMISSION_GATE_FIXTURE_2026-10-02
module: MOD-001
gate: TSD §24.1 gate 4 — permission lint (`tools/validate_architecture_gates.py --gate permission`)
status: EXECUTED — R1 BLOCKED (P1-B); re-implemented to ADR-009 D1-D4; PENDING fresh R2 review
---

# Permission gate fixture record (IMPLEMENTATION.md §4 gate 4)

Synthetic OpenAPI 3.1 JSON documents and a synthetic registry in isolated
temp directories (`tools/tests/test_validate_architecture_gates.py`).
Raw output: `R04-RLS-PERMISSION-GATES-RAW-2026-10-02.txt` §2-§4.

| Fixture | Verdict | Scenario |
|---|---|---|
| Two operations declaring registered `members.profile.read`/`self` and `billing.refund.create`/`location` | PASS, exit 0 (CLI too) | SCN-010 |
| One operation with no `x-veyro-permission`, among valid ones | FAIL, exit 1, exactly one `UNREGISTERED_PERMISSION` citing `DELETE /members (deleteMember)` | SCN-011 |
| Declared but unregistered `platform.tenant.impersonate` | FAIL, `UNREGISTERED_PERMISSION` "not registered" | SCN-011 |
| Missing action / resource / scope; extra key; non-string values; malformed resource ×4 | FAIL, named reason each | SCN-011 family |
| Scope outside TSD §8.4 grammar; grammar-valid scope not registered for the permission | FAIL | SCN-011 family |
| Declaration only at path level | FAIL (does not cover operations) | hardening |
| All 8 HTTP methods undeclared | FAIL ×8 | hardening |
| Empty contract / path with no operations / no documents | INCONCLUSIVE, exit 2, `PERMISSION_GATE_VACUOUS` | hardening |
| YAML file, broken JSON, Swagger 2.0, `$ref` path item, broken registry, 7 invalid registry shapes, missing inputs | ERROR, exit 2 | hardening |

Real repository: `--gate permission` → ERROR exit 2 (`contracts/` not
committed). Correct fail-closed result; no real-repo PASS exists or is
claimed.

The input contract (JSON-only, `contracts/permissions/registry.json`,
`x-veyro-permission` with exactly `action`/`resource`/`scope`, no
exemptions) is this slice's proposal and needs reviewer confirmation.

## Update — R1 remediation and ADR-009 D1-D4 (2026-10-02)

The table above is the pre-R1 run; R1 found P1-B (3.2 `query`/
`additionalOperations` and uppercase `POST` scanned out of existence
beside a valid GET → false PASS). The gate now follows
`knowledge/04-Decisions/ADR-009-permission-lint-input-contract.md`.
All synthetic fixtures now also carry `x-veyro-authentication` and native
`security`; the registry entries carry `authentication` (+ `justification`
for non-session classes). Raw: `R04-ADR009-IMPLEMENTATION-RAW-2026-10-02.txt` §1.

| Fixture | Verdict |
|---|---|
| One operation per class (authenticated, credential_exchange, provider_signature, anonymous), each consistent | PASS; inventory lists exactly the 3 non-`authenticated` ops, in text and JSON; per-class counts in notes |
| Missing / unknown / case-variant / non-string `x-veyro-authentication` | FAIL `UNREGISTERED_PERMISSION` |
| Operation class ≠ registry class (3 directions) | FAIL |
| Non-session registry entry without / with blank / non-string justification; `authenticated` with a justification; missing or non-enum `authentication` | ERROR |
| `authenticated` with root `[{}]`, root `[{session},{}]`, op `[]`, no security at all, undefined scheme, op `[{session},{}]` | FAIL |
| `anonymous` inheriting root, non-empty, `[{}]`, inheriting empty root | FAIL |
| `credential_exchange` / `provider_signature` inheriting root | FAIL; explicit defined security PASS |
| `webhooks` (empty or populated), op `callbacks`, `components.pathItems`, `components.callbacks`, non-object components, path not starting `/`, malformed security shape, undefined root scheme, non-string operationId | ERROR |
| `openapi` 3.0.3, 3.2.0 and malformed versions | ERROR |
| Duplicate `GET /members/{id}/profile` vs `{memberId}` across files; duplicate operationId across files and within a file | ERROR |
| Symlinked document, symlinked subdirectory, symlinked openapi dir, symlinked registry | ERROR |
| R1 P1-B cases (`POST`, `Get`, `query`, `additionalOperations`) | ERROR |

Real repository: ERROR exit 2 (no `contracts/permissions/registry.json`).
No real-repo PASS exists or is claimed. Disposition is the R2 reviewer's.

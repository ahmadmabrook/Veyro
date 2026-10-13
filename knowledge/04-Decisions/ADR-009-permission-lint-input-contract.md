---
doc: ADR-009
status: DECIDED (2026-10-02) — conforming to the governing baseline; no owner approval required (see "Conformance determination")
date: 2026-10-02
decided_by: veyro-lead (fresh Opus architecture-decision session, claude-opus-5-5; not the Slice-6 implementer; no code/security review approval given)
model_attestation: mr_verify.py on complete session transcript 19baa133-c3ea-4927-816c-845de1df57d6.jsonl, tier opus, agent veyro-lead → PASS, 68 turns, 100% claude-opus-5-5 (orchestrator independently re-run after provider limit)
module: MOD-001 (GOV-01-R04, TSD §24.1 gate 4 — permission lint; ADR-005 Decision 1 slice 3)
requested_by: knowledge/03-Modules/MOD-001/evidence/security/R04-CRITICAL-SLICE-SECURITY-REVIEW-R1-2026-10-02.md (P2: "the JSON-only permission format, public-endpoint declaration shape, registry path and extension key need a recorded veyro-lead design decision before CI wiring")
amended_by: ADR-010 D5 (2026-10-02) — D2 registry v2 with resolving `approval` on non-`authenticated` entries; D4.3 strict native `security`/securitySchemes validation. All other ADR-009 text stands.
---

# ADR-009: Permission-lint input contract — OpenAPI 3.1 JSON, permission registry, `x-veyro-permission` + `x-veyro-authentication`, and non-session endpoints without an exemption

## Context

TSD §24.1 gate 4 (verified against the TSD docx itself, not just
`TSD_MIRROR.md` line 11614): *"Permission lint: API commands/queries
declare action/resource/scope; unregistered permission names fail build."*
The baseline fixes the following and this ADR does not change any of it:

- **API style:** TSD ADR-004, *"REST/JSON + OpenAPI with surface BFFs"*
  (`TSD_MIRROR.md` line 737). Reference backend is FastAPI/Pydantic,
  chosen partly for OpenAPI (line 976). Generated clients consume
  OpenAPI (lines 977-980, 1128).
- **Permission grammar:** TSD §8.4, `<domain>.<resource>.<action>`.
  Permissions are *"canonical action/resource pairs"*. **Scope grammar is
  closed:** `tenant | organization | brand | region | location |
  department | assigned_clients | self | explicit_resource`. It has no
  `public`/`anonymous` value.
- **Actors:** TSD §8.2/§8.3. `authorize()` evaluates a human, service, or
  delegated actor. §11.4 adds OAuth 2.1/OIDC partner apps and service
  accounts.
- **Non-session entry points the baseline already requires:**
  - login, OTP, passkey and recovery (IAM-01, line 2772);
  - provider webhooks that are *"HMAC-signed, timestamped and
    replay-protected"* (§11.4) and enter through *"dedicated validated
    endpoints"* (§23.2), via `verify_webhook`/`inbound_webhook`
    (§20.1), with the threat-model row "Webhook/API abuse";
  - synthetic monitoring of login and webhook paths (lines 8838, 11335),
    which implies probe-able endpoints.
- **Repository layout:** EIP `contracts/ # OpenAPI/events/schemas/shared
  contract artifacts` (`EIP_MIRROR.md` line 1494). MOD-001
  `IMPLEMENTATION.md` §1 plans `contracts/openapi/` as the
  permission-lint input. `IMPLEMENTATION.md` §4 names the gate output
  `UNREGISTERED_PERMISSION` citing the endpoint.
- **What the baseline leaves open:** no OpenAPI file format, version,
  extension key, registry location, or registry shape is specified in the
  TSD, EIP, or design bundle (searched). Those are implementation-contract
  details inside an accepted architecture. Deciding them is a veyro-lead
  call, not an owner call, as long as they stay inside the constraints
  above.

The Slice-6 implementer proposed JSON-only input,
`contracts/permissions/registry.json`, `x-veyro-permission`, and **no
exemption mechanism**. The implementer itself noted that health checks
would then need a decision. Independent review R1 asked for that decision
before CI wiring, and separately found operation under-scan (P1-B).
P1-B's remediation is concurrent and is the implementer's. This ADR fixes
the contract the remediation must meet; it does not review that code.

## Decision

### D1 — Input format: OpenAPI **3.1.x**, **JSON**, committed under `contracts/openapi/`

1. Every OpenAPI document the gate reads is a UTF-8 `.json` file under
   `contracts/openapi/`, searched recursively. Any other file there is an
   **ERROR**, never skipped. The only ignored file is `.gitkeep`.
   Symlinks are an ERROR.
2. **`openapi` must match `3.1.<patch>`.** 3.0.x is refused. FastAPI emits
   3.1, so a second dialect adds review surface for no gain. 3.2+ is
   refused because it adds `query` and `additionalOperations`. Accepting
   any later version requires a superseding ADR and gate support for the
   version's new operation-bearing fields.
3. **Operation-bearing locations other than `paths` are refused (ERROR)**
   until a later ADR covers them:
   - top-level `webhooks` (3.1 outbound webhooks — §11.7 says the public
     webhook contract is a separate versioned contract, owned by ECO-01);
   - `components.pathItems`;
   - `components.callbacks`;
   - any operation-level `callbacks`.
   Path-item `$ref` is an ERROR (inline it). Path-item keys are limited to
   the eight lowercase methods plus `summary`, `description`, `servers`,
   `parameters` and `x-*`. Anything else is an ERROR, including uppercase
   methods.
4. **Strict JSON parsing:** duplicate keys are an ERROR, excessive nesting
   is an ERROR, and every parse failure is a structured ERROR, never an
   uncaught exception.
5. **One owner per operation across documents:** a duplicate `(method,
   path template)` is an ERROR, comparing templates with parameter names
   normalised so that `/a/{id}` and `/a/{x}` collide. A duplicate
   `operationId` across all documents is also an ERROR.

**Why JSON, not YAML:**

- It is literally TSD ADR-004's REST/JSON + OpenAPI. It is the native
  output of the reference stack (`app.openapi()`). It needs only the
  stdlib, so no new parser dependency has to be qualified under
  `CAPABILITY_POLICY.md`.
- YAML's anchors, aliases and merge keys, implicit typing, and
  parser-dependent duplicate-key behaviour are attack surface for a
  security gate whose failure mode is a false PASS.

Authors may hand-write YAML for convenience, but the gate input is the
committed JSON. TSD Appendix F's `contracts/ui/screen-contracts.yaml` is a
different artifact (screen-contract lint, gate 5). This decision neither
governs nor conflicts with it.

### D2 — Registry: `contracts/permissions/registry.json`, version 1

```json
{
  "version": 1,
  "permissions": {
    "members.profile.read": {
      "scopes": ["location", "self"],
      "authentication": "authenticated"
    },
    "iam.session.create": {
      "scopes": ["self"],
      "authentication": "credential_exchange",
      "justification": "IAM-01 sign-in establishes the principal; no prior session can exist."
    }
  }
}
```

Validation rules:

- **Top level:** exactly `{version, permissions}`. `version` is a JSON
  integer equal to 1, and a boolean is refused.
- **Names:** each permission name fully matches
  `[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*` (TSD §8.4). Use
  `fullmatch`/`\Z`, never `$`.
- **`scopes`:** a non-empty, duplicate-free list of strings drawn only
  from the nine TSD §8.4 values.
- **`authentication`:** required, a single string from the D4 enum. There
  is no default.
- **Key sets:** an entry whose authentication is `authenticated` has
  exactly `{scopes, authentication}`. Any other authentication value
  requires exactly `{scopes, authentication, justification}`, with a
  non-empty (after trim) string justification.
- **Malformed input:** any malformed entry is a structured ERROR, never an
  exception.

The schema is a MOD-001 deliverable. The real registry *contents* belong
to the authorization module (IAM-03; IAM-002 is co-owned with MOD-008 per
`REQUIREMENTS.md`). MOD-001 commits only synthetic fixtures under
`tools/tests/`. It MAY commit an empty skeleton registry and OpenAPI
directory, which yields INCONCLUSIVE (vacuous), never PASS.

### D3 — Operation declaration: `x-veyro-permission`

Every operation, of all eight methods, in every document carries:

```json
"x-veyro-permission": {"action": "read", "resource": "members.profile", "scope": "self"}
```

- The key set is exactly `{action, resource, scope}`, all strings.
- `resource` fully matches `<domain>.<resource>` and `action` fully
  matches `[a-z][a-z0-9_]*`. The permission name is `resource + "." +
  action`. This is TSD §24.1's "action/resource/scope" wording, mapped
  onto §8.4's three-segment name.
- `scope` is a **single** grammar value, and that value must be in the
  registry entry's `scopes`. Surface BFFs (TSD ADR-004) give staff-scoped
  and self-scoped reads separate operations. A future genuine need for a
  multi-scope operation is a superseding-ADR matter. It needs no owner
  approval while the grammar is unchanged.
- A path-level declaration never covers operations.

### D4 — Authentication class: `x-veyro-authentication` on every operation (the non-exemption mechanism)

Every operation also carries `"x-veyro-authentication": "<class>"`, using
a closed enum:

| Class | Meaning | Baseline anchor |
|---|---|---|
| `authenticated` | A verified principal: user session, service account, partner OAuth token, or delegated actor. `authorize()` runs with full actor context. | TSD §8.1-8.2, §11.4 |
| `credential_exchange` | The operation's purpose is to establish or recover a principal: sign-in, OTP, passkey assertion, token refresh, recovery. | IAM-01 (TSD line 2772) |
| `provider_signature` | An inbound provider callback authenticated by signature, timestamp and replay protection, not by a principal. | TSD §11.4, §20.1, §23.2, threat model "Webhook/API abuse" |
| `anonymous` | No caller verification at all, for example a liveness/readiness probe served by the application. | (no product endpoint authorised by this ADR) |

**Rules enforced by the gate.** Each per-operation failure is reported as
`UNREGISTERED_PERMISSION` citing the endpoint, with the reason in
`detail`. That keeps `IMPLEMENTATION.md` §4's named violation. Input
structure problems are ERROR `PERMISSION_GATE_INPUT_INVALID`.

1. A missing `x-veyro-authentication`, or a value outside the enum, is a
   violation.
2. **Two-key match:** the operation's class must equal the registry
   entry's `authentication` for the declared permission. So every
   non-`authenticated` operation needs both an operation-level
   declaration and a registry entry with a written justification. The
   registry entry also has a distinct permission name, because one entry
   holds exactly one class. Neither key alone suffices, and both show up
   in a diff.
3. **Consistency with native OpenAPI `security`.** Effective security is
   the operation-level `security` if present, otherwise the root-level
   value.
   - `authenticated`: effective security must be present and non-empty,
     must contain no empty requirement object `{}`, and every scheme it
     names must exist in `components.securitySchemes`. This catches a
     route whose contract says "anyone" while its declaration says
     "authenticated".
   - `anonymous`: the operation must explicitly set `"security": []`.
   - `credential_exchange` / `provider_signature`: the operation must set
     `security` explicitly (any valid value, including `[]`). It may not
     silently inherit root security.
4. **Visible inventory:** every run, including PASS, prints each
   non-`authenticated` operation (endpoint, class, permission) and the
   count per class. The JSON report carries the same list. Nothing is
   exempt, and nothing non-standard is quiet.

All four classes still declare a full, registered action/resource/scope
triple. Illustrative values, chosen and justified by the owning module:

- sign-in: `iam.session.create` / `self`;
- payment-provider webhook: `billing.provider_event.ingest` /
  `explicit_resource`, with the target resolved server-side from the
  verified provider reference, never trusted from the payload;
- probe: `platform.health.read` / `explicit_resource`, returning no
  tenant data.

**This ADR authorises the representation only, not any specific public
endpoint.** Whether an anonymous product endpoint exists (for example a
public schedule or lead capture) remains the owning module's product
decision.

### D5 — Explicitly rejected, because each would need owner approval

- **Adding `public`/`anonymous`/`none` to the scope grammar.** That
  changes TSD §8.4.
- **Any exemption list, skip flag, path-pattern allowlist, or "undeclared
  = public" default** for operations. This is the silent bypass the gate
  exists to prevent, and it contradicts §24.1's "API commands/queries
  declare".
- **Excluding health, webhook or login routes from the contract** so they
  are never scanned. That is an exemption in effect, and §23.2 requires
  webhooks at "validated endpoints", which presupposes they are declared.

## Alternatives considered

| Alternative | Consequence | Verdict |
|---|---|---|
| YAML (or both) as gate input | New parser dependency to qualify. Alias/merge/implicit-type ambiguity in a false-PASS-sensitive gate. Two formats double the test matrix. | Rejected |
| OpenAPI 3.0 + 3.1 | Two dialects. 3.0 is not produced by the reference stack. | Rejected; 3.1 only |
| Use only native OpenAPI `security: []` to mark public ops | Public status is silent: one array edit, no registry trace, no justification, and root-level inheritance can flip it. | Rejected as sole mechanism; kept as the D4.3 consistency check |
| `public` scope value | Changes TSD §8.4 grammar. | Owner-reserved; rejected |
| Exemption allowlist file | A silent bypass by design. | Owner-reserved; rejected |
| Annotate code only, no committed contract | Contradicts TSD ADR-004/EIP `contracts/`. Not machine-checkable by a language-neutral gate. | Rejected |
| Separate `domain` field in the declaration | Diverges from §24.1's literal action/resource/scope. | Rejected |

## Consequences

- The gate rejects more inputs: 3.0, `webhooks`/`callbacks`/`pathItems`,
  and duplicate operations. Authors must inline `$ref` path items and
  give each non-session use its own permission name.
- Future FastAPI modules declare both extensions via `openapi_extra`, and
  express authentication with FastAPI security dependencies so `security`
  is emitted. Ideally the runtime authorizer and the declaration come from
  the same object (recommended, not mandated here).
- **Residual risk, disclosed:** the gate proves *contract* declaration,
  not that the served routes equal the contract, nor runtime enforcement
  (IAM-002's runtime half). An operation omitted from the committed
  contract is invisible to this gate. Until a contract/route parity check
  exists (committed `contracts/openapi/*.json` equals the regenerated
  application OpenAPI, in CI), any PASS must be worded "every operation in
  the committed contract", never "every served API". No HTTP route exists
  in the repo today (`backend/` has no FastAPI app), so parity is
  untestable now. It becomes a blocking prerequisite before the first
  module that serves a real route can cite this gate as authorization
  evidence. This is the TSD §24.1 "API/event schema compatibility" stage,
  not new scope.

## Conformance determination

Conforms to Blueprint > TSD v1.4.1 > design bundle > EIP v1.4.1. It
changes:

- no TSD scope or permission grammar;
- no API style (TSD ADR-004 is preserved);
- no product feature: no public endpoint is created or authorised;
- no module scope (it implements an existing GOV-01-R04 gate 4
  obligation);
- no routing (ADR-005 is unchanged).

It incurs no spend, uses no real data, and takes no production action.
**No owner approval is required.** Items in D5 would require it, and none
is adopted.

## Follow-up

**For the critical implementer (`veyro-critical-engineer`, Slice 6
remediation):**

1. Conform `tools/validate_architecture_gates.py --gate permission` to
   D1-D4. The deltas from the current in-flight code as read 2026-10-02:
   - restrict to 3.1.x (it currently also accepts 3.0);
   - refuse `webhooks`, `components.pathItems`, `components.callbacks`
     and operation `callbacks`;
   - refuse symlinks;
   - add the cross-document duplicate operation and `operationId` checks;
   - add the registry `authentication`/`justification` fields;
   - add `x-veyro-authentication` and the two-key match;
   - add the effective-`security` consistency rules;
   - add the non-`authenticated` inventory in text and JSON output;
   - update the module docstring.
2. Add deliberate-negative fixtures, each failing closed:
   - a missing or unknown class;
   - an operation class that mismatches the registry;
   - a non-session registry entry without a justification;
   - `authenticated` with each of: root-only `{}`, `security: []`, absent
     security, and an undefined scheme;
   - `anonymous` without an explicit `security: []`;
   - `credential_exchange` inheriting root security;
   - a `webhooks` key;
   - operation `callbacks`;
   - `components.pathItems`;
   - an `openapi` value of 3.0.3 or 3.2.0;
   - a cross-file duplicate `GET /x` and a duplicate `operationId`;
   - a symlinked document;
   - a boolean `version`.
   Add positive fixtures with one operation of each of the four classes
   passing, and assert they appear in the inventory. Extend the mutation
   kill-check to cover the two-key match and the `security` consistency
   rule.
3. Update the Slice-6 evidence record's "proposed contract" text to cite
   this ADR. Do not self-promote any scenario.

**For the independent re-reviewer (`veyro-security-reviewer` R2, fresh
context):**

- Verify the implementation against D1-D4 literally.
- Specifically try to get a non-`authenticated` operation to PASS without
  a matching justified registry entry.
- Try to get an operation scanned out of existence (3.2 fields, `$ref`,
  `pathItems`, callbacks, case variants, duplicate documents, symlinks).
- Confirm the inventory is printed on PASS.
- Confirm that no exemption, skip, or allowlist path exists anywhere in
  the gate or CLI.
- Judge whether this ADR itself has a gap. If it does, report it as a
  finding against ADR-009, which veyro-lead amends.

**Not decided here; flagged for their owners:**

- **Contract/route parity check:** ownership is to be assigned when CI
  wiring or the first HTTP-serving module is planned. See Consequences.
- **The R1 P2 on `--non-tenant-table` exemptions lacking a committed
  audit trail:** this is RLS-gate scope, outside this ADR.
- **Observation:** MOD-001 `IMPLEMENTATION.md` §1 places
  `contracts/screen-contracts.yaml`, but TSD Appendix F requires
  `contracts/ui/screen-contracts.yaml`. Reconcile it in the gate-5 slice,
  since the TSD governs.
- **Governance records:** `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`, the
  scenario catalog, and the evidence index were deliberately not edited
  by this session. The orchestrator should reference ADR-009 in them when
  next reconciling.

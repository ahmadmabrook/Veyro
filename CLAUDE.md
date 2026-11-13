# Veyro

Multi-tenant gym management platform. Python 3.13, FastAPI, PostgreSQL 16, no ORM.
Claude Code is the development environment; GitHub Actions runs CI and nothing else.

Authority: `knowledge/00-Decisions/OWNER-2026-11-13-full-engineering-delegation.md`. Ordinary
engineering, product, architecture, infrastructure and repository decisions are delegated to the
session. Make them; do not ask. Module implementation is not gated on another module's acceptance.

## Layout

```
backend/app/            service code
  main.py               HTTP surface (platform plane + tenant plane)
  db.py                 per-plane connection pools and the tenant context manager
  config.py             environment configuration, fails closed
  tenancy/service.py    tenant lifecycle and the organization hierarchy
  tenancy/domain/       pure decision functions derived from the TSD; no I/O
  tenancy_s0.py         ProvisionTenant envelope validation (reused by the service)
  configuration/        MOD-005: evaluation.py decides, service.py does the I/O
  billing/              MOD-015: money.py, subscription.py, usage.py decide; service.py writes
  identity/             MOD-007: secrets.py (crypto), policy.py (decisions), service.py (I/O)
  authorization/        MOD-008: catalog, decision, gate, approval, audit; service.py (I/O)
  errors.py             the four service errors every module's service raises
backend/migrations/     platform/, tenant/ and product/ SQL, applied in that order
backend/tests/          unittest suites; tests/sql/isolation.sql is the isolation proof
backend/scripts/        verify_db.sh rebuilds the database and runs the isolation suite
knowledge/              decisions and module notes
tools/                  governance and lint tooling (see "Tooling that still earns its place")
```

Sources of product scope and architecture: the two `.docx` baselines and
`veyro-product-experience-design/`, pinned by SHA-256 in `PROJECT_INDEX.md`. The owner edited the
EIP and TSD on 2026-11-13; those edits are **uncommitted working-tree changes** and the pins still
bind the committed bytes. Adopting them means re-pinning `PROJECT_INDEX.md` and
`governance/registry.json` together, which is authorized but not yet done — see §5 of the
delegation record.

## Running it

Start the development database and build the schema:

```bash
docker run -d --name veyro-pg -e POSTGRES_PASSWORD=veyro_dev -e POSTGRES_DB=veyro -p 127.0.0.1:55432:5432 postgres:16-alpine
```

```bash
backend/scripts/verify_db.sh
```

`verify_db.sh` drops and rebuilds the database, applies every migration, and runs the
tenant-isolation suite. It is the fastest way to know the control plane is intact. To prove a
check still bites, break the thing it guards and watch it fail:

```bash
MUTATE="ALTER TABLE plt01.organizations NO FORCE ROW LEVEL SECURITY;" backend/scripts/verify_db.sh
```

The backend checks, each a separate command so one failure does not hide the rest:

```bash
(cd backend && python3 -m ruff check .)
```

```bash
(cd backend && python3 -m mypy)
```

```bash
(cd backend && VEYRO_DATABASE_URL=postgresql://postgres:veyro_dev@127.0.0.1:55432/veyro python3 -m unittest discover -s tests -t . -v)
```

```bash
(cd backend && python3 -m unittest discover -s app/tenancy/domain/tests -t . -v)
```

These need `backend/requirements-dev.lock` installed in the active interpreter. The repository
carries a `.venv/` (gitignored) created for this purpose; if `ruff`, `mypy`, `fastapi` or
`psycopg` is missing, install the lock into it rather than working around the gap. Say so if the
install is refused — CI covers these, but a local red is cheaper than a red `main`.

Dependencies are declared in `backend/requirements.txt` and hash-pinned in
`backend/requirements.lock`; regenerate with
`uv pip compile backend/requirements.txt --universal --python-version 3.13 --generate-hashes -o backend/requirements.lock`.

## What must not be weakened

These are product requirements, not process, and they hold whatever the schedule says.

**Tenant isolation.** Every table in `plt01` carries `tenant_id uuid NOT NULL`, a tenant-leading
primary key, `ENABLE` *and* `FORCE ROW LEVEL SECURITY`, a policy whose predicate is
`tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid`, and composite foreign keys
that carry `tenant_id` into every parent reference. Copy the pattern in
`backend/migrations/tenant/0001_organization_hierarchy.sql` exactly; each of the four parts is
load-bearing and the comment there says why.

Context is set with `set_config('app.tenant_id', %s, true)` inside a transaction — never at
session level, never interpolated into SQL. With no context the predicate is NULL, so reads return
nothing and writes are refused: **isolation fails closed, and that is the property to protect.**
`app.tenancy.db.tenant_scope` is the only way to reach `plt01`; do not add another.

**The planes are separate.** There are three. `veyro_cp_app` holds privileges in `plt01` and
nothing on the tenant registry; `veyro_cp_platform` holds the registry and nothing in `plt01`;
`veyro_iam_app` (MOD-007) holds the `iam` schema and nothing in either control-plane schema, so a
mistake in a configuration or billing query cannot read a credential hash. **No role is a member
of any other — never write `GRANT <role> TO <role>`.** No runtime role may hold `TRUNCATE` or
`REFERENCES`; `veyro_cp_app` may not hold `DELETE`; and `veyro_iam_app` may not hold `DELETE` on
anything, because revocation in `iam` is a status change that leaves evidence.

**Negative tests must actually fail closed.** A test that still passes when you remove the
protection is not evidence. Every isolation check in `backend/tests/sql/isolation.sql` has been run
against a deliberate mutation and shown to fail; a new one earns its place the same way. This
caught a weak check already: an earlier "the app role cannot DELETE" test passed only because a
foreign key refused the delete first.

**Also binding:** authentication and AAL-3 (MOD-007, built but not enforced on any request yet),
immutable audit, financial correctness, residency and retention. Validate input at trust
boundaries. Historical review outcomes and the preserved evidence trees outside the repository
are never rewritten.

**Owner-reserved**, on the owner's standing instruction and never inferred: real financial
expenditure, production deployment, real member data, and anything needing the owner's personal
authentication. `governance/registry.json` `reserved_actions` keeps the four names.

## State

Module ids come from `tools/mission_runner/module_catalog.json`, and they are **not** the
TSD's section order. PLT-01 is MOD-004, PLT-02 is MOD-005, but PLT-03 is MOD-015 — MOD-006 is
the Compose Multiplatform qualification. Check the catalogue before naming a module; this
session has already labelled one wrong by assuming the two orders matched.

**MOD-004 (tenancy control plane) — implemented, not accepted.** Working: the `plt01_platform`
registry with tenant lifecycle and append-only history, idempotent provisioning, the `plt01`
organization/legal-entity/brand/location hierarchy under forced RLS, and an HTTP surface over
both planes. Proven: isolation checks 1-13, each mutation-tested.

Known gaps, deliberate and worth reading before extending:

- **Requests are still unauthenticated.** `X-Veyro-Tenant` is a claim, shape-checked and nothing
  more, and isolation does not depend on it being honest. MOD-007 now authenticates people and
  issues sessions, but nothing ties a session to the tenant header on a request, and
  authorization is MOD-008's unbuilt work.
- **No reactivation.** `domain/lifecycle.py` admits only `provisioned → active → suspended →
  archived`. TSD §10.3 puts reactivation in PLT-03; do not invent the edge here.
- **No hard deletion.** `delete_tenant` refuses by design: PLT-01-R07 bars it until the legal,
  billing and retention gates exist. That refusal *is* the implemented requirement.
- **`/healthz` is liveness only** and returns ok while the database is unreachable. A readiness
  endpoint that checks the pool is unwritten.
- Departments and cost centres (PLT-01-R02) are unbuilt; nothing reads them yet.
- Most modules under `app/tenancy/domain/` are not wired into the service. `lifecycle` is. The
  rest are spec analyses, and several say in their own docstrings that their answers are the
  author's reading rather than a sourced fact — read that before depending on one.

**MOD-005 (PLT-02 configuration, feature flags and experimentation) — implemented.** Seven
`cfg_*` tables in `plt01` under the same forced RLS, a typed configuration registry with
validation and tenant/brand/location inheritance, append-only value versions with rollback and
preview, feature flags with arbitrary targeting attributes and basis-point rollout, kill switches
that outrank every rule, deterministic experiment assignment with recorded exposures, and a
single-read bundle for mobile, kiosks and devices. Proven: isolation checks 14-20, each
mutation-tested; 32 evaluation unit tests that need no database; 34 integration tests.

Two tables are insert-only in the privilege layer — `cfg_values` and `cfg_exposures` — so a
published value cannot be rewritten and a recorded exposure cannot be revised. That is the
mechanism behind "every change is reversible" and "repair without history rewrite", and checks 19
and 20 prove the grants rather than trusting the migration's comment.

Known gaps, deliberate:

- **No experiment metrics, guardrails or decision records** (part of PLT-02-R04). They need a
  metrics pipeline that does not exist; a decision record with no measurements behind it would be
  worse than the gap.
- **No approval workflow** (part of PLT-02-R05). Approval needs an authenticated principal and
  nothing authorizes an approver yet -- MOD-007 can say who someone is, and MOD-008, which
  would say what they may approve, is unbuilt. TSD paragraph 1020's change control
  for financial and security flag changes in production is therefore not satisfied by anything
  here; this service runs in local, development and staging only.
- **No outbox and no published events.** `configuration.changed`, `feature_flag.evaluated`,
  `experiment.exposed` and `experiment.completed` are named in the TSD and nothing consumes them
  yet. An outbox nothing drains is a table that grows.
- Targeting attributes are flat strings compared for equality. The seven dimensions PLT-02-R02
  names are all expressible that way; set membership and ranges are not, and would need a richer
  match format.

**MOD-015 (PLT-03 plans, subscriptions, metering and invoices) — implemented.** The plan
catalogue lives in `plt01_platform` with no runtime-role grant; nine `bil_*` tables live in
`plt01` under forced RLS. Working: plan versions with prices and entitlement limits, subscriptions
that snapshot the plan they were sold on, the trial/dunning/grace/suspension/reactivation
lifecycle, plan changes with day-count proration, entitlement grants and checks, idempotent
metering with late events and corrections, quotas with overage or hard stop, and issued invoices
with lines, tax, partner revenue share and credit notes. Proven: isolation checks 21-26, each
mutation-tested (13 mutations, every one caught by its own check); 74 domain unit tests that need
no database; 50 integration tests.

Three decisions in this module are worth knowing before extending it:

- **Every amount is an integer in minor units.** No column and no function is floating point.
  Rounding is half away from zero, so a credit and the charge it reverses have the same
  magnitude, and `money.allocate` splits by largest remainder so a divided total still sums to
  itself. The conventions are stated at the top of `app/billing/money.py` because the sources
  state none; proration is actual days over actual days in the period.
- **A published plan version is immutable, by privilege.** `saas_prices` and
  `saas_plan_entitlements` carry no UPDATE grant at all and `saas_plans` carries a column-level
  UPDATE on its three lifecycle columns only. Re-pricing means a new version; subscriptions
  already sold keep their snapshot, so an old invoice stays reconstructible.
- **An invoice has no draft state.** The five ledger tables are insert-only for both runtime
  roles, so a row exists only once issued and a correction is a credit note rather than an edit.

Known gaps, deliberate:

- **No payment provider and no stored payment methods.** Taking a card is real money and the
  owner reserves that. `payment_failed` and `payment_recovered` are the commands an integration
  would call, and they work today against synthetic input.
- **No tax engine.** `issue_invoice` takes a rate; rates are jurisdictional and the sources state
  none. A credit-balance invoice carries no tax rather than a negative one.
- **No cost or gross-margin view** (PLT-03-R07). It needs cloud, AI, messaging and support cost
  feeds that do not exist here.
- **No outbox and no published events**, as in MOD-005.
- `change_plan` takes the tenant's current usage from the caller. The modules that own those
  counts are not this one, so it does not guess at them, and it never deletes anything to make a
  smaller plan fit — it refuses, lists the breaches, and proceeds only when acknowledged.

**MOD-007 (IAM-01 identity, authentication, passkeys and device sessions) — implemented
server-side, and reviewed.** A third plane: schema `iam`, role `veyro_iam_app`, seven tables, all
tenant-bound under forced RLS. Working: identities linked across tenants by a bare `person_id`,
scrypt passwords, recovery codes, device inventory with confirmation, trust and revocation, bearer
sessions stored only as a SHA-256 digest, rotation with stolen-token reuse detection, assurance
levels with step-up against **verified** credentials, lockout, answerable risk challenges, and an
insert-only authentication log. Proven: isolation checks 27-29, each mutation-tested (15
mutations, every one caught by its own check); 55 domain unit tests including all 18 published RFC
4226 and RFC 6238 vectors; 52 integration tests.

**This module was independently reviewed twice and failed twice.** Round one found a complete
account takeover and ten other defects. Round two confirmed all eleven fixed and found two more
in the *new* code -- both in the challenge and recovery paths, one of them in the flow written to
close a round-one finding. The regressions in `ReviewRegressionTests` are named for the attacks,
not the fixes. Six defects are worth carrying forward as rules, because each is a shape that
recurs:

- **Never believe a caller's description of itself.** `/auth/step-up` took a list of factor
  *names* and granted the level they implied, so `{"factors": ["passkey_hardware"]}` bought the
  highest assurance level with nothing presented. It now takes credentials and verifies them, and
  a session records which factors actually opened it.
- **A tenant header is not an authentication.** Password changes, recovery-code issuing and
  session listing were open to anyone holding the tenant UUID. Every identity-scoped route now
  resolves a bearer token and checks it belongs to that identity.
- **A control that commits anything before it refuses is not a control.** The risk challenge
  wrote the device row and then challenged, so sending the same login twice walked past it. A
  device is confirmed only by a login that needed no challenge or by one whose challenge was
  answered -- and there was no endpoint to answer one at all, so it was unanswerable by an honest
  user and free to skip for an attacker.
- **A refusal must not say why.** A locked identity answered 423 in under two milliseconds while
  everything else answered 401 in fifty, which identified every registered address in five
  requests. All refusals now cost one scrypt and return the same 401.
- **Bind a challenge to what it is about.** The login challenge recorded no device, so answering
  it confirmed whichever device had been seen most recently -- an attacker holding the password
  kept theirs newest by retrying, and the victim's own answer whitelisted it. `iam.challenges`
  now carries `device_id` and the answer confirms that one.
- **Verify, decide, then consume.** A step-up burned the recovery code it had verified before
  deciding whether to accept, so a refusal destroyed it for nothing -- and a recovered user, who
  cannot reach level 2 from recovery codes alone, lost one per attempt at a reset they could
  never complete. A session opened with a recovery code may now set a password directly, which is
  what recovery is for.
- **A remedy is new capability, so review it as such.** That recovery allowance reached
  `issue_recovery_codes` as well, and there it was a backdoor: a stolen recovery session minted
  ten fresh codes with no password, and those codes survived the owner's own password reset. The
  allowance now applies to `set_password` only, which is self-limiting because it revokes every
  session including the one that used it.
- **A check belongs where every caller passes.** The identity-status read sat in
  `resolve_session`, so `/auth/rotate` and `/auth/step-up`, which resolve a token directly, let a
  suspended identity refresh indefinitely. It lives in `_session_by_token` now.
- **A session's lifetime follows what it can do, not what it scored.** A recovery-code session is
  level 1 but can reset a password, so `policy.session_expiry` gives it the elevated window and
  `policy.window_is_fixed` stops rotation renewing it.

Things to know before extending it:

- **A failure path must commit before it refuses.** `tenant_scope` rolls back when the block
  raises, so an exception thrown inside it takes the failure's own evidence with it. Every
  recording failure path returns its error and `_settled` raises it after the commit. Two places
  raise inside the block on purpose, where nothing should survive the refusal.
- **Recovery has its own lockout budget**, separate from the password one. Honouring the password
  lock here would shut the only door left, and sharing one counter could not do both jobs.
- **AAL-3 is unreachable today**, and `/auth/require/*` says so in a `reachable` field rather than
  implying otherwise. It needs a hardware authenticator, which needs WebAuthn verification.

Known gaps, deliberate:

- **Passkeys are not an authentication factor.** Enrolment stores the credential, the public key
  and the signature counter, and the clone check on that counter is real and revokes on sight. The
  WebAuthn signature is not verified — CBOR, COSE and ECDSA, and hand-rolling it is how
  authentication bypasses get written. `VERIFIABLE_FACTORS` is the list of what any path accepts
  as proof, and a passkey is not in it.
- **No TOTP enrolment.** The algorithm is implemented and RFC-tested; storing a reversible shared
  secret needs a vault this repository does not have.
- **No OIDC/SAML federation and no SCIM** (IAM-01-R04).
- **No rate limiting.** Lockout bounds guessing against one identity -- on login, on recovery and
  on the re-authentication paths, each metered through `_verify_presented` -- but nothing bounds
  request volume. An attacker who knows an address can still lock its owner out, and a refused
  bearer token writes no audit row, because recording one would let anyone grow an insert-only
  table without limit. Both want the same missing limiter.
- **`iam.challenges` is never swept.** One row per `/auth/require/*` call and per challenged
  login, with no DELETE grant by design. Harmless at this size; it wants a worker, not a grant.
- **Metering cuts both ways.** Now that the re-authentication paths count failures, somebody
  holding a stolen session token can lock the victim out of their own login with five wrong
  passwords at `/auth/step-up`, and lock their recovery budget with five wrong codes. That is the
  usual lockout tradeoff and the right call, but it is a real denial of service and it belongs
  here next to the one above.
- **Registration is open.** Anyone holding the tenant UUID can create an identity in it. That is
  the same unauthenticated-header problem above, not a separate one.
- **The identity plane is a schema, not a separate database.** TSD paragraph 1151 says "Product
  PostgreSQL"; this repository provisions one cluster. The privilege boundary is real and checked
  in both directions; the physical separation is not there.

**MOD-008 (IAM-03 authorization, roles, approvals and audit) — implemented, and reviewed.**
Eleven more tables in `iam`. Working: roles with explicit permission lists, assignments scoped to
tenant, brand or location and optionally expiring, allow/deny/mask policies, a permission
simulator, approvals with thresholds and separation of duties, access reviews, and a hash-chained
audit log. Proven: isolation checks 30-32, each mutation-tested (13 breaks); 7 tamper tests
against the chain; 75 domain unit tests with no database; 32 integration tests.

**Nothing outside MOD-008 is gated yet.** `require` is the only way anything asks whether a
caller may act, and the only callers are MOD-008's own routes. The catalogue's `tenancy.*`,
`config.*` and `billing.*` permissions are real entries that nothing checks, so MOD-004, MOD-005
and MOD-015 are still open to anyone holding a tenant UUID. Wiring them is the next change and it
is deliberately separate: it touches every surface in the product and wants its own review.

The design decisions worth knowing:

- **Permissions live in code** (`app/authorization/catalog.py`), not in a table. TSD paragraph
  1281 names Permission as an authoritative entity and that module is it. A permission is a fact
  about what the software can do; a per-tenant table would let two tenants disagree about which
  permissions exist with only the code able to settle it. `iam.role_permissions` references the
  names and a CHECK constrains their shape.
- **There is no wildcard**, in the grammar or the evaluator. `billing.*` is refused by the
  catalogue at the API and by a CHECK at the table.
- **`catalog.action_class` decides what needs a stepped-up session**, written per permission
  rather than derived, because each one is a judgement. A wrong `routine` is a real defect: a
  test caught `config.flag.write` classified too low against TSD paragraph 1020. `privileged`
  means level 3, which needs a hardware factor MOD-007 cannot verify, so break-glass support
  access and AI acting for a member **cannot be exercised in this build at all** — deliberately.
- **The audit chain detects editing, not truncation.** It catches any change to an entry, a
  deletion from the middle, a rewritten anchor or link, and a deletion from the end that forgets
  the head. It does **not** catch truncation from the end by somebody who also moves the head,
  because every value the verifier compares lives in the database that actor already controls.
  Closing it needs the head digest published somewhere the database cannot reach, on a schedule;
  there is no such place here. Found by tamper-testing, not reasoned about afterwards.
- **A brand-scoped grantor cannot delegate at location granularity** inside their own brand:
  `assign_role` builds its target with no brand, so a location-scoped grant fails the
  scope-coverage check. Fail-closed, and it will surprise somebody.
- **Approval policies are tenant-wide.** IAM-03-R05 names location among its dimensions and the
  schema briefly carried scope columns for it — never selected, never matched, so a
  location-scoped policy would have applied everywhere while reading as though it did not. The
  columns are gone and this is the gap.

**The review found seven defects and four of them were the same mistake in different clothes:
believing the caller.** Worth carrying forward as rules:

- **An unknown attribute must not grant, and must not excuse.** `Policy.matches` is asymmetric by
  effect: an allow needs every attribute it names to be present and equal, a deny or a mask fires
  unless the request positively contradicts it. The first version treated both alike, so leaving
  a field out of the request turned off the deny protecting a minor's record. The reasoning
  behind it was an allow-shaped example applied to both.
  **The operational consequence, which is the correct trade and still a surprise:** a deny policy
  whose attribute nobody supplies denies the action outright. A caller gated by one has to start
  sending the attribute -- `is_minor=false` -- rather than omitting it. Fail-closed, and it will
  break existing callers the day a deny policy is written for an action they use.
- **Derive a scope, never accept one.** A brand-scoped manager reached another brand's location
  by sending their own brand id beside it, and the simulator confirmed the escalation. A
  location's brand is now looked up through `tenancy.brand_of_location`, and `resolve_scope` is
  the only sanctioned way to turn request input into a `Scope`.
- **Terms are snapshotted when a request is made.** Re-deriving them at decision time let
  somebody holding `authz.policy.write` switch separation of duties off for a request already in
  flight and then approve their own. `policy_for` also now combines every applicable policy into
  the strictest terms rather than picking the highest threshold, which are the same only until a
  lenient policy sits above a strict one.
- **A grantor may only grant what they hold** -- when granting a role, when creating one, and
  when editing one. Each is a way of handing out a permission, and guarding only the first left
  the next two open: an actor holding just `authz.role.write` rewrote a role it already held to
  include refunds. `_refuse_escalation` is the one rule, applied in all three places.
- **A refusal that must be recorded cannot be raised from inside the block that recorded it.**
  `tenant_scope` rolls back on a raise, so three denial paths wrote an audit row and threw it
  away -- an attempted privilege escalation, a refused approval request, and every attempt to
  approve one's own request. `_settled` is the pattern, and MOD-007 has the same helper for the
  same reason, which is why it is a rule here rather than a third fix: **anywhere
  `_append_audit` precedes a refusal, return the error and raise it outside.**
- Two smaller ones with the same shape as MOD-007's: a stored column outside the digest
  (`on_behalf_of`, the field recording an agent acting as a member) was editable undetected, and
  a column implying a control nobody implemented (`delegated_from`, approval-policy scope) is
  worse than no column. Both are gone or covered.

Known gaps, deliberate:

- **The bootstrap.** `authz.bootstrap` creates a role holding everything and grants it to the
  caller, refusing once any assignment exists, under a lock that survived ten concurrent
  attempts. It is only as strong as the surface around it, and `X-Veyro-Tenant` is an
  unauthenticated claim — anyone who knows a tenant id can register an identity and bootstrap it
  if nobody has. **When the header stops being a claim, this function needs revisiting with it.**
- **Field masking is computed, not applied.** `Decision.mask` exists and is tested; no read path
  calls it, because no read path is gated yet.
- **No outbox.** IAM-03's five events are written to `iam.audit_events` and published nowhere.
- **Retention control is not implemented.** IAM-03 asks for write-once, integrity-protected *and*
  retention-controlled; the third is a policy about deleting old records on purpose and has no
  implementation here.

**Next.** Gate the product: make MOD-004, MOD-005 and MOD-015 routes call `require`, which is
what turns the catalogue from a list into a control. Then MOD-009 onward.

Module ids are in `tools/mission_runner/module_catalog.json` and are not the TSD's section order.
MOD-006 (Compose Multiplatform qualification) is unbuilt; MOD-007's dependency on it is a
client-side proof that the server plane does not need.

Finish a module's real requirements and tests, then move on.
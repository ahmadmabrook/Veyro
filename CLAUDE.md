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
  privacy/              MOD-009: classification, consent, retention, dsar decide; service.py (I/O)
  events/               MOD-010: catalog and dispatch decide; service.py is the outbox and relay
  observability/        MOD-011: catalog, objectives and ratelimit decide; metrics.py records,
                        service.py does the rest of the I/O
  integrations/         MOD-012: contract, lifecycle and sync decide; service.py spans both
                        planes and snapshots the definition into the install
  notifications/        MOD-013: templates, preferences and delivery decide; service.py
                        authors the message and never sends it
  people/               MOD-014: visibility.py masks, dedup, merge and timeline decide;
                        service.py takes the gate's masked-field list as a required argument
  catalog/              MOD-016: pricing.py, promotions.py, products.py and bundles.py
                        decide; service.py redeems a coupon in the resolution's transaction
  errors.py             the five service errors every module's service raises
backend/migrations/     platform/, tenant/ and product/ SQL, applied in that order
backend/tests/          unittest suites; tests/sql/isolation.sql is the isolation proof
backend/scripts/        verify_db.sh rebuilds the database and runs the isolation suite
knowledge/              decisions and module notes
tools/                  governance and lint tooling (see "Tooling that still earns its place")
```

Sources of product scope and architecture: the two `.docx` baselines and
`veyro-product-experience-design/`, pinned by SHA-256 in `PROJECT_INDEX.md`. The owner edited the
EIP and TSD on 2026-11-13; those revisions are **adopted** — committed, and re-pinned together
with `governance/registry.json`'s `index.sha256`, under §5 of the delegation record, which names
the two digests the re-pin binds. The Blueprint and the design directory keep their 2026-10-15
pins.

What that adoption does **not** mean: neither revision is independently certified, and the check
behind it was structural — document identity, and survival of the functional content by probe —
not a line-by-line review of 2,566 changed paragraphs. The deletions are process scaffolding
(Document Control blocks, the Development Constitution table, the DC-16 apparatus); the
requirement text the implementation reads is unchanged, which is what the probes checked. Re-pin
the two files together or not at all: a pin whose witness disagrees with it is worse than no pin,
and `governance_check.py check --root .` is what catches the disagreement.

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

**The product is gated.** Every tenant-plane route -- the organization hierarchy, configuration
and flags, subscriptions, metering and invoices, and MOD-009's privacy surface -- goes through
`permit`, which calls `authz.require`, which asks authorization and assurance together and writes
the denial to the audit log itself. `backend/tests/test_gating.py` is the suite that says so, and
it is written as the attacker rather than the user: it sweeps the routes with no session (422),
with a session holding nothing (403), with a read permission against a write route, and with a
permission held on a session too weak for it.

A sweep is a sample, though, and a sample cannot prove a negative: a route added without a
`permit` call is invisible to it, because nothing ever calls that route. `GateCoverageTests` reads
`main.py` with `ast` instead and requires every route to do one of three things -- ask the gate,
scope itself to the caller's own identity, or appear in `UNGATED` with a written reason. That
list is where the open surfaces are enumerated, and adding to it is meant to be uncomfortable.

**The platform plane is deliberately still open, and that is wider than it sounds.** `/platform/*`
provisions tenants, moves them through their lifecycle and reads their history, and none of it
asks for anything. Anyone who can reach that surface can create a tenant and bootstrap it -- and
can **suspend or archive a tenant that already exists**, which is denial of service against a live
customer, not merely unwanted signup. Authenticating it is a different problem from authorizing a
tenant's own users: there is no platform identity to be yet, and inventing one here would be
inventing product. **Nothing should be deployed anywhere this surface is reachable.**

Two consequences to know before touching a product route:

- **A caller needs a session, and the session needs a role.** A tenant is unusable until somebody
  bootstraps it, which is one call and self-closing. `backend/tests/support.py` is how the suites
  get an owner; it builds one through the service layer rather than HTTP, because the HTTP path
  spends a dozen scrypt hashes per tenant and that is most of the suite's wall-clock.
- **Several writes need a stepped-up session as well as the permission**, because
  `catalog.action_class` marks them `financial`: every billing write, flag and configuration
  changes, and the hierarchy writes. Holding the permission on an AAL-1 session is not enough.
  That is the point, and it will surprise a caller that read only the permission list.

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
**MOD-009 (SEC-01 security, privacy, compliance and consent) -- implemented, gated, and
reviewed.** Nine `sec_` tables in `plt01` under the same forced RLS, and `app/privacy/` beside
them: a data classification registry, consent with versioned documents, retention with legal
hold, the data subject request workflow, and an incident record. Twenty-five HTTP routes, every
one through `permit`. Proven: isolation checks 33-38, each mutation-tested -- 40 mutations, 39
caught by the check that guards the thing broken and one (dropping a policy outright) caught by
the seed failing closed, which is the property but not a check. Two of those 40 first came back
"caught" for the wrong reason: one broke the seed, and one named a constraint that does not
exist, so the ALTER errored and the mutation never ran at all. Both were re-run correctly.
Also: 62 domain unit tests with no database; 30 service integration tests; 11 reachability tests
against the live catalogue; 18 API tests.

**This build cannot fully erase a person, and that is a tested disclosure rather than a
silence.** Every `plt01` column naming a subject has neither UPDATE nor DELETE for any runtime
role -- the financial ledger, published configuration, recorded exposures and MOD-009's own
evidence -- and three `iam` tables likewise: the audit chain, the authentication log and
approval decisions. Each is correct on its own terms: insert-only is what makes the ledger
reconstructible and the audit chain tamper-evident. Together they mean erasure reaches the
identity plane's mutable tables and nothing else. TSD section 21.6 anticipates exactly this and
points at crypto-shred, which needs a key vault this repository does not have.

So the deliverable is a registry rather than a routine that pretends. `SUBJECT_COLUMNS` in
`app/privacy/classification.py` declares, per subject-bearing column, what erasure does to it and
why, in five mechanisms (`delete`, `anonymize`, `covered`, `pseudonymize`, `unreachable`), and
`test_privacy_reachability.py` checks it against the live catalogue **in both directions**: a new
table carrying a subject id fails until somebody declares it, and a declaration that disagrees
with the grants fails too -- `anonymize` needs UPDATE behind it, `unreachable` needs the absence
of both. `deletion_is_complete()` returns False, `settle()` names the residue, and
`test_this_build_cannot_fully_erase_a_subject_and_says_so` fails if the disclosure ever lapses.

**Three independent reviewers worked this module in parallel -- the schema, the Python, the gate
-- and all three returned CHANGES_REQUESTED.** Seven blocking defects between them, and two of
the three found the same one. Each is carried forward below as a rule, because each is a shape
that recurs:

- **A control consulted once is a control with a window.** Legal holds were read at the DSAR's
  legal-check step and never again. `ready` is durable with no expiry, and litigation ordinarily
  starts *after* a request is queued -- so a correctly-served preservation order was ignored and
  the erasure reported `completed`. `fulfil_dsar` re-reads holds now, along with three other
  facts, and writes nothing until all four pass. Found by two reviewers independently.
- **A locator that exists is not a locator that matched.** `subject_id` carries no foreign key --
  the planes are separate -- and nothing resolved it, so an erasure against an unknown id updated
  zero rows on every target, recorded `done / 0` for each, and completed. The realistic input is
  a caller supplying a `person_id` where an `identity_id` was meant. This is the same defect as
  the `locate_by` one fixed during development, one layer up: there, a static test proved the
  locator column *existed*. Nothing proved it *matched*.
- **A control that commits anything before it refuses is not a control** -- MOD-007's rule, hit
  again. `fulfil_dsar` committed `status = 'fulfilling'` and *then* refused the four non-deletion
  request types. `fulfilling` exits only to `completed` or `refused`, so attempting to answer an
  access request -- the commonest DSAR there is -- made it permanently unanswerable.
- **Derive-don't-accept applies to every field that makes a claim, not just the obvious one.**
  `consent_subject` charged the stronger permission for naming another *subject* and said nothing
  about `guardian_subject_id`, which is the entire control behind `requires_guardian` and has no
  foreign key to check it, or about `source`, where `staff_entry` and `paper_import` assert that
  a signed document exists off-system. A minor on an AAL-1 session satisfied their own guardian
  requirement by typing a UUID, and wrote a row that read as a scanned waiver. All three fields
  now route to `privacy.consent.record_on_behalf`.
- **Evidence with nobody's name on it answers nothing.** Releasing a legal hold -- the single act
  that un-blocks destruction of preserved evidence -- recorded no actor anywhere in the system:
  `veyro_cp_app` holds nothing in `iam`, so MOD-008's audit chain is out of reach, and the row
  was the only possible record. Retiring a processing purpose was the same. Both now carry an
  actor and a correlation id, and the constraint requires them.
- **A CHECK cannot see what a row used to be.** `sec_legal_holds` could be released twice with
  different dates, or set back to NULL so it read as never lifted -- both rewrite how long
  deletion was suspended, which is why the row is kept. A trigger is the only thing that can see
  `OLD`, and this is the one place in the schema that needs one.
- **A mutation sweep proves the tables it names, and nothing else.** My own sweep broke 16 things
  and caught 16, and a reviewer then removed FORCE RLS from `sec_legal_holds` and watched the
  suite report every check passing while the migrator read every tenant's holds. Seven of nine
  tables had no FORCE evidence and eight of nine no `WITH CHECK` evidence. Checks 17, 22 and 28
  already swept `pg_class` for exactly this reason and MOD-009 regressed to a per-table list.
  **Sweep the catalogue; a per-table list has to be edited when a module adds a table, and that
  edit is the moment an unprotected one slips through.**
- **A checker with a blind spot in the shape the next line will be written is worse than none.**
  `GateCoverageTests` filtered on `ast.FunctionDef`, so an `async def` route -- FastAPI's
  ordinary idiom, already used in this file -- was neither gated nor listed, and all three
  coverage tests passed.

Also found and fixed: no id anywhere in MOD-009 was shape-checked, so eight of eight id-bearing
routes answered 500 with a database exception rather than 422; `plan()` derived each step's
mechanism from the request type, advertising `delete` for seven targets the executor anonymizes;
a consent record could cite a version belonging to a *different* definition (now a three-column
foreign key); `data_classes` admitted unknown elements; `received_at` was unbounded, so the
caller set the regulator-facing deadline; free-text `resource_type` defeated the live-policy
unique index. Every one has a named regression test.

**Three reviewers worked this module -- the schema, the Python, the request path -- and all
three returned CHANGES_REQUESTED. Ten blocking defects**, and three of them were the same
mistake: a value returned to the caller and never recorded. Carried forward as rules:

- **A docstring is not an attribution.** `release_run` validated its reason, returned it,
  discarded it, took an `actor_id` it never used, and published nothing -- while both its own
  docstring and the route's said it was recorded. There was nowhere else it could land: MOD-008
  audits denials and not allowed actions, and `veyro_cp_app` holds nothing in `iam`. This is the
  act that puts a connector which burned its entire retry budget back in front of a third-party
  provider, and it resets the attempt count, so the row afterwards read as a fresh run with a
  stale error and no trace of a decision. `finish_run` and `record_reconciliation` were the same
  shape: the two routes that write a run's *results* recorded nobody, so the only name on a
  fabricated "synced four million records" was the name of the party that did **not** make the
  claim -- `integrations.sync.run` is routine and tenant-wide, so any holder can settle any
  running run. `int_connector_runs` now carries `settled_by`, `released_by` and `reconciled_by`
  with their correlation ids, and the reconciliation's own totals.
- **A guard widened past its sibling's is a guard removed.** `finish_run` settles only a
  `running` run and its docstring explains why; `fail_run` accepted `running` **or** `failed`.
  Since `fail_run` does not increment the attempt count -- `retry_run` does -- a caller
  reporting the same failure twice froze `attempts` at one for ever: every report produced the
  same verdict, pushed the backoff out again, and the run **could never reach `dead`**. An
  operator reading the dead-letter board saw it clean while a connector failed continuously,
  which is MOD-010's `outbox_health` finding in this module's clothes.
- **A field on the wrong body is an escalation.** `advance_cursor` took a `conflict_policy`,
  which handed the routine, AAL-1 `integrations.sync.run` permission the decision that
  `/integrations/cursors/policy` charges a financial, stepped-up `integrations.sync.reset` for.
  Since the default is `manual` -- chosen precisely because it refuses to pick a side -- the
  machine permission was the one actually *choosing* whether a provider's copy may overwrite a
  tenant's member records. The field is gone; `set_conflict_policy` now creates the cursor so
  the policy is settable before any sync, which is what made the shortcut tempting.
- **`coalesce` replaces NULL, not the empty string.** Three blank strings erased the fallback,
  the reconciliation procedure and the exit plan from a **live critical** install -- the three
  things paragraph 3033 requires in writing before it may carry traffic -- with the same
  permission that wrote them and no refusal anywhere. "A control consulted once is a control
  with a window", which is MOD-009's legal-hold finding again.
- **Bound an integer at the boundary, or psycopg does it with a 500.** `max_attempts`,
  `records_read`, `records_written`, `conflicts` and the reconciliation counts were unbounded --
  and `NumericValueOutOfRange` is a `DataError`, not the `CheckViolation` the handlers caught.
  MOD-010's `SubscriptionBody.max_attempts`, 230 lines up the same file, is
  `Field(ge=1, le=100)`.
- **An in-flight lock applies to every writer of that status.** `start_run` caught the unique
  violation from `int_connector_runs_one_in_flight`; `retry_run` and `release_run` set the same
  status and did not. Reachable with no concurrency at all, because `start_run` looks at the
  connection and the install and never at other runs: start, fail, start again, retry the first
  -- a 500, and the first run permanently unretryable while the caller is told "try again".

Things worth knowing before extending it:

- **Tombstones are per-column, not a generic NULL.** `identities_has_an_identifier` forbids
  nulling both contact columns, and `salt`, `secret_hash`, `token_hash` and `nonce_hash` are
  `bytea` under `octet_length` checks. Erasure *replaces* an address with a per-row tombstone
  rather than emptying it. `_CLEAR_SQL` is that mapping and every entry answers a real constraint.
- **`coalesce` in a CHECK is load-bearing.** `length(btrim(NULL)) > 0` is NULL and a CHECK passes
  on NULL, so `sec_legal_holds_release_reasoned` admitted the exact row it exists to refuse.
  Check 37 caught it during development; a reviewer then traced all 29 `sec_` CHECKs and found no
  second instance.
- **An interrupted erasure resumes.** `check_ready_to_fulfil` accepts `fulfilling` as well as
  `ready`, because every clear expression is idempotent or writes a fresh tombstone over one
  already written, and the evidence trail is insert-only so both attempts stay visible. Without
  it a transient outage on the identity plane stranded the request for ever.
- **No deadline is defaulted.** The TSD says "within DSAR SLA" and never states one, so
  `response_days` is required -- the same precedent as MOD-015's tax rate.
- **There is no `privacy` audit category.** IAM-03-R06's seven names are a CHECK on
  `iam.audit_events`, so a permission categorised `privacy` would pass the catalogue and then
  fail at the moment a denial had to be written. The fifteen MOD-009 permissions reuse the
  existing categories.
- **`privacy.incident.record` is routine on purpose**, and it is the second entry ever added to
  `ROUTINE_BY_DESIGN`. An incident is recorded during an incident, and the incident may be that
  authentication is unavailable.

Known gaps, deliberate:

- **No crypto-shred, so erasure is incomplete** -- the disclosure above. Closing it needs a key
  vault and per-subject key material, which is a different module's work.
- **Only a deletion has an executor.** Access, portability, correction and restriction can be
  opened, verified and legal-checked; fulfilling one is refused with a reason and leaves the
  request where a human can act on it. An export needs an object store and a residency decision,
  both unmade, and `_perform` recording "exported" with no file would be evidence of work never
  done.
- **No subprocessor propagation.** SEC-01-R07 asks a DSAR to reach subprocessors; there are none
  wired up.
- **No retention sweep.** `retention.may_delete` decides and nothing calls it on a schedule --
  the same missing worker as MOD-007's challenge sweep. `may_delete` also passes
  `subject_id=None`, so under the (correct) hold asymmetry one live per-subject hold blocks
  scheduled expiry of that resource type for every subject. Fail-closed, and a real limitation
  the day a sweep exists.
- **No breach-notification clock.** `sec_incidents` records whether personal data was involved,
  which is what starts one; nothing computes a deadline or notifies anybody.
- **`privacy.consent.read` is routine and tenant-wide** over health and biometric consent history
  including guardian identifiers, while `member.health.read` beside it is `biometric_sensitive`.
  Defensible -- consent state is what a kiosk checks before letting somebody train -- and worth
  revisiting when a read path applies `Decision.mask`.
- **Id validation is MOD-009-wide, not repository-wide.** `require_uuid` guards every privacy
  route; `POST /brands` and its siblings still answer 500 to a malformed id. Same one-line fix,
  not done here because it is not this module.
- **No outbox and no published events**, as in MOD-005, MOD-015 and MOD-008.

**MOD-010 (DAT-01 domain events, event bus and operational timeline) -- implemented, gated and
reviewed.** Five `evt_` tables in `plt01` under the same forced RLS, `app/events/` beside them,
and twelve HTTP routes. Working: a transactional outbox, a canonical envelope, a code-resident
event catalogue with compatibility and payload validation, fan-out to per-consumer deliveries,
at-least-once delivery with deduplication, per-consumer retry with exponential backoff,
dead-letter quarantine with attributed release, and controlled replay that suppresses side
effects by default. Proven: isolation checks 39-43, mutation-tested in two rounds -- 33
mutations before the review and 26 after it showed that check 42 proved almost nothing, all 59
caught by the check that guards what was broken; 31 domain unit tests with no database; 45
service integration tests; 17 API tests that drive the *other* modules' routes and then read the
outbox.

**Three reviewers worked this module too, and all three returned CHANGES_REQUESTED.** Seven
blocking defects. Carried forward as rules:

- **A decision made once per job and applied per item is not the decision it claims to be.**
  `run_replay` read one subscription with `LIMIT 1` and used its `replay_safety` for every event
  in the job. It fails in both directions and which one you get depends on the query planner: a
  consumer `safe` for one type and `suppress` for another had its suppress-class events
  delivered under the default policy -- TSD paragraph 200 defeated by naming a second type, with
  `suppress` recorded on the job and no reason written -- or, with the rows in the other order,
  the whole job suppressed including the type the operator asked to rebuild. A `suppressed`
  delivery row is terminal and every later insert is `ON CONFLICT DO NOTHING`, so nothing in the
  module could undo that. **I flagged the `LIMIT 1` in the reviewer's brief as the thing I was
  least sure about; it was worse than I thought in both directions.**
- **A lookup that proves something exists does not authorise what you do next.** The same
  function queued events of types the consumer had no subscription to, because the events query
  filtered on the job's caller-supplied list while the subscription check was satisfied by one
  match. A holder of the replay permissions could route any event type to any consumer name,
  bypassing `evt_subscriptions` -- the table that is supposed to *be* the routing authority.
- **A failure path inside a batch loop must not raise.** `_record_failure` raised `NotFound`
  when a delivery had no matching subscription. That propagated out of the relay, so the failure
  counted no attempt, wrote no error, never dead-lettered, and aborted every healthy delivery
  behind it -- permanently, since the poison row sorts first. `outbox_health` then showed a
  growing backlog with zero dead letters, pointing an operator away from the cause.
- **A lease is not a lock, so the writer has to re-check.** The success path wrote `handled`
  with no `status = 'pending'` guard and `attempts = attempts + 1`, and the claim only pushed
  `available_at` out by the first backoff -- two seconds. A handler slower than that had its row
  settled by another relay and then overwrote the settlement, leaving a delivery reading
  `handled` beside a live quarantine row and an attempt count past its budget.
- **`events.event.read` was a lateral read path around four other modules' read permissions.**
  One routine permission returned `evt_outbox.payload` from `/events/{id}` and
  `/events/aggregate`: a reviewer was refused 403 by `/privacy/consent/history` and
  `/privacy/requests`, then read who consented to what and who filed which data subject request
  out of the event plane. `get_event` and `aggregate_history` no longer return payloads at all;
  a consumer still gets one on the delivery path, which is what a handler is for.
- **The restricted-field rule checks names, and a value can carry anything.**
  `cfg_exposures.subject_id` is caller-chosen free text at AAL 1, and a reviewer put an email
  address, a date of birth, a national id and a lab result in it -- then read it back out of the
  outbox. `experiment.exposed` now carries `subject_hash`, because an event is the one store
  this build cannot erase from.
- **Applying a lesson at one level does not apply it at the next.** Check 39 sweeps `pg_class`
  and `pg_policies` because MOD-009's review taught that; check 42 then proved the *column*
  grants with a hand-written list of names, and ten distinct grant-widenings passed 43/43 --
  including UPDATE on `evt_outbox.event_type` for the relay role, which re-routes a committed
  event to a different consumer set and is forging an event from every consumer's point of view.
  Check 42 now compares the whole column list against the catalogue for both roles. **In this
  module the column-scoped grant *is* the integrity mechanism: there is no DELETE and no hash
  chain behind it.**

Also found and fixed: the delivery primary key -- which the module calls the deduplication --
had no test, and `ON CONFLICT DO NOTHING` with no conflict target stays valid SQL when the key is
dropped and silently stops deduplicating (the targets are named now); eight constraints, two
unique indexes and the registry foreign keys had no case in check 43; `veyro_cp_worker` was never
exercised behaviourally anywhere in the suite, so a policy carrying `OR current_user =
'veyro_cp_worker'` passed everything; `from_replay_job_id` was a parent reference with no foreign
key; a deactivated subscription could never be reactivated and the error said the opposite of
what was true; running a replay recorded no actor; `organization.updated` minted its own
correlation id so `/events/trace` could never join it to the decision that authorized it.

**And four of MOD-009's own reachability declarations turned out to be false**, found by
strengthening the test the MOD-010 review broke. `test_an_unreachable_declaration_is_actually_unreachable`
read `information_schema.role_table_grants`, which reports table-level grants only -- so for
every table whose UPDATE is column-scoped, which is most of them here, it passed vacuously. It
now asks `has_column_privilege` per column. `unreachable` means the database refuses the write;
the new `write_once` mechanism means a service writes it once under a predicate and no erasure
path clears it, which is the weaker and truer statement for five columns that claimed the
stronger one. The single exception is `sec_legal_holds.released_by`, which really is immutable --
by a trigger, which the test now looks for and requires the reason to name.

**`append_event` takes a connection, not a pool, and that is the whole module.** TSD paragraph
105 requires state and outbox to commit atomically, and the only way to mean it is to run the
append inside the caller's transaction on the caller's connection. Every other service here
takes a pool and opens its own `tenant_scope`; a version of this one that did the same would
read identically and guarantee nothing -- the state change would commit with the event in a
separate transaction that can fail on its own, or the event would commit and the state roll
back. **A pool-taking convenience wrapper around it is the bug**, which is why the one that
exists is called `append_event_in_its_own_transaction` and is correct only where there is no
state change to be atomic with.

**Events are declared in code, not registered in a table** (`app/events/catalog.py`), the same
deviation MOD-008 makes for permissions and for the same reason: an event type is a fact about
what the software emits, so a per-tenant registry lets two tenants disagree about what
`invoice.issued` means. Two controls ride on that:

- **A payload carries exactly its declared fields.** An undeclared key is refused at the
  producer, because an event is fanned out, archived and replayed -- a field that should not be
  in one is in more places than any other kind of mistake, and the deletion-reachability
  registry reaches none of them.
- **No declared field may be one MOD-008 classifies as restricted.** Checked at import, so the
  catalogue cannot name `national_id` or `health_notes` at all; carry an identifier and let a
  consumer that holds the permission read the value from the owning module. Contact fields are
  allowed, because a rule that forbade an email address in a confirmation event would be worked
  around rather than obeyed.
- **Compatibility is checked at import.** A later version may add fields and may not drop one:
  a consumer on v1 reads a dropped field as absent rather than wrong, which is the failure that
  surfaces weeks later. Enforcing it where somebody writes the change is worth more than
  enforcing it at a registration endpoint.

**The producers that can be atomic are wired; the ones that cannot are named.** The outbox is in
`plt01` under `veyro_cp_app`, so a write on another plane cannot share its transaction -- the
roles hold nothing in each other's schemas and are members of no role. Wired, in the same
transaction as the business write: `configuration.changed`, `experiment.exposed`,
`consent.granted`, `consent.withdrawn`, `data_subject_request.created`,
`data_subject_request.completed`, `security.alert.detected` and `organization.updated`.
**Declared and deliberately unproduced**: `tenant.provisioned` and the rest of the tenant
lifecycle (the registry is in `plt01_platform`), and every IAM-01 and IAM-03 event (`iam`).
Appending those in a second transaction would mean a tenant that exists with no event, or an
event for a tenant that does not;
`test_cross_plane_events_have_no_producer_and_the_plane_separation_is_why` fails the day
somebody gives those planes an outbox, which is when this note should be deleted.

Other decisions worth knowing:

- **Retry is per consumer, not per event.** `evt_deliveries` is one row per (consumer, event)
  with its own attempt count, and its primary key is the deduplication -- at-least-once means a
  consumer sees an event twice, and the row already saying `handled` is what makes the second
  time free. Counting attempts on the event would let one failing consumer exhaust the budget
  for every other.
- **Replay suppresses side effects unless somebody writes down why not.** Two statements have to
  agree: the job's policy (what this replay is for) and the subscription's `replay_safety` (what
  re-running that consumer does). A `suppress`-class consumer gets a `suppressed` delivery row
  rather than nothing at all, so the evidence says the event was considered and deliberately
  skipped. A `safe` consumer is delivered even under the default, because rebuilding a
  projection is the ordinary use of replay and a rule that stopped it would make the feature
  useless.
- **A replay queues deliveries; it does not call handlers.** A replayed event takes the same
  path as a live one, including the deduplication. A separate replay path that called handlers
  directly would be a second delivery implementation, and the two would drift.
- **The relay cannot forge.** `evt_outbox` grants UPDATE on the four dispatch columns and
  nothing else, so a relay marks an event sent and cannot change what it says. Check 42 proves
  it from the catalogue and by attempting the write.
- **`event_id` is globally unique and never caller-supplied.** TSD paragraph 3253 requires the
  first; the second is what makes it safe, because a cross-tenant unique index is otherwise a
  refusal one tenant can observe about another. The producer's own handle is `idempotency_key`,
  which is tenant-scoped exactly because it is caller-supplied.
- **Backoff is deterministic with no jitter**, stated as a tradeoff rather than hidden: identical
  failures retry in lockstep. `dispatch.backoff_seconds` is the only place to change it.

Known gaps, deliberate:

- **There is no transport.** TSD paragraph 271 names EventBridge, SNS, per-consumer SQS and an S3
  archive; none exists here and none is simulated, because a module writing "published to SNS"
  into a row while sending nothing is the fabricated-evidence shape this codebase has been bitten
  by. What is built is the half that must be correct whatever the transport turns out to be, plus
  a `Handler` protocol for it to implement. **There is no `POST /events/deliver` route** for the
  same reason: this process registers no handlers, and a route that found an empty registry would
  read as a control and do nothing.
- **No event archive and no retention.** Paragraph 3240 wants retention, compaction, PII
  minimization, encryption and regional routing. PII minimization is built (the payload rule
  above); the rest needs an object store and a residency decision, both unmade. **`evt_outbox`
  therefore grows without bound** -- it has no DELETE grant for any runtime role, which is right
  for evidence and means the archive is the thing that will eventually have to move rows out.
- **`feature_flag.evaluated` is declared and unproduced.** It is in the TSD's list for PLT-02,
  and one durable outbox row per flag evaluation is a write amplification nothing here can
  absorb. It wants sampling or aggregation, which is a decision about a metrics pipeline that
  does not exist.
- **Nothing drives the relay.** `dispatch_pending` and `deliver_pending` are called by a route
  and by tests; no worker loops on them, which is the same missing worker runtime as MOD-007's
  challenge sweep and MOD-009's retention sweep. Three modules now want it.
- **No consumers.** The subscription table routes to names, and no name in this build has a
  handler behind it.
- **One delivery can still run two handlers concurrently.** The claim is a lease, not a lock, so
  a handler slower than `_CLAIM_LEASE` can be joined by a second relay. That is within the
  at-least-once contract the schema documents, and the `status = 'pending'` guard means the late
  writer cannot corrupt the row -- but no consumer in this build has its own idempotency guard,
  so the contract is currently carried by the lease length alone.
- **`evt_outbox.payload` is residue an erasure cannot reach**, and it is declared by hand because
  the reachability sweep matches column names and the subject identifier is inside `jsonb`. Five
  wired producers put one there. No sweep will find the next one either, which is why
  `test_the_subject_identifiers_inside_jsonb_are_declared_by_hand` names it.

**MOD-011 (REL-02 observability, performance, capacity and FinOps) -- implemented, gated and
reviewed.** Eight `ops_` tables in `plt01` under the same forced RLS, `app/observability/`
beside them, and twenty HTTP routes. Working: a pre-bucketed metric store with a code-resident catalogue,
objectives (SLOs and performance budgets) evaluated over a window, a synthetic-check registry and
its insert-only result ledger, capacity forecasts with derived headroom, cost allocation with
corrections, budgets with burn thresholds and once-per-period alerts, a gross-margin read, and an
in-process rate limiter wired into the authentication surfaces and the gate. All four of the
TSD's REL-02 events are produced. Proven: isolation checks 44-48, mutation-tested in two rounds
-- 38 before the review and 87 after it showed what the first round had missed, 86 caught by the
check that guards what was broken and one (dropping a policy outright) caught by the seed failing
closed; 32 domain unit tests with no database; 51 service integration tests; 21 API tests.

**Three reviewers worked this module in parallel -- the schema, the Python, the request path --
and all three returned CHANGES_REQUESTED.** Thirteen blocking defects. Each is carried forward
below as a rule, because each is a shape that recurs.

- **A role that holds a grant gets a seat, in every module.** Every behavioural assertion in
  checks 44-48 ran as `veyro_cp_app`. PostgreSQL ORs permissive policies, so
  `CREATE POLICY ... FOR ALL TO veyro_cp_worker USING (true)` leaves the module's own policy
  intact, still exactly right, still the only one the catalogue comparison looks at -- while the
  worker reads every tenant's FinOps ledger from another tenant's context and from no context at
  all, and the suite reports 48/48. **This is verbatim the regression check 42's comment records
  for `evt_` tables after MOD-010's review.** I fixed it there and scoped the fix to `evt_`;
  MOD-011 granted the worker identical access to eight new tables and inherited the blind spot.
  The structural half matters too: comparing a policy's predicate asserts that a *matching*
  policy exists, which an added second policy satisfies trivially, so check 44 now also requires
  exactly one permissive policy per table.
- **A period that has only a start is not a period.** `evaluate_budget` bounded spend with
  `period_start >= %s` and nothing above it, and took that date from the caller;
  `ops_budgets.period` was written by `set_budget` and read by nothing. A monthly budget 45%
  consumed in January reported 143% -- the whole year -- published three anomaly events and wrote
  three *insert-only* alert rows snapshotting a figure that was never anybody's January spend.
  And because the alert rows are unique per `(budget, period_start, threshold)`, a sweep passing
  today's date re-raised every threshold on every run with a bigger number each time, which is
  the opposite of the once-per-period guarantee the docstring claimed. `cost_summary`, 140 lines
  earlier in the same file, bounded both ends.
- **Derive, never accept, applies to a rate-limit key.** `limit_subject` lowercased and stripped
  the ends, which agrees with `normalize_email` and not with `normalize_phone` -- that one
  strips whitespace, parentheses and hyphens from *anywhere* in the string. Eight spellings of
  one phone number resolved to one identity and took eight full login budgets, each attempt
  still costing a scrypt. The limiter added to close MOD-007's volume gap did not close it for
  any phone identifier.
- **A margin that reads only invoices is blind to the one way revenue goes down.** MOD-015 has
  no invoice edit and no void: a correction is a credit note, stored positive and always read as
  a reduction. `gross_margin` never read that table, so fully crediting an invoice still
  reported a 50% margin on a period that earned nothing -- the overstatement the function's own
  docstring says it exists to avoid.
- **A lookup that proves something exists does not authorise what you do next** (MOD-010's rule,
  hit again, twice). `record_result` selected `enabled` and never looked at it, so disabling a
  probe stopped nothing: results kept arriving, kept feeding the series an availability objective
  reads, and kept publishing `synthetic_check.failed`. And `define_objective` consulted the
  catalogue only to confirm the metric key existed -- never asking its *kind*, so a `ratio`
  stored with `aggregate_as=sum` read as a 99.9% availability SLO and was **met during a total
  outage**, since one success in ten thousand attempts sums to 1.0.
- **An objective that names no dimensions is an objective about nothing anybody defined.**
  `_buckets_for` applied no dimension predicate, so an objective merged every consumer and every
  check key: a consumer sitting at zero was invisible behind nine healthy ones and never
  alerted, and a merged breach paged somebody with no way to tell which one failed. `series` had
  refused a *partial* dimension match from the start, for exactly this reason; the objective
  path did a total one.
- **Evidence with nobody's name on it answers nothing** (MOD-009's rule, recurring).
  `ops_synthetic_results` was the one insert-only table in the module with no actor and no
  correlation id, while every sibling carried both -- and it is the table whose own docstring
  names a fabricated `passed` as the risk. MOD-008 does not audit an allowed action by design,
  so there was no second record to fall back on.
- **A sample proves the sample.** My mutation round broke 38 things and caught 37; a reviewer
  then ran 74 and found **38 uncaught** -- seven of the eight tenant-registry foreign keys, 34 of
  46 CHECK constraints, two unique indexes, and every column-level grant (check 47's three ACL
  bans read `pg_class.relacl`, which holds table-level grants only). Check 48's preamble said
  each constraint had been broken on purpose and watched to fail; that was true of the fifteen it
  named and false of the module. `ops_capacity_forecasts` had no constraint evidence at all.

Five decisions carry the module, and two of them are refusals:

- **A metric that duplicates a table is a second copy of the truth that can disagree with it.**
  The first draft of the catalogue carried `events.outbox_pending`, `events.dead_letters`,
  `privacy.dsar_open` and `privacy.dsar_overdue`. Every one is a count over a table that already
  exists, under a role that can already read it -- so a dashboard and a `SELECT count(*)` could
  answer the same question differently with nothing able to say which was right. That is
  paragraph 3503's "logs are not a shadow database" applied to the metric store itself, and it is
  why the catalogue is five entries rather than nine. What is left is what has no table: how long
  work took, and how often it succeeded.
- **There are no percentiles, and `objectives.py` refuses to fake one.** A point is an hourly
  bucket carrying an observation count and a total, so a sum, a rate and a mean are available and
  a p95 is not. Paragraph 3516 does ask for one; an objective stated as a percentile is therefore
  refused **at definition time**, where somebody can see why, rather than evaluated against a mean
  and reported as a verdict. Closing it needs a histogram this store does not keep.
- **An empty window is not a pass**, and it is not a breach either. A series with nothing in it is
  a producer that stopped or an objective nobody wired up; reporting `met` because nothing
  contradicted the threshold is how a dashboard goes green during an outage. It publishes no
  event, because "the measurement is missing" and "the system is failing" are different alerts and
  conflating them is how a channel gets muted.
- **Cost is an input, not an observation.** There is no cloud bill, AI invoice or messaging
  statement in this repository, so `allocate_cost` records figures a caller supplies -- the same
  precedent as MOD-015's tax rate. Every amount is a signed integer in minor units, a correction
  is a later row rather than an edit, and `ops_cost_records` carries no UPDATE for any runtime
  role. `gross_margin` reads revenue from `bil_invoices` **net of tax and of the partner share**,
  because tax is collected on somebody else's behalf and a revenue share is not Veyro's money;
  counting either would overstate the margin in the direction nobody checks.
- **Nothing here runs a synthetic probe.** `ops_synthetic_checks` is the registry and
  `ops_synthetic_results` is the insert-only ledger whatever runs them writes to. A row saying
  "passed" that no probe produced is the fabricated-evidence shape this codebase has been bitten
  by twice. `description` is prose and not a URL, deliberately: a tenant-writable URL that
  something later fetches is a request-forgery primitive.

Two things are new in the request path and worth knowing before touching `permit`:

- **The rate limiter partially closes MOD-007's named gap, and its counter is in this process's
  memory.** Partially: four routes -- `/auth/login`, `/auth/challenge`, `/auth/step-up` and
  `/auth/recover` -- plus a per-identity budget on everything behind the gate. `POST /identities`
  is still unlimited and is the one worth naming, because it is unauthenticated, costs a scrypt
  and writes a row to a table with no DELETE grant, which is the exact unbounded-growth shape
  `ratelimit.py` argues a durable counter must not become. So are `/auth/rotate`,
  `/identities/{id}/password`, `/identities/{id}/recovery-codes` and the passkey assertion.
  Lockout bounds guessing against one identity and sees nothing when the address is not
  registered; nothing bounded volume. The obvious durable version -- a table keyed by (tenant,
  subject, window) -- fails on the thing a limiter exists for: `/auth/login` is reachable
  unauthenticated and its subject is caller-supplied, so a million distinct addresses write a
  million rows into a table with no DELETE grant, and the limiter becomes the unbounded-growth
  primitive it was added to prevent. The in-memory map is capped and evicts. **It does not
  coordinate across processes**: two replicas each allow the full budget and the counters reset on
  restart. The decision functions take the count as an argument precisely so a shared store can go
  underneath them without the policy moving.
- **`authz.denials` counts refusals and deliberately not allows.** Counting every allow means an
  upsert on one row for every request reaching a gated route, which contends on that row and
  couples every product route's availability to the metric store -- observability taking the
  product down is the wrong trade for a chart. The consequence is stated rather than discovered:
  there is no denominator, so an objective expressed as "denials under 1% of traffic" cannot be
  evaluated here. And the recording failure is swallowed in exactly one place, with a reason: a
  refusal has already reached MOD-008's audit chain, and turning a 403 into a 500 would tell the
  caller "try again" when the answer is "you may not".

Also fixed in that round, each with a named regression test: a naive `observed_at` was bucketed
in the host's local timezone and an unbounded future one let a routine AAL-1 caller hold an
objective green through an outage still to come (the bound is on writes only -- reading up to a
future moment is the ordinary "last 24 hours"); `window_hours` was unbounded, so a billion raised
`OverflowError` before any query and reached the caller as a 500; a `gauge` kind was declared that
the accumulating upsert could not honour, since a second level in an hour yields the sum of the
two; a "correction" was never checked for matching the record it corrected in currency, dimension
or sign; `evaluate_budget` published `cost.anomaly.detected` whether or not its `DO NOTHING`
insert wrote a row, so two sweeps racing both paged while one row existed; a forecast far past its
limit overflowed `integer` into a 500; and FastAPI's default validation handler echoed the
offending *input* into its own 422, which `json.dumps` then refused for a `NaN` the parser had
accepted -- a 500 from inside a 422, on every route in this application rather than only the new
ones.

Known gaps, deliberate:

- **No percentiles, so no p95 budget** -- the refusal above. It needs a histogram or a
  time-series store, which is a different kind of database from the one this build has.
- **No distributed traces and no structured log pipeline.** Paragraph 3494 asks for all three of
  logs, metrics and traces; what is built is the metric third plus the correlation id that
  already threads through every module. A trace needs a collector, and `/events/trace` is the
  nearest thing here.
- **Nothing drives any of it on a schedule.** `evaluate_objective` and `evaluate_budget` are
  called by a route and by tests; no worker loops on them, which is the same missing worker
  runtime as MOD-007's challenge sweep, MOD-009's retention sweep and MOD-010's relay. Four
  modules now want it, and this is the first one where the absence changes the product: an
  objective nobody evaluates raises no alert.
- **No load tests and no scaling policy** (part of paragraph 3498). The capacity table records a
  forecast somebody made; nothing generates the load that would inform one.
- **No cost feed.** The ledger, budgets, burn arithmetic and alerts are built and there is no
  statement to load into them.
- **Alert routing is an owner string and a runbook reference**, not an integration. Paragraph 3501
  asks for routing with ownership and escalation; the ownership and the runbook ride on the row
  and on every event, and nothing delivers them anywhere.
- **The metric upsert contends on one row per (tenant, metric, hour, dimensions).** Microseconds
  of row lock per write at this scale, and the fix when it is not is in-process aggregation with a
  periodic flush -- which wants the same missing worker.
- **`ops_metric_points.dimensions` is residue no erasure can reach**, like `evt_outbox.payload`,
  and it is *not* in `SUBJECT_COLUMNS` because the sweep matches column names and a subject
  identifier would be inside the `jsonb`. That omission is correct today -- all three producers
  read their dimension values from the database rather than from a caller -- and nothing tests
  that invariant. The day a producer passes a caller-supplied string, MOD-010's
  `cfg_exposures.subject_id` finding recurs in a store with no DELETE grant at all.
- **`authz.denials` counts refusals at the gate, which is slightly more than its name.** It fires
  on any `ServiceError` from `authz.require`, including a `NotFound` from scope resolution.
- **`events.delivery_success` counts a lease-stolen delivery as a success.** The handler did run
  cleanly, which is the defensible reading, but two relays racing one slow delivery each count it
  once -- so the ratio is over attempts-by-this-relay rather than over distinct deliveries.
- **An objective cannot span dimension values.** Requiring the full declared set is what makes a
  breach actionable, and it means "availability across all consumers" needs one objective per
  consumer. A metric-wide objective would want an aggregate over series, which is a different
  evaluation than the one this store supports.

**MOD-012 (ECO-02 integration adapter core) -- implemented, gated and reviewed.** Two
tables in `plt01_platform` holding the definition catalogue, five `int_` tables in `plt01` under
the same forced RLS, `app/integrations/` beside them, and twenty-four HTTP routes. Working: a
versioned adapter contract with capabilities, scopes, a configuration schema and regions;
immutable published versions; installs that snapshot the version they were made against; the
connector lifecycle from install through authorize, validate, activate, disable and uninstall;
connections with least-privilege scope grants; credential *references*; sync cursors with a
conflict policy; and connector runs with retry, quarantine, release and reconciliation. All five
of ECO-02's Foundation events are produced. Proven: isolation checks 49-54, mutation-tested in
two rounds -- 83 before the review and 99 after it showed three checks had been silently
disabled by a constraint added to close an earlier finding; 98 of the 99 caught by a check that
guards what was broken and one by the seed failing closed; 30 domain unit tests with no
database; 43 service integration tests; 10 API tests.

**This is ECO-02's Foundation slice only.** The marketplace, partner accounts, listings,
certification and revenue share are its V2 slice and are not built; so is ECO-01's developer
platform, which is where public APIs, OAuth applications and outbound webhooks live.

Four decisions carry the module:

- **A credential reference holds a reference, and there is no column it could hold a secret in.**
  `vault_ref` names a secret kept somewhere this build cannot read. There is no vault here --
  MOD-007 says so about TOTP seeds and MOD-009 says so about crypto-shred -- so the honest shape
  is a table that *cannot* store one rather than one that stores one carefully. The definition
  catalogue carries the same rule from the other side: a configuration field declares a type and
  **there is no `secret` type**, so a definition cannot invite a tenant to paste an API key into
  a value every list route reads. Check 52 asserts the column list in full and tries to declare
  a secret field, because in both places the control is an *absence* and an absence is exactly
  what a later migration adds back.
- **Definitions are rows, not code -- the opposite call from the last four modules.** Permissions
  (MOD-008), event types (MOD-010) and metrics (MOD-011) are code because they are facts about
  what this software does, and two tenants disagreeing would be unresolvable. An integration
  definition is not: ECO-02's own model has partners publishing their own, so the set is open by
  design and the authority is whoever published the version. It lives in `plt01_platform` where
  `saas_plans` lives, published versions are immutable by privilege, and an install
  **snapshots** the version -- which is what lets somebody answer "what did this tenant actually
  authorize" a year later without a cross-plane join the role separation forbids anyway.
- **Widening what a third party may reach is a new authorization, not an edit.**
  `int_connections.granted_scopes` carries no UPDATE grant for any runtime role, and neither
  does a credential reference's `vault_ref`, `scopes` or `expires_at`; a rotation is a new row
  that supersedes the old one. That is the only way "what did this connection hold on the
  fourteenth" stays answerable, and check 53 proves it per column and per role.
- **An uninstall revokes every connection in the same transaction.** An uninstall that left one
  authorized would be a tenant believing a third party no longer has access while it does, which
  is the worst failure available to this module. The rows stay, revoked and attributed: the
  question afterwards is always what the provider could reach and until when.

And three from the schema review, each defeating a protection the module's own prose called
load-bearing:

- **Adding a constraint invalidates every case that inserts a row it touches.** The
  `settled_has_an_actor` constraint added to close the attribution finding fires on every row
  three existing check-54 cases insert, so those three began passing because a *sibling* fired
  -- the status, attempt-budget and failure-explained constraints could all be dropped with the
  suite reporting 54/54. I had written that exact rule into the RLS doc an hour earlier, from
  this module's own first sweep. **A schema change means re-running the sweep, not re-reading
  the cases.**
- **"Immutable" has to name the operation.** A published definition version's entries carried
  `GRANT SELECT, INSERT` and a unique index on the entry name, which stops re-declaring a name
  that exists and stops nothing else -- so the scope set was additive-mutable, and a *required*
  scope could be added to a published version. Installs keep their snapshot, so the blast
  radius is new installs against "version 1" authorizing a wider scope set than the one
  reviewed, which is precisely paragraph 3032's control. The header rested the whole claim on
  "nobody having run the wrong UPDATE". A trigger now refuses any write to a non-draft version,
  and a second one makes `published_at` and `retired_at` final, since a CHECK cannot see `OLD`.
- **A sweep of one kind of reference is not a sweep.** Check 51 swept the tenant-registry
  foreign key across every table and *sampled* the intra-module parents, which left two
  droppable in silence: the rotation chain's self-reference, the only thing keeping a
  credential's predecessor inside its own tenant, and the entries table's reference to the
  definition it belongs to. Every foreign key in the module is now compared as a set.

Also fixed from the advisories: the column-list pin covered only `int_credential_refs`, so
`access_token` on `int_connections` or `shared_secret` on `int_definitions` passed -- all seven
tables are pinned now; `vault_ref` was non-blank text, which made a live API key a valid "vault
reference" and the absence of a secret column a naming convention rather than a control, so it
now has to look like a locator; and three cases were detected only by an exception from a
different object, which turns a red suite into a misleading one.

Things worth knowing before extending it:

- **`validated` means somebody recorded a validation, not that this build performed one.** There
  is no provider to call, so the state carries an actor and a written piece of evidence and the
  row says what it is -- a claim made by a named party at a time. A state reading as "verified"
  while nothing verified anything is the shape MOD-011's synthetic results were built to avoid.
- **A cursor's position is opaque and is never ordered.** A provider's cursor may be a
  timestamp, a token or a sequence number; what `check_advance` compares is when each was
  *observed*, so a late or replayed run cannot settle over a newer result. Moving one backwards
  is `reset_cursor`, a different permission, and it records who and why -- re-reading a window
  costs whatever the provider charges for it.
- **The backoff is MOD-010's, imported rather than copied.** Two retry curves in one repository
  drift, and the day they disagree nobody can say which one is the policy.
- **Succession is checked when a version is registered, not when it is published.** A later
  version may not drop a capability, newly require a configuration field, or newly require a
  scope -- each breaks an install that already exists, and the last one silently, since the
  install reads as active while being under-privileged. Catching it where somebody is writing
  the change is worth more than catching it at a deploy.

Known gaps, deliberate:

- **Nothing syncs.** There is no provider, no outbound HTTP and no adapter code. `start_run`,
  `finish_run` and `fail_run` are written by whatever does the work, and a module that wrote
  "synced 40 records" with nothing having answered would be the fabricated-evidence shape this
  codebase has been bitten by three times.
- **No inbound webhook receiver**, which is the one piece of the EIP's own summary line not
  built. Receiving a provider callback means verifying its signature, which means holding the
  provider's signing secret -- the vault again. An endpoint accepting unverified callbacks is a
  forgery primitive, strictly worse than not having one.
- **No rotation on a schedule.** `credentials_due` decides and publishes when somebody calls it;
  nothing loops, and it is **not idempotent across calls** by design -- making it so needs a
  record of what has already been announced, and a table of announcements nobody consumes is
  the shape this codebase refuses elsewhere. The fifth module now waiting on a worker runtime.
- **No vendor dependency register** (paragraph 3030's SLA, outage fallback, cost and exit plan
  as a catalogue). The per-install obligations are built and enforced at activation; the
  platform-wide register is not.
- **The definition catalogue is on the unauthenticated platform plane**, and it is worse there
  than the plan catalogue: a definition declares the scopes an install may grant a third party,
  so whoever can publish one chooses what a tenant is able to hand out.
- **A value can still carry a secret, and only the names are checked.** `int_installs.config`
  is `jsonb` a tenant supplies, and `contract.check_config` validates field names and types and
  never values -- so a definition declaring a `string` field named `api_key` accepts one. That
  is MOD-010's `cfg_exposures.subject_id` finding recurring: the restricted-field rule checks
  names, and a value can carry anything. The column has an UPDATE grant, so unlike the event
  outbox it is at least erasable.
- **Nothing creates a `pending` connection.** The state exists and the machine admits it,
  because a provider flow that redirects for consent would create the row before the grant
  comes back; in this build authorization and creation are one command.
- **A standalone revocation publishes no event.** ECO-02's event list has no
  `integration.disconnected`, and inventing one is inventing product; an uninstall publishes
  `integration.uninstalled` with the count it revoked.
- **`conflict_resolution` is decided and never applied.** Nothing reads a provider record to
  compare against a local one, so the policy is recorded per cursor and consulted by nobody --
  the same shape as `Decision.mask` in MOD-008.

**MOD-013 (ENG-02 notification platform, templates and preferences) -- implemented, gated and
reviewed.** Nine `ntf_` tables in `plt01` under the same forced RLS, `app/notifications/`
beside them, and twenty HTTP routes. Working: versioned, approved, immutable templates with
localization and variable checking; recipient preferences with quiet hours, frequency caps and
digesting; channel policies with fallback and per-message cost; recipient-to-address bindings;
notification authoring with rendering, deduplication and a recorded decision; one delivery row
per notification and channel with a leased claim, retry and quarantine; bounce and complaint
suppression; and digest batching. Five of ENG-02's six events are produced. Proven: isolation
checks 55-60, mutation-tested in two rounds -- 99 before the review and 154 after it, every one
caught by the check that guards what was broken: 63 table-level (RLS, both policy halves, a
second permissive policy, DELETE, TRUNCATE and an added column, on all nine tables), all 75
CHECK, unique and foreign-key constraints dropped one at a time, the three remaining unique
indexes, both triggers, nine constraint *weakenings* rather than drops, and the partitioned
table a reviewer used to walk past the whole sweep. 32 domain unit tests with no database; 49
service integration tests.

**Three reviewers worked this module in parallel -- the schema, the Python, the request path --
and all three returned CHANGES_REQUESTED.** Twenty-one blocking defects, and the largest single
cause was a control keyed on a value the caller supplies, checked for shape and never for
correspondence. Each is carried forward below as a rule.

- **Resolve the channel before you evaluate anything against it.** The fallback was resolved in
  the middle of `decide`, after the preference, the suppression check and the address digest
  had been read for the channel the message was no longer going to. A tenant falling back from
  email to SMS -- the ordinary response to a provider outage, and exactly when volume gets
  re-routed -- texted a member who had said "don't text me", over a channel that was itself
  disabled, to a number that had reported the tenant as spam. The suppression key is
  `sha256(channel:address)`, so the SMS suppression was not merely unchecked, it was
  *unreachable* from that path; and the row stored the email digest, so the eventual bounce
  wrote a suppression key no later request could ever produce. Four controls, one ordering.
  `preferences.resolve_channel` is now a separate function and `decide` takes the resolved
  channel.
- **Two caller-supplied keys that nothing relates are two halves of a control, each failing
  open.** `recipient_id` keyed the preference, the quiet window and the cap; `address_digest`
  keyed the suppression list; both were shape-checked and neither was ever checked against the
  other. A digest that is not the recipient's finds no suppression and gets the complainant
  mailed; a `person_id` supplied where an `identity_id` was meant misses the preference while
  `GET /notifications/preferences` still shows the opt-out standing. `ntf_recipient_channels`
  binds them in both directions -- one digest per recipient and channel, one recipient per
  digest and channel -- so a suppression recorded against a digest is reachable from every
  later request for that person. **It cannot verify that a digest is really that person's
  address**; there is none on this plane. Correspondence and stability are what the controls
  rest on, and those are enforced.
- **A body field that buys an authority is a permission, so charge one.** `priority:
  "critical"` with any non-blank `bypass_policy_ref` overrode the opt-out, the quiet window and
  the frequency cap, on the same routine AAL-1 permission an ordinary request costs -- so
  paragraph 2461's "only under documented policy" was satisfied by typing `x`. That is MOD-009's
  `consent_subject` finding in this module's clothes, and it takes the same remedy:
  `notifications.notification.request_critical`, financial class, chosen by the route from the
  body. Nothing resolves the reference against a real policy, which is still a gap -- now a gap
  behind a stepped-up permission.
- **The event outbox is the one store no erasure reaches, so nothing free-text goes in it.**
  `notification.failed` carried `reason`, built from the dispatcher's `error` -- and the
  ordinary content of an SMTP rejection is `550 5.1.1 <jane@example.com>: Recipient address
  rejected`. So the realistic bounce, with nobody trying, put a contact address into
  `evt_outbox.payload` from the module whose defining property is that it holds none. MOD-010's
  rule: the restricted-field check reads declared *names*, and a value carries anything. All
  three delivery events dropped the field; the text stays on `ntf_deliveries.last_error`.
- **A claim that does not mark the row claimed is a handout.** `dispatch_notification` set
  `next_attempt_at = NULL`, which the claim query reads as "due now", so five calls handed one
  message to five dispatchers. It now leases the row for `delivery.CLAIM_LEASE` and checks the
  row count. `record_outcome` had the matching half: its guarded UPDATE's row count was
  ignored, so a dispatcher whose claim had already been settled published an outcome nothing
  recorded, and could schedule redelivery of a delivered message.
- **A control consulted once is a control with a window** -- MOD-009's rule, and a deferred
  notification can sit for eight hours. The suppression list was read at request time and never
  again, so an unsubscribe between the request and the dispatch did nothing. It is re-read in
  `dispatch_notification`, which settles the delivery as `suppressed` rather than refusing
  blind -- **and raises the refusal after the commit**, because `tenant_scope` rolls back on a
  raise and the first version threw its own evidence away. That is MOD-007's and MOD-008's rule
  reintroduced; the test asserting the notification reads `suppressed` is what caught it.
- **A state nothing creates is a feature that silently drops messages.** The delivery row was
  inserted only for `send`, so a quiet-hours `defer` had none and `dispatch_notification`
  answered "no delivery is due" for ever -- including for a transactional message, and the
  dispatcher's own `status IN ('requested', 'deferred')` clause was unreachable. "Quiet hours
  defer, they do not suppress" was a comment rather than a behaviour.
- **Irreversible state must not be declarable.** `suppress_address` accepted `bounced` and
  `complained`, and only an unsubscribe may be released -- so a routine AAL-1 permission could
  block an address from every transactional notice for ever, with no remedy anywhere in the
  module. It takes `unsubscribed` only; the genuine ones are written by `record_outcome` from a
  reported delivery, which is where the judgement actually comes from.
- **"Immutable" has to refuse the demotion, not only the edit.** `status` is in the template
  UPDATE grant, so immutability was a two-step: demote to draft (no content field moves),
  rewrite the body, publish again -- leaving the attacker's text under the original approver's
  name and timestamp, the separation of duties on content bypassed entirely. The same trigger
  now refuses `published -> draft`. Not reachable through a route as shipped, which is what
  makes it a finding rather than an incident: the trigger exists for the writer the service's
  choice of SQL is not.
- Three advisories were worth taking as well, each a permission reaching past what its own
  description claims. `record_outcome` selected the delivery with no state filter and required
  no claim, so the routine dispatch permission could settle any pending delivery in the tenant
  as delivered -- or report a bounce on one and write the suppression that follows, which only
  an unsubscribe can undo; it now refuses a delivery that was never dispatched.
  `GET /notifications/channels` was gated on `notifications.template.read`, so "see notification
  templates" also read what every message costs the tenant; `notifications.policy.read` is its
  own permission now. And the reachability reason for `ntf_notifications.recipient_id` disclosed
  that an identifier survives an erasure without saying that the row it keeps alive carries the
  full text of every message ever sent to that person.
- Three smaller ones with the same shapes as earlier modules: `_live_consent` let
  `ORDER BY signed_at DESC LIMIT 1` pick between a grant and a withdrawal carrying the same
  caller-supplied instant (a tie now goes to the withdrawal, deliberately the opposite of
  MOD-009's `consent.latest`, and said so); the digest INSERT omitted `notification_count`, so
  every digest reported one fewer than it held; and `currency` reached `char(3)` unbounded,
  where `StringDataRightTruncation` is a `DataError` rather than the `CheckViolation` the
  handlers catch -- MOD-011's and MOD-012's finding for the third time.

Six decisions carry the module:

- **No column here is for a contact address, and three free-text ones will hold one anyway.**
  `ntf_notifications`, `ntf_suppressions` and `ntf_recipient_channels` carry a SHA-256 of
  `channel:address` and never the address, so a bounce is remembered and a recipient matched
  without a second copy of everyone's email beside the one MOD-007 and MOD-014 own. MOD-009's
  objection to a shadow database is that the copies disagree and only one is reachable by an
  erasure. Check 58 pins every table's column list, because the control is an absence.
  **The digest is pseudonymous, not anonymous** -- somebody with a candidate address can test
  it -- so those columns are declared in `SUBJECT_COLUMNS` and appear in the residue a
  completion report discloses. The header used to claim the module held no contact address at
  all; a reviewer disproved it with an ordinary bounce. `ntf_suppressions.detail`,
  `ntf_deliveries.last_error` and `ntf_deliveries.provider_ref` are free text a dispatcher
  supplies, all three are now declared with the mechanism their grants support, and the first
  of them is residue no erasure can reach.
- **A recipient and an address digest answer to each other** -- the binding above, and the one
  thing that makes the suppression list reach a person rather than a string.
- **The category is paragraph 2463's separation, and no request field overrides it.** A template
  declares it, and the category decides whether a consent record is required before a
  notification may be requested at all and whether a recipient's opt-out can stop it. Only
  `coaching` and `marketing` may be muted -- a constraint, not a convention -- so a tenant can
  always tell somebody their payment failed. A caller able to declare its own category would
  escape both controls with a body field.
- **A marketing notification cites the consent record that permitted it, by foreign key.**
  MOD-009's `sec_consent_records` is on this plane and under this role, so this is the one
  cross-module reference in the module the database can enforce -- not a boolean somebody set,
  and not a call to a service that may have moved on. The constraint makes the citation
  mandatory for marketing and forbidden for anything else, so a receipt cannot ride on a
  marketing consent and make it look used.
- **Paragraph 2464's "cannot be delivered repeatedly" needs both halves.** The *request* is
  deduplicated by `(tenant, idempotency_key)`, so a caller whose own retry fired -- or an event
  redelivered under MOD-010's at-least-once contract -- authors one notification. The *delivery*
  is one row per `(tenant, notification, channel)`, so a dispatcher that sent a message, timed
  out and retried settles the row it already holds. Neither is sufficient alone.
- **The authored message carries no UPDATE grant at all.** Paragraph 2474: "delivery failure
  never rewrites the authored message". The rendered text, the recipient, the digest of their
  address, the category and the consent are what was decided at request time; only the status
  and the schedule move.

Things worth knowing before extending it:

- **A template key is one *message*, not one channel.** Versions are per `(key, channel,
  locale)`, which is what lets a fallback find the text written for the channel it falls back
  *to*. The first version keyed versions on `(key, version)` alone, which forced one channel per
  key and made a fallback carry an email subject onto an SMS -- refused outright by
  `ntf_notifications_subject_matches_channel`. Found by this module's own tests. A key with no
  template for the fallback channel is suppressed with a reason rather than sent as text nobody
  wrote for it, and the category is pinned key-wide so a fallback cannot change what the message
  is allowed to do.
- **A suppressed notification is still authored.** A request that vanished because a preference
  said no is a request nobody can account for when the member asks why they never heard
  anything.
- **A frequency cap digests rather than drops**, which is what makes a cap safe to set low.
- **An author cannot approve their own template**, by constraint: it goes out under the tenant's
  name to everybody, which is MOD-008's separation of duties applied to content.
- **Only an unsubscribe may be released.** A bounce or a complaint is the channel's judgement
  about deliverability, and a tenant that could clear those would be choosing to keep sending to
  an address that rejected them -- which damages the chance of every other notification
  arriving, including the transactional ones nobody opted out of. `reason` carries no UPDATE
  grant, so a bounce cannot be relabelled an unsubscribe and then lifted.
- **A value is never itself expanded.** `templates.render` substitutes in one pass, so a value
  containing `{{ other }}` is inserted literally -- the values come from a caller and the text
  comes from a tenant author, and a second pass would be a template-injection primitive.
- **A request carries one address digest per channel**, because the channel policy may send it
  somewhere other than the template's own channel and a digest is channel-scoped by
  construction. A fallback to a channel the caller gave no digest for is refused rather than
  guessed at.
- **A rebinding is a different permission from a preference change.** `notifications.recipient
  .rebind` is financial class because moving a binding is how somebody would walk a
  complainant's address away from the bounce suppression recorded against it. It carries an
  actor and a written reason, and `bound_at`/`bound_by` carry no UPDATE, so when the binding
  was first made stays answerable after it has moved.
- **The frequency cap counts per channel**, because `ntf_preferences` is keyed on category
  *and* channel: a count across channels compared against one channel's cap is two different
  questions joined by a variable name.

Known gaps, deliberate:

- **Nothing sends.** No provider, no SMTP, no outbound HTTP. `dispatch_notification` claims a
  delivery for whatever does the sending and `record_outcome` is written by it; a module that
  wrote "delivered" with nothing having answered would be the fabricated-evidence shape this
  codebase has been bitten by four times.
- **No provider failover.** Paragraph 2459 asks for it; failing over needs two providers and
  there are none. Channel fallback, which is the half that does not, is built.
- **Digests are batched and never sent.** `ntf_digests` fills and closes; rendering a batch into
  one message needs a digest template format the sources do not state, and nothing sweeps the
  open windows -- the sixth module now waiting on a worker runtime.
- **`status_update.published` is declared and unproduced.** A status page is a surface this
  build does not have, and an event announcing a publication that never happened would be worse
  than the gap.
- **No localization fallback chain.** A template per locale is the mechanism; quietly sending
  English to somebody who asked for Arabic is worse than refusing, and picking a chain is a
  product decision the sources do not state.
- **No delivery analytics or cost reporting.** The per-message cost is recorded on the channel
  policy and nothing aggregates it; that is MOD-011's `ops_cost_records`, and wiring the two
  together is a decision about who owns the figure.
- **A `bypass_policy_ref` is still not resolved against anything.** The constraint refuses a
  blank and the route charges a stepped-up financial permission for using one, and nothing in
  the catalogue, the configuration plane or any table establishes that the reference names a
  documented policy. Paragraph 2461's "documented" is carried by the permission, not by the
  field.
- **The binding cannot verify an address**, only correspondence. A caller that supplies a wrong
  `recipient_id` *consistently*, with a digest no other recipient has claimed, is indistinguish-
  able from a correct one; what is closed is the far commoner case where the two keys disagree
  with each other or with what was bound before.
- **Three free-text columns hold whatever a dispatcher sends**, including an address, and the
  erasure executor reaches only `iam`. `ntf_deliveries.last_error` and `provider_ref` carry an
  UPDATE grant and nothing clears them on a request; `ntf_suppressions.detail` carries none at
  all. Declared, disclosed, and not fixed here -- closing it needs either a provider error
  vocabulary or an erasure path into `plt01`.
- **A lease is not a lock.** A dispatcher slower than `delivery.CLAIM_LEASE` can be joined by a
  second one, which is inside the at-least-once contract; the `state = <what we read>` guard on
  the settling write is what stops the late writer corrupting the row.

**MOD-014 (PPL-01 people, profiles, relationships and Member 360) -- implemented, gated and
reviewed.** Sixteen `ppl_` tables in `plt01` under the same forced RLS, `app/people/`
beside them, and twenty-six HTTP routes. Working: the canonical person with tenant-scoped
profiles for the tenant, the member and the staff role; contact points as the only copy of a
member's address in the build; a directed, time-bounded relationship graph over the five kinds
paragraph 1319 names; tags, schema-governed custom fields and insert-only notes; explainable
duplicate detection with a review queue; a reviewable, reversible, audited merge; a timeline
projected from MOD-010's outbox; and the composed Member 360. All five of PPL-01's events are
produced. Proven: isolation checks 61-66, mutation-tested in two rounds -- 236 before the
review and 25 after it, every one caught. Round one: 137 table-level
(RLS, both policy halves, a second permissive policy, DELETE, TRUNCATE, an added column and a
PUBLIC grant on all sixteen tables, plus eight targeted grant-widenings and the partitioned
table that walks past a `relkind = 'r'` sweep), and 99 over every CHECK, unique and foreign-key
constraint dropped one at a time. **Four were missed on the first pass and the repair was to
the schema, not the test**: one compound CHECK naming a status domain subsumed two siblings, so
it was split into three single-purpose constraints. All four are caught now, and 7 of the 99
could not run because a unique constraint owns its index and the constraint drop covers it. 54
domain unit tests with no database; 55 service integration tests; 16 HTTP tests.

Round two is the reviewers' own mutations, all of which passed before and fail now: thirteen of
sixteen **primary keys** were droppable (the sweep's join was inner, so a table with no primary
key contributed no row and was never flagged -- and the three that resisted were saved by a
dependent foreign key rather than by a check, which is this file's MOD-004 trap verbatim); the
`coalesce` in all three attributed-decision constraints could be removed, because every case
tested a *blank* reason and none a NULL one; **nothing in the 9,000-line suite had ever read
`attnotnull`**, in any module, so dropping NOT NULL from the dedup key admitted unlimited NULL
duplicates per person and blinded the detector to all of them; one side of each split merge
constraint had no case; and a `plt01` table whose name matches no module prefix was invisible to
all sixty-six checks -- a reviewer created `plt01.member_contacts` holding plaintext addresses
with no RLS and no policy and watched the suite report every check passing. That last sweep is
prefix-free now and covers the whole schema, as the `iam` block always did.

**This is the module where `Decision.mask` finally has a read path** -- and the review showed
how much of that was still a claim. MOD-008 computed `masked_fields` on every allowed decision
and from MOD-008 to MOD-013 nothing read it; "computed, not applied" was a standing gap here for
five modules. `permit` returns the gate rather than the session, every read in
`app/people/service.py` takes the list **and** the caller's permission set as required
arguments, and `visibility.apply` walks the record to every depth. What the review had to add
before any of that was true: the permission set is filtered by the session's assurance, the
person's own classified columns are masked by class and not only its custom fields, and the two
read routes that silently dropped the gate's list now take it -- which mypy enforces, because
the argument is required.

**Three reviewers worked this module in parallel -- the schema, the Python, the request path --
and all three returned CHANGES_REQUESTED.** Twenty blocking defects. Five are worth carrying
forward as rules, because each is a shape that has now recurred:

- **A grant is not a session.** `held_permissions` asked `effective_permissions`, which answers
  from role assignments alone, and `permit` assurance-checks only the *route's* action -- routine
  for every masked read. So every permission the masking consulted was effectively routine-class
  however the catalogue declared it: a password-only session holding `member.health.read` read
  medical notes in full, in the build whose own code says health is unreachable because AAL 3
  needs a hardware factor MOD-007 cannot verify. The catalogue, `visibility.py` and this file all
  stated the opposite. **An action class is decorative on any path that reads the permission
  rather than gating on it.**
- **A control consulted on one path and not its sibling** -- the fourth module. Guardianship was
  on `GET /people/{id}` and the 360; `/notes` and `/timeline` served a minor's data to the same
  credential the record read had just refused. Hoisted into `_require_guardianship`, which all
  four reads call, because a copy in three places does not guarantee the fourth.
- **A masking claim is only as wide as the columns it names.** The class mask reached custom
  fields and notes and not the person's own columns, so a routine AAL-1 read returned
  `date_of_birth` -- the canonical `identity` field in MOD-008's own table -- and every contact
  value in the clear, beside a `contact`-classified custom field holding the same phone number
  rendered as `***`. `visibility.COLUMN_CLASSES` is the map that was missing.
- **A merge copies, so an erasure has to reach every copy.** `person_id` carries no UPDATE grant
  and no `ppl_` table carries DELETE, so a merge inserts on the survivor and the source keeps its
  rows -- a person's address exists under two ids. The erasure resolved one through
  `ppl_identity_links` and recorded `done / 1`, and whichever side held the sign-in identity, the
  other kept the name, the birth date, the address and the health note. In the module whose
  registry entry calls `ppl_contact_points.value_raw` "the only copy of a member's address in
  this build". `_person_cluster_for_subject` walks the merge closure in both directions now, and
  two tests prove both directions fail without it.
- **No test ever called a `/people` route successfully**, which is why the four findings above
  all passed a green suite. The service tests reached past the request path and asserted the
  decisions, so the three pieces this change adds to that path -- the gate return, the permission
  resolution, the actor lookup -- were exercised by nothing. `tests/test_people_api.py` is the
  answer: 16 HTTP tests, nine of which failed on their first run.

Five more were features that silently stopped working while reporting success, which is the
other half of the round: `project_timeline` had no "not yet projected" predicate, so a tenant's
timeline stopped at the first batch and every later run reported `projected: 0`; no reader
followed the merge pointer, so a merged member's own app read the dead record for ever and a
guardian whose duplicate was merged was refused their own dependent; `apply_tag` returned
`applied: True` for a write it had not made and a removed tag could never be re-applied;
`find_duplicates` re-queued the pair an operator had just dismissed, and re-raised the pair it
had just merged -- which `check_merge` then refuses for ever; and two timeline projections
declared fields their events do not carry, so one stored `Consent granted for None` into a table
with no UPDATE grant. `reverse_merge` also discarded the row count of its guarded UPDATE, so two
concurrent callers were both told the person was restored.

Four acts took an actor and recorded nobody -- `verify_contact_point` (which returned
`asserted_by` to the caller as though it had), `end_relationship`, and the merge's own
relationship moves. All now carry the actor and the correlation, under constraints, because
MOD-008 audits denials and `veyro_cp_app` holds nothing in `iam`: there was no second record to
fall back on. Third module running for that shape.

Six decisions carry the module:

- **Member 360 is a projection, not a table, and every section names its source.** Paragraph
  816 is explicit: "the canonical model follows aggregate ownership rather than a single shared
  member schema". So there is no `ppl_member_360` row; `member_360` composes this module's own
  tables with the timeline, and the `sections` block says where each part came from -- including
  the seven that belong to modules this repository does not have. Returning `"invoices": []` for
  a member with twelve invoices would be a confident wrong answer in the place a staff member
  looks before talking to somebody.
- **The timeline stores a summary and references the event; it never copies a payload.**
  Paragraph 4021 and paragraph 4224. `ppl_timeline_entries` has no `jsonb` column at all,
  `timeline.PROJECTED` is nine entries with a renderer each, and a renderer sees **only the
  fields its projection declares** -- so an event that grows a field does not grow the timeline.
  `check_summary_fields` runs at import and refuses a renderer that reads anything MOD-008
  classifies as sensitive, which matters more here than in MOD-010: the entries table has no
  UPDATE grant at all, so a summary quoting a health note would be the least erasable copy of it
  in the build.
- **This module owns contact data, and that makes the erasure obligation its own.**
  `ppl_contact_points` holds the real address -- MOD-007 holds the authentication identifier and
  MOD-013 deliberately holds a digest -- so MOD-009's executor was extended to reach `plt01`,
  through `ppl_identity_links`, and four columns now have a clear rule behind them. A subject
  with no recorded identity link reaches none of it and every `plt01` target is recorded
  `blocked` with that reason rather than `done / 0`, which is MOD-009's own review finding one
  plane over.
- **Nothing is deleted, and a merge is reversible because of it.** Paragraph 1300 forbids
  cross-domain write-table access, so a merge cannot find the losing person's rows in other
  modules: it points the record at the survivor and leaves every reference intact. The merge
  record itself carries no UPDATE on what happened and no DELETE at all, so "was this person
  ever merged, by whom, on what evidence" survives the reversal. What the reversal cannot
  restore is stated in its own response rather than implied.
- **The duplicate score is explainable or it is useless, and nothing is fuzzy.** An operator
  asked to merge two records is being asked to destroy one of them, so every signal is named,
  `dedup.WEIGHTS` is the whole table, and `AUTO_MERGE_THRESHOLD` is `None` because paragraph
  10200 requires a human. There is no edit distance and no phonetic match: every one of those
  produces a confident wrong answer on two siblings at one address with one family email. The
  under-detection is the stated cost, and it fails toward leaving two records alone.
- **Optimistic concurrency, because two front-desk staff editing one profile is the ordinary
  case.** Paragraph 1331 asks for it; every mutable aggregate carries `version`, every update
  takes the version the caller read and guards the UPDATE with it, and the row count is checked.
  Last-write-wins discards whichever finished first, which is nobody's intent and leaves no
  trace.

Things worth knowing before extending it:

- **A person id is tenant-scoped, deliberately.** A person known to two tenants is two rows,
  because a tenant must not be able to learn that its member trains somewhere else. The
  cross-tenant link, where one exists, is MOD-007's bare `person_id`, and `ppl_identity_links`
  is the only place the two planes meet -- with **no foreign key**, because `iam` is under a
  separate role that holds nothing here. A stale link is possible and is the gap.
- **An unknown birth date is not a minor**, which is the uncomfortable direction and the right
  one: treating every undated person as a minor would make a guardian relationship mandatory
  before anybody could read the record of a member who never gave a birthday, which is most
  leads. The threshold is eighteen, stated in `visibility.is_minor` rather than configured,
  because the sources name minors four times and give no age.
- **`health` and `biometric` are unreadable in this build, by anybody.**
  `member.health.read` is `biometric_sensitive`, which maps to AAL 3, which needs a hardware
  authenticator MOD-007 cannot verify. So a health-classified note or custom field is stored,
  counted and masked for every caller -- the same deliberate dead end MOD-008 records for
  break-glass support access. `visibility.UNREACHABLE_CLASSES` names it rather than leaving it
  to be discovered.
- **A redacted record still exists.** Telling a coach that a member has no health notes when
  they have three is worse than telling them there are three they cannot read; paragraph 10280's
  "minimum necessary" is not zero knowledge that the context exists.
- **A note is insert-only and so is a timeline entry.** A note that could be edited is a note
  nobody can rely on in the dispute it exists for, so a correction is a new note and a
  retraction is a withdrawal that leaves the original visible. The consequence is that both
  survive an erasure, which is declared.
- **A relationship ends rather than being re-pointed.** `from_person_id`, `to_person_id` and
  `kind` carry no UPDATE grant, so "who was this member's coach in March" stays answerable --
  and a merge moves a relationship by ending it and inserting the replacement, which leaves both
  halves visible.
- **A custom field's type and sensitivity are final.** Re-typing one leaves unparseable values
  readable and re-marking one `none` unmasks in bulk what was collected as health data, so
  neither carries an UPDATE grant; retiring it and declaring a new one is the path. There is no
  `secret` type and no free-form object type, for MOD-012's reason.
- **Two member profiles do not combine in a merge**, and `plan_merge` says so before anybody
  agrees. Combining them would mean silently choosing which lifecycle state and which member
  number survive, and a member number may be on a card and a turnstile.

Known gaps, deliberate:

- **A post-gate refusal is recorded nowhere.** The guardianship check runs after the gate has
  already allowed, and MOD-008 audits denials -- so a refused attempt on a minor's record
  reaches no audit log. Both reviewers raised it. Closing it needs either an audit entry MOD-008
  does not currently write or the check moved into the gate as a request attribute, which is the
  next bullet.
- **No request attributes reach the gate from this module.** Every `permit` call is action-only,
  so IAM-03-R02's attribute policies cannot be targeted here: a `deny` naming `is_minor` fires
  on every person read (fail-closed, and it will surprise the tenant that writes one) and an
  `allow` naming `assigned_to` can never fire. The migration header says the service "can supply
  `is_minor` and `is_assigned` -- which it must"; it supplies neither.
- **A brand- or location-scoped role cannot use this module at all.** Both `permit` and
  `held_permissions` resolve against the tenant-wide default scope, and a narrower assignment
  covers nothing, so a single-brand front desk is refused every read. The direction is safe -- a
  narrower role unmasks less, never more -- and the product consequence is real.
- **An erased minor stops being a minor.** The erasure clears `date_of_birth`, so
  `guardianship_satisfied` then opens the residual record -- the member number and the
  non-health notes -- to any `people.person.read` holder. Fail-open, and the smallest honest fix
  needs an erased marker the guardianship check can read.
- **A merge copies and nothing cleans up.** The source keeps its contact points, notes, tags and
  custom values and the survivor gets its own; `reverse_merge` says so in `not_restored.why`
  rather than implying a move. Making it a true move needs DELETE grants this module
  deliberately lacks.
- **No search.** Paragraph 4218's permission-aware search index with a mandatory query
  pre-filter is ENG-01's, and a `LIKE` scan presented as search would be a read path with no
  freshness contract and no pre-filter. The duplicate detector draws its candidates through the
  indexes instead, which is the one place this module needs to find people by a value.
- **Nothing drives the timeline projection.** `project_timeline` is called by a route and by
  tests; no worker loops on it -- the same missing runtime as MOD-007's challenge sweep,
  MOD-009's retention sweep, MOD-010's relay, MOD-011's objectives, MOD-012's rotations and
  MOD-013's digests. The seventh module to want it, and the third where the absence changes the
  product: a timeline nobody projects stays empty.
- **A verification is recorded, not performed.** Nothing here sends a code or reads a reply, so
  `verify_contact_point` records that a named actor asserted it at a time -- the same shape as
  MOD-012's `validated` install state, and for the same reason.
- **No segments.** PPL-01-R05 names them beside tags and custom fields; a segment is a saved
  query and this module has no query language. Tags are the static half and are built.
- **No progress media.** Paragraph 1320 lists it among the privacy controls; it needs an object
  store and a residency decision, both unmade, which is the same wall MOD-009's data export
  hits.
- **The timeline is nine event types.** Everything from MOD-005, MOD-011, MOD-012 and MOD-013 is
  deliberately absent: a notification being sent is a delivery record rather than a life event,
  and one entry per notification would bury the five that matter. A module that wants its events
  there adds a `Projection` with a summary somebody wrote, which is the review point.
- **A relationship has no scope.** PPL-01-R06's kinds are tenant-wide, so a coach-client link
  does not say which location it applies at. MOD-008's `is_assigned` attribute can be derived
  from it, and nothing does that yet because no read path asks for it.
- **A merge does not reach another module's rows, and cannot.** The pointer is the mechanism and
  every reader has to follow it; `merge.survivor_of` is the walk, and no other module calls it
  because no other module exists yet.

**MOD-016 (COM-02 catalog, pricing, promotions and bundles) -- implemented, gated and
reviewed.** Sixteen `cat_` tables in `plt01` under the same forced RLS, `app/catalog/` beside
them, and twenty-four HTTP routes. Working: a product catalogue over COM-02-R01's eight types
with localized text and merchandising order; price books matching on COM-02-R02's dimensions;
time-bounded prices whose figures no runtime role may edit; promotions with eligibility rules,
stacking groups and approval thresholds; coupons with usage limits counted from an insert-only
ledger; a two-party discount request and approval; deterministic price resolution with a stored
explanation; and bundles with fulfilment obligations, partial delivery and reversal. Seven
events are produced. Proven: isolation checks 67-72, mutation-tested in two rounds -- 431 before the
review and 483 after it, of which 482 were caught by the check that guards what was broken and
one was a no-op statement granting a privilege the role already held; 50 domain unit tests with
no database; 43 HTTP tests.

Six decisions carry the module:

- **A price's figures are never updated, and the privilege is what says so.** `cat_prices`
  carries UPDATE on the four supersession columns and nothing else, so an order resolved last
  March re-derives to the same figure a year later because the row it read cannot have changed.
  `cat_prices_one_per_start` makes the choice between two rows deterministic rather than
  planner-dependent.
- **A resolution is a receipt, insert-only in full.** Three constraints hold its arithmetic in
  the row: the parts add up, the discount does not exceed what is being discounted, and the
  discount is not negative. Paragraph 10220 requires the resolution to return an explanation; a
  row with an empty one is refused by the schema.
- **A coupon is redeemed in the same transaction as the resolution it discounts.** This is the
  module's money correctness and it is the lesson MOD-010's `append_event` teaches: a control
  and the state it bounds commit together, or the control is decoration.
- **The two-party discount.** A request records what was asked and who asked, derived from their
  session; an approval decides a request and copies every figure from it. `approved_by <>
  requested_by` then compares two identities the server derived.
- **An approval is spendable once and expires.** Single use is a partial unique index on the
  resolution that cites it, because the approval table has no UPDATE grant and so cannot be
  marked consumed.
- **A bundle's deliveries are rows, and a mistake is reversed by another row.** `reversed`
  subtracts, which is MOD-015's credit note applied to an obligation and the only correction
  path a table with no UPDATE and no DELETE grant can have.

**Three reviewers worked this module in parallel -- the schema, the Python, the request path --
and all three returned CHANGES_REQUESTED. Twenty-seven blocking defects**, every one executed
rather than reasoned about, and the largest single cause was one shape: **the module decided the
price on one route and recorded the facts that bounded that price on other routes nobody had to
call.** Carried forward as rules:

- **A control and the state it bounds commit together, or the control is decoration.**
  `resolve_price` applied a coupon's discount and read its usage count; only `redeem_coupon` --
  a separate route the caller was free never to call -- wrote the ledger that count came from.
  One single-use 90% code priced six sales on the routine till permission, and
  `max_total_redemptions`, `max_per_subject` and every other usage rule were decorative on the
  only path that sets a price. The permission catalogue's own justification for that permission
  being routine said a redemption "cannot exceed the limits counted from the ledger beside it";
  the discount that reached the customer did not go through a redemption at all.
- **A separation of duties needs two acts, or it is unverifiable in principle.** `requested_by`
  was a field on the approval body with no foreign key and no request record behind it, so all
  three reviewers independently approved their own 99.99% override naming a requester who does
  not exist -- and spent it in the same session. There was nothing a stricter check could have
  consulted. MOD-009's `guardian_subject_id`, MOD-013's `bypass_policy_ref` and MOD-014's
  guardian field are the same shape; this is the fourth, and the first where collapsing two
  acts into one insert is what made it unfixable rather than merely unfixed.
- **An authority with no expiry and no consumption is a bearer token.** `_check_approval`
  verified the variant, the list amount and the depth, and then nothing ever happened to the
  row: a one-off goodwill decision became a standing authority to sell that variant for 0.01,
  five times over, exercisable by the cheapest permission in the module. It also ignored the
  currency, so an approval reasoned and audited as "100.00 JOD down to 1.00 JOD" authorised the
  same minor-unit counts in USD -- the one comparison MOD-015's money discipline forbids.
- **A status selected and discarded is a control that does not exist.** `resolve_price` read
  `p.status` into a variable it never used, so a product nobody had ever published sold and a
  product explicitly retired went on selling. `catalog.product.publish` gated a flag and an
  event and bought nothing on the sales path, and retirement -- the module's only stated way to
  withdraw something -- had no effect at all. The unused select was the trace of the check that
  was intended.
- **Derive, never accept, reaches the dimensions that choose a price.** `customer_segment` and
  `brand_id` were free strings on the resolve body, and a routine AAL-1 session took a 90%
  reduction by sending `"customer_segment": "staff"` -- with the stored resolution citing the
  staff book as its authority. MOD-008's finding, which this module had to learn separately.
  The segment now comes from the subject's own MOD-014 tags and the brand from the location.
- **A control decided by matching words in prose is a control anybody can edit away.**
  `redeem_coupon` refused only if the reason text contained one of `("redeemed", "revoked",
  "ended", "not started")`, which made four English words the whole enforcement of every usage
  limit here: a draft promotion reads "is draft, not active" and matched none of them, so a
  code on a campaign nobody activated redeemed while `/catalog/promotions/validate` said it
  would not -- and a promotion keyed `extended.summer` contains "ended", so a benign rejection
  naming it refused a legitimate redemption. `Eligibility.blocks_redemption` now asks the
  inverse question, so a code nobody thought about refuses.
- **A rule that cannot be evaluated must refuse.** `max_per_subject` was enforced only against
  callers who volunteered a subject: `by_subject` reads 0 both for "never used it" and for
  "nobody said who this is". `promotions.Usage.subject_known` is the distinction. And a usage
  rule on a non-coupon promotion was inert by construction, since nothing writes a redemption
  for a promotion reached without a code -- refused at the write now, because there is nowhere
  else to say it.
- **A guard that admits a state nothing can leave is worse than no guard.** The fulfilment
  ledger carried `UNIQUE (order_reference, bundle_id, variant_id)`, which both
  `bundles.outstanding` and `check_fulfilment` contradicted -- they count only `delivered` rows
  and sum partial deliveries, neither of which that index allowed. A transient provider failure
  recorded `failed` and the retry was refused for ever, with no UPDATE and no DELETE grant: the
  member had paid, the obligation stood, and no call in the module could satisfy it.
- **An irreversible act must not be declarable on a routine permission** -- MOD-013's rule,
  recurring. A routine AAL-1 session recorded all ten sessions of a ten-session bundle as
  delivered and the real fulfiller was then refused permanently. "The record it writes is
  insert-only" was offered as why that was safe and was in fact what made it unrecoverable.
- **Evidence with nobody's name on it answers nothing** -- the fourth module. Activating a price
  book, the act that switches a tenant's prices on, recorded nobody: the table had no
  activation columns at all while every sibling act in the module was attributed. So did
  retiring a product and superseding a price, and neither published an event, so a consumer
  tracking the catalogue saw things appear and never disappear.
- **A value can carry anything, so nothing free-text goes in the outbox.** `bundle.fulfilled`
  carried `order_reference`, caller free text, into the one store no erasure reaches. Third
  occurrence after MOD-010's `cfg_exposures.subject_id` and MOD-013's `notification.failed`
  reason.
- **A second rounding rule is a pair of numbers that disagree on a receipt.**
  `approve_discount` computed its basis-point figure with `round(... * 10_000 / list)` --
  Python's banker's rounding on a float -- while every other figure in the module goes through
  `money.round_half_up`. It disagreed with the resolver on ordinary inputs and overflowed
  float's exact-integer range at the top of the allowed amount.

Also found and fixed: an unneeded `approval_id` was stored unchecked, so a resolution that
needed no approval could permanently cite an unrelated one and the table that *is* the audit
read as though it had authorised a price it has nothing to do with; `publish_product` counted
any non-superseded price including one in a draft or retired book or outside its window, so the
till the check exists to protect could still stop working; an idempotency key reused across two
different codes returned the first redemption with `repeated: True`, telling the caller the
second coupon had been redeemed when it had not; an unknown channel answered 409 rather than
422; a non-coupon promotion with no targeting rule applied to every sale in the tenant, which
halved the price for every customer the moment somebody activated a staff discount; and
`cat_bundle_items` was the only insert-only table in the module with no actor on it.

**And the module's own prose claimed a control it did not have.** Three places said `cat_prices`
"carries no UPDATE grant for any runtime role at all" while the grant included `effective_to` --
the one column whose value decides whether a price is in force, so granting it was granting the
power to withdraw a price with no record of who did it. Nothing in the service ever wrote it.
`cat_price_books` had `priority` and `effective_to` granted and unwritten for the same reason,
and both re-aim every price already written into the book. All three are out of the grants, and
the header now says what the grant actually covers.

**Four schema repairs came out of the mutation sweeps rather than the reviews**, which is the
argument for running them:

- **84 of 431 mutations were missed in the first round, and 80 were `DROP NOT NULL`.** Nothing
  in 11,000 lines of isolation suite had ever read `attnotnull`, in any module, and check 71
  carried a hand-written list of 37 (table, column) pairs. Two reasons it matters more than "a
  NULL where a value was expected": a NOT NULL is what makes a sibling CHECK bite --
  `amounts_sane` evaluates to NULL and therefore passes once `list_amount_minor` is nullable, so
  "an override cannot exceed the list price" stops being enforced -- and **MATCH SIMPLE**, where
  a NULL in any column of a composite foreign key skips the whole check, so dropping NOT NULL
  from `cat_prices.price_book_id` silently switches off a tenant-carrying parent reference that
  check 69's set comparison cannot see. The pin is now the whole catalogue, compared both ways.
- **`cat_price_resolutions_adds_up` was proved on one side only.** A reviewer weakened it to
  `final >= list - discount` and the suite reported 72/72: in that world `final_amount_minor`
  has no upper bound, so a stored receipt reading "10% off 450.00" could charge 900.00, in a
  table with no UPDATE and no DELETE grant. The one invariant the migration itself calls the
  defect nobody would spot by reading the number.
- **Two constraints were proved by a sibling.** `cat_bundle_fulfilments_outcome`'s case left
  `detail` NULL, so `failure_explained` fired first -- and with the outcome domain dropped,
  `pending` stores and `bundle_status` reads the obligation as neither met nor failed.
  `cat_eligibility_rules_kind` was subsumed outright by `operand_matches_kind`, which names all
  seven kinds: the repair was to delete the redundant constraint rather than to write a case
  that cannot exist.
- **The primary keys were unproven.** Their drops failed at mutation time because dependent
  foreign keys block them, so the mutation never ran and the sweep recorded a false catch. They
  need `CASCADE` to actually execute -- this file's own MOD-014 trap, one level up.

Things worth knowing before extending it:

- **`resolve_price` is the sale, not the quote.** It redeems the coupon it applies, so a caller
  that wants to know what a code is worth without consuming it uses
  `/catalog/promotions/validate`, which is a read with no side effect.
- **`channel` is still the caller's word.** There is no server-side source for what kind of
  client is calling, so a channel-scoped price book is only as trustworthy as the client. It is
  bounded to the seven and recorded as a gap rather than papered over.
- **A segmented price book is unreachable for an anonymous sale.** The segment comes from the
  named subject's tags, so a walk-in with no person record cannot be given a corporate rate.
  That is the correct direction: the alternative is letting the till say who it is selling to.
- **There is no tax rate anywhere.** `cat_tax_categories` names a regime and carries no
  percentage -- MOD-015's precedent, where `issue_invoice` takes a rate rather than inventing
  one.
- **A published product with no live price cannot be published**, and the check is over active
  books and live windows rather than over any row at all.

Known gaps, deliberate:

- **Nothing sells anything.** This is the catalogue and the price; the order, the cart and the
  payment are MOD-017's. `order_reference` is free text because the module that owns orders does
  not exist, so a redemption or a fulfilment can cite a reference nothing resolves.
- **No tax calculation.** A tax category is a classification waiting for an engine.
- **No approval threshold by default.** `approval_threshold_bp` defaults to 0, which means
  never, so paragraph 10220's "high discounts require explicit permission" is opt-in per
  campaign: a 100% automatic promotion created with the default needs no approval at any depth.
  Defensible as a product decision and worth saying out loud, because the control is off out of
  the box.
- **A price can be written with an arbitrary past `effective_from`.** The stored resolution is
  immutable so a receipt stands, but a *re-derivation* of a historical order changes.
  `catalog.price.write` is financial class, which is the only thing bounding it.
- **No segments of the kind COM-02-R02 implies.** A customer segment is one tag key on a
  person, chosen by lowest key when somebody has several. A richer segment -- a saved query, or
  a tier derived from spend -- needs what PPL-01-R05 calls segments and MOD-014 does not have.
- **A coupon's limit is serialised per code, not per tenant.** `FOR UPDATE` on the coupon row
  closes the race the reviewers demonstrated; two different codes on one promotion still race
  each other's `max_total_redemptions`, which is counted per promotion.
- **Nothing expires anything on a schedule.** A promotion's window and a price's window are
  read at resolution time and nothing sweeps them, which is the same missing worker runtime as
  MOD-007's challenge sweep, MOD-009's retention sweep, MOD-010's relay, MOD-011's objectives,
  MOD-012's rotations, MOD-013's digests and MOD-014's timeline projection. The eighth module
  to want it, and here the absence is benign: an expired promotion stops applying because the
  resolver reads the window, not because a sweep retired it.
- **An approval's window is twelve hours and the sources state none.** `APPROVAL_VALID_FOR` is a
  judgement -- a shift is the unit of time a till decision belongs to -- and it is a decision
  somebody may want configurable.
- **Five free-text columns are residue an erasure cannot reach**: the resolution's explanation
  (which includes any override reason a caller typed), the request's and the approval's reasons,
  and the fulfilment's detail, external reference and order reference. All declared in
  `SUBJECT_COLUMNS`; closing it needs an erasure path into `plt01` for prose, which is a
  different problem from the per-column tombstones MOD-014 added.
- **Bundle fulfilment records what somebody says happened.** Nothing here grants an entitlement
  or books a session, so the ledger is what COM-01 and OPS-01 will write to -- the same shape as
  MOD-012's `validated` install state and MOD-014's contact verification, and for the same
  reason.
- **A `manual` promotion is storable and unreachable.** `_applicable_promotions` excludes it
  along with `coupon`, because the whole meaning of the kind is "somebody applies this by hand"
  and nothing in this module does. The manual path here is `pricing.override`, which needs a
  recorded approval. Excluding it was a fix, not a gap: the first version excluded only
  `coupon`, so a `manual` promotion applied automatically to every sale in the tenant -- the
  defect a reviewer found for `staff_discount`, in the one kind no targeting rule could fix.

**Next.** MOD-017 (Commercial Core: orders, carts, payments and refunds) is what MOD-016
unblocks and is the natural next module -- it is also where `order_reference` stops being free
text. MOD-019 (Scheduling Pilot) is unblocked by MOD-014 and independent of both. Nothing in the
Foundation wave is left except MOD-006, the Compose Multiplatform qualification, which is a
client-side proof the server plane does not need.

Three things named rather than done remain open across the build: the platform plane is
unauthenticated -- and MOD-012 makes that worse, since the definition catalogue decides which
scopes a tenant may hand to a third party -- no worker runtime exists for the eight schedules
that want one, which MOD-011 makes the most pressing because an objective nobody evaluates
raises no alert, and there is no key vault, which is what MOD-009's crypto-shred, MOD-007's
TOTP seeds and MOD-012's inbound webhook signatures are all waiting on.

`Decision.mask` is no longer on that list. MOD-014 applies it, which closes the five-module gap
-- and note what closing it took: `permit` had to return the gate rather than the session, and
every read had to take the masked-field list as a **required** argument. A read path that could
be called without it is a read path somebody calls without it, which is how the gap survived
five modules in the first place.

MOD-014 also left a counterpart for MOD-013's unverifiable `recipient_id`: `ppl_identity_links`
now relates an identity to a person, so a notification could be bound to a person record rather
than to a caller-supplied uuid. Nothing wires the two together yet. **MOD-016 is the first
module to read MOD-014's tags for a decision of its own** -- the customer segment that chooses a
price book -- which is the shape the rest of that wiring will take.

**The recurring lesson across the last four reviews, stated once.** Every module since MOD-011
has shipped at least one control keyed on a value the caller supplies, shape-checked and never
checked for correspondence with anything. MOD-016 shipped four of them and two were worse than
the earlier ones: a separation of duties that no stricter check could have rescued, because
there was no second act to compare against, and a usage limit whose counter was never moved by
the act it bounded. **The question to ask of any control is not "is this field validated" but
"what did the server derive, and did the thing I am bounding write the state I am reading".**

Module ids are in `tools/mission_runner/module_catalog.json` and are not the TSD's section order.
MOD-006 (Compose Multiplatform qualification) is unbuilt; MOD-007's dependency on it is a
client-side proof that the server plane does not need.

Finish a module's real requirements and tests, then move on.

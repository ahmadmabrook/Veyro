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

**Next.** MOD-012 (Integration Adapter Core) and MOD-014 (People, Profiles & Member 360) are both
unblocked. Three things named rather than done remain open across the build: the platform plane is
unauthenticated, `Decision.mask` is computed on every allowed read while no read path applies it,
and no worker runtime exists for the four schedules that want one -- which MOD-011 makes the most
pressing of the three, because an objective nobody evaluates raises no alert.

Module ids are in `tools/mission_runner/module_catalog.json` and are not the TSD's section order.
MOD-006 (Compose Multiplatform qualification) is unbuilt; MOD-007's dependency on it is a
client-side proof that the server plane does not need.

Finish a module's real requirements and tests, then move on.
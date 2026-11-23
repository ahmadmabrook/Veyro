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
  commercial/           MOD-017: lifecycle.py, entitlements.py, invoicing.py and
                        collections.py decide; service.py holds the two locks the module
                        turns on -- the grant a reservation draws from and the serial
                        counter an invoice is numbered by
  scheduling/           MOD-019: recurrence.py converts each occurrence on its own,
                        availability.py reads each rota window in its own zone, resources.py,
                        conflicts.py, capacity.py, publishing.py and substitution.py decide;
                        service.py holds the one thing that is load-bearing -- take_hold
                        counts under FOR UPDATE on the session, in the transaction that
                        writes the hold
  booking/              MOD-020: policy.py decides the member's side (a quota no booking
                        order can defeat, a calendar bucket in the session's own zone),
                        waitlist.py the queue, attendance.py what a booking becomes,
                        consequence.py what it costs, appeals.py who may decide and against
                        what; service.py owns no capacity at all -- it takes MOD-019's hold
                        on its own connection, so a booking and its seat commit together
  ledger/               MOD-018: accounts.py, wallet.py, periods.py, recognition.py and
                        settlement.py decide; service.py holds the one thing that is
                        load-bearing -- post_journal takes a connection, so a posting commits
                        in the transaction that caused it
  devices/              MOD-021: catalog.py, enrollment.py, safety.py, policy.py and
                        commands.py decide; service.py writes, and `issue_command_on` takes
                        a connection so a command and the state that authorized it commit
                        together
  access/               MOD-022: zones.py classifies and decides what a reader may be told,
                        policy.py evaluates one presentation, credentials.py hashes and
                        bounds a rotating code, occupancy.py counts from events, offline.py
                        judges a reconciliation; service.py takes MOD-021's command on its
                        own connection, so a decision and the unlock it caused commit
                        together -- and no path writes a decision at an exit
  errors.py             the five service errors every module's service raises
  worker/               the scheduled jobs: names.py is the closed set both the registry and
                        MOD-011's catalogue read, registry.py says what each job calls and the
                        role it needs, runner.py owns the tick and the failure isolation
backend/migrations/     platform/, tenant/ and product/ SQL, applied in that order
backend/tests/          unittest suites; tests/sql/isolation.sql is the isolation proof
backend/scripts/        verify_db.sh rebuilds the database and runs the isolation suite
knowledge/              decisions and module notes
tools/                  governance and lint tooling (see "Tooling that still earns its place")
web/                    the Next.js operator surface (see "The web app")
  src/design/           ds.json is the design system; generate.mjs emits the CSS tokens and
                        refuses an unresolved dark reference
  src/lib/              api.ts is the only place a request reaches the backend; device.ts is
                        the device label the fixture has to agree with
  src/components/       nav.tsx filters the sections by the gate; nav-link.tsx is the only
                        client component in the app, and it exists for one ARIA attribute
  tests/unit/           Node's own test runner, no dependencies
  tests/component/      Vitest and Testing Library
  tests/e2e/            Playwright, against a real uvicorn and a real database
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

**And those are not what CI runs.** CI runs eleven more steps -- the governance structural
check, its own validator suite, the domain-closure check and suite, the runner and
trusted-gate suites, the screen-contract identity check, and the web app's `audit:ci`,
`design:check`, `tokens:check` and `test:foundation`. Running the list above is not running
the gate, and that cost a red `main` on **both jobs at once**: an ADR header written as prose
parsed as no header, and `design:coverage` refused three backlog entries whose module had
just landed -- a check this file's own session wrote to catch a stale excuse, firing correctly
on its author. One command covers everything a local run can answer:

```bash
tools/local_ci.sh
```

It omits only what needs Docker (the container build, its smoke test, the rollback rehearsal)
and the browser suite, which needs a provisioned fixture and a port. **It also runs Python
with `-B`, as CI does**, because the domain-closure check refuses a `__pycache__` inside a
lane root and an ordinary local test run creates one -- so the first version of the script
failed twice on an artefact of itself while CI was clean.

These need `backend/requirements-dev.lock` installed in the active interpreter. The repository
carries a `.venv/` (gitignored) created for this purpose; if `ruff`, `mypy`, `fastapi` or
`psycopg` is missing, install the lock into it rather than working around the gap. Say so if the
install is refused — CI covers these, but a local red is cheaper than a red `main`.

Run the scheduled jobs once, over every schedulable tenant, and see what they did:

```bash
(cd backend && VEYRO_ENV=local VEYRO_RELEASE=dev VEYRO_DATABASE_URL=postgresql://postgres:veyro_dev@127.0.0.1:55432/veyro python3 -m app.worker --once)
```

It prints a JSON report and exits non-zero if any run failed. Drop `--once` to loop; add
`--job events.relay` or `--tenant <id>` to narrow it. The e2e fixture runs exactly this
command as its last step, so the browser suite asserts against rows a scheduled job wrote.

Passkey authentication needs two settings and refuses without them, which is deliberate: the
relying party id binds a credential to a domain and guessing it would either break every
credential or accept one made for a domain nobody controls.

```bash
export VEYRO_WEBAUTHN_RP_ID=veyro.test VEYRO_WEBAUTHN_ORIGINS=https://veyro.test
```

`config.load_settings` demands both or neither, refuses an origin carrying a path or a
trailing slash, and refuses a plaintext origin outside `local`. With neither set, enrolment
still works -- storing a credential is not authenticating with one -- and
`/auth/passkey/login` answers 422 naming the configuration rather than 401 naming a
credential.

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

**A blocker is external or it is not a blocker.** Owner instruction of 2026-11-23. The only
thing that may stop this session is something it cannot obtain: the four reserved actions
above, an account or a credential with a third party, a physical device, or a policy that is
the owner's to set. **Everything else is work.** A missing module is work. A missing table is
work. A decision nobody has written down is a decision to make, because the delegation hands
over ordinary engineering, product, architecture and infrastructure decisions -- so "this needs
a judgement the sources do not state" is not a reason to stop, it is the next thing to decide
and record. "No search index", "no CRM", "no handover note column", "no service worker", "no
trial state", "which period is due" and "which objective is due" were all written in this file
as though they were blockers; none of them is.

The distinction is not about size. A service worker and a write queue for the Front Desk is
weeks and is still work; a card charge is one line and is still external. The test is only
whether anything outside this repository has to arrive first.

**What that means for how a gap is written.** A gap note says what is not built and why it is
not built *yet* -- which is a priority, a cost, or a dependency on other work. It may name an
external blocker, and then it says which one and what would clear it. It may not name a
judgement as the obstacle. This session found three notes doing exactly that and one that had
buried a defect behind an accurate sentence; the rules file records all four readings.

### The external blockers, in full

Seven, and nothing else in this repository is one. Each says what has to arrive and what it
would clear. **Everything built up to the seam is this session's work and is not waiting on
any of them**: an adapter with a local implementation, a recorded claim where a provider would
answer, and the half that must be correct whatever the provider turns out to be.

1. **A payment provider, in test mode.** Which provider, and its test keys placed in a file by
   the owner -- this session does not type payment credentials. Clears FD-01 and FD-04 at the
   door, the sales half of the Admin surface, MOD-015's and MOD-017's stored payment methods,
   and MOD-016's till. Real charges stay reserved; test mode is the thing to ask for.
2. **A messaging provider** for email and SMS, test credentials likewise. Clears the dispatcher
   MOD-013 was built around, FD-05's invitation by text, FD-07's shift report, MOD-017's
   dunning messages and MOD-020's waitlist notification. **MOD-013 is otherwise complete**:
   it authors, claims and settles a message and sends nothing.
3. **An object store, and the residency decision that goes with it.** Residency is owner policy
   in the isolation rules. Clears member photos (FD-01's 40px row, FD-02's 44px confirmation),
   MOD-009's data export, MOD-014's progress media, MOD-021's diagnostics bundle and MOD-010's
   event archive. A local store for development needs nobody; a deployed one needs the region.
4. **A key vault.** Clears MOD-007's TOTP seeds, MOD-009's crypto-shred, MOD-012's inbound
   webhook signatures and MOD-021's device certificates -- which is also MOD-022 opening doors
   on an identity nothing verifies. **The seam is this session's work**: an interface with a
   local backend, so only the managed instance is external.
5. **An identity provider** for IAM-01-R04's OIDC/SAML federation. Clears CON-16's sign-in and
   therefore MOD-015's Console screens, the only implemented module with no surface. The
   protocol work is this session's; the tenancy at Okta, Entra or Google Workspace is not.
6. **Door hardware and readers.** Clears MOD-021's gateway and MOD-022's "nothing opens a
   door", plus the anti-tailgating that would let an occupancy count be enforced rather than
   advisory. Physical, so no amount of code substitutes.
7. **Retention policy.** Owner policy, named in the isolation rules beside regions and keys.
   Clears MOD-009's retention sweep, the one sweep where being wrong is unrecoverable.

**An event transport is deliberately not on this list.** MOD-010 names EventBridge, SNS,
per-consumer SQS and an S3 archive, and a managed one would need an account -- but a transport
is an interface with implementations, and writing one that runs here is work rather than a
wait. The same reasoning retires "no histogram store" for MOD-011's percentiles: a bucketed
histogram in the store that already exists is a schema decision, which is delegated.

**The coverage check enforces this now, and what it found is the size of the mislabelling.**
`web/src/design/coverage.mjs` admitted five cause tokens -- `module:`, `owner-reserved:`,
`data:`, `store:`, `client:` -- and three of those named this session's own work, so a screen
could sit in a blocked list while nothing outside the repository was missing. **Thirty-three
of the forty-five did.** `BLOCKED` now admits eight causes and seven of them are the list
above, one token each, so a blocked screen names a thing that has to arrive; `BACKLOG` takes
the rest and each entry says where the work lives -- `MOD-0NN:` for the module that owns it,
`work:` for a module that exists and does not yet do what the screen draws, `client:` for the
one screen that is a service worker. Proven: 14 mutations, every one caught.

Three things fell out of it that are worth more than the count:

- **The two vocabularies are disjoint, which is what makes the distinction hold.** A screen
  whose work is undone is not blocked by the provider waiting at the end of it, so an external
  token in a `BACKLOG` reason fails and a `work:` reason in `BLOCKED` fails. FD-05 is the
  precedent this file already set -- CRM is mine, and its invitation by text is a seam rather
  than a blocker -- and the check now carries it for all ninety screens.
- **`MOD-0NN` made "which module owns this screen" checkable for the first time.** The old
  `module: CRM` named nothing a check could look up; an id is in `module_catalog.json` or it
  is not, and `PACKAGE` maps it to the `backend/app/` package that exists once it is built --
  so a backlog entry for a module that has since landed fails, which is the stale-excuse
  direction. That is also a partial answer to this file's own "nothing maps a screen to a
  module": 33 unbuilt screens now name theirs, and `screen-contracts.yaml` still names none.
- **A messaging provider is on no Admin or Front Desk screen's critical path**, which the
  token set made visible by leaving `messaging:` unused. Every screen here that would send --
  the staff invitation, the broadcast, the class cancellation, the shift report -- needs work
  done first. `vault:`, `identity:`, `hardware:` and `retention:` are unused for a different
  reason: they block modules rather than screens on these two surfaces.

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
- **The surface is read-only.** `web/` renders the typed registry with each value's scope and
  the flags with the reason each resolved by -- see "The web app" -- and every write is a form
  that does not exist: declaring a key, publishing a value, rolling one back, writing a
  targeting rule, engaging a kill switch. Publishing a value and changing a flag are
  financial-class permissions, which is the same reason the hierarchy surface is read-only.
- **There is no route that lists feature flags.** `/flags` evaluates them for one subject, so a
  board can only show what the flags say for somebody rather than what flags exist -- and a
  flag whose evaluation returns nothing is indistinguishable from one that is not there. The
  surface says so rather than implying a complete list; closing it needs a listing route.

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

**MOD-007 (IAM-01 identity, authentication, passkeys and device sessions) — implemented,
reviewed, and the first module with a surface that writes.** A third plane: schema `iam`, role `veyro_iam_app`, seven tables, all
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
- **AAL-3 is reachable now**, and `/auth/require/*` says so in a `reachable` field computed from
  `VERIFIABLE_FACTORS` rather than written down. It needs a device-bound passkey, which needs
  the WebAuthn verification this module refused to fake and now does for real. No surface in
  this build enrols one, so the route is the only way there.
- **The session listing is bounded and filterable**, which it was not until something rendered
  it: `list_sessions` takes `limit` (default `SESSION_PAGE = 50`, refused above it) and
  `live_only`, because an unbounded read of every session an identity ever opened is a page
  describing every device that person has signed in from. The bound belongs here rather than in
  the client for the same reason MOD-017's listing reads are bounded on the server.

Known gaps, deliberate:

- **WebAuthn attestation is not verified, which is a different claim from the signature.** The
  assertion *is* verified now -- see below -- so a passkey is an authentication factor and
  `VERIFIABLE_FACTORS` contains both of them. What is not checked is which *model* of
  authenticator a credential came from, which would need an AAGUID metadata service and a
  tenant policy about which keys are accepted; neither exists, and neither is needed to know
  that whoever signed in holds the private key for the public one on file.
- **A passkey cannot raise an existing session.** `complete_step_up` takes a password or a
  recovery code, so a step-up reaches level 2 and no higher; level 3 is reached by signing in
  at `/auth/passkey/login` with a device-bound credential. Verifying an assertion inside the
  step-up path is the next piece and is deliberately not half-built.
  **And this gap is what `reachable` stopped being able to express.** That field answers
  whether any factor in this build reaches a level, which is now true of all three -- so a
  caller keyed on it alone concludes a step-up can get there and offers a credential prompt
  whose correct answer is still refused. The step-up surface shipped exactly that for one
  commit and CI caught it; `web/src/lib/step-up.ts` is the client's half of the distinction.
  **A route-specific ceiling is not derivable from `reachable` and nothing on the wire states
  it**, so the honest fix on the server side is for this endpoint to say what it can reach --
  which is the shape to prefer over a constant in a client the day a second caller appears.
- **No TOTP enrolment.** The algorithm is implemented and RFC-tested; storing a reversible shared
  secret needs a vault this repository does not have.
- **No OIDC/SAML federation and no SCIM** (IAM-01-R04).
- **No rate limiting.** Lockout bounds guessing against one identity -- on login, on recovery and
  on the re-authentication paths, each metered through `_verify_presented` -- but nothing bounds
  request volume. An attacker who knows an address can still lock its owner out, and a refused
  bearer token writes no audit row, because recording one would let anyone grow an insert-only
  table without limit. Both want the same missing limiter.
- **`iam.challenges` is never swept.** One row per `/auth/require/*` call and per challenged
  login, with no DELETE grant by design. Harmless at this size, and a worker runtime now
  exists -- which is exactly what makes the point: a job here would run and delete nothing,
  because no role holds DELETE on anything in `iam`. It wants the grant decision, not a job.
- **Metering cuts both ways.** Now that the re-authentication paths count failures, somebody
  holding a stolen session token can lock the victim out of their own login with five wrong
  passwords at `/auth/step-up`, and lock their recovery budget with five wrong codes. That is the
  usual lockout tradeoff and the right call, but it is a real denial of service and it belongs
  here next to the one above.
- **A tenant that does not exist used to answer 500 on `/auth/login`**, and that is fixed
  rather than carried. `X-Veyro-Tenant` is an unauthenticated claim, shape-checked and
  nothing more, so anybody can present a well-formed uuid for a tenant nobody provisioned:
  RLS then hides every identity, the unknown-identifier branch is taken, and the failure
  event's own foreign key to the tenant registry refuses the row -- a `ForeignKeyViolation`
  and a stack trace out of an unauthenticated route, once per attempt. **The foreign key is
  the only thing in reach that knows**, because `veyro_iam_app` holds no USAGE on
  `plt01_platform` by design, so the service cannot ask. A savepoint keeps that answer from
  poisoning the caller's transaction and the refusal stays identical -- one scrypt, the same
  `authentication_failed`, no new way to tell a real tenant from an invented one, because
  answering differently would be an oracle about which tenants exist. **Found by a stale
  TestSprite test** carrying the id of a tenant a later fixture run had replaced.
- **Registration is open.** Anyone holding the tenant UUID can create an identity in it. That is
  the same unauthenticated-header problem above, not a separate one.
- **`iam.identities.status` was read by four controls and written by nothing**, which is fixed
  now and is worth carrying as the finding rather than as the fix. The column admits `active`,
  `suspended` and `deactivated`; `authenticate`, the risk challenge, `recover_with_code` and
  `_session_by_token` each refuse an identity that is not `active` -- four independent
  controls, each correct -- and no service function, route or job ever set it, so two of three
  declared states were unreachable and **this product could not shut anybody out**. That is
  MOD-012's "a column implying a control nobody implemented" and MOD-020's "a declared state
  nothing writes", in the module whose subject is who may sign in. **Found by building
  ADM-STF-01**, which composes employment with access precisely because the design says why
  that column exists -- so the board could show an owner that a departed employee can still
  sign in while the product offered no way to act on it. `set_identity_status` is the writer,
  `migrations/product/0003_identity_status.sql` names the three `auth_events` kinds it needs
  (an act whose record cannot be named is an act with nobody's name on it), suspending revokes
  every live session in the same transaction, and **a session cannot suspend the identity it
  is using** -- there is no platform identity and nothing reinstates one from outside the
  tenant, so a self-suspension would end a tenant's administration with no remedy anywhere in
  the product.
- **The identity plane is a schema, not a separate database.** TSD paragraph 1151 says "Product
  PostgreSQL"; this repository provisions one cluster. The privilege boundary is real and checked
  in both directions; the physical separation is not there.

**WebAuthn assertion verification — implemented, and it is the gap this file said cost the
most.** `backend/app/identity/webauthn.py` verifies a signed assertion, so a passkey is an
authentication factor and **AAL 3 is reachable for the first time**: for five modules
`/auth/require/privileged` answered `reachable: false`, because a privileged action needs a
hardware authenticator and nothing checked a signature. `POST /auth/passkey/challenge` issues
the nonce and `POST /auth/passkey/login` verifies the assertion and opens a session at the
level its factor reaches. Proven: 33 unit tests with no database and **12 mutations against
the verifier, every one caught** by the case that names it; 20 integration tests against a
real signature and a real PostgreSQL.

**It needed the first new dependency this repository has taken.** `cryptography` is in
`requirements.txt` and both locks, because verifying an assertion is ECDSA over P-256 and the
standard library has no elliptic-curve arithmetic -- so MOD-007's standing note that
hand-rolling CBOR, COSE and ECDSA "is how authentication bypasses get written" was correct and
the answer was a library rather than a refusal. The signature check is `cryptography`'s; the
parsing is of two binary shapes the specification pins byte for byte.

Seven decisions carry it, and three of them remove something:

- **No CBOR is parsed anywhere.** A COSE_Key is CBOR and this never sees one: enrolment takes
  the SPKI DER that `AuthenticatorAttestationResponse.getPublicKey()` returns, which
  `cryptography` loads directly. A CBOR decoder in the authentication path is a larger attack
  surface than the key it decodes, and the signature proves possession either way -- a client
  that substituted a public key could only enrol a credential it holds, which is what the
  endpoint is for.
- **No migration, and no column.** Within a closed set of three algorithms there is one key
  type each, so `algorithm_for_key` derives the algorithm from the stored key: a request field
  naming it would be a caller choosing how their own signature is checked. The day a second
  algorithm over the same key type is admitted -- PS256 beside RS256 -- this stops being
  derivable and needs the column, which is why the closed set is stated where the derivation
  happens. And `iam.challenges.kind` has admitted `passkey_assertion` since MOD-007 was built:
  **two declared values nothing wrote**, this build's own recurring finding in the schema of
  the module whose subject is signing in, so the ceremony needed no table.
- **`BE`, not `BS`, decides the factor.** Backup *eligibility* is set at creation and never
  changes; `BS` says whether a credential currently is backed up, which flips the first time
  somebody turns a keychain on -- so a credential that reached level 3 on Monday would reach
  it again on Tuesday having been synced in between. The flag is signed over, so a caller
  cannot ask for the hardware factor.
- **A passkey with no user verification is refused rather than counted as something weaker.**
  It proves possession of a device and says nothing about who holds it, and this build has no
  factor name for that -- counting it would be inventing a level.
- **The challenge is consumed on any attempt, which is the opposite of "verify, decide, then
  consume".** That rule is about not destroying a credential the owner cannot replace; a nonce
  is replaceable by one round trip, and one that survived a failed attempt is a replay window.
- **The ceremony answers the same for every identifier.** A challenge is minted and returned
  whatever was typed, and a row is stored only where there is an identity to store it against;
  no credential list is returned either, because `allowCredentials` would name a person's
  credential ids to anybody who knew their address. An assertion against an unstored challenge
  is refused like any other, which is what makes the uniform answer safe -- and the uniformity
  is MOD-007's own rule, which cost it a blocking defect when a locked identity answered 423
  in two milliseconds while everything else answered 401 in fifty.
- **The relying party id and the origins come from configuration with no default.** They are
  deployment facts: the RP id is what binds a credential to a domain, which is the whole
  anti-phishing property, and guessing it would either break every credential or accept one
  made for a domain nobody controls. `config.load_settings` demands both or neither, refuses a
  plaintext origin outside `local`, and refuses an origin carrying a path -- and a build that
  has stated neither answers **422 naming the configuration** rather than 401 naming a
  credential, because "wrong credential" is what the one person who could fix it would read.

Two things to know before extending it:

- **Every WebAuthn field is strict unpadded base64url**, and the enrolment route's two fields
  were standard base64 until now. The alphabets agree on most byte strings and differ on the
  rest, so one surface of the same ceremony spoke a different alphabet from the other -- and a
  credential id written one way at enrolment and the other at sign-in is a credential nothing
  can find. `b64url_decode` refuses `+`, `/` and padding outright, because a lenient decoder
  in a nonce comparison is how a replay gets in.
- **Every refusal is one `authentication_failed`.** `webauthn.REASONS` has twelve codes and
  the caller is told none of them: saying whether the address, the credential or the signature
  was wrong is the oracle MOD-022's public/private split is about. The code lands on the
  insert-only auth log. `check_split` runs at import and requires the declared set and the
  raised set to agree in both directions.

**And a test that asserted the gap had to be rewritten, which is the rule working.**
`test_finding_1b_the_highest_level_is_not_reachable_without_hardware` asserted
`reachable: false`; that was a *consequence* of the gap rather than the finding, which was that
a step-up cannot be had by naming a factor. It now asserts the property that still holds -- two
real credentials, correctly presented, still refused for a privileged action -- and says why
the other assertion is gone. A test insisting on a gap the product no longer has is the gap
note outliving its gap, caught by the suite rather than by a reader.

Known gaps, deliberate:

- **No passkey step-up**, named above: level 3 is reached by signing in, not by raising a
  session.
- **No attestation, so no "only these certified keys" policy.** It needs the AAGUID metadata
  service and a tenant-level decision about which authenticators are acceptable.
- **MOD-021's device identity is not this.** A device certificate is mTLS and a signature this
  build never made; WebAuthn verifies a *person's* authenticator. The vault that gap waits on
  is unmoved, and MOD-022 still opens doors on an identity nothing verifies.
- **CON-16 is still blocked, and this is the correction to this file's own "Next".** It
  specifies "SSO with hardware-key MFA, and it is not optional" -- two halves. The hardware
  half is built; the SSO half is IAM-01-R04's OIDC/SAML federation, which is unbuilt, so
  MOD-015's Console screens remain blocked on federation rather than on WebAuthn.
- **The surface exists now, and building it needed a remedy first.** `/account` enrols a
  passkey and `/login` signs in with one -- see "The web app" -- which closes the "a writer
  with no reader" gap this bullet used to record. What it needed before the button was
  `revoke_passkey`: the only writer of `iam.passkeys.revoked_at` was the clone check, so a
  lost authenticator left a credential that could open a level-3 session for ever, and a
  routine self-scoped permission whose every act is uncorrectable is MOD-013's "an
  irreversible act must not be declarable on a routine permission" from the other side. A
  withdrawal is a status change rather than a delete, because `veyro_iam_app` holds DELETE on
  nothing and "was this credential ever enrolled" is asked precisely when somebody lost a
  device.
- **A passkey still cannot raise an existing session from the surface**, as from the service:
  the account page offers no step-up by passkey, because `complete_step_up` takes a password
  or a recovery code. Signing in afresh is the only route to level 3.

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
  means level 3, which needs a device-bound passkey -- **which is reachable now**, so
  break-glass support access and AI acting for a member are exercisable for the first time.
  They were a deliberate dead end for five modules and the catalogue said so; what changed is
  WebAuthn verification rather than the classification. The matrix's own `reachable_aal` is
  derived from `VERIFIABLE_FACTORS` now, because it was the literal `2` and went stale the
  hour the gap closed.
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
- **`/authz/simulate` answers about one scope, and a caller who asks about the default one
  sees none of a person's narrowly scoped grants.** `permissions_of` lets a broad assignment
  cover a narrow scope and never the reverse, which is correct -- and it means "what may this
  person do" has no single answer: a location-scoped role contributes nothing at the
  tenant-wide default. ADM-STF-02 found this by rendering it, with the fixture's own
  location-scoped refund grant missing from the block that exists to show exactly that kind of
  grant. The surface asks once per distinct scope among the person's live assignments and
  labels each permission with where it applies; **a single-scope caller is the trap**, and
  there is no route that answers "everywhere this identity can do anything" in one request.
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

- **The disclosure is readable now.** `GET /privacy/erasure-reach` returns the registry
  itself -- every subject-bearing column, the mechanism erasure has against it, and why --
  with `erasure_is_complete` and the count of what survives. It takes no pool and no tenant,
  so it reads nobody's rows and two tenants get identical bytes; a test asserts that, because
  the day it differs per tenant it has stopped being a statement about the software. It
  existed nowhere before: `plan_dsar` surfaced the same fact per request, so the honest
  answer to "what can you delete" was reachable only after somebody had asked you to delete
  something, and the registry behind it lived in Python and in a test.
  **The number is worth knowing: 19 of 439 subject-bearing columns are erased or anonymised
  and 420 survive.** (It was 17 of 388 until MOD-019's `0017` added four withdrawal columns,
  then 17 of 392, and MOD-026's first slice added twenty-six more -- fifteen of which the
  registry's own sweep refused to let through undeclared, which is what MOD-009 built it for.
  The eighteenth reached column is MOD-026's task assignee, and **choosing its mechanism is
  where the registry earned its keep twice over**: `covered` was refused by the guard that
  requires a covered reference to point into `iam`, and `write_once` would have been accepted
  by every test while being plainly false, because an assignee moves on every reassignment.
  `anonymize` is the true one, so the executor now clears it -- a task assigned to somebody
  who has been erased is unassigned work, and who actually finished it survives on the
  write-once `settled_by`.)
- **No crypto-shred, so erasure is incomplete** -- the disclosure above. Closing it needs a key
  vault and per-subject key material, which is a different module's work.
- **Only a deletion has an executor.** Access, portability, correction and restriction can be
  opened, verified and legal-checked; fulfilling one is refused with a reason and leaves the
  request where a human can act on it. An export needs an object store and a residency decision,
  both unmade, and `_perform` recording "exported" with no file would be evidence of work never
  done.
- **No subprocessor propagation.** SEC-01-R07 asks a DSAR to reach subprocessors; there are none
  wired up.
- **No retention sweep.** `retention.may_delete` decides and no job calls it: a worker runtime
  exists, and destroying records on a schedule is the one sweep where being wrong is
  unrecoverable, so it waits for a decision about what a sweep may delete without a person.
  `may_delete` also passes
  `subject_id=None`, so under the (correct) hold asymmetry one live per-subject hold blocks
  scheduled expiry of that resource type for every subject. Fail-closed, and a real limitation
  the day a sweep exists.
- **No breach-notification clock.** `sec_incidents` records whether personal data was involved,
  which is what starts one; nothing computes a deadline or notifies anybody.
- **`privacy.consent.read` is routine and tenant-wide** over health and biometric consent history
  including guardian identifiers, while `member.health.read` beside it is `biometric_sensitive`.
  Defensible -- consent state is what a kiosk checks before letting somebody train -- and worth
  revisiting when a read path applies `Decision.mask`.
- **Id validation is repository-wide now, and a sweep is what keeps it so.**
  `tests/test_id_validation.py` reads `main.py` with `ast` and requires every id a route takes
  -- in its body, its path or its query string -- to reach a validator or be declared in
  `NOT_A_UUID` with the column that proves it is not a uuid. Both directions, so a stale
  exemption fails too. Twenty-seven routes
  and forty fields were unwrapped when it was written, across MOD-004, MOD-005, MOD-007,
  MOD-008, MOD-015 and MOD-018. **A body is only half the request**: the first version
  swept `body.*_id` and nothing else, so it reported the request path clean while fifteen
  routes answered 500 to a malformed id in a path segment or a query string -- and
  `owned` counts as a validator without being a shape check, because it refuses anything
  that is not the session's own identity with a 404 and a malformed value can never equal
  a real uuid. **Its first version reported zero**: it matched field names against validator
  calls across the whole file, so a field wrapped in one route read as wrapped in all of them
  -- `organization_id` is wrapped in `/legal-entities`, which made `POST /brands` look safe --
  and it visited only module-level functions, so every route, nested inside `create_app`, was
  invisible. A structural check that passes vacuously is the thing it exists to prevent, which
  is why it was run against a deliberately unwrapped guard before it was believed.
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
- **The relay runs; delivery still does not.** `app/worker/` drives `dispatch_pending` every
  fifteen seconds for every schedulable tenant, so an event reaches its subscribers' delivery
  rows without a person asking. `deliver_pending` is deliberately *not* wired: it refuses a
  consumer with no handler, this process registers none, and a relay driving an empty registry
  would read as a control and do nothing.
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
- **Objectives are evaluated on a schedule now; budgets are not.**
  `observability.evaluate_objectives` is a worker job at five minutes, which closes the gap
  this bullet used to record -- an objective nobody evaluates raises no alert, and nothing
  evaluated one. **The judgement that was actually missing was not "which objective".** Every
  objective carries its own `window_hours`, so there is nothing to choose; what had to be
  decided was *how often a breach is announced*, because `evaluate_objective` published one
  event per evaluation and `evt_outbox` has no DELETE grant for any runtime role -- so a job
  at this cadence would write 288 rows a day about one objective that is still breaching, and
  nobody is better informed by the 288th. `objectives.announcement_window` floors the instant
  to the objective's own window and `breach_key` is the outbox idempotency key over it, so the
  outbox's own unique index is the dedupe and there is no new table: a breach log is
  `GET /events/aggregate` for the objective, which already carries the observed figure, the
  threshold and the owner, and is insert-only. **The announcement is deduplicated for every
  caller, not just the job**: a route that announced every time while the job announced once
  would be behaviour that differs by who asked, so `evaluate_objective` returns `announced`
  and `already_announced_this_window` and both callers get the same event. The period is the
  objective's own window because a breach announced more often than the measurement moves is
  noise, and less often is a breach somebody is not told about while it is true; it is floored
  against the Unix epoch rather than counted from `set_at`, so two objectives on one metric
  announce on the same boundary.
  **`evaluate_budget` is still undriven**, and for the reason this bullet gave: which period
  is due is an accountant's judgement rather than a sweep's predicate.
  Proven: 5 worker integration tests, 5 domain tests over the window with no database, and 5
  mutations in `tests/mutate_worker_sweeps.py`, all caught. Two protections there are
  deliberately **not** mutated and the harness says why -- the savepoint around the append
  changes no behaviour today, because PostgreSQL's `COMMIT` after an error rolls back and
  reports success and nothing follows the append in that transaction; and the sweep's
  per-objective `except` has no isolating case, its reachable trigger being an operator
  retiring an objective between the listing transaction and that objective's evaluation.
- **A job's `units` key was shape-checked and never compared against anything**, which is
  fixed and is worth carrying as the finding. `_units` reads `result[job.units]`, falls back
  to zero and logs -- so a registry entry naming a key its job does not return reports zero
  units for ever, which the operations board reads as "the job ran and did nothing". The only
  assertion was that the string was non-blank. It needs a tick rather than a static read,
  because the key is in the registry and the value is in whatever the service function
  returns and nothing relates them until one runs; `JobOutcome.detail` is the result, so one
  tick compares every job at once. Every existing entry was correct, which is the good kind
  of finding: the guard was missing rather than the agreement.
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
- **The limiter's window is fixed, not sliding, so the bound at a boundary is twice the
  budget.** `ratelimit.py` argues the in-memory design at length and says "30 a minute";
  what it enforces is 30 per fixed window, so a caller who spreads attempts across a boundary
  gets 60 inside one rolling minute. That is the ordinary trade for a fixed-window limiter and
  not worth a sliding one here -- but the prose and the mechanism differ by a factor of two at
  the seam, and saying so is cheaper than somebody deriving it from a flake. **It was a flake
  that surfaced it**: a test proving the bound by making thirty-two real attempts crossed a
  window on a slower CI runner and never saw its 429, because every refused login
  deliberately costs one scrypt. `create_app` takes a `clock` now and the two classes that
  prove a volume bound freeze it.
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
  the shape this codebase refuses elsewhere. A worker runtime now exists and this is one of
  the jobs deliberately not wired to it, for that reason.
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
- **Digests are closed on a schedule and still never sent**, which is this gap split in two
  because the note used to conflate them. `notifications.close_digests` is a worker job at
  five minutes: a window whose `window_end` has passed moves to `closed`, so
  `list_digests(state="closed")` is "what is waiting" and is no longer permanently empty.
  **The blocker this bullet named was the wrong one.** The digest template format renders a
  batch into one message, which is the `sent` state; closing needs no format at all. The state
  had admitted three values since the module was built, the filter had always been there, and
  the grant already carried `UPDATE (state, closed_at)` -- a declared state nothing writes and
  a granted column no service writes, in one row, hidden behind a true sentence about a
  different half. **Never closed early**, because the index that keeps a batch in one row is
  partial on `state = 'open'` and an early close lets the next notification in that window
  open a second row, which is the split that index exists to prevent. `sent` is still a state
  nothing writes, and that half does need the format and a dispatcher.
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
  needed a hardware factor MOD-007 could not verify then. The catalogue, `visibility.py` and
  this file all stated the opposite. **An action class is decorative on any path that reads the permission
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
- **`health` and `biometric` need the highest assurance this product has**, and that was
  unreachable until WebAuthn verification landed. `member.health.read` is
  `biometric_sensitive`, which maps to AAL 3; a device-bound passkey reaches it now, so a
  session that signed in with one and holds the permission reads a health note -- which is
  what the classification always meant. The masking was never keyed on
  `visibility.UNREACHABLE_CLASSES`: `held_permissions` filters by the session's own assurance,
  so the level decides. **The surface enrols one now**, on the account page, so a staff member
  who holds the permission and signs in with their passkey reads a health note -- the first
  time in this build that a `biometric_sensitive` read has been exercisable by anybody at all.
  Every other session still masks them, which is the classification working rather than a gap.
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
- **`ppl_staff_profiles` has a reader now, and had none for fourteen modules.**
  `upsert_staff_profile` and `end_staff_employment` were written and listed by nothing, so a
  tenant's team was reachable only by already knowing a person id -- the fourth instance of
  this build's "a writer with no reader" shape. `GET /staff` and `GET /staff/{person_id}`
  close it, and the response names the two of ADM-STF-01's four columns this module cannot
  answer: the role is MOD-008's `iam.role_assignments` and the last-seen is MOD-007's
  `iam.sessions`, both on a plane `veyro_cp_app` holds nothing in, so the surface composes
  them through their own gates rather than joining. **`location_id` is a filter, not a
  boundary**: the design says a club manager sees only their own club's staff and `permit`
  resolves tenant-wide, which is the scope gap two bullets up, said on the screen rather than
  implied by a filter.
- **No search.** Paragraph 4218's permission-aware search index with a mandatory query
  pre-filter is ENG-01's, and a `LIKE` scan presented as search would be a read path with no
  freshness contract and no pre-filter. The duplicate detector draws its candidates through the
  indexes instead, which is the one place this module needs to find people by a value.
- **A duplicate can be prevented now, and until it could it was only ever cleaned up.**
  `find_duplicates` scores *pairs that already exist* -- both sides have to be rows -- so the
  one moment a duplicate is cheap to stop, the moment before the second record is written,
  had nothing to ask. `GET /people/contact-match` is that read, and the finding is where it
  had to come from: `ppl_contact_points_by_value` has been in the schema since this module
  was built, with its own comment saying "finding everybody who shares an address is how
  `find_duplicates` works", and **no route could pass it a value**. The eighth instance of
  this build's "a writer with no reader" shape, read from the other end -- an index with no
  asker. Three decisions in it: it is normalized by `normalize_contact`, which is the write's
  own function, because a second spelling rule here would make a duplicate invisible to
  exactly the check that exists to find it; it is masked like every other read in the module,
  so a routine AAL-1 desk gets the withheld marker *and* the rest of the row, which is still
  enough to say somebody already holds this number; and it filters `merge_status = 'active'`,
  because a merge leaves the losing record's contact points where they are, so one number
  sits on two rows and offering the merged-away one points a desk at a record whose own
  readers are told to follow a pointer. **It is an exact match and not a search**: a mistyped
  digit finds nothing, which is `dedup`'s own reason for having no edit distance, and the gap
  above is unchanged.
- **The timeline projection runs on a schedule now.** `people.project_timeline` is a worker
  job at sixty seconds, which closes the gap this bullet used to record -- the third place
  where the absence changed the product, because a timeline nobody projects stays empty and
  the Member 360 then shows a member with no history.
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
- **The 360's "not in this build" list went stale, and said so to a staff member.** Five
  sections read "not built in this repository" and four of those modules -- MOD-017,
  MOD-018, MOD-019 and MOD-020 -- have since been built, so the one screen somebody opens
  before talking to a member was telling them that bookings and finance do not exist. That is
  this module's own stated failure mode from the other side, and it is the same class of
  defect as returning `[]`: a confident wrong answer where a missing one would have been
  honest. They say the module owns it and nothing here reads it now, which is true and is a
  gap in the wiring rather than in the product -- paragraph 1300's ban on cross-domain
  write-table access is why the wiring is not a join. **Found by opening the page**, and
  `test_a_section_whose_module_exists_does_not_say_it_was_never_built` is what keeps it from
  going stale in the other direction.

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
- **Nothing expires anything on a schedule**, and here that is benign rather than a gap the
  worker runtime closes: a promotion's window and a price's window are read at resolution time,
  so an expired promotion stops applying because the
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
- **The catalogue can be read now, and `resolve_price` is still the only authority.**
  `GET /catalog/products/{id}` carries a product's variants and `GET /catalog/prices` the
  rows written against them, which is what a board needs -- but a row in its window is not
  the resolved price: the book must also be active and must win the priority comparison
  against every other book matching the sale's seven dimensions. `list_prices` returns
  `in_window_is_not_the_resolved_price` so a surface says that rather than letting a figure
  read as a promise. The product read deliberately carries **no** figure, because a price
  needs `catalog.price.read` and returning both would make "see the catalog" buy "see what
  every sale costs" -- MOD-013's `GET /notifications/channels` finding one module over.
- **`list_promotions` never returned the promotion's own window**, which made the listing
  unable to tell a live campaign from one that ended: nothing retires a promotion when its
  window closes, because the resolver reads the window, so `status = 'active'` on a campaign
  that finished in February is the ordinary state of that table. The window and a derived
  `in_window` are returned now, for the same reason MOD-018 derives `admits_trade` -- the
  implication is the fact, and a reader deriving it from two timestamps gets the open-ended
  case wrong.
- **A published product can stop being sellable with nothing changing its status.**
  `publish_product` refuses one with no live price and nothing re-checks afterwards, so a
  price superseded later, or a book nobody activated, leaves a published product the till
  cannot sell. Nothing on the server notices; the board computes it from the two reads above,
  which is a surface closing a gap rather than hiding one.
- **A `manual` promotion is storable and unreachable.** `_applicable_promotions` excludes it
  along with `coupon`, because the whole meaning of the kind is "somebody applies this by hand"
  and nothing in this module does. The manual path here is `pricing.override`, which needs a
  recorded approval. Excluding it was a fix, not a gap: the first version excluded only
  `coupon`, so a `manual` promotion applied automatically to every sale in the tenant -- the
  defect a reviewer found for `staff_discount`, in the one kind no targeting rule could fix.

**MOD-017 (COM-01 and COM-03: the membership agreement, the rights it grants and the money it
generates) -- implemented, gated and reviewed.** Twenty-two tables in `plt01` under the same
forced RLS, `app/commercial/` beside them, and thirty-three HTTP routes (two of which fill
`plt01.legal_entities`, a table MOD-004 built and nothing could satisfy until COM-03-R07 needed
per-entity fiscal uniqueness). Working: contract versions drafted and published as two acts by
two people; membership terms attached to a MOD-016 product; agreements whose price comes from
the resolution they cite; recorded signatures; activation with effective dating; freeze, pause
and medical hold against the contract's annual allowance; resume with term extension;
cancellation with a disclosed fee the member acknowledged; as-of reconstruction from the
history; entitlement policies, grants, atomic expiring reservations, an insert-only movement
ledger and revocation; billing accounts and schedules; fiscal series with gapless serials;
invoices with lines, tax records and credit notes; payment intents, payments and the `unknown`
outcome; a two-party refund; disputes; a dunning journey; reconciliation; and fiscalization
separate from payment. Nineteen events are produced, three of them added by the review.
Proven: isolation checks 73-78, mutation-tested in three rounds -- 814 mutations with 16 gaps,
then 811 with 3 after the repairs, then 811 with none, every one caught by the check that
guards what was broken. 78 domain unit tests with no database and 83 HTTP tests, inside a suite
of 1,400.

**The three rounds are the finding, not the number.** Round one's 16 gaps were almost all one
shape: a constraint or an index added during the review made a *sibling's* case insert a row it
now refuses, so sixteen cases began proving the new rule instead of the one they named. That is
this repository's own "a schema change means re-running the sweep, not re-reading the cases" for
the fourth module, and it cost four of MOD-017's own constraints their evidence in the hour
between one review round and the next. Round two's three were the opposite mistake and the
newer lesson, written up in the rules file: **a case catches a *weakening* only if the weakened
constraint admits the row.** An invoice line over-stating its gross is refused by `gross <=
net + tax` as surely as by the equality, so that case could never see the weakening; the case
that catches it is the one charging *less*. Every one-directional case in this build needs
reading with that question rather than "does this row violate the rule".

Four decisions carry the module, and the fourth is the one the review turned on:

- **`mem_` is what a member is entitled to; `fin_` is what they owe.** Paragraph 1496:
  "membership state, billing state and access state are related but never conflated." A frozen
  membership is not an unpaid one, an unpaid invoice does not by itself revoke access, and
  whether somebody may train right now is a question only `mem_entitlement_grants` answers.
  The prefix is `fin_` rather than `bil_` because `bil_` is MOD-015 billing the *tenant*; the
  two never join and one name for both would invite the join later.
- **A grant is the fulfilment authority and a reservation is atomic.** Paragraph 1506. So a
  reservation is a row with an expiry taken under `SELECT ... FOR UPDATE` on the grant, and the
  remaining quantity is the sum of an insert-only ledger rather than a column two concurrent
  bookings race on. MOD-016's coupon ledger learned that the hard way.
- **A fiscal serial is allocated under a lock and never skips.** Paragraph 1606. A sequence
  would be faster and would leave gaps on rollback, and a gap in a tax series is something an
  authority asks about.
- **A control and the state it bounds commit together.** MOD-010's `append_event` argument,
  applied here to the tax records written in the invoice's own transaction, the coupon-style
  usage checks, and the entitlement revocation that happens inside the cancellation. **This is
  also the rule MOD-016 broke and this module broke differently**, which is the finding below.

**Three reviewers worked this module in parallel -- the schema, the decisions, the request
path -- and all three returned CHANGES_REQUESTED. Twenty-one blocking defects.** Each is
carried forward as a rule, because each is a shape that has now recurred:

- **A separation of duties needs two acts, or it is unverifiable in principle** -- MOD-016's
  finding, and this module shipped it in a worse place. `publish_contract_version` wrote the
  version and published it in one command, and argued for it: a draft could be signed against
  with nobody having approved the terms. **That argument was false** -- `create_agreement`
  resolves only a *published* version, so a draft is unsignable by construction -- and it
  bought a real cost, because one command makes the author and the publisher the same person
  by definition. This is the prose a member is held to and the policy numbers every lifecycle
  decision is measured against. Two acts now, two permissions, and
  `mem_contract_versions_publisher_is_not_author` is the half the service cannot weaken.
- **A cited authority is the authority, or it is decoration beside the figure.**
  `create_agreement` took `amount_minor`, `currency` and `price_resolution_id` from the caller
  and never compared them, so an agreement could cite MOD-016's receipt for 45.00 JOD and
  record 4.50 -- with the resolution id on the row making the figure read as priced and
  approved. The resolution's own figures are what get written now, and a resolution for a
  different variant is refused rather than quietly used.
- **Derive, never accept, reaches the fields that gate a draw.** `reserve_entitlement` took
  `brand_id` and `local_minute` beside the `location_id`, and `entitlements.usable` gates on
  both: a grant scoped to one brand was drawn on at another by sending the grant's own brand
  id, and an off-peak grant was drawn on at seven in the evening by sending `600`. The second
  is the worse of the two, because the whole point of an off-peak membership is that it is
  cheaper. Both come from the location now -- its brand, and the time of day in *its* timezone,
  which is why the conversion is `AT TIME ZONE` in SQL rather than arithmetic in Python.
- **A control consulted once is a control with a window** -- MOD-009's rule, hit twice.
  `approve_refund` and `request_refund` counted only `pending` and `succeeded` refunds against
  what a payment could still refund, and `unknown` means the provider did not answer -- so a
  refund that may well have left was treated as money still held, the same amount was approved
  again, and settling the first as succeeded afterwards left the member refunded twice. That is
  the one direction in this module that no later row can correct.
- **A derived status has to read everything that moves it.** `_apply_to_invoice` summed
  payments and credit notes and never looked at `fin_refunds`, so an invoice refunded in full
  went on reading `paid` -- the figure an accountant reconciles a bank statement against, and
  the one a dunning sweep decides not to chase. MOD-011 found the mirror of this in its margin
  read, which summed invoices and ignored credit notes.
- **A correction path that nothing can reach is not a correction path.**
  `fin_invoices_credit_matches_kind` makes `document_kind = 'credit_note'` and a credited
  invoice the same fact, and `issue_invoice` never passed the column -- so a credit-note series
  could be opened, and refused every document anybody tried to number from it. The module's own
  header calls the credit note "the only correction path" an insert-only ledger has, and it was
  unreachable.
- **An idempotent command has to be idempotent to the caller, not just in the table.** Three
  commands were careful about the row they wrote and answered 409 on a retry: `activate_
  membership` hit the one-membership-per-agreement index, `approve_refund` hit the
  one-decision-per-request index, and `publish_contract_version` had no notion of a repeat. A
  client whose request timed out after the commit was told the work had failed -- and for the
  refund that means a second approver is asked for a decision that was already made.
- **A retry must be answered from what was recorded, not from what the retry carries.**
  `cancel_membership` echoed the caller's `acknowledged_fee_minor` straight back and reported
  `fee_due_minor` as null, so a second call sending a different figure was told it had been
  accepted: the disclosure check bypassed by retrying with the number you wanted. The freeze
  did the same with a hard-coded zero for the allowance and the change's own effective date as
  the planned end -- two figures a client would believe, neither of them that freeze's.
- **An idempotency key belongs to one command, not to one aggregate.** `_recorded_change`
  compared the membership and not the `change_kind`, and three commands consult it -- so a
  client reusing one key across a freeze and a cancel got the *other* command's change back and
  was told its own had happened. A cancel answered with a freeze reads as a cancellation that
  took effect, and nothing cancelled anything.
- **A cancelled membership whose entitlements still work is access nobody is paying for.**
  Paragraph 1496 keeps the three states apart, and that is about not *conflating* them rather
  than leaving them unrelated: the first version cancelled the membership and left every grant
  `active`, so a member with twenty classes left kept all twenty. The cancellation revokes them
  in its own transaction now, with a ledger row for what was written off; what is *held* stays
  held, because a reservation is a booking somebody made.
- **Evidence with nobody's name on it answers nothing** -- the sixth module. `sign_agreement`
  and `fiscalize_invoice` each took an `actor_id` and a `correlation_id`, used neither and
  published nothing. One is the act that makes a contract binding with a minimum term and a
  cancellation fee behind it; the other declares a document filed with a tax authority, or
  declares it outside the regime altogether. MOD-008 audits denials rather than allowed
  actions and `veyro_cp_app` holds nothing in `iam`, so the row was the only record there could
  be.
- **A permission's name is a claim about what it is for.** `settle_refund` was gated on
  `finance.payment.take` -- money coming in -- so a role holding only "take payments" could
  mark money going out as succeeded, which is the last state anybody checks. And
  `reconcile_intent` was reachable for a `pending` intent, so a caller could create a payment
  for a charge no provider had ever been asked about, naming the outcome and the
  `provider_ref` itself: `finance.payment.take` bought with a different permission.
- **A read the approval needs has to exist.** Four commands wrote a refund and nothing returned
  one, so the second person in the separation of duties approved a figure they could not see,
  and `refundable_minor` -- which both halves refuse against -- was computable only by being
  refused.
- **A health fact is a health fact whatever column it is in.** `mem_freezes.evidence_ref` is
  constrained to a locator so a diagnosis cannot be stored there, and `reason` beside it is
  unconstrained prose that the ordinary operator will use to say why. `membership.record.read`
  is routine and AAL 1, which a front desk and a turnstile hold, so the lifecycle history put a
  staged diagnosis in front of every holder of the cheapest read in the module. A medical
  hold's reason is masked now, for everybody, the same dead end MOD-014 records for its own
  health classes -- and the entry stays visible, because a hold a reader cannot see at all is a
  gap in a dispute record.
- **A locator column is a control only if it has to look like one.** `payment_method_ref`,
  `evidence_ref` and `signature_evidence_ref` were non-blank text, and the module's header
  quoted paragraph 1597 -- "sensitive card data never enters Veyro systems" -- ten lines above a
  column that accepted a sixteen-digit number with an expiry. That is MOD-012's `vault_ref`
  finding and MOD-010's "the restricted-field rule checks names, and a value can carry
  anything", for the third time. All three now have to match a URI shape, which no card number
  does.
- Three smaller ones with the same shapes as earlier modules: the first billing period was one
  day longer than every later one, because `renewal_period` returns the period *after* the date
  it is given and the caller kept its end while overriding its start (a monthly membership
  starting on 1 January ran to 1 February and the drift compounded for life); the reservation
  sweep wrote its expiries inside the transaction that then refused the draw, so `tenant_scope`
  rolled them back and a member with three lapsed holds was refused for ever; and the settling
  UPDATE on a payment intent could violate the unique provider reference and answer 500 with
  the transaction aborted.

**A contract may now let a member leave inside the minimum term for a price, and the finding
is that the design and the implementation disagreed about a money figure.** ADM-MSH-07's
canvas discloses "his 12-month commitment runs to March. Cancelling now triggers a two-month
fee of JOD 80.00, and his access ends on 7 September after the notice period" -- a commitment
broken, a buy-out charged, access ending after notice. `cancellation_effective_on` implemented
the opposite and argued for it in its own docstring: "a member inside their commitment cannot
cancel out of it by giving notice: the notice runs, and the effective date is whichever is
later". Under that rule Tareq's access ends in March and no fee arises at all.

Both readings are defensible from the sources, which name a "contract version, signature,
start/end, minimum term, notice, renewal and cancellation policy" and never say what the
cancellation policy *is*. The design is the authority on what the product does, so the buy-out
is what got implemented -- and **nothing had noticed the divergence because no screen rendered
the fee**, so the only reader of that arithmetic was a test asserting the arithmetic. A figure
with no reader is a figure nobody has checked against the design, which is this build's "a
writer with no reader" shape pointed at a number instead of a table.

Four decisions carry it:

- **`Terms.early_termination_months` is nullable, because zero is a term and not an absence.**
  `NULL` is "this contract holds them to the term", which is what every contract in this build
  said until now and what the lifecycle still enforces for one; `0` is "they may leave free",
  which is a different product a tenant may legitimately sell; an integer is the buy-out in
  months of the agreement amount. A boolean beside a count would let the two disagree, which
  is MOD-020's "two caller-supplied keys that nothing relates are two halves of a control".
- **The term still ends when it ends; what moves is the member's access.** A contract offering
  a buy-out is one where notice is the date and the commitment is the price, so the date stands
  and the fee charges for the rest. Pushing the date out *and* charging the buy-out would make
  the member pay twice for the same months.
- **The fee is `lifecycle.cancellation_fee`, in parts, and both callers read the same
  function.** It used to be an inline proration in `preview_cancellation` and another one in
  `cancel_membership`: two expressions, identical, agreeing for as long as nobody edited one of
  them. Adding the buy-out pulled them apart in the worst direction -- the disclosure read
  would have quoted a figure the command then refused as a mismatch, which is the disclosure
  requirement defeated by the function that exists to serve it. The parts are kept apart rather
  than summed early for MOD-018's reason: a total that has lost its components cannot be
  reconciled against anything, and the first question about a fee is always which half is
  which.
- **The reasoning reaches the caller.** `cancellation_effective_on` returns its steps because
  "COM-01-R06 requires the member to understand the consequence before confirming -- a date
  with no explanation is the thing they dispute", and the only caller unpacked them into `_`.
  A value computed for a reason nobody reads, with the reason written down beside the value.

Proven: 9 domain tests with no database and 8 mutations against the arithmetic, every one
caught -- one of which found a real hole, because nothing asserted the *value* of the period
part and swapping it for the remainder passed; 5 HTTP tests including the canvas's figures end
to end; migration `0018`, whose two constraints are three named isolation cases and 6
mutations, all caught.

**`preview_cancellation` carries a fifth fact, and the reason is a defect this module's own
shape caused on the surface.** `commitment.leaving_early` is "access ends before the term
does" -- the buy-out's own condition -- and it is false for a member a contract holds to the
term, because `cancellation_effective_on` pushes the effective date **to** the term end
precisely then. ADM-MSH-07 read it as "is there a commitment", so a member nine months inside
a twelve-month term was told theirs "has been served" and was the one member denied the
freeze offer that keeps a commitment intact. `commitment.term_is_running` is the other
question -- `today < minimum_term_ends_on` -- derived here because `today` is on no response
and a client comparing dates against its own clock counts days in the wrong frame, which is
MOD-016's `in_window` and MOD-018's `admits_trade` for the same reason. Both fields stay, and
what pins the difference is a test asserting they **disagree** on a held-to-term contract: 3
HTTP tests over all three states and 3 mutations, all caught.

**And the gap note that sent me here was wrong, which is the lesson worth more than the
feature.** ADM-MSH-07's backlog entry said the fee had no reader and was learnable only by
cancelling. `GET /memberships/{id}/cancellation-preview` has existed since the module was
built. The real gap was that the read quoted a different product from the one the design
approved, and nothing compared the two. **A claimed gap is a claim to check before building on
it** -- and had I not gone looking for the reader I would have shipped the second fee
expression this paragraph describes.

**And the future-dated freeze is worth its own paragraph, because the fix was to refuse rather
than to build.** `freeze_membership` took an unbounded `starts_on`, and the allowance is counted
in the contract year containing it -- so a member who had spent all thirty days sent a date one
day before their anniversary and got a second allowance, the whole of COM-01-R04's limit bought
with a date field. It also wrote `status = 'frozen'` whatever the date said, so a freeze booked
for August made the membership read as frozen in May while `status_as_of` correctly said no.
The obvious repair is to leave the cache behind and let something catch it up when the date
arrives. **There was nothing to catch it up** when this was decided, and there still is no job
that does -- a worker runtime exists now, and applying a booked freeze is a membership
lifecycle decision rather than a sweep, so wiring it needs the decision written down first. A
booked freeze that never takes effect is worse than one that cannot be booked. So a freeze starts
within the month before today -- a month back because one agreed at the desk on Friday is
recorded on Monday -- and the cache moves because the change is effective. `planned_ends_on`
remains a column, because what the member asked for and the day the freeze actually ended are
two facts and the first version conflated them.

Things worth knowing before extending it:

- **`append_event` takes the connection, and so does every write that must be atomic with it.**
  The tax records, the credit note's effect on the invoice it credits, the coupon redemption and
  the entitlement revocation all run in the transaction that caused them.
- **Money is an integer count of minor units and `app.billing.money` owns the arithmetic**,
  imported and never reimplemented. MOD-016 shipped a second rounding rule once and a reviewer
  found it.
- **A reconciliation can mark a pending intent `unknown` and cannot settle one.** That is how an
  intent becomes reconcilable, and it creates nothing.
- **`validated`, `verified` and `delivered` are recorded, not performed.** No provider, no
  SMTP, no outbound HTTP: `settle_payment_intent`, `settle_refund` and `record_outcome` are
  written by whatever does the work. A module that wrote "delivered" with nothing having
  answered would be the fabricated-evidence shape this codebase has been bitten by five times.
- **A tax record's export marker is final, by trigger.** A CHECK cannot see `OLD`, and clearing
  the marker returns the row to the unexported index -- the liability counted twice in two
  returns, with the row afterwards reading as a single clean export. Second trigger in the
  module, for `sec_legal_holds`' reason.
- **`length(btrim(x)) > 0` is gone from the whole repository**, and `test_migration_shape.py`
  is what keeps it gone. PostgreSQL's one-argument `btrim` strips spaces and nothing else, so
  every "states a reason" control in this build -- 122 constraints across eleven migrations --
  was satisfied by a single tab. The shape is `x ~ '[^[:space:]]'` now. Nothing in a running
  database would ever flag the old one, which is why the guard is a static read of the
  migration files; it caught four survivors of the regex rewrite that did the other 118.

Known gaps, deliberate:

- **No payment provider and no stored payment methods.** Taking a card is real money and the
  owner reserves that. What is built is the half that must be correct whatever the provider
  turns out to be.
- **No tax engine.** `issue_invoice` takes a rate per line -- MOD-015's precedent, which MOD-016
  followed. What is enforced is that whatever rate was applied is recorded on the line and in
  the return.
- **One schedule is driven and the rest are not.**
  `memberships.revoke_ended_grants` is a worker job at an hour, and it closes the half of a
  future-dated cancellation that never arrived: `cancel_membership` revokes grants in its own
  transaction when the date is today or earlier and deliberately does not when it is later --
  the member is still paying for the notice period -- and nothing revoked them when the date
  came. **The door was never wrong and the entitlement was**, which is why this survived the
  review that found the immediate-cancellation version: MOD-022 reads the membership's dates
  rather than its cached status, so a turnstile refuses a row that calls itself active past
  its own `ends_on`, while `entitlements.usable` sees only the grant -- its own status and its
  own `valid_to`, which is optional -- so a perpetual grant from a cancelled membership stayed
  drawable and a booking took a place somebody paying could have had. The predicate is
  `ends_on`, the same fact the door judges by, so a fixed-term membership that simply ran out
  is swept on the same rule rather than on a second definition of "this membership is over".
  **A renewal, a grace-period entry, a dunning step, a lapsed-hold sweep and applying the
  cancellation to the status cache are still undriven**, and each needs a product decision the
  sources do not state. The cache is the mildest of them: `membership_as_of` is the function
  that tells the truth, and the door does not read the cache.
- **A freeze cannot be booked ahead**, which is the refusal above rather than an omission.
- **The cancellation fee is what the act costs, not what is outstanding.** The period part is
  what the current billing period costs for the days the member will have used when access
  ends; whether that period has already been paid is a question for the invoice and the
  payments against it, and nothing joins the two. The buy-out is always a new charge. Both are
  disclosed on the read and on the screen rather than resolved, because resolving them means
  deciding what "owed" means across an invoice, its payments and a credit note -- which is a
  figure MOD-018 owns and this module would be inventing a second definition of.
- **Nothing invoices the cancellation fee.** It is disclosed and recorded against the change,
  and no invoice is issued and no payment taken, which is why ADM-MSH-07 is buildable while
  ADM-MSH-01, 02, 04 and 05 are not: their buttons take money and this one does not.
- **Eight of thirteen declared lifecycle change kinds have no writer, and this note is the
  first thing in the repository to say so.** `lifecycle.EDGES` admits `activation`, `freeze`,
  `medical_hold`, `resume`, `grace_entry`, `suspension`, `renewal`, `upgrade`, `downgrade`,
  `transfer`, `cancellation`, `expiry` and `reinstatement`; the service writes five --
  activation, both freezes, resume and cancellation -- and nothing anywhere writes the other
  eight. So `mem_lifecycle_changes.change_kind` has eight values the product cannot produce,
  which is this build's most-repeated finding sitting in the module that records what a member
  agreed to. **Found by checking MOD-027's design record against the code**, which needed an
  upgrade to convert a trial and discovered there is none.
  **Six of the eight are writable and want a command; two are not writable at all**, and that
  second half is the finding rather than the count. `upgrade` and `downgrade` are declared
  `active -> active`, and moving a member between products would have to move either
  `mem_memberships.agreement_id` or `mem_agreements.variant_id` -- and **neither is in any
  runtime role's UPDATE grant**, nor is `price_resolution_id`, nor is `person_id`. That is
  deliberate and it is this module's own premise: what the member agreed to does not move, which
  is what makes "what did this member agree to a year ago" answerable from the row. So the two
  kinds are not merely unwritten, they are kinds whose effect the schema forbids -- a declared
  value the privileges rule out, which is stronger than a declared value nothing writes.
  **A product change is therefore a new agreement and a new membership on the same person**, and
  that is also what makes the CRM canvas's "nothing is re-entered" true: everything it lists as
  carrying forward -- her check-ins, her class attendance, her coach's first note -- is
  person-scoped, so the person id is the id that matters and not the membership's. Deleting the
  two kinds is the remedy this build applies elsewhere to a value nothing can produce; widening
  the grant is the alternative and would be wrong for the reason above.
  The other six are commands and jobs nobody has built, each writable with the grants that
  exist: a renewal, a grace entry and an expiry are what the undriven sweeps above would write;
  a suspension, a reinstatement and a transfer are commands. `_record_change` takes the kind
  already and `check_transition` knows the statuses, so each is work rather than a blocker.
- **No installment schedule generation.** `fin_billing_schedules` records the plan and its
  remaining count; nothing walks it.
- **Nothing reverses a payment inside the module.** A payment has no UPDATE grant at all, so a
  payment recorded in error is reversed by a refund -- which needs two people, and that is the
  intended cost.
- **`order_reference` and MOD-016's fulfilment ledger are still not joined.** MOD-016 left
  `order_reference` as free text because the module that owns orders did not exist; this module
  owns the agreement and the invoice, and nothing yet resolves a catalogue fulfilment to one.
- **Five free-text columns and six locators are residue an erasure cannot reach**, all declared
  in `SUBJECT_COLUMNS` by hand because the sweep matches column *names*. Closing it needs an
  erasure path into `plt01` for prose, which is a different problem from MOD-014's per-column
  tombstones.
- **The timeline does not know about any of this.** MOD-014 projects nine event types and none
  of MOD-017's nineteen is among them, so a member's timeline shows no agreement, no freeze and
  no invoice. Adding one is a `Projection` with a summary somebody wrote, which is the review
  point MOD-014 names.
- **Two human-facing member numbers, from two modules, with nothing relating them.**
  `mem_memberships.membership_number` is this module's and `ppl_member_profiles.member_number`
  is MOD-014's; both are the kind of number somebody reads out at a front desk, and a member
  with both has two. Found by rendering them on one page. Relating them is a product decision
  -- which of the two is *the* number -- so it is disclosed on the surface rather than guessed
  at here.
- **The freeze allowance can be read before anybody spends it**, and until it could
  ADM-MSH-03 was undrawable. `allowance_days_used_before` came back from the *write* and from
  nothing else, so the only way to learn how much of a contract's allowance a member had used
  was to use more of it and read the answer -- the seventh instance of this build's "a writer
  with no reader" shape. `GET /memberships/{id}/freeze-allowance` returns the contract year,
  the days used, the days remaining and the window a freeze may start in, **all from the
  expressions `freeze_membership` itself checks against** rather than a second set that
  agrees with them today. It also says which case the figure is: **an open freeze is counted
  to the end of the contract year**, because it is spending the allowance now, so a seven-day
  freeze taken today reads as 275 of 30 used -- right, surprising, and the reason the read
  carries `counting_an_open_freeze` rather than leaving a consequence panel to print a number
  nobody can reconcile against the days they asked for.
- **The listing reads exist now and they are reads only.** `GET /memberships`,
  `GET /memberships/{id}`, `GET /member-entitlements`, `GET /finance/accounts` and
  `GET /finance/invoices` make the module observable; nothing on the surface *writes* to it.
  Selling a membership, freezing one, cancelling one, issuing an invoice and taking a payment
  are all built on the server and none has a form, which is the same gap the hierarchy has and
  for the same reason: every one of those writes is a stepped-up financial permission.
- **The dunning journey is sorted now, and `recovery_treatment` is where.** ADM-PAY-05's
  canvas argues that a batch of failed payments is "one decision, not six" -- which is a
  claim nothing in the module could establish, because whether a case wants a payment link
  or a person depends on *why* the charge failed and *where the member stands*. The
  decision is pure and sits in `collections.py` beside the retry budget it calls rather
  than re-derives; `GET /finance/recovery` runs it over each open case, pairing it with the
  failure that opened it and the membership **the invoice cites** -- never the payer's
  latest, which would answer about a different agreement whenever somebody has two. The
  retry budget there counts **charges presented against the invoice**: a retry in this
  build is a new intent, so an intent's own `attempts` sits at one however many times the
  card has been tried, and the case's `attempts` counts dunning steps, which are not
  charges.

**MOD-018 (COM-04 financial ledger, member wallet and revenue recognition) -- implemented,
gated and reviewed.** Fifteen `led_` tables in `plt01` under the same forced RLS,
`app/ledger/` beside them, and twenty-three HTTP routes. Working: a code-resident chart of
account kinds with per-tenant accounts; signed double-entry postings whose journals balance by
a deferred constraint trigger; financial periods with the open/closing/closed/reopened lock;
corrections as reversing journals; a four-kind member wallet with a fixed spend order and
derived balances; revenue recognition on three bases with cumulative, idempotent runs;
provider settlement import with per-line matching, posted fees and payouts, and a
reconciliation case per unanswered question; cash sessions with a posted opening float and a
variance that goes to suspense; bank deposits posted on the way out and reconciled when the
bank answers; a trial balance; and a period export. Five of COM-04's seven events are
produced. Proven: isolation checks 79-84 plus the cross-row and one-way trigger probes in 84b
and 84c, mutation-tested in four rounds -- 963 mutations in the last of them with three
gaps, each repaired and re-verified; 61 domain unit tests with no database; 64 HTTP tests,
inside a suite of 1,528.

**This module is wired into MOD-017 rather than sitting beside it.** `chart_for`,
`post_invoice`, `post_credit_note`, `allocate_payment` and `post_refund` are called from
`app/commercial/service.py` **on its connection**, inside the transaction that writes the
invoice, the payment or the refund. That is the one thing about the module that is
load-bearing, and it is MOD-010's `append_event` argument applied to money: a payment in
`fin_payments` with no journal, or a journal with no payment, is a state nothing can reconcile.
The pool-taking wrapper is called `post_journal_in_its_own_transaction` and is correct only
where there is no state change to be atomic with.

Six decisions carry the module:

- **Signs, not sides.** A posting carries a signed `amount_minor`: positive is a debit,
  negative a credit, and the side is derived. One column cannot disagree with itself, and
  "the journal balances" is then exactly `sum(amount_minor) = 0` -- a rule the *database*
  enforces per journal rather than a property the service promises. It cannot be a CHECK,
  because the sum spans rows that do not all exist until the last insert, so it is a
  `DEFERRABLE INITIALLY DEFERRED` constraint trigger. **And "balances" needs two more
  clauses than the sum**: no account twice in one journal, because +N and -N on one account
  satisfies the sum and moves nothing; and a journal has at least one posting, because the
  balance trigger is on `led_postings` and an empty journal fires it zero times.
- **Nothing stores a balance.** COM-04-R07. An account balance is a sum over postings and a
  wallet balance is a sum over entries, computed where they are needed. The cost is a query
  per read; the benefit is that a statement and a balance cannot disagree, because they are
  the same sum read to different depths. No table here has a balance column and the sweep
  tries to add one.
- **The wallet is four balances because one would erase the distinction that matters.**
  Paragraph 1686, a Critical Control: a member holding 50.00 they paid in and 10.00 the tenant
  gave away holds two different things, and the first is money the tenant owes. `SPEND_ORDER`
  spends promotional value first and cash last -- **the member's interest, not the tenant's**,
  because spending cash first quietly converts a refundable balance into an unrefundable one
  every time the member buys anything. The caller cannot choose the kind, the liability
  account is derived from it, and the counterpart is checked for what it is.
- **A closed period refuses a posting, and `closing` exists because closing is work.** So
  `closing` admits the close's own entries and no trade; `closed` admits nothing; and a closed
  period never reopens on its own authority, it moves to `reopened`, which has its own
  permission and a written reason. `open -> closed` is refused outright, which surprises a
  caller that expected one step. **The lock binds the posting rows, not just the header**: it
  takes `FOR SHARE` on the period row, so a till inserting a journal and an accountant closing
  the month cannot walk past each other, and it is re-read at commit.
- **A posted journal is corrected, never edited.** Paragraph 1685's Critical Control. Six
  tables carry no UPDATE grant for any runtime role and none carries DELETE, so a correction
  is a reversing journal that names the original. A correction is not itself reversible,
  because that is almost always somebody trying to undo an undo.
- **A lifecycle decision is made once, and a trigger is what says so.** MOD-009's
  `sec_legal_holds` rule: a CHECK cannot see what a row used to be. Seven triggers hold the
  status transitions and make a settlement timestamp un-clearable and un-rewindable, because
  the attribution CHECKs beside them say nothing about the previous row.

**Three reviewers worked this module in parallel -- the schema, the decisions, the request
path -- and all three returned CHANGES_REQUESTED. Twenty-four blocking defects**, every one
executed rather than reasoned about, and every one inside a green 103-test suite. The largest
single cause is the one `CLAUDE.md` already records for every module since MOD-011, and three
of the request-path findings were three faces of it. Carried forward as rules:

- **A control on the journal header is not a control on the money.** The balance trigger is
  `AFTER INSERT ON led_postings`, so a journal with *no* postings fired it zero times and
  nothing about it was ever evaluated -- not the balance, not the control total. A reviewer
  parked a header claiming a 500.00 control total, then satisfied the mandatory `journal_id`
  on a wallet entry with it: the member held 500.00 of spendable value with no liability
  anywhere in the ledger, which is the state this module's own wallet section says cannot
  exist. It was also how a journal reached a *closed* period -- park the header while the
  month is open, close the month, insert the postings -- and the race needs no foresight at
  all, because an FK insert takes `FOR KEY SHARE` and an UPDATE of the non-key `status` takes
  `FOR NO KEY UPDATE`, which do not conflict.
- **"Immutable by privilege" says nothing about the columns that *do* carry a grant.** Nine
  lifecycle columns had a repeatable UPDATE and nothing but an all-or-none attribution CHECK,
  which cannot see `OLD` -- so a reviewer un-closed a filed month with no reason, re-opened it
  to trade and re-closed it under a different actor, leaving a row that reads as a month closed
  once; erased a 400.00 shortfall on a bank deposit; rewrote a till close so the drawer
  balanced and deleted the written variance; and replaced a write-off and the name of whoever
  decided it. Six of the nine are declared `write_once` in the privacy registry and all six
  were service discipline only, in the module whose premise is "this is the half that still
  holds when the service is wrong".
- **Beginning the month-end close stopped the product.** `closing` is a state an accountant
  enters deliberately and the bridge runs inside MOD-017's transaction, so the `Conflict`
  rolled the business write back: no invoice could be issued, no serial allocated, and a card
  the provider had already charged could not be recorded -- which is how a member gets dunned
  for a payment that succeeded. A close begun on the 28th shut the till for four days. A
  bridged posting now walks forward to the first period that admits it, which is what an
  accountant means by "it goes in the next open period"; a journal posted by hand still does
  not walk, because somebody is there to read the refusal.
- **The cheapest permission in the module was an unrestricted posting route.**
  `close_cash_session` took `suspense_account_id` and never checked its kind, so
  `finance.cash.session` -- routine, AAL 1, held by a front desk -- posted any amount up to
  10^12 between the drawer and *any* account in the chart. A reviewer cleared every member's
  outstanding receivable with it. The identical movement through `POST /ledger/journals` is
  refused, because that permission is financial and needs a step-up, and the catalogue's own
  justification for leaving the session permission routine is the variance going to suspense.
  Three sibling commands checked the kinds of the accounts they named and three did not.
- **`purpose` was a word on the body that bought the authority the period state exists to
  withhold.** The identical journal -- same accounts, same amount, `source_kind: "manual"`,
  description "ordinary sale" -- was refused as `trade` in a closing period and accepted as
  `close` or `settlement`. Nothing distinguished the close's own machinery from ordinary trade:
  no second act, no separate permission, no correspondence check. Everything but `close` is
  derived from the source kind now, and `close` costs `finance.period.close`.
- **A predicate in a `LEFT JOIN`'s `ON` clause is not a filter.** The trial balance's entity
  and as-of date both sat there, where a posting whose journal matched neither survived the
  join with NULL journal columns and was summed anyway -- so a per-entity trial balance carried
  the other entity's journals and a period-end one carried journals posted after the date it
  was asked for. That is the figure a close is signed off against, moving whenever a later
  month is posted, in the read the close is verified with; and `export_period` computes its own
  totals correctly, so the filed export and the trial balance disagreed with nothing to say
  which was right.
- **An unordered lookup makes the planner the author.** `chart_for` filtered on neither the
  legal entity nor anything deterministic and filled a dict in row order, so which revenue
  account an invoice credited changed between runs on identical input, and a two-entity
  tenant's receivable landed in the *other* entity's account -- which forecloses the per-entity
  separation COM-03-R07 needs and which `chart_for`'s own docstring claimed.
- **Lapsing a credit without lapsing what was drawn against it charges the member twice.**
  `balances` dropped an expired credit and kept every debit, and a debit carries no expiry --
  so a member who *used* a promo code lost, on the day the promo would have expired, an amount
  of their own paid-in cash equal to the promo they had already spent. The kind went negative,
  `spendable` sums across kinds, and it compounded with every expired credit they had used.
- **One module, two definitions of the same balance.** `_expected_in_drawer` summed a cash
  account's postings with no date bound while `account_balance` thirty lines down had one, so
  one journal dated next year moving 100.00 out of the till made today's close balance:
  nothing posted to suspense, no written reason demanded, no case opened. It also misfired with
  no adversary at all, on any legitimately back- or future-dated journal touching a till.
- **A composition check per deposit cannot see the second deposit.** `create_deposit` compared
  what a bag declared against the sessions it named, per bag -- so one 200.00 session was
  banked in two deposits under two idempotency keys, which is the ordinary
  retry-with-a-new-key case: 400.00 in the bank, minus 200.00 in a drawer, no reconciliation
  case, and the clean route to pocketing 200.00 of notes while the negative drawer reads as a
  banking error.
- **A module docstring claimed a posting the module never made.** `settlement.py` said an
  unmatched line posts to `suspense`; `import_settlement` never called `post_journal` at all.
  A fee and a payout are the two line kinds that definitionally have no counterpart here and
  so *must* post, and both were classified `not_expected` and dropped -- so
  `provider_clearing` was debited by every card payment and relieved by nothing, while
  `allocate_payment`'s whole argument for landing payments there described a reconciliation
  that read the account and never settled it.
- **A `ValueError` is not a `ServiceError`.** `month_bounds` raises `LedgerError`, and
  `_period_for` was the one of ten call sites that did not wrap it -- so a mistyped year
  answered 500 on four money routes including `/finance/invoices`, and conditionally in the
  worst way: a tenant with no chart gets its invoice, so the 500 appeared only once a tenant
  had set its ledger up.
- **A state machine's only exit has to be reachable.** `EDGES["reopened"] = ("closing",)` and
  the UPDATE that takes it there violated `closed_is_closed`, which was a biconditional -- so
  `/ledger/periods/reopen`, the one act COM-04-R06 provides for correcting a filed month, was a
  one-way door that answered 500 on the way out, left the period indefinitely postable, and
  could never be re-locked.
- **A caller-supplied key interpolated into a `LIKE` is a pattern.** A wallet debit keyed `%`
  was answered 201 `repeated: True` quoting the previous sale's figure, so a till handed over
  90.00 of goods for 1.00 of wallet value -- and a legitimate key containing `%` or `_` made
  the day's second genuine sale free.
- **An idempotency namespace a caller can write into is not a namespace.** The commands
  compose their keys into `led_journals.idempotency_key` and `POST /ledger/journals` wrote to
  the same single unique key, so a decoy journal keyed `wallet-credit-TOPUP-9` was handed back
  as the repeat of a wallet credit keyed `TOPUP-9`: 1000.00 of refundable member value with no
  liability recorded, and a trial balance that **cannot see it**, because the decoy balanced.
- **Recognition believed a future date and an unrelated liability.** A caller-chosen `as_of`
  five thousand days out turned a whole prepaid year into revenue in one call and marked the
  schedule `complete`, so the real recognition could never be posted and the journal landed
  outside every as-of read -- paragraph 1695 inverted by the module written to enforce it, and
  MOD-011's unbounded `observed_at` finding in a worse place. And nothing related a schedule's
  `total_minor` to the `unearned_minor` on the invoice behind it, which defaults to zero, so
  `unearned_revenue` went to **minus** 500.00: a liability with a debit balance, reachable by
  accident on the ordinary path.
- **A month that was never opened cannot have been closed.** COM-04-R06's lock is enforced per
  period *row*, so a tenant whose 2026 books were filed had every earlier month wide open and
  `posted_on` was unbounded in both directions.
- **A journal can be filed into a period that is not its entity's.** Nothing related
  `led_journals.legal_entity_id` to `led_periods.legal_entity_id`, so an entity whose November
  was closed posted more November trade through a *sibling* entity's open November -- one
  transaction, no race -- and `led_exports` then carried two legal entities' journals in one
  filing.
- **A posting's currency was checked against the journal's and not its account's.** The
  account's own `currency` is protected from UPDATE precisely so existing postings stay
  addable; that made the label immutable and said nothing about the values it labels, so a JOD
  posting sat in a USD account and that account's balance -- the only balance this module has
  -- became a sum across two currencies.
- **An export-once control that was two contradictory comments and no mechanism.** One comment
  said the marker "gets the same trigger" as `fin_tax_records`; another, forty lines down, said
  it "needs no trigger". There was neither, and no uniqueness on (period, system) either, so
  5,000.00 of debits reached the accounting system twice under two idempotency keys.
- Four more with shapes this file already records: a reconciliation case could be written off
  citing an unrelated journal (MOD-016's `approval_id` finding); `correct_journal` took an
  idempotency key and ignored it on the repeat path, so a client whose request timed out after
  the commit was told 409 for work that had succeeded (MOD-017's own blocking finding);
  `led_wallets` carried a `status` and four freeze columns that nothing in the build could set,
  with `debit_wallet` reading the status and refusing a frozen wallet -- an unreachable control
  whose only writer was the grant, which a reviewer used to clear a freeze and its reason in
  one statement (MOD-012's "a column implying a control nobody implemented"); and three
  free-text columns were undeclared in `SUBJECT_COLUMNS` while a reviewer wrote an address and
  a date of birth into one and read it back.

**The last round's three gaps are worth naming**, because two of them are this module's own
finding recurring in its own evidence: I wrote seven one-way triggers to close the lifecycle
defect and gave two of them no probe, so they were droppable in silence. The third was an
ill-formed weakening -- `amount_minor >= 0` on a postings table whose own rows are half
negative cannot be applied at all, so it tested nothing and read as a gap on every run, which
is the "a mutation that changes nothing is not evidence" trap from the other side.

**And the evidence had three more holes, each in a shape the rules file names.** A
plpgsql branch is invisible to a generated constraint sweep, so the balance trigger's
mixed-currency branch had no probe at all and a reviewer deleted it with the suite reporting
84/84 -- then committed a journal that "balanced" by setting dollars against dinars. The
`lines < 2` branch was proved by a sibling and is in fact subsumed by
`led_postings_amount_not_zero`, so it is deleted rather than tested harder. And check 61b, the
prefix-free `plt01` sweep, covered only ENABLE+FORCE RLS, one permissive policy and a tenant
foreign key -- so a table satisfying those three with `USING (true)`, DELETE, TRUNCATE and a
PUBLIC grant read every tenant's rows with the suite green, and the name
`ledger_running_balances` escaped MOD-018's own two absence-sweeps as well. The predicate
shape, the DELETE/TRUNCATE/REFERENCES and PUBLIC bans, the tenant-leading key and the
forbidden-column-name sweep are prefix-free now.

Things worth knowing before extending it:

- **The chart is tenant configuration, and a tenant without one still gets its invoice.**
  `post_invoice` returns `ledger_skipped_because` rather than refusing: a tenant mid-setup
  must not find its till has stopped working. What makes the skip honest rather than silent is
  that the caller is told.
- **A payment lands in `provider_clearing`, not in the bank**, and the settlement's payout
  line is what moves it to the bank. That is the pair the reconciliation rests on.
- **The opening float is a journal.** A float recorded only on the session row was cash the
  ledger did not know about: the drawer's own account went negative by exactly the float when
  the takings were banked, and the expected count was a number the caller sent. Found by
  writing the HTTP test, which is the argument for writing them.
- **A till variance posts to suspense *and* opens a case**, and an unexplained one refuses the
  close.
- **A fee line opens no case.** A case is an unanswered question; a provider's own fee is its
  own movement, and a case per fee would bury the lines that need somebody. A chargeback, its
  reversal and an adjustment do open one, because each reverses or amends a payment this module
  cannot resolve to one row and posting a guess is worse than asking.
- **`finance.ledger.read` is routine and everything that writes is financial class.** A trial
  balance is how somebody finds out that something is wrong, and a read behind a step-up is a
  read nobody does until the month-end panic. `finance.cash.session` is routine for the same
  reason -- a front desk opens a drawer every shift -- and what bounds it is the suspense
  posting and the case, which is now true.
- **`SELECT ... FOR UPDATE` needs the UPDATE privilege**, so the wallet row -- immutable, with
  no UPDATE grant -- is serialised by an advisory lock instead. MOD-009's precedent.

Known gaps, deliberate:

- **Nothing posts to a general ledger outside this build.** `led_exports` records that a closed
  period was handed to a named system with its totals; there is no connector, and a row saying
  "exported" with nothing having answered would be the fabricated-evidence shape this codebase
  has been bitten by five times.
- **No FX.** `fx_gain_loss` is in the chart because paragraph 115 names it, and nothing
  revalues anything: a journal is single-currency and a cross-currency one is refused.
- **No COGS posting**, and no cost feed to produce one.
- **No wallet refund and no wallet freeze.** Paying money out is the owner-reserved half of
  COM-04-R02; `refundable` tells a member what they could get back and no code acts on it. The
  freeze was deleted rather than left half-built.
- **Nothing recognises revenue, closes a period or sweeps a lapsed deposit on a schedule.**
  `recognition_due` decides and a route calls it; no worker job does, because which period and
  which schedule are due is an accountant's judgement rather than a sweep's predicate. The
  absence changes the product once: revenue sits unrecognised until somebody asks.
  **Wallet expiry is not on that list and this bullet used to put it there, which was wrong
  twice over.** Lapsed value is not spendable: `balances` excludes it at read time by design --
  "expiry is evaluated rather than swept", because a balance that counted lapsed value until a
  worker removed it would be a balance a member could spend after it expired -- and
  `plan_debit` goes through `balances`, so no debit can reach it. And `expiring_before` is not
  a sweep's predicate waiting for a driver; its own docstring says it is "for telling a member,
  not for sweeping", and there is no expire-the-value command for a job to call. What a sweep
  *would* add is the posting that turns unredeemed value into revenue, which is breakage and is
  the accountant's judgement above. **A gap note that invents a job is worse than one that
  omits a job**: this one would have had somebody wire a sweep against a function that says it
  is not for sweeping, to fix a defect the module had already decided not to have.
- **`credit.issued` and `credit.consumed` are declared and deliberately unproduced**: the
  credits COM-04 means are MOD-017's entitlement grants, which already publish their own pair.
- **`units_delivered` on a recognition run is the caller's word.** The delivery count for an
  `entitlement_grant` schedule is MOD-017's `mem_entitlement_ledger` and nothing resolves it,
  so a caller can report ten classes delivered with nothing booked. The bounds that do hold
  are the schedule's `units_total` and the unearned liability behind it.
- **A settlement line matches on the provider reference and the amount, and nothing else.** A
  provider that re-uses a reference across batches, or sends a partial capture under the
  original reference, lands as `amount_mismatch` and opens a case for a human.
- **The trial balance is per entity and per currency, and there is no statement.** A balance
  sheet and a profit-and-loss need an account-class rollup with a period boundary.
- **`chart_for` takes the lower account code when a tenant keeps two of one kind with no
  entity scope.** Stated rather than discovered, and the reason there is no uniqueness
  constraint: `REV` and `REV-RETAIL` is a legitimate chart.
- **No `Decision.mask` on any `/ledger` read**, so `wallet_statement` returns each movement's
  reason -- a tenant's own prose -- to a routine tenant-wide reader. The same disclosure
  MOD-013 carries for `privacy.consent.read`.
- **`finance.ledger.read` is a narrow lateral read around `finance.invoice.read`.** A session
  holding only it gets an invoice's net, tax, gross, document number and the payer's
  `person_id` out of a journal read, while the same session is refused by
  `/finance/invoices/{id}` and `/people/{id}`. It stays a gap rather than a defect only
  because journal ids are not enumerable from any route that permission reaches -- the day a
  journal-listing route is added, this is MOD-010's `events.event.read` finding.
- **Nineteen free-text columns are residue an erasure cannot reach**, all declared in
  `SUBJECT_COLUMNS` by hand because the sweep matches column *names*, and pinned by a named
  test because a reviewer deleted one declaration and watched every test pass.
- **The drawers can be listed now, and until they could ADM-PAY-09 was unbuildable.**
  `open_cash_session` and `close_cash_session` had no reader of any kind -- the sixth
  instance of this build's "a writer with no reader" shape -- so a till could be opened and
  the only way to learn what was in it was to close it and read the refusal.
  `GET /ledger/cash-sessions` returns the expected figure for an **open** drawer, which is
  the design's own decision rather than a leak: "the expected figure is shown before the
  count is entered. Hiding it would be a fraud control; showing it is an accuracy control,
  and accuracy is the more common problem." It is safe to show because it is derived from
  that account's own postings and from no number any caller sent. The read also splits the
  same sum by sign -- the float, what came in, what went out -- so the three lines add up to
  it by construction, which is what makes the figure checkable by the person holding the
  notes. **`entries_in` counts journals, not sales**, and the surface says so rather than
  printing "14 sales" over a number that is not one.
- **The chart and the periods can be listed now; journals deliberately cannot.**
  `GET /ledger/accounts` and `GET /ledger/periods` make the module observable -- and the
  second is COM-04-R06's lock made readable at last: a closed period refuses a posting and
  `closing` admits the close's own entries and no trade, so "which months are shut" decides
  whether a till works, and until that route existed the only way to find out was to attempt
  a posting and read the refusal. **There is still no journal listing, and that is the point**:
  the gap above says this becomes `events.event.read` the day journal ids are enumerable, so
  `test_there_is_no_journal_listing_route` asserts the absence of `GET /ledger/journals` while
  asserting the POST is present. Adding one means fixing the journal read first.
- **A month with no period row has never been opened**, which is not the same as being open,
  because the lock is enforced per row. `list_periods` returns `absence_means_never_opened`
  so a surface says that rather than listing twelve months and implying the absent ones are
  available.
- **The timeline does not know about any of this either.** MOD-014 projects nine event types
  and none of MOD-018's is among them.

**MOD-019 (OPS-01 scheduling, resources and capacity) -- implemented, gated and reviewed.**
Twelve `sch_` tables in `plt01` under the same forced RLS, nine trigger functions,
`app/scheduling/` beside them, and nineteen HTTP routes. Working: one resource model over
OPS-01-R01's seven kinds; a rota of working hours, breaks and dated absences; schedule
templates whose recurrence is a *version* and whose sessions cite the exact version they came
from; per-occurrence local-to-UTC conversion with the spring-forward gap stepped and recorded;
capacity policies with setup and cleanup margins, a waitlist, declared overbooking and a
booking window; eligibility restrictions with an explainable denial; deterministic conflict
detection over double-booking, over-capacity, availability and site; an impact assessment a
publish is refused without; places held as rows and counted under a lock; and the four acts
paragraph 1839 names -- substitution, cancellation, relocation and attendance handoff. Five
events are produced. Proven: isolation checks 85-91, mutation-tested in four rounds -- 770 in
the last, every one caught by the check that guards what was broken; 78 domain unit tests with
no database; 54 HTTP tests.

Six decisions carry the module:

- **The rule and the session are different rows, and the rule is immutable.** Paragraph 4149:
  "recurring schedule definition is separate from generated occurrences so historical instances
  remain stable after template edits." So `sch_recurrence_rules` is one row per version with no
  UPDATE grant at all, a session cites the exact rule it came from by foreign key rather than
  joining through the template, and editing next month's class leaves last month's sessions as
  they were. A design that recomputed occurrences from the current rule would rewrite history
  on every typo fix.
- **A session stores a UTC instant and the local facts it came from.** Paragraph 4150, and the
  conversion is per occurrence: a rule carries a local time plus the location's zone, and each
  date is converted separately. Across a clock change neither fact is derivable from the other.
- **Capacity is held, not counted.** Paragraph 4146 asks for "atomic reservation counters", and
  there is no `held_count` anywhere: one row per place, summed under a row lock on the session.
  The forbidden-name sweep is how that absence is kept, because an absence is what a later
  migration restores.
- **A location is part of every decision.** A resource, a placement and a rota window all carry
  one, and all three are compared: a class at one site cannot hold a studio at another, and a
  coach's rota is read in *their* zone rather than the session's.
- **An impact assessment is what a disruptive publish costs.** Paragraph 1841. The preview is a
  separate read that takes the proposed rule, and a publish that would move or cancel a session
  somebody has booked needs `scheduling.schedule.publish_disruptive` -- a different permission,
  not a flag.
- **A conflict override is a permission plus a written reason.** Paragraph 1842's Critical
  Control. Sending `override_reason` routes the request to `scheduling.conflict.override`, the
  overridden occurrence is created, and the row records that occurrence's own conflicts.

**Three reviewers worked this module in parallel -- the schema, the decision modules, the
request path -- and all three returned CHANGES_REQUESTED. Fifteen blocking defects**, and the
dominant cause was the one `CLAUDE.md` already records: a control keyed on a value the caller
supplies, defended in writing by a claim that was false. Carried forward as rules:

- **`FOR SHARE` does not conflict with `FOR SHARE`.** The capacity trigger -- the whole of
  paragraph 4146's Critical Control -- read the session row with a share lock, so two inserters
  held it at once, neither saw the other's uncommitted hold, and both committed: four places in
  a two-place class, with two ordinary transactions and no adversary. The service happened to be
  safe because it takes `FOR UPDATE` before counting; this trigger exists for the writer that is
  *not* the service, which is the half the paragraph is actually about. **And nothing in the
  isolation suite could ever have seen it**, because a single psql session cannot race itself --
  so the evidence is a two-connection Python test, and it fails with `FOR SHARE`.
- **When a module explains why it accepted something, check whether the danger it names is
  reachable.** `take_hold` took `age_years` from the body, defended by "the member's age belongs
  to MOD-014 and this module reads neither" -- and `ppl_persons` is in the same schema, under
  the same role, behind a composite foreign key the hold row already carries. A reviewer put a
  fourteen-year-old in an 18+ class on `scheduling.place.hold`, the routine AAL-1 permission a
  front desk and a turnstile hold, and the hold row has no UPDATE on `person_id` and no DELETE
  anywhere -- so the record that the child attended is permanent. The age and the entitlements
  are derived now; `skills` stays the caller's word because nothing in this build stores one,
  and that is said in the body rather than implied. **This is MOD-017's lesson, which this
  module had read and shipped anyway.**
- **A field stored beside a decision and never read is not a parameter, it is a comment.**
  `Window.timezone` was declared, written from the resource's own location and read by nothing:
  the rota was evaluated in the *session's* zone, so a London coach rostered 09:00-17:00 was
  available for an 09:00 class in Amman, which is 06:00 their time. With a *dated* absence it
  was worse than mis-timed -- the window is selected by comparing its date against a local date
  computed in the wrong zone, so a day off three hours away was never consulted at all.
- **A guard that compares nothing is not a guard.** `Resource.location_id` and
  `Placement.location_id` had both been carried from the start and neither was compared, so a
  class could be published at one site holding a room and an instructor at another -- and the
  room was *genuinely held*, so the real class at the owning site was correctly refused it. Two
  harms from one missing comparison. `_assign` drew from the whole chart for the same reason.
- **A feature whose success path is unreachable reports success.** An occurrence with a conflict
  was skipped, and *then*, if a reason had been given, an override row was written for each
  session in `created` -- which held only the occurrences that had no conflict. So
  `override_reason` bought nothing at all: 201, nothing created, no override recorded, and
  paragraph 1842 reading as satisfied. The same shape one route over: `relocate_session`
  recorded the change and left `sch_sessions.location_id` alone, with a `note` in the response
  explaining that a published session's identity does not move -- so the destination's calendar
  stayed empty and the origin's showed a class that was not there. **A response field explaining
  why the module did not do what it was asked is the defect, written down.**
- **A pure function that answers differently depending on the order of a list it does not
  control is wrong whatever builds the list.** `publishing.assess` keyed a dict on `starts_at`,
  so a tenant running two classes at six o'clock in two studios had one silently dropped, and
  *which* one depended on row order. With the empty studio last, a publish that cancelled both
  reported zero places affected, needed no acknowledgement under paragraph 1841 and raised no
  notification under 1838. Three rooms over five days reported five cancellations out of
  fifteen and a third of the held places.
- **A Critical Control bought with a free bool is not a control.** `acknowledged_impact` cost
  the same permission as a publish that disturbed nobody, which is MOD-013's `priority:
  "critical"` finding exactly. And the preview that was supposed to inform it **could not assess
  the change**: `preview_publish` had taken a `rule` parameter from the start and nothing passed
  it, so it compared the live rule with itself and answered "nothing changes" -- then the publish
  moved eight classes and cancelled one a member had booked. An operator who did the right thing
  was misled by doing it.
- **A health fact is a health fact whatever column it is in** -- MOD-017's rule, hit again.
  `sch_session_changes.reason` is prose an operator writes about why a class changed, and a
  reviewer read "she is having chemotherapy on Tuesdays" out of `GET /scheduling/sessions/{id}`
  holding only the routine schedule read, while `/people/{id}` refused them 403. The sibling
  declaration in `classification.py` already said in as many words that a reason column is where
  a health fact goes in practice. It is masked unless the caller holds
  `scheduling.session.change` -- whoever can record a substitution can read why one happened.
- **A validation that runs after the commit is not validation.** `occurrence_count` was called
  after the `with tenant_scope` block, and only the rule's *span* was bounded, not its epoch --
  so a thirty-day rule in year 9999 passed `check_rule`, walked `day += timedelta(days=1)` off
  the end of `date`, and answered 500 with the draft, its rule, its policy and its requirements
  all committed. `sch_templates` has a unique index on the code, no DELETE grant and no path
  that retires a draft, so one mistyped year took that template code for ever and every later
  publish of the row was another 500.
- **An idempotency key compared on one field is a hold handed to the wrong person.**
  `take_hold` checked the session and ignored the person, the count, the source and the
  reference -- so a request naming a different member got 201, the previous caller's `hold_id`,
  and (because the repeated branch omitted the field) no `person_id` at all. Bob received
  Alice's booking and nothing said so. The realistic input is a till reusing a per-shift
  counter, which is how a key gets reused in the field.
- **`str.isdigit()` is not `int()`.** It is true for Unicode superscripts that `int` refuses, so
  an age restriction of `'\u00b2'` passed the guard and raised a bare `ValueError` two lines
  later -- which nothing in the request path catches, so the route answered 500 rather than 422.
  `isdecimal` is the predicate that matches.
- Four more with shapes this file records: a resource hold had none of the state guards a *place*
  hold has, so a room could be held for a cancelled session and a retired resource assigned to a
  live one; the session identity guard covered `capacity` and not `overbook_places`, which is
  half a guard because the ceiling is their sum; `retire_template` took a correlation id and
  dropped it, with no column to put it in, while `sch_resources` had carried one from the start;
  and `superseded_by` -- added during this very review to fix the substituted-instructor hold --
  was itself an attribution a later write could erase, which is why an assignment now has a key
  of its own and a supersession is final by trigger.

**And the evidence claimed more than it proved, in three shapes this repository has a rule for
each of.** Both of the module's defining absence sweeps were prefix-scoped, so a reviewer created
`plt01.class_rosters` with a `held_count` and a naive `timestamp`, satisfied the prefix-free RLS
sweep, and watched all 91 checks pass -- the third time a control has escaped on a name. Seven
cases were proved by a *sibling* rather than by the constraint they named. And eight "not blank"
cases used spaces, which `btrim` strips, so none of them could tell the `~ '[^[:space:]]'` form
this repository standardised on from the one it banned across 118 constraints.

**Check 91 is new and is the answer to the first of those.** It pins the *text* of every CHECK,
every index and every trigger on the module's tables, plus an `md5` of each trigger function's
body, compared as a set in both directions. A drop, a weakening and a deleted plpgsql branch all
change the text, so all three fail in CI rather than at the next sweep -- which closes the hole
MOD-018 paid for, where a reviewer deleted an unprobed branch and the suite reported 84/84. It
does not replace the behavioural cases: a pin says the rule is still written down and only a case
says it still bites. It caught two of this module's own changes while they were being made, and
it gives an unprovable constraint somewhere honest to live: `sch_templates_status` has no
isolating case and cannot have one -- a reviewer tried six routes to an unknown status and every
one was refused by a sibling -- so the pin is its whole evidence, and the migration says so.

Things worth knowing before extending it:

- **A resource with no working hours is unconstrained; one with a weekly rota is bound every
  day.** A room, a court and a bike have no rota in any meaningful sense and on the day a gym
  opens nobody has one, so an empty window list cannot mean "never available" -- the first
  version read it that way and nothing could be scheduled in a tenant at all. But a coach
  rostered Monday and Wednesday is refused on Friday, because a weekly rota is a statement about
  the week; and a *dated* working window binds only its own date, because "open specially this
  Sunday" must not close the rest of the week. Three cases, and the first two were each a bug.
- **A substitution supersedes the outgoing hold rather than leaving it.** Leaving it made a coach
  sent home ill unschedulable everywhere else at that hour, for ever. The row stays, so the
  window a past conflict was decided against is still readable; what moves is whether the hold
  still applies. A re-assignment is a new assignment row, which is what keeps the attribution.
- **A relocation moves the session and the holds that belong to a building.** A studio, a zone, a
  court and the bikes in it are the site; a coach and the class format travel. Keyed on the
  *kind* rather than on whether the resource has a location, because a coach has one too.
- **The impact assessment is keyed on the slot, which is the instant and the span.** So a class
  republished at fifteen minutes instead of sixty is not "unchanged" -- `Instance.ends_at` is
  carried for no other purpose -- and scope is compared against the *local* date, because
  `effective_from` is a date an operator typed.
- **`conflicts.detect` checks a requirement's shape and not the whole authoring rule.** "A named
  requirement is for one resource" is true of a template, which a person writes; it is false of a
  requirement rebuilt from what a session already holds, where twenty bikes are one named row
  with a quantity of twenty.
- **A spring-forward gap is stepped until the hour exists, and the local date is re-derived.**
  One hour is enough for every zone that shifts by one and Antarctica/Troll moves by two; and
  America/Nuuk's gap is 23:00 to 23:59, so an adjustment crosses midnight and the two facts the
  row keeps separately would otherwise contradict each other.

Known gaps, deliberate:

- **Nothing books anything.** This is the schedule and the capacity; the member's reservation,
  the waitlist, the no-show policy and the appeal are MOD-020's. `sch_capacity_holds` is the
  authority a booking will cite, which is why it lives here and not there -- "no cross-domain
  write-table access", the same shape as MOD-017's entitlement reservation.
- **Nothing drives anything on a schedule.** A session is generated when somebody asks, and
  nothing completes a session whose time has passed, sweeps a lapsed hold or expires a booking
  window. The worker runtime exists and none of these is wired: completing a session is a
  statement that it happened, which is the same judgement MOD-020's settlement needs.
- **`sch_availability_windows` has a reader now, and had none since the module was built.**
  `set_availability` wrote working hours, breaks and dated absences and nothing in the product
  could show what it wrote -- so a rota could be set and the only way to learn what it said
  was to publish a template against it and read the refusal. The fifth instance of this
  build's "a writer with no reader" shape. `GET /scheduling/availability` is a resource's week:
  the rota rows that bind on each local day, the sessions it still holds, and
  `availability.unavailable_reason` per held session -- so **a booking the rota now refuses is
  returned and flagged rather than dropped**, which is ADM-SCH-04's own requirement. Three
  decisions in it are worth knowing: every span is read in the *resource's* own location zone
  and never the session's, which is the defect a reviewer found in `Window.timezone`; open
  minutes are `null` where no working window binds rather than zero, because "a room has no
  rota" and "the rota says no hours" are different facts and `26 of 0 hours booked` is what
  conflating them produces; and a `time_off` reason is masked unless the caller holds
  `scheduling.availability.write`, because it is the one free-text column in a rota and the one
  place a health fact goes in practice -- the exception itself is never hidden.
- **A rota window can be withdrawn now, and until it could the write form was unbuildable.**
  `sch_availability_windows` carried `GRANT SELECT, INSERT` and nothing else, so a day off
  entered on the wrong date, a shift typed as 06:00 instead of 16:00 or an absence written
  against the wrong coach had **no remedy anywhere in the product** -- a rota could only ever
  grow. Invisible while the only writer was a seed script, and decisive the moment somebody
  can press a button: `scheduling.availability.write` is routine and AAL 1 by design, and a
  routine permission whose every act is uncorrectable is MOD-013's "an irreversible act must
  not be declarable on a routine permission" from the other side. `0017` adds the four
  withdrawal columns with their attribution constraint and a one-way trigger -- a withdrawal,
  **not a delete**, because "was this coach marked off on the fourteenth, and who said so"
  gets asked precisely when somebody was turned away.
- **And it revoked a grant nobody had ever used.** `0013` granted
  `UPDATE (starts_at, ends_at, reason)` on that table to both runtime roles with the comment
  "a rota is edited, so a window's times move", and **no service ever wrote them** -- an
  unattributed retime of the values the table exists to state, with no column anywhere to
  record that they moved. That is MOD-016's `cat_prices.effective_to` for the second time in
  this build. Correcting a window is withdrawing it and adding the corrected one, which is
  the same edit with a history.
- **`week_from` starts the week on Sunday, which is the design's call and not this module's.**
  ADM-SCH-04 draws its columns SUN-SAT and dates its sample week to a Sunday, the working week
  in this product's own market. The first version started on Monday because `Window.weekday` is
  0-Monday -- which is a *storage* convention and says nothing about how a week is read: the
  rota rows are keyed by weekday number either way and only the order of the seven dates moved.
  It is **not** a declaration of which days anybody works; `GET /reports/attendance` still
  refuses to label a day set "weekdays", because nothing in this build records one.
- **Two overlapping working rows double-counted their overlap**, found by the test written for
  the arithmetic rather than by a reviewer. A rota entered as 09:00-13:00 and then widened by
  adding 11:00-15:00 -- rather than by editing the first row, which nothing in this module
  makes anybody do -- is six hours open and was reported as eight. That figure is the
  denominator of ADM-SCH-04's own "26 of 34 available hours booked", so inflating it makes
  somebody look less booked than they are. `availability._merge` is the fix.
- **No travel buffer is enforced.** `availability.check_travel` decides and nothing calls it:
  the buffer is a per-tenant figure the sources do not state, and paragraph 1835's
  cross-location case needs a resource scheduled at two sites in one day, which the location
  guard now makes rarer rather than impossible.
- **A cancelled session cannot be replaced at the same rule and instant.** The one-way
  cancellation is deliberate -- members have been told -- and `UNIQUE (tenant_id, rule_id,
  starts_at)` is the generation idempotency, so a class cancelled for an ill instructor can
  never be re-filled in that slot from that rule even once a substitute is found. Found by a
  reviewer; the interaction was not designed, and the remedy is a new rule version.
- **No waitlist.** `waitlist_capacity` is recorded on the policy and nothing reads it, because
  the waitlist is OPS-02's: position, timed promotion and the offer expiry are its decisions.
- **A session is not completed by anything.** `completed_at` and the `completed` status exist and
  only a caller can set them; attendance is settled per hold.
- **`skills` is the caller's word.** Nothing in this build stores a skill, so a skill restriction
  is only as good as whoever answers it -- the one eligibility fact that is not derived, said out
  loud in the body rather than left to be found.
- **Seven free-text columns are residue an erasure cannot reach**, all declared by hand because
  the sweep matches column names. The one exception is a `staff` resource's display name, which
  is a person's own name and *is* cleared, because the row says which person it is.
- **The timeline does not know about any of this.** MOD-014 projects nine event types and none
  of MOD-019's five is among them, so a member's timeline shows no class they were booked into.
- **The surface is read-only, and one of its writes was never the reason why.** `web/`
  renders the calendar, one session and now a resource's rota -- see "The web app" -- and
  every write here is a form that does not exist: publishing a schedule, generating
  occurrences, substituting an instructor, cancelling and relocating. **This bullet used to
  say each is a stepped-up permission, and that was false for the one the design puts a
  button on.** `scheduling.availability.write` is `configuration` with no financial class --
  routine, AAL 1 -- and the catalogue says why: "a rota is edited by the people who run the
  floor, and refusing them a step-up every time somebody books a day off would make the rota
  wrong instead". So ADM-SCH-04's "Add an exception" is a form this app could build today,
  and `/rota` names it as the next piece of work rather than as a refusal. The other five
  writes really are stepped-up, which is the same reason the hierarchy surface is read-only.
- **The board shows today onwards**, which means its row count drops by one each time UTC
  midnight passes after a fixture is seeded. That is a property of the window rather than a
  defect, and it is why the spec asserts what every row *says* rather than how many there
  are -- an exact count would fail at 00:00 UTC for a reason that has nothing to do with the
  product.

**MOD-020 (OPS-02 booking, waitlist, attendance and appeals) -- implemented, gated and
reviewed.** Seven `bkg_` tables in `plt01` under the same forced RLS, nine trigger functions,
`app/booking/` beside them, and twenty-one HTTP routes. Working: versioned booking policies a
booking snapshots and that can be retired; bookings that take MOD-019's capacity hold in the
transaction that writes them; a stable, explainable denial over ten declared reasons;
order-independent quotas and concurrent limits; cancellations with the consequence the
booking's own policy declares; the gym's own cancellation releasing bookings rather than
blaming anybody; a waitlist with a derived tier, an enforced cap, offers that reserve before
notifying, a member's own exit, and expiry that keeps a place; check-in with attribution;
no-shows derived from three facts with warnings and strikes; attendance intents; and a
two-party appeal whose remedy follows what it is against. Seven events are produced. Proven:
isolation checks 92-98, mutation-tested in two rounds -- 564 mutations before the reviews and
580 after the remediation, of which 577 were caught by the check that guards what was broken,
none were uncaught, and three were ill-formed (a generated body mutation that deletes the
*lookup* a later branch reads, so every row fails and the seed catches it -- the property, but
not a check). 36 trigger branches across nine functions are probed behaviourally and pinned by
digest. 71 domain unit tests with no database; 54 HTTP tests, inside a suite of 1,785.

**The module owns no capacity, and that is its premise.** Paragraph 4145 draws the line --
"Schedule owns published occurrences/resources/capacity. Booking owns member
reservation/waitlist/cancel/attendance intent" -- so paragraph 4697's two invariants are
MOD-019's: capacity never falls below zero, and a duplicate waitlist promotion cannot consume
two seats. There is no seat count in any `bkg_` table and check 95 sweeps the whole of `plt01`
for one. What makes the borrowing real is that `take_hold_on` and `release_hold_on` are
connection-taking: a booking and its hold commit together, which is MOD-010's `append_event`
argument applied to a seat. A hold with no booking is a place nobody can book.

Six decisions carry the module:

- **The hold is the authority and the booking cites it.** `hold_id` is `NOT NULL` with
  `UNIQUE (tenant_id, hold_id)` and a five-branch trigger relating the hold to the row's own
  session, member and status, and the member's entitlement grant to the member. A reviewer
  could not write a booking with no real place, two bookings on one place, or a booking whose
  hold belongs to somebody else.
- **A denial is from a closed set and is stable.** Paragraph 1892 and 5032: `DENIAL_REASONS` is
  ten values, `_evaluate` asks every question the command asks in a fixed order, and
  `denial.is_stable` is a function a test asserts rather than a promise in prose. The
  eligibility read runs the *same* function, so a surface cannot be told yes and then refused.
- **A booking snapshots the policy it was made under.** What a member owes for cancelling late
  is decided months later and must be decided on the terms they agreed to, so retiring a policy
  stops the next sale and changes nothing about the last.
- **A sanction is derived from three facts and nobody can declare one.** The booking is still
  open, nobody checked in, and *both* the check-in window and the session have passed. Two
  tenants cannot disagree about what a no-show is.
- **An appeal is two acts by two parties, and its remedy follows what it is against.** The
  subject is on the row, the decider is derived from the authenticated identity and needs a
  person record, and `against` is checked against what the record actually carries. A warning
  or a strike is overturned here; a fee is MOD-017's and the response says so.
- **There is no predictive no-show score.** Paragraph 1884 asks for one and
  `consequence.predicted_no_show_risk` raises, annotated `NoReturn`. The durable reason is that
  paragraph 1889's "must not discriminate unlawfully" is a property of a population under a
  model rather than of an expression, so no function can promise it -- MOD-011's percentile
  refusal, with a person as the subject. Both sanctioned uses, reminders and controlled
  overbooking, are reachable without one.

**Three reviewers worked this module in parallel -- the schema, the decision modules, the
request path -- and all three returned CHANGES_REQUESTED. Twenty-one blocking defects.** Each
is carried forward as a rule, because each is a shape that has now recurred:

- **A declared state nothing writes is a feature that silently harms somebody.** `released`
  and `session_cancelled` were both declared and both documented as existing so that "somebody
  does not get a strike for a class the gym called off", and nothing in the build wrote either
  -- so settling a cancelled session ran the ordinary no-show path and recorded **every member
  of it** as absent, with a fee, a forfeited credit and a warning or a strike. The state is
  one-way by trigger and `bkg_no_shows` has no DELETE grant, so it was permanent and the only
  remedy was an appeal per member by hand. The module's own code named the failure in two
  places. **The worst defect this module shipped, and a tenant reached it by doing nothing but
  cancelling a class.**
- **A guard whose two reasons are joined by `and` refuses in neither case alone.** `settle`
  required *both* that the check-in window was open and that the session was still running, so
  a settlement went ahead as soon as the session ended -- and a grace period longer than the
  class is inside the policy's own bounds, which a thirty-minute slot with forty-five minutes
  of grace reaches without trying. A member who walked in ten minutes late was written to
  `no_show` the moment the class finished: no way back, the fee charged, the strike counted,
  and the front desk's later check-in refused because the state had moved. Both reviewers found
  it independently, and the refusal's own message said "this session is not over" while not
  refusing.
- **A control keyed on a value the caller supplies, for the sixth module running.** Four here:
  `tier` on the waitlist body decided the queue order a premium member had paid for, so a basic
  member sent a zero and took their place; `person_id` and `subject_person_id` let any member
  cancel another member's class -- releasing their seat and recording a late fee against them
  in an insert-only table -- book in their name against their quota, declare their attendance
  and appeal as them; and `against` was stored beside an appeal's decision and never read.
- **A window that looks one way is defeated by the order of the requests.** The quota ran
  backwards from the session being booked, so a member on three a week booked the last class of
  the week first and every earlier booking saw an empty window: **seven classes under a quota
  of three**, with nothing adversarial. Two sessions at the same instant were worse, because
  the anchor sat on its own window's excluded edge: five classes at six o'clock each saw
  nobody. The rule now is that no window of that length may hold more than the quota, which is
  the same answer in any order.
- **A calendar bucket computed in whatever zone the instant carries is the wrong day.**
  `sch_sessions` stores a UTC instant *and* the zone it came from precisely because neither is
  derivable from the other, and the service passed neither -- so a "two a day" policy in Sydney
  reset at eleven in the morning and a member took two before it and two after. MOD-017's
  `AT TIME ZONE` lesson one module later, with the correct value already in the caller's hand.
- **An idempotency key compared against nothing, three times.** The appeal's was the worst: a
  member with two strikes reusing a per-shift counter was handed the *first* appeal back with
  201 and `repeated: true`, so their second strike had no appeal, nobody saw one in the queue,
  they were told theirs had been heard and rejected, and the thirty-day window ran out. It
  landed on the one remedy a sanction has. The intent's returned 201 for a write that never
  happened, against the wrong booking and reporting the wrong intent. And `confirm_offer`
  wrote into `create_booking`'s key namespace -- MOD-018's "an idempotency namespace a caller
  can write into is not a namespace" -- so a till reusing one counter had its confirmation
  refused as "already confirmed", which was the opposite of true: the offer was never
  confirmed, the member could not confirm it, and the seat stayed held.
- **A read that computes its own answer disagrees with the write path it explains.**
  `_evaluate` left the session's restrictions to `take_hold_on` and the entitlement to a lookup
  that ran after it, so the eligibility read answered `may_book: true` for a fourteen-year-old
  on an 18+ class and for a member with no pass -- the two refusals that matter most, on the
  surface that exists to explain them. `ineligible` and `no_entitlement` were declared and
  never produced; the refusal arrived as free prose outside the closed set.
- **A mask keyed on the cheapest permission in the module masks nothing.** The cancellation
  reason was readable by any holder of `booking.booking.write`, which cancelling your own
  booking needs -- so **every member in the tenant held the key to every other member's
  cancellation prose**, in a build where `member.health.read` is unreachable by anybody and
  `/people/{id}` refuses the same caller. A reviewer read "I am having chemotherapy on
  Tuesdays" with it. The quantifier was the defect: anybody who could write *a* reason read
  *every* reason.
- **An edge the writer takes has to be in the state machine, and leaving it out was worse than
  the defect it was meant to prevent.** Making an expired offer live again (so a member asleep
  at six keeps their place rather than being removed from the queue) left the trigger refusing
  `expired -> offered` -- so from the moment one member failed to answer, every promotion on
  that session picked their entry, took a hold, was refused and rolled back, and **nobody was
  promoted again while places sat free**. Both encodings agreed with each other and neither
  agreed with the service. Introduced while fixing a review finding and found by the next
  reviewer, which is the "a remedy is new capability, so review it as such" rule from MOD-007.
- **A constraint that permits NULL is opt-in to the writer it exists to stop.**
  `decider_is_not_the_subject` compared nothing when `decided_by_person_id` was NULL, so a
  writer decided an appeal with the subject's own login by leaving the person id out, and the
  no-show was overturned. The Python layer was hardened first, which left the schema the
  weaker of two layers that were supposed to fail independently.
- **Two tables had no correspondence trigger at all**, and they were the two where a wrong row
  is permanent. A reviewer wrote a strike on a member who had no booking, from a booking they
  had *attended*, naming a different and cancelled session, under thresholds unrelated to the
  policy the booking snapshotted -- and `_no_show_count` counts by person, so it moved the
  victim's threshold immediately. And a late fee on the wrong member for a booking never
  cancelled. The free-cancellation constraints were reachable past by declaring the other
  occasion: a booking the *gym* released, written up as the member's own late cancellation, was
  charged.
- Three smaller ones with shapes this file records: `next_to_offer` refused to look past a
  single outstanding offer, so five cancellations two hours before a class filled two seats;
  `waitlist_capacity` was declared on MOD-019's policy and read by nothing, which made
  `waitlist_full` an outcome nothing could produce; and `withdrawn` was a declared state no
  route wrote, so a member could not leave a queue and was auto-promoted into a seat they no
  longer wanted while somebody who did want it was told the class was full.

**And the evidence had nine holes, in shapes the rules file names.** Two trigger branches had
no isolating probe -- each was answered by a *different* control, one by a sibling trigger and
one by a sibling branch in the same function, so the probe-count assertions could not see them.
Six constraints and two unique rules had no isolating case: three were subsumed by siblings
(deleted rather than tested harder, MOD-016's judgement), two had no case at all, and
`UNIQUE (tenant_id, hold_id)` -- which the header calls paragraph 4144 at the place -- was one
of them. Five weakenings were caught by nothing. And two properties the migration asserts in
as many words were verified by nothing in 39,000 lines: nothing in this suite had ever read
`proconfig`, `prosecdef` or `tgenabled`, so a reviewer reset a pinned `search_path` and granted
PUBLIC execute on a trigger function with every check passing. Check 96 reads all three now,
swept from the catalogue, and it caught my own two new functions the moment I added them.

Things worth knowing before extending it:

- **`take_hold_on` takes the connection, and `_evaluate` reads the capacity without locking.**
  The count it reads decides whether to *offer the waitlist*, which may be stale without harm;
  the hold is what settles it, under MOD-019's row lock. A second lock here would be a
  different lock ordering on the same row.
- **A no-show is settled by the sweep, and the sweep is not reachable with a caller-supplied
  instant.** No route takes one, because a settlement time a caller chooses decides whether
  somebody is recorded absent -- MOD-011's unbounded `observed_at` in a worse place. The HTTP
  tests that need a finished session therefore settle through the service, and say so.
- **A suppressed request is still authored.** A denial leaves no booking, but it is structured:
  a surface decides what to offer from `reason`, and `offer_waitlist` is why `full` and
  `waitlist_full` are different values.
- **A member acting for themselves and a front desk acting for them are different
  permissions.** `booking.booking.act_for_another` is routine, because a shift worker does it
  all day and a step-up would stop the ordinary job; what makes it safe is that a member's app
  is not granted it.
- **The derived keys are hashed, not truncated.** Two 200-character keys differing in their
  last four characters produced one hold key, so one member's booking refused another's as a
  duplicate in a class with nine free places.

Known gaps, deliberate:

- **Offers expire on a schedule; sessions still settle only when asked.**
  `booking.expire_offers` is a worker job at sixty seconds, so a seat held by an unanswered
  offer is released for the next person in the queue. Settlement is not a job and deliberately
  so: it decides whether somebody was absent, and `settle_session_bookings` takes no
  caller-supplied instant precisely because a settlement time a caller chooses decides who is
  recorded a no-show. Driving it needs a decision about *which* sessions are due, which is
  product nobody has stated. A `lapsed` entry is still never swept.
- **Nothing charges or credits anything.** `fee_due` and `credit_forfeit` are decisions for
  MOD-017 to act on, and an upheld appeal about money is recorded rather than executed. Real
  financial expenditure is owner-reserved.
- **No notification.** `promote_waitlist` reserves the place and returns `notified: false`,
  because MOD-013 sends the message from the row and a module claiming to have sent one is the
  fabricated-evidence shape this codebase has been bitten by five times.
- **A cancellation appeal has no executor.** `bkg_cancellations` carries no UPDATE grant, so
  upholding one is recorded with both nulls disclosed in the response. Half of `APPEALABLE` is
  therefore evidence rather than action for a cancellation.
- **`skills` is still the caller's word**, as in MOD-019: nothing in this build stores a skill.
- **A check-in is recorded, not performed.** Nothing reads a turnstile, so the row carries a
  claim by a named actor at a time -- MOD-012's `validated` shape.
- **A member's no-show count never decays.** A member struck in 2026 is struck by the same
  three misses in 2029; the policy has no window field. A product decision rather than a
  defect, and worth stating beside `warn_after_no_shows`.
- **The timeline does not know about any of this.** MOD-014 projects nine event types and none
  of MOD-020's seven is among them, so a member's timeline shows no class they booked.
- **Nine free-text columns are residue an erasure cannot reach**, all declared by hand.
- **A front desk can check somebody in now, and that is the one write this module has a
  form for.** FD-06 is the screen -- see "The web app" -- and what made it buildable is the
  permission's own class: `booking.attendance.write` is `data_access` with no financial
  class, so a receptionist at an ordinary password sign-in marks a member present. Every
  other write here still has no form: booking, cancelling, joining a waitlist and appealing
  are built on the server and nothing on any surface calls them, so **a member still cannot
  book a class in this build and a front desk still cannot do it for them.** The roster read
  also carries two things it did not: each booking's prior no-show count, which FD-06 draws
  as context for the coach and which is the same figure `consequence` is given when it
  decides a sanction; and each booking's **check-in window**, from `attendance.checkin_window`
  rather than a second computation, because a screen that offered the button outside it
  handed a desk a control the module answers 409 to.

**MOD-021 (HW-01 hardware, edge bridge and device fleet) -- implemented, gated and
reviewed.** Twelve `dev_` tables in `plt01` under the same forced RLS, fourteen trigger
functions, `app/devices/` beside them, and twenty-five HTTP routes under `/fleet`. Working:
a device-type catalogue whose capability set freezes when a second person publishes it;
devices that snapshot their type's capabilities at registration; certificates held as a
fingerprint and a vault reference; hardware safety profiles and the seven commissioning
tests that gate a door going into service *and* every unlock afterwards; signed policy
snapshots with a bounded TTL and a monotonic revocation epoch; a command queue whose only
door-touching action is a momentary unlock; firmware releases with a final withdrawal; edge
health with a derived reachability; and sync-conflict records. Six events are produced.
Proven: isolation checks 99-105 (including 103b's cases and 104b's identity probes),
mutation-tested in three rounds -- 725, then 800, then 810 mutations, the last with none
uncaught, none ill-formed and all thirty-five plpgsql branches caught by the probe that
names them; 50 domain unit tests with no database; 48 HTTP tests; 21 named regression tests.

Six decisions carry the module, and five of them are refusals:

- **Section 16.4 is a fire code, so its rules are refusals with no permission that buys
  them.** `safety.HOLD_COMMANDS` is a list of what this software will never do and
  `COMMAND_ACTIONS` is the vocabulary; the two do not intersect, and `check_command_safety`
  has no override parameter, no reason field and no stepped-up permission that unlocks it.
  **And the vocabulary is not the whole control**: `arguments` was an unvalidated
  passthrough, so a reviewer sent `{"mode": "hold_open", "hold_seconds": 86400}` on an
  `unlock_momentary` and the row the edge agent parameterises its relay from -- and verifies
  by digest -- carried hold-the-door semantics. `COMMAND_ARGUMENTS` declares what each
  action takes and an unlock takes nothing at all, because a door this software can
  parameterise is a door it can hold.
- **A fail-secure barrier on an egress path is refused at commissioning**, not warned about,
  and the claim is on a row whose every field carries no UPDATE grant: a building's safety
  record is superseded by another commissioning that says who did it, never edited.
- **Paragraph 4175 is enforced at the row, not only at the transition.** `activate_device`
  refuses a door with a failing test, and so does the unlock trigger -- which reads the
  latest outcome per test name and requires all seven. A failed re-test also quarantines a
  door already in service, in the transaction that records it, because the gate is read at
  activation and a live device never returns to it.
- **A snapshot has a bounded TTL and an epoch that only goes up**, and both bounds are
  measured against a clock the writer does not choose: `issued_at <= now() + 5 minutes` is
  what makes "a minute" a minute. The trigger that compares a snapshot's epoch against the
  device's takes `FOR UPDATE`, because a plain read let a revocation and a snapshot commit
  side by side.
- **There is no column a secret could live in.** `vault_ref` is a locator by constraint and
  there is no key, certificate body or signature column anywhere -- MOD-012's shape, where
  the control is an absence. Check 101 sweeps the whole of `plt01` for the names *and* for
  the shape, because a name list is whack-a-mole: a reviewer called the columns
  `key_material`, `cert_body` and `online_cached` and all thirteen names missed them.
- **A device's capabilities are snapshotted from its type, and the type's set freezes when
  it is published** -- by a second person, because declaring `access.actuate` is what makes
  a model commandable as a barrier.

**Three reviewers worked this module in parallel -- the schema, the decision modules and the
request path -- and all three returned CHANGES_REQUESTED. Twenty-three blocking defects**,
every one inside a green 116-test suite. Each is carried forward as a rule:

- **A lookup that proves something exists does not authorise what you do next, with a fire
  code as the subject.** The unlock trigger asked whether a `dev_safety_profiles` row
  existed; its own message and this file's header called that the commissioning gate.
  **Nothing in the schema read `dev_commissioning_tests`, ever** -- so a door that reached
  `active` by any writer other than `activate_device` opened with six of seven fire-code
  tests never run, and a failed fire-alarm re-test changed nothing at the row. My own
  check-104 probe credited that branch with paragraph 4175 using a device that had neither
  a profile nor a test, so the probe could not tell the two apart and **the control it
  credited did not exist**.
- **A window measured between two columns the same writer supplies is not a window.**
  `expires_at - issued_at <= interval '60 seconds'` with `issued_at` caller-supplied is a
  minute starting whenever the writer says: a reviewer parked an unlock three days out,
  openable for forty-five seconds on the night it chose, with every CHECK satisfied -- the
  attack that constraint's own comment names, performed against the writer it names. The
  snapshot TTL was the same at seven days. The repair is a one-sided bound against `now()`,
  one-sided because a lower bound fails every row on a restore.
- **A trigger that reads a parent row to decide whether a child may be written has to lock
  it** -- MOD-019's `FOR SHARE` finding one notch weaker, because all three of these took no
  lock at all. Two ordinary transactions at READ COMMITTED wrote a snapshot at an epoch the
  device had already left, valid for twelve hours; the same shape let a capability land on a
  type being published, and a quarantine race an unlock.
- **A control consulted once is a control with a window, and here it was two gates.**
  Revoking a device's last usable certificate computed `device_can_still_authenticate`,
  returned it to the caller and acted on nothing, so a live access point with no credential
  went on accepting unlocks and policy snapshots. A failed commissioning test did the same.
  Both now take the device out of service in the transaction that records the fact.
- **A failure path inside a batch loop must not raise** -- MOD-010's rule, and the permanent
  case is the one that triggers it. `sweep_offline` keyed its event on the silence that
  produced it, which is *stable while a device stays offline*, so the second sweep raised
  out of `tenant_scope`, rolled the batch back and answered 409 -- and every device that had
  gone quiet behind it was never reported. `append_event`'s own comment says a command that
  means to be idempotent checks before it acts; this one did not.
- **An idempotency key compared on fewer fields than the command takes**, for the third
  module running, and with a docstring four lines up claiming all five. A console reusing
  its per-shift counter was told 201 `repeated` and shown a live command id while the
  command that exists targeted a different door with different arguments.
- **Evidence with nobody's name on it answers nothing** -- the seventh module.
  `dev_commands` carried `issued_by` alone, so the only name on a row saying a door opened
  was the party that did *not* make the claim, and `failed`, `acknowledged`, `delivered` and
  `expired` named nobody anywhere. A re-activation -- which re-runs the commissioning gate
  -- wrote no actor at all, leaving a live door's fire-code attribution naming somebody who
  did not make that decision, uncorrectably, because the column is final by trigger.
- **A permission's name is a claim about what it is for.** All three device-type routes were
  gated on `devices.firmware.write` and there was no `devices.type.*` permission anywhere,
  so a role granted "release firmware" silently chose which models of hardware may be
  commanded as doors. And `maintenance` cost the routine write while quarantine cost a
  stepped-up one, although `enrollment.OPERABLE` is `{"active"}` and both stop every command
  -- so the weakest write credential in the module shut every door in a tenant, could not
  undo it, and the fleet view reported the tenant healthy throughout.
- **A field required of the caller, validated, and thrown away** -- MOD-012's `release_run`
  shape. `record_sync_conflict` demanded a statement of what diverged, checked it was not
  blank, answered "recorded, not resolved" and wrote only two hex strings to the outbox.
  There was no table. There is now.
- **Nothing free-text reaches `evt_outbox`**, and the validation was applied in exactly the
  wrong places: `content_digest` and `image_digest`, which land in a table, were shape-
  checked, while the sync-conflict digests, which land *only* in the outbox, accepted
  anything 64 characters long. So did `agent_version` and a firmware `version`. Fourth,
  fifth and sixth occurrence after `cfg_exposures.subject_id`, `notification.failed.reason`
  and `bundle.fulfilled.order_reference`.
- **A pair of caller-supplied ids that nothing relates is two halves of a control**, which
  is this module's own stated standard, written three hundred lines above two supersession
  pointers that related nothing. A turnstile's certificate was recorded as superseded by a
  scanner's, and a fire door's `fail_safe` commissioning by another door's `fail_secure` one
  -- so following that door's chain read "re-commissioned as fail_secure, no independent
  fire release", which is the exact row `egress_is_never_software_gated` exists to make
  unrecordable.
- Smaller ones with shapes this file records: a superseded certificate's replacement pointer
  and date were rewritable and backdatable while a revoked one was frozen; a committed
  command's `signature_ref` could be re-pointed while the digest it covers was frozen; three
  caller-supplied `jsonb` columns were unbounded on insert-only tables; and all twenty
  privacy declarations were actor columns, with eleven caller-written free-text and `jsonb`
  columns undeclared -- a reviewer wrote an address and a date of birth into two of them and
  read both back.

**And the evidence was weaker than the schema, which is the half only a sweep finds.** My
first round ran 725 mutations with none uncaught; a reviewer then ran 165 of their own and
found seven CHECK constraints with no isolating case, eleven weakenings admitted by every
case that named the constraint, and **the module's two defining partial unique indexes
proved by nothing at all** -- because a sweep that generates `ALTER TABLE ... DROP
CONSTRAINT` never runs against an index. Four of the eleven were `coalesce` removals, the
trap the rules file spells out and MOD-014 already paid for: every case sent a tab, none
sent NULL, so a device could be taken out of service with no stated reason on a row the
migration's own comment calls the only record there can be. Check 103b is the thirty-three
cases that answer them, and the third sweep ran 810 with none uncaught.

Things worth knowing before extending it:

- **A device with no capability rows is refused every command**, which reads as a broken
  unit rather than an unfinished enrolment -- so the snapshot is taken in the transaction
  that registers it.
- **`activate_device` is the only way back into service**, and it re-runs both gates on
  every pass. That is what makes quarantine a real remedy and what makes the re-activation
  attribution necessary.
- **The two supersession checks are deferred constraint triggers**, like the foreign keys
  they mirror: a rotation points the outgoing row at a successor that does not exist yet,
  because inserting first violates `one_active_per_device` and a null pointer violates the
  pairing. An immediate check would make the honest order unwritable -- and a probe for a
  deferred trigger has to say `SET CONSTRAINTS ALL IMMEDIATE` or it watches a transaction
  that never commits.
- **`devices.certificate.write` and `devices.command.unlock` are the `access` audit
  category**, which no MOD-021 permission used at first -- so
  `test_money_and_access_decisions_are_not_routine`, the catalogue's one automatic guard
  that a permission granting access needs a second factor, was structurally blind to the
  module whose subject is physical access.

Known gaps, deliberate:

- **Nothing drives any hardware.** No gateway, no relay, no outbound anything: a command is
  written for whatever collects it, and `settle_command` records what that thing reported.
  A row saying a turnstile opened, written by nothing that drives a turnstile, is the
  fabricated-evidence shape this codebase has been bitten by six times.
- **No WebAuthn, no mTLS handshake and no signature verification.** A certificate is a
  fingerprint and a vault reference; `signature_ref` locates a signature this build never
  made. The vault is the same one MOD-007's TOTP seeds, MOD-009's crypto-shred and MOD-012's
  webhook signatures are waiting on.
- **The offline sweep and the command expiry run; certificate rotation does not.**
  `devices.sweep_offline` is a worker job at five minutes against a half-hour silence
  threshold, and `devices.expire_commands` at sixty seconds, so a dead unit reaches a
  dashboard and an uncollected unlock stops reading as a door waiting to open.
  `credentials_due` is still called by a route only: it is **not idempotent across calls** by
  design, so scheduling it needs a record of what has already been announced.
- **`on_egress_path` is a caller's claim**, like `skills` in MOD-019 and `validated` in
  MOD-012. Nothing in this build can see a building, so a commissioning record is what a
  named person asserted at a time -- which is why the attribution and the evidence locator
  are mandatory and why the row cannot be edited.
- **No diagnostics bundle.** Paragraph 3080 names one; it needs an object store and a
  residency decision, the same wall MOD-009's export and MOD-014's progress media hit.
- **Twelve free-text and `jsonb` columns are residue an erasure cannot reach**, all declared
  by hand because the sweep matches column names. The *actor* columns are found by the sweep
  and were: adding `delivered_by`, `settled_by`, `reactivated_by` and a sync conflict's
  `reported_by` turned `test_every_subject_column_in_the_database_is_declared` red until
  each one was declared, which is the registry doing exactly what MOD-009 built it for.
- **The timeline does not know about any of this.** MOD-014 projects nine event types and
  none of MOD-021's six is among them.

**MOD-022 (ACC-01 check-in and access control) -- implemented, gated and reviewed.** Eight
`acc_` tables in `plt01` under the same forced RLS, ten trigger functions, `app/access/`
beside them, and twenty-one HTTP routes. Working: zones with a declared risk class and the
offline ceiling that follows from it; access points joining a zone to a MOD-021 device that
can actually move a barrier and is in service; policy versions drafted and published as two
acts by two people, frozen on publication; credentials held as a SHA-256 digest with a
bounded window for a rotating code and a replay cache behind it; one presentation evaluated
against the policy, the membership, the entitlement, the balance, the age, anti-passback and
the zone's capacity; a decision recorded as a receipt with a public line and a private
reason; the unlock issued through MOD-021 **on the same connection**, so a door that opened
and the decision that opened it commit together; events as what actually happened, which is
not what was decided; occupancy counted from events and disclosed as advisory; offline
reconciliation that judges a decision taken on a snapshot; and an emergency release reviewed
afterwards by somebody other than whoever ordered it. All six of ACC-01's events are
produced. Proven: isolation checks 106-111, mutation-tested in four rounds -- the reviewer's
own 98 drops, of which this module's suite caught seven; 136 drops, keys and branches, all
caught once checks 110 and 111 existed; 193 with the weakenings added, which found nineteen
more gaps; and 192 with none uncaught and none unrun, over 76 CHECK drops, 56 weakenings, 16
keys and indexes and all 44 trigger branches. Also 55 domain unit tests with no database and
50 HTTP tests, one per blocking review finding.

**This is the module that joins three planes that did not know about each other.** MOD-021
has the turnstile and no idea who a member is; MOD-017 has the entitlement and no idea where
a door is; MOD-020 records a check-in whose `CHECKIN_SOURCES` already names `device` with
nothing behind it. `acc_points` is the join MOD-021 deliberately did not make, and it is a
join rather than a column because a device becomes a door only once somebody says which zone
it stands at and which way it faces.

Six decisions carry the module, and the first is a refusal with no permission that buys it:

- **Egress is never software-gated, and the refusal is in the database.** Paragraph 4177 puts
  the way out of a building outside the Veyro application path, so there is no policy, no
  grace and no configuration that records a decision at an exit: `acc_decision_is_coherent`
  raises on a point that faces out *or* on a reader that reports an exit, and the only code
  it admits there is `point_not_an_entry`. A service could be bypassed; this cannot.
- **A credential identifies, and the policy and the entitlement authorize** (paragraph 4155).
  So no column holds a credential in the clear -- `credential_digest` is a SHA-256 and there
  is no card number, no PAN, no secret and no key anywhere in the module, which check 106
  asserts as an absence because an absence is what a later migration restores.
- **A decision is a receipt with two reasons**, which is paragraph 1944's Critical Control
  written as a pair of columns: a public line a door may say out loud and a private reason
  only a permission holder reads. `acc_decisions_restricted_is_masked` makes the five codes
  that disclose a membership, an entitlement, a balance, an age or a safety hold carry the
  discreet line, by constraint rather than by convention.
- **The correspondence trigger, which is most of the module's integrity.** A decision names
  six things -- a point, a zone, a credential, a person, a policy and a policy snapshot --
  and five of them could be another tenant's business entirely if nothing compared them.
  Every one is compared, including the snapshot, whose device must be the door's own.
- **Occupancy is counted from events and is advisory, and says so.** Paragraph 4180 wants a
  count; a count built from readers is wrong the moment somebody holds a door, so
  `occupancy.py` derives it from entries and exits and every surface that shows it carries
  the paragraph's own disclaimer. A capacity policy at a zone with one reader therefore
  **does not refuse** on that number, which a reviewer found by walking through a building.
- **An emergency release is not an unlock, and the second person comes afterwards.** A fire
  alarm cannot wait for an approver, so the order is one act and the review is a separate one
  by somebody who is not the orderer -- the opposite trade from MOD-016's discount approval,
  deliberately, because the harm of a wrongly-refused release is a locked fire door.

**Three reviewers worked this module in parallel -- the schema, the decision modules and the
request path -- and all three returned CHANGES_REQUESTED.** Each finding is carried forward
as a rule, because each is a shape that has now recurred:

- **Gate the fact, not the sentence.** Both reviewers found the same thing: the public and
  private reasons were split correctly and the real `code` was returned beside them, so every
  one of the five restricted codes reached a reader through the field a surface actually
  renders. The discreet line was doing nothing. `zones.public_code` is the fix, and the
  lesson generalises past this module -- a mask applied to the prose and not to the
  enumeration is a mask on the part nobody reads.
- **Never believe a caller's description of itself** -- MOD-007's first rule, in a building.
  A presentation carried the credential's `kind`, and the kind decides whether the rotating
  window and the replay cache apply: a reviewer enrolled a `qr_rotating` credential, presented
  it as `nfc_card` with a month-old token, and was granted. The kind comes from the stored
  credential now, and the request does not carry one.
- **An idempotency key compared on fewer fields than the command takes**, for the fourth
  module running, and three times here. A reused key with a *different card* returned the
  previous decision -- so a till reusing a per-shift counter presented a revoked card and was
  handed somebody else's grant. An override wrote into the ordinary decision namespace, which
  is MOD-018's "a namespace a caller can write into is not a namespace". And an emergency key
  reused for another zone released the first zone's doors and reported the second's.
- **A failure path must not carry on inside a transaction PostgreSQL has aborted.** The
  replay insert caught its own unique violation -- which is the replay being *detected* --
  and went on to record the refusal, in a transaction that was already dead: the caller got a
  500 and the attempt was recorded nowhere, so the one control that notices a cloned rotating
  code left no evidence at all. The detection happens before the write now.
- **A declared value with no writer is a feature that silently does nothing** -- MOD-020's
  rule, and a reviewer tested it the way the rule says to: they grepped the writers of all
  nineteen denial codes and found one that nothing ever produced.
- **A lookup that proves something exists does not authorise what you do next.** An access
  point could be declared over a device that had been registered and nothing else -- no safety
  profile, no commissioning tests, never activated. MOD-021 still refused the unlock, so no
  door opened; what was created was a point that **reads as commissioned and can never work**,
  while a decision at it answers `granted`. Paragraph 4175 is explicit that a failed or
  missing commissioning blocks the point going into production, and declaring the point *is*
  that. The actuator trigger now reads the device's state.
- **A rate-limit budget that does not exist is not a limit.** `access/evaluate` named a budget
  `ratelimit.BUDGETS` did not declare, and `decide` defaulted to allowing -- so the one
  unauthenticated-adjacent route in the module was unlimited while reading as limited.
  `decide` refuses an undeclared key now, and
  `test_every_rate_limited_route_names_a_budget_that_exists` walks `main.py` with `ast` and
  asserts every `rate_limit(limit_key=...)` names a declared one. Mutation-proven, because a
  structural test that passes vacuously is the thing it is written against.
- **A `both` lane decides nothing on the way out either.** A turnstile that reads in each
  direction is the arrangement that makes paragraph 4177 hard: the point's own `direction` is
  `both`, so nothing in the row said which way this particular person was going, and a
  reviewer walked a member in and then refused them on the way out. `reported_direction` is
  the column that carries what the reader saw, and the egress branch reads it as well as the
  point's.
- **A biconditional between a status and its timestamp breaks the moment a state is
  re-entered** -- the rules file records this for MOD-018's period lock, and
  `acc_policies_published_is_published` had the same shape. It is an implication now: a
  published policy has a publication time, and "a publication time never disappears" is the
  trigger's job.
- A naive timestamp answered 500 rather than 422, which is MOD-011's finding for the third
  time, and the bound on an event's `occurred_at` is forward-only: an offline reader
  legitimately reports something from two hours ago, and refusing that would make the offline
  path unusable.

**And the evidence was the largest finding of the three.** The module shipped with seven
behavioural cases for ninety-eight schema rules and no mutation sweep at all -- its
"20/20 mutations caught" was a Python sweep over the decision modules, which is a different
half of the system. An independent reviewer dropped all 73 `acc_` CHECK constraints
individually and watched the suite catch seven; dropped all 25 indexes and keys and watched it
catch none; and replaced five of the ten trigger functions with `BEGIN RETURN NEW; END` while
the suite reported 109/109. Check 110 is the answer for the constraints and the keys -- 115
cases, generated from the catalogue by `tests/sql/generate_access_cases.py` from a row the
committed seed already proved valid, with exactly one column moved so the row violates exactly
the rule under test, **one case per weakening rather than one per constraint**: a two-sided
bound needs a case at each end and a conjunction needs one per conjunct, and the sweep found
seventeen bounds with only one side proven. Check 111 is the answer for the trigger functions:
**one probe per plpgsql branch, forty-four of them**, each asserting the sentence that must
refuse it rather than the exception class, because a `NOT EXISTS` branch is satisfied by a
parent that does not exist and so answers for the branch above it; the probe count is compared
against the `RAISE` count in the catalogue, so a branch added later without a probe fails.
`tests/sql/sweep_access.sh` is the harness, and it judges checks 108-111 alone rather than the
whole file, because check 107's definition pin notices any change to a rule's text and a sweep
that cannot tell a pin from a case reports the vacuity as success.

**And every case now names the constraint that refused it.** `check_violation` is the same
exception for every CHECK on a table, so a case that counts it proves whichever fires first --
the trap this repository has shipped in five modules and found by sweeping afterwards each
time. `GET STACKED DIAGNOSTICS offender = CONSTRAINT_NAME` turns that into a failure on a clean
database: it caught fourteen of these cases being answered by a sibling, and four more in the
hour it was added, two of them in cases written minutes earlier. The remedy per case is the
companion columns the sibling demands -- an attribution trio needs its status, a bound needs
the pairing that lets the column be set at all -- which is not derivable from the predicate
under test and so is written down beside it.

Things worth knowing before extending it:

- **`issue_command_on` takes the connection**, so the unlock command and the decision that
  authorized it commit in one transaction. A pool-taking version would read identically and
  guarantee a door that opened with no record, or a record with no door.
- **The replay cache is the one table in this module with a DELETE grant**, because every row
  in it expires and it is meant to be swept. Everything else is insert-only or
  lifecycle-only, and the decisions table has no UPDATE at all.
- **A decision and an event are different rows on purpose.** What was decided is not what
  happened: a granted decision followed by nobody walking through is an ordinary occurrence,
  and an entry that cites a refusal is a door held open -- an incident rather than an entry,
  which the event trigger refuses outright.
- **One live policy per zone at every statement**, which is what makes "the policy that
  decided this" answerable a year later without reading a history.
- **A health or safety hold is not a column in this build.** MOD-014's health classes are
  unreachable by anybody, so `safety_hold` is a code the evaluator can return and nothing
  here produces -- disclosed rather than faked.

Known gaps, deliberate:

- **Nothing opens a door.** There is no gateway, no relay and no outbound anything: the unlock
  is a MOD-021 command written for whatever collects it, and `settle_command` records what
  that thing reported. A row saying a turnstile opened, written by nothing that drives a
  turnstile, is the fabricated-evidence shape this codebase has been bitten by six times.
- **The replay cache is swept; the rest still waits for a person.** `access.replay_sweep` is
  a worker job at five minutes, and the only job in the registry that runs as
  `veyro_cp_worker` -- `sweep_replay_tokens` needs the DELETE grant that `veyro_cp_app` holds
  nowhere, which is why a job declares the role it needs rather than the process holding the
  union of both. An offline reconciliation still runs when somebody calls it, and an
  unreviewed emergency release sits in its index until a human looks: both are judgements
  rather than sweeps.
- **Occupancy is advisory and a capacity policy cannot be enforced from it.** A count built
  from readers is wrong the moment a door is held, and refusing a member on a number the
  module itself calls approximate is the direction nobody would defend. Enforcing it needs
  anti-tailgating hardware this build has no access to. **That advisory-ness is what
  ADM-RPT-04's report refuses to divide by**, which is the gap being honoured one surface
  over rather than closed: `app/access/attendance.py` names the busiest window and the
  quietest attended hour as shares of the busiest *hour*, never of `acc_policies.capacity`.
  Two independent reasons, either enough: entries in an hour are arrivals rather than people
  inside at a moment -- a hundred arrivals is a floor holding a hundred if everybody stays an
  hour and fifty if everybody stays half of one -- and a concurrency figure summed over four
  weeks at an entry-only turnstile climbs all month. `NO_CAPACITY_PERCENTAGE` rides on every
  response, because a reader who took a share for a capacity would be making a staffing
  decision on the wrong number.
- **An hourly histogram counts presentations, not people, and `visits_on` has the same
  shape.** `GET /reports/attendance` sums every zone of a club unless narrowed, so a member
  who passes the front door and then a studio reader is two entries. Disclosed on both reads
  rather than changed: "visits" counted per zone is what the event ledger holds, and picking
  one zone per club would be a read deciding which door is the door. Narrowing to one zone is
  the figure a manager wants for a building's own arrivals, and the surface offers it.
- **Nothing in this build records when a club is open.** So the hourly read returns all
  twenty-four hours and the quietest hour is the quietest one that *saw anybody* -- taken over
  all twenty-four it is four in the morning in every club in the world. Its share of the peak
  rides beside it, which is what makes a stray 04:00 entry read as what it is rather than as
  a gap worth filling. MOD-019's `sch_availability_windows` is a *resource* rota rather than a
  site's opening hours, so deriving one from the other would be inventing product.
- **No anti-tailgating, no video, no visitor management and no mobile credential.** A reader
  presents a digest; the NFC, BLE and wallet-credential halves are a client-side problem and
  the vault one.
- **An offline decision is judged, not prevented.** The snapshot ceiling bounds how long a
  reader may decide alone and `offline.py` says afterwards whether what it decided stands;
  nothing stops a device that has lost its link from granting inside its window, which is the
  point of the window.
- **Eleven free-text columns are residue an erasure cannot reach**, all declared by hand
  because the reachability sweep matches column names.
- **The timeline does not know about any of this.** MOD-014 projects nine event types and none
  of MOD-022's six is among them, so a member's timeline shows no door they walked through.

**MOD-026 (AUT-02 tasks, cases, approvals and SLA) -- implemented: R01 to R07, screens
included.** Ten `tsk_` tables in
`plt01` under the same forced RLS, five trigger functions, and `app/tasks/` beside them: a
business calendar, work queues, tasks with their checklists and dependencies, cases with an
insert-only timeline, an owner, a deferral and the records an exception is about, SLA clocks
with their pauses, with a service and twenty-five routes through `permit` -- and three screens,
`/tasks`, `/tasks/cases/{case_id}` and `/tasks/resolved`, which are the first in this app with
a full set of working write forms. Design record:
`knowledge/00-Decisions/ADR-0009-mod026-tasks-cases-approvals-sla.md`.

**Slice 1 landed in two parts and the second was prompted by this file's own standard.** 1a
was the schema and the pure decisions, and the ADR says a slice lands whole *including* the
service and the routes -- so 1a was a schema with no reader, this build's most-repeated
finding, written down rather than quietly redefined. 1b is the service, the routes, the eight
permissions and the masking.

**Writing the service found two defects in 1a**, which is the argument for not stopping at a
schema. `0019` gave tasks and cases **no idempotency key**, so a timed-out retry would have
created a second task -- every other module's create takes one, and MOD-017's review found
exactly that in three commands at once. And the cycle check used `SELECT ... FOR UPDATE` on
`tsk_dependencies`, which has no UPDATE grant: **that needs the UPDATE privilege and fails
with `permission denied` at runtime**, which the rules file records and I wrote anyway. An
advisory lock needs no table privilege, which is MOD-009's precedent, and the lock is wanted
rather than incidental -- two concurrent inserts can each be acyclic alone and form a loop
together. Proven: isolation check 112, mutation-tested with 5 mutations, all
caught; 19 domain unit tests with no database; 9 domain mutations, all caught.

**INV-AUT-02 is in the database now, and putting it there found three things.** The invariant
is "approvers cannot approve their own restricted actions unless explicit emergency policy
applies", and it lived in `app/authorization/approval.py` and nowhere else --
`iam.approval_decisions` carried one CHECK, on the decision domain. `product/0004_approval_
integrity.sql` adds the trigger, and it is **conditional**, because `approval.py` reads
`if policy.separation_of_duties and decided_by == requested_by`: a policy may legitimately
permit self-approval, which is the invariant's own "unless" clause, and a trigger refusing it
outright would be MOD-020's waitlist shape. It reads the request's **snapshot**, never the
policy, because re-deriving is the defect the snapshot exists to prevent. Isolation check 113,
with the trigger's two live branches probed by their sentence and the third deliberately left
to the foreign key. **Proven: 9 mutations, 8 caught by check 113 and one by check 30** --
which is reported that way rather than as nine, because a mutation caught by a sibling proves
the sibling. That ninth makes the trigger raise for a request it cannot find instead of
returning, and the cross-tenant case in check 30 is what sees it first; check 30 names the
confusion now rather than dying with the trigger's message, which is this build's own remedy
for a red suite with a misleading cause. The sweep also found a defect in check 113 itself:
the branch proving a **permission** was a bare INSERT, so when the trigger was wrong the block
aborted with the trigger's message and the harness reported MUTERR for a mutation the branch
had correctly caught. **A probe that proves a permission needs a handler exactly as much as
one that proves a refusal.**

- **The snapshot was rewritable, which made it not a snapshot.** MOD-008's review stopped the
  terms being re-derived at decision time; the grant was table-wide `UPDATE`, so
  `separation_of_duties` and `requested_by` were writable and the same attack worked one step
  over. The service writes `state` and `decided_at`, in one statement, and the grant says so
  now. **The wider finding is named rather than fixed here: the whole `iam` plane is
  table-wide -- fifteen tables, zero column-scoped grants** -- while every `plt01` module
  since MOD-005 is column-scoped. The approval path is MOD-026's because the invariant is;
  the other thirteen are MOD-008's.
- **The new trigger refused the isolation suite's own seed.** `isolation.sql` had one identity
  per tenant from MOD-008 onwards, so its approval was requested and decided by the same
  person with separation of duties on -- a row the service refuses and the invariant forbids,
  sitting in the evidence for as long as the table has existed. The seed has a second identity
  now, which is what the browser fixture needed for MOD-022's two-party publication.
- **And it invalidated a case, which is this build's own rule met by its author.** CHECK 32's
  "one decision per approver per request" inserted a second decision by the *requester*, so
  the trigger fired before the unique index and that case began proving the trigger, leaving
  the index droppable in silence.

**`SELECT ... FOR UPDATE` works under a column-scoped grant**, measured rather than reasoned
about -- `has_table_privilege(..., 'UPDATE')` reads false afterwards, so deriving the answer
from it would have been wrong, and the trigger's lock depends on it.

**And delegation is built, which is AUT-02-R05's remaining word.** MOD-008 had a
`delegated_from` column and deleted it because "no code set and no evaluator read" it -- a
column implying a model that did not exist -- so the model is built or the word is not
claimed. `product/0005_approval_delegation.sql` is one table, one column on
`approval_decisions`, and three refusals; the service derives the delegator from the session,
evaluates the policy against the **delegator's** permissions (which is what being delegated
to means), and the three routes sit on `authz.approval.decide` and `authz.role.read`.

**The reason it needed designing before coding is that a delegation can defeat the invariant
MOD-026 claims.** If Alice raises a request and delegates to Bob, Bob deciding it is Alice
approving her own request through a proxy: separation of duties intact in the column and gone
in fact. So `check_decider` takes `acting_for` and the trigger compares both identities.
That is MOD-007's "a remedy is new capability, so review it as such", applied before the code
rather than after -- it was learned when a recovery allowance added to close one finding
became a backdoor minting ten codes with no password.

Three more decisions, each stated rather than discovered: a delegation is **not transitive**,
because a chain makes "on whose authority" unevaluable without walking it; it has **both ends
and a ninety-day ceiling**, because an open-ended one is a permanent transfer of approval
authority, which is a role assignment and already has a table; and **only the delegator
revokes it**, because an administrator who could would be deciding who may approve while
somebody is away, which is the same power.

Proven: isolation check 113 now runs thirteen probes -- the trigger branches by their
sentence, two **weakenings** the branch probes cannot see (a revoked delegation and an expired
one, which an absent-delegation probe would pass), and four constraint cases naming the
constraint that refused them. 11 mutations, 10 caught by check 113 and one by check 28's
prefix-free `iam` sweep. 14 service and HTTP tests.

**AUT-02-R06 is built: the arithmetic (3a) and the clocks it measures (3b).** INV-AUT-02's other half is "SLA calculation is time-zone and
business-calendar aware", and that sentence is this module. Nothing is stored: a clock is its
target, the calendar and its pauses, and the remaining time is a function of those and
`now()` -- MOD-018's no-stored-balance for the fifth time. 25 unit tests with no database and
11 mutations, all caught.

**Every span is measured in the location's own zone and the answer is real elapsed time**,
which is what makes a clock-change day come out right with no special case: a local
`00:00-23:00` window is 22 real hours on Britain's spring-forward Sunday, 24 on the autumn
one and 23 on an ordinary one, because those are the instants a member actually waited.
MOD-019 paid for the inverse -- a rota read in the session's zone rather than the resource's
made a London coach available at six in the morning.

Three decisions carry it. **A dated row replaces the weekly pattern for its date rather than
adding to it**, because otherwise a half-day before a holiday is unexpressible: you could
lengthen a day and never shorten one. **A pause is subtracted where it overlaps open time**,
not whole, because a clock paused overnight was not running anyway and subtracting it twice
is how a target silently doubles. And **an empty calendar raises rather than answering
zero** -- MOD-019's "no rota is not never available", in the direction that matters here,
because a clock that never advances is a breach that never fires.

**3b is two tables, two triggers, a service and five routes.** `tsk_sla_clocks` holds what
the target is, when it started and which calendar it is measured against; `tsk_sla_pauses`
holds every span it was stopped for, each with an actor and a stated reason -- because "why
did this clock stop" is asked precisely when a target was missed. Four decisions:

- **The location is derived from the subject's queue and snapshotted on the clock.** A caller
  able to name one could measure a promise against a calendar the work is not done in, which
  is MOD-017's `brand_id` finding; re-reading the queue later would change what a member was
  promised after the fact, which is MOD-019's "a session snapshots everything that describes
  it" applied to a promise.
- **A club with no stated business hours falls back to elapsed wall-clock time and the read
  says so.** MOD-019's "no rota is not never available", in the direction that matters here:
  a business-hours clock against an empty calendar never advances, which is a breach that
  never fires.
- **An escalation to a retired queue is refused by a trigger** -- an alarm wired to a bell
  nobody answers, which is MOD-021's "a lookup that proves something exists does not
  authorise what you do next".
- **A target is judged once and the judgement does not move**, by trigger, because
  re-measuring a promise after the fact is how a missed one becomes a met one. The remedy
  exists by construction rather than as a gap: the running-clock index is partial, so a new
  target can be started on the same subject once the old is settled -- the recurrence pattern
  this module already uses for a case.

**`tasks.sla.read` and `tasks.sla.write` are their own pair**, because setting a target is a
different act from doing the work: a queue manager who decides what a club promises is not
necessarily the person answering the task, and folding it into `tasks.task.write` would be
MOD-013's `GET /notifications/channels` finding one module over.

**And the no-countdown claim is swept for now, because `0021`'s header claimed it before it
was true.** Check 112 bans a dozen stored-countdown column names under `tsk_` -- plus `due_at`
on the clock tables only, where it is a derivation rather than the ordinary caller-stated
field it is on a task. Proven by adding `seconds_remaining` and `breached` and watching it
fail. That is the "a doc claiming a control it does not have" shape, caught by writing the
control.

**3c is the tenth worker job, and it is what makes a target mean anything.**
`sla.state`'s own docstring already said a breach is computed and that an escalation needs
the worker to evaluate it -- so until `tasks.evaluate_slas` existed, a missed promise stayed
`running` for ever and `escalate_to_queue_id` was a column implying a control nobody
implemented, which is this build's most-repeated finding in the module whose subject is work
nobody is doing. Five minutes, because an SLA is stated in hours and the finest grain anyone
writes is minutes. Four decisions carry it:

- **Idempotent by construction, so the schedule stays disposable.** The settlement trigger
  admits one judgement per clock and the escalation task carries a key derived from it, so a
  second pass settles nothing and raises nothing. No table records what has run.
- **It takes no caller-supplied instant**, which is MOD-020's settlement rule: a time a
  caller chooses decides who is recorded as having failed. The service tests age a clock by
  inserting the row that waiting would have left.
- **An escalation raises a task rather than claiming anybody was told.** MOD-013 sends
  nothing, so a job recording "notified" would be the fabricated-evidence shape. And **the
  task does not cite the case**: `tsk_task_matches_its_case` refuses a task filed under a
  different queue from its case, "so the same work would not be counted in two backlogs", and
  an escalation is by definition filed somewhere else -- so the link is the clock through
  `evidence_ref` and what travels is the subject.
- **Each clock is judged in its own savepoint and a failed escalation leaves it running.** A
  breach settled with nobody told is a missed promise that reads as handled.

**And it went red on `main` for one line nothing local could reach.** The operations board's
browser spec asserts the number of scheduled-job rows as a literal, and its own comment says
that is a tripwire on purpose -- "wiring a job should bring somebody to this file". The whole
backend suite ran twice on a freshly rebuilt database and every non-Docker CI step passed,
because the backend's own assertion derives from `len(registry.JOBS)` and that spec holds the
only hard-coded count of it in the repository. The tripwire worked and its author did not come;
the answer is to visit the file, not to soften the check.

**And one of the four decisions was wrong when first written, which the second test found.**
The sweep returned early for any clock with an open pause -- "a stopped clock is not spending
its target", which is true and is already what `_consumed` does, since it subtracts the
pause. What the guard added was an escape: a clock whose target had *already* gone could be
kept out of the sweep for ever by pausing it afterwards, and pausing does not un-break a
promise that is already broken. Two rules for one question, and the one written as a guard
was the wrong one. Deleted, with a test on each side of the distinction.

**And `create_task` never resolved its `case_id`.** This application has no handler for a
psycopg error at all -- only `RequestValidationError` and `ServiceError` -- so an unknown
case answered 500 whether the composite key or the trigger spoke, which is MOD-009's "an id
shape-checked and never resolved" in a route whose two sibling lookups were already there.

**Writing the second reader found that the first one contradicted itself.** `read_clock`
returned `consumed_seconds` and `remaining_seconds` computed from the business calendar
*minus the pauses*, and a `state` computed by comparing `now` against a due instant walked
forward from the start -- and `due_at` knows nothing about `tsk_sla_pauses`. So a clock
stopped for a week read `breached` beside a `remaining_seconds` well above zero, which makes
a pause decorative on the one field anybody acts on; and the warning threshold was
`(now - started) / (due - started)`, wall-clock over wall-clock, in the module whose entire
subject is that those are not the same thing -- a target opened at five on Friday is 80% of
the way to a Monday deadline by Sunday evening with no business second spent. **Both were
invisible while the only reader was the read itself**, whose test asserted `state` was one
of three strings. `sla.state` now takes the consumed seconds and the target, so the verdict
and the remaining time are the same two numbers; `due_at` is projected from *now* on what is
left, and is absent entirely for a paused clock, because when it resumes is nobody's to
guess. `service._consumed` is the one definition both callers read.

**And a guard that admitted a state nothing could leave.** `tsk_sla_escalation_is_live` is
`BEFORE INSERT OR UPDATE` and re-judged the route on every write, so retiring a queue refused
every later update to every clock pointing at it -- the settlement included, which is the one
write that makes the record true. A target whose escalation team was merged into another
could never be judged. The control is "a clock may not be pointed at a dead bell"; what it
did was "a clock pointed at a dead bell is frozen". `0022` re-checks only on an insert or
when the pointer moves -- **the clause was already in this module's own sibling trigger**,
three files earlier.

**And the branches had no probes at all.** CHECK 112 pins this module's grants, NOT NULLs and
foreign keys, and a plpgsql branch is invisible to every one of them -- MOD-018 paid for that
when a reviewer deleted a trigger branch and the suite reported 84/84. CHECK 114 is one probe
per branch, asserting the *sentence* and running as the **table owner**: `target_seconds` and
`started_at` are outside every runtime role's UPDATE grant, so under `veyro_cp_app` the
branch refusing a re-measured promise is answered by the privilege layer and proves the
grant. It carries one probe for a *permission* too, which is the only thing that can see a
guard refusing too much. Two of the eleven refusals turned out to have no case available at
all -- every row reaching them is already refused by a sibling CHECK or by the composite
foreign key -- so `0023` deletes those, which is MOD-016's judgement for a constraint
subsumed by a sibling.

**And four of the sweep's own mutations were ill-formed in a way worth naming**: `IF false
AND a OR b` is `(false AND a) OR b`, because `AND` binds tighter, so a prefix mutation on a
multi-line disjunction disables one term and leaves the branch firing. All four came back
UNCAUGHT and all four were the harness's fault -- the third distinct form of
"a mutation that changes nothing is not evidence" this module has paid for. **And the sweep
left the database mutated when it finished**, because `verify_db.sh` applies `MUTATE` after
the build and nothing puts it back: a full backend suite then reported 2,648 tests OK
against a trigger branch the sweep had disabled, with a green suite, passing checks and a
clean diff, because the stale artefact was in the database rather than in the tree.

**A mutation came back uncaught and the guard it removed turned out to be subsumed by
accident.** A `kind == "open"` filter was redundant because a closed window has no hours --
except that `Window` did not actually forbid one carrying hours, though the schema does. So a
`Window` the database cannot hold was constructible, which is this build's "fixture encoding
a state the system cannot produce" shape appearing in a *production* type. The invariant now
mirrors the schema and the redundant filter is deleted, which is the judgement MOD-016's
redundant kind domain already set.

**The sweep found three uncaught and two of my own mutations malformed**, which is the
harness rule paid again: the three were the delegation table's own CHECKs, which the trigger
probes could not reach -- "a constraint nobody has broken on purpose is a constraint nobody
has tested" -- and the two malformed ones kept a dummy `RAISE` to preserve the branch count
and fired it unconditionally, so the seed died and the sweep reported MUTERR for mutations it
had never really run.

**Slice 4a and 4b are built: the attention-item schema the canvas needs, and the reads and
writes over it.** `0024` adds four things ADM-TSK-01, ADM-CC-06 and ADM-CC-07 draw and the
slice-1 schema could not express, plus one hardening carried over; `app/tasks/attention.py`
decides what an attention item *is*; and eight routes make the sheet, the resolved record and
R07's workload readable. The screens are 4c and are the only part of the slice still owed.

**The ADR's slice 4 was amended before any of it was written, which is the part worth
keeping.** That line said "the workload read the three screens draw", and reading the canvases
found it understated by four schema facts -- so the amendment went in first and the migration
followed it. Each item is a thing a drawing requires:

- **A source**, closed over ADM-TSK-01's own three: "assigned by a person, generated by an
  automation, or suggested by Veyro. The source is always named -- a task nobody can account
  for gets ignored." That second sentence is why the column is NOT NULL, why the body field
  has no default, and why `ALTER COLUMN source DROP DEFAULT` follows the backfill: leaving the
  default would name it for the first caller who forgot, which is the state it exists to
  prevent. It is in no UPDATE grant, because where work came from does not change.
- **An owner on a case.** ADM-CC-06's states are unassigned, assigned to me, assigned to
  someone else and resolved; a task has carried an assignee since slice 1 and a case carried
  none, so four of five were unrepresentable on the record the sheet is about. One route sets
  the column and **which act it was is derived** from what the column held, so a caller cannot
  report a release and perform a handover -- and the handover's history is a timeline entry,
  because "who has it" and "who gave it to them" are two facts and one column cannot hold
  both.
- **A snooze, as five columns and deliberately not a status.** "Snoozing requires a reason and
  a return date -- an exception cannot be dismissed, only deferred with an account of why." A
  fourth status would need `tsk_case_resolution_is_final`'s forward-only rank to admit a
  reversal, which is MOD-020's waitlist edge; a case is *snoozed* when `status = 'open' AND
  snoozed_until > now()`, derived, which is this module's no-stored-countdown discipline. The
  remedy came with it: deferring is routine, so a return date typed as next year would hide an
  exception for eleven months, and `return_case_to_queue` is the withdrawal that answers it --
  MOD-013's rule from the other side, for the third time in this build.
- **Affected records, plural.** "6 payments failed overnight ... THE SIX RECORDS · EACH LINKS
  TO ITS MEMBER". A case has one subject, which is right for the ordinary case and cannot
  express an exception that is *about* six members. The subject is in the primary key, so the
  count a batch action is sized by cannot be inflated by adding the same member twice; a
  record comes off by withdrawal rather than deletion, because "was this member ever on this
  exception" is asked exactly when somebody was contacted by mistake.
- **And `tsk_sla_clocks.started_at` was unbounded**, carried over from `0021`. Nothing
  reachable moves it -- the service writes `now()`, the grant excludes it, the trigger freezes
  it -- and MOD-011's unbounded `observed_at` is the precedent for closing it anyway, anchored
  to `created_at` because a row-local bound needs no re-validation argument at all.

**Reopen needed nothing, which is the pleasant half.** ADM-CC-06 offers it and ADM-CC-07
settles what it means: "there is no un-resolve -- reopening happens on the item itself and
appears here as a new row, so this list is a record rather than a state." That is
`recurs_from_case_id`, decided in slice 1 for a different reason and agreeing with the
drawing. `test_the_resolved_record_is_read_only_and_there_is_no_un_resolve_route` asserts the
absence, which is MOD-018's journal-listing shape.

**And the erasure registry refused the obvious declaration, for a reason only the constraint
knew.** The three new subject columns on a case looked like `anonymize`, and the executor's
clear table would have cleared `assignee_person_id`, `snoozed_by` and `snooze_reason` --
which `tsk_cases_snooze_attributed` refuses, because the five snooze columns are all-or-none.
Clearing all five would have been worse than the refusal: it **un-defers the case**, moving it
back into a queue somebody has to work, so an erasure would have changed what a tenant has to
do today. The assignee clears and the two snooze columns are declared `write_once` residue
with that reason on the row. The disclosure moves to **19 of 438** -- and to **19 of 439**
with slice 5's staged-approval author, which the registry's own sweep refused to let through
undeclared, for the second time in two slices.

**R07's bottleneck names the blockers rather than counting blocked work**, which is MOD-005's
"a rule id is not a reason" one level up: a count of blocked tasks is what a reader cannot act
on, and the task that blocks the most other work is where somebody should look. Its
compliance share is `None` rather than zero where nothing has been judged, which is MOD-011's
rule -- a window with no measurement is not a window in which nothing was kept.

**`assign_task` takes no actor and `assign_case` does**, which is an asymmetry this slice
found rather than created: a task has no timeline to write a handover to, so re-pointing one
is unattributed. The canvas's handover requirement is on the case, so the case is where the
attribution went; the task half is named in the gaps rather than left to be discovered.

Proven: 114/114 isolation checks with `0024` applied, its three pins each refusing the
migration until extended and fourteen constraint cases naming the constraint that refused
them; 15 domain tests and 11 mutations over `attention.py`, all caught; 24 service tests and
8 HTTP tests, the last being the layer MOD-014's review showed matters -- the gate return, the
mask decision and the derived viewer are exercised by nothing else.

**Slice 4c is the three screens, and they are the first in this app with a full set of
working write forms.** Every MOD-026 permission is `data_access` or `configuration` with no
financial class -- "raising, assigning and settling a task is the ordinary work of a shift" --
so ADM-TSK-01's bulk completion, ADM-CC-06's assign, release, take over, snooze, return and
resolve all have forms, where every other write in this app is a stepped-up financial
permission and "a button that answered 403 is worse than its absence". The screens are argued
one by one in `contracts/ui/design-compliance.md`; what is worth carrying here is what
building them found.

**Three defects, all one shape: a figure with two definitions on one screen.** MOD-018's "one
module, two definitions of the same balance" usually spans two functions; this produced it
three times in one page, and **none of the three was visible to any assertion** -- two were
found by rendering the page and reading it, the third by looking at a column:

- **The chips counted work in hand and the table listed every status**, so the board read
  `Team · 7` over eight rows with one already done. `list_tasks` grew `in_hand`, the same
  restriction the chip uses, rather than the client filtering what it was given -- which is
  the members list's own finding, where summing the page was honest and still the wrong number
  in the place a manager reads the business.
- **Lateness was an instant on the server and a calendar day in the client.** The overdue
  filter is `due_at < now()`; `dueState` bucketed by date on both sides, so a task due at nine
  this morning read "due today" at five in the afternoon beside an Overdue chip that counted
  it. The corrected rule needed a second message as well: zero whole days late is "overdue"
  with no count, because "overdue 0 days" is not a sentence and English's plural rules pick
  `other` for 0.
- **A hand-written type called the queue's name field `name` and the route sends
  `display_name`**, so every queue rendered as the fallback word "Queue". That is
  `AccessDecision.masked` again -- a hand-written type over an untyped JSON response is
  invisible to every typecheck -- and the tell is a fallback appearing on *every* row.

**Two routes gained a derived flag, because two of the canvas's controls cannot be expressed in
a client at all.** A session carries an `identity_id` and the link to a person is MOD-014's
through `ppl_identity_links`, so a browser has no person id for its own reader: ADM-TSK-01's
`Mine` chip and ADM-CC-06's "Assign to me" are both unwritable client-side. `GET /tasks` takes
`mine=true` and `POST /tasks/cases/{id}/assign` takes `to_self`, both resolved through
`actor_person_id` -- the derivation `/tasks/workload` already made for the count the chip
shows. Accepting a person id for either would let a reader ask the question as somebody else,
which is MOD-020's four caller-supplied person ids in one route; and `to_self` beside a named
person is refused, because a request carrying both is a caller that does not know which it
meant. **An unlinked identity gets an empty answer rather than everybody's work**, and
`mine_is_zero_without_a_person_record` is how the screen says why: staff hold permissions and
do not have to be anybody in particular. Proven: 5 HTTP tests and 5 mutations, all caught.

**And the fixture seeds a reader who is somebody**, because both of those states need one and
the owner is nobody in this tenant. A duty manager is seeded, linked and granted only the
MOD-026 reads and writes; the owner then reads the same item as *somebody else's*, which is the
one state ADM-CC-06 is most specific about. Both halves have a browser fixture rather than only
a component test, which is this build's "a surface branch no fixture can reach" trap, paid for
four times.

**Slice 5 is R05's last word, "sequential, parallel", and a stage is a permission rather
than a position.** `required_approvals` was a quorum of one authority, so "a club manager and
then finance" was unexpressible -- and the two facts the requirement carries are exactly that
an approval can need more than one *kind* of approver, and that sequential means the second
kind cannot decide before the first has. `product/0006` adds a policy's stages, the request's
own snapshot of them, a `sequential` flag on each, and a `stage_ordinal` on every decision.
Proven: isolation check 113 now runs 26 probes -- every trigger branch by its sentence, two
*permissions* no refusal probe can see, and nine constraint cases naming the constraint that
refused them; 12 mutations in `tests/sql/sweep_approval_stages.py`, all caught; 17 domain
tests with no database; 18 service tests.

Four decisions carry it, and one of them is a deletion:

- **A stage is "N holders of permission P", keyed by the permission**, which is what makes the
  combination rule survive. `policy_for` combines every applicable policy and never chooses
  between them, because a single column naming one permission had to pick by row order when
  two applied at the same strictness. A stage *list* has that problem one level up:
  concatenating two policies' stages is order-dependent, the exact dependence combining was
  built to remove. Keyed by permission it is not -- the count is the most any policy asks for,
  the ordinal is the highest any gives it, and the result is renumbered 1..N so `sequential`'s
  "every earlier stage" cannot depend on how somebody numbered a row.
- **The combined order is a topological sort of every policy's own order, and a cycle is
  refused when the policy is written.** Taking the highest ordinal each permission was given
  was the first version and it is arbitrary on a case no pairwise check sees: three policies
  ordering A before B, B before C and C before A each agree with the others on their one
  shared permission, and the maxima then come out equal so the result falls back to the
  alphabet -- a policy's stated order silently violated, which is the row-order dependence
  `policy_for` exists to remove wearing a different hat. `order_conflict` is the cycle check
  and it runs at the policy write, which is MOD-012's succession rule: catching it at the
  moment somebody needs an approval is catching it too late for the person waiting to do
  anything about. **Found by working the cycle through on paper**, which is worth noting
  because the pairwise version passed every test that existed at the time.
- **`UNIQUE (tenant_id, request_id, decided_by)` is untouched and is what makes a stage mean
  something.** One person, one decision per request across every stage: a two-stage approval
  decided twice by one person is one approval wearing two hats, which is the thing stages
  exist to prevent. The constraint that already stopped a quorum being one person pressing the
  button twice turns out to be the constraint a stage needs, unchanged.
- **The trigger takes no lock, and that is a correction rather than an omission.** The first
  version took `FOR UPDATE` on the request by analogy with MOD-019's `FOR SHARE` finding; the
  mutation sweep reported its removal as uncaught, and checking each reader is why it is gone.
  `sequential` is outside every runtime role's UPDATE grant so it cannot move, and the earlier
  stages' approvals come from an insert-only table -- so two concurrent decisions at READ
  COMMITTED are each fail-*closed* with respect to the other. The lock would only have made
  the guard more permissive under concurrency, which is the wrong direction for a guard.

**And a staged policy could name an authority no stage charges, which is a hole the new rule
opened.** With stages the permission requirement is the stage's -- charging the policy's own to
every decider is the defect two paragraphs down -- so a `required_permission` outside the stage
list is simply never checked by anything. `write_approval_policy` refuses it now, which is a
declared value nothing reads caught before it is written rather than found later as a policy
that admits anybody; and the refusal immediately caught two of this slice's own test fixtures,
which is the usual sign it was worth having.

**And three defects came out of writing the tests, each a shape this file records.** `stages`
on the wire meant "this combination has a stage list", which `combine_stages` produces for a
plain policy too -- so an unstaged request reported one stage while its snapshot carried none,
two answers to "is this staged". It means "somebody declared stages" now, and the first
attempt at that collapsed a one-stage combination to nothing, which **silently lost a count**:
a policy whose single stage asks for two approvers has `required_approvals = 1` on its own
row. `check_decider` charged the *union* of every applicable policy's permission to every
decider, so each approver needed every stage's authority -- which is to say one person could
satisfy all of them, the exact opposite of what a stage is for. And `_decide_in_tx` built its
effective policy without the snapshot's stages, so that path saw a staged request as unstaged
and refused a finance approver the finance stage. All three were found by tests rather than by
reading, and the third by the one test that needs a decider holding exactly one stage's
authority.

**The decision that shaped the module is that there is one approval engine and it is
MOD-008's.** `iam.approval_policies` already carries `action`, `threshold_minor`,
`required_permission`, `required_approvals` and `separation_of_duties`, and its requests
snapshot those terms and carry `expires_at` -- so of AUT-02-R05's five named behaviours,
**quorum, amount-based and expiry are already built and tested**. A second engine in `plt01`
would be two tables able to disagree about whether a refund was approved, which is this
build's "one module, two definitions" at its worst. So MOD-026 extends `iam` in slice 2 and
spans two planes as MOD-012 does, and what it adds is stages (R05's "sequential, parallel"),
delegation, and the action-class catalogue.

**Checking that claim found two things the ADR's first draft had wrong**, and both are worth
carrying:

- **R04 names seven action classes and six are permissions.** Refunds, discounts, price
  overrides, data export, access exceptions and deletion all exist in
  `app/authorization/catalog.py`; **payroll does not, because there is no payroll module in
  this build**, so a policy naming it would be a policy for an action nothing can perform --
  MOD-020's "declared value nothing writes" before the value is declared.
- **INV-AUT-02's separation of duties is enforced in Python only.** The draft said a CHECK
  forbids approving one's own request; `iam.approval_decisions` carries exactly one CHECK, on
  the decision domain, plus a unique index stopping one person pressing the button twice. The
  rule lives in the service, which is correct and is the *service* -- and this build's premise
  is that the schema is the half that holds when the service is wrong. It cannot be a CHECK,
  because `requested_by` is on the parent row; it is a trigger, which is `sec_legal_holds`'
  precedent. **Writing it is slice 2's first job**, because a module cannot claim an invariant
  whose only enforcement is a layer it does not own.

Four decisions carry the slice:

- **A task's subject is a closed nine-name vocabulary with an id and no foreign key.** R01
  names member, lead, tenant, invoice, incident, device, booking, asset and workflow; a lead
  is MOD-027's, a workflow MOD-055's, and nothing here owns an asset. Free text would make
  R07's "how many tasks are about invoices" a group-by over typos, which is MOD-010's
  restricted-field argument pointed at a discriminator; nine nullable key columns with eight
  NULL per row is MOD-021's supersession shape, and under MATCH SIMPLE a NULL in a composite
  key skips the check entirely. So `subjects.py` declares the five that resolve, the three
  that are claims with the module that would fix each, and `tenant` -- which resolves against
  nothing and is **not** a gap, because a task about the tenant is about the row's own
  `tenant_id`, which RLS already bounds.
- **Business hours are this module's own table, and that is the one new fact the build
  needed.** INV-AUT-02 wants SLA arithmetic "time-zone and business-calendar aware", and
  nothing here records when a club is open -- MOD-022's attendance report says so and refuses
  to derive it, because MOD-019's rota is a *resource's* rather than a site's. The weekly and
  dated split is MOD-019's, reused rather than re-chosen. **A location with no rows has no
  business hours, which is not the same as being closed all week**: MOD-019's first version
  read an empty rota as "never available" and nothing could be scheduled in a tenant at all,
  so here the consequence is an SLA on wall-clock time and slice 3's response will say so.
- **No countdown is stored anywhere.** An SLA clock is its target, its pauses and this
  calendar, evaluated at read time -- MOD-018's no-stored-balance, MOD-019's no-`held_count`
  and MOD-016's derived `in_window` for the fourth time. The consequence is stated rather than
  discovered: a breach is computed, so nothing fires when it happens. `tasks.evaluate_slas`
  is that job now -- and the announcement window this bullet predicted it would need turned
  out not to exist: the settlement is one-way by trigger, so the clock itself is the dedupe
  and the escalation task's key is derived from it. A prediction about a mechanism is a claim
  like any other, and this one was a borrowed answer to MOD-011's problem rather than this
  module's.
- **A case moves forward only, and `recurs_from_case_id` is why it does not have to reopen.**
  The first draft of the migration let a resolved case return to `open` and claimed in a
  comment that its first resolution's attribution stayed put -- which the attribution CHECK
  makes false, since an `open` case must carry no resolution, so reopening would erase exactly
  what the trigger was written to protect. **Two encodings of one rule that disagree is
  MOD-020's waitlist edge**, caught here by reading the file rather than by a reviewer. A
  recurrence is a new case citing the old, which is this build's answer everywhere else.

Things worth knowing before extending it:

- **The Python status tables are compared against the migration's own CHECK text**, by a test
  that reads the `.sql` file. MOD-020 shipped a state machine that admitted an edge its
  trigger refused and "both encodings agreed with each other and neither agreed with the
  service"; from the moment one member failed to answer an offer nobody was promoted again
  while places sat free. A regex over the migration is what makes that drift fail in CI.
- **A cancelled dependency stops blocking.** Treating called-off work as a blocker leaves
  every downstream task stuck with no way to clear it, which is MOD-016's bundle-fulfilment
  finding -- a transient failure made an obligation permanently unsatisfiable.
- **`blocking` names the blockers rather than counting them**, because a count is what a
  reader cannot act on: MOD-005's "a rule id is not a reason".
- **The cycle walk is iterative and the schema only sees self-reference.** A longer cycle
  spans rows, so the service is the half that holds, and the walk is iterative because
  `edges` is caller-supplied -- a recursive version answers 500 on input somebody can send,
  which is MOD-019's `str.isdigit` finding in another shape.
- **A blocked task is unblocked before it is finished.** Finishing one leaves a dependency
  that was never satisfied or removed, so R07 cannot say whether the blocker mattered.
  Cancelling a blocked task is allowed, because calling off blocked work is ordinary.
- **Twenty-six privacy declarations, fifteen of which the registry demanded.** The rest are
  the free-text columns the name-matching sweep will never find -- a task title is the
  likeliest place in this module for a member's name, because "call Hala about her card" is
  how one gets written.
- **A 422 here never names the field, and a test of mine asserted it did.** This application
  replaced FastAPI's validation handler because the default echoed the offending input into
  its own 422 and `json.dumps` then refused a `NaN` the parser had accepted -- a 500 from
  inside a 422 on every route. So a `Literal` on a body buys a refusal at the boundary rather
  than a 500 from a CHECK, and the answer is `{"error": "invalid_request"}` and nothing more.
  Worth knowing before writing a route comment that promises otherwise, which two of mine did.
- **The masking is decided by the gate, in the route.** A service test passing
  `may_read_reasons=False` proves the service and not that the route computes it, which is
  MOD-014's finding -- no test had ever called a `/people` route successfully, so the gate
  return and the permission resolution were exercised by nothing and four defects passed a
  green suite.

Known gaps, deliberate:

- **ADM-CC-06 is "the side sheet every Command Center row opens into", and no Command Center
  row opens into it.** The screen is built -- see "The web app" -- and it is a page, reached
  from the task list and from the resolved board. What it is not reached from is the queue the
  canvas draws it over: that queue is derived from live state in MOD-017's collections,
  MOD-019's staffing and MOD-022's doors rather than from `tsk_cases`, so there is no
  originating row for the canvas's Esc to return focus to. A case is the durable record an
  exception *would* be resolved through and nothing routes to it from there. A gap in the
  wiring rather than in either half, and closing it means deciding which of those computed
  items becomes a case -- a product decision about what an exception *is*.
- **No Reopen on a resolved item, and the obstacle is the case number.** The canvas offers it
  and ADM-CC-07 settles what it means: "reopening happens on the item itself and appears here
  as a new row". That is `recurs_from_case_id`, which exists -- but `case_number` is
  caller-supplied, the tenant's own human-facing reference like `membership_number`, and
  nothing in this build mints one. A form asking a reader to type a case number would be
  asking them to do the product's job, and a client inventing a scheme would be MOD-017's "two
  human-facing member numbers, with nothing relating them" again. What is owed is a decision
  about how a recurrence is numbered.
- **A task's reassignment is unattributed.** `assign_task` writes `assignee_person_id` and
  records nobody, because a task has no timeline to write a handover to -- while
  `assign_case` writes an `assignment` entry naming both ends. The canvas puts the handover
  requirement on the case, which is where the attribution went; closing the task half needs
  either columns or a per-task timeline, and a count of "who has what" is answerable today
  while "who gave it to them" is not.
- **Nothing publishes an event.** AUT-02 names none in the catalogue this build carries, and
  inventing one would be inventing product -- but a task raised and settled is exactly the
  kind of thing MOD-014's timeline projects, and it projects none of them.
- **Payroll approvals are the one requirement fragment with nothing to point at**, which is
  R04's seventh action class: `action` is a permission-shaped string and there is no payroll
  module in this build, so a policy naming one would be a policy for an action nothing can
  perform -- the "declared value nothing writes" shape, refused rather than stored. The other
  six action classes are in the catalogue. **R05 is complete as of slice 5**: quorum, amount
  thresholds, expiry, delegation and now stages, sequential and parallel.
- **The approval engine has no screen, and that is the design's own shape rather than a gap
  here.** Checked rather than assumed: the Admin inventory carries no approvals queue. What it
  carries is thresholds *inside* other screens -- ADM-POS-03's discount threshold, which is
  what makes POS-06 require a manager -- and "Tasks, cases & approvals" is a domain item whose
  V1 screen is ADM-TSK-01. So this module's surface obligation is the three screens it has, and
  a reader looking for an approvals board is looking for something the design does not draw.
  Whoever builds POS-06 will want a decision control on it, which is that screen's work.
- **Nothing announces a breach *warning*.** `sla.state` returns `warning` past the threshold
  and only a reader sees it; the sweep acts on the breach. Two reasons, and the first is a
  product judgement rather than a wait: a warning task per clock at eighty per cent doubles
  what the escalation queue holds and the breach task behind it says the same thing later, so
  a warning's natural form is a message to whoever is answering -- and MOD-013 authors one
  and sends nothing. The threshold is stored and evaluated, so closing it is a dispatcher and
  a decision about who hears it, not a change here.
- **A case's documents are references, not files.** There is no object store -- the isolation
  rules name one beside regions and keys -- so `document_ref` has to look like a locator,
  which is MOD-012's `vault_ref` rule: a non-blank text column beside a comment promising it
  holds no payload is a naming convention rather than a control, and a reviewer disproved
  exactly that claim once with a card number.
- **A longer dependency cycle is the service's to refuse and there is no service yet**, so
  today nothing stops one. The schema refuses self-reference; `workflow.check_no_cycle` is
  written and tested and has no caller until slice 2 -- which is this build's "a writer with
  no reader" shape, named here rather than discovered later.
- **A queue's `location_id` is a scope, not a boundary.** `permit` resolves tenant-wide, so a
  club manager sees every queue -- MOD-014's standing scope gap, said here rather than implied
  by a column that looks like it restricts something.
- **An escalation will end in a notification request and will not claim anybody was told**,
  because MOD-013 authors a message and sends nothing.

## The worker runtime

`backend/app/worker/` is the thing this file asked for in fifteen places. Every one of those
bullets named a decision function that was written, tested and reachable from a route, waiting
for something to call it without a person asking -- and until now the honest answer was that no
such thing existed. Ten jobs are wired: MOD-010's relay, MOD-011's objective evaluation,
MOD-013's digest close, MOD-014's timeline projection, MOD-017's ended-membership grant
revocation, MOD-021's offline sweep and command expiry, MOD-020's waitlist-offer expiry,
MOD-022's replay-cache sweep and MOD-026's SLA breach sweep. `python -m app.worker --once` runs one tick and prints what it did;
without `--once` it loops until a signal.

Five decisions carry it, and three of them are refusals:

- **A job is an adapter, not a new implementation.** Every entry in `registry.py` calls a
  service function that already exists with arguments it already takes. A worker that
  re-implemented a sweep would be a second copy of the rule, and the day the two disagreed
  nobody could say which was the policy -- which is MOD-012's argument for importing MOD-010's
  backoff rather than copying it.
- **A job declares the role it needs, and the replay sweep is why.** `veyro_cp_worker` differs
  from `veyro_cp_app` in exactly one direction: it holds DELETE on the configuration registry
  and on `plt01.acc_replay_tokens`, and `veyro_cp_app` holds DELETE nowhere. A process holding
  the union of both could delete a tenant's feature flags in order to sweep a replay cache, so
  `Pools` carries the pools and `Job.role` picks one. The negative test is what makes that real
  rather than decorative: `sweep_replay_tokens` under the `veyro_cp_app` pool is refused by the
  privilege layer, and the test asserts the refusal. This is also the first thing in the build
  to use `veyro_cp_worker` as a *client* rather than as a name in a GRANT -- a review found it
  had never been exercised behaviourally at all.
- **Every job is idempotent, so the schedule is disposable, so there is no table.** Due-times
  live in the runner's memory and a restart makes everything due at once. That is safe because
  a second pass is free by construction -- a unique index, an idempotency key, or a predicate
  that no longer matches -- and it is why this change adds no migration, no RLS, no grants, no
  isolation checks and no mutation sweep. What a durable schedule would buy is *not* re-running
  after a restart; what it would cost beyond the work is a second place where "has this run" is
  recorded, which can disagree with the effect the job had. **The day a job appears that is not
  idempotent, it needs durable state before it needs a schedule.**
- **No lock, and the jobs are why.** `dispatch_pending` claims with `FOR UPDATE SKIP LOCKED`,
  `project_timeline` is idempotent by a unique index, `sweep_offline` filters on idempotency
  keys before it publishes, and the sweeps are statements whose predicate no longer matches the
  rows another worker took. An advisory lock around each job would make that invisible rather
  than true, and `test_two_runners_over_one_tenant_do_not_dispatch_an_event_twice` is two real
  threads rather than an assertion about one.
- **Two metrics and no table, for the same reason.** A job run is "how long work took and how
  often it succeeded", which is exactly what MOD-011's store is for and exactly what has no
  table of its own -- so `worker.job_duration` and `worker.job_success` duplicate nothing,
  which is the test that catalogue applies to itself. The `job` dimension is the first closed
  one in it: a consumer name and a check key are tenant-chosen, and a job is code.

Things worth knowing before extending it:

- **A failure path inside a batch loop must not raise**, and here the unit is a whole tenant.
  MOD-010 shipped a relay whose failure handler raised, so a poison row aborted every healthy
  delivery behind it; the same shape is available one level up, where one tenant's bad data
  would stop every tenant after it in the list while the process still looked like it was
  running. Every job runs inside its own `try`, and `run_forever` catches the tick's own
  exceptions too -- a tenant list that cannot be read is a reason to wait, not to exit.
- **The schedulable set is `provisioned` and `active`.** Suspension is a customer being told
  they do not have the product, and archival is finished, so neither gets work done on its
  behalf. Provisioned is the one worth arguing: the obvious reading is that nothing has
  happened in it yet, and in this build that is false -- nothing on the tenant plane checks the
  registry before a write, so a tenant accumulates outbox rows from its own bootstrap onwards.
  Excluding it would leave a backlog that reads exactly like a relay that had stopped.
- **The actor is a fixed, derived identifier and is obviously not a person.** Three jobs write
  evidence, and this codebase's standing rule is that evidence with nobody's name on it answers
  nothing. `WORKER_ACTOR` is a version-5 UUID over a `.invalid` URL: stable across restarts,
  never issued by MOD-007 (whose identifiers are version 4), and a row attributed to it says
  "the scheduled worker did this", which is a true and useful sentence. A random id per run
  would say nothing and a borrowed operator's id would be a lie about who decided.
- **The name list is a leaf module on purpose.** `app/worker/names.py` imports nothing, because
  the registry imports every module whose work it drives and MOD-011's catalogue is imported by
  most of them -- so the names could not live in the registry without closing that loop. The
  registry asserts at import that the two agree in both directions, which is MOD-010's
  check-at-import argument: a job with no declared name could not record a point at all, and a
  declared name with no job is a dimension value nothing can emit.

What is deliberately **not** a job, each for a stated reason:

- **MOD-007's challenge sweep.** `iam.challenges` has no DELETE grant for any role, by design.
  A job that ran and deleted nothing would be activity with no effect -- worse than the gap.
- **MOD-010's `deliver_pending`.** It refuses a consumer with no handler, and this process
  registers none. A relay driving an empty registry would read as a control and do nothing.
- **MOD-020's session settlement.** It decides whether somebody was absent, and
  `settle_session_bookings` deliberately takes no caller-supplied instant. **Which sessions are
  due is a decision to make here, not a blocker** -- a session whose check-in grace has run out
  is the obvious predicate and the function already computes that window. It is unwired because
  it has not been done, which is a priority rather than an obstacle.
- **MOD-012's credential rotation announcement.** `credentials_due` is not idempotent across
  calls by design, so scheduling it needs a record of what has already been announced. That
  record is a table and an idempotency key -- work, and the same shape MOD-011's breach
  announcement turned out to need. Unwired, not blocked.
- **MOD-009's retention sweep is the one external entry here**: retention is owner policy,
  named in the isolation rules beside regions and keys, and destroying records on a schedule is
  the one sweep where being wrong is unrecoverable.
- **MOD-017's renewals and dunning, and MOD-018's recognition and period close, are work.**
  This list used to say each "needs a judgement this registry would have to invent", and that
  was wrong twice over: the delegation hands over product decisions as well as engineering
  ones, so a recognition cadence and a dunning step are mine to decide and record -- and
  dunning's *message* is the only part that waits on anything, which is the messaging provider
  above. They are unwired because nothing has written the decision down yet. **MOD-011's objective evaluation and MOD-013's digest close both came off this
  list, and neither by making the decision it was said to need**,
  and the shape of that is the lesson: the judgement it looked like it needed, *which*
  objective is due, turned out not to exist -- every objective carries its own window -- and
  the one it really needed was *how often a breach is announced*, which is a different
  question and a smaller one. `objectives.announcement_window` answers it from the objective,
  so the job's cadence does not decide how many events get written, which is what made it safe
  to wire at all. MOD-013's was starker: its note said closing a digest window needed the
  digest template format, and that format renders a batch into a *message* -- it has nothing
  to do with whether an elapsed window is marked closed, which needed no decision at all.
  **Ask of each remaining one which judgement it actually needs**, because three times now
  the obvious reading of "this needs a decision" named a decision that was not in the way -- and
  the second time the blocker named was a true sentence about a different half of the feature,
  which is the harder kind to see past. **And the third reading found no job at all**:
  MOD-018's bullet listed wallet expiry among its undriven sweeps and claimed lapsed value
  stays spendable, when `balances` excludes it at read time by design and `expiring_before`'s
  own docstring says it is "for telling a member, not for sweeping". There was nothing to
  drive. A gap note that invents a job costs more than one that omits a job, because the
  omission is found by looking for work and the invention is found only by trying to do it.
  **And the fourth reading found a defect the note had buried.** MOD-017's bullet said nothing
  applies a cancellation when its notice runs out and named the consequence as a stale status
  cache -- which is the mild half. The consequential half was that the *grants* were never
  revoked either, so a member who cancelled with notice went on drawing entitlements after
  their membership ended: `_revoke_grants`' own "access the member is no longer paying for",
  in the path that survived the review which found it. The note mentioned the cache because
  the cache is what a reader of the table sees; the grant is what a member spends.

Known gaps, deliberate:

- **One process, and the schedule is in its memory.** Two workers are safe (the jobs
  coordinate) but they do the same work twice; there is no leader election and no partitioning
  by tenant. At this scale that is waste rather than a fault.
- **Nothing restarts it.** There is no process manager, no deployment and no health endpoint
  for the worker itself -- the operations board answers "did it run" from what it recorded,
  which is the honest form of that question and not a heartbeat.
- **A tick is sequential over tenants and jobs**, so the wall-clock of one tick grows linearly
  with the tenant count. The fix when it matters is concurrency per tenant, which the advisory
  lock this change did not need would then earn.
- **`project_timeline` re-asks "what is not yet projected" every minute**, against an outbox
  that has no DELETE grant and no archive. The predicate is a `NOT EXISTS` over the timeline
  table bounded by the nine projected event types, so it is cheap now and gets less cheap as
  the outbox grows -- the cost of running a job on a schedule rather than when somebody asks.
  The archive MOD-010 names is what fixes it, not a change here.

## The web app

`web/` is the operator surface, and it exists because a module whose only client is a test is
not a product. Next.js 16 on the App Router, TypeScript, no UI framework and no CSS library:
`src/design/ds.json` is the design system and `generate.mjs` emits the CSS custom properties
from it, **failing the build on a dark-mode reference it cannot resolve** -- which is how
seven missing dark tokens were found rather than shipped.

What is built: a sign-in flow that works with JavaScript disabled, because it is a Server
Action and a form rather than a fetch (the first version was a client component, and an
un-hydrated page did a native GET that put the password in the query string -- the defect is
recorded at the top of `src/app/login/actions.ts`); MOD-007's device challenge answered in the
same form, with the password field *removed* once a challenge is in flight; a step-up that
raises a session from level 1 to level 2 and replaces the cookie, which is what makes the
identity-class fields on a member's record readable; English and Arabic
with real RTL, switched by a form rather than an `onChange`; a light and dark theme; a section
navigation whose every entry is present exactly when the gate allows the page behind it;
MOD-004's hierarchy -- the organization, its brands, its sites with the timezone MOD-019 reads
every rota window in, and the legal entity MOD-017 numbers invoices per; MOD-008's roles, the
permissions this session actually holds and the hash-chained audit log; MOD-014's duplicate
queue and Member 360, with MOD-017's membership, entitlement and billing blocks composed onto
it; MOD-019's schedule board and session detail with MOD-020's roster on
it; MOD-005's configuration and feature-flag board; MOD-021's fleet board and
device detail; an operations board over MOD-010's event plane, MOD-011's objectives and the
worker's own scheduled jobs; MOD-022's door board and zone detail, which read the real
routes and render the public code, the policy terms, the advisory occupancy with paragraph
4180's disclaimer, the access points, the gaps the module discloses about itself and the
decision log with its public/private split; MOD-026's task list, attention item and resolved
board, which are the **first screens here with a full set of working write forms** -- every
permission in that module is routine, so the bulk completion, the five assignment and deferral
acts and the resolution all have forms rather than reasons for not having them; and MOD-007's
account page, which was the only screen in this app that wrote anything for a long stretch and
has five of them: revoking another live session, revoking a device, trusting one, minting a
batch of recovery codes and enrolling a passkey.

**MOD-026's three screens are where a reader who is *nobody* became a product state worth
rendering.** Two of ADM-CC-06's five states and ADM-TSK-01's first chip are derived from
`ppl_identity_links`, and a staff login does not have to be anybody in particular -- the
fixture's owner holds all 217 permissions and is nobody in this tenant. So `Mine · 0` is two
different facts and only one of them is about the work, which the board says out loud; "Assign
to me" is rendered with the reason rather than as a button the server would refuse by name; and
the fixture seeds a duty manager who *is* a person, so the owner reads the same item as somebody
else's and both halves of the one state the canvas is most specific about have a browser
fixture.

**And the elapsed figures on the resolved board are all under a minute, which is the fixture
rather than the screen.** `tsk_cases.opened_at` is `now()` and no route backdates it, which is
right for the product -- a case is opened when it is opened -- so `TOOK` and the median are
honest and uninformative there, and the *format* is proven against the canvas's own `12m` /
`1h 20m` / `2h 04m` in `web/tests/component/tasks.test.ts`. Saying which layer proves which
half is cheaper than a reader deriving it from a weak-looking browser assertion.

**The Member 360 is where `Decision.mask` finally reaches a reader.** MOD-008 computed
`masked_fields` on every allowed decision and from MOD-008 to MOD-013 nothing read it; MOD-014
applies it, and until this surface existed nothing *rendered* it. A page that dropped a masked
value would undo the application silently, because an empty cell is indistinguishable from
"there was nothing here" -- which is the one reading that is always wrong, and MOD-014's own
rule is that a redacted record still exists. So a withheld value is marked, with a dashed
border rather than a colour, and the marker names which of two reasons it is: an identity field
needs a stronger sign-in, and a health field cannot be read by anybody in this build.
Offering a step-up for the second would send somebody looking for a hardware key MOD-007
cannot verify. The fixture's browser session is assurance level 1, which is the useful level to
test at: `contact` opens on a routine permission and `identity` needs a financial one, so one
record shows a masked legal name beside an unmasked email address.

**Four layers of tests and 140 green assertions did not notice that the schedule board showed
the wrong time, and that is the finding of this whole surface.** The rule says 18:00 and the
site is `Asia/Amman`, so MOD-019 stores 15:00 UTC and the local facts beside it -- because
neither is derivable from the other, which is the module's own first decision. The board
sliced the ISO string and rendered `15:00`, under a heading promising the site's own timezone.
Every test passed, because every one of them asserted that the *name* of the timezone was on
the page rather than what the times said. **It was found by opening the page and looking at
it**, which nobody had done for any surface in this repository until somebody asked.

The same look found that **seven of thirteen surfaces scrolled sideways at phone width** --
every page with a table, plus a label/value grid whose track was wider than the screen before
the value was drawn -- so a reader on a phone could not see that `Free` and `Status` existed.
Neither defect is subtle. Both are invisible to assertions about text and structure, which is
what all four layers were.

So there are two more layers now, and they are the durable half of the answer:
`tests/component/scheduling.test.ts` tests `inZone` where it is decided, including the
midnight case that reads `24:00` without `hourCycle: "h23"`; and `tests/e2e/phone.spec.ts`
drives all thirteen surfaces at 375px and fails on one pixel of horizontal scroll, with an axe
run at that width because making a table scroll is also what makes it a scrollable region that
needs keyboard access -- which it duly failed until every table got a `tabindex`.

Looking also found the two smaller ones that make the first two worth stating as a class.
**The Member 360 told a staff member the product does not have bookings** -- five sections
said "not built in this repository" and four of those modules have been built since, with an
e2e test *asserting* the false string. And **every instant outside the schedule had no zone on
it**, which was merely ambiguous while every screen did it and became misleading the moment
one screen started converting; `src/lib/time.ts` now holds both readings together so the
difference is a decision rather than one page's habit.

**And the message catalogue's parity check was one-directional**, which is the finding with
the longest reach. `MESSAGE_KEYS` is the English catalogue's own keys, so the check saw an
English key missing from Arabic and was blind to the reverse -- an Arabic-only key is a
translation nothing renders, and it reads as a translated interface to anything counting keys.
Found by adding one by accident and watching the file stay green. It is both directions now,
which is the rule this repository already applies to event payloads, to the id sweep's stale
exemptions and to the worker's name list: **a check in one direction is half a check, and the
half it is missing is the one nobody is looking at.**

**A screenshot is not a test and looking is not a layer**, so the lesson is narrower than "take
screenshots": an assertion about a *rendered value* catches what an assertion about a label
cannot, and "the timezone is named on the page" was always the weaker of the two available
assertions. The stronger one -- every row reads 18:00 -- costs the same to write.

**The configuration board is four answers that look like two numbers**, and it is the first
surface where the interesting thing is a *reason* rather than a value. A resolved configuration
value and a flag's variant are the two fields on that screen most likely to be read as
something they are not, so neither is rendered alone:

  * **A default is not a setting.** An unset key reads back as its own default, with scope
    `default` and `version` null, which is indistinguishable from a tenant that published the
    same value on purpose unless the scope is shown. The board says "nobody set it".
  * **`off` is four different facts**: a kill switch somebody engaged, a flag nobody enabled, a
    targeting rule that sent this subject to the control arm, or no rule matching at all. The
    kill switch gets an alarm of its own because it outranks every rule -- it is a deliberate
    stop rather than a rollout, which is the distinction MOD-005's evaluator is built on.
  * **A rule id is not a reason.** `rule:0f3a…` tells a reader nothing, so the page says "a
    targeting rule matched" and leaves the id in the data for whoever is debugging.
  * **A flag is evaluated per subject, and no route lists flags without evaluating them.** So
    the board is "what these flags say for one subject" rather than "what flags exist", which
    it says -- otherwise a flag missing from it reads as a flag that is absent. The subject is
    the reader's own identity unless a link names another: derived, not accepted, which is the
    same rule the schedule's site follows.

Both blocks are gated on their own permission, because `config.flag.read` and
`config.definition.read` are separate and a reader may hold one: an empty flag board would say
this tenant has no flags, which is a different fact from "you may not see them".

**The schedule board is the second place a withheld field reaches a reader, and the first
where the surface has to say which of two refusals it is.** MOD-019 masks a session change's
`reason` for anybody who does not hold `scheduling.session.change`, after a reviewer read "she
is having chemotherapy on Tuesdays" out of that column holding only the routine schedule
permission. The page marks the withholding rather than dropping the entry -- an absent row
says nothing changed, which is a different and wrong fact -- and then asks the gate *why* it is
withheld, because `reason_masked` is one boolean over two situations with different remedies:

  * **a session too weak for a financial action**, which a step-up fixes. `scheduling.session
    .change` is financial class, so `held_permissions` filters it out of a password-only
    session -- which means **the fixture's owner, holding all 202 permissions, cannot read it
    either**. That is MOD-014's "a grant is not a session" finding showing up as a product
    behaviour rather than as a defect, and the page offers the step-up it needs.
  * **an identity that does not hold the permission at any assurance**, which a step-up would
    not fix. Offering one would send somebody looking for a second factor that changes
    nothing, so the page says so instead.

Both answers are asserted, and the second needed a session that is genuinely masked: the
fixture's second identity now holds `scheduling.schedule.read` without
`scheduling.session.change`, which is the pair the mask exists for. Signing in as the owner
could only ever have proved the step-up half.

**Two more things the board says because the module refuses to store them.** `Taken` is a sum
over the hold rows and `Free` is MOD-019's own answer rather than a subtraction -- there is no
`held_count` anywhere in the module and the absence is swept for, so a reader who took these
for counters would be reasoning about a mechanism that does not exist, and a surface that
computed `places - held` would render a negative number for a session whose overbooking was
reduced after the holds were taken. And `dst_adjusted` is the one flag marked on the board: a
full class is ordinary and a cancelled one is a decision somebody made, but an occurrence
stepped forward because its local time did not exist that day is a session whose members were
told a time that is not when it happens.

**The roster is on that page too, gated on its own permission**, because paragraph 4145 puts
the occurrence and its capacity on MOD-019's side of the line and the member's reservation on
MOD-020's. A reader may hold one and not the other, so the block refuses rather than rendering
an empty class: "nobody is booked" and "you may not see who is" are different facts and only
the first is one a coach would act on. The seats above it belong to the schedule -- there is no
roster table and no cached total -- so the page says so, because a reader who counted the rows
would disagree with the seat count the first time a hold had no booking behind it, which an
unanswered waitlist offer is. That is also the first MOD-020 surface in the build, and the
first time `/booking/sessions/{id}/roster` has been called by anything but a backend test.

**Listing the sites is a different permission from reading the schedule**, and separating them
was what let the masked-reason case be tested at all. The calendar carries the site's own name
and timezone, so a board needs no hierarchy read -- only the *picker* does. A session holding
the schedule read alone is told to open the board from a link that names the site, rather than
shown an empty picker that would read as "this tenant has no sites".

**The operations board is where the worker runtime became visible, and it changed what a
backlog means.** This file's most-repeated gap was "nothing drives this on a schedule", and
the event outbox was where it showed: every module writes to it, there is no DELETE grant, and
nothing drained it -- so the number climbed whenever somebody used the product and the page's
whole job was to stop that reading as an incident. The relay now runs every fifteen seconds,
so a *pending event* that persists is a worker that is down, which is the first fault this
page can diagnose rather than excuse. A *pending delivery* is unchanged and still expected: no
name in this build has a handler behind it.

Telling those apart needs evidence the worker ran, and the scheduled-jobs block is it --
`/ops/worker`, the one read in the build where a dimension may be named, because a job name is
code and a consumer name is a tenant's. **A zero there is a sentence rather than an absence**:
every job runs for every tenant at least every five minutes, so no recorded run over a window
of hours is a stopped worker. A count of runs against an *expected* count is deliberately not
returned, although the arithmetic is trivial: every reading of it is wrong unless the worker
was up for the whole window, which is the thing being tested, so a worker started ten minutes
ago would report 40 runs against an expected 5,760 and read as broken. `no_evidence` is kept apart from `stopped` for the same reason a
refusal is kept apart from an empty table -- a reader without `ops.metric.read` has learned
nothing, and a page that called that an incident would be inventing one out of its own
permissions. A dead letter stays apart from all of it, because that one is a fault whatever
else is true.

And the fixture **runs the real worker**: `python -m app.worker --once` is its last step, so
the board is asserted against rows a scheduled job actually wrote rather than against an empty
screen with an explanation on it. The spec that used to assert the pending count was *not*
zero now asserts that it is.

**The fleet board is three answers rather than a list**, and the fixture seeds all three
because one healthy turnstile cannot show what the board is for: a door that works, a door that
cannot be put into service because paragraph 4175's commissioning is incomplete, and a device
that is not a door at all. The pages say three things the product cannot do -- reachability is
worked out from the last report and nothing polls on a schedule, so the board is "as of" when
it loaded; "needs somebody" is `active` *and* `offline` together, because a device in
maintenance is not an incident; and a credential is a fingerprint and a vault reference with no
signature verified anywhere, which matters because MOD-022 opens doors on that identity. The
commissioning block lists all seven tests with which are recorded, not only the missing ones: a
list of what is missing cannot be told from a list of everything when nothing is missing.

**The permissions page is where a surface had to be stopped from making a true-sounding
claim.** MOD-008's chain detects editing and not truncation by somebody who also moves the
head, so the page prints that caveat beside the *green* answer rather than under the red one --
a tick with no caveat is the more misleading of the two. And the first version of the page said
allowed actions are never recorded; they mostly are not, but MOD-008 records the acts that hand
out access, and the fixture's own log shows `role.assigned` with outcome `recorded`. A surface
that describes a log wrongly is worse than one that does not describe it, and the data is what
caught it.

**The step-up is where the web app meets MOD-007's own shape most directly.** MOD-007 does not
elevate a session in place: it revokes the one it came from with `revoke_reason = 'stepped_up'`
and opens a new one, because a session's lifetime follows what it can do and a level-2 window is
twelve hours rather than a fortnight. **So a step-up that does not write the new token into the
cookie is a sign-out dressed as a success** -- on the one path where the reader has just proved
who they are -- and that is the first thing the browser suite asserts. Three more facts come from
the server rather than from an assumption: which factor can raise *this* session (two passwords
are one kind, so a password session needs a recovery code and a recovery-code session needs the
password), whether the level is reachable at all (level 3 is not, by anybody here), and the
challenge, fetched immediately before the post rather than rendered into a hidden field where it
would go stale while somebody looks for their codes.

And `next` is validated as a shape rather than against a list of hosts -- it arrives in a link,
and sign-in and step-up are the two pages where a redirect to a lookalike host is worth the
most. `safeNext` keeps a same-origin path and refuses protocol-relative `//host`, the backslash
variant browsers normalise, an absolute URL with or without a leading slash, and a control
character; a refused value redirects home without saying so, because a message would only teach
somebody which probe got through.

**The navigation is the first surface with a test that needs a weaker session.** The fixture's
owner holds all 202 permissions, so signing in as the owner proves only the allowed half of any
gate -- a navigation that ignored the gate entirely would pass every assertion. The fixture
already created a second identity for MOD-022's two-party policy publication, holding
`access.zone.read` and not `tenancy.organization.read`; it now confirms that identity's browser
device too and exports its credentials, and one spec signs in as it to assert the Organization
entry is **absent** rather than disabled and that the page itself answers "not permitted"
rather than an empty tree. The same shape will be needed by every surface from here on.

How it is proved, in four layers that answer different questions:

```bash
(cd web && npm run verify)
```

- `tests/unit/` runs on Node's own test runner with no dependencies -- the design tokens, the
  contrast ratios, the locale conventions.
- `tests/component/` is Vitest and Testing Library: the states a reader is actually given,
  which is where the challenge form lives, because an end-to-end test of a challenge passes
  or fails depending on whether an earlier test in the run burned it.
- `tests/e2e/` is Playwright against a real uvicorn and a real PostgreSQL. `tests/e2e/serve.mjs`
  starts the backend, `tests/e2e/fixture.mjs` provisions a tenant, an identity, a session
  stepped up to AAL 2 and a complete MOD-022 fixture through the service layer, and writes
  `web/.env.e2e.local` at mode 600. **It prints no generated credential.** The one password
  on its summary line is a constant in the file -- a convenience sign-in for whoever is
  looking at the page -- so a terminal scrollback learns nothing it could not read from the
  source; every password it *derives* stays in the 600 file. The flat claim that it "never
  prints the password" was here until somebody ran it and read the output, which is this
  file's own standard applied to itself: a doc claiming a control it does not have is worse
  than no claim.
- `tests/e2e/mutate.mjs` is the sweep: it breaks a surface on purpose and asserts the suite
  goes red. A green browser suite proves nothing about a page nobody asserted, and this is
  what found a test that passed with the recovery-code field deleted.

**Three things about the suite itself are worth carrying forward, and two of them are one
rule.** `tsconfig.json` excluded `tests/e2e`, so the only TypeScript in the repository nobody
typechecked was the suite that drives the product: a spec calling a helper it had not imported
passed `npm run typecheck`. That is a check that cannot run, which is the same shape as a
vacuous test.

The other two are the same mistake twice, and a third instance made the pattern clear: **a
test that spends a budget the product keeps per identity has a green that depends on how many
times it has been run.** A single-use recovery code, spent answering the device challenge, was
green on the first run against a fresh fixture and red on the second. Thirty logins a minute,
spent by a `beforeEach`, put a cap on how many tests the suite could contain and it hit that
cap at 53. And five recovery failures lock an identity's recovery path with nothing to reset
it, so the test that submits a wrong recovery code spent one of the owner's five per run --
and on the fifth run every step-up failed with "that was not accepted", for a code minted
seconds earlier. **The rule: a test that consumes a product budget must consume one nobody
else depends on, or provision its own.** None of the three is visible in a single run; running
the browser suite twice in a row is what finds them.

Both jobs run in CI (`.github/workflows/veyro-foundation-ci.yml`), and the web job builds the
database, starts the backend, installs Chromium and runs the browser suite rather than
mocking the API -- a mocked backend would have passed every one of the defects the real one
caught.

**And a test that asserts a freshness has to create it**, which is the same rule as the three
budget findings above and was found the same way: by running the suite an hour after seeding.
The fleet board shows `Online` only while a device has reported within ten minutes, so that
assertion was true because the fixture's health report made it true -- and ten minutes later it
was false. CI provisions immediately before the suite and never saw it; a local run against a
stale fixture reads `Late`, which looks exactly like a product regression and cost three runs
before it was fixed properly. **The spec reports the device healthy itself now**, reading the
bearer token out of the browser's own session cookie -- `context.cookies()` can see an httpOnly
cookie where page JavaScript cannot -- so the freshness it asserts is the freshness it made.

**And the linter had never run.** `next lint` was removed in Next 16 and ESLint 10 ignores
`.eslintrc.json`, so `npm run lint` answered "Invalid project directory provided, no such
directory: web/lint" and nothing in CI called it -- a check that cannot run is a check nobody
has, which is the same shape as a test that passes vacuously. The flat config in
`web/eslint.config.mjs` is the migration; its first run found four unused imports and
variables, and it is in `npm run verify` and in the CI job now.

**The membership and billing blocks are the first surface that composes two modules, and
building them needed five routes that did not exist.** MOD-017 shipped with no listing route of
any kind: every read took an id the caller already had to know, so a membership, a grant, a
billing account and an invoice were each reachable only by having just written one. That is the
"a writer with no reader" gap `GET /brands` closed for MOD-004, two years of modules later and
four times over, and the remedy was the same -- routes on the server rather than inference in
the client. `GET /memberships`, `GET /memberships/{id}`, `GET /member-entitlements`,
`GET /finance/accounts` and `GET /finance/invoices`, each on the permission whose own
description already covered it, so nothing in the catalogue moved.

Four things about those reads are worth carrying:

  * **None of them returns a name, an address or a birth date.** `membership.record.read` is
    routine and AAL 1 -- a front desk and a turnstile hold it -- so a membership list carrying
    the member's legal name would be a lateral read path around `people.person.read`, which is
    MOD-010's `events.event.read` finding exactly. A test asserts the absence by *name*, not by
    field list, on all four list routes.
  * **A filter value outside its domain refuses.** `status=actve` and "this member has no
    active membership" are different answers and a list that renders both as an empty table is
    a surface nobody can trust.
  * **Every list is bounded and ordered.** Unbounded is a bulk export and a denial of service
    at once; unordered makes the planner the author, which is MOD-018's `chart_for` finding.
  * **The balance is `entitlements.balance_of`, not a `sum()` in the SQL.** Both are addition
    today, which is why writing the second one was tempting -- and a balance with two
    definitions has two answers the day either moves, which this module's own invoice list says
    one function up.

The page composes rather than joins. Paragraph 1300 bars a cross-domain read, so MOD-014's
projection says in its own `sections` block that it does not read MOD-017; a *surface* has no
such restriction and every reason to compose, so it calls each module's routes through each
module's gate and renders them beside the person. Three gates, asked separately, because a
reader may hold any subset -- a coach sees the membership and not the money -- and a refused
block says it was refused rather than rendering empty.

**MOD-012's board found two defects in itself, and one red CI run found a third elsewhere.**
Nothing syncs, so a run's record counts are a caller's word and the page says so beside them;
a credential is a reference to the vault MOD-007's TOTP seeds, MOD-009's crypto-shred and
MOD-021's device certificates are also waiting on, said in the same words the fleet board uses
because four screens saying it four ways would read as four gaps.

What the board shipped wrong, and looking found:

  * **The written-obligations check was keyed on `live_critical`**, which
    `int_installs.criticality` never holds -- the vocabulary is `convenience`, `important`,
    `critical`, and `lifecycle.py` compares against the last. So every install reported "not
    required at this criticality", including a `critical` one carrying traffic without its
    exit plan. A control keyed on a value that never occurs, caused by taking the prose ("a
    live critical install") for the stored value.
  * **The same comparison was written twice.** The page re-derived it inline for its own cell
    while the library answered the banner, so fixing the library left the cell wrong -- the
    banner correctly named the install while the row beside it said the obligations did not
    apply. `obligationsApply` is exported so there is one definition, which is MOD-014's "a
    control consulted on one path and not its sibling" in a surface.

**And a 500 on the unauthenticated platform plane.** `register_definition` read `f["name"]`
and `f["field_type"]` out of caller-supplied dicts, so a field missing either key raised
`KeyError` and answered 500 -- found by a fixture sending `type`, which is the name a person
reaches for. The shape is checked at the boundary now and the error names the index, because
"a config field is malformed" in a list of eight sends somebody reading all eight. An
`isinstance` guard was written beside it and deleted: Pydantic refuses a non-object at the
request boundary, so the branch was unreachable, and a branch no caller can reach is dead code
reading as a control.

**MOD-013's board is the opposite problem: the module works and nothing sends.** There is no
provider, no SMTP and no outbound request, so every notification sits at `requested` for ever
-- and the honest thing to render is an absence. The waiting count leads the page with the
sentence that says what it means: not a backlog to clear, the lack of a dispatcher. A board
showing the number alone would be claiming an outbound path there is none of.

Three things the page does not show, each the server's decision rather than the surface's
restraint: no message text, because the list route carries no rendered body on purpose and
one that did would be a read path to everything a tenant has ever said to anybody under one
permission; no address, because the tables hold a SHA-256 of `channel:address`; and no release
control on a bounce, because only an unsubscribe may be lifted, so the page says which kind a
row is rather than offering a button that would be refused.

**The template *body* now has a reader, and it did not before.** `list_templates` omits it --
a body per row over every template a tenant has authored is a page of prose nobody asked for
-- which left the text unreadable anywhere in the build: a template could be drafted,
approved and published and the only way to see what it said was to send a message with it.
`GET /notifications/templates/published` is the single-template read, on the same
`notifications.template.read`, because a body carries no subject data: the text is the
tenant's own prose and its variables are placeholders rather than values. ADM-PAY-05's
message preview is the first surface to need it, and it renders the body **unrendered** --
`templates.render` requires a value for every declared variable, and the one this build
cannot supply is the payment link.

**And the decision reason was rendering as its stored enum.** `no_preference_stops_it` tells
a reader nothing they can act on -- "a rule id is not a reason", which MOD-005's board learned
about flags, met again one module over. The eight reasons read as sentences now, and an
unknown value falls through to its raw form rather than to "unknown": the set is the module's
and may grow, and hiding a decision somebody needs to see is worse than showing an ugly one.

**The first fix for that was itself a defect, and only the other locale showed it.** The
sentences went into a `Record<string, string>` in the library -- English prose, rendered
straight to the page -- so the most explanatory field on the Arabic board read in English
while every heading, caption and empty state around it was correct. `MESSAGE_KEYS` compares
the two catalogues against each other and is structurally blind to a string that never became
a key, so no assertion could have found it; it was found by switching the language and
looking. The map returns a `MessageKey` now, a component test asserts every key it maps to
exists in **both** catalogues, and a browser test reads the Arabic sentence off the Arabic
page. The rule is in `.claude/rules/backend/mod004-rls.md` beside the other evidence rules,
because the blind spot is the check's and not this module's.

**MOD-009's board is the disclosure, finally somewhere a person can look.** 17 subject-bearing
columns are erased or anonymised and 375 survive, and that ratio is the most important thing
this build knows about itself. Three decisions carry the block:

  * **It groups rather than dumps.** The first version rendered all 371 rows with their
    reasons: a 25,000-pixel table. A privacy officer reasons in areas -- "the ledger survives,
    the audit chain survives" -- not column by column, so the residue is grouped by schema and
    module prefix, largest first, with one reason per area as the example. 2,472 pixels, and
    the shape is legible. The full per-column registry stays on the route.
  * **It renders the registry's emphasis.** Those reasons were written where `**` is emphasis
    and a backtick is a column name, in a Python module a developer reads -- so the page was
    printing `**who pays.** The account is...`, punctuation nobody wrote for a reader, in the
    one block whose job is to be read by somebody who is not a developer. `src/lib/prose.ts`
    splits the two delimiters and nothing else; stripping them was the worse fix, because the
    emphasis is each reason's summary phrase.
  * **It says the block reads no tenant data.** Two tenants get identical bytes, and a test
    asserts it.

Two defects in the surface, both shapes this file records. The page had a `Released` branch
for legal holds that **nothing could reach**, because the client never passed
`include_released` -- a declared state nothing writes, in a surface instead of a service. And
the request queue compared `overdue` before sorting by deadline, which the mutation sweep
reported as uncaught: an overdue request is one whose due date has passed, so a date sort
already orders them. That comparison was dead logic reading as a control, and the remedy was
to delete it rather than write a case that cannot exist -- the judgement the rules file records
for a constraint subsumed by a sibling.

**MOD-016's board is three claims the module refuses to make, made legible.** No figure on
it is "the price": `resolve_price` is the sale, because it redeems the coupon it applies, so
the route that answers authoritatively cannot be called as a lookup. What a board can show is
what was written, and the page says which of the three conditions it has checked -- the row's
window, the book's status, and the priority comparison it cannot do.

Two findings came out of building it, and one is in the existing read:

  * **`list_promotions` never returned the promotion's own window.** Nothing retires a
    promotion when its window closes, so a board showing `status: active` says a campaign is
    running when it finished in February -- and the listing had no way to say otherwise. The
    fixture seeds one live promotion and one that ended while still reading as active,
    because with only a live one the distinction is a comment rather than a behaviour.
  * **A published product can stop being sellable with nothing changing its status**, and
    nothing on the server notices. The board computes it from the product read and the price
    read, and names the right next action: `not_published` and `no_live_price` send somebody
    to two different forms.

And a third thing worth stating because it is a units trap rather than a product one: a
promotion's `percent_bp` is basis points, so rendering the stored number puts `1000` on screen
for ten percent. That is MOD-015's money discipline one field over, and an assertion about the
word "worth" passes either way.

**ADM-SCH-04's grid is the schedule board's missing third view, and its read did not exist.**
That board's own note said so -- "`Coaches` is in the gaps below: it is a grid of rota rows
rather than of sessions, and nothing here reads a resource's availability" -- and it was right
about the whole build: `set_availability` had a writer and no reader since MOD-019 was built.
`/rota` is the screen and `GET /scheduling/availability` is the read. Five things about it are
decisions rather than rendering:

  * **The rota is the background and the bookings are drawn on top**, and a booking the rota
    now refuses is **drawn and flagged** rather than dropped or silently honoured. The canvas
    argues it: "reducing availability never deletes a booking -- it surfaces the conflict for
    a person to resolve, because the member on the other end has already been told a time."
    So `bookedConflict` is a cell state of its own, and the refused bookings are also listed
    beneath the grid, because a marked cell in a grid of ninety is something somebody has to
    find. The fixture seeds exactly the canvas's case: an evening off with a class inside it,
    written *after* the class, which is the realistic order.
  * **Open hours are no figure where no rota binds, not zero**, so the page says
    "unconstrained" and draws no grid rather than seven columns of "not working" -- which
    would read as a studio nothing can be booked into. The fixture carries both members of
    that pair, and getting that wrong is how the branch nearly shipped unrendered: it was
    first pointed at the stand-in, which **has** a rota, because a substitution is refused
    unless the replacement's week covers the class -- so the test asserting "no rota binds"
    ran against a page showing 112 open hours across a full grid. A third staff resource
    with nothing written against it is the member that was missing, and a new hire is the
    realistic shape, since on the day a gym opens nobody has a rota.
  * **The hours figure is a whole number, and the alternative was a 500 on every request.**
    `formatInteger` throws for a fraction, because this app has exactly one
    number-rendering path and a cross-runtime parity test that compares it against the
    backend's character for character. The first version returned tenths, so the page
    answered 500 from inside `fill` with the route and the data both correct. Rounding to
    the hour is the fix and the screen says so, because across a week it is immaterial and
    below an hour it is not: a half-hour booking reads as no hours beside a cell that is
    visibly booked, and the exact minutes are on the route.
  * **The grid scrolls inside itself, and that needs a containment boundary.** `WeekGrid`
    had no live caller until this screen, so its wrapper scrolled and nothing stopped the
    overflow reaching the document root -- 95px of sideways scroll at phone width, which is
    `/permissions`' own finding in a component whose comment explains why the table is
    64rem wide. **Both halves are asserted**, because the two wrong states hide each other:
    a table pinned to its container inside a contained wrapper reports zero document
    overflow and has nothing to scroll, so the columns are clipped and unreachable while
    every assertion about text still passes.
  * **A week grid needs a way to leave the week it opened on, and this one had none.**
    Found by TestSprite, which is what an independent layer is for: `here({ from })` was
    defined in the page and called by nothing, and every spec here navigates straight to
    `?from=`, so none of them could notice. The screen answers "when can this coach work"
    and the question is almost always about a week that is not this one -- the canvas's own
    example is an exception agreed three weeks before the day it covers, which is the shape
    the fixture seeds and exactly what was unreachable.
  * **`WeekGrid` is the design system's own component for this shape**, and hand-rolling a
    second one was caught by the usage sweep. Its rule -- *severity is an edge-mark and never
    a fill* -- holds rather than conflicting: that rule is about a class cell, where a week
    with three tinted classes reads as three-quarters wrong, while these cells are states of
    availability and the fill is what the legend names. The one severity here is a refused
    booking, which the canvas marks with a border.
  * **A time-off reason is masked unless the caller could have written one**, because it is
    the one free-text column in a rota and the one place a health fact goes in practice. The
    exception itself is never hidden.
  * **ADM-MSH-03's freeze is the first *stepped-up* write form, and it falsifies a claim
    this file has repeated for every absent form.** "A button that answered 403 is worse
    than its absence" is true of a button that just fails, and says nothing about one that
    offers the step-up first -- which this app already does for a masked *read*. The honest
    cost is one recovery code per twelve-hour window rather than one per act. The allowance
    reads on the routine permission, so the figure that bounds the act is legible without
    stepping up at all; the act offers the step-up with `next` back to the member. The same
    shape as MOD-019's note claiming every scheduling write was stepped-up when the one the
    design put a button on was routine: a blanket reason covering a dozen screens is worth
    re-deriving for each of them.
  * **"Add an exception" is built, and it is the first write in this app that is not a
    member acting on their own account.** Every other absent form here is a stepped-up
    financial permission and "a button that answered 403 is worse than its absence";
    `scheduling.availability.write` is routine, and the catalogue says why. MOD-019's own
    gap note claimed every scheduling write is stepped-up, which was false for the one the
    design puts a button on. **What it needed first was the remedy**: the table was
    insert-only, so the button would have written a permanent, uncorrectable row on a
    routine permission -- MOD-013's rule from the other side. `0017` is the withdrawal; the
    form writes a dated absence and takes one back, and a reader without the write
    permission is given neither control rather than one that answers 403.

**ADM-MSH-07's cancellation is the third write form, and building it found that the design
and the implementation disagreed about a money figure.** That half is in MOD-017's notes
above; what is the surface's own is the shape of the sheet and five decisions in it:

  * **A side sheet this app has none of, so it is a parameter on the tab.** The canvas is
    explicit -- "none uses a modal -- they are side sheets over Member 360, so the member's
    context stays visible while you change their agreement" -- and `?tab=membership&cancel=1`
    keeps that property while giving "Keep it" something to do. A permanently-open destructive
    form has no way out, and a `<button>` that did nothing would be confirmed by somebody
    reaching for the exit.
  * **The commitment line is four sentences and the canvas draws one of them.** "His 12-month
    commitment runs to March" is false for a member on a rolling contract, for one whose term
    has run out, and for one whose contract sells no way out of a term they are inside -- the
    last being the state *every* contract in this build was in until the buy-out existed.
    `commitmentLine` decides which, so each branch has a test.
  * **The interruption's argument is conditional, and its two halves come apart.** "He stopped
    visiting 12 days ago and has not given a reason. A freeze costs him nothing and keeps the
    commitment intact" joins a claim about attendance to a claim about a commitment, and
    `freezeOffer` returns which of them holds. Told to a member on a monthly rolling contract,
    the second half describes a benefit that does not exist.
  * **An unknown last visit is not dormancy.** `days_since` is null at a club with no readers
    as readily as for a member who never came, so the freeze is not offered on dormancy
    grounds rather than offered on the assumption nobody has come -- MOD-014's "an unknown
    birth date is not a minor", in the same direction.
  * **The total is the server's and the screen never adds the parts.** The form echoes
    `disclosed_fee_minor` back for the command to compare against what it recomputes, so a sum
    computed here would be the second arithmetic this whole screen was built out of.

Proven: 23 component tests over every branch and 5 browser mutations, all caught; and the
sheet renders in a real browser at 375px without pushing the page sideways, which CI ran and
passed -- `phone.spec.ts` carries its route, and a surface reachable only with a query string
is exactly the kind that gets left out of a list of paths.

**The sheet's content is asserted now, and seeding it found a defect in this very screen.**
The geometry was covered and the figures were not; the fixture carried one contract, with no
minimum term, so of `commitmentLine`'s four sentences exactly one -- "this member has no
commitment" -- had ever rendered. The two-fee-line breakdown is gated on there being more
than one part and had therefore never rendered at all, and neither had "Before you cancel",
because the fixture's member visited yesterday and so is not dormant. Five branches, nothing
drawing any of them.

**Of the three unrendered sentences, one was unreachable, and the member it describes was
being told the opposite of the truth.** `commitmentLine` and `freezeOffer` both asked
`commitment.leaving_early`, which is "access ends before the term does" -- the buy-out's own
condition. Where a contract forbids an early exit `cancellation_effective_on` pushes the
effective date **to** the term end, so that flag goes false exactly when the member is most
firmly held: a member nine months inside a twelve-month commitment read **"The commitment to
2027-08-25 has been served"**, and was the one member denied the freeze offer whose whole
subject is keeping a commitment intact. `held_to_term` could not be produced by any input.

**And a component test had "proved" that branch with a quote the server cannot emit** --
`leaving_early: true` beside `may_leave_early: false`. So the dead branch sat behind a green
assertion, which is this build's vacuous-evidence shape arriving from a direction it had not
arrived from before: not a surface branch no fixture reaches, but a *hand-written unit
fixture* encoding a state the system cannot reach. The quote builder now throws on all three
combinations the server's own arithmetic forbids, and a test proves it throws.

The fix is a second fact rather than a cleverer branch, which is the lesson `reachable` taught
one module over: `commitment.term_is_running` is "is the commitment running today", derived
on the server because `today` is on no response and a client comparing `ends_on` against its
own clock counts days in a frame this build has three recorded defects from -- MOD-016's
`in_window` and MOD-018's `admits_trade` for the same reason. `leaving_early` stays, because
the buy-out is charged on precisely it, and what pins the distinction is a test asserting the
two **disagree** on a held-to-term contract rather than a comment saying they might.

`cancel.offerCommitted` was reworded in both locales for the same reason: "where cancelling
inside it is charged for" is false for a member held to term, where nothing is charged and
access simply runs to the term's end. It now states what is true of both and leaves the money
to the consequence block, which already says it exactly -- one claim in one place rather than
one case's version of it twice.

Proven: the fixture seeds a member for each of the four sentences -- a twelve-month term with
a two-month buy-out at JOD 40.00 a month, so the canvas's "two-month fee of JOD 80.00" is the
figure the real lifecycle computes; the same term with no buy-out; a one-month term that has
been served; and the rolling member. Read off the live API, the four answer
`leaving_early` / `held_to_term` / `served` / `none` with 2, 1, 1 and 1 fee lines. Four
browser tests read those sentences off the page, 3 backend tests pin the field in both
directions, 3 service mutations and 3 client mutations, every one caught.

**One assertion was deliberately not written: the headline total.** It is the buy-out plus
the part of the current period already used, and monthly periods tiling from a start ninety
days back put the period boundary near the notice date on some calendar days and not others
-- so the total is JOD 120.00 most of the year and a few fils under it the rest. A test
asserting it would be green depending on the day it ran. The buy-out is `months x
amount_minor` and never moves, so that is the figure the browser asserts.

**And the seed found a constraint by being refused rather than by anybody reading the
migration**: `mem_membership_terms` admits one set per product, so each contract needed its
own product. That is also the truer shape -- a twelve-month deal that sells an exit, one that
does not, and a rolling monthly are three things a gym sells, not three contracts on one
product.

**This paragraph claimed the browser layer had not run at all, which was wrong**, and the
error is worth recording rather than quietly fixing: the local suite needs port 3000 and the
shared `.env.e2e.local`, both held by another session's servers in this tree, and I read "I
cannot run it here" as "it has not run". CI builds the database, starts the backend, installs
Chromium and runs the whole browser suite on every push -- which this file says two sections
down. **An under-claim is a stale gap note like any other**, and it points a reader at work
that is already done.

**ADM-MEM-10's walk-in form is the second write in this app that is not a member acting on
their own account, and it needed a read nothing could ask for.** The canvas is two fields and
one interruption -- "This number already has a record · **Hala Barakat** · joined Feb 2025.
Continue and you will create a second record for the same person", with "Open that record" and
"Different person" -- and its own footnote states the mechanism: "Detection runs on phone as it
is typed, before anything is saved. Preventing the duplicate costs one screen; ADM-MEM-11
exists because prevention is never perfect." The read is in MOD-014's notes above. Five things
on the screen are decisions rather than rendering:

  * **A stale answer can never land, and that is a derivation rather than a guard.** The
    check is debounced and asynchronous, so a reply for a number the desk has already edited
    would mark a clear number as duplicated, or clear a duplicated one. The first version
    stored the whole state and compared each reply against a ref; `detectionFor(value,
    answer)` derives it instead, so an answer carries the value it was about and is simply not
    the answer to any other. **Found by the linter**, which refused `setState` inside the
    effect for two of the three writes -- and it was right for a better reason than the one it
    gives: a value computable from a prop is not state, and storing it is what created the
    race.
  * **"Different person" answers one number.** A dismissal that survived an edit would hide
    the interruption for whatever is typed next, so the acknowledgement *is* the value.
    Proving it in a browser takes two seeded duplicate numbers; one can only ever prove that
    a dismissal sticks.
  * **A check that could not run is not a check that passed.** An unreachable server holds the
    button exactly as a match does, because "we do not know" and "it is free" are different
    facts and conflating them turns a network blip into a silent duplicate.
  * **No keystroke validation, which is the Input contract's own rule.** "Validate on blur,
    never on keystroke; re-validate on submit" -- so the submit is not gated on the fields
    being filled, because a button that un-disables as they become acceptable is keystroke
    validation wearing a different control and leaves a reader with a dead button and no
    sentence. The *duplicate* hold is not validation: it is the canvas's own mechanism.
  * **One primary per view, and which control it is is what the duplicate changes.** With an
    interruption on screen, opening the record it found *is* the recommended action, so the
    create drops to secondary.

**And the sweep found the two shared-component defects, which is what a shared component
costs.** `Button` with an `href` renders a real anchor, and the global `a` rule sets only the
colour -- so **every non-link button with an `href` in this app has rendered underlined since
the component existed**, which is the thing the source forbids in as many words ("a link
styled as a button, and the inverse too"). And `Field` marked its control only for an `error`,
while the canvas marks the phone in the attention colour with the sentence in the panel below;
putting that sentence in the message slot as well renders it twice under one field, which is
the duplication the slot's own rule exists to prevent. `marked` is a mark without a message,
for the one case the slot cannot serve: the explanation is a region the control points at.

**And ADM-MEM-05 specified a control it did not have, with nothing recording that it did
not.** "Add member" is in that canvas's header and this app rendered nothing there -- and it
was not in that screen's own gap list either, so a specified control was missing from the
product with no record anywhere. It is the only way to reach ADM-MEM-10, and it is shown by
`gateVerdict` rather than by `allowed`: a reader who could step up gets the button, and one
the gate denies outright does not.

**FD-06 is the first Front Desk screen, and the first working write form in this app that is
not behind a step-up.** Every other absent form here is a stepped-up financial permission;
`booking.attendance.write` is `data_access` with no financial class, so a receptionist at an
ordinary password sign-in marks a member present -- which closes the half of MOD-020's own gap
note ("a front desk cannot do it for them") that needed no new permission. The canvas: "Spin ·
19:00 · Dana · Studio 2 · 12 of 18 here · Waitlist · 3 … Four minutes to go, six not here …
Rows are 48px because this is tapped while looking at a person, not at the screen. Hala's two
prior no-shows are shown without judgement -- it is context for the coach, not a flag on her."

Five things in it are decisions, and four were found by opening the page:

  * **A button the module will refuse is worse than no button.** `may_check_in` opens the
    check-in window an hour before the session and closes it after that booking's own
    snapshotted grace, and the first version offered the control whatever the clock said --
    so a desk opening tomorrow's class got a 409 rendered as prose under a row. The roster
    read now carries the window, computed by `attendance.checkin_window` rather than a second
    time here, because a screen and a refusal that disagree is worse than either; the row says
    when it opens instead.
  * **"2,266 minutes to go."** The canvas's lead sentence is an urgency four minutes out, and
    an urgency about something tomorrow is not one. `COUNTDOWN_WINDOW_MINUTES` is ninety and
    the figure is a judgement rather than a source. Arithmetic that is correct and a sentence
    that is absurd: no assertion about text could see it.
  * **Which class this is.** The roster is MOD-020's and carries a session id, an instant and
    a count; the title, the coach, the studio and the timezone are MOD-019's, composed through
    its own gate. A desk that cannot see which class it is looking at is a desk checking people
    into the wrong one -- and the instant is read in the site's zone, which is the schedule
    board's own hard-won rule.
  * **Three counts over the same rows, each from one place.** "0 of 12 here" counts attendance
    against the *session's* places rather than the roster's length, because a class with free
    seats is twelve of eighteen; "six not here" is the bookings still open and unarrived; the
    waitlist is a different list. All three live in `@/lib/desk` so the screen cannot compute
    one differently from another.
  * **A gym cancellation never reads as an absence.** MOD-020's worst shipped defect was
    exactly that collapse -- every member of a cancelled class recorded absent, with a fee and
    a strike -- so `released` and `session_cancelled` are their own row state, marked on the
    edge rather than filled.

**And the canvas's own promise is the one sentence the screen refuses to repeat**: "At 19:00
their places release to the waitlist automatically and the three waiting are notified -- you do
not have to remember." Nothing in this build does either. Settling a class decides whether
somebody was absent, which is a judgement rather than a sweep, so it is deliberately not a
worker job; and MOD-013 sends nothing. A screen that printed that sentence would be telling a
receptionist to forget something nobody is holding.

**Two reads came out of it, and one sweep.** `GET /people/names` is the batch a composed
roster needs -- eighteen rows asking one at a time is the round-trip problem the staff list
paid for once -- masked through MOD-014's own gate so it is a list of single reads rather than
a weaker one. And `tests/unit/shell-tokens.test.mjs` grew a sweep for `ds-` classes the
stylesheet does not define, which found **four**: `ds-card`, which two screens asked for and
which has no rule at all, so a card rendered as a loose stack of text; a spinner with no
animation; the field shell's contextual-action slot; and the data grid's own wrapper. A class
that styles nothing is invisible to every other layer -- the text and the structure are
identical either way.

**FD-08 is the strip above that desk, and it is the first thing in this app that is
deliberately not a screen.** "It sits above both Front Desk and POS at all times. Hardware
failing silently is how a receptionist ends up apologising for something they could not see."
So it is a layout, and every `/desk` route carries it; there is no POS here, which is the
other half of the sentence and a gap rather than a decision.

**The requirement is the fallback, and it is the part a backend cannot answer.** "The card
reader is down and the strip says *what to do instead*, not just that it failed." MOD-021
knows a device's kind, its state and whether it has reported; it does not know what a
receptionist should do, and there is no column where a tenant could say. So the fallback is a
map from kind to a sentence, and the discipline is that **every sentence names something this
build can actually do**. The canvas's own example is not one of them: "type the name instead"
needs a member search this product does not have, so following it would stop a receptionist
twice -- once at the hardware and once at the advice. What a desk can do when a reader dies is
find the member on the class they booked, which FD-06 renders. Where there is no honest answer
-- a kiosk, a gateway -- the kind is absent from the map and the strip says it has no fallback
to offer, which is true and uncomfortable.

**Two screens over the same data disagree on purpose, and both say so.** MOD-021's
`blocks_operation` is `active` *and* `offline`, and it deliberately excludes a device that has
never reported: nobody can be paged about when it stopped. The fleet board therefore says
nothing has gone quiet. A front desk's question is whether the reader works *now*, and an
in-service scanner that never checked in is exactly as unusable as one that died this morning
-- so the strip calls it degraded and names the fallback. The first attempt changed the
*board's* test to match the strip, which was the wrong direction; the board was right.

**And a false all-clear was on the screen.** `needsAttention` is not the inverse of "all is
well": a device registered and never activated raises no attention -- correctly, since a
half-installed reader is not an incident -- so the strip said "everything this desk needs is
responding" directly above two out-of-service readers. One statement is about whether to act
and the other is about the hardware. Found by looking at the page.

**The fixture gained the device both boards needed.** Nothing in it was ever `active` and
unreachable, so FD-08's degraded row and the fleet board's own "needs somebody" title had
never rendered -- the fourth instance of this build's "a branch no fixture can reach". One
scanner, provisioned and activated and never reporting, is what makes both legible.

**FD-03 is the screen where what a receptionist may say is governed by a permission**, and
that is MOD-022 working rather than a gap. The canvas: "**His membership ended on 7 August**
and the 14-day grace ran out five days ago. He was here three times a week for two years --
worth asking whether something changed before you lead with the renewal." A refusal carries a
public line a door may display and the real reason behind `access.decision.read_reason`, which
is financial class and whose split covers the *code* as well as the prose -- so the same
refusal reads as two different sentences depending on how the reader signed in, and **the
fixture's owner, holding all 207 permissions, gets the discreet one.** The screen says so and
offers the step-up, which is the member record's own pattern applied to a refusal.

Four modules on one screen, composed through four gates rather than joined, plus a fifth for
the door. Five things in it are decisions:

  * **The sentence comes from the code, never from the prose.** `sayFor` maps all nineteen
    reason codes to a sentence a desk can say, and `see_front_desk` -- the one a restricted
    refusal becomes outward -- gets a sentence saying so rather than one that pretends to
    explain. A surface that parsed a reason string to decide what to show is the shape MOD-016
    shipped, where four English words were the whole enforcement of a usage limit.
  * **A door's fault is not a member's.** `reader_clock_unreliable` and `device_untrusted` are
    both "denied" and nothing else about them is alike: one is a conversation with the member,
    the other with whoever maintains the hardware, so the screen says which.
  * **Nothing in the app admits anybody.** The override is one-way -- the decision log is
    insert-only and nothing withdraws an admission -- so the browser suite never presses the
    button and the fixture seeds an *already-answered* refusal on the twin instead, which is
    `freeze.spec.ts`'s own call for the same reason. The already-answered branch therefore
    renders from a real row rather than only in a component test.
  * **"Never a locked control with no route."** The button is absent where the gate says no,
    and the panel says that naming who to call is the half this build cannot do -- MOD-008's
    `/authz/simulate` answers what one person may do and not who may do one thing.
  * **Three of the canvas's four actions are absent and each says why**: renewing and a day
    pass are sales and taking money is owner-reserved; the photo needs an object store. So is
    half of the canvas's own header line -- the club is one more read that tells a receptionist
    standing in it nothing, and the plan is what the renewal button was for.

**And it broke four things of its own, three of them mine and one of them everybody's.**

- **A placeholder renamed across the catalogue took six messages with it.** Fixing the new
  plural message's placeholder to `{count}` -- which `fill` requires of a plural -- renamed
  `{days}` and `{rate}` in `cc.retentionTitle`, `freeze.lasts`, `freeze.leaves`,
  `dispute.due`, `dispute.windowClosed`, `invoice.taxedAt` and `member.wasPerWeek`. `fill` is
  strict in both directions, so each is a 500 on a rendered page, and the Command Center
  answered an error boundary for every reader. **Four test layers stayed green**: the key is
  in both catalogues, the plural forms match, the parity test compares key *sets*, and a
  renamed placeholder is an ordinary string. It was found by signing in.
  The durable half is two new checks -- both catalogues must name the same values, and every
  `fill(locale, "key", {…})` site must match the message's placeholders **per plural form**,
  because `fill` picks one form and the first version unioned them, which is how a rename in
  the `one` form only would have survived the very test written for it. **The sweep said so**:
  the mutation reproducing the real defect came back uncaught. The per-form version then found
  two live defects nobody had reported -- `access.pointsCounted` and `perms.showingModules`
  each have an Arabic `zero` form that drops a value its call site passes, so an Arabic reader
  at a zone with no readers, or a filtered permissions page with no module, got a 500.
- **A field I declared and the server has never sent.** `AccessDecision.masked` is
  `reason_withheld` on the wire, so the offer to read why a member was refused never rendered
  at all -- the control was dead on arrival. A hand-written type over an untyped JSON response
  is invisible to every typecheck, and the server's name is the better one anyway: it already
  means "withheld *from this caller*". Read the response; do not name the field.
- **An idempotency key that deduped two different admissions.** It was
  `(point, person, reason)`, and `override_access` answers a repeated key from the row it
  already wrote -- so a member refused today and admitted by hand, then refused again
  tomorrow and admitted for the same reason, produced **no second row**: the desk was told it
  had worked and the log showed one override for two. `overrideKey` is the refusal's own id
  now, and the reason is deliberately out of it, because two presses with two reasons would
  write two rows saying somebody was let in once. **Found by working out how a browser test
  would re-run**, not by reading it.
- **The design system's own badge rendered an English enum.** `StatusBadge` takes a closed
  twenty-word vocabulary so an engineer cannot invent "Semi-active", and FD-03 is the first
  screen in the app to use it -- so "Denied" went out in Latin letters in the middle of an
  Arabic line. The enum is the state and `label` is the word now, and a usage sweep requires
  it, because `MESSAGE_KEYS` is structurally blind to a string that never became a key. Fifth
  instance of "a vocabulary the backend stores is never a label", and the first where the
  vocabulary is the design's own.

Two harness findings came with it, both already written in the rules file and both paid again.
**Importing the sweep module runs it**, because the mutation loop is top-level code -- and the
stop left `httpOnly: false` on the session cookie in `login/actions.ts`, a file this session
had never touched, which is why the check is the *hunks* rather than the file names. And **a
test asserting a freshness has to create it**: FD-06's countdown is green for half an hour
after provisioning and red afterwards, which CI never sees because it provisions immediately
before the suite. The freshness cannot be made here -- moving a session is a stepped-up
scheduling write -- so the screen's own answer picks which sentence to expect and both are
asserted, a class in progress with six people missing being urgency too.

**ADM-RPT-04's board is one chart and one sentence, and the sentence is the requirement.**
The canvas's own note says why it is derived rather than left to the reader: "The conclusion is
written in words beneath the chart. A manager should not have to interpret a heat strip to find
the actionable hour." So the busiest window and the quietest attended hour come off the server
from `app/access/attendance.py`, where they are unit-tested, and the page renders a sentence.
Five things about it are decisions rather than rendering:

  * **The one claim it refuses is the canvas's own percentage of capacity**, for the two
    reasons MOD-022's gaps now record -- and the refusal is *on the screen*, naming the claim,
    because a note saying only "shares are relative" leaves a reader to work out which number
    is missing. Every share on the page is a share of the busiest hour.
  * **No chip says "Weekdays."** A working week is Sunday to Thursday in this product's own
    market and Monday to Friday in the one its design language comes from, and nothing in the
    build declares either -- so the route refuses to default the set and each chip names
    *which days*, which is a fact, rather than what they mean to a business, which is not.
    A component test asserts no label contains "weekday", "weekend" or "working".
  * **Twenty-four bars, including the empty ones.** Trimming the axis to the hours that saw
    somebody would be the surface inventing opening hours, and a 03:00 entry is exactly the
    bar a manager wants to see. The empty hours are drawn at the baseline, which is the
    weekbar chart's rule: an absent bar and a bar nobody can see are the same to a reader.
  * **The three heat tiers are semantic tokens, not the canvas's primitives.** It paints
    `warm.300`, `warm.400` and `warning.600`, and the generated token file says components
    must not reference layer 1 because "a theme is a remapping of layer 2 rather than a
    rewrite of layer 1" -- a light-theme warm grey hard-coded here is a bar that vanishes into
    a dark card. `--color-border-strong`, `--color-text-tertiary` and
    `--color-semantic-warning` come out monotonic in both themes, which is what a heat strip
    needs, and the light values match the canvas. The colour is never alone: each bar carries
    its hour and count as text and the conclusion names the window in words.
  * **Class fill and capacity planning are named rather than drawn.** The registry line is
    "peak hours, class fill, capacity planning" and the canvas draws the first of the three.
    A second chart this design does not have would be as much a deviation as a missing one.

**Two process findings came out of running it, and the first cost a whole suite.**
`playwright.config.ts` runs `npm run start` under `CI=1`, which serves whatever `.next` is
already on disk -- so `CI=1` alone does not build the change, and a brand-new *route* answers
404 while every existing page is fine. All of the new spec file failed at once, which reads as
a destroyed session or a broken fixture and was neither: the file before it was green, most of
its tests failed at the `expect` timeout while one failed in 391ms (a `toBe` against
`undefined` needs no wait), and the data was correct read straight from the database. One
`curl` of the page with the saved session cookie settled it in a second. The CI workflow runs
`npm run build` as its own step; a local judgement has to as well. And stopping the browser
mutation sweep to apply an unrelated change left `composeTree` returning
`orphanLocations: []` -- the same file and the same mutation the rules file already records,
because the harness restores on SIGINT, SIGTERM and SIGHUP and `TaskStop` reaches none of
them. The tell was a modified file this session had never touched.

And the fixture had to grow a day's shape to render it. The access seed was one entry a day at
mid-morning, which draws a single bar -- a chart with one bar demonstrates nothing, which is
this repository's own rule about a fixture carrying one of a kind, met here with none. The
seeded day now has an evening peak with its peak-tier neighbour, a middle tier and a quiet
morning hour, written as UTC instants at the club's local hours so the e2e assertion is about
a *rendered value* rather than about the timezone being named: `19:00` carries ten and `16:00`
carries nothing, in a club that is UTC+3. That is the schedule board's defect asserted against
rather than reasoned about.

**MOD-018's board is the period lock, made visible for the first time.** A closed period
refuses a posting and `closing` admits the close's own entries and no trade at all, so an
accountant beginning a month-end close is deliberately stopping that entity's till -- and
nothing in the product told anybody, because neither the periods nor the chart could be
listed. Two reads closed that, and four decisions carry the board:

  * **`admits_trade` is derived by the server, not by each reader.** `closing` is the state
    that surprises, and a surface reasoning from `status` alone gets the one case that matters
    wrong.
  * **A month that is not listed has never been opened**, which is not the same as being open.
    The lock is per period row, so a tenant whose later books are filed has no row for any
    earlier month; a board that listed twelve months would be inventing eleven.
  * **Both the entity and the currency are derived.** A trial balance is per legal entity and
    per currency, and the first version of the block said so in its own lead and then rendered
    only the currency -- the defect the sentence warns about, on the page that warns about it.
    Naming the entity needs `tenancy.organization.read`, which an accountant may not hold, so
    the name is looked up when it can be and the id is shown when it cannot.
  * **A retired account stays on the trial balance and is marked.** It has to stay, because a
    retired account with a balance is exactly the row somebody needs to notice; unmarked, it
    reads as a live one. The first version dropped the status the read already carried.

**And there is no journal on that page and no route to list one**, which is the gap MOD-018
discloses about itself being respected rather than closed in the wrong direction: a lateral
read around `finance.invoice.read` is safe only while journal ids cannot be enumerated.

**The fixture seeds the chart before the invoice, and the ordering is the evidence.** MOD-018's
bridge runs inside MOD-017's transaction, so an invoice issued with no chart is posted nowhere
-- `post_invoice` returns `ledger_skipped_because` rather than refusing, precisely so a tenant
mid-setup does not find its till has stopped working. With the chart first, an invoice and a
payment produce a trial balance an accountant can check by hand: `provider_clearing` debited by
what the card paid, revenue and tax credited by what the invoice said, receivable back to zero.
Two periods, because the invoice is back-dated ninety days and the payment is today.

**And a second money formatter was written and deleted in the same change.** `money()` took
`Intl`'s own currency exponent, divided by it and formatted with `Intl.NumberFormat` -- a
second implementation of money rendering, in the one place this repository already has a
*cross-runtime* parity test. `tests/unit/conventions-parity.test.mjs` spawns Python and
compares `src/i18n/conventions.mjs` against `backend/app/l10n/conventions.py` character for
character, bidi controls included, because the design system requires numerals "applied
identically on screen, receipt, export and PDF" and a receipt is rendered by the backend. Two
implementations pass their own tests forever while drifting apart -- which is the argument this
same change wrote into `list_entitlement_grants` about `balance_of` versus a `sum()` in SQL,
one file over. It delegates to `formatMoney` now, with `latn` because the numeral system is a
tenant setting this build does not carry, and a fallback for a currency outside the supported
table rather than a 500 on a member's record. **Found by reading the test directory, not by a
failure**: `Intl` and `formatMoney` agree on JOD's three minor digits, so every assertion
passed either way.

**Looking at the rendered blocks found two more.** `.facts` is a two-column grid whose items
are the `dt` and the `dd` themselves, so wrapping each pair in a `<div>` -- valid HTML, and the
obvious way to group them -- makes the div the grid item and puts both labels on one row with
their values beneath. No assertion about text can see that, so the test asserts the geometry:
the second label's box is below the first's, not beside it. And the invoice was due the day it
was issued, because the fixture set both dates to the same value, so the "due" caption repeated
the date above it; a payment term of zero is a real `payment_terms_days` value and not the one
anybody means.

**And looking at it found a defect nothing else would have.** The page now carries two
human-facing member numbers: MOD-014's `ppl_member_profiles.member_number` on the profile and
MOD-017's `mem_memberships.membership_number` on the agreement. Nothing in this build relates
them, both are the kind of number a member reads out at a front desk, and the first version of
the fixture gave them the same value -- which hid it. They are rendered as different numbers
with a caption saying so. The test that proves no MOD-017 data leaks to a refused reader
initially asserted the *wrong* number and failed for that reason, which is the confusion
arriving in the evidence before it could arrive in the product.

**The staff list is the first screen that composes three planes, and building it found a
control nobody could reach.** ADM-STF-01 draws four columns and they live in three schemas
under three roles: the staff profile is MOD-014's in `plt01`, the role is MOD-008's and the
login is MOD-007's, both in `iam`, which `veyro_cp_app` holds nothing in. So the page asks
three gates and composes -- the Member 360's pattern, for the stronger reason that a reader
may hold any subset, and a refused half says it was refused rather than rendering an empty
cell. Both new reads are **batched**, because fifty rows asking one at a time is the
round-trip problem `/authz/checks` exists for.

**The design states the LAST SEEN column's purpose and it is a control, not a timestamp**:
"last seen exists so a departed employee with a live login is visible rather than discovered."
Putting the two halves together is what showed that **nothing in this build could offboard
anybody** -- `iam.identities.status` was read by four controls and written by nothing, so the
board could name a problem the product could not act on. That is in MOD-007's notes above; the
surface's half is that the warning box the canvas fills with a certification expiry (there are
no certifications here) now carries the finding the design's own footnote names, with real
data behind it.

Three things on these two screens are refusals rather than omissions, and each is in this
file's recurring shapes. There is **no Invite button and no third chip**: no invitation exists
in this build at all, and `Invited · 0` would say nobody has been invited rather than that
nothing can invite anybody. There are **no unticked grant rows**: the canvas draws two
capabilities its subject lacks, which implies a candidate set, and here a permission exists if
a role carries it -- so "what somebody could have" is the whole 207-entry catalogue and
picking two would be inventing the product's idea of a sensitive capability. And **"a club
manager sees only their own club's staff" is not true here**, said on the screen, because
`permit` resolves tenant-wide.

**The screenshot pass found a defect in every grid in the app.** `DataGrid` has said from the
start that "a droppable value is in the DOM twice and visible once -- the stylesheet shows
exactly one at any width", and below 600px it showed both: `.ds-col-p2 { display: none }` is
specificity (0,1,0) and the rule that turns the table into a list,
`.ds-grid-table td { display: block }`, is (0,1,1) and comes after it. Twenty-one duplicated
values on the members list, twenty-one on the payments ledger, twelve on the staff list -- the
whole priority-collapse mechanism inoperative at the one width it exists for, for as long as it
has existed. Nothing in four layers could see it: an assertion about text matches either copy,
a component test renders without the media query, and the phone sweep measures horizontal
scroll, which a duplicate does not cause. `phone.spec.ts` asserts the property on three grids
now. **And `/permissions` overflowed by 125px** once the fixture added a role, because the
matrix's width is a count rather than a layout -- two causes, a table box pinned to its
container so its scroll wrapper had nothing to scroll, and a genuine scroll container whose
overflow still reached the document root until `contain: layout` stopped it.

**Five more defects were found by reading the rendered page and none by a failing test**, which
is this surface's own standing lesson for the fifth time. The worst was that the grants block
asked the permission simulator about **one** scope: `permissions_of` lets a broad assignment
cover a narrow scope and never the reverse, so every narrowly scoped grant -- which is exactly
what "beyond their role" means -- was invisible in the block built to show it. The others were
two level-1 headings (a `PageHeader` over a `RecordHeader`, which axe does not flag while a
screen reader reads two documents), a header figure that disagreed with the table under it by
two, a `role_key` printed beside its own display name, and an explanation gated on a condition
that is always true, so it explained a row that was usually absent. **And my first evidence
for the scope defect was wrong** -- the fixture's narrow grant was missing because it was
`routine`, a right answer for a different reason -- so the mechanism is now asserted by two
backend tests instead of reasoned about, which is "a theory that explains a failure is not the
cause of it" met again.

**The account page is the first screen in this app that writes, and which four writes it is
was decided by the gate rather than chosen.** Every other surface here is read-only because
every `tenancy.*`, `config.*`, `catalog.*` and `finance.*` write is a stepped-up financial
permission, so a form for one is a form whose first act is a step-up. MOD-007's identity
routes are the exception: `owned(session, identity_id)` refuses any subject that is not the
session's own with a 404, so there is **nothing to authorize** -- which is also why the
navigation entry is unconditional rather than gated, and why these are the four writes a
member can be given without inventing an approval flow.

Four decisions carry it, and the first is the reason the page is a client component at all:

- **A batch of recovery codes exists in one HTTP response and nowhere else**, because MOD-007
  stores only a hash. A redirect would lose it, and carrying it in a query string or a cookie
  to survive one would be writing permanent credentials into somewhere a browser keeps things.
  `useActionState` renders it in place, once, and the page says that out loud -- a reader who
  assumed the codes could be fetched again would write none of them down.
- **The button is offered only where the server would accept it.** `_issue_codes_in_tx` takes
  the current password or a stepped-up session and deliberately *not* the recovery allowance
  `set_password` has, because MOD-007's second review found a stolen recovery session minting
  ten fresh codes with no password and those codes surviving the owner's own reset. So
  `mayIssueRecoveryCodes` is `aal >= 2` and a level-1 session is told what it needs rather
  than shown a button that fails.
- **A live session is two facts.** Revoked is explicit, expired is a comparison, and a board
  reading only the flag lists a fortnight-old session as open. The bound and the filter went
  on the **server** -- `list_sessions` takes `limit` and `live_only` now, with
  `SESSION_PAGE = 50` -- because a client that fetched everything and sliced would still have
  carried every device a member has ever signed in from across the wire. The page was 13,542
  pixels tall before that and is 3,923 after it.
- **The decisions import nothing, and that is not tidiness.** The first version put them beside
  the fetchers, which reach `@/lib/api` and therefore `next/headers`; a client component that
  imports a module touching `next/headers` fails the build, so **the login page started
  answering 500**. `account.ts` (decisions, no imports) and `account-reads.ts` (I/O) is the
  split the backend makes between `domain` and `service`, arrived at the hard way.

**And the fixture grew a fourth identity for it.** This repository already records three
tests whose green depended on how many times the suite had been run, all of them spending a
product budget somebody else needed; minting recovery codes needs a step-up, a step-up spends
a recovery code, and five wrong ones lock the recovery path with nothing in the build to
reset it. So the reissue test signs in as an identity nobody else touches. **The rule is the
one already written down**: a test that consumes a product budget provisions its own.

**The passkey is the fifth write on that page and the first ceremony in this app**, and it is
why `/account` stops being a dead end for a member who runs out of recovery codes. The server
half landed first -- `webauthn.py` verifies an assertion, so a passkey is an authentication
factor and AAL 3 is reachable -- and for one commit the only caller was a test suite, which is
this build's "a writer with no reader" shape in the module whose subject is signing in.
`/account` enrols one and `/login` signs in with one.

Six decisions carry it:

- **The remedy came before the button.** `revoke_passkey` is new, because the only writer of
  `iam.passkeys.revoked_at` was the clone check: a lost authenticator left a credential good
  for a level-3 session for ever, and `passkeys.write` is routine and self-scoped, so the form
  would have written a permanent uncorrectable row on the cheapest permission in the module.
  That is MOD-013's "an irreversible act must not be declarable on a routine permission" and
  ADM-SCH-04's rota withdrawal, met a third time: **the question to ask before building any
  form is what undoes this, and does it exist.** The row stays and recedes rather than
  disappearing, for the reason a redacted field is marked rather than dropped.
- **No CBOR reaches the client either.** `enrolmentPayload` sends what
  `AuthenticatorAttestationResponse.getPublicKey()` returns -- SPKI DER, which `cryptography`
  loads directly -- so a browser without that method is told to use a current one rather than
  enrolling a credential that could never sign in. A client that parsed COSE to be helpful
  would be the attack surface the service refused on purpose.
- **The cookie is written by a server action, which is the whole shape of the sign-in.** The
  session cookie is httpOnly precisely so page JavaScript cannot hold a bearer token, so the
  client runs the ceremony and hands four base64url fields across the boundary.
  `finishPasskeySignIn` writes the cookie and calls `revalidatePath`; the push then fetches a
  layout that knows about it, because a router cache populated before the action ran renders
  the signed-out page with a live session in the jar.
- **The control is absent where the browser cannot ask**, not disabled. `PublicKeyCredential`
  is the feature test and `navigator.credentials` deliberately is not: the latter carries the
  password-manager API too, so checking it reports a browser as capable and then throws at the
  ceremony. It is read through `useSyncExternalStore` so a server render and the first client
  render agree.
- **The listing reads `BE` at 0x08, which is the flag the level follows**, and reading `BS`
  at 0x10 instead was a defect I shipped and then found by reading the two together. Backup
  *eligibility* is set when the credential is created and never changes, and `factor_for` reads
  it; `BS` says whether the credential currently *is* backed up and flips the first time a
  keychain syncs. Nothing updates the column after enrolment, so an eligible-but-unsynced
  credential -- the ordinary state of a platform passkey for its first few seconds -- was listed
  as "Stays on this device, reaches assurance level 3" and then signed in as `passkey_synced` at
  level 2. **The listing's own words are about the level, so the flag behind them has to be the
  one the level is decided by**; the label is "can be synced" rather than "is synced" for the
  same reason, because eligibility is a capability and the present tense would go stale in the
  other direction.
- **Not a `StatusBadge`, and the reason is the design rather than convenience.** Its
  vocabulary is closed over membership, payment, booking and access, and a credential is none
  of them: the nearest word, `Cancelled`, is a membership state, and putting a membership word
  on a passkey is how two screens come to spell one thing two ways. Adding to the vocabulary
  would mean editing the design source to suit the implementation, which is the one thing this
  project forbids outright -- so the state is marked text with its own three words and the gap
  is recorded.

**Its own tests found two defects, and both are shapes this file already records.** The
withdrawal rendered `state.error` and nothing else, so the most consequential control in the
section said nothing when it worked; and once it did say something, the row that withdraws
itself unmounted the button **and the `useActionState` holding the message it had just
produced** -- verbatim MOD-007's `revokeDevice`, which "returned a success message into a page
that no longer had a session to render it on". The state lives at the section now. Nothing
else could have seen it: the row visibly changes state either way, so an assertion about the
row passes with the sentence missing. And the account page told the one session holding the
strongest credential in the product that its level is one nothing can reach, and called its
fifteen minutes "the long window" -- `assuranceMeans` had no branch above 2 and the caption
read the password one. **A gap note outliving its gap, in a sentence shown to the reader it is
about**, which is the schedule board's finding in the module that closed the gap.

**The ceremony is proven against a real authenticator, which is the only honest way.**
`tests/e2e/passkey.spec.ts` drives Chromium's virtual authenticator over CDP -- `ctap2`,
`internal`, resident key, user verification, backup eligibility left false so the credential
is device-bound and reaches level 3 -- so a real key pair signs a real challenge and
`cryptography` verifies it. 9 browser tests, 21 component tests for the options and the
encoding (`navigator.credentials` does not exist in jsdom and faking it would be asserting a
fake), and 10 mutations. **Both halves of the factor distinction are rendered**, because the
authenticator's `defaultBackupEligibility` is a parameter: one test enrols a device-bound
credential and reaches level 3, another enrols a synced one and reaches 2, and until the
second existed "can be synced" was a branch no fixture could reach. The spec signs in for itself rather than adopting the shared cookie,
because it signs out and `playwright/.auth/owner.json` is a file every other spec reads --
and its label carries a per-run suffix, because a credential enrolled here stays enrolled and
asserting on a fixed label resolved to five rows on the fifth local run.

**There is no TestSprite journey for it**, and that is a bound on the layer rather than a gap
in the product: an outside tester cannot be handed a credential that signs, since the only
second factor this surface offers is a single-use recovery code and giving it one would spend
it on the first run. Said rather than fabricated.

**And `tests/setup.ts` gained an app-router stub**, because a client component calling
`useRouter` throws in jsdom -- in the *component*, so three login-form tests went red the hour
the sign-in page grew a passkey button, for a reason that has nothing to do with what they
assert. It is a stub and not a fake: `push` navigates nowhere, because a component test
asserting a navigation would be asserting Next's behaviour, and the one place that is worth
proving is a browser against a real server.

**And closing the gap made eight reader-facing sentences false, which CI found one of.** The
step-up page keyed on `reachable`, and that field answers two different questions in two
different modules: `/auth/require/*` computes it from every verifiable factor, so it went true
for level 3, while MOD-008's gate computes it from the two factors `/auth/step-up` accepts, so
it stayed false. The page read the first and started offering a credential prompt whose correct
answer is still refused -- strictly worse than the honest "nobody can do this here" it replaced.
`src/lib/step-up.ts` is the distinction, with a ceiling derived from what the endpoint accepts,
and the action refuses *before* spending the credential, because a recovery code burnt on a
level this route can never reach is "verify, decide, then consume" from the surface's side.

The other eight were sentences, and six of them said the same wrong thing -- **"nothing here
enrols a passkey"**, which `/account` had just falsified. The ninth was on the account page
itself: the recovery-codes lead called a recovery code "the only second factor this build can
verify", directly above the section that enrols one. Correcting it is where `hasUsableKey`
found its reader -- a function I had written and nothing called, which is this change's own
subject in its own new code. What a reader needs there is not which factors exist but whether
*they* have one, because a member with a passkey cannot be locked out by spending ten codes
and a member without one can, so the page asks that question and the section's own banner asks
it through the same function rather than a second copy. The permissions legend told a reader
that break-glass support access is "held by nobody who can use it"; the matrix cell read "Not
available in this build"; the staff record said no session anybody can open holds a level-3
permission; the Member 360's withheld-health marker said the level cannot be reached and that
nothing enrols one. Each is now the honest form: held, and only a passkey sign-in can use it.
**A gap list is a claim about the product, so closing a gap means deleting its note in the same
change** -- and the reach of that is wider than the module's own gap bullets, because the same
claim had been copied into a legend, a table cell, a mask marker, four module docstrings, a
README and five test names.

**The lesson worth carrying is the one boolean.** `reachable` was right in both modules for as
long as level 3 was unreachable by anybody, so every reader of it was right by coincidence. One
field answering two questions is right only while the two agree, and closing a gap is exactly
what pulls them apart: when a capability lands, grep every *reader* of the flag that stood for
its absence, not only the tests that asserted it. MOD-008's field is now narrower than its own
name, which is recorded where it is defined rather than renamed across the gate, the matrix,
the surface and their tests -- and the honest long-term shape is for the endpoint to state its
own reach, since a constant in one client is a fact nothing can check against the server that
owns it.

**The design canvases render, so the comparison is mechanical.** `support.js` is a design
runtime: it resolves every `{{ }}` placeholder and `sc-for` loop against React 18, so a
canvas can be opened in a browser and a screen put beside its own approved drawing.
`web/tests/visual/visual.mjs` does that, and it **classifies rather than lists**, which is the
whole difficulty. The canvases are a sequence and the later ones correct the earlier ones: the
HF Command Center draws its page title at 24px where `TYPE_SCALE` fixes `type.h1` at 26, and
sets 27 small-text elements in `#85807a` where the `CONTRAST` matrix rates that "FAIL under
18.66px on every surface". A raw diff produces findings whose correction would undo the design
system, so an unmatched declaration is a **deviation** only when the token tables sanction it
and is otherwise reported as prototype drift or as a pairing the contrast matrix bars. Thirty-
nine raw differences on ADM-CC-01 became sixteen worth reading, and three of those were real:
the attention queue has two row heights and this had one, staffing escalated to `critical`
where the canvas draws `info`, and the collections breakdown printed a legal entity's UUID
where a name belonged.

**A refusal and a failure are different facts.** `gate` and `gateAll` fail closed -- an
unreachable gate is not permission, which is right for access -- so a transport failure
reaches a page in exactly the shape of a refusal, and twenty-five places said "Not permitted"
for both. `gateVerdict` separates four states: the request got no answer, the assurance is
unreachable in this build, a step-up would open it, or the gate said no. Only the last is
about what the reader holds, and a page that confuses them sends somebody to ask for a grant
they already have.

**A vocabulary the backend stores is never a label.** Four instances in one pass --
`lifecycle_state`, the membership plan words, the wallet's value kinds, a door visit's
credential kind -- each a column's value rendered where a word belongs, and each Latin
letters in the middle of an Arabic line. `MESSAGE_KEYS` cannot see any of them: it compares
the two catalogues against each other and is blind to a string that never became a key.

**TestSprite cannot see anything behind a step-up, and that bounds the layer rather than
the product.** The only second factor *this surface* offers is a single-use recovery code: a
passkey is verifiable on the server now and no page calls the browser API, and TOTP has no
enrolment for want of a vault. So an outside reader can be given no credential that would
raise a session, and handing one to a stored test would spend it on the first run. ADM-MSH-03's journey established the bound by hitting it: it verified the
figure that bounds a freeze reads *without* a step-up, offered to go further, and stopped
exactly where a real reader without a code would. Everything past that wall is the browser
suite's, which holds the password and mints a fresh code per run.

**TestSprite is the independent layer**, and `qa/testsprite/plans.mjs` generates four journeys
from the live fixture. Its value is that it has not read this repository: a Playwright spec and
the page it tests were written by the same hand on the same day. One found a real defect
first -- every name on `/members` reads "Name withheld" at AAL 1 and the step-up that lifts it
was offered on a member's *record* only, so the tester clicked the marker looking for a way
through and there was none. **And then it found the sequel.** Told to open a staff record by
clicking the row, it could not: a withheld name rendered the marker *instead of* the link, so
on an ordinary sign-in -- the front desk's own credential -- the members list and the staff
list were both dead ends and not one row on either could be opened. It went looking for
another way through, found the step-up, and was blocked by a recovery code it had none of.
`WithheldLink` puts the marker inside the link with an accessible name built from what is not
withheld. Twice now, the same reader behaviour against the same cell, and neither time by a
test written here. Two bounds: a run signs in with the fixture's synthetic
credentials through a tunnel, and **a created test carries that tenant's id for ever**, so
re-running the fixture invalidates every test already created.

Known gaps: the surface covers the sign-in, the step-up, the account page, MOD-004, MOD-005,
MOD-007, MOD-008, MOD-009, MOD-010, MOD-011, MOD-012, MOD-013, MOD-014, MOD-016, MOD-017,
MOD-018, MOD-019, MOD-021, MOD-022 and MOD-026, plus MOD-020's roster on a session,
ADM-SCH-04's availability grid at `/rota`, ADM-MSH-07's cancellation sheet at
`/people/{id}?tab=membership&cancel=1`, ADM-MEM-10's walk-in form at
`/members/new`, FD-06's class check-in at `/desk/classes/{id}` and FD-03's denial
resolution at `/desk/denials/{id}`, with FD-08's device strip above both -- the first Front
Desk screens -- ADM-STF-01/02's
staff list and staff record, ADM-PAY-05's
recovery workspace, ADM-PAY-10's dispute board, ADM-RPT-01/02/03/04
under `/reports`, ADM-PAY-07's wallet on a member's billing tab and ADM-MEM-07's attendance
tab, and MOD-026's task list, attention item and resolved board under `/tasks`.
MOD-015 is the one
implemented module with no screen at all, which is the bulk of the remaining work; MOD-019's
own surface is read-only -- publishing a schedule, substituting an instructor and cancelling a
session are all built on the server and none has a form, which is the same gap the hierarchy
has and for the same reason: every one of those writes is stepped-up; the staff screens are
read-only too, and `End access` is the one control there whose server half now exists --
`set_identity_status` is built and tested, and revoking an assignment takes a written reason,
so a form that collects one is a different piece of work from a button;
a step-up spends a recovery code, and the account page's reissue needs a stepped-up session,
so the batch that runs out pays for the step-up that mints the next one with its own last
code -- **and the way out of that is now built rather than named**: a member who enrols a
passkey signs in at level 3 directly, which needs no code at all, and `/account` is where
they enrol it. What is still a dead end is a member who has spent all ten codes *and* has no
passkey, which is the case the section's own warning is about;
every `tenancy.*.write` is a stepped-up
financial permission and none of those forms is built, so the hierarchy and the people surfaces
are read-only; there is no mobile client and no edge agent; and nothing here is deployed
anywhere, which is deliberate while the platform plane is unauthenticated.


**Next.** The standard for a finished module is now the whole stack, not the backend: owner
directive of 2026-11-18, which says in as many words that a module is not complete because its
backend tests pass, and that every applicable frontend, integration and end-to-end requirement
is part of it. (It is cited here in prose and has no file in `knowledge/00-Decisions/`, unlike
the delegation record this file's Authority line names.)

**By that standard no module is finished, and this paragraph used to say MOD-022 was the
exception.** It is not. Every one of the eighteen with a backend implementation carries its own
"Known gaps, deliberate" list -- unmet requirements on the *server* plane, before the frontend
question arises -- and MOD-022's runs to nine entries: nothing opens a door, occupancy cannot
enforce a capacity policy, no anti-tailgating, no video, no visitor management, no mobile
credential, an offline decision is judged rather than prevented, eleven free-text columns are
beyond any erasure, and the member timeline knows none of it. What was true of MOD-022 is
narrower and worth keeping: it is the one module whose *surface* was built in the same stretch
as its backend, which is why it reads as finished to anybody counting screens.

**And the per-module frontend verdict is not derivable from this repository at all**, which is
why the claim went unchallenged for so long. `contracts/ui/screen-contracts.yaml` carries 170
specified V1 screens and leaves `owning_module` null for every one of them -- its own
`unresolved_policy` says no owning implementation module has been inferred, and that null is
not a pass. So nothing maps a screen to a module, and any statement of the form "module X's
frontend is complete" is an assertion about a mapping that does not exist here. What the
artefacts do support is per *surface*: `design:coverage` reports 43 screens in the inventory
across Admin and Front Desk, 12 blocked on something external and 29 in the backlog, and
Member, Coach, Console and POS have no implementation at all. **Closing this honestly means
resolving the mapping before claiming a module is done**, not counting routes -- and the
backlog is now the half of that mapping which exists: every unbuilt screen on those two
surfaces names the module that owns it, checked against the catalogue, so the modules with
Admin and Front Desk screens still owed are MOD-027 (8), MOD-055 (3), MOD-058 (1) and
MOD-059 (1), plus 15 screens that are work inside modules already built. **MOD-026 came off
that list by building its three**, which is the first time a module has: its backlog entries
had been rewritten twice as the slices landed, because the check validates the module id and
cannot read the sentence beside it.

So "implemented" above is accurate about the server plane and incomplete about the product
everywhere, and the backlog has two halves.

The first is the screens the eighteen built modules do not have. `web/` covers the sign-in, the
step-up, the account page, MOD-004, MOD-005, MOD-007, MOD-008, MOD-009, MOD-010, MOD-011,
MOD-012, MOD-013, MOD-014, MOD-016, MOD-017, MOD-018, MOD-019, MOD-020's roster, MOD-021 and
MOD-022, and the staff list and record ADM-STF-01/02 specify -- so **MOD-015 is the only
implemented module with no screen at all**;
`contracts/ui/screen-contracts.yaml` names the rest.

**And MOD-015's screens are not Admin screens, which changes what "next" means.** This
sentence used to call them the bulk of the remaining work; they are the *Console* surface --
CON-06 subscription and entitlements, CON-07 usage and metering, CON-13 tenant billing and
dunning -- and the Console is the platform operator's, on the plane that has no
authentication at all. A UI there is a UI over a surface where anybody who can reach it can
**suspend or archive a live customer's tenant**, so the screens are behind CON-16 rather than
beside it. **And CON-16 is specified in a way this build cannot satisfy**: "No password
field. SSO with hardware-key MFA, and it is not optional. This is the account that can reach
every customer's data -- it gets the strongest door in the product." Both halves are unbuilt
-- IAM-01-R04's OIDC/SAML federation, and the hardware factor AAL 3 needs, which needs the
WebAuthn verification MOD-007 refuses to hand-roll. A console sign-in with a password would
be substituting a weaker screen for the one the design draws, on the one account the design
says must have the strongest door.

**WebAuthn verification is built now, and it was half of that wall.** `passkey_hardware` is a
verifiable factor, AAL 3 is reachable, and break-glass support access and AI acting for a
member are exercisable for the first time -- so what blocks the Console is the *other* half:
IAM-01-R04's OIDC/SAML federation, which is unbuilt. That is the piece whose absence now costs
the most on this surface. MOD-021's device identity is a separate wall and unmoved: a device
certificate is mTLS and a signature nothing here makes, which is the vault rather than
WebAuthn, and MOD-022 still opens doors on an identity nothing verifies.

**The Front desk is where the reclassification bites hardest**, nine screens whose modules
are all built and all on the authenticated tenant plane. Three are built: FD-03 denial resolution and
FD-08's device strip are MOD-022's and MOD-021's, FD-06 class check-in is MOD-020's. Six
are not: FD-01 live check-in is MOD-022's, FD-02 member lookup is MOD-014's (and now its
contact-match read), FD-04 day pass and FD-05 walk-in trial are sales, FD-07 shift open and
close is MOD-018's cash sessions, which `/payments/cash` already answers from the Admin
side. **`design:coverage` holds this surface to the Admin one's standard now**, so each of
those six carries a written reason -- and under the external-blocker rule only two of them
are blockers. **FD-01 and FD-04 are payments at the door**, which is the provider the owner
supplies. The other four are this session's work and were mislabelled: FD-02's search is a
gated, masked read over `ppl_contact_points_by_value`, and calling it ENG-01's was an
architecture decision of mine rather than a constraint (only its 44px photo wants the object
store); FD-05 is CRM, and building CRM is delegated, though it does need a trial state
`mem_memberships` has no value for and its invitation waits on the messaging provider; **FD-07
needs nothing from anybody** -- the count, the expected figure and the variance are already
`/payments/cash`, and the handover note the canvas calls the point of the screen is a migration
and a form; and FD-09's service worker and write queue are weeks of work and still work. The
day-pass half of FD-04 is mine too: `PRODUCT_TYPES` already carries `session_credit` and
`service`, so "there is no day-pass product" described configuration as a capability gap.

**Of the specified Admin screens with no route, the ones with reads behind them are what to
build next.** That audit is a **check** now rather than a count somebody re-derives, because
doing it by hand gave a different answer each time: `web/src/design/coverage.mjs`, in
`design:check` and therefore in CI, requires every specified screen on a covered surface to be
named in `contracts/ui/design-compliance.md`, mapped to a screen it is a *state* of, blocked
on one of the eight external causes, or put in the backlog under the module whose work it is.
**"Not built yet" is not a cause and there is deliberately no token for it**, which is
`GateCoverageTests.UNGATED`'s discipline one layer up: adding to either list is meant to be
uncomfortable.

It reads **90 specified screens on Admin and Front desk: 40 in the inventory, 6 states of
those, 12 blocked on something external, 32 in the backlog**, and it names the five surfaces
it does *not* cover with their counts. It checks both directions -- a reason for a screen the inventory now argues is a
stale excuse and fails, which is the schedule board's "gap note that outlived its gap" caught
structurally. My own hand audit had said 43 were missing; the truth was that most were built,
mislabelled or states, and the number that is genuinely unaccounted for is zero.

**It covered one surface of eight, and it counted a mention as a claim.** Two findings about
the check itself, both of shapes this file records one layer down. `surface === "Admin"` left
the nine Front Desk screens needing no row and no reason -- a prefix-scoped sweep, in the one
place here where a gap list was not a claim about the product. And `named` asked whether the
inventory *contained* the id anywhere, so a design-sources row (`| `Veyro HF Front Desk and
POS` | FD-01, POS-01 |`), a cross-reference in another screen's "still open" list, and a bold
paragraph arguing a screen is **not** built all read as coverage. **Thirteen screens were
accounted for that way** -- seven Admin and six Front Desk -- including `ADM-SCH-06`, which
this check's own docstring calls the worked example of `data:` and which had no reason in it
at all. A claim is now one of the three shapes the document actually commits in: a fidelity
table row, a section heading, or a per-screen bullet carrying its route. A prose paragraph is
deliberately not one, because "we wrote about why this is missing" must stay distinguishable
from "we built it".

Two smaller things came out of tightening it, and the first is the trap this file warns about
in the other direction: the id pattern allowed three letters in the middle segment, so
`ADM-AUTH-01` and `ADM-AUTH-02` -- both built, both in the table -- were reported missing, and
**a check that reports a defect the app does not have costs the same trust as one that misses a
defect it does**. And narrowing `COVERED` back to Admin now *fails*, because the Front Desk
reasons would be orphaned: the both-directions rule applied to the check's own scope, which is
what stops the scope being quietly narrowed again. **ADM-SCH-04 came off the list by writing the read it needed**, and the
read was the finding: `set_availability` had had a writer and no reader since MOD-019 was
built, so a rota could be set and the only way to learn what it said was to publish a template
against it and read the refusal. `/rota` is also where the standing claim that every form here
is blocked turned out to be wrong -- `scheduling.availability.write` is routine, so the
design's "Add an exception" is buildable today. **ADM-SCH-06 did not come off it**, and for a
reason worth recording: the canvas draws capacity and equipment columns, `sch_resources` has
`quantity` -- how many of a thing there are -- and capacity lives on a template's own policy,
so the screen as drawn would have one real column and two invented ones.
**ADM-MEM-10 came off that list the same way, and the read it needed is the one worth
naming**: `find_duplicates` scores pairs that already exist, so the moment a duplicate is
cheapest to prevent had nothing to ask, and the index that would answer it has been in
MOD-014's schema since the module was built. It is also where **ADM-MEM-05's own missing
"Add member" button** surfaced -- specified in that canvas's header, rendered nowhere, and
absent from that screen's gap list too, so nothing in the repository recorded that a
specified control was missing.
**ADM-RPT-04 came off that list by writing the read it needed**, and the
interesting half was deciding what *not* to answer: `GET /reports/attendance` buckets entries
into a club's own local hours over complete local days of a caller-chosen day set, and
`app/access/attendance.py` derives the busiest window and the quietest attended hour, which is
the canvas's own requirement rather than a styling note. What it refuses is the canvas's
"94% of floor capacity": a capacity figure exists and is not this chart's denominator, because
entries in an hour are arrivals rather than people inside at a moment and occupancy here is
advisory unless a zone reads both directions. **ADM-STF-01/02 came off that list, and found a
defect doing it.** The three
reads it needed are each on the plane that owns the fact -- `GET /staff` for the employment
half, `GET /authz/assignments` (batched) for the role, `GET /identities/last-seen` for the
login -- and composing the last two is what the design's own footnote asks for: "last seen
exists so a departed employee with a live login is visible rather than discovered." Putting
them together showed that **nothing in this build could offboard anybody**: four controls read
`iam.identities.status` and no code path wrote it, so the board could name a problem the
product could not act on. `POST /identities/{id}/status` is the writer and
`product/0003_identity_status.sql` is the evidence its `auth_events` kind needed. **ADM-PAY-05
came off that list by writing the reads it
needed**, which is the shape the rest of them take: `collections.recovery_treatment` sorts the
failed payments the canvas calls one decision, `GET /finance/recovery` pairs each case with
the failure that opened it and the membership its invoice cites, and
`GET /notifications/templates/published` gave MOD-013's template body its first reader -- the
listing omits it, so the text had been unreadable anywhere in the build. **ADM-PAY-10 came
off it the same way**: `GET /finance/disputes` (the module had three dispute writers and no
reader at all), `GET /access/attendance/window` for the check-in record a chargeback is
answered with, and a routine `finance.dispute.read` beside the financial write -- MOD-018's
rule, because a read behind a step-up is a read nobody does until the window has expired. ADM-RPT-05's export gate, ADM-STF-03's invitation and every
`tenancy.*`/`catalog.*`/`finance.*` form are blocked on the same thing: each is a stepped-up
financial write with no form in this app, and a button that answered 403 is worse than its
absence. The rest need modules this repository does not have (CRM, automation, search) --
**tasks came off that list**, because MOD-026 exists and its three screens are built.

Within those, the work is per module rather than per screen, because each one needs its gate,
its masked fields and its failure states wired the way those are. The second is the modules
themselves. **MOD-026 is built, R01 to R07 with its screens** -- see its entry above -- so the
three Admin screens that waited on it are done and it is the first module in this build whose
backlog entries came off `design:coverage` by being satisfied rather than rewritten. It was
chosen by dependency order rather than by screen count: MOD-027, MOD-047 and MOD-055 all depend
on it. The one requirement fragment with nothing to point at is R04's payroll action class,
which waits on a payroll module this build does not have: a policy naming it would be a policy
for an action nothing can perform.

**MOD-027 is next and its design record is written**:
`knowledge/00-Decisions/ADR-0010-mod027-crm-lead-pipeline-and-trial.md`. It is unblocked --
MOD-013, MOD-014 and MOD-026 are its dependencies and all three are built -- and eight
backlogged Admin screens are its, more than any other module's. Four things that record
settles, because the canvas is unusually explicit about them:

- **A lead, a trialist and a member are one `ppl_persons` row**, which the canvas states as a
  structural requirement rather than a preference: "a lead, a trialist and a member are one
  record at three stages, never three records". So MOD-027 owns the pipeline and MOD-014 keeps
  owning the person, and ADM-CRM-04's phone duplicate check is `GET /people/contact-match`,
  which exists.
- **A trial is an `active` membership on a trial product**, not a CRM clock and not a new
  status: "a real member record from the start -- access pass, app login, class booking
  rights" is only true if the ordinary readers treat it as live, and a `trial` status would be
  a new value MOD-022, MOD-020 and MOD-017's own lifecycle would all have to learn.
- **Converting it is MOD-017's `upgrade`**, which is where checking the record against the
  code found the gap two sections up: eight of thirteen declared change kinds have no writer,
  `upgrade` among them. So the conversion is MOD-017's work and MOD-027's slice 2 depends on
  it.
- **Lost is reversible, which is the opposite of MOD-026's case.** A case moves forward only
  and a problem that returns is a new case; a lost lead is re-contacted on the same record,
  because a new one would defeat the first point.

MOD-023 (Coach Workspace, which needs MOD-014 and MOD-008, both
built) unblocks nothing and so comes after it. MOD-006 is the Compose Multiplatform
qualification, which is a client-side proof the server plane does not need and the mobile half
does.

Two things named rather than done remain open across the build: the platform plane is
unauthenticated -- and MOD-012 makes that worse, since the definition catalogue decides which
scopes a tenant may hand to a third party -- and there is no key vault, which is what
MOD-009's crypto-shred, MOD-007's TOTP seeds, MOD-012's inbound webhook signatures and
MOD-021's device certificates are all waiting on. **The vault is the one that has moved from
inconvenient to load-bearing**: MOD-021 enrols a credential it cannot verify a signature
against, so a device's identity is a fingerprint somebody recorded rather than a key anything
checks -- and MOD-022 now opens doors on that identity. **WebAuthn verification does not touch
this**, and the distinction is worth keeping straight: a passkey's private key never leaves
the user's authenticator, so verifying an assertion needs no secret of ours at all, which is
exactly why that gap could be closed while this one cannot. A device certificate is the
opposite shape -- it is a secret this build would have to hold.

**The worker runtime is no longer on that list, and ten of the fifteen schedules are
driven.**
`backend/app/worker/` has its own section above. What closing it took is worth the same note
`Decision.mask` gets below: no new table, because every wired job is idempotent and a durable
schedule's real cost is a second place where "has this run" is recorded that can disagree with
the effect the job had. The five schedules still undriven are undriven for a reason each, and
**exactly one of those reasons is a blocker**: MOD-009's retention sweep waits on the owner's
retention policy. The rest are work. `iam.challenges` has no DELETE grant for anybody, which
is a grant decision to make here rather than an obstacle; `deliver_pending` has no handler to
drive, which is a handler to write; and MOD-017's renewals and MOD-018's recognition want a
cadence decided and recorded, which the delegation covers. **MOD-011's objective evaluation
came off that list by making its decision**, and the shape is worth knowing before the next:
the judgement it looked like it needed (which objective is due) did not exist, and the one it
really needed (how often a breach is announced) was a different and smaller question.
**MOD-026's SLA sweep is the third of those**: a target is a number of seconds somebody wrote
on the row, so there was no deadline to decide at all -- what was missing was a reader.

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

**The recurring lesson across the last five reviews, stated once.** Every module since MOD-011
has shipped at least one control keyed on a value the caller supplies, shape-checked and never
checked for correspondence with anything. MOD-016 shipped four of them and two were worse than
the earlier ones: a separation of duties that no stricter check could have rescued, because
there was no second act to compare against, and a usage limit whose counter was never moved by
the act it bounded. **The question to ask of any control is not "is this field validated" but
"what did the server derive, and did the thing I am bounding write the state I am reading".**

MOD-017 shipped four more, and one of them is the first in this build where the *argument for*
the shortcut was written down and was wrong. Publishing a contract version in one command was
defended in a docstring -- a draft could be signed against with nobody having approved the
terms -- and `create_agreement` resolves only a published version, so a draft was unsignable by
construction. **The defence was checkable against the code in the same module and nobody
checked it.** So the question above has a companion: when a module explains why it collapsed
two acts into one, read the other act and see whether the danger it names is reachable at all.

MOD-020 shipped four more, and added a second kind of defect that is worth naming beside them:
**a declared state, reason or occasion that nothing in the build ever writes.** `released` and
`session_cancelled` were both declared and both documented as existing so that a member does
not get a strike for a class the gym called off, and the code path that should have written
them ran the ordinary no-show path instead -- so every member of every cancelled class was
recorded absent, with a fee and a strike, permanently. `withdrawn` was the same shape with a
smaller cost, `waitlist_full` and `ineligible` and `no_entitlement` were declared denial
reasons nothing produced, and `expired -> waiting` was a declared edge nothing took. **An
enumeration is a claim about what the software does**, so the question to ask of every declared
value is not "is this reachable in principle" but "grep the writers: which line puts this
value in the column". A value with no writer is either a gap to disclose or a defect wearing a
design decision's clothes, and in MOD-020 it was four of each.

MOD-022 shipped four more of the first kind and one of the second, and added a third shape
that is worth naming because it is the one a careful reader is most likely to produce: **a
control applied to the explanation rather than to the fact.** The decision receipt splits a
public line from a private reason exactly as paragraph 1944 asks, and five denial codes are
required by constraint to carry the discreet public line -- and the real `code` was returned
beside it, in the field a surface actually renders. Both reviewers found it independently.
Nothing was unvalidated, nothing was caller-supplied, and the module's own tests asserted the
masking they were written for; the mask was simply on the prose and the enumeration went out
in the clear. **So the question to ask of any disclosure control is not "is the sensitive
text masked" but "what else in this response answers the same question".**

And MOD-022's largest finding was not in the code at all. Its schema carried ninety-eight
rules and seven behavioural cases, and no mutation sweep had ever been run against it -- the
"20/20 mutations caught" it shipped with was a Python sweep over the decision modules, which
is a different half of the system. A reviewer dropped all 73 CHECK constraints one at a time
and the suite caught seven; dropped all 25 keys and indexes and it caught none; replaced five
of the ten trigger functions with `BEGIN RETURN NEW; END` and it reported 109/109. Nothing in
the shipped schema was wrong. **A module's evidence is a deliverable with its own failure
mode, and the only thing that measures it is breaking the rules on purpose and watching.**

Module ids are in `tools/mission_runner/module_catalog.json` and are not the TSD's section order.
MOD-006 (Compose Multiplatform qualification) is unbuilt; MOD-007's dependency on it is a
client-side proof that the server plane does not need.

Finish a module's real requirements and tests, then move on.

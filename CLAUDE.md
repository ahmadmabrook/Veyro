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
backend/migrations/     platform/ and tenant/ SQL, applied in filename order
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

**The two planes are separate.** `veyro_cp_app` holds privileges in `plt01` and nothing on the
tenant registry; `veyro_cp_platform` holds the registry and nothing in `plt01`. Neither is a member
of the other — never write `GRANT <role> TO <role>`. Neither runtime role may hold `TRUNCATE` or
`REFERENCES`, and `veyro_cp_app` may not hold `DELETE`.

**Negative tests must actually fail closed.** A test that still passes when you remove the
protection is not evidence. Every isolation check in `backend/tests/sql/isolation.sql` has been run
against a deliberate mutation and shown to fail; a new one earns its place the same way. This
caught a weak check already: an earlier "the app role cannot DELETE" test passed only because a
foreign key refused the delete first.

**Also binding:** authentication and AAL-3 (MOD-002, not yet wired in), immutable audit,
financial correctness, residency and retention. Validate input at trust boundaries. Historical
review outcomes and the preserved evidence trees outside the repository are never rewritten.

**Owner-reserved**, on the owner's standing instruction and never inferred: real financial
expenditure, production deployment, real member data, and anything needing the owner's personal
authentication. `governance/registry.json` `reserved_actions` keeps the four names.

## State

**MOD-004 (tenancy control plane) — implemented, not accepted.** Working: the `plt01_platform`
registry with tenant lifecycle and append-only history, idempotent provisioning, the `plt01`
organization/legal-entity/brand/location hierarchy under forced RLS, and an HTTP surface over
both planes. Proven: 13 isolation checks, each mutation-tested.

Known gaps, deliberate and worth reading before extending:

- **No authentication.** `X-Veyro-Tenant` is a claim, shape-checked and nothing more. Isolation
  does not depend on it being honest, but authorization does not exist yet. MOD-002 owns it.
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

**Next:** MOD-005 onward. Finish a module's real requirements and tests, then move on.

## Tooling that still earns its place

- `tools/migration_lint/migration_lint.py lint --track tenant|platform --tests-root backend/tests/sql <files>`
  — static checks on migration SQL. **Run it on every new migration.** It is strict and useful: it
  refused the hierarchy migration until `legal_entities` had a real negative test. It reads SQL
  only and asserts nothing about a live cluster; `verify_db.sh` is the live half.
- `python3 tools/governance/governance_check.py check --root .` — structural check; mainly catches
  drift between `PROJECT_INDEX.md` and `governance/registry.json`. CI runs it. It is not a gate on
  your work, but keep it green.
- `node tools/screen_contracts/screen_contracts.mjs check-identity` — screen registry identity.
  `check-complete` fails by design (1530 per-screen fields deferred to the owning product modules).
- `tools/mission_runner/` is retired as an execution path — its launchd services are stopped and
  it must not be restarted or rebuilt — but it is tracked code whose tests CI runs. Leave it.

## Workflow

Smallest reviewable change. Match the surrounding code's naming and comment density. Run the
checks above, then commit and push to `main` — no force, no history rewrite. Confirm CI is green
on the pushed commit:

```bash
gh run list --commit "$(git rev-parse HEAD)" --json headSha,databaseId,conclusion,event
```

Look for `event` `push`, a matching `headSha` and `conclusion` `success`. A green run on another
SHA proves nothing. If it fails, repair forward or revert; never force-push, and do not stack work
on a red `main`.

Use an independent review for genuinely risky work — tenant isolation, authentication, money,
anything whose failure is silent. Not for prose. Do not open a review loop on documentation.

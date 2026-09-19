<!-- Target path once applied: .claude/rules/backend/architecture.md -->

# Rule: Backend Modular-Monolith Architecture Boundaries (`backend/**/*.py` binding)

Authored 2026-09-19 (MOD-001, `ADR-005` Decision 2 binding pre-implementation
condition — "Before implementation work begins at `infra/**`, CI, or
`backend/**`: the two profiles' agents and rule families must exist with
real content," see
`knowledge/04-Decisions/ADR-005-mod001-critical-slice-and-surface-profile-routing.md`).
Grounded directly in EIP §4.3's Backend/API profile row
(`EIP_MIRROR.md` lines 1270-1277: "backend/**/*.py — FastAPI/Pydantic
boundaries; modular-monolith/domain ownership; business logic outside
routers; ... clean, testable layers without pattern cargo-cult"), TSD
§1.2/§2.2 (`TSD_MIRROR.md` lines 565-567, 636-647: "No domain reads or
writes another domain's tables directly. Cross-domain collaboration uses
application contracts, read models or events" / `DOM-001`), and TSD
§24.1's module dependency/SQL lint (`TSD_MIRROR.md` lines 11603-11608) —
read directly this session from the owner-produced mirrors, not from a
secondhand citation. Per this project's own convention
(`REQUIREMENTS.md` §0), the governing `.docx` wins over this
mirror-sourced text on any conflict.

This rule is active now for whatever real Python backend code MOD-001
itself writes (scaffold, the tenant-isolation/RLS and migration-safety
harnesses, `app/main.py`, `alembic/`) and binds forward to every later
domain module that adds real per-aggregate business logic under
`backend/**`. Per `ADR-005` Decision 2, Backend-profile activation is
bounded to the scaffold/harness code MOD-001 actually writes; the
profile's per-aggregate behaviors are inherited by MOD-002+, not
satisfied by MOD-001 itself.

## Required controls for `backend/**/*.py`

1. **One sub-package per owned domain.** Each business domain owns
   exactly one sub-package under `app/modules/<domain>/` (e.g.
   `app/modules/membership/`, `app/modules/booking/`). A domain's own
   database tables and ORM models are private to that sub-package — no
   other module may import them directly. Violating this is the exact
   condition the module dependency/SQL lint gate (TSD §24.1) denies as
   `CROSS_DOMAIN_SQL_IMPORT`, citing the importing/imported module pair.

2. **Cross-domain collaboration is contract-only.** A module may
   interact with another domain only through that domain's own
   published application-service interface (an explicit, importable
   function/class the owning module exports for this purpose) or
   through domain events it publishes/consumes — never raw SQL or a
   direct ORM query against another module's tables (TSD §1.2: "No
   domain reads or writes another domain's tables directly.
   Cross-domain collaboration uses application contracts, read models
   or events"; `DOM-001`).

3. **`app/modules/_shared/` holds only domain-free code.**
   Cross-cutting infrastructure with no single owning domain (auth
   middleware, the tenant-context resolver, generic typed-error base
   classes) may live in `app/modules/_shared/`. Business logic owned by
   a specific domain may not be placed there, and no module may use
   `_shared/` as an indirect route to another domain's private
   internals — the same import restriction in control 1 applies to
   anything actually re-exported from `_shared/`.

4. **The TSD §6.3 bidirectional-pair exception is narrow and
   TSD-controlled.** TSD §24.1 names exactly four intentional
   bidirectional module pairs where one synchronous, directed edge may
   import the opposite module's application interface, while the
   reverse edge must stay event-driven — "§6.3 is the normative
   directed graph: only the listed synchronous edge may import/call the
   opposite application interface; the reverse edge must remain
   event-driven" (`TSD_MIRROR.md` lines 11606-11608). This rule does not
   enumerate the four pairs here; TSD §6.3 itself is the controlling
   source for which pairs and which directed edge qualify, and it wins
   on any conflict with a restatement here. Until a specific module
   boundary is confirmed as one of the §6.3-listed pairs, treat controls
   1-3 above as applying without exception — the reverse (event-driven)
   edge of a §6.3 pair, or any synchronous cross-domain import outside
   the §6.3 list, fails the gate as `REVERSE_EDGE_NOT_EVENT_DRIVEN` or
   `CROSS_DOMAIN_SQL_IMPORT` respectively.

5. **An empty domain scaffold does not yet carry these constraints; its
   first real source file does.** A domain sub-package created as an
   empty shell (`__init__.py` plus a placeholder scaffold test, per
   `ADR-005` Decision 2 Part 1) is not itself a violation of control 1.
   The moment a domain path receives real application source, the
   surface-profile-activation gate (TSD §24.1 gate 7, `ADR-005` Decision
   2 Part 3) and controls 1-4 above both apply to it.

6. **Business logic lives in the domain layer, not the route handler.**
   A FastAPI route handler parses/validates its request, resolves
   tenant context, and calls into its own domain's application-service
   layer — it does not itself contain conditional business rules,
   multi-step orchestration, or direct database access. See
   `.claude/rules/backend/api.md` for the API-boundary half of this
   constraint.

## Fail-closed rule

A pull request introducing a cross-domain table/ORM import outside the
TSD §6.3 exception, a synchronous import on a §6.3 pair's non-listed
(reverse) edge, or domain-owned business logic placed in
`app/modules/_shared/`, does not merge. The module dependency/SQL lint
gate (TSD §24.1) is CI-blocking, not advisory, and is proven by a
deliberate-violation fixture per `IMPLEMENTATION.md` §4.

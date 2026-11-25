# ADR-0014 — MOD-008: the gate answers *where*, so a club manager can use the product

- ID: ADR-0014
- Status: ACCEPTED
- Decision-Key: mod008-the-gate-answers-where
- Covers: backend/app/authorization/, backend/app/main.py, web/src/

**Dated 2026-11-25. Scope: ADM-CC-02, and the single most-repeated product limitation in this
build.** Authority is `knowledge/00-Decisions/OWNER-2026-11-13-full-engineering-delegation.md`,
which delegates ordinary product and architecture decisions. The sources are
`veyro-product-experience-design/` — ADM-CC-02's canvas and the role lines in the Admin
inventory — and `backend/app/authorization/` as it stands.

## The limitation

`authz.check` takes an optional `scope` and defaults to `authz.Scope()`, the tenant-wide one.
`authz.permissions_of` lets a broad assignment cover a narrow scope and never the reverse, which
is correct and is the whole safety property. Together they mean a **location-scoped assignment
contributes nothing at the default scope** — so a club manager holding `people.person.read` at
one club is refused every gated read in the product.

Four modules record it in their own gap lists, in almost the same words:

- MOD-014: "**A brand- or location-scoped role cannot use this module at all.** Both `permit`
  and `held_permissions` resolve against the tenant-wide default scope, and a narrower
  assignment covers nothing, so a single-brand front desk is refused every read."
- MOD-017's staff list: "**`location_id` is a filter, not a boundary**: the design says a club
  manager sees only their own club's staff and `permit` resolves tenant-wide."
- MOD-026: "A queue's `location_id` is a scope, not a boundary."
- MOD-027: "A source's `location_id` is a scope, not a boundary."

And ADM-CC-02 is the screen it is about: the club manager's Command Center, whose canvas says
"the rail is generated from his role rather than greyed".

**The direction of the failure is safe and the product cost is total.** Nothing leaks; a whole
role simply cannot sign in and work. Every tenant in this build has exactly one kind of user:
one who holds everything everywhere.

## What must not change

`permissions_of`'s asymmetry. A narrow assignment must never read as a broad one — MOD-008's
review found a brand-scoped manager reaching another brand's location by sending their own brand
id beside it, and `resolve_scope` exists because of it. Nothing here widens what an assignment
covers.

## The decision

**D1 — A route that names no scope is asking "may this caller do this *anywhere*", and the gate
answers with where.** The alternative readings are both worse: refusing (today) means the role
cannot work, and treating a narrow grant as tenant-wide is the escalation the review closed.

**D2 — The scopes are the caller's own live assignment scopes, derived and never accepted.**
`check` loads the assignments already; it now asks `permissions_of` at each distinct scope among
them and keeps the ones that hold the action. A request that *does* name a scope is unchanged —
that path is `resolve_scope`'s and stays the only way to turn request input into a `Scope`.

**D3 — A tenant-wide holder gets `tenant_wide = true` and one scope, so nothing in the build
changes behaviour.** This is load-bearing rather than cautious: every route, every test and
every fixture in this repository assumes a tenant-wide caller, and a change that altered what
they see would be a change to the product nobody asked for, made invisibly.

**D4 — A route opts in to a scoped caller, and the default is to refuse one.** This is the half
that keeps the change fail-closed. If the gate simply allowed a scoped caller, every read that
has not been taught to filter would return the whole tenant to a club manager — which turns a
role that cannot work into a role that sees everything, and does it silently across a hundred
routes. So `permit` refuses a caller who is not tenant-wide unless the route passes
`scoped=True`, and a route passes that only when it uses `gate.scopes` to filter.

**D5 — The opt-in is checked structurally, because a flag a route sets is a declaration.**
`GateCoverageTests` already reads `main.py` with `ast` and requires every route to ask the gate
or be listed with a written reason. It now also requires that a route passing `scoped=True`
mentions `scopes` in its body — so the flag cannot be set by a route that then ignores where the
caller may act. That is the same discipline as `UNGATED`: adding to the list is meant to be
uncomfortable.

**D6 — Assurance is about the session, not the scope.** A stepped-up session is stepped up
everywhere, and a step-up per club would be a second meaning for AAL that nothing else in the
build has. So the assurance check is unchanged and runs once.

## What this does not decide

- **Which reads filter.** The gate can answer *where* now; teaching each module's reads to use
  it is per-module work, and until a route opts in, a scoped caller is refused exactly as
  today. The honest claim after this slice is that the gate says where and the routes that act
  on it are named, not that the product is scope-aware.
- **The hierarchy.** `Scope.covers` says "a brand scope reaches that brand, and a location
  inside it — which the caller establishes by sending the location's brand along with it,
  because this module does not know the hierarchy and must not guess at it". That is unchanged:
  the scopes this returns are the assignment's own, so a brand-scoped caller gets a brand scope
  and a read that wants its locations asks `tenancy` for them.
- **Delegation at location granularity.** MOD-008's gap stands: "a brand-scoped grantor cannot
  delegate at location granularity inside their own brand", because `assign_role` builds its
  target with no brand. This slice does not touch granting.
- **Masking per scope.** `held_permissions` resolves at the caller's own held scopes now, so a
  club manager is no longer handed an *empty* permission set -- but the change is **inert on
  every route that has opted in**, and that is stated rather than discovered: `/staff` is the
  only one, its maskable columns are `identity` class, and the only class a scoped caller could
  open with a routine permission is `contact`, which that list has no field of. So there is no
  behavioural case to write and a mutation against it would correctly come back uncaught. It is
  kept because the next route to opt in would otherwise inherit an empty set silently, and the
  opt-in is designed to be added one route at a time. **A mask that differs by club** -- the
  same person readable at one site and withheld at another -- is a further question and is not
  this one.
- **The reader-facing consequence this slice did create, and closed.** A location-scoped caller
  reaching `/staff` sees every name withheld, correctly: they hold `people.person.read`, which
  opens no class. The marker beside it offered a step-up, which for them lifts nothing --
  `member.identity.read` is `financial` and they hold it at no assurance. Before this slice
  that reader could not reach the page at all, so the sentence had never been wrong for anybody.
  `withheldRemedy` in `web/src/lib/mask.ts` is the split and the gate decides it; the fix
  reached sixteen marker sites across thirteen files (twenty files in all, the rest
  threading the key through a helper or a client form), because the same key was passed
  unconditionally everywhere a name can be masked. **And the step-up *offer* was a separate
  control on seven of those screens**, each on its own condition, so correcting the sentence
  left the link -- which is the half that actually costs a recovery code.

## The evidence

- **11 Python mutations** in `backend/tests/mutate_scoped_gate.py`, all caught. Two needed
  cases that did not exist, and both for the same reason: removing the permission filter from
  `scopes_holding` and removing its liveness check both leave the answer unchanged for a caller
  with one role at one club, because the two rules agree on that input. The cases that bite are
  a second role at a second club granting something else, and a revoked assignment at a third.
  That is "a case catches a weakening only if the two rules disagree on it", applied to a
  derivation rather than a constraint.
- **8 HTTP tests** in `backend/tests/test_authorization_api.py`: a location-scoped read and its
  boundary in both directions, a route that has not opted in still refusing, a brand-scoped
  caller refused, a tenant-wide caller unchanged, only the held permission's club, an expired
  and a revoked assignment opening no club, the gate the rail reads, and a request that names a
  scope asking about that scope only.
- **2 structural tests** in `backend/tests/test_gating.py`: a route passing `scoped=True` must
  read `gate.scopes`, and at least one route must pass it — because a structural check
  asserting an empty list proves nothing until it can see its subjects.
- **4 browser tests** in `web/tests/e2e/scoped-gate.spec.ts`, against a club-manager identity
  the fixture seeds: the bounded staff read with its notice, a route that has not opted in
  refusing, the rail generated from the role rather than greyed, and the owner unchanged.
- **6 component tests** over `withheldRemedy` and both message catalogues, plus **4 browser
  mutations** in `web/tests/e2e/mutate.mjs` for the remedy split and its two renderings, and
  one more browser test on the member record for the reader who holds no *contact* read --
  a branch no fixture could reach before, because the test beside it proves a routine session
  *sees* the address.

**And the first implementation was silently inert, which is the finding worth carrying.**
`check` keys on the scope argument being *absent*, and both `/authz/check` and `/authz/checks`
passed `resolve_scope(None, None)` — the tenant-wide `Scope()`, which is the right answer for
the permission simulator and the wrong one here. So `/staff` answered a club manager "yes"
while the gate every surface in this app reads answered "no": the screen said "Not permitted"
over a read that would have worked, which is the worse half of the two. `None` and `Scope()`
are two different questions, and nothing in 46 authorization tests had ever asked the gate as
a scoped caller.

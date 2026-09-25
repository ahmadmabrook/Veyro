---
scope: path
paths:
  - "backend/**/*.py"
---
<!-- Target path once applied: .claude/rules/backend/concurrency.md -->

# Rule: Backend Optimistic Concurrency for Mutable Aggregates (`backend/**/*.py` binding)

Authored 2026-09-19 (MOD-001, `ADR-005` Decision 2 binding pre-implementation
condition — see `architecture.md` for the shared authority citation, not
restated here). Grounded directly in TSD §2.2's `DOM-002` global
invariant (`TSD_MIRROR.md` lines 643-647, verbatim: "Each mutable
aggregate uses optimistic concurrency/versioning. Lost-update behavior
must be explicit"), the same invariant's Appendix I entry
(`EIP_MIRROR.md` lines 20899-20906, co-owned by MOD-001, MOD-002,
MOD-019, MOD-020, MOD-034, MOD-037), and `REQUIREMENTS.md`'s own
disposition of it ("Proven by a concurrency/versioning test pattern in
the test-pyramid's persistence layer | GOV-01-R02; CONC category") —
read directly this session from the owner-produced mirrors. Per this
project's own convention (`REQUIREMENTS.md` §0), the governing `.docx`
wins over this mirror-sourced text on any conflict.

This rule is active now for MOD-001's own scaffold persistence layer
(the concurrency/versioning test pattern GOV-01-R02 requires) and binds
forward to every later domain module's real mutable-aggregate tables
under `backend/**`.

## Required controls for `backend/**` (mutable-aggregate persistence)

1. **Every mutable aggregate's table carries an explicit version
   column.** A table supporting in-place mutation of a
   business-meaningful row (not append-only/immutable) has a version/
   optimistic-lock column (e.g. `version integer NOT NULL DEFAULT 1`,
   or an equivalent monotonic token). A mutable-aggregate table with no
   such column violates `DOM-002`.

2. **Every mutation reads, checks, and increments the version in one
   atomic statement.** A mutation includes the version it read in the
   update's `WHERE` clause and increments it as part of the same
   statement/transaction — e.g. `UPDATE ... SET version = version + 1
   WHERE id = :id AND version = :expected_version`. A mutation that
   writes to a versioned table without a version-checked `WHERE`
   predicate is a rule violation, whether or not a conflict happens to
   occur in practice.

3. **A version mismatch is a real conflict, never silently
   overwritten.** When the version-checked update affects zero rows
   because another writer moved the version first, that outcome is
   surfaced as a typed, distinguishable conflict error (see `api.md`'s
   typed-errors control) — it is never silently retried with a blind
   unconditional overwrite, and it is never swallowed or logged-and-
   ignored.

4. **Lost-update behavior is an explicit, documented decision.** Per
   `DOM-002`, "lost-update behavior must be explicit": the chosen
   resolution for a version conflict on a given aggregate (reject and
   let the caller retry, an explicit merge strategy, or an
   explicitly-acknowledged last-writer-wins) is a stated design decision
   recorded in the owning domain module's own documentation — never an
   accidental consequence of whichever concurrent write happened to
   land last.

5. **Append-only tables are exempt.** Ledger postings, domain events,
   and audit rows are never mutated in place, so this rule's version-
   column requirement does not apply to them — a table is "mutable" for
   this rule's purposes only if application code issues in-place
   `UPDATE` statements against its existing rows.

## Fail-closed rule

A mutable-aggregate table with no version column, or a mutation path
that updates such a table without a version-checked `WHERE` clause and
atomic increment, does not merge. This is proven by the concurrency/
versioning test pattern in the persistence-layer test suite (GOV-01-R02,
CONC category) — a deliberately-broken version-check fixture must be
shown to fail closed, not silently pass.

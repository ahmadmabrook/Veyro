# ADR-0017 — MOD-008: a staff invitation, and the escalation rule a week can outlive

- ID: ADR-0017
- Status: ACCEPTED
- Decision-Key: mod008-staff-invitation
- Covers: backend/migrations/product/, backend/app/authorization/, backend/app/identity/, backend/app/main.py, web/src/

**Dated 2026-11-25. Scope: ADM-STF-03.** Authority is
`knowledge/00-Decisions/OWNER-2026-11-13-full-engineering-delegation.md`, which delegates
ordinary product and architecture decisions. The source is the drawn canvas in
`veyro-product-experience-design/project/Veyro V1 Batch J Staff and Communication.dc.html`,
read in the batch file rather than in `veyro-screen.js` — ADR-0015's finding, where the
prototype and the deliverable disagreed about which fields exist.

## The canvas

> **ADM-STF-03 · INVITE** — "Invite someone" · **EMAIL** `kareem@nadi.jo` · **ROLE** "Sales ▾"
> · **CLUBS** "Khalda, Sweifieh ▾" · "The link expires in **7 days**. Sales can see leads and
> members at those two clubs, sell memberships, and take payments. No financial
> administration." · "Send invitation" · **PENDING · 2** — `yasmin@nadi.jo` "2d left" Resend ·
> `omar.s@nadi.jo` "expired" Resend

## What already exists, checked rather than assumed

`iam.roles` carries a tenant-written `description`, and `create_role` writes it, so the
canvas's sentence has a column and a writer. `list_roles` returns each role's full permission
list. `iam.role_assignments` carries `scope_type`, `brand_id` and `location_id` with **real
composite foreign keys into `plt01.brands` and `plt01.locations`** — so a table in `iam` can
reference the tenant plane even though `veyro_iam_app` holds no privileges there, and this
invitation carries the same references rather than bare ids. `_assign_in_tx` is already
connection-taking, so MOD-008 needs no extraction; `register_identity` is not, so MOD-007 gets
an `_on` form.

**What does not exist**: there is no invitation of any kind in this build — no table, no token,
no expiry, and nothing that accepts one. `POST /identities` is open, which MOD-007 records as
a gap.

## Decisions

**D1. The invitation is MOD-008's, and MOD-008 imports MOD-007's identity creation.** It spans
both, so one of them has to import the other — and the control that must not be bypassed is
"a grantor may only grant permissions they themselves hold, at a scope they themselves cover",
which is MOD-008's rule and the one a review found a clerk escalating through. Putting the
invitation in MOD-007 would put that rule in the module that does not own it. Neither module
imports the other today, so there is no cycle either way.

**D2. One transaction for the accept, because both tables are in `iam` under one role.** An
identity created with its assignment rolled back is a login with no permissions — and the
retry cannot repair it, because the identifier is now taken and `register_identity` answers
`identifier_already_registered`. That is the difference from ADR-0010's walk-in, where the
partial outcomes are each a less complete record that can be completed.

**D3. The token is stored as a SHA-256 digest and the plaintext is returned once.** MOD-007's
session precedent, and the reason there is the reason here: a table that can be read is a table
that can be read by the wrong person. The consequence decides D4.

**D4. A resend is a new invitation superseding the old, not a rewritten expiry.** It *cannot* be
the same link, because the plaintext is gone (D3) — so a resend necessarily mints a new token,
and a design that moved `expires_at` on the existing row would rewrite when a link was valid.
The old row is revoked with its reason, the new one names what it replaces, and nothing is
edited: MOD-021's certificate rotation and MOD-017's agreement supersession, for the same
reason both of those are rows rather than updates.

**D5. One live invitation per email address, by partial unique index.** Two live invitations for
one address with different roles means whichever link the invitee clicks decides what they can
do, which is an ambiguity nobody would defend. A resend revokes and inserts in one transaction,
so the index is satisfied by construction.

**D6. There is no status column.** Pending is derived — not accepted, not revoked, and
`expires_at > now()` — and "2d left" is arithmetic over the row rather than a counter something
has to sweep. MOD-026's no-stored-countdown discipline and MOD-018's no-stored-balance, in a
table where a stale `expired` flag would be a live link the product says is dead.

**D7. The clubs are a child table, because the canvas invites somebody to two of them.**
`iam.role_assignments` admits exactly one scope per row, so "Khalda, Sweifieh" is two
assignments — and the invitation therefore carries a list. One scope row per club, and the
accept creates one assignment per row in the same transaction.

**D8. Seven days, from the canvas, bounded one to thirty.** The upper bound is the interesting
half: an invitation is a bearer credential that creates an identity with a role, so a
year-long one is a permanent back door with a friendly name.

**D9. Accepting is unauthenticated by construction, and it does not close open registration.**
The token *is* the authentication — an invitee has no identity yet, by definition — and the
route is rate-limited for that reason. What it does **not** do is withdraw `POST /identities`:
that is a separate decision with a wide blast radius (every fixture and harness in this build
creates an identity through it), and the honest state is that there are now two paths, one of
which grants a role. Closing the open one needs a decision about how a tenant's first identity
is created, which is `authz.bootstrap`'s own standing gap.

**D10. The escalation rule is re-checked at accept, not only at invite.** This is the finding
the slice turns on: a week is long enough for the inviter's own grant to be revoked, so an
invitation whose role was legitimate on Monday would hand out a permission its author no longer
holds on Friday — "a control consulted once is a control with a window", which is MOD-009's
legal-hold defect and the shape this build has met in four modules. The check at accept asks
about the *inviter* rather than the invitee, because the invitee holds nothing yet; an
invitation whose author can no longer grant it is refused with that reason, and the row stays so
the refusal is answerable.

**D11. No name on the invitation, because the canvas collects none.** Read against the
drawing rather than inferred: ADM-STF-03's form is `EMAIL · ROLE · CLUBS`, and its pending list
draws `yasmin@nadi.jo · 2d left` rather than a person. The first draft of this slice carried a
`display_name` column, a form field, two message keys and a second line in every pending row —
a field the design does not draw, holding a copy of somebody's name in the plane whose own
authentication log deliberately records none (`iam.auth_events` has an identity id and no
identifier, and says in its comment why). So the column is gone and the identity's display name
is the invitee's own, typed on the page where they set their password, which is also the better
shape: a person's name is theirs to give.

The consequence is that `accept_invitation` requires one, and there is **no blank-name guard in
it** — one was written and the mutation sweep came back UNCAUGHT, because
`register_identity_on` refuses a whitespace-only name inside the same transaction. Deleted
rather than tested harder, which is this build's judgement for a constraint subsumed by a
sibling; the property keeps its case either way.

**D12. The address is immutable while the link is alive and erasable once it is settled.**
MOD-009's reachability registry is what forced this, and it is the registry doing exactly what
it was built for: the sweep matches column *names*, so `email_normalized` on a new table is
invisible to it and only a hand-written declaration catches it. Declared `unreachable` — which
the first draft's grants and trigger made true — the row would have outlived the identity it
is the second copy of, because `iam.identities.email_normalized` *is* cleared by an erasure. An
invitation would then be the most reachable copy of an erased person's address in the build, in
the one plane where erasure works at all.

So the column carries an UPDATE grant for one writer and the trigger refuses the write while
the invitation is live. Both halves are load-bearing and each answers the other's risk: an
invitation is a bearer credential that creates an identity with a role, and the address is
where the link went, so a writable address on a *live* row is a way to redirect somebody
else's grant — while on a settled row the token is spent or withdrawn and `accept_invitation`
refuses it either way. The two conditions line up exactly: a DSAR names an identity, and the
only invitation an identity can be matched to is one it accepted, which is settled by
definition. An invitation nobody accepted is therefore not reachable, and the run records it
with that reason rather than as `done / 0` — MOD-014's own finding one plane over.

**CHECK 116b's sixth probe is a permission for that reason**, and it is the only thing that can
see the branch tightened back to "the address never moves": under that rule every refusal probe
still passes while the erasure the registry promises fails at run time.

## What this does not do

**It sends nothing.** MOD-013 authors a message and has no dispatcher, so the invitation is
created and its link is returned to the caller — which is the seam, and the screen says so
rather than implying an email went out. **It does not verify the address**, which is MOD-013's
own standing limitation: an invitation to a mistyped address is a link nobody can use, and the
remedy is a resend to the corrected one. **It writes no `ppl_staff_profiles` row**: employment
is MOD-014's and an invitation is about access, which ADM-STF-01 composes from three planes
precisely because they are different facts.

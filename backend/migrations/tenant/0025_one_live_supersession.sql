-- MOD-017 — one live supersession per agreement, so "what is this member on now" has one
-- answer.
--
-- **The chain was writable and nothing read it**, which is the finding this closes from the
-- schema's side. `mem_agreements.supersedes_agreement_id` has existed since `0011` -- its own
-- comment says it is "for an upgrade, downgrade or transfer ... so the chain answers what did
-- this member have in March" -- `create_agreement` takes it and `POST /memberships/agreements`
-- exposes it. **All eight readers** of a membership's terms went to
-- `mem_memberships.agreement_id`, the chain's *root*, which is immutable by grant because
-- what the member originally agreed to does not move. Five are service functions and three
-- were SQL joins in listing queries, which is why the first count of them was five: a join on
-- `m.agreement_id` is a reader of the chain that no test of the other five can see.
--
-- `current_agreement` is the reader for one membership and `_walk_from` is the recursive CTE
-- the three listing reads join. What both need from here is that the walk cannot fork:
-- nothing stopped two agreements superseding one, and a fork makes the answer depend on which
-- row the planner returns -- MOD-018's `chart_for` finding on the figure a member disputes.
--
-- **Partial on the status, not on the column alone**, because an upgrade can be cancelled and
-- the member then upgraded again: `A -> B`, B cancelled, `A -> C` is the ordinary sequence and
-- a plain unique index would refuse C. The predicate is the same one the reader filters by, so
-- the index and the walk agree by construction rather than by two expressions that match
-- today.
CREATE UNIQUE INDEX mem_agreements_one_live_supersession
    ON plt01.mem_agreements (tenant_id, supersedes_agreement_id)
    WHERE supersedes_agreement_id IS NOT NULL AND status <> 'void';

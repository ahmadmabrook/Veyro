-- MOD-027 / MOD-017 -- what marks a product as a trial, in one column.
--
-- ADR-0010 D7. MOD-027's pipeline derives two of its five columns from MOD-017 -- "On trial" is
-- *this person has an active membership on a trial product* -- and nothing in this build could
-- tell a trial product from a real one, so `/leads` drew that column empty with the reason on
-- it. This is the fact it was missing.
--
-- **Three shapes this is not**, each refused for a reason the sources state:
--
--   * **Not a `cat_products.product_type`.** COM-02-R01 names eight and a trial is not a ninth
--     kind of thing to sell: a 7-day trial of a membership is a membership. A ninth value would
--     make the bundle fulfilment kinds and the entitlement rule answer about a taxonomy the
--     requirement does not have.
--   * **Not an eleventh `membership_kind`.** `0011`'s own comment says "COM-01-R01 in full. An
--     eleventh shape is a product decision, not a migration", and a shape decides *which
--     lifecycle edges exist and how the billing schedule is built*. A trial has the edges of
--     whatever it is sold as; being a trial is orthogonal to its shape.
--   * **Not a boolean beside a length.** `mem_contract_versions.early_termination_months` is
--     the precedent -- one nullable integer rather than a flag and a count, because two columns
--     can disagree and this build has shipped that defect deliberately once.
--
-- **And the length in days is a fact nothing else here can carry**, which is what makes this
-- one column rather than a flag. The term fields are months; `prepaid_days` is bound to
-- `membership_kind = 'prepaid'` by a biconditional, and a trial is not a prepayment because
-- nothing was paid. ADM-CRM-01's button says "Start a 7-day trial", so the offered length has
-- to be the product's and not the receptionist's: a length typed at the desk is two people
-- giving two different trials.
--
-- **NULL is "not a trial" and 0 is refused.** That is the one place this diverges from
-- `early_termination_months`, where 0 is a real product ("they may leave free"). A zero-day
-- trial is not something a gym sells, so admitting it would be a declared value nothing can
-- mean -- this build's most-repeated finding, created on purpose.
--
-- **Ninety days is the ceiling**, stated rather than open: a trial longer than a quarter is a
-- membership sold cheaply, and every reader of this column -- the door, the grant sweep, the
-- countdown -- treats it as a short clock. An unbounded integer here is MOD-011's unbounded
-- `observed_at` in another column: a value a caller chooses that decides how long somebody has
-- access for.
ALTER TABLE plt01.mem_membership_terms
    ADD COLUMN trial_days integer;

ALTER TABLE plt01.mem_membership_terms
    ADD CONSTRAINT mem_membership_terms_trial_days_sane
        CHECK (trial_days IS NULL OR (trial_days >= 1 AND trial_days <= 90));

-- **A trial is not sold on a shape whose own field contradicts it.** An `installment` plan is
-- paid in instalments and a `prepaid` membership covers a prepayment; a trial is neither, and a
-- row claiming both would make "how long does this last" have two answers -- `trial_days` and
-- `prepaid_days` -- with nothing to say which the door should read. The other eight shapes are
-- all admissible: a trial can be fixed-term, recurring, off-peak, a class-credit bundle or any
-- of the rest, because what it is sold *as* is a different question from whether it is a trial.
ALTER TABLE plt01.mem_membership_terms
    ADD CONSTRAINT mem_membership_terms_trial_is_not_a_payment_plan
        CHECK (trial_days IS NULL
               OR membership_kind NOT IN ('installment', 'prepaid'));

-- The grant. `mem_membership_terms` carries `UPDATE (status, version)` only -- publishing and
-- retiring the terms -- so this column is set once with the row and never moves, which is the
-- right rule rather than an omission: re-typing the offered length on live terms would change
-- what a trial means for the product while members are on one, and the membership's own
-- `ends_on` is what governs an existing trial either way. Correcting it is a new set of terms,
-- which is what `status` is for.
COMMENT ON COLUMN plt01.mem_membership_terms.trial_days IS
    'The offered trial length in days, or NULL where this product is not sold as a trial. '
    'The actual end of one trial is mem_memberships.ends_on, derived from this at activation.';

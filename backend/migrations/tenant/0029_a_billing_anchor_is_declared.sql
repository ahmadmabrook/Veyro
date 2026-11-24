-- MOD-017 -- which boundary a billing period falls on, declared per contract.
--
-- ADR-0011. ADM-CRM-06 draws a conversion as "Club · monthly · JOD 55.00 / Pro-rata to 31 Aug
-- · JOD 21.29 / Then 55.00 from 1 Sep", and 21.29 is `55.00 × 12/31` -- twelve days left in a
-- thirty-one-day August. So the boundary is the end of the calendar month and the recurring
-- charge starts on the first, which `lifecycle.renewal_period` cannot express: it tiles from
-- the previous period's end, and `activate_membership` sets the first period to `starts_on`
-- through `starts_on + 1 month - 1 day`. A membership sold on 20 August bills 20 Aug-19 Sep,
-- and the design's figure is not reachable from that.
--
-- **The default is what this build already does, and that is load-bearing rather than
-- cautious.** `agreement_start` is today's behaviour exactly, so every membership already sold
-- keeps the periods it was sold on. This module's premise is that a contract's figures do not
-- move -- it is why `cat_prices` carries no UPDATE on its amounts and why an agreement
-- snapshots its price resolution -- and a column that re-anchored live memberships on being
-- added would move every renewal date in the product, silently, for people who have been told
-- a date.
--
-- **It is a property of the contract, not of the agreement.** A gym bills its monthly
-- memberships one way for everybody; two members on one contract with different anchors is a
-- difference nobody chose and nobody could explain at the desk. `mem_membership_terms` is
-- where `billing_period` already lives, and the two are one decision read together.
--
-- **Only the first period moves.** Under `calendar` the first period ends at the end of the
-- calendar unit containing its start, and the existing rule -- the next period starts the day
-- after the last one ended -- lands on calendar boundaries by itself from then on: 20 Aug
-- gives 20-31 Aug, then 1-30 Sep, then 1-31 Oct. So there is no second tiling rule, which
-- matters because two of them are a pair of dates that can disagree about when a member is
-- billed, and this build has shipped one-module-two-definitions often enough to name it.
ALTER TABLE plt01.mem_membership_terms
    ADD COLUMN billing_anchor text NOT NULL DEFAULT 'agreement_start';

ALTER TABLE plt01.mem_membership_terms
    ADD CONSTRAINT mem_membership_terms_billing_anchor
        CHECK (billing_anchor IN ('agreement_start', 'calendar'));

-- **A week has no calendar boundary this build may name, so `calendar` is refused for one.**
-- Whether a week begins on Sunday or on Monday is exactly the fact ADM-RPT-04 refuses to
-- assert -- its day chips name *which days* rather than what they mean to a business, because
-- no table or configuration key in this build records a working week -- and inventing one here
-- to anchor a billing period would be inventing product in the place it decides what somebody
-- is charged. `one_off` has no renewal to anchor at all. Both are refused here rather than in
-- the service, because the service is the half that can be wrong.
ALTER TABLE plt01.mem_membership_terms
    ADD CONSTRAINT mem_membership_terms_calendar_anchor_has_a_boundary
        CHECK (billing_anchor = 'agreement_start'
               OR billing_period IN ('monthly', 'quarterly', 'annual'));

-- The grant. As with `trial_days`, `mem_membership_terms` carries `UPDATE (status, version)`
-- only, so the anchor is set once with the row and never moves -- which is the rule rather than
-- an omission. Re-anchoring published terms would re-date every future renewal for every
-- member on them, so a different anchor is a different contract, which is what `status` is for.
COMMENT ON COLUMN plt01.mem_membership_terms.billing_anchor IS
    'Which boundary a billing period falls on: agreement_start tiles from the membership''s '
    'own start date, calendar from the end of the calendar month, quarter or year containing '
    'it. Final on a published contract; a different anchor is a different contract.';

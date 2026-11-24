-- MOD-027 slice 3 -- a lead that said no, and the interest recorded by mistake.
--
-- ADR-0010 D8 to D11. ADM-CRM-07 asks "Why did Omar Zaid not join?" over four reasons and a
-- free-text follow-up, and its footnote is the whole design: "Not deleted. Reopenable, and
-- re-contact after 90 days is a supported flow rather than a fresh record. The reason feeds
-- source effectiveness in ADM-RPT-03."
--
-- **`lost` is a fact beside the stage, not a sixth value in it, and that corrects a prediction
-- `0027` made.** That migration's comment said the stage domain admits three "because a
-- declared value nothing writes is this build's most-repeated finding and slice 3 is what
-- writes it" -- which assumed a stage value. ADR-0010 D3 rules it out one section earlier: the
-- pipeline runs forward only, because "a tour that fell through is a touchpoint saying so" and
-- a backwards move would make `Toured · 6` a count nobody can reconstruct. A lost lead that
-- reopens needs exactly that backwards edge, so a stage value buys an unreconstructable board.
--
-- Beside the stage instead, three things fall out:
--
--   * **Reopening is exact.** The lead resumes where they were, because `stage` never moved --
--     and the next touchpoint advances it, since `record_touchpoint` already does. A stage
--     value would have had to choose where a reopened lead lands, and any choice is a number
--     somebody cannot reconstruct.
--   * **`pipeline.EDGES` is unchanged**, so there is one stage machine and it still refuses
--     every backwards move. Two encodings of "where is this lead" that could disagree is
--     MOD-020's waitlist edge; a position and a liveness are different facts, which is why
--     MOD-017 keeps membership, billing and access state apart.
--   * **The board excludes a lost lead rather than drawing a sixth column**, which is what the
--     canvas shows: five columns, and ADM-CRM-07 as a side sheet.
ALTER TABLE plt01.crm_leads
    ADD COLUMN lost_at timestamptz,
    ADD COLUMN lost_reason text,
    ADD COLUMN lost_detail text,
    ADD COLUMN lost_by uuid;

-- **All of it or none of it**, so a lead cannot be lost with no reason, carry a reason while
-- live, or be lost by nobody -- the attribution shape this build uses wherever a decision is
-- recorded, because "evidence with nobody's name on it answers nothing". The detail is the one
-- field that may be absent while the rest are present: the canvas asks "which gym, if he
-- said", and the condition is that he said.
ALTER TABLE plt01.crm_leads
    ADD CONSTRAINT crm_leads_lost_is_reasoned_and_attributed
        CHECK ((lost_at IS NULL) = (lost_reason IS NULL)
               AND (lost_at IS NULL) = (lost_by IS NULL));

-- A detail about a loss that did not happen is a sentence with nothing to attach to.
ALTER TABLE plt01.crm_leads
    ADD CONSTRAINT crm_leads_lost_detail_needs_a_loss
        CHECK (lost_detail IS NULL OR lost_at IS NOT NULL);

-- **The four the canvas draws, closed because a group-by needs a closed set.** The registry
-- note is "Structured reason, feeds retention analytics", and free text would make any such
-- report a group-by over typos -- MOD-026's queue finding and this module's own reason for
-- making a source a row rather than a string.
--
-- **And no screen reads it yet, which is a correction to what the canvas says.** ADM-CRM-07's
-- footnote sends the reason to "source effectiveness in ADM-RPT-03", and ADM-RPT-03 is the
-- *membership* report: its own canvas draws "WHY THE 23 LEFT" and says "Reasons come from
-- ADM-MSH-07's required field" -- members cancelling, not leads who never joined. ADR-0010's
-- build order names ADM-RPT-06 for the same read, and there is no ADM-RPT-06 in the registry
-- at all. So the destination is a screen nobody has drawn, and the closed set is justified by
-- what a group-by needs rather than by a report that exists.
--
-- **In code and in this CHECK rather than in a tenant's own table, which is the opposite call
-- from `crm_sources`.** A source is a club's own open day and belongs to that club; a lost
-- reason is a category of market behaviour, and a per-tenant set would make ADM-RPT-03's
-- columns vary by tenant with nothing able to say which set is the product's. `pipeline.py`
-- declares the same four and a test compares the two, which is MOD-026's precedent for a
-- vocabulary that lives in both places.
--
-- **There is no "Other".** The canvas draws four and no catch-all; "no_longer_responding" is
-- the one that absorbs a lead who simply stopped, and `lost_detail` is where a salesperson
-- writes what they actually learned. A fifth reason is a product decision rather than a
-- migration.
ALTER TABLE plt01.crm_leads
    ADD CONSTRAINT crm_leads_lost_reason
        CHECK (lost_reason IS NULL OR lost_reason IN (
            'too_expensive', 'joined_elsewhere', 'location_or_hours',
            'no_longer_responding'));

-- Prose a salesperson types, bounded at the boundary as well so a long one is a 422 naming the
-- request rather than a `DataError` the handlers do not catch -- MOD-011's, MOD-012's and
-- MOD-013's finding, and non-blank because a detail of whitespace is a field nobody filled in.
ALTER TABLE plt01.crm_leads
    ADD CONSTRAINT crm_leads_lost_detail_said_something
        CHECK (lost_detail IS NULL
               OR (lost_detail ~ '[^[:space:]]' AND length(lost_detail) <= 500));

-- The four columns join the UPDATE grant, because a loss is recorded and a reopening clears
-- it -- ADR-0010 D4's "state with a reason and an attribution that can be left". The history
-- is the touchpoint timeline, which is insert-only, so what a reopening clears is the *current*
-- state and never the record of it.
GRANT UPDATE (lost_at, lost_reason, lost_detail, lost_by)
    ON plt01.crm_leads TO veyro_cp_app, veyro_cp_worker;

COMMENT ON COLUMN plt01.crm_leads.lost_at IS
    'When this lead was marked lost, or NULL while they are live. Not a stage: the pipeline '
    'runs forward only, so the stage they reached is kept and a reopening resumes it.';
COMMENT ON COLUMN plt01.crm_leads.lost_reason IS
    'One of the four ADM-CRM-07 draws. Closed because ADM-RPT-03 groups by it.';

-- ------------------------------------------------------------------ the interest withdrawal
--
-- ADR-0010 D11. `crm_lead_interests` carried `GRANT SELECT, INSERT` and nothing else, and
-- `0027` said so in as many words: "An interest is recorded or withdrawn, and withdrawing is
-- slice 3's work alongside `lost`; until then the set only grows, which is honest for a first
-- slice and is stated rather than discovered." This is that work.
--
-- **Why it matters at all for three values on a sales record**: `crm.lead.write` is routine
-- and AAL 1, and a routine permission whose every act is uncorrectable is MOD-013's "an
-- irreversible act must not be declarable on a routine permission" -- the same finding MOD-019
-- paid for with a rota somebody is turned away by. The scale is smaller and the shape is
-- identical.
--
-- **A withdrawal, not a delete.** `0017`'s precedent: "was this lead ever interested in PT" is
-- asked precisely when somebody has changed their mind, and a deleted row answers nothing.
ALTER TABLE plt01.crm_lead_interests
    ADD COLUMN withdrawn_at timestamptz,
    ADD COLUMN withdrawn_by uuid;

ALTER TABLE plt01.crm_lead_interests
    ADD CONSTRAINT crm_lead_interests_withdrawal_is_attributed
        CHECK ((withdrawn_at IS NULL) = (withdrawn_by IS NULL));

GRANT UPDATE (withdrawn_at, withdrawn_by)
    ON plt01.crm_lead_interests TO veyro_cp_app, veyro_cp_worker;

-- **One way, because a CHECK cannot see what a row used to be.** MOD-009's `sec_legal_holds`
-- rule: without this, a withdrawal could be cleared so the interest reads as never withdrawn,
-- or re-dated so when somebody changed their mind becomes unanswerable. Re-recording an
-- interest somebody wants again is an INSERT, which the partial index below admits.
CREATE OR REPLACE FUNCTION plt01.crm_interest_withdrawal_is_final()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
    IF OLD.withdrawn_at IS NOT NULL
       AND NEW.withdrawn_at IS DISTINCT FROM OLD.withdrawn_at THEN
        RAISE EXCEPTION
            'a withdrawn interest stays withdrawn, and when it was withdrawn does not move';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION plt01.crm_interest_withdrawal_is_final() FROM PUBLIC;

CREATE TRIGGER crm_interest_withdrawal_is_final
    BEFORE UPDATE ON plt01.crm_lead_interests
    FOR EACH ROW EXECUTE FUNCTION plt01.crm_interest_withdrawal_is_final();

-- **The uniqueness has to become partial, or an interest can never be recorded again.**
-- `0027`'s key is one row per (tenant, lead, interest), which is right while the set only
-- grows and wrong the moment one can be withdrawn: a member who wanted PT, changed their mind
-- and changed it back would be refused by the row they withdrew. Partial on live rows, so a
-- withdrawn interest keeps its place in the record and does not block the new one.
-- **A surrogate id rather than `recorded_at` in the key**, because `recorded_at` defaults to
-- `now()` and two rows written in one transaction share it: a lead who withdraws PT and asks
-- for it again in the same request would be refused by a primary key, as a 409 nobody could
-- read. Every other table in this build keys on its own id for the same reason.
ALTER TABLE plt01.crm_lead_interests
    ADD COLUMN interest_id uuid NOT NULL DEFAULT gen_random_uuid();

ALTER TABLE plt01.crm_lead_interests
    DROP CONSTRAINT crm_lead_interests_pkey;

ALTER TABLE plt01.crm_lead_interests
    ADD CONSTRAINT crm_lead_interests_pkey
        PRIMARY KEY (tenant_id, interest_id);

CREATE UNIQUE INDEX crm_lead_interests_one_live
    ON plt01.crm_lead_interests (tenant_id, lead_id, interest)
    WHERE withdrawn_at IS NULL;

COMMENT ON COLUMN plt01.crm_lead_interests.withdrawn_at IS
    'When this interest was taken back, or NULL while it stands. A withdrawal rather than a '
    'delete: "was this lead ever interested in PT" is asked when somebody changed their mind.';

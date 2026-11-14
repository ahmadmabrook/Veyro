-- MOD-020 OPS-02: booking, waitlist, no-show policy and appeals.
--
-- **Seven `bkg_` tables, under the same forced RLS as every other `plt01` table.** The pattern
-- in `0001_organization_hierarchy.sql` is copied exactly and each of its four parts is
-- load-bearing: `tenant_id NOT NULL`, a tenant-leading primary key, ENABLE *and* FORCE row
-- level security, and a policy whose predicate is the approved one on both halves. A composite
-- foreign key carries `tenant_id` into every parent reference.
--
-- **This module owns no capacity, and that is the design.** Paragraph 4141: "Schedule owns
-- published occurrences/resources/capacity. Booking owns member reservation/waitlist/cancel/
-- attendance intent." So a booking carries a foreign key to the MOD-019 hold that *is* its
-- place, the hold is taken in the same transaction, and the two invariants paragraph 4697 names
-- are MOD-019's to keep:
--
--   * "Booking capacity never falls below zero" -- `sch_hold_fits_the_session` counts under
--     `FOR UPDATE` on the session and refuses the hold, so a booking cannot exist without a
--     place. There is no counter here to disagree with it.
--   * "Duplicate waitlist promotion cannot consume multiple seats" --
--     `sch_capacity_holds_one_live_per_person` is a partial unique index on (session, person),
--     so a second promotion of one member is refused by the database rather than by this
--     module remembering. The idempotency paragraph 4144 asks for is that index plus the
--     `one_live_per_session` index below, not a flag somebody sets.
--
-- A second count here would be MOD-018's cached-balance argument applied to seats: two
-- authorities that can disagree, with the disagreement surfacing as a member refused a place
-- the roster says is free.

-- ---------------------------------------------------------------- the policy
--
-- OPS-01-R02's booking rules, versioned. A booking snapshots the version it was made under --
-- MOD-012's rule, where an install snapshots the definition -- because the consequence of
-- cancelling late is decided months later and has to be decided on the terms the member
-- agreed to. Changing the window next week cannot change what somebody owes for last week.
CREATE TABLE plt01.bkg_policies (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    policy_id uuid NOT NULL DEFAULT gen_random_uuid(),
    policy_key text NOT NULL,
    version integer NOT NULL,
    display_name text NOT NULL,
    -- Hours before the start after which cancelling carries the policy's consequence. Zero
    -- means a cancellation is never late, which is a real choice a tenant makes.
    cancellation_hours integer NOT NULL DEFAULT 12,
    max_concurrent integer NOT NULL DEFAULT 10,
    quota integer,
    quota_period text NOT NULL DEFAULT 'rolling_7_days',
    checkin_grace_minutes integer NOT NULL DEFAULT 15,
    warn_after_no_shows integer NOT NULL DEFAULT 2,
    strike_after_no_shows integer NOT NULL DEFAULT 3,
    priority_rule text NOT NULL DEFAULT 'first_come',
    offer_minutes integer NOT NULL DEFAULT 60,
    -- Whether a late cancellation or a no-show forfeits the entitlement the booking drew on.
    -- A tenant that refunds the class instead is as ordinary as one that does not, so this is
    -- declared rather than assumed.
    forfeits_entitlement boolean NOT NULL DEFAULT true,
    status text NOT NULL DEFAULT 'active',
    retired_at timestamptz,
    retired_by uuid,
    retire_reason text,
    retire_correlation_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, policy_id),
    UNIQUE (tenant_id, policy_key, version),
    CONSTRAINT bkg_policies_key_shape
        CHECK (policy_key ~ '^[A-Z0-9][A-Z0-9._-]{1,47}$'),
    CONSTRAINT bkg_policies_name_not_blank CHECK (display_name ~ '[^[:space:]]'),
    CONSTRAINT bkg_policies_version_positive CHECK (version >= 1),
    CONSTRAINT bkg_policies_cancellation_sane
        CHECK (cancellation_hours >= 0 AND cancellation_hours <= 168),
    CONSTRAINT bkg_policies_concurrent_sane
        CHECK (max_concurrent >= 1 AND max_concurrent <= 100),
    -- A quota of zero is a policy that books nothing, which nobody means; the absence of a
    -- quota is NULL, and the two are different statements.
    CONSTRAINT bkg_policies_quota_sane
        CHECK (quota IS NULL OR (quota >= 1 AND quota <= 10000)),
    CONSTRAINT bkg_policies_quota_period
        CHECK (quota_period IN ('day', 'week', 'rolling_7_days', 'rolling_30_days')),
    CONSTRAINT bkg_policies_grace_sane
        CHECK (checkin_grace_minutes >= 0 AND checkin_grace_minutes <= 240),
    CONSTRAINT bkg_policies_warn_positive CHECK (warn_after_no_shows >= 1),
    CONSTRAINT bkg_policies_strike_positive CHECK (strike_after_no_shows >= 1),
    -- **A strike comes after a warning.** A sanction with no notice is what an appeal exists
    -- to overturn, and a policy that struck first would make every strike appealable on that
    -- ground alone.
    CONSTRAINT bkg_policies_strike_follows_warning
        CHECK (strike_after_no_shows >= warn_after_no_shows),
    CONSTRAINT bkg_policies_priority
        CHECK (priority_rule IN ('first_come', 'membership_tier')),
    CONSTRAINT bkg_policies_offer_sane
        CHECK (offer_minutes >= 1 AND offer_minutes <= 1440),
    CONSTRAINT bkg_policies_status CHECK (status IN ('active', 'retired')),
    CONSTRAINT bkg_policies_retired_is_retired
        CHECK (status <> 'retired' OR retired_at IS NOT NULL),
    CONSTRAINT bkg_policies_retirement_attributed CHECK (
        (retired_at IS NULL AND retired_by IS NULL AND retire_reason IS NULL
         AND retire_correlation_id IS NULL)
        OR (retired_at IS NOT NULL AND retired_by IS NOT NULL
            AND coalesce(retire_reason, '') ~ '[^[:space:]]'
            AND retire_correlation_id IS NOT NULL))
);
CREATE INDEX bkg_policies_live
    ON plt01.bkg_policies (tenant_id, policy_key, version DESC) WHERE status = 'active';
ALTER TABLE plt01.bkg_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.bkg_policies FORCE ROW LEVEL SECURITY;
CREATE POLICY bkg_policies_tenant ON plt01.bkg_policies
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- the booking
--
-- The Booking entity. **`hold_id` is the place**, and it is what makes paragraph 4142's "atomic
-- reservation" true rather than claimed: the hold is inserted in the same transaction, under
-- MOD-019's `FOR UPDATE` count and its fit trigger, so a booking row cannot exist for a
-- session that was full. There is no `seat_number` and no counter here.
CREATE TABLE plt01.bkg_bookings (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    booking_id uuid NOT NULL DEFAULT gen_random_uuid(),
    session_id uuid NOT NULL,
    person_id uuid NOT NULL,
    -- **The MOD-019 hold this booking is.** Not nullable: a booking with no hold is a member
    -- who thinks they have a place and does not, which is the worst failure available here.
    hold_id uuid NOT NULL,
    -- The policy version it was made under, snapshotted by reference. A foreign key rather
    -- than copied columns, because the policy row is immutable in the fields that matter --
    -- re-pricing a policy is a new version -- so the reference is the snapshot.
    policy_id uuid NOT NULL,
    -- How the member came to be booked. `waitlist` is separate from `member` because a
    -- promotion is a different conversation and a report of how a class filled needs it.
    source_kind text NOT NULL,
    -- The MOD-017 entitlement grant this drew on, where one did. NULL for a walk-in or a
    -- pay-as-you-go booking, and the reason `credit_forfeit` is a decision rather than an act:
    -- the grant is MOD-017's to debit.
    entitlement_grant_id uuid,
    state text NOT NULL DEFAULT 'booked',
    checked_in_at timestamptz,
    checked_in_by uuid,
    checkin_source text,
    checkin_correlation_id uuid,
    settled_at timestamptz,
    cancelled_at timestamptz,
    cancelled_by uuid,
    cancellation_reason text,
    cancel_correlation_id uuid,
    booked_at timestamptz NOT NULL DEFAULT now(),
    booked_by uuid NOT NULL,
    idempotency_key text NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, booking_id),
    UNIQUE (tenant_id, idempotency_key),
    -- **One booking per place.** This is paragraph 4144's "a member cannot consume the same
    -- capacity twice" at the place: MOD-019's hold is the authority a booking cites, and two
    -- bookings citing one hold would be two members in one seat. The *other* half -- one live
    -- booking per member per session -- is the partial index below, which this comment used
    -- to describe while sitting here. Found by review.
    UNIQUE (tenant_id, hold_id),
    FOREIGN KEY (tenant_id, session_id)
        REFERENCES plt01.sch_sessions (tenant_id, session_id),
    FOREIGN KEY (tenant_id, person_id) REFERENCES plt01.ppl_persons (tenant_id, person_id),
    FOREIGN KEY (tenant_id, hold_id)
        REFERENCES plt01.sch_capacity_holds (tenant_id, hold_id),
    FOREIGN KEY (tenant_id, policy_id) REFERENCES plt01.bkg_policies (tenant_id, policy_id),
    FOREIGN KEY (tenant_id, entitlement_grant_id)
        REFERENCES plt01.mem_entitlement_grants (tenant_id, grant_id),
    CONSTRAINT bkg_bookings_source_kind
        CHECK (source_kind IN ('member', 'waitlist', 'front_desk', 'migration')),
    CONSTRAINT bkg_bookings_state
        CHECK (state IN ('booked', 'attended', 'no_show', 'cancelled', 'released')),
    CONSTRAINT bkg_bookings_key_not_blank CHECK (idempotency_key ~ '[^[:space:]]'),
    -- **A check-in names who marked them present and how.** Nothing in this build reads a
    -- turnstile, so the row records a claim by a named actor at a time -- MOD-012's `validated`
    -- shape -- and a report of who was in a class has to separate a reader from a front desk.
    CONSTRAINT bkg_bookings_checkin_attributed CHECK (
        (checked_in_at IS NULL AND checked_in_by IS NULL AND checkin_source IS NULL
         AND checkin_correlation_id IS NULL)
        OR (checked_in_at IS NOT NULL AND checked_in_by IS NOT NULL
            AND checkin_source IS NOT NULL AND checkin_correlation_id IS NOT NULL)),
    CONSTRAINT bkg_bookings_checkin_source
        CHECK (checkin_source IS NULL
               OR checkin_source IN ('front_desk', 'self_service', 'device', 'migration')),
    -- An attended booking was checked in, and a check-in without attendance is a booking whose
    -- session has not finished yet -- so the implication runs one way only.
    CONSTRAINT bkg_bookings_attended_was_present
        CHECK (state <> 'attended' OR checked_in_at IS NOT NULL),
    CONSTRAINT bkg_bookings_no_show_was_absent
        CHECK (state <> 'no_show' OR checked_in_at IS NULL),
    CONSTRAINT bkg_bookings_settled_is_settled
        CHECK ((state IN ('attended', 'no_show')) = (settled_at IS NOT NULL)),
    CONSTRAINT bkg_bookings_cancellation_attributed CHECK (
        (cancelled_at IS NULL AND cancelled_by IS NULL AND cancellation_reason IS NULL
         AND cancel_correlation_id IS NULL)
        OR (cancelled_at IS NOT NULL AND cancelled_by IS NOT NULL
            AND coalesce(cancellation_reason, '') ~ '[^[:space:]]'
            AND cancel_correlation_id IS NOT NULL)),
    -- `released` is the gym cancelling the session and `cancelled` is the member cancelling
    -- their place. Both carry the attribution; only the member's own is their act.
    CONSTRAINT bkg_bookings_cancelled_is_cancelled
        CHECK (state NOT IN ('cancelled', 'released') OR cancelled_at IS NOT NULL)
);
-- **One live booking per member per session**, the other half of paragraph 4144. Partial, so
-- a member who cancelled and rebooked is an ordinary case.
--
-- **It has no behavioural case and cannot have one**, which is worth saying rather than
-- leaving somebody to find: two live bookings for one member on one session need two live
-- holds for them, and MOD-019's own `sch_capacity_holds_one_live_per_person` refuses the
-- second -- so no insert this schema admits can reach this rule, and an UPDATE back to
-- `booked` is refused by the one-way trigger. The definition pin in check 98 is its whole
-- evidence, which is the third option the rules file allows for an unprovable constraint:
-- keep the primitive statement, say here that it has no case and why, and let the pin catch
-- its removal. It stays because MOD-019's index is another module's and could move.
CREATE UNIQUE INDEX bkg_bookings_one_live_per_person
    ON plt01.bkg_bookings (tenant_id, session_id, person_id)
    WHERE state IN ('booked', 'attended');
CREATE INDEX bkg_bookings_by_person
    ON plt01.bkg_bookings (tenant_id, person_id, booked_at DESC);
CREATE INDEX bkg_bookings_by_session
    ON plt01.bkg_bookings (tenant_id, session_id, state);
-- The index a settlement sweep reads: everything still open on a session that has finished.
CREATE INDEX bkg_bookings_unsettled
    ON plt01.bkg_bookings (tenant_id, session_id) WHERE state = 'booked';
ALTER TABLE plt01.bkg_bookings ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.bkg_bookings FORCE ROW LEVEL SECURITY;
CREATE POLICY bkg_bookings_tenant ON plt01.bkg_bookings
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **A booking's hold is for that booking's session and that booking's member.** The two
-- composite foreign keys each carry `tenant_id` and neither relates the hold to the *session*
-- or the *person* on this row -- so without this a booking could cite a hold taken for
-- somebody else's place in another class, and the member would read as booked while the place
-- they held was elsewhere. MOD-013's finding: two caller-supplied keys that nothing relates
-- are two halves of a control, each failing open.
CREATE OR REPLACE FUNCTION plt01.bkg_booking_hold_matches()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    hold_session uuid;
    hold_person uuid;
    hold_status text;
    grant_person uuid;
BEGIN
    SELECT session_id, person_id, status INTO hold_session, hold_person, hold_status
      FROM plt01.sch_capacity_holds
     WHERE tenant_id = NEW.tenant_id AND hold_id = NEW.hold_id;
    IF hold_session IS NULL THEN
        RAISE EXCEPTION 'a booking cites a capacity hold that does not exist';
    END IF;
    IF hold_session <> NEW.session_id THEN
        RAISE EXCEPTION
            'this hold is for another session; a booking is the place it cites';
    END IF;
    IF hold_person <> NEW.person_id THEN
        RAISE EXCEPTION
            'this hold is for another member; a booking is the place it cites';
    END IF;
    -- A booking being *created* needs a live hold. A settled one keeps its hold reference
    -- afterwards, which is how "what place was this" stays answerable.
    IF TG_OP = 'INSERT' AND hold_status <> 'held' THEN
        RAISE EXCEPTION 'this hold is % and is not a place anybody has', hold_status;
    END IF;
    -- **And the entitlement it draws on is this member's.** The foreign key proves the grant
    -- exists and says nothing about whose it is, so a booking could cite another member's
    -- paid-for class pass -- and `credit_forfeit` then forfeits *their* class when this
    -- member does not turn up. `_entitlement_for`'s own docstring says "derived, never
    -- accepted ... a caller naming a grant id would be naming somebody else's entitlement",
    -- which MOD-016's review found in a coupon; the schema did not say it. Found by review.
    IF NEW.entitlement_grant_id IS NOT NULL THEN
        SELECT person_id INTO grant_person
          FROM plt01.mem_entitlement_grants
         WHERE tenant_id = NEW.tenant_id AND grant_id = NEW.entitlement_grant_id;
        IF grant_person IS NULL THEN
            RAISE EXCEPTION 'this booking cites an entitlement grant that does not exist';
        END IF;
        IF grant_person <> NEW.person_id THEN
            RAISE EXCEPTION
                'this entitlement belongs to another member; a booking spends its own';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER bkg_bookings_hold_matches
    BEFORE INSERT OR UPDATE ON plt01.bkg_bookings
    FOR EACH ROW EXECUTE FUNCTION plt01.bkg_booking_hold_matches();

-- **A booking's state moves one way, and a settled one is final.** Members have been told
-- whether they attended, and a no-show that could be flipped to attended is a sanction nobody
-- can rely on -- while one that could be flipped the other way is a member marked absent from
-- a class they were in. The attribution is never replaced, for MOD-009's reason: a CHECK
-- cannot see what a row used to be.
CREATE OR REPLACE FUNCTION plt01.bkg_booking_is_one_way()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF OLD.state <> 'booked' THEN
        RAISE EXCEPTION
            'this booking is % and a % booking does not change again', OLD.state, OLD.state;
    END IF;
    IF OLD.checked_in_at IS NOT NULL AND (
        NEW.checked_in_at IS DISTINCT FROM OLD.checked_in_at
        OR NEW.checked_in_by IS DISTINCT FROM OLD.checked_in_by
        OR NEW.checkin_source IS DISTINCT FROM OLD.checkin_source
        OR NEW.checkin_correlation_id IS DISTINCT FROM OLD.checkin_correlation_id) THEN
        RAISE EXCEPTION 'this check-in has already been recorded';
    END IF;
    -- What the booking *is* does not move: the place it holds, the member it is for, the
    -- session it is on and the policy it was made under are what every later decision reads.
    IF NEW.hold_id <> OLD.hold_id OR NEW.person_id <> OLD.person_id
       OR NEW.session_id <> OLD.session_id OR NEW.policy_id <> OLD.policy_id
       OR NEW.entitlement_grant_id IS DISTINCT FROM OLD.entitlement_grant_id THEN
        RAISE EXCEPTION
            'a booking keeps its place, its member, its session and its policy; cancel it '
            'and make another';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER bkg_bookings_one_way
    BEFORE UPDATE ON plt01.bkg_bookings
    FOR EACH ROW EXECUTE FUNCTION plt01.bkg_booking_is_one_way();

-- ---------------------------------------------------------------- the waitlist
--
-- The WaitlistEntry entity. OPS-02-R03 and paragraph 4144: "Waitlist promotion is an idempotent
-- workflow with offer/expiry policy; a member cannot consume the same capacity twice."
--
-- **An offer holds a real place.** Paragraph 5031: "waitlist promotion reserves before
-- notifying." So `hold_id` is set when the offer is made and the place is MOD-019's from that
-- moment -- which is what makes a notification that never arrives a member who has to be told
-- again rather than a member who lost their place (paragraph 5032). The cost is an hour of
-- capacity nobody else can book, which the expiry bounds.
CREATE TABLE plt01.bkg_waitlist_entries (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    entry_id uuid NOT NULL DEFAULT gen_random_uuid(),
    session_id uuid NOT NULL,
    person_id uuid NOT NULL,
    policy_id uuid NOT NULL,
    state text NOT NULL DEFAULT 'waiting',
    -- The tier `membership_tier` orders by. Zero for every member in a tenant with no tiers,
    -- which makes the rule collapse to `first_come` rather than erroring.
    tier integer NOT NULL DEFAULT 0,
    joined_at timestamptz NOT NULL DEFAULT now(),
    -- The place being held open for them, while an offer is live.
    hold_id uuid,
    offered_at timestamptz,
    offer_expires_at timestamptz,
    offer_correlation_id uuid,
    -- How many times this member has been offered this place and not taken it. An expired
    -- offer returns them to `waiting` -- somebody asleep at six did not decline -- and this is
    -- what stops that being an unbounded loop.
    offers_made integer NOT NULL DEFAULT 0,
    settled_at timestamptz,
    settled_by uuid,
    settle_reason text,
    settle_correlation_id uuid,
    -- The booking a confirmed offer became, so "what happened to my place on the waitlist" is
    -- answerable from this row alone.
    booking_id uuid,
    joined_by uuid NOT NULL,
    idempotency_key text NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, entry_id),
    UNIQUE (tenant_id, idempotency_key),
    FOREIGN KEY (tenant_id, session_id)
        REFERENCES plt01.sch_sessions (tenant_id, session_id),
    FOREIGN KEY (tenant_id, person_id) REFERENCES plt01.ppl_persons (tenant_id, person_id),
    FOREIGN KEY (tenant_id, policy_id) REFERENCES plt01.bkg_policies (tenant_id, policy_id),
    FOREIGN KEY (tenant_id, hold_id)
        REFERENCES plt01.sch_capacity_holds (tenant_id, hold_id),
    FOREIGN KEY (tenant_id, booking_id)
        REFERENCES plt01.bkg_bookings (tenant_id, booking_id),
    CONSTRAINT bkg_waitlist_entries_state CHECK (
        state IN ('waiting', 'offered', 'confirmed', 'declined', 'expired', 'withdrawn',
                  'lapsed')),
    CONSTRAINT bkg_waitlist_entries_tier_sane CHECK (tier >= 0 AND tier <= 1000),
    CONSTRAINT bkg_waitlist_entries_offers_sane
        CHECK (offers_made >= 0 AND offers_made <= 100),
    CONSTRAINT bkg_waitlist_entries_key_not_blank
        CHECK (idempotency_key ~ '[^[:space:]]'),
    -- **An offer has a time, an expiry, a correlation and a place.** All four or none: an
    -- offer with no expiry holds capacity for ever, and one with no hold is a member told they
    -- have a place that is not reserved -- which is paragraph 5031 inverted.
    CONSTRAINT bkg_waitlist_entries_offer_complete CHECK (
        (offered_at IS NULL AND offer_expires_at IS NULL AND offer_correlation_id IS NULL)
        OR (offered_at IS NOT NULL AND offer_expires_at IS NOT NULL
            AND offer_correlation_id IS NOT NULL)),
    CONSTRAINT bkg_waitlist_entries_offer_ordered
        CHECK (offer_expires_at IS NULL OR offer_expires_at > offered_at),
    CONSTRAINT bkg_waitlist_entries_offered_has_an_offer
        CHECK (state <> 'offered' OR offered_at IS NOT NULL),
    -- A live offer holds a place; a resolved entry does not. `confirmed` keeps its hold
    -- because the booking it became *is* that hold.
    CONSTRAINT bkg_waitlist_entries_offered_holds_a_place
        CHECK (state <> 'offered' OR hold_id IS NOT NULL),
    CONSTRAINT bkg_waitlist_entries_confirmed_became_a_booking
        CHECK (state <> 'confirmed' OR booking_id IS NOT NULL),
    CONSTRAINT bkg_waitlist_entries_booking_is_confirmed
        CHECK (booking_id IS NULL OR state = 'confirmed'),
    CONSTRAINT bkg_waitlist_entries_settlement_attributed CHECK (
        (settled_at IS NULL AND settled_by IS NULL AND settle_reason IS NULL
         AND settle_correlation_id IS NULL)
        OR (settled_at IS NOT NULL AND settled_by IS NOT NULL
            AND coalesce(settle_reason, '') ~ '[^[:space:]]'
            AND settle_correlation_id IS NOT NULL)),
    CONSTRAINT bkg_waitlist_entries_settled_is_settled
        CHECK (state NOT IN ('withdrawn', 'declined') OR settled_at IS NOT NULL)
);
-- **One live entry per member per session.** A member in the queue twice would be offered the
-- next two places, and "a member cannot consume the same capacity twice" (paragraph 4144) is
-- as much about the queue as about the hold. Partial, so somebody who withdrew and rejoined is
-- an ordinary case.
--
-- **All three live states**, which `waitlist.LIVE_STATES` is the other half of. The first
-- version named `waiting` and `offered` while the queue counted `expired` as live too, so a
-- member with a lapsed offer *and* a fresh entry held two of three positions -- and the
-- comment in `waitlist.py` asserted this index covered the same three when it covered two.
-- Found by review; the two halves are now one list in each language and the mutation sweep
-- compares them.
CREATE UNIQUE INDEX bkg_waitlist_entries_one_live_per_person
    ON plt01.bkg_waitlist_entries (tenant_id, session_id, person_id)
    WHERE state IN ('waiting', 'offered', 'expired');
-- **One entry per booking**, the other half of the trigger branch above: two confirmed
-- entries could name one booking, which is one seat recorded as two members' promotions.
CREATE UNIQUE INDEX bkg_waitlist_entries_one_per_booking
    ON plt01.bkg_waitlist_entries (tenant_id, booking_id)
    WHERE booking_id IS NOT NULL;
-- The index the promoter reads, in the order `first_come` promotes in.
CREATE INDEX bkg_waitlist_entries_queue
    ON plt01.bkg_waitlist_entries (tenant_id, session_id, tier, joined_at, entry_id)
    WHERE state IN ('waiting', 'offered');
-- The index the expiry sweep reads.
CREATE INDEX bkg_waitlist_entries_expiring
    ON plt01.bkg_waitlist_entries (tenant_id, offer_expires_at) WHERE state = 'offered';
ALTER TABLE plt01.bkg_waitlist_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.bkg_waitlist_entries FORCE ROW LEVEL SECURITY;
CREATE POLICY bkg_waitlist_entries_tenant ON plt01.bkg_waitlist_entries
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **A waitlist entry's hold is for that entry's session and member**, the same control the
-- booking has and for the same reason: nothing else relates the hold to the session or the
-- person on this row, so without it an offer could reserve somebody else's place.
CREATE OR REPLACE FUNCTION plt01.bkg_entry_hold_matches()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    hold_session uuid;
    hold_person uuid;
    hold_status text;
    booked_person uuid;
BEGIN
    -- **The booking check comes before the early return on a null hold**, because a confirmed
    -- entry releases its hold: `hold_id` is NULL exactly when `booking_id` is set, so a check
    -- after the return would never run on the row it is about.
    IF NEW.booking_id IS NOT NULL THEN
        SELECT person_id INTO booked_person
          FROM plt01.bkg_bookings
         WHERE tenant_id = NEW.tenant_id AND booking_id = NEW.booking_id;
        IF booked_person IS NULL THEN
            RAISE EXCEPTION 'this entry cites a booking that does not exist';
        END IF;
        IF booked_person <> NEW.person_id THEN
            RAISE EXCEPTION
                'that booking is another member''s; a confirmed entry became its own';
        END IF;
    END IF;
    IF NEW.hold_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT session_id, person_id, status INTO hold_session, hold_person, hold_status
      FROM plt01.sch_capacity_holds
     WHERE tenant_id = NEW.tenant_id AND hold_id = NEW.hold_id;
    IF hold_session IS NULL THEN
        RAISE EXCEPTION 'a waitlist offer cites a capacity hold that does not exist';
    END IF;
    IF hold_session <> NEW.session_id OR hold_person <> NEW.person_id THEN
        RAISE EXCEPTION
            'this hold is for another member or another session; an offer is the place it '
            'reserves';
    END IF;
    -- **And the place has to still be a place**, which is the branch
    -- `bkg_booking_hold_matches` has and this did not: an `offered` entry could cite a
    -- *released* hold, so `offered_holds_a_place` proved the reference existed rather than
    -- that the seat did. The member was told they had a place, held nothing, and could not
    -- confirm -- which is paragraph 5031 inverted, the exact failure the constraint beside
    -- this trigger is documented as preventing. Found by review.
    IF NEW.state = 'offered' AND hold_status <> 'held' THEN
        RAISE EXCEPTION
            'this hold is % and is not a place anybody has; an offer reserves a live place',
            hold_status;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER bkg_waitlist_entries_hold_matches
    BEFORE INSERT OR UPDATE ON plt01.bkg_waitlist_entries
    FOR EACH ROW EXECUTE FUNCTION plt01.bkg_entry_hold_matches();

-- **A waitlist entry moves only where `waitlist.EDGES` allows.** An expired offer stays in the
-- queue at its own place rather than going to the back, because a member asleep at six in the
-- morning did not decline -- and a *declined* offer is a choice and ends the entry. Encoded
-- here as well as in Python because the service is not the only writer this table could have.
--
-- **`expired -> offered` is the edge the promoter actually takes**, and leaving it out was
-- worse than the defect it was meant to prevent. Both encodings agreed with each other and
-- neither agreed with the service: `next_to_offer` draws from `waiting` *and* `expired`, and
-- an expired entry keeps its `joined_at`, so it sorts first -- which meant that from the
-- moment one member failed to answer an offer, every promotion on that session picked their
-- entry, took a MOD-019 hold, was refused here and rolled back. **Nobody on that waitlist was
-- ever promoted again while places sat free.** Found by review; the `expired -> waiting` edge
-- the first version offered instead is the one nothing in the build ever writes.
CREATE OR REPLACE FUNCTION plt01.bkg_entry_is_one_way()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF OLD.state <> NEW.state AND NOT (
        (OLD.state = 'waiting' AND NEW.state IN ('offered', 'withdrawn', 'lapsed'))
        OR (OLD.state = 'offered' AND NEW.state IN ('confirmed', 'declined', 'expired'))
        OR (OLD.state = 'expired' AND NEW.state IN ('offered', 'waiting', 'lapsed'))
    ) THEN
        RAISE EXCEPTION
            'a waitlist entry does not move from % to %', OLD.state, NEW.state;
    END IF;
    IF OLD.settled_at IS NOT NULL AND (
        NEW.settled_at IS DISTINCT FROM OLD.settled_at
        OR NEW.settled_by IS DISTINCT FROM OLD.settled_by
        OR NEW.settle_reason IS DISTINCT FROM OLD.settle_reason
        OR NEW.settle_correlation_id IS DISTINCT FROM OLD.settle_correlation_id) THEN
        RAISE EXCEPTION 'what happened to this waitlist entry is recorded once';
    END IF;
    -- When they joined is their place in the queue, and the session and member are what the
    -- entry is. Moving any of them would re-order the queue after the fact.
    IF NEW.joined_at <> OLD.joined_at OR NEW.session_id <> OLD.session_id
       OR NEW.person_id <> OLD.person_id THEN
        RAISE EXCEPTION
            'a waitlist entry keeps its place in the queue, its session and its member';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER bkg_waitlist_entries_one_way
    BEFORE UPDATE ON plt01.bkg_waitlist_entries
    FOR EACH ROW EXECUTE FUNCTION plt01.bkg_entry_is_one_way();

-- ------------------------------------------------- cancellations, no-shows and appeals
--
-- The Cancellation entity. **Insert-only**, because it is the record of what a member was told
-- they owe: a cancellation that could be relabelled in-time is a fee nobody can dispute and a
-- late one that could be erased is a policy nobody can enforce.
CREATE TABLE plt01.bkg_cancellations (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    cancellation_id uuid NOT NULL DEFAULT gen_random_uuid(),
    booking_id uuid NOT NULL,
    person_id uuid NOT NULL,
    -- `cancelled_in_time`, `cancelled_late` or `session_cancelled`, decided by
    -- `app.booking.policy.cancellation_is_late` against the policy the booking snapshotted.
    occasion text NOT NULL,
    -- The hours the policy demanded and the hours actually given, both recorded: the decision
    -- is reconstructible from the row without re-reading a policy that may have moved on.
    policy_hours integer NOT NULL,
    hours_given integer NOT NULL,
    fee_due boolean NOT NULL,
    credit_forfeit boolean NOT NULL,
    -- Prose, because why somebody cancelled is a sentence they write. The *declared* occasion
    -- above is what the arithmetic reads.
    reason text NOT NULL,
    cancelled_at timestamptz NOT NULL DEFAULT now(),
    cancelled_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, cancellation_id),
    -- One cancellation per booking: a booking is cancelled once, and the one-way trigger above
    -- is what makes that true of the booking too.
    UNIQUE (tenant_id, booking_id),
    FOREIGN KEY (tenant_id, booking_id)
        REFERENCES plt01.bkg_bookings (tenant_id, booking_id),
    FOREIGN KEY (tenant_id, person_id) REFERENCES plt01.ppl_persons (tenant_id, person_id),
    CONSTRAINT bkg_cancellations_occasion
        CHECK (occasion IN ('cancelled_in_time', 'cancelled_late', 'session_cancelled')),
    -- **No bound on `policy_hours` here.** It has to equal the booking's own policy's
    -- `cancellation_hours`, which `bkg_policies_cancellation_sane` already bounds at 0 to 168 --
    -- so a hand-written bound on this copy is subsumed by the trigger and has no isolating
    -- case: a reviewer found it had none even before the trigger existed. The rules file
    -- settles it: a bound on a derived column is usually implied by the bounds on what it is
    -- derived from, and the primitive statement is the one to keep.
    -- Negative hours given is a cancellation after the session started, which is a real and
    -- common case -- so the floor is well below zero rather than at it.
    CONSTRAINT bkg_cancellations_hours_given_sane
        CHECK (hours_given >= -8760 AND hours_given <= 8760),
    CONSTRAINT bkg_cancellations_reason_not_blank CHECK (reason ~ '[^[:space:]]'),
    -- **A cancellation the gym caused costs the member nothing.** Stated as a constraint
    -- rather than left to the service: a `session_cancelled` row carrying a fee is a member
    -- charged for a class the gym called off, which is the worst row this table could hold.
    CONSTRAINT bkg_cancellations_gym_cancellation_is_free
        CHECK (occasion <> 'session_cancelled' OR (fee_due = false AND credit_forfeit = false)),
    CONSTRAINT bkg_cancellations_in_time_is_free
        CHECK (occasion <> 'cancelled_in_time' OR (fee_due = false AND credit_forfeit = false))
);
CREATE INDEX bkg_cancellations_by_person
    ON plt01.bkg_cancellations (tenant_id, person_id, cancelled_at DESC);
ALTER TABLE plt01.bkg_cancellations ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.bkg_cancellations FORCE ROW LEVEL SECURITY;
CREATE POLICY bkg_cancellations_tenant ON plt01.bkg_cancellations
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- The NoShowRecord entity. **Insert-only, and the count is its sum.** A `no_show_count` column
-- on the member would be MOD-018's cached balance applied to a sanction: two authorities on how
-- many times somebody missed a class, with the disagreement deciding whether they are struck.
CREATE TABLE plt01.bkg_no_shows (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    no_show_id uuid NOT NULL DEFAULT gen_random_uuid(),
    booking_id uuid NOT NULL,
    person_id uuid NOT NULL,
    session_id uuid NOT NULL,
    fee_due boolean NOT NULL,
    credit_forfeit boolean NOT NULL,
    -- `none`, `warning` or `strike`, decided by `app.booking.consequence.decide`.
    sanction text NOT NULL,
    -- The count this decision was made against, so the row says why it was a strike rather
    -- than leaving a reader to recount against a policy that may have changed.
    no_show_count integer NOT NULL,
    policy_warn_after integer NOT NULL,
    policy_strike_after integer NOT NULL,
    -- Set by an upheld appeal. The record stays -- the member did miss the class -- and what
    -- the appeal changes is whether it counts against them.
    overturned_at timestamptz,
    overturned_by uuid,
    overturn_appeal_id uuid,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    recorded_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, no_show_id),
    UNIQUE (tenant_id, booking_id),
    FOREIGN KEY (tenant_id, booking_id)
        REFERENCES plt01.bkg_bookings (tenant_id, booking_id),
    FOREIGN KEY (tenant_id, person_id) REFERENCES plt01.ppl_persons (tenant_id, person_id),
    FOREIGN KEY (tenant_id, session_id)
        REFERENCES plt01.sch_sessions (tenant_id, session_id),
    -- **The sanction domain lives in `sanction_follows_the_count` and nowhere else.** A
    -- separate `sanction IN (...)` CHECK was subsumed by it -- the disjunction names all
    -- three values, so every value outside them violates both and the domain had no
    -- isolating case and could not have one. The rules file settles this: one constraint that
    -- is the stronger statement beats two where the weaker is permanently unprovable. Deleted
    -- rather than tested harder, which is MOD-016's `cat_eligibility_rules_kind`.
    CONSTRAINT bkg_no_shows_count_positive
        CHECK (no_show_count >= 1 AND no_show_count <= 10000),
    -- **No bounds on the two thresholds here either**, for the same reason: they have to
    -- equal the booking's own policy's, where `bkg_policies_warn_positive`,
    -- `bkg_policies_strike_positive` and `bkg_policies_strike_follows_warning` hold. All
    -- three copies here were found to have no isolating case -- each was answered by
    -- `sanction_follows_the_count` or by its sibling -- and the trigger now subsumes them
    -- outright.
    -- **The sanction agrees with the count and the policy on the row.** Without this, a row
    -- could say `strike` on a first no-show under a policy that strikes after three -- which
    -- is a sanction with no stated basis, and the row is the only basis there is.
    CONSTRAINT bkg_no_shows_sanction_follows_the_count CHECK (
        (sanction = 'strike' AND no_show_count >= policy_strike_after)
        OR (sanction = 'warning' AND no_show_count >= policy_warn_after
            AND no_show_count < policy_strike_after)
        OR (sanction = 'none' AND no_show_count < policy_warn_after)),
    CONSTRAINT bkg_no_shows_overturn_attributed CHECK (
        (overturned_at IS NULL AND overturned_by IS NULL AND overturn_appeal_id IS NULL)
        OR (overturned_at IS NOT NULL AND overturned_by IS NOT NULL
            AND overturn_appeal_id IS NOT NULL))
);
CREATE INDEX bkg_no_shows_by_person
    ON plt01.bkg_no_shows (tenant_id, person_id, recorded_at DESC)
    WHERE overturned_at IS NULL;
ALTER TABLE plt01.bkg_no_shows ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.bkg_no_shows FORCE ROW LEVEL SECURITY;
CREATE POLICY bkg_no_shows_tenant ON plt01.bkg_no_shows
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- The Appeal entity. **Two acts and two parties.** MOD-016's review found a separation of
-- duties no stricter check could rescue, because the request and the approval were one insert
-- and there was no second act to compare against. So the request creates the row and only a
-- decision fills the decision columns, and the constraint below refuses a decider who is the
-- subject -- which the service also derives rather than accepting.
CREATE TABLE plt01.bkg_appeals (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    appeal_id uuid NOT NULL DEFAULT gen_random_uuid(),
    subject_person_id uuid NOT NULL,
    -- What is being appealed, and the record it is against. Exactly one of the two, because an
    -- appeal with neither is about nothing and one with both is two appeals.
    no_show_id uuid,
    cancellation_id uuid,
    against text NOT NULL,
    grounds text NOT NULL,
    state text NOT NULL DEFAULT 'open',
    decided_at timestamptz,
    -- **The deciding identity and the person it is**, where that identity has a person record.
    -- Both, because the constraint compares the *person* -- an identity id would let one
    -- member decide their own appeal from a second login.
    decided_by uuid,
    decided_by_person_id uuid,
    decision_note text,
    decide_correlation_id uuid,
    raised_at timestamptz NOT NULL DEFAULT now(),
    raised_by uuid NOT NULL,
    idempotency_key text NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, appeal_id),
    UNIQUE (tenant_id, idempotency_key),
    FOREIGN KEY (tenant_id, subject_person_id)
        REFERENCES plt01.ppl_persons (tenant_id, person_id),
    FOREIGN KEY (tenant_id, no_show_id)
        REFERENCES plt01.bkg_no_shows (tenant_id, no_show_id),
    FOREIGN KEY (tenant_id, cancellation_id)
        REFERENCES plt01.bkg_cancellations (tenant_id, cancellation_id),
    FOREIGN KEY (tenant_id, decided_by_person_id)
        REFERENCES plt01.ppl_persons (tenant_id, person_id),
    CONSTRAINT bkg_appeals_against
        CHECK (against IN ('fee', 'credit_forfeit', 'warning', 'strike')),
    CONSTRAINT bkg_appeals_state
        CHECK (state IN ('open', 'upheld', 'rejected', 'withdrawn')),
    CONSTRAINT bkg_appeals_grounds_not_blank CHECK (grounds ~ '[^[:space:]]'),
    CONSTRAINT bkg_appeals_key_not_blank CHECK (idempotency_key ~ '[^[:space:]]'),
    CONSTRAINT bkg_appeals_is_about_one_thing
        CHECK ((no_show_id IS NULL) <> (cancellation_id IS NULL)),
    -- A decided appeal names who decided it, when, and why. The decision is the evidence, and
    -- MOD-008 audits denials rather than allowed acts, so this row is the only record.
    CONSTRAINT bkg_appeals_decision_attributed CHECK (
        (decided_at IS NULL AND decided_by IS NULL AND decision_note IS NULL
         AND decide_correlation_id IS NULL)
        OR (decided_at IS NOT NULL AND decided_by IS NOT NULL
            AND coalesce(decision_note, '') ~ '[^[:space:]]'
            AND decide_correlation_id IS NOT NULL)),
    -- **A decision names the person who made it**, which is what makes the constraint below
    -- more than opt-in. `decided_by_person_id` was nullable and nothing required it, so a
    -- writer could decide an appeal with the subject's own login and simply leave the person
    -- id out: `decider_is_not_the_subject` compares nothing against NULL, so a member upheld
    -- their own appeal and the no-show was overturned. The control was optional to exactly
    -- the writer it exists for -- "a writer that is not the service", as the comment below
    -- says. Found by review, after `appeals.check_decider` had been hardened on the Python
    -- side and left the schema the weaker of the two layers.
    CONSTRAINT bkg_appeals_decider_is_named
        CHECK ((decided_at IS NULL) = (decided_by_person_id IS NULL)),
    CONSTRAINT bkg_appeals_decided_is_decided
        CHECK ((state IN ('upheld', 'rejected')) = (decided_at IS NOT NULL)),
    -- **A member does not decide their own appeal.** The service derives both sides and this
    -- says it again for a writer that is not the service.
    CONSTRAINT bkg_appeals_decider_is_not_the_subject
        CHECK (decided_by_person_id IS NULL
               OR decided_by_person_id <> subject_person_id),
    CONSTRAINT bkg_appeals_decider_person_needs_a_decision
        CHECK (decided_by_person_id IS NULL OR decided_at IS NOT NULL)
);
CREATE INDEX bkg_appeals_open
    ON plt01.bkg_appeals (tenant_id, raised_at) WHERE state = 'open';
CREATE INDEX bkg_appeals_by_subject
    ON plt01.bkg_appeals (tenant_id, subject_person_id, raised_at DESC);
ALTER TABLE plt01.bkg_appeals ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.bkg_appeals FORCE ROW LEVEL SECURITY;
CREATE POLICY bkg_appeals_tenant ON plt01.bkg_appeals
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **An appeal is decided once, and a decision is final.** A reopened appeal is a sanction
-- nobody can rely on; a second look is a second appeal with its own decider.
CREATE OR REPLACE FUNCTION plt01.bkg_appeal_is_decided_once()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF OLD.state <> 'open' THEN
        RAISE EXCEPTION
            'this appeal is % and a decided appeal does not change again; a second look is a '
            'second appeal', OLD.state;
    END IF;
    IF NEW.state NOT IN ('upheld', 'rejected', 'withdrawn') THEN
        RAISE EXCEPTION
            'an open appeal is upheld, rejected or withdrawn; % is none of those', NEW.state;
    END IF;
    IF NEW.subject_person_id <> OLD.subject_person_id
       OR NEW.against <> OLD.against
       OR NEW.no_show_id IS DISTINCT FROM OLD.no_show_id
       OR NEW.cancellation_id IS DISTINCT FROM OLD.cancellation_id THEN
        RAISE EXCEPTION
            'an appeal keeps its subject and what it is about; raise another one';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER bkg_appeals_one_way
    BEFORE UPDATE ON plt01.bkg_appeals
    FOR EACH ROW EXECUTE FUNCTION plt01.bkg_appeal_is_decided_once();

-- **An appeal is against a record about its own subject.** Nothing else relates
-- `subject_person_id` to the `person_id` on the no-show or the cancellation, so without this
-- one member could appeal another's strike -- and an upheld one would overturn it.
-- **A sanction and a fee answer to the booking they cite.** These two tables had no trigger at
-- all, and they carry the same shape every other trigger in this file exists for: a pair of
-- caller-supplied ids that nothing relates, on insert-only rows with no UPDATE grant on any
-- figure and no DELETE anywhere -- so a wrong row is permanent and the only remedy is an
-- appeal. A reviewer wrote a strike on a member who had no booking, from a booking they had
-- *attended*, naming a different and cancelled session, under thresholds unrelated to the
-- policy the booking snapshotted; and a late fee on the wrong member for a booking never
-- cancelled, 48 hours ahead of a 12-hour window. `_no_show_count` counts by `person_id`, so
-- the fabricated strike moved the victim's threshold immediately.
--
-- **And the free-cancellation constraints were reachable past by declaring the other
-- occasion.** `gym_cancellation_is_free` refuses a `session_cancelled` row carrying a fee and
-- binds only the declared word: a booking the *gym* released, written up as the member's own
-- late cancellation, was charged. Relating `occasion` to `bkg_bookings.state` is what makes
-- that constraint mean what its comment says.
--
-- The service derives all of this correctly. The exposure is the writer every trigger here is
-- for -- a migration, a repair script, the DDL role.
CREATE OR REPLACE FUNCTION plt01.bkg_no_show_matches_its_booking()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    b_person uuid;
    b_session uuid;
    b_state text;
    b_policy uuid;
    p_warn integer;
    p_strike integer;
BEGIN
    SELECT person_id, session_id, state, policy_id
      INTO b_person, b_session, b_state, b_policy
      FROM plt01.bkg_bookings
     WHERE tenant_id = NEW.tenant_id AND booking_id = NEW.booking_id;
    IF b_person IS NULL THEN
        RAISE EXCEPTION 'a no-show cites a booking that does not exist';
    END IF;
    IF b_person <> NEW.person_id THEN
        RAISE EXCEPTION
            'this booking is another member''s; a no-show is recorded against the member '
            'whose booking it was';
    END IF;
    IF b_session <> NEW.session_id THEN
        RAISE EXCEPTION 'this booking is not on that session';
    END IF;
    IF b_state <> 'no_show' THEN
        RAISE EXCEPTION
            'this booking is %, so there is no no-show to record; the booking is settled '
            'first and the record follows it', b_state;
    END IF;
    -- **The thresholds are the ones the booking was made under.** Recorded on the row so the
    -- decision is reconstructible without re-reading a policy that may have moved on -- which
    -- is only worth anything if they are the policy's.
    SELECT warn_after_no_shows, strike_after_no_shows INTO p_warn, p_strike
      FROM plt01.bkg_policies
     WHERE tenant_id = NEW.tenant_id AND policy_id = b_policy;
    IF NEW.policy_warn_after <> p_warn OR NEW.policy_strike_after <> p_strike THEN
        RAISE EXCEPTION
            'these thresholds are not the ones this booking was made under (% and %)',
            p_warn, p_strike;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER bkg_no_shows_matches_its_booking
    BEFORE INSERT ON plt01.bkg_no_shows
    FOR EACH ROW EXECUTE FUNCTION plt01.bkg_no_show_matches_its_booking();

CREATE OR REPLACE FUNCTION plt01.bkg_cancellation_matches_its_booking()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    b_person uuid;
    b_state text;
    b_policy uuid;
    p_hours integer;
BEGIN
    SELECT person_id, state, policy_id INTO b_person, b_state, b_policy
      FROM plt01.bkg_bookings
     WHERE tenant_id = NEW.tenant_id AND booking_id = NEW.booking_id;
    IF b_person IS NULL THEN
        RAISE EXCEPTION 'a cancellation cites a booking that does not exist';
    END IF;
    IF b_person <> NEW.person_id THEN
        RAISE EXCEPTION
            'this booking is another member''s; a cancellation is recorded against the '
            'member whose booking it was';
    END IF;
    -- **`released` is the gym''s act and `cancelled` is the member''s.** The occasion has to
    -- agree with which of the two happened, or `gym_cancellation_is_free` is a constraint
    -- about a word rather than about what the gym did.
    IF NEW.occasion = 'session_cancelled' AND b_state <> 'released' THEN
        RAISE EXCEPTION
            'this booking is %, not released: a session the gym cancelled releases its '
            'bookings and this records that', b_state;
    END IF;
    IF NEW.occasion <> 'session_cancelled' AND b_state <> 'cancelled' THEN
        RAISE EXCEPTION
            'this booking is %, so there is no member cancellation to record', b_state;
    END IF;
    SELECT cancellation_hours INTO p_hours
      FROM plt01.bkg_policies
     WHERE tenant_id = NEW.tenant_id AND policy_id = b_policy;
    IF NEW.policy_hours <> p_hours THEN
        RAISE EXCEPTION
            'this window is not the one this booking was made under (%)', p_hours;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER bkg_cancellations_matches_its_booking
    BEFORE INSERT ON plt01.bkg_cancellations
    FOR EACH ROW EXECUTE FUNCTION plt01.bkg_cancellation_matches_its_booking();

CREATE OR REPLACE FUNCTION plt01.bkg_appeal_subject_matches()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    record_person uuid;
BEGIN
    -- **"Exactly one record" is the CHECK's job, not this trigger's.** A BEFORE INSERT trigger
    -- runs before every CHECK on the table, so raising here on a row that names neither record
    -- made `bkg_appeals_is_about_one_thing` unprovable: its case was refused by this function
    -- and passed for the wrong reason. Returning early leaves the CHECK as the only thing in
    -- the way, which is what gives it an isolating case. Found by the isolation suite on its
    -- first run.
    IF NEW.no_show_id IS NULL AND NEW.cancellation_id IS NULL THEN
        RETURN NEW;
    END IF;
    IF NEW.no_show_id IS NOT NULL THEN
        SELECT person_id INTO record_person FROM plt01.bkg_no_shows
         WHERE tenant_id = NEW.tenant_id AND no_show_id = NEW.no_show_id;
    ELSE
        SELECT person_id INTO record_person FROM plt01.bkg_cancellations
         WHERE tenant_id = NEW.tenant_id AND cancellation_id = NEW.cancellation_id;
    END IF;
    IF record_person IS NULL THEN
        RAISE EXCEPTION 'an appeal cites a record that does not exist';
    END IF;
    IF record_person <> NEW.subject_person_id THEN
        RAISE EXCEPTION
            'this record is about another member; an appeal is about its own subject';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER bkg_appeals_subject_matches
    BEFORE INSERT OR UPDATE ON plt01.bkg_appeals
    FOR EACH ROW EXECUTE FUNCTION plt01.bkg_appeal_subject_matches();

-- ---------------------------------------------------------------- attendance intent
--
-- The AttendanceIntent entity, which paragraph 4141 names as booking's: "Booking owns member
-- reservation/waitlist/cancel/attendance intent." A booking is a place held; an intent is the
-- member *saying* whether they are coming, which is a different fact and arrives later --
-- usually as a reply to MOD-013's reminder.
--
-- **Insert-only, so a change of mind is a new row.** "I am coming" at nine in the morning and
-- "I cannot make it" at five are both true of their day, and overwriting the first would lose
-- the fact that the gym was told twice. The latest row is the current intent and the history is
-- why a tenant can tell a member who always answers from one who never does.
--
-- **This is the signal paragraph 1884 wanted a score from**, and it is a fact rather than a
-- prediction: a member who declared they were not coming is not a no-show risk, they are a
-- place that can be offered to the waitlist. `app/booking/consequence.py` records why no score
-- is computed; this is what makes the absence of one affordable.
CREATE TABLE plt01.bkg_attendance_intents (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    intent_id uuid NOT NULL DEFAULT gen_random_uuid(),
    booking_id uuid NOT NULL,
    person_id uuid NOT NULL,
    -- `attending`, `not_attending` or `unsure`. The third is a real answer and conflating it
    -- with silence would make a member who told the gym they might not come indistinguishable
    -- from one who ignored the message.
    intent text NOT NULL,
    -- How the member said so. `reminder_reply` is MOD-013's channel; `app` is the member's own
    -- surface; `front_desk` is somebody telephoning.
    source text NOT NULL,
    declared_at timestamptz NOT NULL DEFAULT now(),
    declared_by uuid NOT NULL,
    idempotency_key text NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, intent_id),
    UNIQUE (tenant_id, idempotency_key),
    FOREIGN KEY (tenant_id, booking_id)
        REFERENCES plt01.bkg_bookings (tenant_id, booking_id),
    FOREIGN KEY (tenant_id, person_id) REFERENCES plt01.ppl_persons (tenant_id, person_id),
    CONSTRAINT bkg_attendance_intents_intent
        CHECK (intent IN ('attending', 'not_attending', 'unsure')),
    CONSTRAINT bkg_attendance_intents_source
        CHECK (source IN ('app', 'reminder_reply', 'front_desk', 'migration')),
    CONSTRAINT bkg_attendance_intents_key_not_blank
        CHECK (idempotency_key ~ '[^[:space:]]')
);
CREATE INDEX bkg_attendance_intents_latest
    ON plt01.bkg_attendance_intents (tenant_id, booking_id, declared_at DESC);
ALTER TABLE plt01.bkg_attendance_intents ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.bkg_attendance_intents FORCE ROW LEVEL SECURITY;
CREATE POLICY bkg_attendance_intents_tenant ON plt01.bkg_attendance_intents
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **An intent is the member's own about their own booking.** Nothing else relates
-- `person_id` here to the `person_id` on the booking, so without this one member could declare
-- another's attendance -- and a tenant acting on it would offer somebody's place away.
CREATE OR REPLACE FUNCTION plt01.bkg_intent_booking_matches()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    booking_person uuid;
    booking_state text;
BEGIN
    SELECT person_id, state INTO booking_person, booking_state
      FROM plt01.bkg_bookings
     WHERE tenant_id = NEW.tenant_id AND booking_id = NEW.booking_id;
    IF booking_person IS NULL THEN
        RAISE EXCEPTION 'an attendance intent cites a booking that does not exist';
    END IF;
    IF booking_person <> NEW.person_id THEN
        RAISE EXCEPTION
            'this booking is another member''s; an intent is about one''s own place';
    END IF;
    IF booking_state <> 'booked' THEN
        RAISE EXCEPTION
            'this booking is % and its attendance is already settled', booking_state;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER bkg_attendance_intents_booking_matches
    BEFORE INSERT ON plt01.bkg_attendance_intents
    FOR EACH ROW EXECUTE FUNCTION plt01.bkg_intent_booking_matches();

-- ---------------------------------------------------------------- privileges
--
-- **Four of the seven tables carry no UPDATE grant at all**, and each is a record of something
-- a member was told: the cancellation and its fee, the no-show and its sanction (apart from an
-- upheld appeal's overturn), and every attendance intent. A record that could be edited is one
-- nobody can rely on in the dispute it exists for -- MOD-018's argument for a posted journal.
--
-- No runtime role holds DELETE, TRUNCATE or REFERENCES anywhere here, and nothing is granted to
-- PUBLIC. The column lists are compared *as sets and per role* by the isolation suite, because
-- a hand-written list of the columns that matter is not a pin -- and because this module's
-- defining control is an *absence*: there is no seat count, no `no_show_count` on a member and
-- no `risk_score` anywhere, and an absence is exactly what a later migration restores.

GRANT SELECT, INSERT ON plt01.bkg_policies TO veyro_cp_app, veyro_cp_worker;
-- The name and the retirement. **Not the rules**: a booking snapshots the policy by reference,
-- so editing a live version in place would change the terms of every booking already made
-- under it -- which is what versioning is for.
GRANT UPDATE (display_name, status, retired_at, retired_by, retire_reason,
              retire_correlation_id)
    ON plt01.bkg_policies TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.bkg_bookings TO veyro_cp_app, veyro_cp_worker;
-- **The lifecycle only.** The place, the member, the session and the policy are what the
-- booking is, and the trigger above refuses a change to any of them even for a writer holding
-- this grant.
GRANT UPDATE (state, checked_in_at, checked_in_by, checkin_source, checkin_correlation_id,
              settled_at, cancelled_at, cancelled_by, cancellation_reason,
              cancel_correlation_id)
    ON plt01.bkg_bookings TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.bkg_waitlist_entries TO veyro_cp_app, veyro_cp_worker;
-- The offer, the resolution and the booking it became. **Not `joined_at`**: that is the
-- member's place in the queue, and moving it re-orders the queue after the fact.
GRANT UPDATE (state, hold_id, offered_at, offer_expires_at, offer_correlation_id,
              offers_made, settled_at, settled_by, settle_reason, settle_correlation_id,
              booking_id)
    ON plt01.bkg_waitlist_entries TO veyro_cp_app, veyro_cp_worker;

-- **No UPDATE.** What a member was told they owe is what they were told.
GRANT SELECT, INSERT ON plt01.bkg_cancellations TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.bkg_no_shows TO veyro_cp_app, veyro_cp_worker;
-- **The overturn and nothing else.** An upheld appeal stops a no-show counting against the
-- member; it does not unsay that they missed the class, so the record and its figures stay.
GRANT UPDATE (overturned_at, overturned_by, overturn_appeal_id)
    ON plt01.bkg_no_shows TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.bkg_appeals TO veyro_cp_app, veyro_cp_worker;
-- The decision. **Not the grounds and not the subject**: the member's own words and what they
-- are appealing are what the decision was made about.
GRANT UPDATE (state, decided_at, decided_by, decided_by_person_id, decision_note,
              decide_correlation_id)
    ON plt01.bkg_appeals TO veyro_cp_app, veyro_cp_worker;

-- **No UPDATE.** A change of mind is a new row, which is what makes the history of who answers
-- a reminder readable at all.
GRANT SELECT, INSERT ON plt01.bkg_attendance_intents TO veyro_cp_app, veyro_cp_worker;

-- The trigger functions are not SECURITY DEFINER and their `search_path` is pinned, so a
-- runtime role cannot reach them to redefine one -- `CREATE OR REPLACE` needs CREATE on the
-- schema, which no runtime role holds.
REVOKE ALL ON FUNCTION plt01.bkg_booking_hold_matches() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.bkg_booking_is_one_way() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.bkg_entry_hold_matches() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.bkg_entry_is_one_way() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.bkg_appeal_is_decided_once() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.bkg_appeal_subject_matches() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.bkg_intent_booking_matches() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.bkg_no_show_matches_its_booking() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.bkg_cancellation_matches_its_booking() FROM PUBLIC;

-- MOD-020 / ADM-SCH-07: a cancellation names what the members get. ADR-0016.
--
-- Two facts the slice-14 schema could not express, and both were found by reading the canvas
-- against the tables rather than by a reviewer.
--
-- **A booking can be the replacement for one the gym cancelled.** `bkg_bookings.source_kind`
-- says how the member came to be booked, and its own comment explains why `waitlist` is a
-- separate value from `member`: "a promotion is a different conversation and a report of how
-- a class filled needs it". A member moved off a class the gym called off is a different
-- conversation again -- and without the pointer, "which booking replaced which" is answerable
-- only from prose in a cancellation reason.
--
-- **A goodwill grant had no idempotency of any kind.** `mem_entitlement_grants` carries no
-- idempotency key and no unique rule beyond its primary key, which was invisible for as long
-- as the only writers granted one right to one named member. ADM-SCH-07 grants eighteen in one
-- command, so a retry after a timeout would hand every member a second credit. ADR-0016 D7:
-- the answer is what the data means rather than a caller's string.

-- ------------------------------------------------- a booking that replaces another

ALTER TABLE plt01.bkg_bookings
    ADD COLUMN moved_from_booking_id uuid;

COMMENT ON COLUMN plt01.bkg_bookings.moved_from_booking_id IS
    'The booking this one replaces, where the gym cancelled a session and moved the member '
    'to another. NULL for every other booking, which is why it is nullable rather than NOT '
    'NULL with a backfill: a member who booked a class themselves replaced nothing.';

ALTER TABLE plt01.bkg_bookings
    DROP CONSTRAINT bkg_bookings_source_kind;

ALTER TABLE plt01.bkg_bookings
    ADD CONSTRAINT bkg_bookings_source_kind
        CHECK (source_kind IN ('member', 'waitlist', 'front_desk', 'migration', 'moved'));

ALTER TABLE plt01.bkg_bookings
    ADD CONSTRAINT bkg_bookings_predecessor_fk
        FOREIGN KEY (tenant_id, moved_from_booking_id)
        REFERENCES plt01.bkg_bookings (tenant_id, booking_id);

-- **Both halves, because either alone is a worse row than none.** A `moved` booking with no
-- predecessor is a member the product says was moved from nothing; a predecessor on any other
-- source kind is a pointer no reader of `source_kind` would consult. This build's own
-- most-repeated finding is a column one half of a control writes and nothing relates.
ALTER TABLE plt01.bkg_bookings
    ADD CONSTRAINT bkg_bookings_moved_names_its_predecessor
        CHECK ((source_kind = 'moved') = (moved_from_booking_id IS NOT NULL));

-- **There is deliberately no `<> booking_id` CHECK**, and the reason is this repository's own
-- judgement about a constraint subsumed by a sibling. On the INSERT path the row's own id does
-- not exist yet, so the trigger below answers "cites a booking that does not exist"; on an
-- UPDATE by the table owner it answers "that booking is on this same session". Either way the
-- CHECK has no isolating case and could not be given one, which is MOD-016's reason for
-- deleting a kind domain its operand constraint already named.

-- **The predecessor is the same member, on another session.** The foreign key proves the row
-- exists and says nothing about whose it is or where -- MOD-021's rule, which this build has
-- paid for in a certificate chain and in a commissioning record: "a pair of caller-supplied
-- ids that nothing relates is two halves of a control". Citing another member's booking would
-- attribute somebody else's cancelled class to this one; citing a booking on the *same*
-- session would be a member moved to the class they were already on, which makes the figures
-- the screen discloses wrong.
--
-- **No lock, and the reason is that there is nothing to race.** `bkg_bookings` carries
-- SELECT and INSERT and no UPDATE grant at all on `session_id` or `person_id`, so the two
-- values this reads cannot move under it. A `FOR UPDATE` here would need the UPDATE privilege
-- the role does not hold, which is MOD-009's finding, and would buy nothing.
CREATE OR REPLACE FUNCTION plt01.bkg_booking_predecessor_matches()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    was_person uuid;
    was_session uuid;
BEGIN
    IF NEW.moved_from_booking_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT person_id, session_id INTO was_person, was_session
      FROM plt01.bkg_bookings
     WHERE tenant_id = NEW.tenant_id AND booking_id = NEW.moved_from_booking_id;
    IF was_person IS NULL THEN
        RAISE EXCEPTION 'a moved booking cites a booking that does not exist';
    END IF;
    IF was_person <> NEW.person_id THEN
        RAISE EXCEPTION
            'that booking is another member''s; a move replaces the member''s own place';
    END IF;
    IF was_session = NEW.session_id THEN
        RAISE EXCEPTION
            'that booking is on this same session; a move goes to another one';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION plt01.bkg_booking_predecessor_matches() FROM PUBLIC;

CREATE TRIGGER bkg_bookings_predecessor_matches
    BEFORE INSERT OR UPDATE ON plt01.bkg_bookings
    FOR EACH ROW EXECUTE FUNCTION plt01.bkg_booking_predecessor_matches();

-- Finding a member's replacement booking from the one it replaced, which is the direction a
-- cancellation's own report reads: eighteen predecessors, and what each member got.
CREATE INDEX bkg_bookings_by_predecessor
    ON plt01.bkg_bookings (tenant_id, moved_from_booking_id)
    WHERE moved_from_booking_id IS NOT NULL;

-- ------------------------------------------------- one goodwill credit per source

-- **ADR-0016 D7.** One goodwill grant per person per policy per source: for ADM-SCH-07 that is
-- "a member gets one class credit for one cancelled class", so a command that grants eighteen
-- is safe to retry by construction rather than by the client remembering a key.
--
-- **Partial on the source, deliberately.** A free-standing goodwill gesture names no source and
-- is outside the index: a tenant may legitimately give the same person two unrelated credits,
-- and refusing the second would make the index a rule about generosity rather than about
-- retries.
--
-- **Partial on the status too**, which is `0025`'s precedent: a revoked grant frees its slot,
-- because a credit revoked by mistake has to be re-grantable. `exhausted` and `expired` do
-- not -- the member had their credit and it ran out, and a second one would be a new gesture
-- with its own source.
CREATE UNIQUE INDEX mem_entitlement_grants_one_goodwill_per_source
    ON plt01.mem_entitlement_grants (tenant_id, person_id, policy_id, source_id)
    WHERE source_kind = 'goodwill' AND source_id IS NOT NULL AND status <> 'revoked';

-- ------------------------------------------------- a cancelled class lapses its queue

-- **`lapsed` was a declared state nothing wrote** (ADR-0016 D9), and the gap it left is this
-- screen's: cancelling a session leaves the three people on its waitlist reading `waiting` for
-- a class that will never run, and an `offered` entry reading as an offer whose hold the
-- cancellation has already released. `waitlist.py`'s own comment says `lapsed` is "where an
-- entry goes when the session it was waiting for is cancelled" -- this is the writer.
--
-- The state machine admitted `waiting -> lapsed` and `expired -> lapsed` and not
-- `offered -> lapsed`, so the one entry that *has* a place could not be settled at all. The
-- two encodings -- `waitlist.EDGES` and this trigger -- are compared against each other by a
-- test, because MOD-020's worst shipped defect was the two agreeing with each other and
-- neither agreeing with the service.
CREATE OR REPLACE FUNCTION plt01.bkg_entry_is_one_way()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF OLD.state <> NEW.state AND NOT (
        (OLD.state = 'waiting' AND NEW.state IN ('offered', 'withdrawn', 'lapsed'))
        OR (OLD.state = 'offered' AND NEW.state IN ('confirmed', 'declined', 'expired',
                                                    'lapsed'))
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

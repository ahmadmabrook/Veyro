-- MOD-008 IAM-03-R06: the audit log's integrity, verified against the rows `isolation.sql` left.
--
-- **This runs after `isolation.sql`, on purpose.** The `MUTATE` hook in `verify_db.sh` applies
-- before any migration's data exists, so a tamper expressed there hits an empty table and proves
-- nothing. `TAMPER` applies between the two files, which is the only point at which a deletion
-- or an edit can be aimed at a real chain. That distinction was found by a mutation test that
-- passed when it should have failed.
--
-- Insert-only grants make the log write-once for the application. This file is about the other
-- half of IAM-03's control -- "integrity-protected" -- which has to mean something when the
-- person editing the table is an administrator with direct database access. The chain cannot
-- stop them. It stops them doing it quietly.
--
-- **What it does not catch, stated plainly: truncation from the end.** An actor who deletes the
-- newest entries *and* moves `iam.audit_chain_heads` to match leaves a log that is internally
-- consistent -- linked, contiguous, correctly anchored, head in agreement -- because every value
-- the verifier compares lives in the same database the actor already controls. This was found by
-- tamper-testing, not reasoned about afterwards, and it is not fixable from inside: closing it
-- needs the head digest published somewhere the database cannot reach, on a schedule, so that a
-- shortened log can be compared against a witness. That is an operational control this
-- repository does not have, and CLAUDE.md records it as a gap rather than this file implying
-- otherwise.
--
-- **Two verifiers, and they catch different things.** This file walks the stored digests and so
-- catches a deletion from the middle (a gap), a rewritten link, a rewritten anchor and a
-- deletion from the end (the head disagrees). It does **not** recompute a digest from an entry's
-- content, so an edit made together with a matching digest passes here and is caught only by
-- `app.authorization.service.verify_audit_chain`, which recomputes every one. The `TAMPER` hook
-- in `verify_db.sh` exercises this file; the content case is covered by
-- `test_authorization_api.py::test_editing_an_entry_behind_the_application_is_detected` and by
-- `test_every_stored_field_is_covered_by_the_digest` in the domain suite.

\set ON_ERROR_STOP on
\set tenant_a '11111111-1111-4111-8111-111111111111'

BEGIN;
SET LOCAL ROLE veyro_iam_app;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
DO $$
DECLARE
    broken bigint;
    highest bigint;
    entries bigint;
    head_sequence bigint;
    head_digest bytea;
BEGIN
    SELECT count(*) INTO entries FROM iam.audit_events;
    IF entries = 0 THEN
        RAISE EXCEPTION 'AUDIT CHAIN FAILED: no entries to verify, so this file proves nothing';
    END IF;

    -- 1. Every entry links to the one before it.
    SELECT count(*) INTO broken FROM (
        SELECT e.prev_hash, lag(e.entry_hash) OVER (ORDER BY e.sequence) AS expected
        FROM iam.audit_events e
    ) linked
    WHERE expected IS NOT NULL AND prev_hash IS DISTINCT FROM expected;
    IF broken <> 0 THEN
        RAISE EXCEPTION 'AUDIT CHAIN FAILED: % entries do not link to their predecessor', broken;
    END IF;

    -- 2. No gaps. A deleted entry leaves every surviving link intact, so contiguity is what
    --    catches a deletion from the middle.
    SELECT max(sequence) INTO highest FROM iam.audit_events;
    IF highest <> entries THEN
        RAISE EXCEPTION
            'AUDIT CHAIN FAILED: sequence runs to % but the log holds % entries -- a gap',
            highest, entries;
    END IF;

    -- 3. The chain starts from a fixed anchor rather than from whatever the first writer chose,
    --    so the beginning cannot be rewritten and still verify.
    IF (SELECT prev_hash FROM iam.audit_events WHERE sequence = 1)
       IS DISTINCT FROM decode(repeat('00', 32), 'hex') THEN
        RAISE EXCEPTION 'AUDIT CHAIN FAILED: the chain does not start from the zero digest';
    END IF;

    -- 4. The head agrees with the log. A deletion from the end leaves no gap and breaks no link,
    --    so the head is what notices it.
    SELECT sequence, head_hash INTO head_sequence, head_digest
    FROM iam.audit_chain_heads;
    IF head_sequence IS NULL THEN
        RAISE EXCEPTION 'AUDIT CHAIN FAILED: the log has entries but no head';
    END IF;
    IF head_sequence <> highest THEN
        RAISE EXCEPTION 'AUDIT CHAIN FAILED: head is at % but the log ends at %',
            head_sequence, highest;
    END IF;
    IF head_digest IS DISTINCT FROM
       (SELECT entry_hash FROM iam.audit_events WHERE sequence = highest) THEN
        RAISE EXCEPTION 'AUDIT CHAIN FAILED: the head digest is not the last entry''s';
    END IF;
END $$;
ROLLBACK;

\echo 'audit chain: linked, contiguous, anchored, head agrees'

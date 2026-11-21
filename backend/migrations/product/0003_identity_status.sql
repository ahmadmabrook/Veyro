-- MOD-007 IAM-01: the evidence an identity status change leaves behind.
--
-- **`iam.identities.status` was read by four controls and written by nothing.** The column
-- admits `active`, `suspended` and `deactivated`; `authenticate`, the risk challenge, the
-- recovery path and `_session_by_token` each refuse an identity that is not `active`, which
-- is a complete control on the read side -- and no service function, no route and no job ever
-- set it. So two of the three declared states were unreachable, which is MOD-012's "a column
-- implying a control nobody implemented" and MOD-020's "a declared state nothing writes", in
-- the module whose subject is who may sign in.
--
-- **Found by building ADM-STF-01.** The staff list composes the employment state with the
-- login state precisely because the design says why that column exists -- "a departed
-- employee with a live login is visible rather than discovered" -- and the screen could show
-- an owner the finding while the product offered no way to act on it. Revoking a role
-- assignment stops what somebody can *do* and not that they can sign in.
--
-- This migration is the half the schema has to carry: `iam.auth_events` is the insert-only
-- record of everything that happens to an identity, its `kind` is a closed set, and a status
-- change could not be recorded at all without being named here. Writing the row is the
-- service's job and `set_identity_status` does it inside the transaction that moves the
-- column, so an identity cannot be suspended with no record of who did it -- this build's
-- most-repeated finding, seven modules running.

ALTER TABLE iam.auth_events DROP CONSTRAINT auth_events_kind;

ALTER TABLE iam.auth_events ADD CONSTRAINT auth_events_kind CHECK (kind IN (
    'identity.created', 'authentication.succeeded', 'authentication.failed',
    'session.revoked', 'session.rotated', 'passkey.registered', 'passkey.revoked',
    'risk.challenge.required', 'step_up.succeeded', 'device.revoked', 'identity.locked',
    'identity.linked', 'recovery.used', 'recovery.codes_issued', 'password.changed',
    'device.trusted', 'device.readmission_refused',
    -- The three acts this migration exists for. One kind per act rather than one
    -- `identity.status_changed` carrying the new value in `reason`, because that is the
    -- vocabulary's own shape: `device.revoked` and `device.trusted` are two kinds for two
    -- directions of one column, and a reader filtering the log for "who was shut out" should
    -- not have to parse a free-text field to find out.
    'identity.suspended', 'identity.deactivated', 'identity.reinstated'
));

COMMENT ON CONSTRAINT auth_events_kind ON iam.auth_events IS
    'The closed set of things that happen to an identity. A kind that is not here cannot be '
    'recorded, which is why adding a status writer needed a migration: the evidence has to be '
    'nameable before the act can be allowed.';

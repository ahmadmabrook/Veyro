-- MOD-007 IAM-01-R01..R07 identity plane: identities, credentials, passkeys, devices, sessions.
--
-- Every tenant-bound table repeats the four protections documented at the head of
-- `../tenant/0001_organization_hierarchy.sql`, with one difference: the policy names
-- `veyro_iam_app`, not the control-plane roles. No control-plane role is granted anything here
-- and `veyro_iam_app` is granted nothing in `plt01` or `plt01_platform`, so a bug in a
-- configuration or billing path cannot reach a credential hash. Checks 27 and 28 assert both
-- directions rather than trusting this paragraph.
--
-- Three things in this file are security decisions, not schema decisions, and each is written
-- where the column is so it cannot drift from the code:
--
--   * **No secret is stored in a form that can be read back.** Passwords and recovery codes are
--     scrypt hashes with a per-credential salt. Session tokens are stored only as a SHA-256
--     digest -- the token itself exists in the response that created it and nowhere else, so a
--     dump of this schema does not let anyone log in. Passkey public keys are stored because
--     they are public.
--   * **TOTP is deliberately absent.** A TOTP factor requires storing a shared secret that must
--     be read back to verify a code, which means encryption at rest with a key from the vault
--     TSD paragraph 1151 requires and this repository does not have. The algorithm is
--     implemented and tested in `app/identity/secrets.py` against the RFC 6238 vectors; the
--     column to hold the secret is the part that is missing, and it stays missing until there is
--     somewhere safe to put it.
--   * **`iam.auth_events` is insert-only.** It is the record of who authenticated, what failed
--     and what was revoked. A role that could edit it could erase its own traces.

-- IAM-01-R01 links one human to identities in several tenants through `person_id`. There is
-- deliberately **no `persons` table**. A foreign key to one would secure nothing: any tenant can
-- name any `person_id` it likes, existing or not, and the constraint would allow it either way.
-- What it would cost is a table with no tenant column that every identity row points at -- a
-- cross-tenant surface disclosing the platform-wide identity count, in exchange for rejecting
-- links to ids nobody ever created, which are indistinguishable in effect from links to a person
-- with no other identities. So the column stands alone and defaults to a fresh uuid.
CREATE TABLE iam.identities (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    identity_id uuid NOT NULL DEFAULT gen_random_uuid(),
    person_id uuid NOT NULL DEFAULT gen_random_uuid(),
    email_normalized text,
    phone_normalized text,
    display_name text NOT NULL,
    status text NOT NULL DEFAULT 'active',
    failed_attempts integer NOT NULL DEFAULT 0,
    locked_until timestamptz,
    -- Recovery carries its own budget, deliberately separate from the password one. A password
    -- lockout must not block recovery -- being locked out is the reason people reach for a
    -- recovery code -- but recovery itself still has to be bounded, or it is an unlimited
    -- guessing oracle costing one scrypt per stored code per attempt. One counter could not do
    -- both jobs.
    recovery_failed_attempts integer NOT NULL DEFAULT 0,
    recovery_locked_until timestamptz,
    version bigint NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, identity_id),
    UNIQUE (tenant_id, email_normalized),
    UNIQUE (tenant_id, phone_normalized),
    CONSTRAINT identities_status CHECK (status IN ('active', 'suspended', 'deactivated')),
    -- An identity nobody can address is an identity nobody can authenticate or recover.
    CONSTRAINT identities_has_an_identifier CHECK
        (email_normalized IS NOT NULL OR phone_normalized IS NOT NULL),
    CONSTRAINT identities_failed_attempts CHECK (failed_attempts >= 0),
    CONSTRAINT identities_recovery_attempts CHECK (recovery_failed_attempts >= 0),
    CONSTRAINT identities_version_positive CHECK (version > 0)
);
ALTER TABLE iam.identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.identities FORCE ROW LEVEL SECURITY;
CREATE POLICY identities_tenant ON iam.identities
    FOR ALL TO veyro_iam_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE iam.credentials (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    credential_id uuid NOT NULL DEFAULT gen_random_uuid(),
    identity_id uuid NOT NULL,
    kind text NOT NULL,
    algorithm text NOT NULL,
    salt bytea NOT NULL,
    secret_hash bytea NOT NULL,
    params jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz,
    consumed_at timestamptz,
    revoked_at timestamptz,
    PRIMARY KEY (tenant_id, credential_id),
    FOREIGN KEY (tenant_id, identity_id)
        REFERENCES iam.identities (tenant_id, identity_id),
    CONSTRAINT credentials_kind CHECK (kind IN ('password', 'recovery_code')),
    CONSTRAINT credentials_status CHECK (status IN ('active', 'consumed', 'revoked')),
    CONSTRAINT credentials_algorithm CHECK (algorithm = 'scrypt'),
    -- Length floors, so a truncated or placeholder value cannot be stored as if it were a hash.
    -- They do not make a weak hash strong; they make an obviously broken one impossible.
    CONSTRAINT credentials_salt_length CHECK (octet_length(salt) >= 16),
    CONSTRAINT credentials_hash_length CHECK (octet_length(secret_hash) >= 32),
    CONSTRAINT credentials_consumed_at CHECK ((status = 'consumed') = (consumed_at IS NOT NULL)),
    CONSTRAINT credentials_revoked_at CHECK ((status = 'revoked') = (revoked_at IS NOT NULL))
);
ALTER TABLE iam.credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.credentials FORCE ROW LEVEL SECURITY;
CREATE POLICY credentials_tenant ON iam.credentials
    FOR ALL TO veyro_iam_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- One active password per identity. Two would mean either could log in, and revoking the one
-- the user knows about would leave the other working.
CREATE UNIQUE INDEX credentials_one_active_password
    ON iam.credentials (tenant_id, identity_id)
    WHERE kind = 'password' AND status = 'active';

CREATE TABLE iam.passkeys (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    passkey_id uuid NOT NULL DEFAULT gen_random_uuid(),
    identity_id uuid NOT NULL,
    webauthn_credential_id bytea NOT NULL,
    public_key bytea NOT NULL,
    -- An authenticator that reports a sign count must never report one it has already used: a
    -- repeat or a regression is the documented signal that the credential has been cloned. The
    -- column exists so the check in `app/identity/policy.py` has something to compare against.
    sign_count bigint NOT NULL DEFAULT 0,
    aaguid uuid,
    transports text[],
    backed_up boolean NOT NULL DEFAULT false,
    label text,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz,
    revoked_at timestamptz,
    PRIMARY KEY (tenant_id, passkey_id),
    FOREIGN KEY (tenant_id, identity_id)
        REFERENCES iam.identities (tenant_id, identity_id),
    UNIQUE (tenant_id, webauthn_credential_id),
    CONSTRAINT passkeys_sign_count CHECK (sign_count >= 0),
    CONSTRAINT passkeys_credential_id_length CHECK (octet_length(webauthn_credential_id) >= 16),
    CONSTRAINT passkeys_public_key_length CHECK (octet_length(public_key) >= 32)
);
ALTER TABLE iam.passkeys ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.passkeys FORCE ROW LEVEL SECURITY;
CREATE POLICY passkeys_tenant ON iam.passkeys
    FOR ALL TO veyro_iam_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE iam.devices (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    device_id uuid NOT NULL DEFAULT gen_random_uuid(),
    identity_id uuid NOT NULL,
    fingerprint text NOT NULL,
    label text,
    platform text,
    trusted boolean NOT NULL DEFAULT false,
    trusted_at timestamptz,
    -- A device row is created the first time it is seen, which is *before* its risk challenge is
    -- answered. Until `confirmed_at` is set it does not count as known, so repeating a challenged
    -- login cannot promote the device by the act of being retried.
    confirmed_at timestamptz,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    revoked_reason text,
    PRIMARY KEY (tenant_id, device_id),
    FOREIGN KEY (tenant_id, identity_id)
        REFERENCES iam.identities (tenant_id, identity_id),
    UNIQUE (tenant_id, identity_id, fingerprint),
    CONSTRAINT devices_trusted_at CHECK (trusted = (trusted_at IS NOT NULL)),
    CONSTRAINT devices_revoked_reason CHECK
        ((revoked_at IS NULL) = (revoked_reason IS NULL))
);
ALTER TABLE iam.devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.devices FORCE ROW LEVEL SECURITY;
CREATE POLICY devices_tenant ON iam.devices
    FOR ALL TO veyro_iam_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE iam.sessions (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    session_id uuid NOT NULL DEFAULT gen_random_uuid(),
    identity_id uuid NOT NULL,
    device_id uuid,
    -- The SHA-256 of the bearer token and nothing else. The token is returned once, by the call
    -- that creates the session, and is never recoverable from this schema. A plain digest is the
    -- right primitive here rather than scrypt: the token is 256 bits of CSPRNG output, so there
    -- is no dictionary to slow down, and a login path has to be fast.
    token_hash bytea NOT NULL,
    aal smallint NOT NULL DEFAULT 1,
    -- The factor kinds that were **verified** to open this session, so a later step-up can tell
    -- whether a newly presented factor is a second one or the same kind again. Without it the
    -- service would have to assume how the session began, and "two passwords" would read as
    -- multi-factor.
    factors text[] NOT NULL DEFAULT '{}',
    issued_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    last_seen_at timestamptz,
    rotated_from uuid,
    revoked_at timestamptz,
    revoke_reason text,
    PRIMARY KEY (tenant_id, session_id),
    FOREIGN KEY (tenant_id, identity_id)
        REFERENCES iam.identities (tenant_id, identity_id),
    FOREIGN KEY (tenant_id, device_id) REFERENCES iam.devices (tenant_id, device_id),
    FOREIGN KEY (tenant_id, rotated_from) REFERENCES iam.sessions (tenant_id, session_id),
    UNIQUE (tenant_id, token_hash),
    CONSTRAINT sessions_expires_after_issue CHECK (expires_at > issued_at),
    -- IAM-01-R06's assurance levels: 1 routine, 2 stepped up for financial or privileged work,
    -- 3 hardware-backed and verifier-impersonation-resistant.
    CONSTRAINT sessions_aal CHECK (aal BETWEEN 1 AND 3),
    CONSTRAINT sessions_token_hash_length CHECK (octet_length(token_hash) = 32),
    CONSTRAINT sessions_revoke_reason CHECK ((revoked_at IS NULL) = (revoke_reason IS NULL))
);
ALTER TABLE iam.sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.sessions FORCE ROW LEVEL SECURITY;
CREATE POLICY sessions_tenant ON iam.sessions
    FOR ALL TO veyro_iam_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE INDEX sessions_by_identity ON iam.sessions (tenant_id, identity_id, issued_at);

-- A rotated session must not be rotated twice: the second use of an already-rotated token is the
-- classic stolen-refresh-token signal, and the service revokes the whole chain when it sees one.
CREATE UNIQUE INDEX sessions_rotated_from_once
    ON iam.sessions (tenant_id, rotated_from) WHERE rotated_from IS NOT NULL;

CREATE TABLE iam.challenges (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    challenge_id uuid NOT NULL DEFAULT gen_random_uuid(),
    identity_id uuid NOT NULL,
    kind text NOT NULL,
    nonce_hash bytea NOT NULL,
    -- The device that drew this challenge, so answering it confirms **that** device and no
    -- other. Without the binding, confirmation has to guess from `last_seen_at`, and an attacker
    -- holding the password can keep their own device most-recently-seen and have the victim's
    -- answer whitelist it. Nullable because a step-up challenge is about the session, not a
    -- device.
    device_id uuid,
    required_aal smallint,
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, challenge_id),
    FOREIGN KEY (tenant_id, identity_id)
        REFERENCES iam.identities (tenant_id, identity_id),
    FOREIGN KEY (tenant_id, device_id) REFERENCES iam.devices (tenant_id, device_id),
    UNIQUE (tenant_id, nonce_hash),
    CONSTRAINT challenges_kind CHECK
        (kind IN ('step_up', 'risk', 'recovery', 'passkey_registration', 'passkey_assertion')),
    CONSTRAINT challenges_nonce_hash_length CHECK (octet_length(nonce_hash) = 32),
    CONSTRAINT challenges_required_aal CHECK (required_aal IS NULL OR required_aal BETWEEN 1 AND 3)
);
ALTER TABLE iam.challenges ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.challenges FORCE ROW LEVEL SECURITY;
CREATE POLICY challenges_tenant ON iam.challenges
    FOR ALL TO veyro_iam_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE iam.auth_events (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    event_id uuid NOT NULL DEFAULT gen_random_uuid(),
    -- Nullable: a failed attempt against an address that matches no identity is exactly the
    -- event worth recording, and there is no identity to attribute it to. A composite foreign
    -- key is satisfied when any of its columns is NULL, so containment still holds when it is
    -- not.
    identity_id uuid,
    kind text NOT NULL,
    outcome text NOT NULL,
    factor text,
    device_id uuid,
    session_id uuid,
    reason text,
    correlation_id uuid NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, event_id),
    FOREIGN KEY (tenant_id, identity_id)
        REFERENCES iam.identities (tenant_id, identity_id),
    CONSTRAINT auth_events_outcome CHECK (outcome IN ('succeeded', 'failed')),
    CONSTRAINT auth_events_kind CHECK (kind IN (
        'identity.created', 'authentication.succeeded', 'authentication.failed',
        'session.revoked', 'session.rotated', 'passkey.registered', 'passkey.revoked',
        'risk.challenge.required', 'step_up.succeeded', 'device.revoked', 'identity.locked',
        'identity.linked', 'recovery.used', 'recovery.codes_issued', 'password.changed',
        'device.trusted', 'device.readmission_refused'
    ))
);
ALTER TABLE iam.auth_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.auth_events FORCE ROW LEVEL SECURITY;
CREATE POLICY auth_events_tenant ON iam.auth_events
    FOR ALL TO veyro_iam_app
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE INDEX auth_events_by_identity ON iam.auth_events (tenant_id, identity_id, occurred_at);

-- Only the identity role, and no DELETE, TRUNCATE or REFERENCES anywhere.
GRANT SELECT, INSERT, UPDATE ON iam.identities TO veyro_iam_app;
GRANT SELECT, INSERT, UPDATE ON iam.credentials TO veyro_iam_app;
GRANT SELECT, INSERT, UPDATE ON iam.passkeys TO veyro_iam_app;
GRANT SELECT, INSERT, UPDATE ON iam.devices TO veyro_iam_app;
GRANT SELECT, INSERT, UPDATE ON iam.sessions TO veyro_iam_app;
GRANT SELECT, INSERT, UPDATE ON iam.challenges TO veyro_iam_app;

-- The audit trail. Insert and read only: a role that could edit this could erase the record of
-- its own authentication failures, which is the first thing an attacker would want.
GRANT SELECT, INSERT ON iam.auth_events TO veyro_iam_app;

-- MOD-013 ENG-02: notification templates, preferences, channel policies, notifications,
-- deliveries, suppressions and digests. Tables are module-prefixed `ntf_`.
--
-- Every table repeats the four protections documented at the head of
-- `0001_organization_hierarchy.sql`: tenant-leading primary key, ENABLE plus FORCE row level
-- security, the `current_setting('app.tenant_id', true)` predicate that is NULL when no context
-- is set, and composite foreign keys carrying `tenant_id` into every parent -- including the
-- reference to `plt01_platform.tenants`. Checks 55 to 60 sweep all of it from the catalogue,
-- seat both runtime roles, compare every foreign key as a set and every UPDATE column grant per
-- role, and carry a case for every CHECK constraint -- the full shape the last three review
-- rounds arrived at, written in from the start rather than added afterwards.
--
-- Six decisions are specific to this module.
--
--   * **No column here is for a contact address**, and three free-text columns will hold one
--     anyway. `ntf_suppressions`, `ntf_notifications` and `ntf_recipient_channels` carry a
--     SHA-256 digest of `channel:address`, never the address, so a bounce can be remembered
--     and a recipient matched without a second copy of everyone's email beside the one MOD-007
--     and MOD-014 own. MOD-009's objection to a shadow database is that the copies disagree
--     and only one is reachable by an erasure; a digest is reachable by neither and needs to
--     be. The reasoning is in `app/notifications/delivery.py`.
--
--     The header used to say "this module holds no contact address", and a reviewer disproved
--     it with the ordinary content of a bounce: `ntf_suppressions.detail`,
--     `ntf_deliveries.last_error` and `ntf_deliveries.provider_ref` are free text a dispatcher
--     supplies, and `550 5.1.1 <jane@example.com>: Recipient address rejected` is what a
--     provider actually sends. MOD-010's rule -- the restricted-field check reads declared
--     *names*, and a value carries anything. All three are declared in `SUBJECT_COLUMNS` with
--     the mechanism their grants support, the delivery events no longer carry the text at all,
--     and check 58 pins every column list because the control is an absence.
--
--   * **A recipient and an address digest are bound to each other.** `ntf_recipient_channels`
--     is the whole reason a suppression recorded against a digest is reachable from a later
--     request for that person: both keys arrive from the caller, the preference and the cap
--     are keyed on one and the suppression list on the other, and before this table nothing
--     related them, so each half of every control failed open. Neither key can be verified
--     against a real address here -- there is none on this plane -- so what is enforced is
--     correspondence and stability, in both directions.
--
--   * **The category is the separation paragraph 2463 asks for.** A template declares one, the
--     category decides whether a consent record is required before a notification may be
--     requested at all, and only `coaching` and `marketing` may be switched off by a
--     recipient's preference -- so a tenant can always tell somebody their payment failed.
--     `ntf_preferences_optional_categories_only` is that rule as a constraint.
--
--   * **One delivery row per notification and channel**, which is paragraph 2464's control
--     against a provider's own retry: a dispatcher that timed out and retried settles the row
--     it already holds. The request side is deduplicated separately, by `idempotency_key`.
--
--   * **A published template version is immutable, by privilege and by trigger.** The same pair
--     MOD-012 ended up with: column-scoped grants for the lifecycle, and a trigger refusing any
--     write to a non-draft version -- because the threat is a changed body or a new variable,
--     and a grant cannot see the parent's status. `status` is itself in the UPDATE grant, so
--     the trigger also refuses `published -> draft`: without that the immutability was a
--     two-step -- demote (no content moves), rewrite, publish again -- leaving the attacker's
--     text under the original approver's name and timestamp, with the separation of duties on
--     content bypassed entirely. Found by review; check 59 runs the three statements.
--
--   * **A notification snapshots the rendered text.** The template may be retired or superseded
--     tomorrow; what was sent is what somebody will ask about, and re-rendering it later from a
--     newer version would answer a different question.

-- ---------------------------------------------------------------- templates

CREATE TABLE plt01.ntf_templates (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    template_id uuid NOT NULL DEFAULT gen_random_uuid(),
    template_key text NOT NULL,
    version bigint NOT NULL,
    -- A template is identified by key, category, channel and locale together, and a later
    -- version may change none of them: a category that moved from `transactional` to
    -- `marketing` would have notifications already sent under the old consent rules, and a
    -- move the other way would let a campaign ride on a receipt's exemption from opt-out.
    category text NOT NULL,
    channel text NOT NULL,
    locale text NOT NULL,
    subject text NOT NULL DEFAULT '',
    body text NOT NULL,
    variables text[] NOT NULL DEFAULT '{}',
    status text NOT NULL DEFAULT 'draft',
    -- Paragraph 2456 asks for approval. An approver who is the author is not an approval, which
    -- `ntf_templates_approver_is_not_the_author` enforces -- MOD-008's separation of duties,
    -- applied to the content that goes out under a tenant's name.
    authored_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    approved_at timestamptz,
    approved_by uuid,
    published_at timestamptz,
    retired_at timestamptz,
    PRIMARY KEY (tenant_id, template_id),
    -- **Versions are per (key, channel, locale), not per key.** One key is one *message*,
    -- and the same message has an email version, an SMS version and an Icelandic version --
    -- so a channel fallback can find the text written for the channel it falls back *to*.
    -- A unique index on (key, version) alone forced one channel per key and made a fallback
    -- carry an email subject onto an SMS, which `ntf_notifications_subject_matches_channel`
    -- refused outright. Found by this module's own tests before review saw it.
    UNIQUE (tenant_id, template_key, channel, locale, version),
    CONSTRAINT ntf_templates_key_shape
        CHECK (template_key ~ '^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*)*$'),
    CONSTRAINT ntf_templates_version_positive CHECK (version > 0),
    CONSTRAINT ntf_templates_category
        CHECK (category IN ('transactional', 'operational', 'coaching', 'marketing')),
    CONSTRAINT ntf_templates_channel
        CHECK (channel IN ('email', 'sms', 'whatsapp', 'push', 'in_app')),
    CONSTRAINT ntf_templates_locale_shape CHECK (locale ~ '^[a-z]{2,3}(-[A-Z]{2})?$'),
    CONSTRAINT ntf_templates_body_not_blank CHECK (length(btrim(body)) > 0),
    -- Only email shows a subject. One on an SMS is text that goes nowhere, and its author
    -- expects it to be read.
    CONSTRAINT ntf_templates_subject_matches_channel CHECK (
        (channel = 'email') = (length(btrim(subject)) > 0)),
    CONSTRAINT ntf_templates_status CHECK (status IN ('draft', 'published', 'retired')),
    CONSTRAINT ntf_templates_approval_attributed CHECK (
        (approved_at IS NULL) = (approved_by IS NULL)),
    CONSTRAINT ntf_templates_approver_is_not_the_author CHECK (
        approved_by IS NULL OR approved_by <> authored_by),
    -- Publication requires an approval, which is what makes the approval a control rather than
    -- a field: paragraph 2456 lists preview and approval beside versioning.
    CONSTRAINT ntf_templates_published_is_approved CHECK (
        status <> 'published' OR (published_at IS NOT NULL AND approved_at IS NOT NULL)),
    CONSTRAINT ntf_templates_retired_at CHECK
        ((status = 'retired') = (retired_at IS NOT NULL))
);
CREATE INDEX ntf_templates_lookup
    ON plt01.ntf_templates (tenant_id, template_key, channel, locale, status);
ALTER TABLE plt01.ntf_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ntf_templates FORCE ROW LEVEL SECURITY;
CREATE POLICY ntf_templates_tenant ON plt01.ntf_templates
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- A published version is immutable. This trigger is the UPDATE half of that and only that:
-- there is no INSERT trigger, and DELETE is carried by the absence of a grant -- the comment
-- used to credit this function with both, which a reviewer corrected. The grant cannot see the
-- parent's status, and the threat is a changed body or a new variable on a template
-- notifications are already being authored from -- MOD-012's finding, which this module
-- inherits rather than rediscovers. It also refuses `published -> draft`, because `status` is
-- itself in the grant and without that the immutability is a two-step.
CREATE FUNCTION plt01.ntf_templates_body_is_draft_only() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog, plt01
AS $$
BEGIN
    -- **A published template cannot go back to being a draft.** `status` is in the UPDATE
    -- grant, so without this the immutability below is a two-step: set the status to `draft`
    -- (permitted, content unchanged), then rewrite the body (permitted, `OLD.status` is now
    -- `draft`). Found by review, reasoning from the grant rather than from the trigger.
    IF OLD.status <> 'draft' AND NEW.status = 'draft' THEN
        RAISE EXCEPTION 'a published template cannot return to draft'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.status <> 'draft'
       AND (NEW.body, NEW.subject, NEW.variables, NEW.category, NEW.channel, NEW.locale)
           IS DISTINCT FROM
           (OLD.body, OLD.subject, OLD.variables, OLD.category, OLD.channel, OLD.locale) THEN
        RAISE EXCEPTION 'a published template version cannot be changed'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.published_at IS NOT NULL AND NEW.published_at IS DISTINCT FROM OLD.published_at THEN
        RAISE EXCEPTION 'a publication date cannot be changed'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.retired_at IS NOT NULL AND NEW.retired_at IS DISTINCT FROM OLD.retired_at THEN
        RAISE EXCEPTION 'a retirement cannot be undone or moved'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;
REVOKE EXECUTE ON FUNCTION plt01.ntf_templates_body_is_draft_only() FROM PUBLIC;
CREATE TRIGGER ntf_templates_draft_only BEFORE UPDATE ON plt01.ntf_templates
    FOR EACH ROW EXECUTE FUNCTION plt01.ntf_templates_body_is_draft_only();

-- **One key is one message, so one key is one category.** A key whose email version is
-- transactional and whose SMS version is marketing would change what a fallback is allowed to
-- do -- paragraph 2463's separation defeated by a fallback. The service checks this with a
-- SELECT, which two concurrent creates of a new key both pass under READ COMMITTED; a
-- constraint cannot see other rows, so this is the one place the module needs a trigger for a
-- cross-row rule.
CREATE FUNCTION plt01.ntf_templates_one_category_per_key() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog, plt01
AS $$
DECLARE
    sibling text;
BEGIN
    SELECT category INTO sibling FROM plt01.ntf_templates
    WHERE tenant_id = NEW.tenant_id AND template_key = NEW.template_key
      AND template_id <> NEW.template_id
    LIMIT 1;
    IF sibling IS NOT NULL AND sibling <> NEW.category THEN
        RAISE EXCEPTION 'template key % is already %, not %',
            NEW.template_key, sibling, NEW.category
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;
REVOKE EXECUTE ON FUNCTION plt01.ntf_templates_one_category_per_key() FROM PUBLIC;
CREATE TRIGGER ntf_templates_one_category BEFORE INSERT ON plt01.ntf_templates
    FOR EACH ROW EXECUTE FUNCTION plt01.ntf_templates_one_category_per_key();

-- ---------------------------------------------------------------- preferences

CREATE TABLE plt01.ntf_preferences (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    preference_id uuid NOT NULL DEFAULT gen_random_uuid(),
    -- The person this is about, as an identity on the `iam` plane. No foreign key: the planes
    -- are separate and neither role can reach the other's schema, which is the same
    -- unenforceable reference MOD-009's `subject_id` carries and for the same reason.
    recipient_id uuid NOT NULL,
    category text NOT NULL,
    channel text NOT NULL,
    allowed boolean NOT NULL DEFAULT true,
    quiet_from time,
    quiet_until time,
    -- An IANA zone name, supplied rather than inferred: this module has no person record to
    -- read a timezone from, and a quiet hour in the server's zone is a quiet hour for nobody.
    quiet_timezone text,
    daily_cap integer,
    digest_mode text NOT NULL DEFAULT 'immediate',
    set_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, preference_id),
    UNIQUE (tenant_id, recipient_id, category, channel),
    CONSTRAINT ntf_preferences_category
        CHECK (category IN ('transactional', 'operational', 'coaching', 'marketing')),
    CONSTRAINT ntf_preferences_channel
        CHECK (channel IN ('email', 'sms', 'whatsapp', 'push', 'in_app')),
    CONSTRAINT ntf_preferences_digest_mode
        CHECK (digest_mode IN ('immediate', 'hourly', 'daily')),
    CONSTRAINT ntf_preferences_cap_not_negative CHECK (daily_cap IS NULL OR daily_cap >= 0),
    CONSTRAINT ntf_preferences_quiet_hours_complete CHECK (
        (quiet_from IS NULL) = (quiet_until IS NULL)
        AND (quiet_from IS NULL OR length(btrim(coalesce(quiet_timezone, ''))) > 0)),
    -- **Only an optional category may be switched off.** A member who mutes marketing still
    -- gets their invoice: a preference that could suppress a transactional message would mean a
    -- tenant unable to tell somebody their payment failed. This is paragraph 2463's separation
    -- in the one place a tenant could otherwise defeat it by accident.
    CONSTRAINT ntf_preferences_optional_categories_only CHECK (
        allowed OR category IN ('coaching', 'marketing'))
);
ALTER TABLE plt01.ntf_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ntf_preferences FORCE ROW LEVEL SECURITY;
CREATE POLICY ntf_preferences_tenant ON plt01.ntf_preferences
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- channel policies

CREATE TABLE plt01.ntf_channel_policies (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    policy_id uuid NOT NULL DEFAULT gen_random_uuid(),
    channel text NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    fallback_channel text,
    -- Paragraph 2460's cost by tenant and channel. An integer in minor units, as every amount
    -- in this repository is; the figure is a tenant's own statement about what a message costs
    -- them, since there is no provider here to bill anybody.
    cost_per_message_minor bigint,
    currency char(3),
    set_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, policy_id),
    UNIQUE (tenant_id, channel),
    CONSTRAINT ntf_channel_policies_channel
        CHECK (channel IN ('email', 'sms', 'whatsapp', 'push', 'in_app')),
    CONSTRAINT ntf_channel_policies_fallback CHECK (
        fallback_channel IS NULL
        OR (fallback_channel IN ('email', 'sms', 'whatsapp', 'push', 'in_app')
            AND fallback_channel <> channel)),
    CONSTRAINT ntf_channel_policies_cost_complete CHECK (
        (cost_per_message_minor IS NULL) = (currency IS NULL)
        AND (cost_per_message_minor IS NULL OR cost_per_message_minor >= 0)),
    CONSTRAINT ntf_channel_policies_currency_shape
        CHECK (currency IS NULL OR currency ~ '^[A-Z]{3}$')
);
ALTER TABLE plt01.ntf_channel_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ntf_channel_policies FORCE ROW LEVEL SECURITY;
CREATE POLICY ntf_channel_policies_tenant ON plt01.ntf_channel_policies
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- notifications

-- The authored notification. Insert-only apart from its own lifecycle: paragraph 2474 says
-- "delivery failure never rewrites the authored message", so the rendered subject and body
-- carry no UPDATE grant at all.
CREATE TABLE plt01.ntf_notifications (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    notification_id uuid NOT NULL DEFAULT gen_random_uuid(),
    template_id uuid NOT NULL,
    -- What the template said when this was rendered. The template may be retired or superseded
    -- tomorrow; what was sent is what somebody will ask about.
    template_key text NOT NULL,
    template_version bigint NOT NULL,
    category text NOT NULL,
    channel text NOT NULL,
    locale text NOT NULL,
    rendered_subject text NOT NULL DEFAULT '',
    rendered_body text NOT NULL,
    recipient_id uuid NOT NULL,
    -- **A digest, never the address.** See the module header.
    address_digest text NOT NULL,
    priority text NOT NULL DEFAULT 'normal',
    -- Paragraph 2461: a critical alert bypasses preferences only under documented policy, so
    -- the bypass names one. **The constraint refuses a blank, not an unverifiable one**:
    -- nothing in the catalogue, the configuration plane or any table establishes that the
    -- reference names a policy that exists. What carries "documented" is the permission --
    -- `notifications.notification.request_critical`, financial class -- after a reviewer
    -- showed the routine one plus the string `x` overriding an opt-out, a quiet window and a
    -- frequency cap together.
    bypass_policy_ref text,
    status text NOT NULL DEFAULT 'requested',
    decision_reason text NOT NULL,
    -- The consent record that permitted a marketing notification, on MOD-009's table. A
    -- foreign key, because that table is on this plane and under this role -- so the one
    -- cross-module reference in this module is one the database can actually enforce.
    consent_record_id uuid,
    -- The caller's own handle. Unique per tenant, which is the request-side half of paragraph
    -- 2464: a caller that asks twice authors one notification.
    idempotency_key text NOT NULL,
    scheduled_for timestamptz,
    requested_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, notification_id),
    FOREIGN KEY (tenant_id, template_id)
        REFERENCES plt01.ntf_templates (tenant_id, template_id),
    FOREIGN KEY (tenant_id, consent_record_id)
        REFERENCES plt01.sec_consent_records (tenant_id, record_id),
    UNIQUE (tenant_id, idempotency_key),
    CONSTRAINT ntf_notifications_category
        CHECK (category IN ('transactional', 'operational', 'coaching', 'marketing')),
    CONSTRAINT ntf_notifications_channel
        CHECK (channel IN ('email', 'sms', 'whatsapp', 'push', 'in_app')),
    CONSTRAINT ntf_notifications_locale_shape CHECK (locale ~ '^[a-z]{2,3}(-[A-Z]{2})?$'),
    CONSTRAINT ntf_notifications_priority CHECK (priority IN ('normal', 'high', 'critical')),
    CONSTRAINT ntf_notifications_status
        CHECK (status IN ('requested', 'deferred', 'digested', 'dispatched', 'suppressed')),
    CONSTRAINT ntf_notifications_body_not_blank CHECK (length(btrim(rendered_body)) > 0),
    CONSTRAINT ntf_notifications_subject_matches_channel CHECK (
        (channel = 'email') = (length(btrim(rendered_subject)) > 0)),
    CONSTRAINT ntf_notifications_digest_shape CHECK (address_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ntf_notifications_idempotency_not_blank
        CHECK (length(btrim(idempotency_key)) > 0),
    CONSTRAINT ntf_notifications_reason_not_blank CHECK (length(btrim(decision_reason)) > 0),
    CONSTRAINT ntf_notifications_critical_names_a_policy CHECK (
        priority <> 'critical' OR length(btrim(coalesce(bypass_policy_ref, ''))) > 0),
    -- A bypass reference on something that is not critical is a field claiming an authority it
    -- does not have.
    CONSTRAINT ntf_notifications_bypass_is_critical_only CHECK (
        bypass_policy_ref IS NULL OR priority = 'critical'),
    -- Marketing needs the consent that permitted it; nothing else may cite one, because a
    -- transactional receipt riding on a marketing consent would make the consent look used.
    CONSTRAINT ntf_notifications_marketing_cites_consent CHECK (
        (category = 'marketing') = (consent_record_id IS NOT NULL)),
    CONSTRAINT ntf_notifications_deferred_is_scheduled CHECK (
        status <> 'deferred' OR scheduled_for IS NOT NULL)
);
CREATE INDEX ntf_notifications_recipient
    ON plt01.ntf_notifications (tenant_id, recipient_id, category, requested_at DESC);
CREATE INDEX ntf_notifications_due
    ON plt01.ntf_notifications (tenant_id, status, scheduled_for);
ALTER TABLE plt01.ntf_notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ntf_notifications FORCE ROW LEVEL SECURITY;
CREATE POLICY ntf_notifications_tenant ON plt01.ntf_notifications
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- deliveries

-- **One row per notification and channel.** That uniqueness is paragraph 2464's control against
-- a provider's own retry: a dispatcher that sent a message, timed out and retried settles the
-- row it already holds rather than creating a second delivery of one authored message.
CREATE TABLE plt01.ntf_deliveries (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    delivery_id uuid NOT NULL DEFAULT gen_random_uuid(),
    notification_id uuid NOT NULL,
    channel text NOT NULL,
    state text NOT NULL DEFAULT 'pending',
    attempts integer NOT NULL DEFAULT 0,
    max_attempts integer NOT NULL DEFAULT 5,
    last_error text,
    next_attempt_at timestamptz,
    -- The provider's own handle for the message, when there is one. There is no provider in
    -- this build, so every value here today came from a caller.
    provider_ref text,
    dispatched_at timestamptz,
    delivered_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, delivery_id),
    FOREIGN KEY (tenant_id, notification_id)
        REFERENCES plt01.ntf_notifications (tenant_id, notification_id),
    UNIQUE (tenant_id, notification_id, channel),
    CONSTRAINT ntf_deliveries_channel
        CHECK (channel IN ('email', 'sms', 'whatsapp', 'push', 'in_app')),
    CONSTRAINT ntf_deliveries_state CHECK (
        state IN ('pending', 'sent', 'delivered', 'failed', 'dead', 'suppressed')),
    CONSTRAINT ntf_deliveries_attempts_sane
        CHECK (attempts >= 0 AND max_attempts >= 1 AND attempts <= max_attempts),
    CONSTRAINT ntf_deliveries_failure_explained CHECK (
        state NOT IN ('failed', 'dead') OR length(btrim(coalesce(last_error, ''))) > 0),
    CONSTRAINT ntf_deliveries_delivered_at CHECK (
        (state = 'delivered') = (delivered_at IS NOT NULL))
);
CREATE INDEX ntf_deliveries_due
    ON plt01.ntf_deliveries (tenant_id, state, next_attempt_at);
ALTER TABLE plt01.ntf_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ntf_deliveries FORCE ROW LEVEL SECURITY;
CREATE POLICY ntf_deliveries_tenant ON plt01.ntf_deliveries
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- suppressions

-- Paragraph 2460's complaint and bounce suppression. Keyed on the digest, so this table is a
-- list of addresses that must not be written to and not a list of addresses.
CREATE TABLE plt01.ntf_suppressions (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    suppression_id uuid NOT NULL DEFAULT gen_random_uuid(),
    channel text NOT NULL,
    address_digest text NOT NULL,
    reason text NOT NULL,
    detail text,
    -- A bounce is reported by a provider and an unsubscribe by the recipient, so the actor is
    -- nullable -- but a *release* always has one, because releasing is a decision.
    recorded_by uuid,
    correlation_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    released_at timestamptz,
    released_by uuid,
    release_reason text,
    release_correlation_id uuid,
    PRIMARY KEY (tenant_id, suppression_id),
    CONSTRAINT ntf_suppressions_channel
        CHECK (channel IN ('email', 'sms', 'whatsapp', 'push', 'in_app')),
    CONSTRAINT ntf_suppressions_digest_shape CHECK (address_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ntf_suppressions_reason
        CHECK (reason IN ('bounced', 'complained', 'unsubscribed')),
    -- **Only an unsubscribe may be released.** A bounce or a complaint is the channel's
    -- judgement about deliverability, and a tenant that could clear those would be choosing to
    -- keep sending to an address that rejected them -- which damages the deliverability of
    -- every other notification, including the transactional ones nobody opted out of.
    CONSTRAINT ntf_suppressions_only_unsubscribes_release CHECK (
        released_at IS NULL OR reason = 'unsubscribed'),
    CONSTRAINT ntf_suppressions_release_attributed CHECK (
        (released_at IS NULL AND released_by IS NULL AND release_reason IS NULL
         AND release_correlation_id IS NULL)
        OR (released_at IS NOT NULL AND released_by IS NOT NULL
            AND release_correlation_id IS NOT NULL
            AND length(btrim(coalesce(release_reason, ''))) > 0))
);
-- One live suppression per channel and address. A second would mean a release that cleared one
-- left the other standing, and the address would read as both suppressed and not.
CREATE UNIQUE INDEX ntf_suppressions_live
    ON plt01.ntf_suppressions (tenant_id, channel, address_digest) WHERE released_at IS NULL;
ALTER TABLE plt01.ntf_suppressions ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ntf_suppressions FORCE ROW LEVEL SECURITY;
CREATE POLICY ntf_suppressions_tenant ON plt01.ntf_suppressions
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- digests

-- A batch of notifications a recipient's preference asked to receive as one. Paragraph 2458's
-- digesting, and the reason a frequency cap is safe to set low: a capped notification is
-- digested rather than dropped, so nothing is lost.
CREATE TABLE plt01.ntf_digests (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    digest_id uuid NOT NULL DEFAULT gen_random_uuid(),
    recipient_id uuid NOT NULL,
    category text NOT NULL,
    channel text NOT NULL,
    window_start timestamptz NOT NULL,
    window_end timestamptz NOT NULL,
    state text NOT NULL DEFAULT 'open',
    notification_count integer NOT NULL DEFAULT 0,
    closed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, digest_id),
    CONSTRAINT ntf_digests_category
        CHECK (category IN ('transactional', 'operational', 'coaching', 'marketing')),
    CONSTRAINT ntf_digests_channel
        CHECK (channel IN ('email', 'sms', 'whatsapp', 'push', 'in_app')),
    CONSTRAINT ntf_digests_window_ordered CHECK (window_end > window_start),
    CONSTRAINT ntf_digests_state CHECK (state IN ('open', 'closed', 'sent')),
    CONSTRAINT ntf_digests_count_not_negative CHECK (notification_count >= 0),
    CONSTRAINT ntf_digests_closed_at CHECK ((state = 'open') = (closed_at IS NULL))
);
-- One open digest per recipient, category, channel and window. Two would split a batch that
-- exists to be one message.
CREATE UNIQUE INDEX ntf_digests_open
    ON plt01.ntf_digests (tenant_id, recipient_id, category, channel, window_start)
    WHERE state = 'open';
ALTER TABLE plt01.ntf_digests ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ntf_digests FORCE ROW LEVEL SECURITY;
CREATE POLICY ntf_digests_tenant ON plt01.ntf_digests
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **Which address digest belongs to which recipient, on each channel.**
--
-- The module is handed two caller-supplied keys per request: a `recipient_id`, which the
-- preference, the quiet window and the frequency cap are keyed on, and an `address_digest`,
-- which the suppression list is keyed on. Both were shape-checked and nothing related them, so
-- every control split cleanly down the middle and each half failed open. Supply a digest that
-- is not the recipient's and the suppression lookup finds nothing, the member who complained
-- is mailed, and the bounce that follows writes a suppression against the junk digest -- the
-- control defeated end to end by one unverified field. Supply a `person_id` where an
-- `identity_id` was meant -- the realistic mistake, and the one MOD-009's review named -- and
-- the preference lookup misses, so the opt-out does not apply while
-- `GET /notifications/preferences` still shows it standing.
--
-- This table makes the two keys answer to each other, in both directions: the primary key
-- fixes one digest per recipient and channel, and `ntf_recipient_channels_one_owner` fixes one
-- recipient per digest and channel. The first binding wins and a contradiction is refused, so
-- a suppression written against a digest is reachable from every later request for that person
-- -- which is the property the suppression list needs and did not have.
--
-- **It cannot verify that a digest is really that person's address**: there is no address on
-- this plane to hash, by design. What it enforces is correspondence and stability, which is
-- what the controls above actually rest on.
--
-- An address does change, so a rebinding exists -- under its own, stronger permission, with an
-- actor and a written reason, because it is the one act that moves a person away from a
-- suppression recorded against them.
CREATE TABLE plt01.ntf_recipient_channels (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    recipient_id uuid NOT NULL,
    channel text NOT NULL,
    address_digest text NOT NULL,
    bound_at timestamptz NOT NULL DEFAULT now(),
    bound_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    rebound_at timestamptz,
    rebound_by uuid,
    rebind_reason text,
    rebind_correlation_id uuid,
    PRIMARY KEY (tenant_id, recipient_id, channel),
    CONSTRAINT ntf_recipient_channels_channel
        CHECK (channel IN ('email', 'sms', 'whatsapp', 'push', 'in_app')),
    CONSTRAINT ntf_recipient_channels_digest_shape
        CHECK (address_digest ~ '^[0-9a-f]{64}$'),
    -- A rebinding carries who, when, why and under which correlation, or none of them. The
    -- btrim is load-bearing: a CHECK passes on NULL, so `length(btrim(rebind_reason)) > 0`
    -- without the coalesce admits the blank reason it exists to refuse -- MOD-009's legal-hold
    -- finding, which this module has now paid for twice.
    CONSTRAINT ntf_recipient_channels_rebind_attributed CHECK (
        (rebound_at IS NULL AND rebound_by IS NULL AND rebind_reason IS NULL
         AND rebind_correlation_id IS NULL)
        OR (rebound_at IS NOT NULL AND rebound_by IS NOT NULL
            AND rebind_correlation_id IS NOT NULL
            AND length(btrim(coalesce(rebind_reason, ''))) > 0))
);
-- One digest belongs to one recipient on a channel. Without this the correspondence holds in
-- one direction only, and the `person_id`-for-`identity_id` case above walks straight past it.
CREATE UNIQUE INDEX ntf_recipient_channels_one_owner
    ON plt01.ntf_recipient_channels (tenant_id, channel, address_digest);
ALTER TABLE plt01.ntf_recipient_channels ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ntf_recipient_channels FORCE ROW LEVEL SECURITY;
CREATE POLICY ntf_recipient_channels_tenant ON plt01.ntf_recipient_channels
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- Which digest a notification was folded into, if any. A separate table rather than a column on
-- the notification, because the notification is insert-only apart from its own lifecycle and
-- this is a fact discovered after it was authored.
CREATE TABLE plt01.ntf_digest_entries (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    digest_id uuid NOT NULL,
    notification_id uuid NOT NULL,
    added_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, digest_id, notification_id),
    FOREIGN KEY (tenant_id, digest_id) REFERENCES plt01.ntf_digests (tenant_id, digest_id),
    FOREIGN KEY (tenant_id, notification_id)
        REFERENCES plt01.ntf_notifications (tenant_id, notification_id),
    -- A notification belongs to at most one digest: two would send it twice, which is the one
    -- thing paragraph 2464 forbids.
    UNIQUE (tenant_id, notification_id)
);
ALTER TABLE plt01.ntf_digest_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ntf_digest_entries FORCE ROW LEVEL SECURITY;
CREATE POLICY ntf_digest_entries_tenant ON plt01.ntf_digest_entries
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- privileges

-- A template moves through draft, approval, publication and retirement. Its content is what it
-- *is*, and the trigger above refuses a content change on a published version even though the
-- grant admits one on a draft.
GRANT SELECT, INSERT ON plt01.ntf_templates TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (subject, body, variables, status, approved_at, approved_by, published_at,
              retired_at)
    ON plt01.ntf_templates TO veyro_cp_app, veyro_cp_worker;

-- A preference is a living setting; that is what it is for.
GRANT SELECT, INSERT ON plt01.ntf_preferences TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (allowed, quiet_from, quiet_until, quiet_timezone, daily_cap, digest_mode,
              set_by, correlation_id, updated_at)
    ON plt01.ntf_preferences TO veyro_cp_app, veyro_cp_worker;
GRANT SELECT, INSERT ON plt01.ntf_channel_policies TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (enabled, fallback_channel, cost_per_message_minor, currency, set_by,
              correlation_id, updated_at)
    ON plt01.ntf_channel_policies TO veyro_cp_app, veyro_cp_worker;

-- **The authored message carries no UPDATE grant.** Paragraph 2474: "delivery failure never
-- rewrites the authored message/notification". The rendered subject, the rendered body, the
-- recipient, the digest of their address, the category and the consent that permitted it are
-- all what was decided at request time; only the status and the schedule move.
GRANT SELECT, INSERT ON plt01.ntf_notifications TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (status, scheduled_for) ON plt01.ntf_notifications
    TO veyro_cp_app, veyro_cp_worker;

-- A delivery settles.
GRANT SELECT, INSERT ON plt01.ntf_deliveries TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (state, attempts, last_error, next_attempt_at, provider_ref, dispatched_at,
              delivered_at)
    ON plt01.ntf_deliveries TO veyro_cp_app, veyro_cp_worker;

-- A suppression is recorded and released. Why it was recorded and against which address are
-- what a complaint investigation reads.
GRANT SELECT, INSERT ON plt01.ntf_suppressions TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (released_at, released_by, release_reason, release_correlation_id)
    ON plt01.ntf_suppressions TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.ntf_digests TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (state, notification_count, closed_at) ON plt01.ntf_digests
    TO veyro_cp_app, veyro_cp_worker;
-- Insert-only: which notifications a digest covered is the digest.
GRANT SELECT, INSERT ON plt01.ntf_digest_entries TO veyro_cp_app, veyro_cp_worker;

-- A binding is created by the first request that uses it and moved only by a rebinding, which
-- is a different permission. `bound_at`, `bound_by` and `correlation_id` carry no UPDATE, so
-- when the binding was first made stays answerable after it has been moved.
GRANT SELECT, INSERT ON plt01.ntf_recipient_channels TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (address_digest, rebound_at, rebound_by, rebind_reason, rebind_correlation_id)
    ON plt01.ntf_recipient_channels TO veyro_cp_app, veyro_cp_worker;

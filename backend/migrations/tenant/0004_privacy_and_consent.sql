-- MOD-009 SEC-01-R05..R08 tenant track: data classification in force, the consent registry,
-- retention policies with legal hold, and data subject requests with their evidence trail.
-- Tables are module-prefixed `sec_` as the other tenant modules are.
--
-- Every table repeats the four protections documented at the head of
-- `0001_organization_hierarchy.sql`: tenant-leading primary key, ENABLE plus FORCE row level
-- security, the `current_setting('app.tenant_id', true)` predicate that is NULL when no context
-- is set, and composite foreign keys carrying `tenant_id` into every parent. Read that file's
-- comment before changing anything here.
--
-- Four decisions are specific to this module and are stated rather than left to be inferred.
--
--   * **These tables live in `plt01`, not in a fourth plane.** MOD-007 earned its own schema and
--     role because a configuration query that could read a credential hash is a different class
--     of mistake. Consent records and retention policies are not secrets; they are evidence
--     about processing, and the thing that has to reach them is the deletion path, which must
--     also reach every other tenant table. A privilege boundary that the deletion path crosses
--     on every single request is a boundary that gets worked around, and a worked-around
--     boundary is worse than none. What protects this data is the same forced RLS as everything
--     else in `plt01`, plus MOD-008's gate in front of every route.
--
--   * **`subject_id` carries no foreign key.** The subject is an identity, and identities live
--     in the `iam` schema which `veyro_cp_app` cannot reach at all -- that separation is
--     deliberate and checked in both directions. A foreign key is therefore not available, and
--     inventing one would mean granting this role access to the identity plane to satisfy a
--     constraint. The column is a bare `uuid`, exactly as `iam.identities.identity_id` is.
--
--     **Nothing in the database checks that a `subject_id` names anybody**, so the check has to
--     live where it costs something to skip. `fulfil_dsar` resolves the subject against the
--     identity plane before it erases anything, because an erasure that matches no row reports
--     success having destroyed nothing -- a controller telling a live member their data is gone
--     while every row is intact. Opening a request, recording consent or placing a hold against
--     an unknown subject is merely a row nobody will read, so those do not resolve. An
--     independent review found the first case; this comment used to claim all of them resolved,
--     which was the `delegated_from` mistake -- a comment asserting a control nobody wrote.
--
--   * **Consent is append-only, and a grant binds one published version.** `sec_consent_records`
--     has no UPDATE and no DELETE grant, so a withdrawal is a new row and never an edit of the
--     grant it withdraws. TSD paragraph 4382 requires a consent record to carry the document
--     version, the signature time, the evidence hash and the withdrawal; a mutable row can carry
--     at most the latest of those, and the legal question is almost always about an earlier one.
--     `sec_consent_versions` is likewise insert-only, so a published document cannot be edited
--     under the feet of the people who already consented to it: a changed document is a new
--     version, and consent to the old version does not carry over.
--
--   * **A legal hold is released once, never deleted, and never un-released.** The table
--     carries a column-level UPDATE on the four release columns only, and no DELETE. A hold
--     that can vanish is not a hold -- the evidence that deletion *was* suspended, and for how
--     long, is the point of recording it -- and a CHECK cannot enforce that, because a CHECK
--     sees one row and not what the row used to be. A released hold could be re-released with a
--     different date, or set back to NULL so it read as never lifted. The trigger below is the
--     one place in this schema that needs to see OLD, and it is there for that reason. The same reasoning gives `sec_dsar_actions` no UPDATE or DELETE at
--     all: it is the record-count and hash evidence that TSD paragraph 4396 requires a deletion
--     job to produce, and evidence that the job can rewrite is not evidence.

-- ---------------------------------------------------------------- processing purposes

-- SEC-01-R05 and TSD paragraph 4389: "Mixed roles are recorded by processing purpose." The
-- controller/processor distinction is per purpose, not per tenant, because one tenant's data is
-- processed under both roles at once -- Veyro is processor for member data on the gym's
-- instructions and controller for its own security and billing data.
CREATE TABLE plt01.sec_processing_purposes (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    purpose_id uuid NOT NULL DEFAULT gen_random_uuid(),
    purpose_code text NOT NULL,
    description text NOT NULL,
    lawful_basis text NOT NULL,
    controller_role text NOT NULL,
    data_classes text[] NOT NULL,
    registered_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    registered_at timestamptz NOT NULL DEFAULT now(),
    -- Retirement is attributed. Registering a purpose records who did it; retiring one withdraws
    -- the stated justification for processing, which is at least as answerable, and the first
    -- version of this table recorded only the timestamp. An independent review named it: the
    -- question somebody is asked later is who, not when.
    retired_at timestamptz,
    retired_by uuid,
    retire_correlation_id uuid,
    PRIMARY KEY (tenant_id, purpose_id),
    CONSTRAINT sec_purposes_code_shape CHECK (purpose_code ~ '^[a-z0-9]+(\.[a-z0-9_]+)*$'),
    -- The six bases of Jordan PDPL No. 24 of 2023, which TSD paragraph 4387 names as the launch
    -- baseline. Not GDPR's list: they overlap heavily but are not the same enumeration, and
    -- writing GDPR's here would be inventing the law this product is held to.
    CONSTRAINT sec_purposes_lawful_basis CHECK (lawful_basis IN (
        'consent', 'contract', 'legal_obligation', 'vital_interest',
        'public_interest', 'legitimate_interest')),
    CONSTRAINT sec_purposes_controller_role CHECK (controller_role IN ('controller', 'processor')),
    -- Both halves matter. An empty array names nothing, so no retention policy and no export
    -- can find the purpose; an element outside the four classes of TSD section 21.2 names a
    -- classification no rule exists for. `<@` on an array containing NULL evaluates to false
    -- rather than NULL, so this refuses `ARRAY[NULL]::text[]` without a three-valued-logic trap.
    CONSTRAINT sec_purposes_classes_known CHECK (
        cardinality(data_classes) > 0
        AND data_classes <@ ARRAY['public', 'internal', 'confidential', 'restricted']::text[]),
    CONSTRAINT sec_purposes_retirement_attributed CHECK (
        (retired_at IS NULL AND retired_by IS NULL AND retire_correlation_id IS NULL)
        OR (retired_at IS NOT NULL AND retired_by IS NOT NULL
            AND retire_correlation_id IS NOT NULL))
);
-- Live codes are unique; a retired purpose keeps its row so the consent that cited it still
-- resolves, and its code can be registered again under a new purpose with a new lawful basis.
CREATE UNIQUE INDEX sec_purposes_live_code
    ON plt01.sec_processing_purposes (tenant_id, purpose_code) WHERE retired_at IS NULL;
ALTER TABLE plt01.sec_processing_purposes ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.sec_processing_purposes FORCE ROW LEVEL SECURITY;
CREATE POLICY sec_processing_purposes_tenant ON plt01.sec_processing_purposes
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- consent

-- SEC-01-R06 names the eight consent kinds this table's CHECK enumerates. They are a closed set
-- on purpose: a tenant that could invent a consent kind could collect a health consent under a
-- name no retention policy and no DSAR export knows about.
CREATE TABLE plt01.sec_consent_definitions (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    definition_id uuid NOT NULL DEFAULT gen_random_uuid(),
    consent_type text NOT NULL,
    purpose_id uuid NOT NULL,
    requires_guardian boolean NOT NULL DEFAULT false,
    withdrawable boolean NOT NULL DEFAULT true,
    defined_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    registered_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, definition_id),
    UNIQUE (tenant_id, consent_type),
    FOREIGN KEY (tenant_id, purpose_id)
        REFERENCES plt01.sec_processing_purposes (tenant_id, purpose_id),
    CONSTRAINT sec_consent_definitions_type CHECK (consent_type IN (
        'terms', 'privacy', 'marketing', 'waiver',
        'health', 'biometrics', 'media', 'data_sharing'))
);
ALTER TABLE plt01.sec_consent_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.sec_consent_definitions FORCE ROW LEVEL SECURITY;
CREATE POLICY sec_consent_definitions_tenant ON plt01.sec_consent_definitions
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- Insert-only. A published consent document is what somebody agreed to, so editing it would
-- silently rewrite the terms of an agreement already made. A changed document is a new version.
CREATE TABLE plt01.sec_consent_versions (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    consent_version_id uuid NOT NULL DEFAULT gen_random_uuid(),
    definition_id uuid NOT NULL,
    version integer NOT NULL,
    language text NOT NULL,
    document_ref text NOT NULL,
    document_hash text NOT NULL,
    effective_from timestamptz NOT NULL,
    published_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    published_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, consent_version_id),
    UNIQUE (tenant_id, definition_id, version, language),
    -- Redundant as a key -- consent_version_id is already unique within the tenant -- and there
    -- so that `sec_consent_records` can reference the pair and bind a record to a version *of
    -- the definition it names*. Without it the record carries two independent references and a
    -- waiver can cite the marketing document: an agreement attributed to a text its signer never
    -- saw, which is the failure the cross-tenant case of this rule already guards against.
    UNIQUE (tenant_id, consent_version_id, definition_id),
    FOREIGN KEY (tenant_id, definition_id)
        REFERENCES plt01.sec_consent_definitions (tenant_id, definition_id),
    CONSTRAINT sec_consent_versions_positive CHECK (version > 0),
    -- The hash identifies the bytes somebody agreed to. The document itself lives outside this
    -- database; the hash is what makes "which text was that" answerable years later.
    CONSTRAINT sec_consent_versions_hash_shape CHECK (document_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT sec_consent_versions_language_shape CHECK (language ~ '^[a-z]{2}(-[A-Z]{2})?$')
);
ALTER TABLE plt01.sec_consent_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.sec_consent_versions FORCE ROW LEVEL SECURITY;
CREATE POLICY sec_consent_versions_tenant ON plt01.sec_consent_versions
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- Insert-only, and the whole consent history of a subject is the set of its rows. Current state
-- is the latest row per (subject, definition) and is derived, never stored: a stored "is
-- consented" flag is a second source of truth that can disagree with the evidence behind it.
CREATE TABLE plt01.sec_consent_records (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    record_id uuid NOT NULL DEFAULT gen_random_uuid(),
    subject_id uuid NOT NULL,
    definition_id uuid NOT NULL,
    consent_version_id uuid NOT NULL,
    action text NOT NULL,
    -- When the subject actually signed, which is not when the row was written. A paper waiver
    -- digitised on Monday was signed on Saturday, and the legal question is about Saturday.
    signed_at timestamptz NOT NULL,
    evidence_hash text,
    evidence_ref text,
    source text NOT NULL,
    guardian_subject_id uuid,
    locale text NOT NULL,
    correlation_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, record_id),
    FOREIGN KEY (tenant_id, definition_id)
        REFERENCES plt01.sec_consent_definitions (tenant_id, definition_id),
    -- Three columns, not two: the version must belong to the definition this record names. The
    -- service already filters candidate versions by definition, but a database that accepts the
    -- mismatch is one SQL path away from recording a health consent against a marketing
    -- document, and the row is insert-only so nobody could correct it.
    FOREIGN KEY (tenant_id, consent_version_id, definition_id)
        REFERENCES plt01.sec_consent_versions (tenant_id, consent_version_id, definition_id),
    CONSTRAINT sec_consent_records_action CHECK (action IN ('granted', 'withdrawn')),
    CONSTRAINT sec_consent_records_source CHECK (source IN (
        'member_app', 'kiosk', 'staff_entry', 'paper_import', 'web', 'api')),
    CONSTRAINT sec_consent_records_evidence_shape
        CHECK (evidence_hash IS NULL OR evidence_hash ~ '^[0-9a-f]{64}$'),
    -- A guardian who is also the subject is a data-entry error that would otherwise read as a
    -- valid minor's consent.
    CONSTRAINT sec_consent_records_guardian_distinct
        CHECK (guardian_subject_id IS NULL OR guardian_subject_id <> subject_id)
);
CREATE INDEX sec_consent_records_subject
    ON plt01.sec_consent_records (tenant_id, subject_id, definition_id, signed_at DESC);
ALTER TABLE plt01.sec_consent_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.sec_consent_records FORCE ROW LEVEL SECURITY;
CREATE POLICY sec_consent_records_tenant ON plt01.sec_consent_records
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- retention and legal hold

-- SEC-01-R08. Retention carries a data class, as TSD paragraph 4385 requires, but the live
-- policy is keyed on resource and region only: a resource has one period, and the class is what
-- that period is justified by rather than a second dimension of the key. `set_retention_policy`
-- retires by the same pair, so the index and the service agree. The period is in days because
-- every source that states one states it in days or months.
CREATE TABLE plt01.sec_retention_policies (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    policy_id uuid NOT NULL DEFAULT gen_random_uuid(),
    resource_type text NOT NULL,
    data_class text NOT NULL,
    retention_days integer NOT NULL,
    legal_basis text NOT NULL,
    region text NOT NULL,
    set_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    set_at timestamptz NOT NULL DEFAULT now(),
    retired_at timestamptz,
    retired_by uuid,
    retire_correlation_id uuid,
    PRIMARY KEY (tenant_id, policy_id),
    CONSTRAINT sec_retention_class CHECK (data_class IN (
        'public', 'internal', 'confidential', 'restricted')),
    -- Zero days is legitimate: "do not retain past the transaction" is a real policy. A negative
    -- period is not, and an unbounded one is written as a policy that does not exist rather than
    -- as a very large number nobody will recognise as meaning "forever".
    CONSTRAINT sec_retention_days_sane CHECK (retention_days >= 0 AND retention_days <= 36500),
    -- The live-policy index is unique on (resource_type, region), so free text defeats it:
    -- 'Consent_Record' and 'consent_record ' are three live policies for one resource and
    -- whichever the service reads first wins. These shapes make the key mean what it says.
    CONSTRAINT sec_retention_resource_shape CHECK (resource_type ~ '^[a-z0-9]+(_[a-z0-9]+)*$'),
    CONSTRAINT sec_retention_region_shape CHECK (region ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    CONSTRAINT sec_retention_retirement_attributed CHECK (
        (retired_at IS NULL AND retired_by IS NULL AND retire_correlation_id IS NULL)
        OR (retired_at IS NOT NULL AND retired_by IS NOT NULL
            AND retire_correlation_id IS NOT NULL))
);
CREATE UNIQUE INDEX sec_retention_live_resource
    ON plt01.sec_retention_policies (tenant_id, resource_type, region) WHERE retired_at IS NULL;
ALTER TABLE plt01.sec_retention_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.sec_retention_policies FORCE ROW LEVEL SECURITY;
CREATE POLICY sec_retention_policies_tenant ON plt01.sec_retention_policies
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- A hold with a NULL subject_id covers the whole tenant, which is what a regulator's or a
-- court's instruction usually looks like. Released, never deleted: see the header.
CREATE TABLE plt01.sec_legal_holds (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    hold_id uuid NOT NULL DEFAULT gen_random_uuid(),
    subject_id uuid,
    resource_type text,
    reason text NOT NULL,
    reference text NOT NULL,
    placed_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    placed_at timestamptz NOT NULL DEFAULT now(),
    released_at timestamptz,
    release_reason text,
    released_by uuid,
    release_correlation_id uuid,
    PRIMARY KEY (tenant_id, hold_id),
    CONSTRAINT sec_legal_holds_reason_not_blank CHECK (reason ~ '[^[:space:]]'),
    CONSTRAINT sec_legal_holds_reference_not_blank CHECK (reference ~ '[^[:space:]]'),
    -- A release without a reason is indistinguishable from a mistake, and without an actor it
    -- is unanswerable: releasing a hold is the single act that un-blocks destruction of
    -- preserved evidence, so the four columns move together or not at all.
    -- `coalesce` is load-bearing, not decoration: `NULL ~ '[^[:space:]]'` is NULL, and a
    -- CHECK passes when its expression is NULL. Without it this constraint admitted exactly the
    -- row it exists to refuse -- a hold released with no reason -- and read as though it did
    -- not. Check 37 caught it.
    CONSTRAINT sec_legal_holds_release_reasoned CHECK (
        (released_at IS NULL AND release_reason IS NULL AND released_by IS NULL
         AND release_correlation_id IS NULL)
        OR (released_at IS NOT NULL AND coalesce(release_reason, '') ~ '[^[:space:]]'
            AND released_by IS NOT NULL AND release_correlation_id IS NOT NULL))
);

-- A CHECK sees one row and cannot see what that row used to be, so the constraint above permits
-- a released hold to be released again with a different date and reason -- or set back to NULL,
-- so the row reads as a hold that was never lifted. Either rewrites the record of how long
-- deletion was suspended, which is the whole point of keeping it. A trigger is the only thing
-- that can see OLD, and this is the one place in the schema that needs to.
--
-- SECURITY INVOKER (the default) and a pinned search_path; EXECUTE is revoked from PUBLIC. A
-- trigger function needs no EXECUTE grant to fire, so the runtime roles are unaffected.
CREATE FUNCTION plt01.sec_legal_holds_release_is_final() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path = pg_catalog, plt01
AS $$
BEGIN
    IF OLD.released_at IS NOT NULL THEN
        RAISE EXCEPTION 'a released legal hold cannot be changed'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;
REVOKE EXECUTE ON FUNCTION plt01.sec_legal_holds_release_is_final() FROM PUBLIC;
CREATE TRIGGER sec_legal_holds_release_is_final
    BEFORE UPDATE ON plt01.sec_legal_holds
    FOR EACH ROW EXECUTE FUNCTION plt01.sec_legal_holds_release_is_final();
CREATE INDEX sec_legal_holds_live
    ON plt01.sec_legal_holds (tenant_id, subject_id) WHERE released_at IS NULL;
ALTER TABLE plt01.sec_legal_holds ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.sec_legal_holds FORCE ROW LEVEL SECURITY;
CREATE POLICY sec_legal_holds_tenant ON plt01.sec_legal_holds
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- data subject requests

-- SEC-01-R07. The five request types are the ones the requirement enumerates; TSD paragraph 4384
-- adds that each needs identity verification and a legal-hold check before it is fulfilled, and
-- the state machine in app/privacy/dsar.py is where that ordering is decided.
CREATE TABLE plt01.sec_dsar_requests (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    request_id uuid NOT NULL DEFAULT gen_random_uuid(),
    subject_id uuid NOT NULL,
    request_type text NOT NULL,
    status text NOT NULL,
    received_at timestamptz NOT NULL,
    due_at timestamptz NOT NULL,
    identity_verified_at timestamptz,
    identity_verified_by uuid,
    legal_checked_at timestamptz,
    legal_checked_by uuid,
    refused_reason text,
    completed_at timestamptz,
    opened_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, request_id),
    CONSTRAINT sec_dsar_type CHECK (request_type IN (
        'access', 'correction', 'portability', 'restriction', 'deletion')),
    CONSTRAINT sec_dsar_status CHECK (status IN (
        'received', 'identity_pending', 'legal_pending', 'ready', 'fulfilling',
        'completed', 'refused')),
    -- A refusal is a decision the subject can appeal, so it carries its reason in the row rather
    -- than only in a log somebody has to go and find.
    CONSTRAINT sec_dsar_refusal_reasoned CHECK (
        status <> 'refused' OR coalesce(refused_reason, '') ~ '[^[:space:]]'),
    CONSTRAINT sec_dsar_completed_consistent CHECK (
        (status = 'completed') = (completed_at IS NOT NULL))
);
CREATE INDEX sec_dsar_requests_subject
    ON plt01.sec_dsar_requests (tenant_id, subject_id, received_at DESC);
CREATE INDEX sec_dsar_requests_open
    ON plt01.sec_dsar_requests (tenant_id, due_at) WHERE status NOT IN ('completed', 'refused');
ALTER TABLE plt01.sec_dsar_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.sec_dsar_requests FORCE ROW LEVEL SECURITY;
CREATE POLICY sec_dsar_requests_tenant ON plt01.sec_dsar_requests
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- Insert-only: the record-count and hash evidence TSD paragraph 4396 requires a deletion job to
-- produce. One row per (request, store, table) pair actually acted on, including the ones that
-- could not be deleted and were pseudonymized instead, and including failures -- paragraph 4385
-- says jobs "do not silently ignore failures", and a trail that only records successes is how
-- they get ignored.
CREATE TABLE plt01.sec_dsar_actions (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    action_id uuid NOT NULL DEFAULT gen_random_uuid(),
    request_id uuid NOT NULL,
    store text NOT NULL,
    target text NOT NULL,
    mechanism text NOT NULL,
    outcome text NOT NULL,
    rows_affected bigint NOT NULL,
    evidence_hash text NOT NULL,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    performed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, action_id),
    FOREIGN KEY (tenant_id, request_id)
        REFERENCES plt01.sec_dsar_requests (tenant_id, request_id),
    -- The three mechanisms of TSD paragraph 4394 for PostgreSQL domain rows. `pseudonymize` is
    -- the one for rows whose deletion is legally barred -- the financial ledger and the audit
    -- chain, which carry no DELETE grant for any runtime role precisely so that they cannot be
    -- rewritten. `export` is here because an access or portability request acts on the same
    -- tables and produces the same kind of evidence.
    CONSTRAINT sec_dsar_actions_mechanism CHECK (mechanism IN (
        'delete', 'anonymize', 'pseudonymize', 'export', 'restrict')),
    CONSTRAINT sec_dsar_actions_outcome CHECK (outcome IN ('done', 'blocked', 'failed')),
    CONSTRAINT sec_dsar_actions_rows_sane CHECK (rows_affected >= 0),
    CONSTRAINT sec_dsar_actions_evidence_shape CHECK (evidence_hash ~ '^[0-9a-f]{64}$')
);
CREATE INDEX sec_dsar_actions_request
    ON plt01.sec_dsar_actions (tenant_id, request_id, performed_at);
ALTER TABLE plt01.sec_dsar_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.sec_dsar_actions FORCE ROW LEVEL SECURITY;
CREATE POLICY sec_dsar_actions_tenant ON plt01.sec_dsar_actions
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- security incidents

-- SEC-01-R09, the part of it that is a record rather than an operation. Insert-only for the same
-- reason the audit chain is: an incident record that the party responding to the incident can
-- edit afterwards is not evidence. A correction is a later row referring to the earlier one.
CREATE TABLE plt01.sec_incidents (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    incident_id uuid NOT NULL DEFAULT gen_random_uuid(),
    supersedes_incident_id uuid,
    severity text NOT NULL,
    -- Shape-constrained rather than a closed set, deliberately. Severity and
    -- `personal_data_involved` beside it are closed because the sources enumerate them; no
    -- source in this repository enumerates incident categories, and inventing a taxonomy here
    -- would be inventing product. The shape at least stops free text drifting into three
    -- spellings of the same category.
    category text NOT NULL,
    summary text NOT NULL,
    detected_at timestamptz NOT NULL,
    -- Whether personal data was involved decides whether a notification clock starts, so it is a
    -- required three-state answer rather than a boolean that defaults to false. "Not yet known"
    -- is the honest answer in the first hour and must be sayable.
    personal_data_involved text NOT NULL,
    notification_assessment text,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    recorded_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, incident_id),
    FOREIGN KEY (tenant_id, supersedes_incident_id)
        REFERENCES plt01.sec_incidents (tenant_id, incident_id),
    CONSTRAINT sec_incidents_severity CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    CONSTRAINT sec_incidents_personal_data CHECK (
        personal_data_involved IN ('yes', 'no', 'unknown')),
    CONSTRAINT sec_incidents_summary_not_blank CHECK (summary ~ '[^[:space:]]'),
    CONSTRAINT sec_incidents_category_shape CHECK (category ~ '^[a-z0-9]+(_[a-z0-9]+)*$'),
    CONSTRAINT sec_incidents_no_self_supersede CHECK (
        supersedes_incident_id IS NULL OR supersedes_incident_id <> incident_id)
);
CREATE INDEX sec_incidents_detected
    ON plt01.sec_incidents (tenant_id, detected_at DESC);
ALTER TABLE plt01.sec_incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.sec_incidents FORCE ROW LEVEL SECURITY;
CREATE POLICY sec_incidents_tenant ON plt01.sec_incidents
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- privileges

-- Mutable registries. A purpose and a retention policy are retired rather than deleted, so the
-- UPDATE is column-scoped to the retirement columns: nothing can quietly change the lawful basis
-- a consent was collected under, or shorten a retention period that has already been applied.
GRANT SELECT, INSERT ON plt01.sec_processing_purposes TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (retired_at, retired_by, retire_correlation_id) ON plt01.sec_processing_purposes
    TO veyro_cp_app, veyro_cp_worker;
GRANT SELECT, INSERT ON plt01.sec_retention_policies TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (retired_at, retired_by, retire_correlation_id) ON plt01.sec_retention_policies
    TO veyro_cp_app, veyro_cp_worker;

-- A consent definition's purpose link and guardian requirement are structural, so they move
-- together with the schema rather than at runtime; only the full registry row is insertable.
GRANT SELECT, INSERT ON plt01.sec_consent_definitions TO veyro_cp_app, veyro_cp_worker;

-- A hold is released, never deleted, and only those two columns move.
GRANT SELECT, INSERT ON plt01.sec_legal_holds TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (released_at, release_reason, released_by, release_correlation_id)
    ON plt01.sec_legal_holds TO veyro_cp_app, veyro_cp_worker;

-- A request moves through its state machine, so it needs a real UPDATE -- but not on what it
-- was: the subject, the type and when it arrived are what the deadline is computed from, and a
-- request whose type can change is a deletion that can become an access request after the fact.
GRANT SELECT, INSERT ON plt01.sec_dsar_requests TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (status, identity_verified_at, identity_verified_by, legal_checked_at,
              legal_checked_by, refused_reason, completed_at)
    ON plt01.sec_dsar_requests TO veyro_cp_app, veyro_cp_worker;

-- Evidence. No UPDATE and no DELETE for either runtime role: a consent record, a published
-- consent document, a deletion-evidence row and an incident record are each the answer to a
-- question somebody will ask later, and each is worthless if the party being asked can revise
-- it. Checks 33 to 38 in backend/tests/sql/isolation.sql prove these grants rather than trusting
-- this comment, and each was run against a deliberate mutation and shown to fail.
GRANT SELECT, INSERT ON plt01.sec_consent_versions TO veyro_cp_app, veyro_cp_worker;
GRANT SELECT, INSERT ON plt01.sec_consent_records TO veyro_cp_app, veyro_cp_worker;
GRANT SELECT, INSERT ON plt01.sec_dsar_actions TO veyro_cp_app, veyro_cp_worker;
GRANT SELECT, INSERT ON plt01.sec_incidents TO veyro_cp_app, veyro_cp_worker;

-- MOD-014 PPL-01: the canonical person, tenant/member/staff profiles, contact points,
-- relationships, tags, custom fields, duplicate review, merge provenance and the member
-- timeline. Tables are module-prefixed `ppl_`.
--
-- Every table repeats the four protections documented at the head of
-- `0001_organization_hierarchy.sql`: tenant-leading primary key, ENABLE plus FORCE row level
-- security, the `current_setting('app.tenant_id', true)` predicate that is NULL when no context
-- is set, and composite foreign keys carrying `tenant_id` into every parent -- including the
-- reference to `plt01_platform.tenants`. Checks 61 to 66 sweep all of it from the catalogue,
-- seat both runtime roles, compare every foreign key as a set and every UPDATE column grant per
-- role, and carry a case per side of every constraint.
--
-- Seven decisions are specific to this module.
--
--   * **Member 360 is a projection, not a table.** Paragraph 816: "the canonical model follows
--     aggregate ownership rather than a single shared member schema. Member 360 is a read
--     projection assembled from domain-owned records and the event timeline." So there is no
--     `ppl_member_360` row anywhere here. What exists is a person, the profiles that belong to
--     it, and a timeline assembled from events other modules published; the 360 read composes
--     those at request time and says how fresh each part is.
--
--   * **The timeline stores a summary, never a payload.** Paragraph 4021: "timeline projections
--     store user-safe event summaries, not raw event payloads", and paragraph 4224 adds that
--     each item "references the authoritative aggregate/event and applies permission/field
--     masking at read time". `ppl_timeline_entries` therefore carries a reference to the event
--     and a short human sentence, with the visibility class the masking reads -- and no `jsonb`
--     column at all, because MOD-010's review found a caller-chosen string inside `jsonb`
--     carrying a date of birth and a lab result into a store nothing could erase from.
--
--   * **This module owns contact data, and it is the only copy.** `ppl_contact_points` holds
--     real addresses: MOD-007's `iam.identities` holds the *authentication* identifier and
--     MOD-013 deliberately holds only a digest, so a member's email lives here once. That makes
--     the erasure obligation this module's: both value columns carry an UPDATE grant, they are
--     declared `anonymize` in `SUBJECT_COLUMNS`, and MOD-009's executor reaches them through
--     `ppl_identity_links`. A contact store an erasure cannot reach would be the shadow
--     database MOD-009 objects to.
--
--   * **A merge is reversible and the provenance is insert-only.** Paragraph 10200: "merges are
--     reviewable, reversible where feasible and fully audited". `ppl_merges` records what was
--     merged into what, by whom, on what evidence; reversal is a later column on the same row,
--     and the row itself can never be deleted, so "was this person ever merged" stays
--     answerable after the reversal. A merged person is not deleted either -- the row stays with
--     `merge_status = 'merged'` and a pointer -- because everything referencing it by id would
--     otherwise dangle.
--
--   * **Optimistic concurrency, not a lost update.** Paragraph 1331: "aggregate version
--     supports optimistic concurrency". Every mutable aggregate here carries `version`, every
--     update takes the version the caller read, and a mismatch is refused. Two front-desk staff
--     editing one profile is the ordinary case, and last-write-wins silently discards one of
--     them.
--
--   * **A minor's record is marked, not inferred at the far end.** Paragraph 1372:
--     "guardianship and consent must be validated before exposing minor data". `date_of_birth`
--     is on the person and `ppl_relationships` carries the guardian link, so the service can
--     supply `is_minor` and `is_assigned` to MOD-008 as request attributes -- which it must,
--     because MOD-008's review established that a deny policy whose attribute nobody supplies
--     denies the action outright. Fail-closed in the right direction.
--
--   * **A custom field has a schema before it has a value.** Paragraph 1318 asks for custom
--     fields "governed by schema and permissions". A definition declares a type and whether the
--     field is sensitive; a value is refused if it does not parse as that type. There is no
--     `secret` type and no free `jsonb` value, for the reason MOD-012's definition catalogue
--     has none: a type that invites a tenant to paste a credential into a column every list
--     route reads is worse than no field at all.

-- ---------------------------------------------------------------- the canonical person

-- One row per real person, per tenant. The id is tenant-scoped, which is deliberate: a person
-- known to two tenants is two rows, because a tenant must not be able to learn that its member
-- trains somewhere else. The cross-tenant link, where one exists, is MOD-007's bare
-- `person_id`, and `ppl_identity_links` is the only place the two meet.
CREATE TABLE plt01.ppl_persons (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    person_id uuid NOT NULL DEFAULT gen_random_uuid(),
    -- The name the tenant's records are filed under.
    legal_name text NOT NULL,
    -- **Paragraph 1320's first privacy control.** What the person asks to be called, which is
    -- not always what a contract says, and is the name every surface should show.
    preferred_name text,
    date_of_birth date,
    -- `active` or `merged`. A merged person keeps its row and points at the survivor.
    merge_status text NOT NULL DEFAULT 'active',
    merged_into_person_id uuid,
    merged_at timestamptz,
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, person_id),
    FOREIGN KEY (tenant_id, merged_into_person_id)
        REFERENCES plt01.ppl_persons (tenant_id, person_id),
    CONSTRAINT ppl_persons_merge_status
        CHECK (merge_status IN ('active', 'merged')),
    -- A merged person names its survivor and when, and an active one names neither. One
    -- direction without the other leaves a row that reads as merged into nothing, or as active
    -- while something points past it.
    --
    -- **Two constraints rather than one, because one compound CHECK over the status and both
    -- nullable columns cannot be tested.** The first version wrote it as a single disjunction
    -- naming `merge_status`, which meant every status value outside the two failed *it* as
    -- well as the domain CHECK -- so `ppl_persons_merge_status` and
    -- `ppl_persons_merge_is_not_self` could both be dropped with the suite reporting 66/66,
    -- their cases passing on a sibling's refusal. Found by the mutation sweep, which is the
    -- only thing that sees it. Split, each one is isolatable.
    CONSTRAINT ppl_persons_merge_pair
        CHECK ((merged_into_person_id IS NULL) = (merged_at IS NULL)),
    CONSTRAINT ppl_persons_merge_status_matches
        CHECK ((merge_status = 'merged') = (merged_at IS NOT NULL)),
    -- Nothing merges into itself; that is a cycle of length one and it strands every reference.
    CONSTRAINT ppl_persons_merge_is_not_self
        CHECK (merged_into_person_id IS NULL OR merged_into_person_id <> person_id),
    CONSTRAINT ppl_persons_legal_name_not_blank CHECK (legal_name ~ '[^[:space:]]'),
    CONSTRAINT ppl_persons_preferred_name_not_blank
        CHECK (preferred_name IS NULL OR preferred_name ~ '[^[:space:]]'),
    -- A birth date in the future is a typo, and this one decides whether somebody is a minor.
    --
    -- `CURRENT_DATE` is **stable, not immutable**, which PostgreSQL permits in a CHECK and which
    -- is safe here in one direction only: a date that was in the past stays in the past, so a
    -- row that validated once keeps validating as time passes, including through the revalidation
    -- a `pg_restore` performs. The caveat a reviewer added is timezone, not time --
    -- `CURRENT_DATE` is session-dependent, so a row written by a session in a forward timezone
    -- can be one day ahead of a later session's "today" and a restore in that session would
    -- refuse it. It needs a same-day birth registration east of the restoring session, and the
    -- failure is a refused restore rather than bad data. So: monotonic **within a timezone**.
    -- The service refuses a future date as well, which is where a caller gets a 422 instead.
    CONSTRAINT ppl_persons_born_in_the_past
        CHECK (date_of_birth IS NULL OR date_of_birth <= CURRENT_DATE),
    CONSTRAINT ppl_persons_version_positive CHECK (version >= 1)
);
CREATE INDEX ppl_persons_by_name ON plt01.ppl_persons (tenant_id, lower(legal_name));
-- **The other half of the duplicate draw.** `find_duplicates` matches on a folded name *or* a
-- birth date, and with only the name index the planner read the whole tenant and filtered --
-- measured by a reviewer, against the docstring's claim to "use the indexes to find the small
-- set", at the 450,000 profiles the module is specified for. Partial, because a NULL birth date
-- is most leads and is never a match.
CREATE INDEX ppl_persons_by_birth_date ON plt01.ppl_persons (tenant_id, date_of_birth)
    WHERE date_of_birth IS NOT NULL;
ALTER TABLE plt01.ppl_persons ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ppl_persons FORCE ROW LEVEL SECURITY;
CREATE POLICY ppl_persons_tenant ON plt01.ppl_persons
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- Which MOD-007 identity, if any, signs in as this person. **No foreign key, and there cannot
-- be one**: `iam` is a separate plane under a separate role that holds nothing here, which is
-- the isolation this build rests on. So the link is recorded and the absence is the finding --
-- a stale link is possible and `LinkIdentity` is the only thing that writes one.
CREATE TABLE plt01.ppl_identity_links (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    person_id uuid NOT NULL,
    -- `iam.identities.identity_id`, in this tenant. Unverifiable from here, by design.
    identity_id uuid NOT NULL,
    linked_at timestamptz NOT NULL DEFAULT now(),
    linked_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, person_id, identity_id),
    FOREIGN KEY (tenant_id, person_id) REFERENCES plt01.ppl_persons (tenant_id, person_id),
    -- One identity signs in as one person. Two would mean a login resolving to two member
    -- records, and every permission decision afterwards would be about an arbitrary one.
    UNIQUE (tenant_id, identity_id)
);
ALTER TABLE plt01.ppl_identity_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ppl_identity_links FORCE ROW LEVEL SECURITY;
CREATE POLICY ppl_identity_links_tenant ON plt01.ppl_identity_links
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- contact points

-- **The authoritative contact record, and the only copy.** MOD-007 holds the identifier somebody
-- authenticates with; MOD-013 holds a digest on purpose; a member's actual email and phone live
-- here, once. `value_normalized` is what everything keys and deduplicates on, and it is produced
-- by the same normalizer MOD-007 uses -- one spelling rule in the build, because two drift and
-- the day they disagree a duplicate is invisible to one of them.
CREATE TABLE plt01.ppl_contact_points (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    contact_point_id uuid NOT NULL DEFAULT gen_random_uuid(),
    person_id uuid NOT NULL,
    kind text NOT NULL,
    -- What the person gave us, kept so a display is not a round trip through normalization.
    value_raw text NOT NULL,
    -- What everything matches on.
    value_normalized text NOT NULL,
    is_primary boolean NOT NULL DEFAULT false,
    -- **A verification names who asserted it.** `verified_at` is the signal
    -- `dedup.WEIGHTS` scores highest, which makes it the evidence an operator destroys a
    -- record on -- and the first version recorded only the timestamp while the service
    -- returned `asserted_by` to the caller and its docstring said the row carried it. There is
    -- no second record to fall back on: MOD-008 audits denials and `veyro_cp_app` holds
    -- nothing in `iam`. Found by review; the same shape as MOD-012's `release_run`, MOD-011's
    -- `ops_synthetic_results` and MOD-009's hold release, which is why it is a constraint here
    -- rather than a convention.
    verified_at timestamptz,
    verified_by uuid,
    verify_correlation_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    recorded_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, contact_point_id),
    FOREIGN KEY (tenant_id, person_id) REFERENCES plt01.ppl_persons (tenant_id, person_id),
    CONSTRAINT ppl_contact_points_kind CHECK (kind IN ('email', 'phone', 'address')),
    CONSTRAINT ppl_contact_points_raw_not_blank CHECK (value_raw ~ '[^[:space:]]'),
    CONSTRAINT ppl_contact_points_normalized_not_blank
        CHECK (value_normalized ~ '[^[:space:]]'),
    CONSTRAINT ppl_contact_points_verification_attributed CHECK (
        (verified_at IS NULL AND verified_by IS NULL AND verify_correlation_id IS NULL)
        OR (verified_at IS NOT NULL AND verified_by IS NOT NULL
            AND verify_correlation_id IS NOT NULL))
);
-- One of each kind per person is primary. A second primary email means every surface picks a
-- different one and a member gets told different things on each.
CREATE UNIQUE INDEX ppl_contact_points_one_primary
    ON plt01.ppl_contact_points (tenant_id, person_id, kind) WHERE is_primary;
-- The same value twice on one person is a data-entry duplicate, not two ways to reach them.
CREATE UNIQUE INDEX ppl_contact_points_distinct
    ON plt01.ppl_contact_points (tenant_id, person_id, kind, value_normalized);
-- The duplicate-candidate index paragraph 9973 asks for: finding everybody who shares an
-- address is how `find_duplicates` works, and it must not be a sequential scan of the tenant.
CREATE INDEX ppl_contact_points_by_value
    ON plt01.ppl_contact_points (tenant_id, kind, value_normalized);
ALTER TABLE plt01.ppl_contact_points ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ppl_contact_points FORCE ROW LEVEL SECURITY;
CREATE POLICY ppl_contact_points_tenant ON plt01.ppl_contact_points
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- profiles

-- The tenant-specific view of a person: one row per person per tenant, holding what this tenant
-- knows that no other tenant should. Separate from the person because the person is identity and
-- this is relationship -- paragraph 1296 names TenantProfile as its own authoritative entity.
CREATE TABLE plt01.ppl_tenant_profiles (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    profile_id uuid NOT NULL DEFAULT gen_random_uuid(),
    person_id uuid NOT NULL,
    -- Where in the hierarchy this person belongs. Both optional: a person may be known to the
    -- tenant before anybody decides which location they belong to.
    brand_id uuid,
    location_id uuid,
    -- How they came to be known. A lead that became a member keeps its origin, because
    -- attribution is what paragraph 1421 asks a merge to preserve.
    acquisition_source text,
    preferred_language text,
    notes_internal text,
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, profile_id),
    FOREIGN KEY (tenant_id, person_id) REFERENCES plt01.ppl_persons (tenant_id, person_id),
    FOREIGN KEY (tenant_id, brand_id) REFERENCES plt01.brands (tenant_id, brand_id),
    FOREIGN KEY (tenant_id, location_id) REFERENCES plt01.locations (tenant_id, location_id),
    -- One tenant profile per person. Two would be the duplicate record this module exists to
    -- prevent, inside the table that is supposed to be the single view.
    UNIQUE (tenant_id, person_id),
    CONSTRAINT ppl_tenant_profiles_language
        CHECK (preferred_language IS NULL OR preferred_language ~ '^[a-z]{2}(-[A-Z]{2})?$'),
    CONSTRAINT ppl_tenant_profiles_version_positive CHECK (version >= 1)
);
ALTER TABLE plt01.ppl_tenant_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ppl_tenant_profiles FORCE ROW LEVEL SECURITY;
CREATE POLICY ppl_tenant_profiles_tenant ON plt01.ppl_tenant_profiles
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- The member role a person holds, and its lifecycle. **This is not the membership**: COM-01's
-- `app.membership` is the agreement and is the lifecycle source of truth for *that*. This row is
-- the person's standing as a member of this tenant, which exists before any agreement (a lead)
-- and after the last one ends (a former member whose history must stay readable).
CREATE TABLE plt01.ppl_member_profiles (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    member_profile_id uuid NOT NULL DEFAULT gen_random_uuid(),
    person_id uuid NOT NULL,
    lifecycle_state text NOT NULL DEFAULT 'lead',
    state_changed_at timestamptz NOT NULL DEFAULT now(),
    state_reason text,
    -- The tenant's own member number, where it has one. Scoped by tenant, as paragraph 1331
    -- requires of an external identifier.
    member_number text,
    joined_on date,
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, member_profile_id),
    FOREIGN KEY (tenant_id, person_id) REFERENCES plt01.ppl_persons (tenant_id, person_id),
    UNIQUE (tenant_id, person_id),
    CONSTRAINT ppl_member_profiles_lifecycle CHECK (lifecycle_state IN (
        'lead', 'prospect', 'active', 'paused', 'cancelled', 'former')),
    CONSTRAINT ppl_member_profiles_number_not_blank
        CHECK (member_number IS NULL OR member_number ~ '[^[:space:]]'),
    CONSTRAINT ppl_member_profiles_reason_not_blank
        CHECK (state_reason IS NULL OR state_reason ~ '[^[:space:]]'),
    CONSTRAINT ppl_member_profiles_version_positive CHECK (version >= 1)
);
-- A member number identifies one member, which is the only thing it is for.
CREATE UNIQUE INDEX ppl_member_profiles_number
    ON plt01.ppl_member_profiles (tenant_id, member_number) WHERE member_number IS NOT NULL;
CREATE INDEX ppl_member_profiles_by_state
    ON plt01.ppl_member_profiles (tenant_id, lifecycle_state, state_changed_at DESC);
ALTER TABLE plt01.ppl_member_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ppl_member_profiles FORCE ROW LEVEL SECURITY;
CREATE POLICY ppl_member_profiles_tenant ON plt01.ppl_member_profiles
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- The staff or coach role a person holds. Separate from the member profile because one person is
-- routinely both -- a coach who trains at the gym they work at -- and collapsing the two would
-- make "is this person a member" and "is this person staff" one answer.
CREATE TABLE plt01.ppl_staff_profiles (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    staff_profile_id uuid NOT NULL DEFAULT gen_random_uuid(),
    person_id uuid NOT NULL,
    employment_state text NOT NULL DEFAULT 'active',
    job_title text,
    -- Where they work. A coach assigned to one location should not appear on another's roster.
    location_id uuid,
    started_on date,
    ended_on date,
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, staff_profile_id),
    FOREIGN KEY (tenant_id, person_id) REFERENCES plt01.ppl_persons (tenant_id, person_id),
    FOREIGN KEY (tenant_id, location_id) REFERENCES plt01.locations (tenant_id, location_id),
    UNIQUE (tenant_id, person_id),
    CONSTRAINT ppl_staff_profiles_state
        CHECK (employment_state IN ('active', 'suspended', 'ended')),
    -- Employment that ended has an end date, and employment that has not has none. A row
    -- reading `ended` with no date makes "who was working on the fourteenth" unanswerable.
    CONSTRAINT ppl_staff_profiles_end_is_complete
        CHECK ((employment_state = 'ended') = (ended_on IS NOT NULL)),
    CONSTRAINT ppl_staff_profiles_dates_ordered
        CHECK (started_on IS NULL OR ended_on IS NULL OR ended_on >= started_on),
    CONSTRAINT ppl_staff_profiles_title_not_blank
        CHECK (job_title IS NULL OR job_title ~ '[^[:space:]]'),
    CONSTRAINT ppl_staff_profiles_version_positive CHECK (version >= 1)
);
ALTER TABLE plt01.ppl_staff_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ppl_staff_profiles FORCE ROW LEVEL SECURITY;
CREATE POLICY ppl_staff_profiles_tenant ON plt01.ppl_staff_profiles
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- relationships

-- The relationship graph paragraph 1319 names: coach-client, guardian-dependent,
-- company-employee, referrer-referred and household. Directed, because every one of those has a
-- direction that matters -- a guardian is not a dependent -- and time-bounded, because a coach
-- stops being somebody's coach without that ever having been untrue.
CREATE TABLE plt01.ppl_relationships (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    relationship_id uuid NOT NULL DEFAULT gen_random_uuid(),
    kind text NOT NULL,
    from_person_id uuid NOT NULL,
    to_person_id uuid NOT NULL,
    valid_from timestamptz NOT NULL DEFAULT now(),
    valid_to timestamptz,
    ended_reason text,
    -- Ending a `guardian_dependent` edge is the act that removes a guardian's read access to a
    -- minor's record, so it names who did it. The first version took an `actor_id` and used it
    -- for nothing.
    ended_by uuid,
    end_correlation_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, relationship_id),
    FOREIGN KEY (tenant_id, from_person_id)
        REFERENCES plt01.ppl_persons (tenant_id, person_id),
    FOREIGN KEY (tenant_id, to_person_id)
        REFERENCES plt01.ppl_persons (tenant_id, person_id),
    CONSTRAINT ppl_relationships_kind CHECK (kind IN (
        'coach_client', 'guardian_dependent', 'company_employee', 'referrer_referred',
        'household')),
    -- Nobody is their own guardian, coach or referrer. Allowing it would make
    -- `is_assigned` true for everybody about themselves, which is an authorization bypass
    -- dressed as a data-entry mistake.
    CONSTRAINT ppl_relationships_not_self CHECK (from_person_id <> to_person_id),
    CONSTRAINT ppl_relationships_window CHECK (valid_to IS NULL OR valid_to > valid_from),
    -- An ended relationship may say why; one still running may not, because a reason with no
    -- end reads as an explanation of something that has not happened.
    CONSTRAINT ppl_relationships_reason_needs_an_end
        CHECK (ended_reason IS NULL OR valid_to IS NOT NULL),
    CONSTRAINT ppl_relationships_reason_not_blank
        CHECK (ended_reason IS NULL OR ended_reason ~ '[^[:space:]]'),
    CONSTRAINT ppl_relationships_end_attributed CHECK (
        (valid_to IS NULL AND ended_by IS NULL AND end_correlation_id IS NULL)
        OR (valid_to IS NOT NULL AND ended_by IS NOT NULL
            AND end_correlation_id IS NOT NULL
            AND coalesce(ended_reason, '') ~ '[^[:space:]]'))
);
-- One live relationship of a kind between two people. A second is a duplicate edge, and a
-- guardian counted twice is a guardian whose revocation leaves one behind.
CREATE UNIQUE INDEX ppl_relationships_live
    ON plt01.ppl_relationships (tenant_id, kind, from_person_id, to_person_id)
    WHERE valid_to IS NULL;
-- Both directions are read: "who are this coach's clients" and "who is this member's coach".
CREATE INDEX ppl_relationships_from
    ON plt01.ppl_relationships (tenant_id, from_person_id, kind);
CREATE INDEX ppl_relationships_to
    ON plt01.ppl_relationships (tenant_id, to_person_id, kind);
ALTER TABLE plt01.ppl_relationships ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ppl_relationships FORCE ROW LEVEL SECURITY;
CREATE POLICY ppl_relationships_tenant ON plt01.ppl_relationships
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- tags and custom fields

CREATE TABLE plt01.ppl_tags (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    tag_id uuid NOT NULL DEFAULT gen_random_uuid(),
    tag_key text NOT NULL,
    display_name text NOT NULL,
    -- A tag a member can see on themselves, or one only staff read. "Difficult" is a real tag
    -- real gyms write, and a member reading it is a complaint.
    is_internal boolean NOT NULL DEFAULT false,
    retired_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, tag_id),
    UNIQUE (tenant_id, tag_key),
    CONSTRAINT ppl_tags_key_shape CHECK (tag_key ~ '^[a-z][a-z0-9_.-]{1,62}$'),
    CONSTRAINT ppl_tags_display_not_blank CHECK (display_name ~ '[^[:space:]]')
);
ALTER TABLE plt01.ppl_tags ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ppl_tags FORCE ROW LEVEL SECURITY;
CREATE POLICY ppl_tags_tenant ON plt01.ppl_tags
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- Insert-only: who tagged somebody and when is the thing a member asks about, and an UPDATE
-- grant would let it be rewritten. Removing a tag sets `removed_at`, which is in the grant.
CREATE TABLE plt01.ppl_person_tags (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    person_id uuid NOT NULL,
    tag_id uuid NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now(),
    applied_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    removed_at timestamptz,
    removed_by uuid,
    PRIMARY KEY (tenant_id, person_id, tag_id),
    FOREIGN KEY (tenant_id, person_id) REFERENCES plt01.ppl_persons (tenant_id, person_id),
    FOREIGN KEY (tenant_id, tag_id) REFERENCES plt01.ppl_tags (tenant_id, tag_id),
    CONSTRAINT ppl_person_tags_removal_attributed
        CHECK ((removed_at IS NULL) = (removed_by IS NULL))
);
ALTER TABLE plt01.ppl_person_tags ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ppl_person_tags FORCE ROW LEVEL SECURITY;
CREATE POLICY ppl_person_tags_tenant ON plt01.ppl_person_tags
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **A custom field declares its type, and there is no `secret` type.** MOD-012's definition
-- catalogue makes the same refusal for the same reason: a type that invites a tenant to paste a
-- credential into a column every list route reads is worse than having no field.
CREATE TABLE plt01.ppl_custom_field_defs (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    field_id uuid NOT NULL DEFAULT gen_random_uuid(),
    field_key text NOT NULL,
    display_name text NOT NULL,
    value_type text NOT NULL,
    -- Whether the value is one MOD-008 masks. A tenant collecting a national id in a custom
    -- field is collecting a national id, and the masking has to know.
    sensitivity text NOT NULL DEFAULT 'none',
    is_required boolean NOT NULL DEFAULT false,
    retired_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, field_id),
    UNIQUE (tenant_id, field_key),
    CONSTRAINT ppl_custom_field_defs_key_shape
        CHECK (field_key ~ '^[a-z][a-z0-9_.-]{1,62}$'),
    CONSTRAINT ppl_custom_field_defs_display_not_blank
        CHECK (display_name ~ '[^[:space:]]'),
    CONSTRAINT ppl_custom_field_defs_type
        CHECK (value_type IN ('text', 'integer', 'decimal', 'boolean', 'date', 'enum')),
    -- The five classes MOD-008's `SENSITIVE_FIELDS` uses, plus `none`. A sixth invented here
    -- would be a class the masking does not know and would read as unmasked.
    CONSTRAINT ppl_custom_field_defs_sensitivity CHECK (sensitivity IN (
        'none', 'contact', 'identity', 'financial', 'health', 'biometric'))
);
ALTER TABLE plt01.ppl_custom_field_defs ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ppl_custom_field_defs FORCE ROW LEVEL SECURITY;
CREATE POLICY ppl_custom_field_defs_tenant ON plt01.ppl_custom_field_defs
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- The allowed values of an `enum` field, as rows rather than an array so the set can be
-- read, displayed and extended without rewriting a column.
--
-- **The check is `fields.normalize_value`, not a foreign key**, and the first version of this
-- comment claimed otherwise. A foreign key is not available here and could not be: `value_text`
-- is shared with `text`, `integer` and `date` fields that have no option rows at all, and
-- MOD-009's erasure writes `'erased'` into it. Found by review as a false claim rather than a
-- hole -- every write path does go through the validator.
CREATE TABLE plt01.ppl_custom_field_options (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    field_id uuid NOT NULL,
    option_value text NOT NULL,
    display_name text NOT NULL,
    PRIMARY KEY (tenant_id, field_id, option_value),
    FOREIGN KEY (tenant_id, field_id)
        REFERENCES plt01.ppl_custom_field_defs (tenant_id, field_id),
    CONSTRAINT ppl_custom_field_options_value_not_blank
        CHECK (option_value ~ '[^[:space:]]'),
    CONSTRAINT ppl_custom_field_options_display_not_blank
        CHECK (display_name ~ '[^[:space:]]')
);
ALTER TABLE plt01.ppl_custom_field_options ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ppl_custom_field_options FORCE ROW LEVEL SECURITY;
CREATE POLICY ppl_custom_field_options_tenant ON plt01.ppl_custom_field_options
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- One value per field per person. Stored as text with the definition's type validated by the
-- service before the write -- there is no `jsonb` here, for MOD-010's reason: a sweep that
-- matches column names cannot see a subject identifier inside `jsonb`, and a custom field is
-- exactly where a tenant will put one.
CREATE TABLE plt01.ppl_custom_field_values (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    person_id uuid NOT NULL,
    field_id uuid NOT NULL,
    value_text text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, person_id, field_id),
    FOREIGN KEY (tenant_id, person_id) REFERENCES plt01.ppl_persons (tenant_id, person_id),
    FOREIGN KEY (tenant_id, field_id)
        REFERENCES plt01.ppl_custom_field_defs (tenant_id, field_id),
    CONSTRAINT ppl_custom_field_values_not_blank CHECK (value_text ~ '[^[:space:]]')
);
ALTER TABLE plt01.ppl_custom_field_values ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ppl_custom_field_values FORCE ROW LEVEL SECURITY;
CREATE POLICY ppl_custom_field_values_tenant ON plt01.ppl_custom_field_values
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- notes

-- RecordMemberNote. **Paragraph 1320 calls these sensitive notes and they are the most
-- consequential free text in the product**: what a coach writes about a client, what a front
-- desk writes about a complaint. Insert-only, because a note that can be edited is a note
-- nobody can rely on in a dispute, and classified so the masking knows which roles see it.
CREATE TABLE plt01.ppl_person_notes (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    note_id uuid NOT NULL DEFAULT gen_random_uuid(),
    person_id uuid NOT NULL,
    -- `general` is readable with the profile; `health` and `sensitive` are not.
    note_class text NOT NULL DEFAULT 'general',
    body text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    recorded_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    -- A note is withdrawn rather than deleted: the author recorded something and later said it
    -- should not stand, and both halves are the record.
    withdrawn_at timestamptz,
    withdrawn_by uuid,
    withdraw_reason text,
    PRIMARY KEY (tenant_id, note_id),
    FOREIGN KEY (tenant_id, person_id) REFERENCES plt01.ppl_persons (tenant_id, person_id),
    CONSTRAINT ppl_person_notes_class
        CHECK (note_class IN ('general', 'health', 'sensitive')),
    CONSTRAINT ppl_person_notes_body_not_blank CHECK (body ~ '[^[:space:]]'),
    -- Who, when and why together, or none of them. The `coalesce` is load-bearing: a CHECK
    -- passes on NULL, so `withdraw_reason ~ '[^[:space:]]'` without it admits the blank
    -- reason it exists to refuse -- MOD-009's legal-hold finding, which this build has now paid
    -- for three times.
    CONSTRAINT ppl_person_notes_withdrawal_attributed CHECK (
        (withdrawn_at IS NULL AND withdrawn_by IS NULL AND withdraw_reason IS NULL)
        OR (withdrawn_at IS NOT NULL AND withdrawn_by IS NOT NULL
            AND coalesce(withdraw_reason, '') ~ '[^[:space:]]'))
);
CREATE INDEX ppl_person_notes_by_person
    ON plt01.ppl_person_notes (tenant_id, person_id, recorded_at DESC);
ALTER TABLE plt01.ppl_person_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ppl_person_notes FORCE ROW LEVEL SECURITY;
CREATE POLICY ppl_person_notes_tenant ON plt01.ppl_person_notes
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- duplicates and merges

-- What `find_duplicates` proposed, so a human can decide. A candidate pair is ordered by id so
-- the same pair cannot be queued twice in opposite directions, and `signals` is a text array of
-- named reasons rather than free prose -- an operator deciding a merge needs to know *why* the
-- system thinks these are one person, and "0.82" is not that.
CREATE TABLE plt01.ppl_duplicate_candidates (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    candidate_id uuid NOT NULL DEFAULT gen_random_uuid(),
    lower_person_id uuid NOT NULL,
    higher_person_id uuid NOT NULL,
    score integer NOT NULL,
    signals text[] NOT NULL,
    status text NOT NULL DEFAULT 'open',
    detected_at timestamptz NOT NULL DEFAULT now(),
    decided_at timestamptz,
    decided_by uuid,
    decision_reason text,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, candidate_id),
    FOREIGN KEY (tenant_id, lower_person_id)
        REFERENCES plt01.ppl_persons (tenant_id, person_id),
    FOREIGN KEY (tenant_id, higher_person_id)
        REFERENCES plt01.ppl_persons (tenant_id, person_id),
    CONSTRAINT ppl_duplicate_candidates_status
        CHECK (status IN ('open', 'merged', 'dismissed')),
    -- Ordered, which is what makes the uniqueness below mean "this pair", not "this direction".
    CONSTRAINT ppl_duplicate_candidates_ordered CHECK (lower_person_id < higher_person_id),
    -- A score outside 0..100 is a scoring bug reaching the table rather than the caller. The
    -- bound also stops `integer` overflow becoming a 500, which MOD-011 and MOD-012 each shipped.
    CONSTRAINT ppl_duplicate_candidates_score CHECK (score BETWEEN 0 AND 100),
    CONSTRAINT ppl_duplicate_candidates_signals_present CHECK (cardinality(signals) > 0),
    -- A decision carries who, when and why, or none of them -- and a blank reason is not a
    -- reason, for the third time in this schema.
    CONSTRAINT ppl_duplicate_candidates_decision_attributed CHECK (
        (status = 'open' AND decided_at IS NULL AND decided_by IS NULL
         AND decision_reason IS NULL)
        OR (status <> 'open' AND decided_at IS NOT NULL AND decided_by IS NOT NULL
            AND coalesce(decision_reason, '') ~ '[^[:space:]]'))
);
-- One open candidate per pair. A second would let two operators decide the same merge twice.
CREATE UNIQUE INDEX ppl_duplicate_candidates_open
    ON plt01.ppl_duplicate_candidates (tenant_id, lower_person_id, higher_person_id)
    WHERE status = 'open';
ALTER TABLE plt01.ppl_duplicate_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ppl_duplicate_candidates FORCE ROW LEVEL SECURITY;
CREATE POLICY ppl_duplicate_candidates_tenant ON plt01.ppl_duplicate_candidates
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- Merge provenance. Paragraph 10200: reviewable, reversible where feasible, fully audited.
-- Insert-only apart from the reversal columns, so "was this person ever merged, and by whom"
-- stays answerable after it has been undone -- which is the half a delete would destroy.
CREATE TABLE plt01.ppl_merges (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    merge_id uuid NOT NULL DEFAULT gen_random_uuid(),
    source_person_id uuid NOT NULL,
    target_person_id uuid NOT NULL,
    reason text NOT NULL,
    -- What moved, as named counts, so a reversal knows what it is undoing and a reviewer can
    -- see the size of what happened without reconstructing it.
    moved_contact_points integer NOT NULL DEFAULT 0,
    moved_relationships integer NOT NULL DEFAULT 0,
    moved_notes integer NOT NULL DEFAULT 0,
    moved_tags integer NOT NULL DEFAULT 0,
    -- The fifth count. The service counted custom field values, returned the number to the
    -- caller and recorded it nowhere, and the reversal's `not_restored` omitted them entirely
    -- -- which in a reviewer's probe silently included a health-classified value copied onto
    -- another person and left there after the reversal.
    moved_custom_fields integer NOT NULL DEFAULT 0,
    merged_at timestamptz NOT NULL DEFAULT now(),
    merged_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    reversed_at timestamptz,
    reversed_by uuid,
    reverse_reason text,
    reverse_correlation_id uuid,
    PRIMARY KEY (tenant_id, merge_id),
    FOREIGN KEY (tenant_id, source_person_id)
        REFERENCES plt01.ppl_persons (tenant_id, person_id),
    FOREIGN KEY (tenant_id, target_person_id)
        REFERENCES plt01.ppl_persons (tenant_id, person_id),
    CONSTRAINT ppl_merges_not_self CHECK (source_person_id <> target_person_id),
    CONSTRAINT ppl_merges_reason_not_blank CHECK (reason ~ '[^[:space:]]'),
    CONSTRAINT ppl_merges_counts_non_negative CHECK (
        moved_contact_points >= 0 AND moved_relationships >= 0 AND moved_notes >= 0
        AND moved_tags >= 0 AND moved_custom_fields >= 0),
    CONSTRAINT ppl_merges_reversal_attributed CHECK (
        (reversed_at IS NULL AND reversed_by IS NULL AND reverse_reason IS NULL
         AND reverse_correlation_id IS NULL)
        OR (reversed_at IS NOT NULL AND reversed_by IS NOT NULL
            AND reverse_correlation_id IS NOT NULL
            AND coalesce(reverse_reason, '') ~ '[^[:space:]]'))
);
-- A person is merged away once. A second merge of the same source is either a double-submit or
-- a chain, and both want the reversal to be unambiguous about which one it undoes.
CREATE UNIQUE INDEX ppl_merges_one_live_per_source
    ON plt01.ppl_merges (tenant_id, source_person_id) WHERE reversed_at IS NULL;
ALTER TABLE plt01.ppl_merges ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ppl_merges FORCE ROW LEVEL SECURITY;
CREATE POLICY ppl_merges_tenant ON plt01.ppl_merges
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- the timeline

-- **A projection, and it says so.** Paragraph 4223: "timeline is a projection of selected domain
-- events into human-readable entries. It is not the source of truth for domain state."
-- Paragraph 4021: "timeline projections store user-safe event summaries, not raw event
-- payloads." So: a reference to the event, a one-line summary, and the visibility class the
-- masking reads. No payload column of any type, which is why this table has no `jsonb` and
-- check 64 pins the column list.
--
-- Insert-only. Paragraph 4225 says the projection "can be rebuilt from retained events", and a
-- rebuild that could silently rewrite an entry would make the timeline unreliable in exactly
-- the way the paragraph above denies it is authoritative for.
CREATE TABLE plt01.ppl_timeline_entries (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    entry_id uuid NOT NULL DEFAULT gen_random_uuid(),
    person_id uuid NOT NULL,
    -- The event this was projected from. No foreign key to `evt_outbox`: the outbox is MOD-010's
    -- and an archive will eventually move rows out of it, so a hard reference would turn a
    -- retention action into a referential failure. The id is the handle paragraph 4224 asks for.
    event_id uuid NOT NULL,
    event_type text NOT NULL,
    occurred_at timestamptz NOT NULL,
    -- What the authoritative record is, so a reader can go and look rather than believe this.
    aggregate_type text NOT NULL,
    aggregate_id uuid NOT NULL,
    -- One human sentence. Rendered when the entry was projected, from the event's own fields.
    summary text NOT NULL,
    -- Which of MOD-008's classes this entry belongs to. `none` is readable with the timeline;
    -- the rest are masked unless the caller holds the matching permission.
    visibility_class text NOT NULL DEFAULT 'none',
    projected_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, entry_id),
    FOREIGN KEY (tenant_id, person_id) REFERENCES plt01.ppl_persons (tenant_id, person_id),
    -- One entry per event per person. A rebuild re-runs the projection over the same events, so
    -- without this a second pass doubles every member's history.
    UNIQUE (tenant_id, person_id, event_id),
    CONSTRAINT ppl_timeline_entries_summary_not_blank CHECK (summary ~ '[^[:space:]]'),
    CONSTRAINT ppl_timeline_entries_type_not_blank CHECK (event_type ~ '[^[:space:]]'),
    CONSTRAINT ppl_timeline_entries_aggregate_not_blank
        CHECK (aggregate_type ~ '[^[:space:]]'),
    CONSTRAINT ppl_timeline_entries_visibility CHECK (visibility_class IN (
        'none', 'contact', 'identity', 'financial', 'health', 'biometric'))
);
CREATE INDEX ppl_timeline_entries_by_person
    ON plt01.ppl_timeline_entries (tenant_id, person_id, occurred_at DESC);
ALTER TABLE plt01.ppl_timeline_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.ppl_timeline_entries FORCE ROW LEVEL SECURITY;
CREATE POLICY ppl_timeline_entries_tenant ON plt01.ppl_timeline_entries
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- privileges

-- A person's own fields change: somebody corrects a name, records a birth date, or the merge
-- machinery points the row at its survivor. `created_by` and `correlation_id` do not move, so
-- who created the record stays answerable.
GRANT SELECT, INSERT ON plt01.ppl_persons TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (legal_name, preferred_name, date_of_birth, merge_status, merged_into_person_id,
              merged_at, version, updated_at)
    ON plt01.ppl_persons TO veyro_cp_app, veyro_cp_worker;

-- Insert-only, and unlinking is not implemented: an identity that signed in as this person did
-- so, and a link that could be quietly removed would make a past authorization unexplainable.
GRANT SELECT, INSERT ON plt01.ppl_identity_links TO veyro_cp_app, veyro_cp_worker;

-- **A contact point is erasable, which is the point.** This is the only copy of a member's
-- address in the build, so MOD-009's executor needs both value columns writable; `recorded_by`
-- and `correlation_id` are not, so who entered it survives the erasure of what they entered.
GRANT SELECT, INSERT ON plt01.ppl_contact_points TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (value_raw, value_normalized, is_primary, verified_at, verified_by,
              verify_correlation_id, updated_at)
    ON plt01.ppl_contact_points TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.ppl_tenant_profiles TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (brand_id, location_id, acquisition_source, preferred_language, notes_internal,
              version, updated_at, updated_by, correlation_id)
    ON plt01.ppl_tenant_profiles TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.ppl_member_profiles TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (lifecycle_state, state_changed_at, state_reason, member_number, joined_on,
              version, updated_at, updated_by, correlation_id)
    ON plt01.ppl_member_profiles TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.ppl_staff_profiles TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (employment_state, job_title, location_id, started_on, ended_on, version,
              updated_at, updated_by, correlation_id)
    ON plt01.ppl_staff_profiles TO veyro_cp_app, veyro_cp_worker;

-- A relationship ends; it is not deleted and it is not re-pointed. `from_person_id`,
-- `to_person_id` and `kind` carry no UPDATE, so "who was this member's coach in March" cannot
-- be rewritten -- and a merge moves a relationship by ending it and inserting the replacement,
-- which leaves both halves visible.
GRANT SELECT, INSERT ON plt01.ppl_relationships TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (valid_to, ended_reason, ended_by, end_correlation_id)
    ON plt01.ppl_relationships TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.ppl_tags TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (display_name, is_internal, retired_at) ON plt01.ppl_tags
    TO veyro_cp_app, veyro_cp_worker;
-- **Re-applying a removed tag is a fresh act by whoever did it.** The row is keyed on
-- (tenant, person, tag), so there is exactly one per pairing for ever: with `applied_at` and
-- `applied_by` outside the grant, a removed tag could never be re-applied and `apply_tag`
-- reported success for a write it had not made. Attributing the re-application to the original
-- applier would have been the wrong record, so the two columns move -- which costs the first
-- application's attribution and is the lesser loss, stated rather than discovered.
GRANT SELECT, INSERT ON plt01.ppl_person_tags TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (applied_at, applied_by, correlation_id, removed_at, removed_by)
    ON plt01.ppl_person_tags TO veyro_cp_app, veyro_cp_worker;

-- A definition's *type* and *sensitivity* carry no UPDATE. Changing either would reclassify or
-- invalidate every value already stored against it, silently: a field re-typed from text to
-- integer leaves unparseable values readable, and one re-marked `none` unmasks what was
-- collected as health data. Retiring it and declaring a new one is the supported path.
GRANT SELECT, INSERT ON plt01.ppl_custom_field_defs TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (display_name, is_required, retired_at) ON plt01.ppl_custom_field_defs
    TO veyro_cp_app, veyro_cp_worker;
-- An option set is additive; removing a value would orphan the rows that hold it.
GRANT SELECT, INSERT ON plt01.ppl_custom_field_options TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (display_name) ON plt01.ppl_custom_field_options
    TO veyro_cp_app, veyro_cp_worker;
GRANT SELECT, INSERT ON plt01.ppl_custom_field_values TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (value_text, updated_at, updated_by, correlation_id)
    ON plt01.ppl_custom_field_values TO veyro_cp_app, veyro_cp_worker;

-- **A note's body carries no UPDATE grant.** What a coach wrote about a client is what they
-- wrote; a correction is a new note and a retraction is a withdrawal, both of which leave the
-- original visible. A note that could be edited is a note nobody can rely on in the dispute it
-- exists for.
GRANT SELECT, INSERT ON plt01.ppl_person_notes TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (withdrawn_at, withdrawn_by, withdraw_reason) ON plt01.ppl_person_notes
    TO veyro_cp_app, veyro_cp_worker;

-- A candidate is decided once. The pair and the signals that produced it carry no UPDATE, so
-- the evidence an operator acted on cannot be rewritten after the fact.
GRANT SELECT, INSERT ON plt01.ppl_duplicate_candidates TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (status, decided_at, decided_by, decision_reason)
    ON plt01.ppl_duplicate_candidates TO veyro_cp_app, veyro_cp_worker;

-- The merge record: what happened carries no UPDATE at all, only the reversal.
GRANT SELECT, INSERT ON plt01.ppl_merges TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (reversed_at, reversed_by, reverse_reason, reverse_correlation_id)
    ON plt01.ppl_merges TO veyro_cp_app, veyro_cp_worker;
-- **A merge copies; it does not move**, and the header says so above. `person_id` carries no
-- UPDATE grant on any of the tables a merge touches and no table here carries DELETE, so the
-- losing record keeps its rows and the survivor gets its own. The consequence is that a
-- person's data exists under two ids after a merge, which is why MOD-009's erasure resolves the
-- whole merge cluster rather than one id -- a reviewer cleared one side and watched the other
-- keep the name, the birth date, the address and a health note while the run recorded `done`.

-- Insert-only, in full. A projection that could be edited in place would be a second,
-- divergent copy of history rather than a view of it -- and `summary` is the one column a
-- rebuild would be tempted to "fix".
GRANT SELECT, INSERT ON plt01.ppl_timeline_entries TO veyro_cp_app, veyro_cp_worker;

-- MOD-027 slice 1 — ECO/CRM: the lead, its pipeline, its interests and its touchpoints.
--
-- Design record: `knowledge/00-Decisions/ADR-0010-mod027-crm-lead-pipeline-and-trial.md`.
-- Slices 2 (the trial and its conversion), 3 (lost, reopen and the source-effectiveness read)
-- and 4 (the conversation record) follow; nothing here depends on them, which is why this is
-- the slice that lands first.
--
-- Four decisions from the ADR and the canvases are visible in the shapes below:
--
--   * **A lead is a `ppl_persons` row, and this is the sales record attached to it.**
--     ADM-CRM-01 states it as a structural requirement -- "a lead, a trialist and a member are
--     one record at three stages, never three records" -- and ADM-CRM-06 repeats it: "the lead
--     ID becomes the member ID -- this is the duplicate-entry fix from the UX review, enforced
--     structurally rather than by discipline". So there is no name, no phone and no email in
--     this module at all: MOD-014 owns the person and `ppl_contact_points` is, in its own
--     registry entry, "the only copy of a member's address in this build". A second copy here
--     would be MOD-013's shadow-database objection with a sales team editing one of them.
--   * **The stage stored is the *sales* stage and the last two columns are derived.** The
--     board draws New, Contacted, Toured, On trial, Joined; the last two are "this person has
--     an active membership on a trial product" and "... not a trial product", which MOD-017
--     answers. A stored `on_trial` would be a second definition of whether somebody has a
--     membership and would go stale the moment a trial lapsed -- MOD-018's
--     one-module-two-definitions finding, created on purpose.
--   * **`lost` is deliberately absent from the stage domain.** ADM-CRM-07 is slice 3, and a
--     declared value nothing writes is this build's most-repeated finding -- found in MOD-012,
--     MOD-013, MOD-016, MOD-017, MOD-020 and MOD-022. The slice that writes it adds it.
--   * **A source is a tenant's own row, not a string.** The canvas draws a dropdown
--     ("SOURCE · OPTIONAL Sweifieh open day ▾") and ADM-RPT-03 groups conversions by it, so
--     free text would make the one report this field exists for a group-by over typos --
--     MOD-026's queue finding, and MOD-010's restricted-field argument applied to a
--     discriminator. The set is open by design and the authority is the tenant, which is
--     MOD-012's test for a row rather than code.

-- ------------------------------------------------------------------ the sources
--
-- Open by design: "Sweifieh open day" is an event a club ran, and no closed vocabulary this
-- repository could write would contain it. Retired rather than deleted, because a lead that
-- came through a source nobody runs any more still came through it, and ADM-RPT-03 reads the
-- history.
CREATE TABLE plt01.crm_lead_sources (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    source_id uuid NOT NULL DEFAULT gen_random_uuid(),
    source_key text NOT NULL,
    display_name text NOT NULL,
    -- Which club ran it, where that is a fact. A scope rather than a boundary: `permit`
    -- resolves tenant-wide, so a club manager sees every source -- MOD-014's standing gap,
    -- said here rather than implied by a column that looks like it restricts something.
    location_id uuid,
    status text NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    create_correlation_id uuid NOT NULL,
    retired_at timestamptz,
    retired_by uuid,
    retire_reason text,
    retire_correlation_id uuid,
    PRIMARY KEY (tenant_id, source_id),
    FOREIGN KEY (tenant_id, location_id)
        REFERENCES plt01.locations (tenant_id, location_id),
    CONSTRAINT crm_lead_sources_key_shape
        CHECK (source_key ~ '^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*)*$'
               AND length(source_key) BETWEEN 2 AND 63),
    CONSTRAINT crm_lead_sources_name_stated CHECK (display_name ~ '[^[:space:]]'),
    CONSTRAINT crm_lead_sources_status CHECK (status IN ('active', 'retired')),
    -- One decision, so its three facts arrive together. `coalesce` is load-bearing: a CHECK
    -- passes on NULL, so without it a source could be retired with no stated reason -- the
    -- trap MOD-014 and MOD-021 each paid for once.
    CONSTRAINT crm_lead_sources_retirement_attributed CHECK (
        (retired_at IS NULL AND retired_by IS NULL AND retire_reason IS NULL
         AND retire_correlation_id IS NULL)
        OR (retired_at IS NOT NULL AND retired_by IS NOT NULL
            AND coalesce(retire_reason, '') ~ '[^[:space:]]'
            AND retire_correlation_id IS NOT NULL)),
    CONSTRAINT crm_lead_sources_retired_is_retired
        CHECK ((status = 'retired') = (retired_at IS NOT NULL))
);
ALTER TABLE plt01.crm_lead_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.crm_lead_sources FORCE ROW LEVEL SECURITY;
CREATE POLICY crm_lead_sources_tenant ON plt01.crm_lead_sources
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE UNIQUE INDEX crm_lead_sources_one_key
    ON plt01.crm_lead_sources (tenant_id, source_key);

-- -------------------------------------------------------------------- the lead
--
-- **One per person, for ever.** ADM-CRM-07: "Not deleted. Reopenable, and re-contact after 90
-- days is a supported flow rather than a fresh record." A second row for the same person is
-- exactly the duplicate the design is structured to prevent, so the uniqueness is on
-- `person_id` and not on `(person_id, status)`.
--
-- **`owner_person_id` is nullable, because the board draws unassigned leads.** The canvas's
-- own counts -- "36 open leads · 7 going cold" -- are over leads nobody has claimed as much as
-- over claimed ones, and a required owner would mean the add-lead form could not be the two
-- fields it is drawn as: "Name and phone are enough. Everything else can wait."
CREATE TABLE plt01.crm_leads (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    lead_id uuid NOT NULL DEFAULT gen_random_uuid(),
    -- MOD-014's person. Every name, phone number and email on this module's screens is read
    -- through MOD-014's own gate and masked by its rules; nothing is copied here.
    person_id uuid NOT NULL,
    -- `new`, `contacted`, `toured`. `on_trial` and `joined` are MOD-017's answer and `lost`
    -- is slice 3's -- see the header.
    stage text NOT NULL DEFAULT 'new',
    stage_changed_at timestamptz NOT NULL DEFAULT now(),
    source_id uuid,
    owner_person_id uuid,
    -- ADM-CRM-02's NEXT ACTION column. Both halves or neither: a date with no action is a
    -- reminder about nothing, and an action with no date is a note.
    next_action text,
    next_action_on date,
    -- MOD-014's convention. Two salespeople editing one lead is the ordinary case, and
    -- last-write-wins discards whichever finished first and leaves no trace.
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, lead_id),
    FOREIGN KEY (tenant_id, person_id)
        REFERENCES plt01.ppl_persons (tenant_id, person_id),
    FOREIGN KEY (tenant_id, source_id)
        REFERENCES plt01.crm_lead_sources (tenant_id, source_id),
    FOREIGN KEY (tenant_id, owner_person_id)
        REFERENCES plt01.ppl_persons (tenant_id, person_id),
    CONSTRAINT crm_leads_stage CHECK (stage IN ('new', 'contacted', 'toured')),
    CONSTRAINT crm_leads_next_action_paired
        CHECK ((next_action IS NULL) = (next_action_on IS NULL)),
    CONSTRAINT crm_leads_next_action_stated
        CHECK (next_action IS NULL OR next_action ~ '[^[:space:]]'),
    CONSTRAINT crm_leads_next_action_bounded
        CHECK (next_action IS NULL OR length(next_action) <= 200),
    CONSTRAINT crm_leads_version_positive CHECK (version >= 1)
);
ALTER TABLE plt01.crm_leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.crm_leads FORCE ROW LEVEL SECURITY;
CREATE POLICY crm_leads_tenant ON plt01.crm_leads
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
-- The duplicate the design exists to prevent, refused by the database rather than by the
-- service's own check at the door: `GET /people/contact-match` catches the common case while
-- somebody is typing, and this catches the race and the caller that did not look.
CREATE UNIQUE INDEX crm_leads_one_per_person ON plt01.crm_leads (tenant_id, person_id);
-- ADM-CRM-02 sorts by age and filters by owner and stage; "Mine · 12" is the default for a
-- salesperson and the board counts by stage.
CREATE INDEX crm_leads_by_stage ON plt01.crm_leads (tenant_id, stage, created_at DESC);
CREATE INDEX crm_leads_by_owner ON plt01.crm_leads (tenant_id, owner_person_id, created_at DESC)
    WHERE owner_person_id IS NOT NULL;

-- --------------------------------------------------------------- the interests
--
-- ADM-CRM-04 offers three and ADM-CRM-03 renders a *set* of them -- "interested in classes and
-- PT" -- so this is a child table rather than a column. A closed vocabulary, because unlike a
-- source these are what the business sells rather than where a lead came from, and a report
-- that counted "classes" and "Classes" separately would be the finding this module avoided one
-- table up.
CREATE TABLE plt01.crm_lead_interests (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    lead_id uuid NOT NULL,
    interest text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    recorded_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, lead_id, interest),
    FOREIGN KEY (tenant_id, lead_id)
        REFERENCES plt01.crm_leads (tenant_id, lead_id),
    CONSTRAINT crm_lead_interests_vocabulary
        CHECK (interest IN ('classes', 'pt', 'gym_only'))
);
ALTER TABLE plt01.crm_lead_interests ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.crm_lead_interests FORCE ROW LEVEL SECURITY;
CREATE POLICY crm_lead_interests_tenant ON plt01.crm_lead_interests
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ------------------------------------------------------------- the touchpoints
--
-- ADM-CRM-03's TOUCHPOINTS list: "Met Yasmin at the open day · asked twice about spin". Prose
-- a salesperson writes, which is why it is a table here and not a MOD-014 timeline entry --
-- that timeline is *projected* from declared events with a renderer each, and a sales note is
-- not an event anything emits. The profile composes the two, as the Member 360 composes four
-- modules, and does not join them.
--
-- **Insert-only, and that is what makes it a record.** A touchpoint somebody could edit is a
-- touchpoint nobody can rely on in the conversation it exists to document -- MOD-014's note
-- rule, and the reason a correction is a new touchpoint.
--
-- **`summary` is prose and is where a health fact will go in practice.** MOD-017 and MOD-019
-- both paid for discovering that about a free-text reason column, so this one is declared in
-- MOD-009's registry as residue and is masked for a reader who cannot write one -- the same
-- trade `scheduling.session.change` makes.
CREATE TABLE plt01.crm_touchpoints (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    touchpoint_id uuid NOT NULL DEFAULT gen_random_uuid(),
    lead_id uuid NOT NULL,
    kind text NOT NULL,
    -- When it happened, which is not when it was typed: a salesperson writes up Friday's open
    -- day on Monday, and "No contact · 2 days" is counted from the former.
    occurred_at timestamptz NOT NULL,
    summary text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    recorded_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, touchpoint_id),
    FOREIGN KEY (tenant_id, lead_id)
        REFERENCES plt01.crm_leads (tenant_id, lead_id),
    CONSTRAINT crm_touchpoints_kind
        CHECK (kind IN ('call', 'message', 'email', 'visit', 'tour', 'note')),
    CONSTRAINT crm_touchpoints_summary_stated CHECK (summary ~ '[^[:space:]]'),
    CONSTRAINT crm_touchpoints_summary_bounded CHECK (length(summary) <= 2000),
    -- Forward-only, against the server's clock rather than between two columns the same
    -- writer supplies -- MOD-021's finding, where a window measured that way was a minute
    -- starting whenever the writer said. A touchpoint in the future is a note about something
    -- that has not happened, and "no contact for two days" is counted from this column.
    CONSTRAINT crm_touchpoints_not_in_the_future
        CHECK (occurred_at <= recorded_at + interval '5 minutes')
);
ALTER TABLE plt01.crm_touchpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.crm_touchpoints FORCE ROW LEVEL SECURITY;
CREATE POLICY crm_touchpoints_tenant ON plt01.crm_touchpoints
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
-- The timeline, newest first, and the one read "No contact 48h" is computed from.
CREATE INDEX crm_touchpoints_by_lead
    ON plt01.crm_touchpoints (tenant_id, lead_id, occurred_at DESC);

-- ------------------------------------------------------------------- privileges
--
-- No TRUNCATE, no REFERENCES, no DELETE and no PUBLIC grant anywhere, which the prefix-free
-- sweeps in the isolation suite assert over the whole schema rather than per table.

GRANT SELECT, INSERT ON plt01.crm_lead_sources TO veyro_cp_app, veyro_cp_worker;
-- The label and the retirement. Not `source_key`: a lead cites the source by id and the key is
-- what a report groups by, so re-keying one would silently merge two histories -- MOD-016's
-- `cat_prices.effective_to` finding, which is a granted column no service writes, avoided by
-- not granting it.
GRANT UPDATE (display_name, status, retired_at, retired_by, retire_reason,
              retire_correlation_id)
    ON plt01.crm_lead_sources TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.crm_leads TO veyro_cp_app, veyro_cp_worker;
-- Not `person_id`: re-pointing a lead at another person is the duplicate-entry defect this
-- module is structured against, arriving through an UPDATE. Not `created_at` either, because
-- age is the column ADM-CRM-02 says "matters" and a lead whose age could be reset is a lead
-- that never goes cold.
GRANT UPDATE (stage, stage_changed_at, source_id, owner_person_id, next_action,
              next_action_on, version)
    ON plt01.crm_leads TO veyro_cp_app, veyro_cp_worker;

-- **No UPDATE at all.** An interest is recorded or withdrawn, and withdrawing is slice 3's
-- work alongside `lost`; until then the set only grows, which is honest for a first slice and
-- is stated rather than discovered.
GRANT SELECT, INSERT ON plt01.crm_lead_interests TO veyro_cp_app, veyro_cp_worker;

-- **No UPDATE at all**, which is what makes the timeline a record -- see the table's comment.
GRANT SELECT, INSERT ON plt01.crm_touchpoints TO veyro_cp_app, veyro_cp_worker;

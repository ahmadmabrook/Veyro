-- MOD-019 OPS-01: scheduling, resources and capacity.
--
-- **Twelve `sch_` tables, under the same forced RLS as every other `plt01` table.** The pattern in
-- `0001_organization_hierarchy.sql` is copied exactly and each of its four parts is
-- load-bearing: `tenant_id NOT NULL`, a tenant-leading primary key, ENABLE *and* FORCE row
-- level security, and a policy whose predicate is the approved one on both halves. A
-- composite foreign key carries `tenant_id` into every parent reference, so a child cannot
-- point at another tenant's row even with the predicate satisfied.
--
-- Three decisions shape the whole file, and each answers a paragraph rather than a preference:
--
--   * **The rule and the sessions it generated are different rows, and the rule is immutable
--     once published.** Paragraph 4149: "Recurring schedule definition is separate from
--     generated occurrences so historical instances remain stable after template edits." So
--     `sch_recurrence_rules` is one row per template version with no UPDATE grant on anything
--     that describes the recurrence, a session cites the exact rule it came from, and editing
--     next month's class leaves last month's sessions as they were. A design that recomputed
--     occurrences from the current rule would rewrite history on every typo fix.
--
--   * **A session stores a UTC instant and the local facts it came from.** Paragraph 4150:
--     "store UTC instants and source local timezone/recurrence rule for correct DST behavior."
--     Both, because the instant is what orders a schedule and the local date is what a member
--     recognises -- and across a clock change neither is derivable from the other without the
--     timezone.
--
--   * **Capacity is held, not counted.** Paragraph 4146 asks for "optimistic concurrency or
--     atomic reservation counters to prevent overbooking", and there is no `held_count` column
--     anywhere here: `sch_capacity_holds` is one row per place and the count is its sum, taken
--     under a row lock on the session. MOD-018 spent four review rounds on cached totals and
--     the lesson is in this file by omission -- which is why the column-list pin in the
--     isolation suite compares the whole list rather than the columns somebody reasoned about.

-- ---------------------------------------------------------------- resources
--
-- OPS-01-R01: "Resource model for staff, room, zone, court, equipment, service and composite
-- requirements." One table for all seven, because one scheduling engine for every bookable
-- thing (paragraph 1831) is only possible if they are the same shape -- what differs is the
-- *requirement*, which is its own table below.
CREATE TABLE plt01.sch_resources (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    resource_id uuid NOT NULL DEFAULT gen_random_uuid(),
    -- A tenant's own code for it, so a rota can be read without uuids.
    resource_code text NOT NULL,
    resource_kind text NOT NULL,
    display_name text NOT NULL,
    -- Where it is. A room cannot move; a member of staff can, which is what the travel buffer
    -- on `sch_availability_windows` is about. NULL means the resource is not tied to a site.
    brand_id uuid,
    location_id uuid,
    -- For `equipment`: how many there are. Twenty bikes is one row with a quantity of twenty,
    -- never twenty rows, because the question a booking asks is "are there enough".
    quantity integer NOT NULL DEFAULT 1,
    -- The person a `staff` resource is, where the tenant has one on record. MOD-014 owns the
    -- person; this is the link, and it has a composite foreign key because it can be checked.
    person_id uuid,
    status text NOT NULL DEFAULT 'active',
    retired_at timestamptz,
    retired_by uuid,
    retire_correlation_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, resource_id),
    UNIQUE (tenant_id, resource_code),
    FOREIGN KEY (tenant_id, brand_id) REFERENCES plt01.brands (tenant_id, brand_id),
    FOREIGN KEY (tenant_id, location_id) REFERENCES plt01.locations (tenant_id, location_id),
    FOREIGN KEY (tenant_id, person_id) REFERENCES plt01.ppl_persons (tenant_id, person_id),
    CONSTRAINT sch_resources_code_shape
        CHECK (resource_code ~ '^[A-Z0-9][A-Z0-9._-]{1,47}$'),
    CONSTRAINT sch_resources_kind_shape CHECK (resource_kind ~ '^[a-z][a-z0-9_]{1,31}$'),
    CONSTRAINT sch_resources_name_not_blank CHECK (display_name ~ '[^[:space:]]'),
    CONSTRAINT sch_resources_quantity_sane CHECK (quantity >= 1 AND quantity <= 10000),
    -- **A location names a brand**, the same hierarchy rule MOD-018's accounts carry: a
    -- location-scoped row that does not say which brand cannot be read by a brand-scoped role.
    CONSTRAINT sch_resources_location_names_a_brand
        CHECK (location_id IS NULL OR brand_id IS NOT NULL),
    CONSTRAINT sch_resources_status CHECK (status IN ('active', 'retired')),
    CONSTRAINT sch_resources_retired_is_retired
        CHECK (status <> 'retired' OR retired_at IS NOT NULL),
    -- **Who withdrew a resource.** Retiring the only studio takes every class in it off the
    -- schedule, so the question afterwards is always who decided.
    CONSTRAINT sch_resources_retirement_attributed CHECK (
        (retired_at IS NULL AND retired_by IS NULL AND retire_correlation_id IS NULL)
        OR (retired_at IS NOT NULL AND retired_by IS NOT NULL
            AND retire_correlation_id IS NOT NULL))
);
CREATE INDEX sch_resources_by_kind
    ON plt01.sch_resources (tenant_id, resource_kind, status);
CREATE INDEX sch_resources_by_location
    ON plt01.sch_resources (tenant_id, location_id) WHERE location_id IS NOT NULL;
CREATE INDEX sch_resources_by_person
    ON plt01.sch_resources (tenant_id, person_id) WHERE person_id IS NOT NULL;
ALTER TABLE plt01.sch_resources ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.sch_resources FORCE ROW LEVEL SECURITY;
CREATE POLICY sch_resources_tenant ON plt01.sch_resources
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **A retired resource does not come back**, and the retirement is recorded once. MOD-018's
-- rule, which it learned from MOD-009: a CHECK cannot see what a row used to be, so an
-- attribution constraint says nothing about whether the attribution was replaced.
CREATE OR REPLACE FUNCTION plt01.sch_resource_retirement_is_final()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF OLD.status = 'retired' AND NEW.status <> 'retired' THEN
        RAISE EXCEPTION
            'resource % is retired; add a new one rather than reviving it',
            OLD.resource_code;
    END IF;
    -- The correlation is in here too: it is in the UPDATE grant, and an attribution CHECK
    -- cannot see what the row used to be.
    IF OLD.retired_at IS NOT NULL AND (
        NEW.retired_at IS DISTINCT FROM OLD.retired_at
        OR NEW.retired_by IS DISTINCT FROM OLD.retired_by
        OR NEW.retire_correlation_id IS DISTINCT FROM OLD.retire_correlation_id) THEN
        RAISE EXCEPTION
            'the retirement of resource % has already been recorded', OLD.resource_code;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER sch_resources_one_way
    BEFORE UPDATE ON plt01.sch_resources
    FOR EACH ROW EXECUTE FUNCTION plt01.sch_resource_retirement_is_final();

-- ---------------------------------------------------------------- availability
--
-- OPS-01-R03: "Availability, working hours, breaks, time off, substitutions and cross-location
-- travel buffers." Three window kinds in one table because they are the same shape -- a span
-- of local time that adds or removes availability -- and separate rows because a time-off
-- request has to outlive a change to the working hours it overlapped.
CREATE TABLE plt01.sch_availability_windows (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    window_id uuid NOT NULL DEFAULT gen_random_uuid(),
    resource_id uuid NOT NULL,
    window_kind text NOT NULL,
    -- **Local time, and the zone it is local to.** A rota is written in local time and a clock
    -- change must not move somebody's shift, which is paragraph 4150 applied to people rather
    -- than to sessions.
    timezone text NOT NULL,
    starts_at time NOT NULL,
    ends_at time NOT NULL,
    -- Weekly or dated, never both: "every Tuesday" and "this Tuesday" are different rows, and
    -- one nullable pair would make them the same.
    weekday smallint,
    on_date date,
    -- Why, for time off. A break needs none -- it is part of the rota -- and an absence does.
    reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, window_id),
    FOREIGN KEY (tenant_id, resource_id)
        REFERENCES plt01.sch_resources (tenant_id, resource_id),
    CONSTRAINT sch_availability_windows_kind
        CHECK (window_kind IN ('working', 'break', 'time_off')),
    CONSTRAINT sch_availability_windows_zone_shape
        CHECK (timezone ~ '^[A-Za-z][A-Za-z0-9+_/-]{1,63}$'),
    -- **A window ends after it starts.** One over midnight is two windows, because the day it
    -- belongs to is otherwise unanswerable -- and a rota that cannot say which day a shift is
    -- on is a rota nobody can read back.
    CONSTRAINT sch_availability_windows_ordered CHECK (ends_at > starts_at),
    CONSTRAINT sch_availability_windows_weekly_or_dated
        CHECK ((weekday IS NULL) <> (on_date IS NULL)),
    CONSTRAINT sch_availability_windows_weekday_shape
        CHECK (weekday IS NULL OR (weekday >= 0 AND weekday <= 6)),
    CONSTRAINT sch_availability_windows_reason_not_blank
        CHECK (reason IS NULL OR reason ~ '[^[:space:]]'),
    -- Time off states why; a working window and a break do not, because they are the rota.
    CONSTRAINT sch_availability_windows_absence_reasoned
        CHECK (window_kind <> 'time_off' OR coalesce(reason, '') ~ '[^[:space:]]')
);
CREATE INDEX sch_availability_windows_by_resource
    ON plt01.sch_availability_windows (tenant_id, resource_id, window_kind);
CREATE INDEX sch_availability_windows_by_date
    ON plt01.sch_availability_windows (tenant_id, on_date) WHERE on_date IS NOT NULL;
ALTER TABLE plt01.sch_availability_windows ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.sch_availability_windows FORCE ROW LEVEL SECURITY;
CREATE POLICY sch_availability_windows_tenant ON plt01.sch_availability_windows
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- templates and their rules
--
-- OPS-01-R02 and OPS-01-R06. **A template is an identity and a rule is a version of it**,
-- which is the two entities the TSD names (ScheduleTemplate, RecurrenceRule) and also what
-- paragraph 4149 needs: a session cites the exact rule version it was generated from, so
-- publishing a new rule leaves every existing session exactly as it was.
CREATE TABLE plt01.sch_templates (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    template_id uuid NOT NULL DEFAULT gen_random_uuid(),
    template_code text NOT NULL,
    display_name text NOT NULL,
    -- What this template schedules. A `service` resource carries the format and its
    -- requirements; the template says when it runs.
    service_resource_id uuid NOT NULL,
    location_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'draft',
    -- The version currently generating sessions. NULL while the template is a draft.
    live_rule_id uuid,
    published_at timestamptz,
    published_by uuid,
    publish_correlation_id uuid,
    retired_at timestamptz,
    retired_by uuid,
    retire_reason text,
    -- The correlation, which `sch_resources` has carried from the start and this did not: the
    -- route took one, the service dropped it, and MOD-008 audits denials rather than allowed
    -- actions -- so stopping a recurring class left no trace anybody could follow back to the
    -- request that did it. Found by review.
    retire_correlation_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, template_id),
    UNIQUE (tenant_id, template_code),
    FOREIGN KEY (tenant_id, service_resource_id)
        REFERENCES plt01.sch_resources (tenant_id, resource_id),
    FOREIGN KEY (tenant_id, location_id) REFERENCES plt01.locations (tenant_id, location_id),
    CONSTRAINT sch_templates_code_shape
        CHECK (template_code ~ '^[A-Z0-9][A-Z0-9._-]{1,47}$'),
    CONSTRAINT sch_templates_name_not_blank CHECK (display_name ~ '[^[:space:]]'),
    CONSTRAINT sch_templates_status CHECK (status IN ('draft', 'published', 'retired')),
    -- A published template has a live rule and a publication; a draft has neither.
    CONSTRAINT sch_templates_published_has_a_rule
        CHECK (status = 'draft' OR live_rule_id IS NOT NULL),
    CONSTRAINT sch_templates_publication_attributed CHECK (
        (published_at IS NULL AND published_by IS NULL AND publish_correlation_id IS NULL)
        OR (published_at IS NOT NULL AND published_by IS NOT NULL
            AND publish_correlation_id IS NOT NULL)),
    CONSTRAINT sch_templates_published_is_published
        CHECK (status = 'draft' OR published_at IS NOT NULL),
    -- **Retiring a schedule states why.** It stops a recurring class, which is the thing
    -- members notice, and nothing else on the row can answer the question.
    CONSTRAINT sch_templates_retirement_attributed CHECK (
        (retired_at IS NULL AND retired_by IS NULL AND retire_reason IS NULL
         AND retire_correlation_id IS NULL)
        OR (retired_at IS NOT NULL AND retired_by IS NOT NULL
            AND coalesce(retire_reason, '') ~ '[^[:space:]]'
            AND retire_correlation_id IS NOT NULL)),
    CONSTRAINT sch_templates_retired_is_retired
        CHECK (status <> 'retired' OR retired_at IS NOT NULL)
);
CREATE INDEX sch_templates_by_location
    ON plt01.sch_templates (tenant_id, location_id, status);
ALTER TABLE plt01.sch_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.sch_templates FORCE ROW LEVEL SECURITY;
CREATE POLICY sch_templates_tenant ON plt01.sch_templates
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- The RecurrenceRule entity: one row per version of a template's recurrence.
--
-- **Immutable once a session cites it**, which the grants below enforce by giving the recurrence
-- columns no UPDATE at all. A rule a session points at describes what that session *is*; an
-- editable one would let somebody change what last month's class had been, which is the
-- history rewrite paragraph 4149 exists to prevent.
CREATE TABLE plt01.sch_recurrence_rules (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    rule_id uuid NOT NULL DEFAULT gen_random_uuid(),
    template_id uuid NOT NULL,
    version integer NOT NULL,
    frequency text NOT NULL,
    -- The local time of day and the zone it is local to. Not a UTC instant: paragraph 4150,
    -- and an 18:00 class is at 18:00 for the member whatever the clocks did.
    local_time time NOT NULL,
    timezone text NOT NULL,
    duration_minutes integer NOT NULL,
    starts_on date NOT NULL,
    until_date date NOT NULL,
    -- Monday=0 .. Sunday=6, which is `date.weekday()`'s own numbering so nothing converts
    -- between two conventions -- a conversion is where an off-by-one lands a class on the
    -- wrong day.
    weekdays smallint[] NOT NULL DEFAULT '{}',
    week_of_month smallint,
    -- OPS-01-R02's exceptions and seasonality: a public holiday, a shutdown week. Kept on the
    -- rule rather than deleted from the sessions, so "why is there no class that Monday" is
    -- answerable.
    excluded_dates date[] NOT NULL DEFAULT '{}',
    -- **When this version starts applying.** Paragraph 1841's effective dating: sessions
    -- before it are left exactly as they were.
    effective_from date NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, rule_id),
    UNIQUE (tenant_id, template_id, version),
    FOREIGN KEY (tenant_id, template_id)
        REFERENCES plt01.sch_templates (tenant_id, template_id),
    CONSTRAINT sch_recurrence_rules_version_positive CHECK (version >= 1),
    CONSTRAINT sch_recurrence_rules_frequency
        CHECK (frequency IN ('once', 'daily', 'weekly', 'monthly_by_weekday')),
    CONSTRAINT sch_recurrence_rules_zone_shape
        CHECK (timezone ~ '^[A-Za-z][A-Za-z0-9+_/-]{1,63}$'),
    CONSTRAINT sch_recurrence_rules_duration_sane
        CHECK (duration_minutes >= 1 AND duration_minutes <= 1440),
    CONSTRAINT sch_recurrence_rules_dates_ordered CHECK (until_date >= starts_on),
    -- The horizon the generator enforces, stated here too because the generator is not the
    -- only writer this table could have.
    CONSTRAINT sch_recurrence_rules_horizon
        CHECK (until_date - starts_on <= 400),
    CONSTRAINT sch_recurrence_rules_once_is_one_day
        CHECK (frequency <> 'once' OR until_date = starts_on),
    -- A weekly or monthly rule names its days; the other two do not.
    CONSTRAINT sch_recurrence_rules_weekdays_match_frequency CHECK (
        (frequency IN ('weekly', 'monthly_by_weekday')) = (cardinality(weekdays) > 0)),
    CONSTRAINT sch_recurrence_rules_weekdays_shape
        CHECK (weekdays <@ ARRAY[0, 1, 2, 3, 4, 5, 6]::smallint[]),
    CONSTRAINT sch_recurrence_rules_week_matches_frequency
        CHECK ((frequency = 'monthly_by_weekday') = (week_of_month IS NOT NULL)),
    CONSTRAINT sch_recurrence_rules_week_shape
        CHECK (week_of_month IS NULL
               OR week_of_month IN (1, 2, 3, 4, -1)),
    CONSTRAINT sch_recurrence_rules_exclusions_bounded
        CHECK (cardinality(excluded_dates) <= 200)
);
CREATE INDEX sch_recurrence_rules_by_template
    ON plt01.sch_recurrence_rules (tenant_id, template_id, version DESC);
ALTER TABLE plt01.sch_recurrence_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.sch_recurrence_rules FORCE ROW LEVEL SECURITY;
CREATE POLICY sch_recurrence_rules_tenant ON plt01.sch_recurrence_rules
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **A template's status moves one way.** A published template is changed by publishing a new
-- rule version, not by going back to draft: the demotion MOD-013's review found was a two-step
-- rewrite of already-approved content, and here it would change a class members have booked.
CREATE OR REPLACE FUNCTION plt01.sch_template_is_one_way()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF OLD.status <> NEW.status AND NOT (
        (OLD.status = 'draft' AND NEW.status = 'published')
        OR (OLD.status = 'published' AND NEW.status = 'retired')
    ) THEN
        RAISE EXCEPTION
            'a schedule template does not move from % to %', OLD.status, NEW.status;
    END IF;
    IF OLD.published_at IS NOT NULL AND (
        NEW.published_at IS DISTINCT FROM OLD.published_at
        OR NEW.published_by IS DISTINCT FROM OLD.published_by
        OR NEW.publish_correlation_id IS DISTINCT FROM OLD.publish_correlation_id) THEN
        RAISE EXCEPTION
            'the publication of template % has already been recorded', OLD.template_code;
    END IF;
    IF OLD.retired_at IS NOT NULL THEN
        RAISE EXCEPTION
            'template % is retired; publish a new one rather than reviving it',
            OLD.template_code;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER sch_templates_one_way
    BEFORE UPDATE ON plt01.sch_templates
    FOR EACH ROW EXECUTE FUNCTION plt01.sch_template_is_one_way();

-- **A template's live rule is one of its own**, and a trigger is the only thing that can say
-- so. `live_rule_id` carries no foreign key because the reference is circular -- a rule names
-- its template and the template names the rule it publishes -- and without this a publish
-- could point a template at *another* template's recurrence. Generation then reads the wrong
-- days and times under the right name, and every session it produced cites a rule belonging
-- to something else, which is paragraph 4149's stability guarantee inverted: the history is
-- stable and wrong.
--
-- Found by writing check 90's fixtures, which needed a retired template and could satisfy
-- every constraint on the row while naming a rule from a different one.
CREATE OR REPLACE FUNCTION plt01.sch_template_rule_belongs_to_it()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NEW.live_rule_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM plt01.sch_recurrence_rules r
         WHERE r.tenant_id = NEW.tenant_id
           AND r.rule_id = NEW.live_rule_id
           AND r.template_id = NEW.template_id
    ) THEN
        RAISE EXCEPTION
            'the live rule of template % is not a rule of that template', NEW.template_code;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER sch_templates_live_rule
    BEFORE INSERT OR UPDATE ON plt01.sch_templates
    FOR EACH ROW EXECUTE FUNCTION plt01.sch_template_rule_belongs_to_it();

-- What a template's sessions need, before expansion. OPS-01-R01's "composite requirements"
-- as rows: a spin class needs one instructor, one studio and twenty bikes, and the conflict
-- detector checks each.
--
-- **On the template rather than on the rule version.** A rule version is a change of *when*;
-- a requirement change is a change of what the class is. The session snapshots the expansion
-- either way -- that is `sch_session_resources` -- so the two do not have to be versioned
-- together, and versioning them together would mint a rule version every time somebody added
-- a mat.
CREATE TABLE plt01.sch_template_requirements (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    requirement_id uuid NOT NULL DEFAULT gen_random_uuid(),
    template_id uuid NOT NULL,
    requirement_kind text NOT NULL,
    quantity integer NOT NULL DEFAULT 1,
    -- Set to require *that* resource: the senior instructor, court three. NULL means any free
    -- one of the kind, which is a different booking and the reason both forms exist.
    resource_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, requirement_id),
    -- **A kind is required once.** Two requirements for `room` cannot say whether they mean
    -- the same room or different ones, so the engine would satisfy them independently and
    -- nothing would say which was meant. The partial index is on the anonymous form, because
    -- two requirements naming *different* resources of one kind is a composite and legitimate.
    FOREIGN KEY (tenant_id, template_id)
        REFERENCES plt01.sch_templates (tenant_id, template_id),
    FOREIGN KEY (tenant_id, resource_id)
        REFERENCES plt01.sch_resources (tenant_id, resource_id),
    CONSTRAINT sch_template_requirements_kind_shape
        CHECK (requirement_kind ~ '^[a-z][a-z0-9_]{1,31}$'),
    CONSTRAINT sch_template_requirements_quantity_sane
        CHECK (quantity >= 1 AND quantity <= 10000),
    -- A requirement naming a particular resource is for that one resource.
    CONSTRAINT sch_template_requirements_named_is_one
        CHECK (resource_id IS NULL OR quantity = 1),
    -- A service or composite requirement names which one: the kind alone describes nothing a
    -- session can hold.
    CONSTRAINT sch_template_requirements_offering_is_named
        CHECK (requirement_kind NOT IN ('service', 'composite') OR resource_id IS NOT NULL)
);
CREATE UNIQUE INDEX sch_template_requirements_one_per_kind
    ON plt01.sch_template_requirements (tenant_id, template_id, requirement_kind)
    WHERE resource_id IS NULL;
CREATE UNIQUE INDEX sch_template_requirements_one_per_resource
    ON plt01.sch_template_requirements (tenant_id, template_id, resource_id)
    WHERE resource_id IS NOT NULL;
ALTER TABLE plt01.sch_template_requirements ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.sch_template_requirements FORCE ROW LEVEL SECURITY;
CREATE POLICY sch_template_requirements_tenant ON plt01.sch_template_requirements
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- capacity policies
--
-- OPS-01-R04: "Capacity, setup/cleanup time, age/skill restrictions, equipment requirements and
-- entitlement checks." The policy belongs to the template, and a session **snapshots** it --
-- MOD-012's rule, where an install snapshots the version it was made against -- so raising a
-- class's capacity next month does not retrospectively change what last month's class held.
CREATE TABLE plt01.sch_capacity_policies (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    policy_id uuid NOT NULL DEFAULT gen_random_uuid(),
    template_id uuid NOT NULL,
    version integer NOT NULL,
    capacity integer NOT NULL,
    -- Minutes the resources are held beyond the session itself. The member's schedule still
    -- says the session's own end: conflating the two would either publish a class that runs
    -- longer than it does, or let the next one walk into a room being wiped down.
    setup_minutes integer NOT NULL DEFAULT 0,
    cleanup_minutes integer NOT NULL DEFAULT 0,
    waitlist_capacity integer NOT NULL DEFAULT 0,
    -- Extra places, in places rather than a percentage: paragraph 1888 allows "controlled
    -- overbooking", and a percentage of a twelve-place class is a fraction somebody rounds.
    overbook_places integer NOT NULL DEFAULT 0,
    -- The booking window, which is a property of the session rather than of the member --
    -- MOD-020 adds the member's own eligibility on top.
    opens_hours_before integer NOT NULL DEFAULT 168,
    closes_minutes_before integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, policy_id),
    UNIQUE (tenant_id, template_id, version),
    FOREIGN KEY (tenant_id, template_id)
        REFERENCES plt01.sch_templates (tenant_id, template_id),
    CONSTRAINT sch_capacity_policies_version_positive CHECK (version >= 1),
    CONSTRAINT sch_capacity_policies_capacity_sane
        CHECK (capacity >= 1 AND capacity <= 10000),
    CONSTRAINT sch_capacity_policies_setup_sane
        CHECK (setup_minutes >= 0 AND setup_minutes <= 120),
    CONSTRAINT sch_capacity_policies_cleanup_sane
        CHECK (cleanup_minutes >= 0 AND cleanup_minutes <= 120),
    CONSTRAINT sch_capacity_policies_waitlist_sane
        CHECK (waitlist_capacity >= 0 AND waitlist_capacity <= 10000),
    -- **Overbooking is extra places, so not negative** -- fewer places is a smaller capacity --
    -- and not beyond the capacity itself, which would make the room's own number meaningless.
    CONSTRAINT sch_capacity_policies_overbook_sane
        CHECK (overbook_places >= 0 AND overbook_places <= capacity),
    CONSTRAINT sch_capacity_policies_window_sane
        CHECK (opens_hours_before >= 0 AND opens_hours_before <= 8760
               AND closes_minutes_before >= 0 AND closes_minutes_before <= 525600)
);
ALTER TABLE plt01.sch_capacity_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.sch_capacity_policies FORCE ROW LEVEL SECURITY;
CREATE POLICY sch_capacity_policies_tenant ON plt01.sch_capacity_policies
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- The eligibility rules on a policy. OPS-01-R04's "age/skill restrictions ... and entitlement
-- checks", as rows because a session has several and each is a separate denial reason --
-- paragraph 1892 makes an understandable denial a Critical Control, and "you are not eligible"
-- is not one.
CREATE TABLE plt01.sch_restrictions (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    restriction_id uuid NOT NULL DEFAULT gen_random_uuid(),
    policy_id uuid NOT NULL,
    restriction_kind text NOT NULL,
    -- Years for an age restriction, a key for a skill or an entitlement. Text for both,
    -- because a column that held either would need a type nobody could constrain.
    restriction_value text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, restriction_id),
    UNIQUE (tenant_id, policy_id, restriction_kind, restriction_value),
    FOREIGN KEY (tenant_id, policy_id)
        REFERENCES plt01.sch_capacity_policies (tenant_id, policy_id),
    CONSTRAINT sch_restrictions_kind
        CHECK (restriction_kind IN ('min_age', 'max_age', 'skill', 'entitlement')),
    CONSTRAINT sch_restrictions_value_not_blank
        CHECK (restriction_value ~ '[^[:space:]]'),
    -- An age is a number of years and a plausible one. A restriction nobody can evaluate is a
    -- restriction that refuses everybody, which is the direction this fails in.
    --
    -- **The bound is in the regex and there is no cast.** It was
    -- `restriction_value ~ '^[0-9]{1,3}$' AND restriction_value::integer <= 120`, and the
    -- mutation sweep showed what that rests on: weakening it by removing the regex left the
    -- cast alone, and `'sixteen'::integer` *raises* rather than returning false. So the
    -- constraint was correct only because PostgreSQL happened to evaluate the left conjunct
    -- first, which it does not promise -- and on the day it did not, an ordinary typo at the
    -- front desk would answer 500 with `invalid input syntax for type integer` instead of a
    -- clean refusal. A regex that encodes 0-120 needs no cast and no evaluation order.
    CONSTRAINT sch_restrictions_age_is_a_number CHECK (
        restriction_kind NOT IN ('min_age', 'max_age')
        OR restriction_value ~ '^([0-9]|[1-9][0-9]|1[01][0-9]|120)$')
);
CREATE INDEX sch_restrictions_by_policy
    ON plt01.sch_restrictions (tenant_id, policy_id);
ALTER TABLE plt01.sch_restrictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.sch_restrictions FORCE ROW LEVEL SECURITY;
CREATE POLICY sch_restrictions_tenant ON plt01.sch_restrictions
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- the sessions
--
-- The ScheduledInstance entity: one row per occurrence, generated from a rule and then standing
-- on its own. **Everything it needs to be read is on the row or snapshotted beside it**, which
-- is what makes a session survive a template edit: the rule it came from, the capacity it was
-- published with, and the requirements it holds.
CREATE TABLE plt01.sch_sessions (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    session_id uuid NOT NULL DEFAULT gen_random_uuid(),
    template_id uuid NOT NULL,
    -- **The exact rule version this came from.** Not the template's current one: that is the
    -- whole of paragraph 4149, and it is why this is a foreign key to the rule rather than a
    -- join through the template.
    rule_id uuid NOT NULL,
    policy_id uuid NOT NULL,
    location_id uuid NOT NULL,
    -- The instant, and the local facts it came from. Both, because the instant orders a
    -- schedule and the local date is what a member recognises -- and across a clock change
    -- neither is derivable from the other without the timezone.
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    local_date date NOT NULL,
    timezone text NOT NULL,
    -- True when the local time did not exist that day and the session moved forward out of a
    -- spring-forward gap. One day a year, in one zone, and the row says so rather than leaving
    -- an hour's difference to be discovered.
    dst_adjusted boolean NOT NULL DEFAULT false,
    -- The capacity as published. Snapshotted from the policy, so raising a class's capacity
    -- next month does not retrospectively change what last month's class held.
    capacity integer NOT NULL,
    overbook_places integer NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'scheduled',
    cancelled_at timestamptz,
    cancelled_by uuid,
    cancellation_reason text,
    cancel_correlation_id uuid,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, session_id),
    -- **One session per rule per instant.** Generating twice is the ordinary case -- a publish
    -- that was retried, a worker that ran again -- and this is what makes the second run
    -- produce nothing rather than a duplicate class.
    UNIQUE (tenant_id, rule_id, starts_at),
    FOREIGN KEY (tenant_id, template_id)
        REFERENCES plt01.sch_templates (tenant_id, template_id),
    FOREIGN KEY (tenant_id, rule_id)
        REFERENCES plt01.sch_recurrence_rules (tenant_id, rule_id),
    FOREIGN KEY (tenant_id, policy_id)
        REFERENCES plt01.sch_capacity_policies (tenant_id, policy_id),
    FOREIGN KEY (tenant_id, location_id) REFERENCES plt01.locations (tenant_id, location_id),
    CONSTRAINT sch_sessions_ordered CHECK (ends_at > starts_at),
    CONSTRAINT sch_sessions_bounded
        CHECK (ends_at - starts_at <= interval '1 day'),
    CONSTRAINT sch_sessions_zone_shape
        CHECK (timezone ~ '^[A-Za-z][A-Za-z0-9+_/-]{1,63}$'),
    CONSTRAINT sch_sessions_capacity_sane CHECK (capacity >= 1 AND capacity <= 10000),
    CONSTRAINT sch_sessions_overbook_sane
        CHECK (overbook_places >= 0 AND overbook_places <= capacity),
    CONSTRAINT sch_sessions_status CHECK (status IN ('scheduled', 'cancelled', 'completed')),
    CONSTRAINT sch_sessions_cancelled_is_cancelled
        CHECK (status <> 'cancelled' OR cancelled_at IS NOT NULL),
    CONSTRAINT sch_sessions_completed_is_completed
        CHECK (status <> 'completed' OR completed_at IS NOT NULL),
    -- **A cancellation names who, why and under which declared reason.** The reason decides
    -- what a member is owed, which is why it is a declared value rather than prose: an
    -- instructor's illness and a weather closure are different conversations, and MOD-017's
    -- entitlement is what gets returned either way.
    CONSTRAINT sch_sessions_cancellation_attributed CHECK (
        (cancelled_at IS NULL AND cancelled_by IS NULL AND cancellation_reason IS NULL
         AND cancel_correlation_id IS NULL)
        OR (cancelled_at IS NOT NULL AND cancelled_by IS NOT NULL
            AND cancellation_reason IS NOT NULL AND cancel_correlation_id IS NOT NULL)),
    CONSTRAINT sch_sessions_cancellation_reason CHECK (
        cancellation_reason IS NULL
        OR cancellation_reason IN ('instructor_unavailable', 'resource_unavailable',
                                   'insufficient_bookings', 'facility_closed', 'weather',
                                   'other'))
);
CREATE INDEX sch_sessions_by_window
    ON plt01.sch_sessions (tenant_id, location_id, starts_at);
CREATE INDEX sch_sessions_by_template
    ON plt01.sch_sessions (tenant_id, template_id, starts_at);
CREATE INDEX sch_sessions_live
    ON plt01.sch_sessions (tenant_id, starts_at) WHERE status = 'scheduled';
ALTER TABLE plt01.sch_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.sch_sessions FORCE ROW LEVEL SECURITY;
CREATE POLICY sch_sessions_tenant ON plt01.sch_sessions
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- A session's resource holds: what it needs, expanded from the template's requirements at
-- generation and **snapshotted**, so changing a class's requirements next month does not change
-- what last month's class held.
CREATE TABLE plt01.sch_session_resources (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    assignment_id uuid NOT NULL DEFAULT gen_random_uuid(),
    session_id uuid NOT NULL,
    resource_id uuid NOT NULL,
    resource_kind text NOT NULL,
    -- How many of a countable resource this session holds. One for an exclusive kind, which
    -- the CHECK below makes the only possibility.
    quantity integer NOT NULL DEFAULT 1,
    -- **The window the resource is held for**, which is the session plus its setup and cleanup.
    -- Stored rather than derived, because the policy's margins can change and the hold a
    -- conflict was detected against has to stay what it was.
    holds_from timestamptz NOT NULL,
    holds_until timestamptz NOT NULL,
    -- **When this hold stopped applying**, for a substitution or a relocation. The row stays,
    -- so the window a past conflict was decided against is still readable; what the marker
    -- does is stop the replaced resource reading as busy for ever.
    --
    -- Without it a coach who went home ill still held that hour, so the conflict detector
    -- refused to schedule them anywhere else at that time -- and a relocated session kept the
    -- old room, which made the destination's calendar empty and the origin's wrong. Found by
    -- the HTTP tests. The division of labour is: this table says what the session holds *now*,
    -- and `sch_session_changes` is the insert-only history of who held what and why it moved.
    superseded_at timestamptz,
    superseded_by uuid,
    supersede_correlation_id uuid,
    assigned_at timestamptz NOT NULL DEFAULT now(),
    assigned_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    -- **One row per assignment, not one per (session, resource).** The key was the pair, which
    -- forced a re-assignment of the same resource -- putting a recovered coach back on the
    -- class they were substituted out of -- to be an `ON CONFLICT DO UPDATE` that cleared the
    -- supersede marker. That made `superseded_by` the one attribution column in the module a
    -- later write could erase: the name of whoever took a coach off a class, gone, with the row
    -- reading as though the supersession never happened. A reviewer found it as an undeclared
    -- column and it was worse than the declaration.
    --
    -- With an assignment of its own, a re-assignment is a new row, the superseded one keeps its
    -- attribution for ever, and the marker is write-once by the trigger below. The live-hold
    -- rule the pair used to carry is the partial unique index beside it -- the same shape
    -- `sch_capacity_holds` already uses for one live place per person.
    PRIMARY KEY (tenant_id, assignment_id),
    FOREIGN KEY (tenant_id, session_id)
        REFERENCES plt01.sch_sessions (tenant_id, session_id),
    FOREIGN KEY (tenant_id, resource_id)
        REFERENCES plt01.sch_resources (tenant_id, resource_id),
    CONSTRAINT sch_session_resources_supersede_attributed CHECK (
        (superseded_at IS NULL AND superseded_by IS NULL
         AND supersede_correlation_id IS NULL)
        OR (superseded_at IS NOT NULL AND superseded_by IS NOT NULL
            AND supersede_correlation_id IS NOT NULL)),
    CONSTRAINT sch_session_resources_kind_shape
        CHECK (resource_kind ~ '^[a-z][a-z0-9_]{1,31}$'),
    CONSTRAINT sch_session_resources_quantity_sane
        CHECK (quantity >= 1 AND quantity <= 10000),
    -- **An exclusive resource is held once.** A room held twice by one session is a modelling
    -- error, and the conflict detector's arithmetic for exclusive kinds assumes one.
    CONSTRAINT sch_session_resources_exclusive_is_one CHECK (
        resource_kind NOT IN ('staff', 'room', 'zone', 'court') OR quantity = 1),
    CONSTRAINT sch_session_resources_window_ordered CHECK (holds_until > holds_from)
);
-- The index the conflict detector reads: everything *still* holding a resource over a window.
-- Partial, because a superseded hold is history and the detector must not see it.
CREATE INDEX sch_session_resources_by_resource
    ON plt01.sch_session_resources (tenant_id, resource_id, holds_from, holds_until)
    WHERE superseded_at IS NULL;
-- **One live hold per resource per session**, which is what the primary key used to say. An
-- exclusive resource held twice by one session is a modelling error and the detector's
-- arithmetic assumes one; a *superseded* hold alongside a live one is the ordinary case after
-- a substitution, which is why this is partial.
CREATE UNIQUE INDEX sch_session_resources_one_live
    ON plt01.sch_session_resources (tenant_id, session_id, resource_id)
    WHERE superseded_at IS NULL;
CREATE INDEX sch_session_resources_by_session
    ON plt01.sch_session_resources (tenant_id, session_id);
ALTER TABLE plt01.sch_session_resources ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.sch_session_resources FORCE ROW LEVEL SECURITY;
CREATE POLICY sch_session_resources_tenant ON plt01.sch_session_resources
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **A supersession is recorded once.** The attribution CHECK beside the table cannot see what
-- the row used to be -- MOD-009's `sec_legal_holds` rule -- so without this, superseding a hold
-- again would replace the name of whoever did it first. Re-assigning the same resource is a new
-- row, which is what the assignment key is for.
CREATE OR REPLACE FUNCTION plt01.sch_assignment_supersede_is_final()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF OLD.superseded_at IS NOT NULL THEN
        RAISE EXCEPTION
            'this assignment was already superseded; re-assigning is a new assignment';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER sch_session_resources_one_way
    BEFORE UPDATE ON plt01.sch_session_resources
    FOR EACH ROW EXECUTE FUNCTION plt01.sch_assignment_supersede_is_final();

-- **A resource hold gets the guards a place hold has, which it had none of.**
-- `sch_hold_fits_the_session` refuses a *place* in a cancelled class and a reviewer pointed out
-- that nothing refused a *room*: a new hold could be written against a cancelled session, so
-- the room read as busy for a class nobody runs, and a retired resource could be assigned to a
-- live one. The window is bounded against the session too -- nothing stopped a one-hour class
-- holding a studio for four years, and the window columns carry no UPDATE grant, so the only
-- remedy afterwards was the supersede marker.
CREATE OR REPLACE FUNCTION plt01.sch_assignment_fits_the_session()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    session_status text;
    session_starts timestamptz;
    session_ends timestamptz;
    resource_status text;
BEGIN
    SELECT status, starts_at, ends_at
      INTO session_status, session_starts, session_ends
      FROM plt01.sch_sessions
     WHERE tenant_id = NEW.tenant_id AND session_id = NEW.session_id;
    IF session_status IS NULL THEN
        RAISE EXCEPTION 'an assignment names a session that does not exist';
    END IF;
    IF session_status <> 'scheduled' THEN
        RAISE EXCEPTION
            'this session is % and holds nothing further', session_status;
    END IF;
    SELECT status INTO resource_status
      FROM plt01.sch_resources
     WHERE tenant_id = NEW.tenant_id AND resource_id = NEW.resource_id;
    IF resource_status IS NULL THEN
        RAISE EXCEPTION 'an assignment names a resource that does not exist';
    END IF;
    IF resource_status <> 'active' THEN
        RAISE EXCEPTION 'this resource is % and is not assigned to anything', resource_status;
    END IF;
    -- The session's own span plus the widest margins a policy can declare, which is two hours
    -- either side. Derived rather than read from the policy: the policy can change and the
    -- hold a conflict was decided against cannot.
    IF NEW.holds_from < session_starts - interval '2 hours'
       OR NEW.holds_until > session_ends + interval '2 hours' THEN
        RAISE EXCEPTION
            'a resource is held for its session and its margins, not from % to %',
            NEW.holds_from, NEW.holds_until;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER sch_session_resources_fit
    BEFORE INSERT ON plt01.sch_session_resources
    FOR EACH ROW EXECUTE FUNCTION plt01.sch_assignment_fits_the_session();

-- ---------------------------------------------------------------- capacity holds
--
-- **The count of taken places, as rows.** Paragraph 4146 asks for "optimistic concurrency or
-- atomic reservation counters to prevent overbooking", and there is no `held_count` column on
-- `sch_sessions`: a cached total is a second authority that can disagree with the first, which
-- is MOD-018's COM-04-R07 argument applied to places instead of money.
--
-- **MOD-020 takes a hold; this module owns it.** Booking cannot read these tables to count what
-- is taken -- "no cross-domain write-table access" -- so the module that owns capacity owns the
-- hold, and booking's reservation cites one. The same shape as MOD-017's entitlement
-- reservation, for the same reason.
CREATE TABLE plt01.sch_capacity_holds (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    hold_id uuid NOT NULL DEFAULT gen_random_uuid(),
    session_id uuid NOT NULL,
    -- Who the place is for. MOD-014 owns the person and the composite foreign key is what
    -- stops a hold naming another tenant's member.
    person_id uuid NOT NULL,
    -- How many places. Above one for a household or a guest booking, which paragraph 1890
    -- names -- and the session's capacity is what bounds the total.
    places integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'held',
    -- What took it. `booking` is MOD-020's; `walk_in` is the front desk putting somebody in the
    -- room. Declared rather than free text, because a report of who is in a class has to be
    -- able to separate the two.
    source_kind text NOT NULL,
    source_ref text NOT NULL,
    released_at timestamptz,
    released_by uuid,
    release_reason text,
    release_correlation_id uuid,
    taken_at timestamptz NOT NULL DEFAULT now(),
    taken_by uuid NOT NULL,
    idempotency_key text NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, hold_id),
    UNIQUE (tenant_id, idempotency_key),
    -- **One live hold per person per session.** A member holding two places in one class by
    -- retrying is the double-consumption paragraph 4148 names for waitlists, one layer down.
    -- Partial, so a released hold does not block a later one: somebody who cancelled and
    -- rebooked is an ordinary case.
    FOREIGN KEY (tenant_id, session_id)
        REFERENCES plt01.sch_sessions (tenant_id, session_id),
    FOREIGN KEY (tenant_id, person_id) REFERENCES plt01.ppl_persons (tenant_id, person_id),
    CONSTRAINT sch_capacity_holds_places_sane CHECK (places >= 1 AND places <= 100),
    CONSTRAINT sch_capacity_holds_status CHECK (status IN ('held', 'released', 'attended')),
    CONSTRAINT sch_capacity_holds_source_kind
        CHECK (source_kind IN ('booking', 'walk_in', 'migration')),
    CONSTRAINT sch_capacity_holds_source_ref_not_blank
        CHECK (source_ref ~ '[^[:space:]]'),
    CONSTRAINT sch_capacity_holds_key_not_blank
        CHECK (idempotency_key ~ '[^[:space:]]'),
    CONSTRAINT sch_capacity_holds_released_is_released
        CHECK (status <> 'released' OR released_at IS NOT NULL),
    -- **Releasing a place states who and why.** It is the act that takes a member out of a
    -- class, and `veyro_cp_app` holds nothing in `iam`, so this row is the only record there
    -- can be.
    CONSTRAINT sch_capacity_holds_release_attributed CHECK (
        (released_at IS NULL AND released_by IS NULL AND release_reason IS NULL
         AND release_correlation_id IS NULL)
        OR (released_at IS NOT NULL AND released_by IS NOT NULL
            AND coalesce(release_reason, '') ~ '[^[:space:]]'
            AND release_correlation_id IS NOT NULL))
);
CREATE UNIQUE INDEX sch_capacity_holds_one_live_per_person
    ON plt01.sch_capacity_holds (tenant_id, session_id, person_id)
    WHERE status IN ('held', 'attended');
CREATE INDEX sch_capacity_holds_by_session
    ON plt01.sch_capacity_holds (tenant_id, session_id, status);
ALTER TABLE plt01.sch_capacity_holds ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.sch_capacity_holds FORCE ROW LEVEL SECURITY;
CREATE POLICY sch_capacity_holds_tenant ON plt01.sch_capacity_holds
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **A hold does not exceed the session's places, and the trigger is what means it.** The
-- service takes a row lock on the session and counts first, which gives the caller a readable
-- refusal; this holds for any other writer, which is the half paragraph 4146 is actually about.
-- A session that is not `scheduled` takes no holds at all: putting somebody into a cancelled
-- class is the worst failure available here.
--
-- **The "session does not exist" branch is a message, not the control.** The composite foreign
-- key is what actually refuses a hold on a session that is not there; this branch fires first,
-- because a BEFORE INSERT trigger runs before the reference is checked, and says so in a
-- sentence instead of a constraint name. The mutation sweep is what made the distinction
-- matter: dropping the trigger was "caught" by the foreign key, so the probe proved nothing
-- about the trigger until it learned to tell the two refusals apart.
CREATE OR REPLACE FUNCTION plt01.sch_hold_fits_the_session()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    session_status text;
    room integer;
    taken integer;
BEGIN
    -- **`FOR UPDATE`, because `FOR SHARE` does not conflict with `FOR SHARE`.** Two inserters
    -- held the share lock at once, neither saw the other's uncommitted hold, and both
    -- committed: a reviewer put four places in a two-place class with two ordinary
    -- transactions and no adversary. The service happens to be safe because `_session` takes
    -- `FOR UPDATE` before it counts -- but this trigger exists for the writer that is *not*
    -- the service, which is the half paragraph 4146 is actually about, and that half did not
    -- hold. `FOR UPDATE` still conflicts with the cancelling UPDATE, so the book-against-cancel
    -- exclusion `FOR SHARE` bought is kept.
    SELECT status, capacity + overbook_places INTO session_status, room
      FROM plt01.sch_sessions
     WHERE tenant_id = NEW.tenant_id AND session_id = NEW.session_id
       FOR UPDATE;
    IF session_status IS NULL THEN
        RAISE EXCEPTION 'a hold names a session that does not exist';
    END IF;
    IF session_status <> 'scheduled' THEN
        RAISE EXCEPTION
            'this session is % and takes no places', session_status;
    END IF;
    SELECT coalesce(sum(places), 0) INTO taken
      FROM plt01.sch_capacity_holds
     WHERE tenant_id = NEW.tenant_id AND session_id = NEW.session_id
       AND status IN ('held', 'attended')
       AND hold_id <> NEW.hold_id;
    IF taken + NEW.places > room THEN
        RAISE EXCEPTION
            'this session has % places, % are held and % more was asked for',
            room, taken, NEW.places;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER sch_capacity_holds_fit
    BEFORE INSERT ON plt01.sch_capacity_holds
    FOR EACH ROW EXECUTE FUNCTION plt01.sch_hold_fits_the_session();

-- **A hold is settled once.** Releasing a released place, or marking an attended one released,
-- would rewrite who was in the room -- and the release carries the only attribution there is.
CREATE OR REPLACE FUNCTION plt01.sch_hold_is_settled_once()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF OLD.status <> 'held' THEN
        RAISE EXCEPTION
            'this place is already % and what happened to it is recorded once', OLD.status;
    END IF;
    IF NEW.status NOT IN ('released', 'attended') THEN
        RAISE EXCEPTION 'a held place is released or attended; % is neither', NEW.status;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER sch_capacity_holds_one_way
    BEFORE UPDATE ON plt01.sch_capacity_holds
    FOR EACH ROW EXECUTE FUNCTION plt01.sch_hold_is_settled_once();

-- ---------------------------------------------------------------- changes and overrides
--
-- The Substitution entity, widened to the four acts paragraph 1839 names: "Instructor
-- substitution, cancellation, relocation and attendance handoff". **Insert-only**, because each
-- is a thing a member was told and a record that could be edited is a record nobody can rely
-- on in the dispute it exists for.
CREATE TABLE plt01.sch_session_changes (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    change_id uuid NOT NULL DEFAULT gen_random_uuid(),
    session_id uuid NOT NULL,
    change_kind text NOT NULL,
    -- For a substitution: who is covering. For a relocation: where it moves to. For a handoff:
    -- who takes the attendance.
    replacement_id uuid,
    -- What it replaced, so "who was teaching before" stays answerable without reading the
    -- session's history forwards.
    replaced_id uuid,
    -- Prose, because why a class changed is a sentence somebody writes. The declared
    -- cancellation reason is on the session, where the arithmetic reads it.
    reason text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    recorded_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, change_id),
    FOREIGN KEY (tenant_id, session_id)
        REFERENCES plt01.sch_sessions (tenant_id, session_id),
    CONSTRAINT sch_session_changes_kind CHECK (
        change_kind IN ('substitution', 'relocation', 'cancellation', 'handoff')),
    CONSTRAINT sch_session_changes_reason_not_blank CHECK (reason ~ '[^[:space:]]'),
    -- **A substitution, relocation or handoff names what replaces what; a cancellation
    -- replaces the session with nothing.** Each half is a separate constraint so each has an
    -- isolating case: a compound one would make both droppable in silence, which is the
    -- MOD-014 lesson in the rules file.
    CONSTRAINT sch_session_changes_replacement_matches_kind
        CHECK ((change_kind <> 'cancellation') = (replacement_id IS NOT NULL)),
    CONSTRAINT sch_session_changes_replaced_matches_kind
        CHECK (change_kind <> 'cancellation' OR replaced_id IS NULL)
);
CREATE INDEX sch_session_changes_by_session
    ON plt01.sch_session_changes (tenant_id, session_id, recorded_at);
ALTER TABLE plt01.sch_session_changes ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.sch_session_changes FORCE ROW LEVEL SECURITY;
CREATE POLICY sch_session_changes_tenant ON plt01.sch_session_changes
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **The evidence paragraph 1842 asks for.** "Resource conflicts cannot be overridden without
-- permission and reason": the permission is `scheduling.conflict.override` and this table is
-- the reason. Insert-only, and the conflict summary is stored as it was detected -- recomputing
-- it later would read a schedule that has since moved, so the row would no longer say what was
-- overridden.
--
-- **It records a claim about what was detected, not a verified one.** The conflicts are
-- computed from rows that change, so nothing here can prove the summary was accurate when it
-- was written; what it proves is that a named actor published over a conflict and said why,
-- which is what the Critical Control is for. Stated rather than implied, because MOD-012's
-- `validated` install state cost a review round for exactly this ambiguity.
CREATE TABLE plt01.sch_conflict_overrides (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    override_id uuid NOT NULL DEFAULT gen_random_uuid(),
    session_id uuid NOT NULL,
    -- What was detected, as the detector summarised it: every conflict, not the first, because
    -- an operator who fixed the room clash and then met the coach clash was sent round twice.
    conflict_summary text NOT NULL,
    conflict_count integer NOT NULL,
    reason text NOT NULL,
    overridden_at timestamptz NOT NULL DEFAULT now(),
    overridden_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, override_id),
    FOREIGN KEY (tenant_id, session_id)
        REFERENCES plt01.sch_sessions (tenant_id, session_id),
    CONSTRAINT sch_conflict_overrides_summary_not_blank
        CHECK (conflict_summary ~ '[^[:space:]]'),
    -- An override of nothing is not an override. The count is what makes the row readable
    -- without parsing the summary.
    CONSTRAINT sch_conflict_overrides_count_positive
        CHECK (conflict_count >= 1 AND conflict_count <= 1000),
    CONSTRAINT sch_conflict_overrides_reason_not_blank CHECK (reason ~ '[^[:space:]]')
);
CREATE INDEX sch_conflict_overrides_by_session
    ON plt01.sch_conflict_overrides (tenant_id, session_id);
ALTER TABLE plt01.sch_conflict_overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.sch_conflict_overrides FORCE ROW LEVEL SECURITY;
CREATE POLICY sch_conflict_overrides_tenant ON plt01.sch_conflict_overrides
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **A session's status moves one way, and a cancelled one does not come back.** Members have
-- been told; reinstating it would leave them with a cancellation notice for a class that
-- happened, and a replacement session is a new one -- which is also what makes "what did we
-- actually run" answerable. The cancellation's own attribution is never replaced, for
-- MOD-009's reason: a CHECK cannot see what a row used to be.
CREATE OR REPLACE FUNCTION plt01.sch_session_is_one_way()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    -- **A settled session does not change again, in any way.** Not only its status: a
    -- cancelled class whose room moved is a row that reads as though somebody ran it
    -- somewhere else.
    IF OLD.status <> 'scheduled' THEN
        RAISE EXCEPTION
            'this session is % and a % session does not change again',
            OLD.status, OLD.status;
    END IF;
    -- **There is no branch here refusing an unknown target status**, and there was one: it
    -- read `NEW.status NOT IN ('cancelled', 'completed')` and fired on every update that did
    -- not move the status at all -- so a relocation, which touches only `location_id`, was
    -- refused with "a scheduled session is cancelled or completed; scheduled is neither".
    -- Guarding it with `NEW.status <> OLD.status` makes it unreachable: the status CHECK
    -- admits only the three values, the branch above refuses every update from the other two,
    -- and `scheduled -> scheduled` is not a change. So it is deleted rather than tested
    -- harder, which is this repository's rule for a branch subsumed by a sibling. Found by the
    -- HTTP tests.
    --
    -- The instant, the rule it came from and the capacity it was published with do not move.
    -- Moving a session is a cancellation and a new one, because that is what a member is told.
    --
    -- **`overbook_places`, `local_date` and `policy_id` are in the list**, and were not: the
    -- fit trigger's ceiling is `capacity + overbook_places`, so guarding the capacity and
    -- leaving the overbooking was half a guard -- a reviewer doubled a one-place session's
    -- places with it. `local_date` is the date the member knows and `policy_id` is the
    -- snapshot every published figure came from.
    IF NEW.starts_at <> OLD.starts_at OR NEW.ends_at <> OLD.ends_at
       OR NEW.rule_id <> OLD.rule_id OR NEW.capacity <> OLD.capacity
       OR NEW.overbook_places <> OLD.overbook_places
       OR NEW.local_date <> OLD.local_date
       OR NEW.policy_id <> OLD.policy_id THEN
        RAISE EXCEPTION
            'a published session keeps its time, its rule, its places and the policy it was '
            'published under; cancel it and schedule another';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER sch_sessions_one_way
    BEFORE UPDATE ON plt01.sch_sessions
    FOR EACH ROW EXECUTE FUNCTION plt01.sch_session_is_one_way();

-- **A change is recorded against a session that can still change.** A substitution on a
-- cancelled class is a row that reads as though somebody covered a session nobody ran.
--
-- As with the hold trigger, the "session does not exist" branch is a readable message in front
-- of the foreign key rather than the control itself.
CREATE OR REPLACE FUNCTION plt01.sch_change_needs_a_live_session()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    session_status text;
BEGIN
    SELECT status INTO session_status
      FROM plt01.sch_sessions
     WHERE tenant_id = NEW.tenant_id AND session_id = NEW.session_id;
    IF session_status IS NULL THEN
        RAISE EXCEPTION 'a change names a session that does not exist';
    END IF;
    -- A cancellation is recorded in the same transaction as the status change, so the session
    -- may already read `cancelled` by the time this fires. Everything else needs a live one.
    IF session_status <> 'scheduled' AND NEW.change_kind <> 'cancellation' THEN
        RAISE EXCEPTION
            'this session is % and a % cannot be recorded against it',
            session_status, NEW.change_kind;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER sch_session_changes_live
    BEFORE INSERT ON plt01.sch_session_changes
    FOR EACH ROW EXECUTE FUNCTION plt01.sch_change_needs_a_live_session();

-- ---------------------------------------------------------------- privileges
--
-- **Seven tables carry no UPDATE grant at all**, and each is a record of something that
-- happened: the recurrence rule a session was generated from, the requirements and the capacity
-- policy that rule version was published with, the eligibility rules somebody was refused
-- under, the resources the session held, the changes recorded against it and the overrides
-- published over its conflicts. Paragraph 4149 is what makes the first three immutable --
-- "historical instances remain stable after template edits" is only true if the rule they cite
-- cannot be rewritten -- and the rest are the same argument MOD-018 makes for a posted
-- journal.
--
-- No runtime role holds DELETE, TRUNCATE or REFERENCES anywhere here, and nothing is granted to
-- PUBLIC. The column lists below are compared *as sets and per role* by the isolation suite,
-- because MOD-010's review showed that a hand-written list of the columns that matter is not a
-- pin -- and because two of this module's controls are an *absence*: there is no `held_count` on
-- a session and no `conflict_resolved` flag anywhere, and an absence is exactly what a later
-- migration adds back.

GRANT SELECT, INSERT ON plt01.sch_resources TO veyro_cp_app, veyro_cp_worker;
-- A resource's kind, its code and its scope do not move: re-pointing a `room` at `staff` would
-- invert every conflict decision ever made with it, and changing the quantity of a countable
-- one retroactively changes whether a past class was over capacity. The name and the
-- retirement are what change.
GRANT UPDATE (display_name, status, retired_at, retired_by, retire_correlation_id)
    ON plt01.sch_resources TO veyro_cp_app, veyro_cp_worker;

-- A rota is edited, so a window's times move. Its kind and its resource do not: changing a
-- `working` window into `time_off` would turn availability into an absence with no record that
-- it had ever been a shift.
GRANT SELECT, INSERT ON plt01.sch_availability_windows TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (starts_at, ends_at, reason)
    ON plt01.sch_availability_windows TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.sch_templates TO veyro_cp_app, veyro_cp_worker;
-- The name, the lifecycle and which rule is live. **Not the service or the location**: a
-- template re-pointed at another location would move every session it had generated, in a
-- table whose sessions carry their own location and would then disagree with it.
GRANT UPDATE (display_name, status, live_rule_id, published_at, published_by,
              publish_correlation_id, retired_at, retired_by, retire_reason,
              retire_correlation_id)
    ON plt01.sch_templates TO veyro_cp_app, veyro_cp_worker;

-- **No UPDATE at all.** A rule a session cites describes what that session *is*; editing one
-- is the history rewrite paragraph 4149 exists to prevent. A changed recurrence is a new
-- version, which is what `version` is for.
GRANT SELECT, INSERT ON plt01.sch_recurrence_rules TO veyro_cp_app, veyro_cp_worker;

-- A policy is a version too, and a session snapshots the capacity it was published with -- so
-- the policy itself needs no UPDATE either. Raising a class's capacity is a new version.
GRANT SELECT, INSERT ON plt01.sch_capacity_policies TO veyro_cp_app, veyro_cp_worker;
-- A requirement is added or removed rather than edited: changing a kind in place would make
-- every session generated before it disagree with the template it came from, and the sessions
-- carry their own expansion. Removal is a DELETE nobody holds, so a withdrawn requirement is
-- a new template -- which is the same trade `sch_recurrence_rules` makes and worth saying.
GRANT SELECT, INSERT ON plt01.sch_template_requirements TO veyro_cp_app, veyro_cp_worker;
GRANT SELECT, INSERT ON plt01.sch_restrictions TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.sch_sessions TO veyro_cp_app, veyro_cp_worker;
-- **The lifecycle only.** The instant, the rule, the policy, the location and the capacity are
-- what the session is, and the trigger above refuses a change to the first, second and last of
-- those even for a writer holding this grant. Moving a session is a cancellation and a new one,
-- because that is what a member is told.
-- `location_id` is in the list because a relocation has to move the session: paragraph 1839
-- names relocation as an act this module performs, and a relocation that left the column alone
-- showed the class at the site it had left and nothing at the site it had moved to. The
-- timezone is not, which is why `relocate_session` refuses a destination in another zone --
-- the local date and time on the row were computed in the old one.
GRANT UPDATE (status, cancelled_at, cancelled_by, cancellation_reason,
              cancel_correlation_id, completed_at, location_id)
    ON plt01.sch_sessions TO veyro_cp_app, veyro_cp_worker;

-- **The supersede marker and nothing else.** What a session held and the window it held it
-- for are what the conflict detector decided against, and a re-pointed hold would make a past
-- decision unreproducible -- so `resource_id`, `resource_kind`, `quantity`, `holds_from` and
-- `holds_until` carry no UPDATE at all. What moves is whether the hold still applies, which is
-- what a substitution and a relocation change.
--
-- It *is* write-once, by the trigger above: a supersession is recorded once, and re-assigning
-- a resource is a new assignment rather than a cleared marker. An earlier version cleared it on
-- re-assignment, which made this the one attribution column in the module a later write could
-- erase.
GRANT SELECT, INSERT ON plt01.sch_session_resources TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (superseded_at, superseded_by, supersede_correlation_id)
    ON plt01.sch_session_resources TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.sch_capacity_holds TO veyro_cp_app, veyro_cp_worker;
-- A place is taken once and settled once. **Not `places` and not `person_id`**: changing either
-- would rewrite who was in the room and how many places they took, after the fact.
GRANT UPDATE (status, released_at, released_by, release_reason, release_correlation_id)
    ON plt01.sch_capacity_holds TO veyro_cp_app, veyro_cp_worker;

-- **No UPDATE on either.** A change recorded against a session is what a member was told, and
-- an override is the evidence for paragraph 1842's Critical Control. Both are insert-only for
-- the same reason a posted journal is.
GRANT SELECT, INSERT ON plt01.sch_session_changes TO veyro_cp_app, veyro_cp_worker;
GRANT SELECT, INSERT ON plt01.sch_conflict_overrides TO veyro_cp_app, veyro_cp_worker;

-- The trigger functions are not SECURITY DEFINER and their `search_path` is pinned, so a
-- runtime role cannot reach them to redefine one -- `CREATE OR REPLACE` needs CREATE on the
-- schema, which no runtime role holds.
REVOKE ALL ON FUNCTION plt01.sch_resource_retirement_is_final() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.sch_template_is_one_way() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.sch_template_rule_belongs_to_it() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.sch_assignment_supersede_is_final() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.sch_assignment_fits_the_session() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.sch_hold_fits_the_session() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.sch_hold_is_settled_once() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.sch_session_is_one_way() FROM PUBLIC;
REVOKE ALL ON FUNCTION plt01.sch_change_needs_a_live_session() FROM PUBLIC;

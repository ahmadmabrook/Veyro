-- MOD-019 / ADM-SCH-06 — a room has a capacity, and a format can take a bike per attendee.
-- ADR-0018.
--
-- **Three different numbers, and this build had one of them.** `sch_resources.quantity` is
-- "how many of a thing there are" -- the migration that added it says so: *twenty bikes is one
-- row with a quantity of twenty, never twenty rows, because the question a booking asks is are
-- there enough*. `sch_capacity_policies.capacity` is how many places a class offers. What
-- ADM-SCH-06 draws is neither: **how many people a space holds**, with its own sentence saying
-- what it is for -- "capacity here is the ceiling every class inherits ... the constraint lives
-- in one place, not in each scheduler's memory".
--
-- And one relation, which the same card's third column draws and which nothing recorded:
-- **which space a piece of equipment is in**. `location_id` is a *club*, not a room, so twenty
-- bikes were at Khalda and in no particular studio -- which makes ADM-SCH-03's own named gap
-- unanswerable: "Studio 2 holds 20 bikes. Capacity cannot exceed the room" needs the bikes to
-- be *in* Studio 2.
--
-- **A ceiling, not a default** (D2). A template keeps its own capacity, which is what a session
-- snapshots; what the room adds is a refusal. Inheriting the room's figure where a template
-- states none would make the class's own number optional and leave two columns that can
-- disagree about how many places a session has -- this build's most-repeated finding, created
-- on purpose. The canvas's word is *ceiling*.

-- ---------------------------------------------------------------- a space's capacity

-- **Nullable, and only a space may carry one** (D1). A coach, a service and a composite hold
-- nobody, and a zero would read as "this room holds no people" rather than "this is not a
-- room". The three kinds admitted are the three of OPS-01-R01's seven that are places.
ALTER TABLE plt01.sch_resources
    ADD COLUMN capacity integer;

COMMENT ON COLUMN plt01.sch_resources.capacity IS
    'How many people this space holds. NULL for anything that is not a room, zone or court. '
    'A ceiling on every class in it (ADR-0018 D2), never a default for one.';

ALTER TABLE plt01.sch_resources
    ADD CONSTRAINT sch_resources_capacity_is_a_space
        CHECK (capacity IS NULL
               OR resource_kind IN ('room', 'zone', 'court')),
    -- The same bound `sch_capacity_policies.capacity` carries, because the two are compared:
    -- a ceiling above the largest expressible class is a ceiling that cannot bind.
    ADD CONSTRAINT sch_resources_capacity_sane
        CHECK (capacity IS NULL OR (capacity >= 1 AND capacity <= 10000));

-- ---------------------------------------------------------------- equipment inside a space

-- **A self-reference, because a room containing bikes is one table's own shape** (D3). The
-- composite foreign key carries the tenant, as every parent reference in this schema does.
ALTER TABLE plt01.sch_resources
    ADD COLUMN parent_resource_id uuid;

COMMENT ON COLUMN plt01.sch_resources.parent_resource_id IS
    'The space this equipment is in. NULL for anything that is not equipment, and for '
    'equipment nobody has placed. Only a room, zone or court may be one, and it must be at '
    'the same location (ADR-0018 D3) -- a ceiling computed across clubs is the defect this '
    'exists to prevent.';

ALTER TABLE plt01.sch_resources
    ADD CONSTRAINT sch_resources_parent_is_equipment
        CHECK (parent_resource_id IS NULL OR resource_kind = 'equipment'),
    -- **There is no `parent <> resource_id` constraint, and the case is why.** One was
    -- written and had no isolating path: a BEFORE trigger runs ahead of every CHECK on the
    -- table, so on an insert the trigger's own lookup answers ("that space does not exist",
    -- since the row is not there yet) and on an update it answers again -- equipment whose
    -- parent is itself is equipment inside equipment, which the kind branch refuses by name.
    -- A room naming itself is refused by `parent_is_equipment` above. Deleted rather than
    -- tested harder, which is this build's judgement for a constraint subsumed by a sibling;
    -- there is no path left for self-containment to take.
    ADD CONSTRAINT sch_resources_parent_in_tenant
        FOREIGN KEY (tenant_id, parent_resource_id)
        REFERENCES plt01.sch_resources (tenant_id, resource_id);

CREATE INDEX sch_resources_by_parent
    ON plt01.sch_resources (tenant_id, parent_resource_id)
    WHERE parent_resource_id IS NOT NULL;
COMMENT ON INDEX plt01.sch_resources_by_parent IS
    'ADM-SCH-06 reads the equipment of every room on one page, and the ceiling read asks the '
    'same question per space.';

-- **What the parent is, and where, needs a trigger**: a CHECK cannot see another row. Both
-- halves are load-bearing and each answers a different wrong answer -- a parent that is a
-- coach makes "the room's capacity" unreadable, and a parent at another club makes the
-- ceiling a number about equipment nobody at this site can use.
CREATE OR REPLACE FUNCTION plt01.sch_resource_parent_is_a_space()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    parent_kind text;
    parent_location uuid;
BEGIN
    IF NEW.parent_resource_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT resource_kind, location_id INTO parent_kind, parent_location
      FROM plt01.sch_resources
     WHERE tenant_id = NEW.tenant_id AND resource_id = NEW.parent_resource_id;
    IF parent_kind IS NULL THEN
        -- The composite foreign key is the control; this fires first only to say which
        -- resource is missing, and the probe for it has to know that.
        RAISE EXCEPTION 'that space does not exist';
    END IF;
    IF parent_kind NOT IN ('room', 'zone', 'court') THEN
        RAISE EXCEPTION
            'equipment goes in a room, a zone or a court, and % is a %',
            NEW.parent_resource_id, parent_kind;
    END IF;
    IF parent_location IS DISTINCT FROM NEW.location_id THEN
        RAISE EXCEPTION
            'this equipment and the space it is in are at different locations';
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION plt01.sch_resource_parent_is_a_space() FROM PUBLIC;

CREATE TRIGGER sch_resources_parent_is_a_space
    BEFORE INSERT OR UPDATE OF parent_resource_id, location_id, resource_kind
    ON plt01.sch_resources
    FOR EACH ROW EXECUTE FUNCTION plt01.sch_resource_parent_is_a_space();

-- --------------------------------------------- one REVOKE `0017` did not issue
--
-- **Not this slice's rule, and found by this slice's sweep.** `0035` adds a trigger function
-- and a mutation against its pinned `search_path` came back uncaught -- because MOD-019 had
-- no `proconfig`/`prosecdef`/`tgenabled` sweep at all: MOD-020's CHECK 96, MOD-021's and
-- MOD-022's each read all three over their own prefix and `sch_%` was never added, so ten
-- trigger functions' pinned search path and closing `REVOKE` were verified by nothing and
-- `md5(prosrc)` cannot see any of the three.
--
-- Adding the sweep found that `0017`'s own function never got the `REVOKE` every one of its
-- ten siblings has. Exploitability is low -- every reference in that body is schema-qualified
-- and trigger invocation does not check EXECUTE -- but rule 5 of the isolation rule forbids a
-- PUBLIC privilege on a function outright, and an asserted control with no evidence is what
-- these sweeps exist to prevent. **It is corrected here rather than in `0017`**, because a
-- committed migration does not change: the database somebody has already applied is the one
-- this has to fix.
REVOKE ALL ON FUNCTION plt01.sch_availability_window_withdrawal_is_final() FROM PUBLIC;

-- ---------------------------------------------------------------- a bike per attendee

-- **A flag, not a second quantity** (D4). The requirement already carries `quantity`; what
-- this says is whether that figure is per *session* -- one studio, one coach -- or per
-- *attendee*, which is the fact ADM-SCH-03's ceiling needs and which `web/src/lib/new-class.ts`
-- names as the one thing nothing records. A second integer would be two numbers that can
-- disagree about one requirement.
ALTER TABLE plt01.sch_template_requirements
    ADD COLUMN per_attendee boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN plt01.sch_template_requirements.per_attendee IS
    'Whether `quantity` is per attendee rather than per session: one bike each. Refused for a '
    'requirement naming a particular resource, which is for one of it (ADR-0018 D4).';

-- A requirement naming *that* resource already has `quantity = 1` by its sibling constraint,
-- so per-attendee against it is a figure with no reading.
ALTER TABLE plt01.sch_template_requirements
    ADD CONSTRAINT sch_template_requirements_per_attendee_is_anonymous
        CHECK (NOT per_attendee OR resource_id IS NULL);

-- ---------------------------------------------------------------- the grants
--
-- **There is no statement here, and that is the decision rather than an omission.** Both
-- tables carry a table-level `GRANT SELECT, INSERT`, which covers a column added later; the
-- only UPDATE on `sch_resources` is column-scoped -- `display_name, status, retired_at,
-- retired_by, retire_correlation_id` -- and a column-scoped grant does *not* extend to a new
-- column. So all three columns here are insert-only, with no statement required.
--
-- **Which is `quantity`'s own arrangement, and the same gap.** Twenty bikes becoming eighteen
-- has no route either: a resource states what it is when it is registered. Adding an UPDATE
-- grant for a capacity would be a grant no service writes until somebody builds the form the
-- canvas does not draw -- MOD-016's `cat_prices.effective_to` and `0017`'s rota window, both
-- of which were granted and unwritten, which is an unattributed edit path to the values the
-- table exists to state. The refit that re-rates a room is named in ADR-0018's own "what this
-- does not do" rather than half-granted here.
--
-- **And re-registering is not the remedy it is for a rota window**, which is worth saying
-- because the two look alike: `sch_template_requirements.resource_id` and
-- `sch_session_resources` both reference this row, so a replacement resource is a new
-- `resource_code` that every template naming the old one would have to be re-pointed at. That
-- is why the gap is a route rather than a workaround.

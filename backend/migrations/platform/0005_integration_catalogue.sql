-- MOD-012 ECO-02 platform track: the integration definition catalogue.
--
-- Platform state, not tenant state, so it sits in `plt01_platform` with no row-level security
-- and no grant to either runtime role -- the same boundary `0003_saas_plan_catalogue.sql` draws
-- and for the same reason: a tenant-facing connection must not reach it at all. The tenant plane
-- gets what it needs the way billing does, by reading through `veyro_cp_platform` and
-- **snapshotting** the version into the install.
--
-- **A published definition version is immutable, and the privilege layer is what makes that
-- true**, exactly as for a plan version. `int_definition_versions` carries no UPDATE grant at
-- all and `int_definitions` carries a column-level UPDATE on its lifecycle columns only. The
-- capabilities, the scopes and the configuration schema therefore cannot be edited after an
-- install was made against them. Changing what an adapter asks for means publishing a new
-- version; installs already made stay on the version they were made on.
--
-- That matters for a reason the plan catalogue does not have: the scopes on a version are the
-- permissions a third party was granted. If today's definition could be edited, nobody could
-- say afterwards what an install had actually authorized -- which is paragraph 3032's control
-- ("third parties receive only required data and permissions") resting on nobody having run
-- the wrong UPDATE.
--
-- **Definitions are rows here and not code**, which is the opposite call from MOD-008's
-- permissions, MOD-010's event types and MOD-011's metrics. Those are facts about what this
-- software does, so two tenants disagreeing about them would be unresolvable. An integration
-- definition is not: ECO-02's own model has partners publishing their own, so the set is open
-- by design and the authority is whoever published the version. The reasoning is in
-- `app/integrations/contract.py`.

CREATE TABLE plt01_platform.int_definitions (
    definition_key text NOT NULL,
    version bigint NOT NULL,
    provider text NOT NULL,
    display_name text NOT NULL,
    status text NOT NULL DEFAULT 'draft',
    -- How much a tenant loses when this provider is unavailable. `critical` carries the
    -- paragraph 3033 obligations, which `app/integrations/lifecycle.py` enforces at activation
    -- rather than here: the fallback and the exit plan are written per install, because what a
    -- tenant falls back *to* depends on what else that tenant has.
    criticality text NOT NULL,
    -- Who answers when it breaks (paragraph 3024). Free text rather than a foreign key: the
    -- owner is a team or a partner, and there is no table of either in this build.
    support_owner text NOT NULL,
    description text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    retired_at timestamptz,
    PRIMARY KEY (definition_key, version),
    CONSTRAINT int_definitions_key_shape
        CHECK (definition_key ~ '^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*)*$'),
    CONSTRAINT int_definitions_provider_shape CHECK (provider ~ '[^[:space:]]'),
    CONSTRAINT int_definitions_version_positive CHECK (version > 0),
    CONSTRAINT int_definitions_status CHECK (status IN ('draft', 'published', 'retired')),
    CONSTRAINT int_definitions_criticality
        CHECK (criticality IN ('convenience', 'important', 'critical')),
    CONSTRAINT int_definitions_support_owner_not_blank
        CHECK (support_owner ~ '[^[:space:]]'),
    CONSTRAINT int_definitions_description_not_blank
        CHECK (description ~ '[^[:space:]]'),
    CONSTRAINT int_definitions_published_at CHECK
        (status = 'draft' OR published_at IS NOT NULL),
    CONSTRAINT int_definitions_retired_at CHECK
        ((status = 'retired') = (retired_at IS NOT NULL))
);

-- One row per capability, scope and configuration field of a version. Three narrow tables would
-- be three places to look; one with a `kind` is one shape with one grant, and the CHECK below
-- is what keeps each kind's columns honest.
CREATE TABLE plt01_platform.int_definition_versions (
    entry_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    definition_key text NOT NULL,
    version bigint NOT NULL,
    kind text NOT NULL,
    name text NOT NULL,
    -- `scope`: whether this scope is one the integration cannot work without.
    -- `config`: whether a value is required before the install may be activated.
    required boolean NOT NULL DEFAULT false,
    -- `config` only: the declared type, and the closed set for an enum.
    field_type text,
    enum_values text[],
    description text NOT NULL DEFAULT '',
    FOREIGN KEY (definition_key, version)
        REFERENCES plt01_platform.int_definitions (definition_key, version),
    UNIQUE (definition_key, version, kind, name),
    CONSTRAINT int_definition_versions_kind
        CHECK (kind IN ('capability', 'scope', 'config', 'region')),
    CONSTRAINT int_definition_versions_name_not_blank CHECK (name ~ '[^[:space:]]'),
    -- A configuration field declares a type; nothing else does. **There is no `secret` type**,
    -- and its absence is the control: there is no vault in this repository, so a definition
    -- inviting a tenant to paste an API key into a config value would be inviting this build to
    -- store one in a table every list route reads. Credentials go through
    -- `plt01.int_credential_refs`, which holds a reference and never a value.
    CONSTRAINT int_definition_versions_field_type CHECK (
        (kind = 'config') = (field_type IS NOT NULL)
        AND (field_type IS NULL
             OR field_type IN ('string', 'integer', 'boolean', 'reference', 'enum'))),
    CONSTRAINT int_definition_versions_enum_values CHECK (
        (field_type = 'enum') = (enum_values IS NOT NULL)
        AND (enum_values IS NULL OR array_length(enum_values, 1) > 0)),
    -- Only a scope or a config field can be required. A required capability is a capability,
    -- and a required region is a contradiction.
    CONSTRAINT int_definition_versions_required_kinds
        CHECK (NOT required OR kind IN ('scope', 'config'))
);
CREATE INDEX int_definition_versions_lookup
    ON plt01_platform.int_definition_versions (definition_key, version, kind);

-- **Immutability needs a trigger, because the threat is an INSERT and a grant cannot see the
-- parent.** `GRANT SELECT, INSERT` on the entries table plus `UNIQUE (definition_key, version,
-- kind, name)` stops re-declaring a name that already exists and stops nothing else: a
-- published version's scope set was additive-mutable, and a *required* scope could be added to
-- it. Installs already made keep their snapshot, so the blast radius is new installs against
-- "version 1" authorizing a wider scope set than the one that was published and reviewed --
-- which is exactly the control paragraph 3032 names. Found by review; the header above rested
-- the whole claim on "nobody having run the wrong UPDATE" and the wrong INSERT was unguarded.
CREATE FUNCTION plt01_platform.int_definition_versions_are_draft_only() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog, plt01_platform
AS $$
DECLARE
    parent_status text;
BEGIN
    SELECT status INTO parent_status FROM plt01_platform.int_definitions
    WHERE definition_key = coalesce(NEW.definition_key, OLD.definition_key)
      AND version = coalesce(NEW.version, OLD.version);
    -- A missing parent is the foreign key's refusal to make, not this trigger's. Raising here
    -- would mask it, and a case that proves the FK would then be passing because a different
    -- control fired -- the vacuity this suite has already been bitten by twice.
    IF parent_status IS NOT NULL AND parent_status <> 'draft' THEN
        RAISE EXCEPTION 'a published definition version cannot be changed'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;
REVOKE EXECUTE ON FUNCTION plt01_platform.int_definition_versions_are_draft_only()
    FROM PUBLIC;
CREATE TRIGGER int_definition_versions_draft_only
    BEFORE INSERT OR UPDATE OR DELETE ON plt01_platform.int_definition_versions
    FOR EACH ROW EXECUTE FUNCTION plt01_platform.int_definition_versions_are_draft_only();

-- And the lifecycle dates themselves. A CHECK sees only the new row, so `published_at` could be
-- moved and a retired definition un-retired -- MOD-009's rule that a CHECK cannot see what a row
-- used to be, applied to the column that answers "when did installs against this version become
-- possible".
CREATE FUNCTION plt01_platform.int_definitions_dates_are_final() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog, plt01_platform
AS $$
BEGIN
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
REVOKE EXECUTE ON FUNCTION plt01_platform.int_definitions_dates_are_final() FROM PUBLIC;
CREATE TRIGGER int_definitions_dates_final
    BEFORE UPDATE ON plt01_platform.int_definitions
    FOR EACH ROW EXECUTE FUNCTION plt01_platform.int_definitions_dates_are_final();

-- The platform role reads and writes the catalogue; no runtime role is granted anything at all,
-- and `backend/tests/sql/isolation.sql` proves the absence rather than trusting this comment.
GRANT SELECT, INSERT ON plt01_platform.int_definitions TO veyro_cp_platform;
GRANT SELECT, INSERT ON plt01_platform.int_definition_versions TO veyro_cp_platform;
-- Lifecycle only. The capabilities, scopes and configuration of a published version are what an
-- install authorized against, and an UPDATE on them would rewrite what a third party was given.
GRANT UPDATE (status, published_at, retired_at) ON plt01_platform.int_definitions
    TO veyro_cp_platform;

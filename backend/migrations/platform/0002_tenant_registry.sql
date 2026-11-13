-- MOD-004 PLT-01-R01/R07 platform track: the tenant registry, its append-only lifecycle
-- history, and command idempotency.
--
-- These are platform-plane objects, not tenant-scoped rows, so they carry no `tenant_id`
-- policy: the registry is the thing that *defines* tenants. Reachability is controlled by
-- grant instead -- only `veyro_cp_platform` touches them. `veyro_cp_app` deliberately holds
-- nothing here, so a tenant-scoped request cannot enumerate tenants even in principle.
--
-- Lifecycle states are the four TSD paragraph 1222 verbs that paragraph 1237 also supplies a
-- command for: provisioned, active, suspended, archived. There is no `deleted` state. Paragraph
-- 1237 carries no DeleteTenant command and paragraph 1241 publishes no tenant.deleted event, and
-- PLT-01-R07 bars hard deletion before legal, billing and retention gates pass -- gates that
-- live in modules that do not exist yet. A deletion request is refused at the application edge
-- rather than modelled as a state here.

CREATE TABLE plt01_platform.tenants (
    tenant_id uuid PRIMARY KEY,
    external_key text NOT NULL UNIQUE,
    display_name text NOT NULL,
    status text NOT NULL,
    region text NOT NULL,
    version bigint NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT tenants_status_check
        CHECK (status IN ('provisioned', 'active', 'suspended', 'archived')),
    CONSTRAINT tenants_version_positive CHECK (version > 0)
);

-- Append-only by name (`_history`) and by grant: no UPDATE, DELETE or TRUNCATE is granted to
-- anyone. The lifecycle record is evidence, so a correction is a new row, never an edit.
CREATE TABLE plt01_platform.tenant_lifecycle_history (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    from_status text,
    to_status text NOT NULL,
    command text NOT NULL,
    actor_id uuid NOT NULL,
    correlation_id uuid NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX tenant_lifecycle_history_tenant_time
    ON plt01_platform.tenant_lifecycle_history (tenant_id, occurred_at);

-- Idempotency: one row per accepted command key. A replay finds the row and returns the prior
-- result instead of re-running the command. TSD paragraph 1237 attaches idempotency to every
-- one of the seven commands.
CREATE TABLE plt01_platform.command_idempotency (
    idempotency_key uuid PRIMARY KEY,
    command text NOT NULL,
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    result_version bigint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT, UPDATE ON plt01_platform.tenants TO veyro_cp_platform;
GRANT SELECT, INSERT ON plt01_platform.tenant_lifecycle_history TO veyro_cp_platform;
GRANT SELECT, INSERT ON plt01_platform.command_idempotency TO veyro_cp_platform;

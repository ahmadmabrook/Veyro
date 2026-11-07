-- Legitimate shape for a platform function: SECURITY INVOKER needs no allowlist entry, and a
-- platform table needs no RLS (D6: the boundary is schema, ownership and the function allowlist).
CREATE TABLE plt01_platform.tenant_placement (
    tenant_id uuid NOT NULL PRIMARY KEY,
    region text NOT NULL DEFAULT 'UNASSIGNED'
);
CREATE FUNCTION plt01_api.resolve_placement(p_tenant_id uuid)
RETURNS text
LANGUAGE plpgsql
SET search_path = pg_catalog, plt01_platform, pg_temp
AS $fn$
BEGIN
    RETURN 'UNASSIGNED';
END;
$fn$;

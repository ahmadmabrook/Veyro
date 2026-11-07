CREATE FUNCTION plt01_api.remove_tenant(p_tenant_id uuid) RETURNS void
LANGUAGE sql AS $fn$ SELECT 1 $fn$;

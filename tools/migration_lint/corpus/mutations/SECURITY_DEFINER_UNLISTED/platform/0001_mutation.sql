-- Mutation: a SECURITY DEFINER function with a correctly pinned search_path that is not on the
-- reviewed D5 allowlist.
CREATE FUNCTION plt01_api.provision_tenant(p_external_key text)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, plt01_platform, pg_temp
AS $fn$
BEGIN
    RETURN gen_random_uuid();
END;
$fn$;

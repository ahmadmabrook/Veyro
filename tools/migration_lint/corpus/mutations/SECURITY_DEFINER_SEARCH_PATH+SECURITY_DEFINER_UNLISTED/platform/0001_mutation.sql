-- Mutation: a SECURITY DEFINER function that pins no search_path, so it is hijackable; it is also
-- unlisted, which is declared.
CREATE FUNCTION plt01_api.resolve_placement(p_tenant_id uuid)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
AS $fn$
BEGIN
    RETURN 'UNASSIGNED';
END;
$fn$;

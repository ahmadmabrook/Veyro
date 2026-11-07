-- Mutation: an archive function. D6 admits no archive, delete, relocate-source-deletion or
-- cross-tenant list function in S1.
CREATE FUNCTION plt01_api.archive_tenant(p_tenant_id uuid)
RETURNS void
LANGUAGE sql
AS $fn$ SELECT 1 $fn$;

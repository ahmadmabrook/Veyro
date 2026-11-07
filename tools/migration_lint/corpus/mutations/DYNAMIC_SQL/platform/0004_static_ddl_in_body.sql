-- Not dynamic at all, but equally invisible: a body is blanked out of the text the statement
-- rules read, so DDL written inside one is linted by nothing.
CREATE FUNCTION plt01_api.weaken() RETURNS void LANGUAGE plpgsql
AS $fn$
BEGIN
    ALTER TABLE plt01.brand_appearance DISABLE ROW LEVEL SECURITY;
END
$fn$;

-- Legitimate: a single-quoted function body that contains no DDL and no EXECUTE. The DYNAMIC_SQL
-- rule refuses a body carrying either, so this guards the inverse.
CREATE FUNCTION plt01_api.pure_one() RETURNS integer LANGUAGE sql AS 'SELECT 1';

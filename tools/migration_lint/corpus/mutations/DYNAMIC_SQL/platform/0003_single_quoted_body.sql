-- A function body may be single-quoted as well as dollar-quoted. Only the dollar form was
-- collected, so this spelling was neither linted nor refused.
CREATE FUNCTION plt01_api.touch() RETURNS void LANGUAGE plpgsql
AS 'BEGIN EXECUTE ''ALTER TABLE plt01.brand_appearance DISABLE ROW LEVEL SECURITY''; END';

-- D15.10 item 1 bans the command name as well as the entity name.
CREATE FUNCTION plt01_api.create_brand_theme() RETURNS void LANGUAGE sql AS $fn$ SELECT 1 $fn$;

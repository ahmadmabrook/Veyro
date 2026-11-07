-- Same violation inside a function body.
CREATE FUNCTION plt01_api.provision_tenant(p_key text)
RETURNS void
LANGUAGE plpgsql
AS $fn$
BEGIN
    EXECUTE 'GRANT SELECT ON plt01.brand_appearance TO PUBLIC';
END;
$fn$;

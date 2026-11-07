-- Same violation reached through a comma join rather than FROM/JOIN of the tenant table.
CREATE VIEW plt01.brand_appearance_v WITH (security_invoker = true) AS
    SELECT b.tenant_id FROM pg_catalog.pg_class c, plt01.brand_appearance b;

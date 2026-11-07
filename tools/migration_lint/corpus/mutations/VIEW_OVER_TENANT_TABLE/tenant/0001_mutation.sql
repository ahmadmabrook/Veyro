-- Mutation: a view over a tenant table, which is banned by default even with security_invoker.
CREATE VIEW plt01.brand_appearance_v WITH (security_invoker = true) AS
    SELECT tenant_id, brand_id FROM plt01.brand_appearance;

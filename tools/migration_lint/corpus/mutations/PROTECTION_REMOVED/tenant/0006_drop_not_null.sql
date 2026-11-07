-- The same loss by a different route: a nullable tenant_id falls outside every policy comparison,
-- which is why NOT NULL is required at creation.
ALTER TABLE plt01.brand_appearance ALTER COLUMN tenant_id DROP NOT NULL;

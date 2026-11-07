-- Mutation: the tenant track alters a platform table. Only the platform track may.
ALTER TABLE plt01_platform.tenants ADD COLUMN plan_code text;

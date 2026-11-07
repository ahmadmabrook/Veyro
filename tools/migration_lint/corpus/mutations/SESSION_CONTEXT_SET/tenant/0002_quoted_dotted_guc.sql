-- Same violation with the parameter name quoted; PostgreSQL's var_name admits a quoted ColId.
SET "app"."tenant_id" = '00000000-0000-4000-8000-000000000001';

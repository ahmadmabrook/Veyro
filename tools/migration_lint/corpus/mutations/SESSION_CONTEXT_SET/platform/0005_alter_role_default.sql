-- A role default, which RESET ALL re-applies on the next pooled checkout (D5 bullet 5).
ALTER ROLE veyro_cp_app SET "app"."tenant_id" = '00000000-0000-4000-8000-000000000001';

-- set_config's third argument must be the literal true; a cast is the same session-level set.
SELECT set_config('app.tenant_id', '00000000-0000-4000-8000-000000000001', false::boolean);

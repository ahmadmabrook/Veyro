-- D1.1 is [SRC]: runtime roles do not own tenant tables. An owner can disable RLS on its own
-- table, so this hands the runtime role the power to remove its own isolation.
ALTER TABLE plt01.brand_appearance OWNER TO veyro_cp_app;

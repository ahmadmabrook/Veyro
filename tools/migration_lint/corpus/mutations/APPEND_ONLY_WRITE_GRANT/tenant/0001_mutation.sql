-- Mutation: UPDATE on an append-only history table, which lets a runtime role rewrite history. DELETE would
-- also trip the D6.2 runtime-privilege rule, so UPDATE keeps this mutation on one rule.
GRANT SELECT, INSERT, UPDATE ON plt01.brand_appearance_history TO veyro_cp_app;

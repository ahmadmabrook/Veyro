-- Mutation: a default-privilege GRANT to PUBLIC. A REVOKE-only entry is the safe pattern.
ALTER DEFAULT PRIVILEGES IN SCHEMA plt01 GRANT EXECUTE ON FUNCTIONS TO PUBLIC;

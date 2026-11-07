-- Mutation: a later migration takes RLS off a table an earlier migration protected.
ALTER TABLE plt01.brand_appearance DISABLE ROW LEVEL SECURITY;

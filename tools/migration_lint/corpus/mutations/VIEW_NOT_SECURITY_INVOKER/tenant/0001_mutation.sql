-- Mutation: a view without security_invoker runs as its owner and bypasses the caller's policy.
CREATE VIEW plt01.active_brand_count AS SELECT 1 AS n;

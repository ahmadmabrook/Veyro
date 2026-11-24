-- MOD-014 -- a name a front desk can type half of. ADR-0012.
--
-- FD-02 is "search by name, phone or partial", and its canvas types `hala` to get two people
-- side by side. The phone half exists -- `GET /people/contact-match`, deliberately exact,
-- because "a mistyped digit finding somebody else is worse than finding nobody" -- and the
-- name half had nothing behind it.
--
-- **This is not paragraph 4218's search index**, which is ENG-01's and which MOD-014's own gap
-- list sends there. ADR-0012 separates the two: a lookup is one entity, inside one tenant under
-- forced RLS (so the "mandatory query pre-filter" that paragraph asks for is the database's
-- rather than something a module remembers to add), with no index to go stale because it reads
-- the table of record, and a bounded page every row of which goes through this module's gate.
-- ADM-SRCH-01's pg_trgm command bar across entities is still MOD-059's.
--
-- **`0009`'s name index cannot do it, and that is a measurement rather than a guess.** It is
-- `(tenant_id, lower(legal_name))` with the default operator class, and this database is
-- `en_US.utf8` rather than C -- so a b-tree on a collated text expression cannot answer
-- `LIKE 'hala%'` at all. Against 60,002 rows:
--
--     -- (tenant_id, lower(legal_name))
--     Seq Scan on people
--       Filter: ((tenant_id = ...) AND (lower(legal_name) ~~ 'hala%'))
--
--     -- (tenant_id, lower(legal_name) text_pattern_ops)
--     Index Scan using probe_by_name_prefix on people
--       Index Cond: ((tenant_id = ...) AND (lower(legal_name) ~>=~ 'hala')
--                    AND (lower(legal_name) ~<~ 'halb'))
--
-- **Both indexes earn their place, and the cost is stated rather than discovered.** Two
-- b-trees over one expression double the write amplification on a person's name, which moves
-- on a merge and on an ordinary correction. Replacing the existing one is not available:
-- `text_pattern_ops` compares byte by byte, so an equality lookup through it is correct only
-- for the exact bytes, and `find_duplicates` folds the name before comparing -- which is what
-- `0009`'s index is for and what makes the duplicate detector use an index rather than scan a
-- tenant.
CREATE INDEX ppl_persons_by_name_prefix
    ON plt01.ppl_persons (tenant_id, lower(legal_name) text_pattern_ops);

COMMENT ON INDEX plt01.ppl_persons_by_name_prefix IS
    'FD-02''s lookup: a name beginning with what somebody typed. `text_pattern_ops` because '
    'this database is not in the C locale, so the default operator class on the same '
    'expression serves equality only -- which is what ppl_persons_by_name is for.';

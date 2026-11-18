#!/usr/bin/env python3
"""Generate MOD-022's isolation checks, with every pinned set read from a live database.

**The pins are generated and the cases are written.** A column list, a NOT NULL set, a grant
set and the text of every CHECK, index and trigger are facts about the schema; typing them by
hand is how a pin ends up agreeing with what somebody remembered rather than with what is
there. The behavioural cases below them are hand-written, because a generated case proves
whatever the generator assumed.

    docker exec -i veyro-verify psql -U postgres -d veyro   # the database to read
    ./generate_access_checks.py > /tmp/access_checks.sql

Run it against a database built from the migrations and nothing else: it reads the catalogue,
so a database somebody has edited pins the edit.
"""

from __future__ import annotations

import subprocess
import sys

CONTAINER = sys.argv[1] if len(sys.argv) > 1 else "veyro-verify"
TENANT = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


def q(sql: str) -> list[list[str]]:
    out = subprocess.run(
        ["docker", "exec", "-e", "PGPASSWORD=veyro_dev", CONTAINER,
         "psql", "-U", "postgres", "-d", "veyro", "-tAF", "\x1f", "-c", sql],
        capture_output=True, text=True, check=True).stdout
    return [line.split("\x1f") for line in out.splitlines() if line.strip()]


def lit(value: str) -> str:
    """A PostgreSQL string literal, doubling embedded quotes."""
    return "'" + value.replace("'", "''") + "'"


def values(rows: list[str], indent: str = "        ") -> str:
    if not rows:
        return indent + "(NULL)"
    return ",\n".join(f"{indent}({lit(r)})" for r in rows)


tables = [r[0] for r in q(
    "select c.relname from pg_class c where c.relnamespace='plt01'::regnamespace"
    " and c.relkind in ('r','p') and c.relname like 'acc\\_%' order by 1")]

columns = [f"{r[0]}.{r[1]}" for r in q(
    "select table_name, column_name from information_schema.columns"
    " where table_schema='plt01' and table_name like 'acc\\_%'"
    " order by table_name, column_name")]

not_null = [f"{r[0]}.{r[1]}" for r in q(
    "select c.relname, a.attname from pg_attribute a join pg_class c on c.oid=a.attrelid"
    " where c.relnamespace='plt01'::regnamespace and c.relname like 'acc\\_%'"
    " and a.attnum>0 and not a.attisdropped and a.attnotnull order by 1,2")]

grants = [f"{r[0]} {r[1]}.{r[2]}" for r in q(
    "select g.rolname, c.relname, a.attname from pg_class c"
    " join pg_attribute a on a.attrelid=c.oid and a.attnum>0 and not a.attisdropped"
    " cross join (values ('veyro_cp_app'),('veyro_cp_worker')) as g(rolname)"
    " where c.relnamespace='plt01'::regnamespace and c.relkind in ('r','p')"
    " and c.relname like 'acc\\_%'"
    " and has_column_privilege(g.rolname, c.oid, a.attname, 'UPDATE') order by 1,2,3")]

checks = [f"{r[0]} {r[1]}" for r in q(
    "select con.conname, pg_get_constraintdef(con.oid) from pg_constraint con"
    " join pg_class c on c.oid=con.conrelid"
    " where c.relnamespace='plt01'::regnamespace and c.relname like 'acc\\_%'"
    " and con.contype='c' order by 1")]

indexes = [f"{r[0]} {r[1]}" for r in q(
    "select i.relname, pg_get_indexdef(i.oid) from pg_index x"
    " join pg_class i on i.oid=x.indexrelid join pg_class c on c.oid=x.indrelid"
    " where c.relnamespace='plt01'::regnamespace and c.relname like 'acc\\_%' order by 1")]

triggers = [f"{r[0]} on {r[1]}" for r in q(
    "select t.tgname, c.relname from pg_trigger t join pg_class c on c.oid=t.tgrelid"
    " where c.relnamespace='plt01'::regnamespace and c.relname like 'acc\\_%'"
    " and not t.tgisinternal order by 1")]

bodies = [f"{r[0]} {r[1]}" for r in q(
    "select p.proname, md5(p.prosrc) from pg_proc p"
    " where p.pronamespace='plt01'::regnamespace and p.proname like 'acc\\_%' order by 1")]

fkeys = [f"{r[0]} {r[1]}" for r in q(
    "select con.conname, pg_get_constraintdef(con.oid) from pg_constraint con"
    " join pg_class c on c.oid=con.conrelid"
    " where c.relnamespace='plt01'::regnamespace and c.relname like 'acc\\_%'"
    " and con.contype='f' order by 1")]

print(f"""
-- ------------------------------------------- 106. MOD-022's shape, pinned from the catalogue
-- **The structural floor is check 61b's and is not repeated here.** That sweep is prefix-free
-- over the whole of `plt01`, so every `acc_` table already has ENABLE and FORCE row level
-- security, exactly one permissive policy whose predicate is the approved text, a
-- tenant-leading primary key, a tenant-registry foreign key, no DELETE for `veyro_cp_app`, no
-- TRUNCATE or REFERENCES for either runtime role, and no PUBLIC grant at table or column
-- level. A per-module copy of all that would be a second list to edit.
--
-- What is left is what 61b cannot know: **which columns exist, which are NOT NULL, and which
-- carry an UPDATE grant for which role.** Each is compared as a set in both directions, which
-- is the only form that catches an addition as well as a removal:
--
--   * the column list, because the controls in this module are absences -- there is no column
--     a credential value could sit in, and a later migration adding one is exactly what this
--     notices;
--   * every NOT NULL, because nothing in this file read `attnotnull` until MOD-016 and 84 of
--     its 120 columns turned out to be droppable in silence. A NOT NULL is what makes a
--     sibling CHECK bite -- a `coalesce`-free predicate evaluates to NULL and therefore
--     passes -- and under MATCH SIMPLE a NULL in any column of a composite foreign key skips
--     the whole reference, so dropping one switches off a tenant-carrying parent in a way the
--     foreign-key set comparison cannot see;
--   * every column-level UPDATE grant per role, read through `has_column_privilege` rather
--     than `information_schema`, whose views are filtered to what the current user can see --
--     so a check running as one role proves nothing about the other and passes vacuously for
--     half the roles it claims to cover.
--
-- {len(tables)} tables, {len(columns)} columns, {len(not_null)} NOT NULLs,
-- {len(grants)} column grants, {len(fkeys)} foreign keys.
DO $$
DECLARE
    wrong text;
    seen int;
BEGIN
    SELECT count(*) INTO seen FROM pg_class c
    WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
      AND c.relname LIKE 'acc\\_%';
    IF seen <> {len(tables)} THEN
        RAISE EXCEPTION 'CHECK 106 FAILED: expected {len(tables)} MOD-022 tables, found %', seen;
    END IF;

    WITH expected(col) AS (VALUES
{values(columns)}
    ), actual(col) AS (
        SELECT table_name || '.' || column_name FROM information_schema.columns
        WHERE table_schema = 'plt01' AND table_name LIKE 'acc\\_%'
    )
    SELECT string_agg(col, ', ' ORDER BY col) INTO wrong
    FROM ((SELECT col FROM expected EXCEPT SELECT col FROM actual)
          UNION ALL (SELECT col FROM actual EXCEPT SELECT col FROM expected)) AS d;
    IF wrong IS NOT NULL THEN
        RAISE EXCEPTION
            'CHECK 106 FAILED: MOD-022 columns differ from the pinned set: %', wrong;
    END IF;

    WITH expected(col) AS (VALUES
{values(not_null)}
    ), actual(col) AS (
        SELECT c.relname || '.' || a.attname FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        WHERE c.relnamespace = 'plt01'::regnamespace AND c.relname LIKE 'acc\\_%'
          AND a.attnum > 0 AND NOT a.attisdropped AND a.attnotnull
    )
    SELECT string_agg(col, ', ' ORDER BY col) INTO wrong
    FROM ((SELECT col FROM expected EXCEPT SELECT col FROM actual)
          UNION ALL (SELECT col FROM actual EXCEPT SELECT col FROM expected)) AS d;
    IF wrong IS NOT NULL THEN
        RAISE EXCEPTION
            'CHECK 106 FAILED: MOD-022 NOT NULL columns differ from the pinned set: %', wrong;
    END IF;

    WITH expected(g) AS (VALUES
{values(grants)}
    ), actual(g) AS (
        SELECT r.rolname || ' ' || c.relname || '.' || a.attname
        FROM pg_class c
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
        CROSS JOIN (VALUES ('veyro_cp_app'), ('veyro_cp_worker')) AS r(rolname)
        WHERE c.relnamespace = 'plt01'::regnamespace AND c.relkind IN ('r', 'p')
          AND c.relname LIKE 'acc\\_%'
          AND has_column_privilege(r.rolname, c.oid, a.attname, 'UPDATE')
    )
    SELECT string_agg(g, ', ' ORDER BY g) INTO wrong
    FROM ((SELECT g FROM expected EXCEPT SELECT g FROM actual)
          UNION ALL (SELECT g FROM actual EXCEPT SELECT g FROM expected)) AS d;
    IF wrong IS NOT NULL THEN
        RAISE EXCEPTION
            'CHECK 106 FAILED: MOD-022 column UPDATE grants differ from the pinned set: %',
            wrong;
    END IF;

    -- Every parent reference compared as a set, not sampled. MOD-012's review found two
    -- droppable in silence because one table's case had been written and the rest asserted.
    WITH expected(k) AS (VALUES
{values(fkeys)}
    ), actual(k) AS (
        SELECT con.conname || ' ' || pg_get_constraintdef(con.oid)
        FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid
        WHERE c.relnamespace = 'plt01'::regnamespace AND c.relname LIKE 'acc\\_%'
          AND con.contype = 'f'
    )
    SELECT string_agg(k, '; ' ORDER BY k) INTO wrong
    FROM ((SELECT k FROM expected EXCEPT SELECT k FROM actual)
          UNION ALL (SELECT k FROM actual EXCEPT SELECT k FROM expected)) AS d;
    IF wrong IS NOT NULL THEN
        RAISE EXCEPTION
            'CHECK 106 FAILED: MOD-022 foreign keys differ from the pinned set: %', wrong;
    END IF;
END $$;


-- ------------------------------------------- 107. MOD-022's rules, pinned by their own text
-- **The second line of evidence, which runs in CI rather than at the next sweep.** A
-- behavioural case proves that a rule refuses the row it should; none of them notices a rule
-- being *weakened* into one that still refuses that particular row, and none of them sees a
-- plpgsql branch deleted. The text and an `md5` of each trigger body do.
--
-- It does not replace the cases: a pin says the rule is still written down and only a case
-- says it still bites, and one without the other is how vacuous evidence happens. A legitimate
-- schema change fails this until it is regenerated, which is the moment a human reads the diff.
--
-- {len(checks)} checks, {len(indexes)} indexes, {len(triggers)} triggers, {len(bodies)} bodies.
DO $$
DECLARE
    wrong text;
BEGIN
    WITH expected(rule) AS (VALUES
{values(checks)}
    ), actual(rule) AS (
        SELECT con.conname || ' ' || pg_get_constraintdef(con.oid)
        FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid
        WHERE c.relnamespace = 'plt01'::regnamespace AND c.relname LIKE 'acc\\_%'
          AND con.contype = 'c'
    )
    SELECT string_agg(rule, '; ' ORDER BY rule) INTO wrong
    FROM ((SELECT rule FROM expected EXCEPT SELECT rule FROM actual)
          UNION ALL (SELECT rule FROM actual EXCEPT SELECT rule FROM expected)) AS d;
    IF wrong IS NOT NULL THEN
        RAISE EXCEPTION
            'CHECK 107 FAILED: MOD-022 CHECK constraints differ from the pinned set: %', wrong;
    END IF;

    WITH expected(rule) AS (VALUES
{values(indexes)}
    ), actual(rule) AS (
        SELECT i.relname || ' ' || pg_get_indexdef(i.oid)
        FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid
        JOIN pg_class c ON c.oid = x.indrelid
        WHERE c.relnamespace = 'plt01'::regnamespace AND c.relname LIKE 'acc\\_%'
    )
    SELECT string_agg(rule, '; ' ORDER BY rule) INTO wrong
    FROM ((SELECT rule FROM expected EXCEPT SELECT rule FROM actual)
          UNION ALL (SELECT rule FROM actual EXCEPT SELECT rule FROM expected)) AS d;
    IF wrong IS NOT NULL THEN
        RAISE EXCEPTION
            'CHECK 107 FAILED: MOD-022 indexes differ from the pinned set: %', wrong;
    END IF;

    WITH expected(rule) AS (VALUES
{values(triggers)}
    ), actual(rule) AS (
        SELECT t.tgname || ' on ' || c.relname FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        WHERE c.relnamespace = 'plt01'::regnamespace AND c.relname LIKE 'acc\\_%'
          AND NOT t.tgisinternal
    )
    SELECT string_agg(rule, '; ' ORDER BY rule) INTO wrong
    FROM ((SELECT rule FROM expected EXCEPT SELECT rule FROM actual)
          UNION ALL (SELECT rule FROM actual EXCEPT SELECT rule FROM expected)) AS d;
    IF wrong IS NOT NULL THEN
        RAISE EXCEPTION
            'CHECK 107 FAILED: MOD-022 triggers differ from the pinned set: %', wrong;
    END IF;

    -- `md5(prosrc)` catches a deleted branch, which `pg_trigger` cannot see at all: MOD-018's
    -- balance trigger had five branches and four probes, and a reviewer deleted the
    -- mixed-currency one with the suite reporting 84/84.
    WITH expected(rule) AS (VALUES
{values(bodies)}
    ), actual(rule) AS (
        SELECT p.proname || ' ' || md5(p.prosrc) FROM pg_proc p
        WHERE p.pronamespace = 'plt01'::regnamespace AND p.proname LIKE 'acc\\_%'
    )
    SELECT string_agg(rule, '; ' ORDER BY rule) INTO wrong
    FROM ((SELECT rule FROM expected EXCEPT SELECT rule FROM actual)
          UNION ALL (SELECT rule FROM actual EXCEPT SELECT rule FROM expected)) AS d;
    IF wrong IS NOT NULL THEN
        RAISE EXCEPTION
            'CHECK 107 FAILED: a MOD-022 trigger body differs from the pinned digest: %',
            wrong;
    END IF;

    -- Nothing in this file read `proconfig`, `prosecdef` or `tgenabled` until MOD-020, so two
    -- properties the migration asserts in as many words were verified by nothing: a reviewer
    -- ran `ALTER FUNCTION ... RESET search_path` against "their search_path is pinned" and
    -- `GRANT EXECUTE ... TO PUBLIC` against the closing `REVOKE ALL ... FROM PUBLIC`, and the
    -- suite reported every check passing both times. `md5(prosrc)` cannot see either, and
    -- `ALTER TABLE ... DISABLE TRIGGER` leaves the catalogue row in place.
    SELECT string_agg(p.proname, ', ' ORDER BY p.proname) INTO wrong FROM pg_proc p
    WHERE p.pronamespace = 'plt01'::regnamespace AND p.proname LIKE 'acc\\_%'
      AND (p.proconfig IS NULL
           OR NOT ('search_path=pg_catalog, public' = ANY (p.proconfig))
           OR p.prosecdef
           OR has_function_privilege('public', p.oid, 'EXECUTE'));
    IF wrong IS NOT NULL THEN
        RAISE EXCEPTION
            'CHECK 107 FAILED: a MOD-022 function has an unpinned search_path, is SECURITY '
            'DEFINER, or is executable by PUBLIC: %', wrong;
    END IF;

    SELECT string_agg(t.tgname, ', ' ORDER BY t.tgname) INTO wrong FROM pg_trigger t
    JOIN pg_class c ON c.oid = t.tgrelid
    WHERE c.relnamespace = 'plt01'::regnamespace AND c.relname LIKE 'acc\\_%'
      AND NOT t.tgisinternal AND t.tgenabled <> 'O';
    IF wrong IS NOT NULL THEN
        RAISE EXCEPTION 'CHECK 107 FAILED: a MOD-022 trigger is disabled: %', wrong;
    END IF;
END $$;
""")

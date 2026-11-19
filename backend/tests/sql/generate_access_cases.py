#!/usr/bin/env python3
"""Generate a behavioural case per MOD-022 CHECK and per unique rule, from the live schema.

**The cases are generated and then *validated by a mutation sweep*, which is the only thing
that makes a generated case worth anything.** A case written by a generator proves whatever
the generator assumed; `sweep_access.sh` drops the rule the case names and requires the case
to notice. Anything it does not notice is reported as a gap and gets written by hand.

The shape of each case is the one the rules file prescribes: take a row the seed already
proved valid, change **one** column so the row violates exactly the rule under test, and leave
every other column alone. That is what stops a case passing because a sibling fired first --
the trap this file's own suite has been bitten by in four modules.

    ./generate_access_cases.py [container] > cases.sql

Read against a database built from the migrations and the committed seed, so the template rows
are the ones checks 108 and 109 already read.
"""

from __future__ import annotations

import re
import subprocess
import sys

CONTAINER = sys.argv[1] if len(sys.argv) > 1 else "veyro-verify"
TENANT = "11111111-1111-4111-8111-111111111111"

#: One seeded row per table, by primary key, used as the template every case perturbs.
TEMPLATE_KEY = {
    "acc_zones": ("zone_id", "88888888-1000-4000-8000-000000000001"),
    "acc_points": ("point_id", "88888888-2000-4000-8000-000000000001"),
    "acc_policies": ("policy_id", "88888888-3000-4000-8000-000000000002"),
    "acc_credentials": ("credential_id", "88888888-4000-4000-8000-000000000001"),
    "acc_decisions": ("decision_id", "88888888-5000-4000-8000-000000000001"),
    "acc_events": ("event_id", "88888888-6000-4000-8000-000000000001"),
    "acc_emergency_unlocks": ("unlock_id", "88888888-7000-4000-8000-000000000001"),
    "acc_replay_tokens": (
        "token_key", "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"),
}

#: Columns whose value must be fresh on every inserted row, or a unique rule fires instead of
#: the constraint under test. Each maps to a generator of a distinct value.
FRESH = {
    "acc_zones": {"zone_id": "uuid", "zone_key": "text"},
    "acc_points": {"point_id": "uuid", "device_id": "device"},
    "acc_policies": {"policy_id": "uuid", "version": "int"},
    "acc_credentials": {"credential_id": "uuid", "credential_digest": "digest"},
    "acc_decisions": {"decision_id": "uuid", "idempotency_key": "text"},
    "acc_events": {"event_id": "uuid", "idempotency_key": "text"},
    "acc_emergency_unlocks": {"unlock_id": "uuid", "idempotency_key": "text"},
    "acc_replay_tokens": {"token_key": "digest"},
}


def q(sql: str) -> list[list[str]]:
    out = subprocess.run(
        ["docker", "exec", "-e", "PGPASSWORD=veyro_dev", CONTAINER,
         # Separate `-c` flags so the SETs' own output does not land in the result: one
         # `-c` with three statements prints "SET" twice before the rows, which the parser
         # then reads as columns.
         "psql", "-U", "postgres", "-d", "veyro", "-tAqF", "\x1f",
         "-c", "SET ROLE veyro_cp_migrator",
         "-c", f"SET app.tenant_id = '{TENANT}'",
         "-c", sql],
        capture_output=True, text=True, check=True).stdout
    return [line.split("\x1f") for line in out.splitlines() if line.strip()]


def lit(value: str | None, typename: str) -> str:
    if value is None or value == "":
        return "NULL"
    escaped = value.replace("'", "''")
    return f"'{escaped}'::{typename}"


def perturb(predicate: str, columns: dict[str, tuple[str | None, str]]) -> dict[str, str] | None:
    """Several columns at once, for the predicate shapes that relate two of them.

    Each family here is a rule this schema states more than once, so recognising the shape is
    worth more than writing the cases out: a biconditional between a status and its timestamp,
    an attribution trio, a pairing, a non-equality between two actors, an ordering between two
    instants, and a bound against the server's clock. The perturbation always breaks exactly
    one of them -- the others keep the template row's own values.
    """
    p = " ".join(predicate.split())

    # `ts <= now() + interval` -- a bound against the server's clock, not between two
    # caller-supplied columns. Breaking it means a row dated well into the future.
    m = re.fullmatch(r"CHECK \(\((\w+) <= \(now\(\) \+ '[^']+'::interval\)\)\)", p)
    if m and m.group(1) in columns:
        return {m.group(1): "now() + interval '1 year'"}

    # `(status = 'X') = (ts IS NOT NULL)` -- a state and the moment it was entered. Breaking
    # it means claiming the state with no timestamp, which is a row that says when nothing.
    m = re.fullmatch(r"CHECK \(\(\((\w+) = '([^']+)'::text\) = \((\w+) IS NOT NULL\)\)\)", p)
    if m and m.group(1) in columns and m.group(3) in columns:
        return {m.group(1): f"'{m.group(2)}'", m.group(3): "NULL"}

    # The same shape with the sides written the other way round.
    m = re.fullmatch(r"CHECK \(\(\((\w+) = '([^']+)'::text\) = \((\w+) IS NOT NULL\)\)\)",
                     p.replace(" = (", " = ("))
    if m and m.group(1) in columns and m.group(3) in columns:
        return {m.group(1): f"'{m.group(2)}'", m.group(3): "NULL"}

    # `(a IS NULL) = (b IS NULL)` -- a pairing. Breaking it means setting one and not the
    # other, which is half a fact.
    m = re.fullmatch(r"CHECK \(\(\((\w+) IS NULL\) = \((\w+) IS NULL\)\)\)", p)
    if m and m.group(1) in columns and m.group(2) in columns:
        a, b = m.group(1), m.group(2)
        # **Where the template already sets both, break the pairing by clearing one** rather
        # than by inventing a value for the other: a made-up id reaches a foreign key or a
        # coherence trigger first, and the case then proves whichever of those answered.
        if columns[a][0] is not None and columns[b][0] is not None:
            return {b: "NULL"}
        kind = columns[a][1]
        value = ("600" if kind in ("integer", "bigint")
                 else "'33333333-3333-4333-8333-333333333333'::uuid" if kind == "uuid"
                 else "now()" if "time" in kind else "'x'")
        return {a: value, b: "NULL"}

    # `a IS NULL OR a <> b` -- two parties who must differ. Breaking it means one person
    # doing both acts, which is the separation of duties.
    m = re.fullmatch(r"CHECK \(\(\((\w+) IS NULL\) OR \((\w+) <> (\w+)\)\)\)", p)
    if m and m.group(2) in columns and m.group(3) in columns:
        other = columns[m.group(3)][0]
        if other:
            return {m.group(2): lit(other, columns[m.group(3)][1])}

    # `a IS NULL OR a >= b` -- an ordering between two instants.
    m = re.fullmatch(r"CHECK \(\(\((\w+) IS NULL\) OR \((\w+) >= (\w+)\)\)\)", p)
    if m and m.group(2) in columns and m.group(3) in columns:
        other = columns[m.group(3)][0]
        if other:
            return {m.group(2): f"{lit(other, columns[m.group(3)][1])} - interval '1 hour'"}

    # `a > b` -- a window with a positive length.
    m = re.fullmatch(r"CHECK \(\((\w+) > (\w+)\)\)", p)
    if m and m.group(1) in columns and m.group(2) in columns:
        other = columns[m.group(2)][0]
        if other:
            return {m.group(1): f"{lit(other, columns[m.group(2)][1])} - interval '1 second'"}

    # `(a - b) <= interval` -- a bounded window.
    m = re.fullmatch(r"CHECK \(\(\((\w+) - (\w+)\) <= '([^']+)'::interval\)\)", p)
    if m and m.group(1) in columns and m.group(2) in columns:
        other = columns[m.group(2)][0]
        if other:
            return {m.group(1): f"{lit(other, columns[m.group(2)][1])} + interval '1 year'"}

    # `a IS NULL OR a <> b` where the two are minute-of-day numbers: both set to one value,
    # which is a window that opens and closes at the same moment.
    m = re.fullmatch(r"CHECK \(\(\((\w+) IS NULL\) OR \((\w+) <> (\w+)\)\)\)", p)
    if m and m.group(2) in columns and m.group(3) in columns:
        return {m.group(2): "600", m.group(3): "600"}

    # `status <> 'X' OR ts IS NOT NULL` -- an implication rather than a biconditional.
    m = re.fullmatch(r"CHECK \(\(\((\w+) <> '([^']+)'::text\) OR \((\w+) IS NOT NULL\)\)\)", p)
    if m and m.group(1) in columns and m.group(3) in columns:
        return {m.group(1): f"'{m.group(2)}'", m.group(3): "NULL"}

    # `source = 'offline' = (seq IS NOT NULL)` with the text literal on the left.
    m = re.fullmatch(
        r"CHECK \(\(\((\w+) = '([^']+)'::text\) = \((\w+) IS NOT NULL\)\)\)", p)
    if m and m.group(1) in columns and m.group(3) in columns:
        return {m.group(1): f"'{m.group(2)}'", m.group(3): "NULL"}

    # An attribution trio: all three NULL or all three set. **Broken with NULL, never a
    # blank** -- `length(btrim(NULL)) > 0` is NULL and a CHECK passes on NULL, so only the
    # NULL case proves the `coalesce` these constraints are written around.
    m = re.search(
        r"\(\((\w+) IS NULL\) AND \((\w+) IS NULL\) AND \((\w+) IS NULL", p)
    if m and all(g in columns for g in m.groups()):
        first, second, third = m.groups()
        if all(columns[g][0] is not None for g in (first, second, third)):
            return {second: "NULL"}
        kind = columns[first][1]
        set_value = ("now()" if "time" in kind
                     else "'33333333-3333-4333-8333-333333333333'::uuid" if kind == "uuid"
                     else "'x'")
        return {first: set_value, second: "NULL", third: "NULL"}
    return None


def violations(predicate: str, column: str, typename: str) -> list[tuple[str, str]]:
    """Every value that breaks this predicate for this column, from the predicate's own shape.

    **A list rather than one value, and that is the whole point.** The first version returned
    the first shape it recognised, so `x >= 0 AND x <= 1000000` got a case for the floor and
    none for the ceiling -- and a weakening sweep then showed seventeen bounds and conjuncts
    with no case behind them, which is `.claude/rules/backend/mod004-rls.md`'s "a case proves
    the constraint it names only in the direction it exercises" measured rather than argued.
    The caller walks every column the predicate names, so a conjunction over two columns gets
    a case each.

    An empty list means the shape is not one of the mechanical ones; those are reported and
    written by hand, which is the honest split -- a generator that guessed would produce a
    case that passes for the wrong reason.
    """
    p = " ".join(predicate.split())
    col = re.escape(column)
    found: list[tuple[str, str]] = []

    if re.search(rf"\b{col}\s*=\s*ANY\s*\(ARRAY\[", p):
        found.append(("domain", "'not-a-declared-value'"))
    if re.search(rf"\b{col}\s*~\s*'\[\^\[:space:\]\]'", p):
        # A tab, not spaces: `btrim` strips spaces and nothing else, so a space case cannot
        # tell `length(btrim(x)) > 0` from the form this build standardised on.
        found.append(("blank", "E'\\t'"))
    for m in re.finditer(rf"length\(\s*{col}\s*\)\s*<=\s*(\d+)", p):
        found.append(("too-long", f"repeat('x', {int(m.group(1)) + 1})"))
    if typename in ("integer", "bigint"):
        for m in re.finditer(rf"\b{col}\s*>=\s*'?(-?\d+)'?", p):
            found.append(("below-the-floor", str(int(m.group(1)) - 1)))
        for m in re.finditer(rf"\b{col}\s*<=\s*'?(-?\d+)'?", p):
            found.append(("above-the-ceiling", str(int(m.group(1)) + 1)))
        for m in re.finditer(rf"\b{col}\s*<\s*'?(-?\d+)'?(?!=)", p):
            found.append(("at-the-ceiling", m.group(1)))
    if re.search(rf"\b{col}\s*~\s*'\^", p):
        # Spaces, uppercase and punctuation together: no shape regex in this schema admits
        # all three, and `'not-the-right-shape'` did -- it is a valid slug, so the zone-key
        # case passed its own constraint and proved nothing.
        found.append(("shape", "'!! NOT A VALID VALUE !!'"))

    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for label, value in found:
        if value in seen:
            continue
        seen.add(value)
        unique.append((label, value))
    return unique


def fresh_value(table: str, column: str, typename: str, nth: int) -> str | None:
    kind = FRESH.get(table, {}).get(column)
    if kind is None:
        return None
    if kind == "device":
        # The seed's fifth device, which carries `access.actuate`, is active and is the point
        # of no committed access point. Without it the primary-key case duplicated the device
        # key as well -- and `DROP CONSTRAINT ... CASCADE` takes that key with the key under
        # test, so nothing was left to fire and the case proved nothing.
        return "'77777777-2000-4000-8000-000000000005'::uuid"
    if kind == "uuid":
        return f"'88888888-{nth:04d}-4000-8000-0000000000ff'::uuid"
    if kind == "digest":
        return f"lpad('{nth:x}', 64, 'e')"
    if kind == "int":
        return str(100 + nth)
    return f"'generated-case-{nth}'"


def main() -> int:
    tables = sorted(TEMPLATE_KEY)
    rows: dict[str, dict[str, tuple[str | None, str]]] = {}
    for table in tables:
        key, value = TEMPLATE_KEY[table]
        cols = q(
            "SELECT column_name, data_type FROM information_schema.columns"
            f" WHERE table_schema='plt01' AND table_name='{table}'"
            " ORDER BY ordinal_position")
        names = [c[0] for c in cols]
        data = q(f"SELECT {', '.join(names)} FROM plt01.{table}"
                 f" WHERE {key} = '{value}'")
        if not data:
            print(f"-- NO TEMPLATE ROW for {table}", file=sys.stderr)
            continue
        rows[table] = {
            name: (None if raw == "" else raw, kind)
            for (name, kind), raw in zip(cols, data[0], strict=True)
        }

    constraints = q(
        "SELECT c.relname, con.conname, pg_get_constraintdef(con.oid)"
        " FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid"
        " WHERE c.relnamespace='plt01'::regnamespace AND c.relname LIKE 'acc\\_%'"
        "   AND con.contype='c' ORDER BY 1, 2")

    # **Constraints whose every possible case is answered by a trigger first.** The rules file
    # gives three options for a rule with no isolating case: delete it if a sibling subsumes
    # it, write a case that reaches it, or keep the primitive statement and let the definition
    # pin be its evidence. This is the third, and the reason has to be written down.
    #
    # `acc_events_direction` is a domain over entry and exit, and `acc_event_is_coherent`
    # refuses any direction its access point does not face -- which is every value outside the
    # domain, for every point in the seed. A row that reached the CHECK would need a point
    # facing `both`, and seeding one would take the spare device the point cases use to avoid
    # the one-point-per-device key, so the cases that currently prove four other rules would
    # start proving that key instead. The trigger branch has its own probe in check 111 and
    # the CHECK's text is pinned by check 107.
    # **Columns a case has to set so that only the rule under test refuses the row.**
    # `check_violation` does not say *which* constraint fired, and the first version of these
    # cases counted any of them -- so fourteen of them were answered by a sibling and the
    # sweep found all fourteen when the drops stopped being caught. The handler now asserts
    # `CONSTRAINT_NAME`, which turns a sibling into a reported confusion rather than a catch,
    # and these are what make each row reach the rule it names.
    #
    # Each entry is the sibling's own requirement, read off the sibling: an attribution trio
    # needs its status, a bounded value needs the pairing that permits it to be set at all,
    # and a domain needs the correspondence CHECK beside it satisfied.
    COMPANIONS = {
        # `granted_matches_code` would fire on any code outside the granted set.
        "acc_decisions_code": {
            "granted": "false", "code": "'not-a-declared-value'", "masked": "true",
            "public_reason": "'please see the front desk'",
        },
        # The mirror: a valid refusal code on a row that claims to be a grant.
        "acc_decisions_granted_matches_code": {
            "granted": "true", "code": "'outstanding_balance'", "masked": "true",
            "public_reason": "'please see the front desk'",
        },
        # `override_attributed` demands the override code and an actor before a reason may
        # be set at all, so the length bound is unreachable without them.
        "acc_decisions_override_reason_bounded": {
            "code": "'granted_by_override'", "granted": "true",
            "overridden_by": "'33333333-3333-4333-8333-333333333333'::uuid",
            "masked": "false", "public_reason": "'welcome'",
            "policy_id": "NULL", "policy_version": "NULL",
        },
        # The separation of duties is reachable only once the review is complete, because
        # `review_attributed` is all-or-none and fires first on a half-written one.
        "acc_emergency_unlocks_reviewer_is_not_orderer": {
            "reviewed_at": "now()", "review_note": "'the alarm was genuine'",
            "review_correlation_id": "'33333333-3333-4333-8333-333333333333'::uuid",
        },
        # The same for a policy: `publication_attributed` fires before the two-party rule.
        "acc_policies_publisher_is_not_author": {
            "published_at": "now()",
            "publish_correlation_id": "'33333333-3333-4333-8333-333333333333'::uuid",
        },
        # `review_attributed` is all-or-none, so a review time alone never reaches the
        # ordering rule.
        "acc_emergency_unlocks_review_after_order": {
            "reviewed_by": "'44444444-4444-4444-8444-444444444444'::uuid",
            "review_note": "'the alarm was genuine'",
            "review_correlation_id": "'33333333-3333-4333-8333-333333333333'::uuid",
        },
        "acc_events_reconciled_outcome": {
            "reconciled_at": "now()",
            "reconciled_by": "'33333333-3333-4333-8333-333333333333'::uuid",
            "reconcile_correlation_id": "'33333333-3333-4333-8333-333333333333'::uuid",
        },
        # The attribution itself: a complete reconciliation minus the actor.
        "acc_events_reconciliation_attributed": {
            "reconciled_outcome": "'accepted'", "reconciled_at": "now()",
            "reconciled_by": "NULL",
            "reconcile_correlation_id": "'33333333-3333-4333-8333-333333333333'::uuid",
        },
        # `sequence_matches_source` ties the sequence number to the offline source.
        "acc_events_sequence_sane": {"source": "'offline'"},
        # `retired_is_retired` is a biconditional, so an attribution case has to retire the
        # row as well.
        "acc_points_retirement_attributed": {"status": "'retired'", "retired_at": "now()"},
        "acc_policies_retirement_attributed": {"status": "'retired'", "retired_at": "now()"},
        "acc_zones_retirement_attributed": {"status": "'retired'", "retired_at": "now()"},
        # `hours_paired` means neither minute can be set on its own.
        "acc_policies_opens_in_a_day": {"closes_minute": "1200"},
        "acc_policies_closes_in_a_day": {"opens_minute": "0"},
        # `window_bounded` is measured between the two columns, so moving one alone breaks it
        # as well; the expiry follows the seen time.
        "acc_replay_tokens_not_postdated": {
            "seen_at": "now() + interval '1 year'",
            "expires_at": "now() + interval '1 year' + interval '90 seconds'",
        },
    }

    # **Where the mechanical variant is the wrong row entirely.** `granted = (code = ANY ...)`
    # names `code`, so the shape reader moves `code` to an undeclared value -- which violates
    # the domain beside it and not this rule at all. For these the whole change is written
    # out, and the variants are not consulted.
    OVERRIDES = {
        "acc_decisions_granted_matches_code": {
            "granted": "true", "code": "'outstanding_balance'", "masked": "true",
            "public_reason": "'please see the front desk'",
        },
        "acc_events_reconciliation_attributed": {
            "reconciled_outcome": "'accepted'", "reconciled_at": "now()",
            "reconciled_by": "NULL",
            "reconcile_correlation_id": "'33333333-3333-4333-8333-333333333333'::uuid",
        },
    }

    NO_ISOLATING_CASE = {
        # `acc_event_is_coherent` refuses any direction the point does not face, which is
        # every value outside the domain -- so the row has to arrive at a point facing
        # `both`, and there is none in the committed seed. The case is hand-written: it
        # creates one on the spare device inside its own block, which the refusal then rolls
        # back. Left here as the record of why a generated case cannot reach it.
        "acc_events_direction":
            "needs a point facing both, which the hand-written case creates in its own block",
    }

    emitted, skipped, nth = [], [], 0
    for table, name, predicate in constraints:
        if table not in rows:
            continue
        if name in NO_ISOLATING_CASE:
            skipped.append(f"{name}: {NO_ISOLATING_CASE[name]}")
            continue
        # Which column this constraint is about: the first one it names.
        column = next((c for c in rows[table] if re.search(rf"\b{re.escape(c)}\b", predicate)),
                      None)
        if column is None:
            skipped.append(f"{name}: names no column of {table}")
            continue
        variants: list[tuple[str, dict[str, str]]] = []
        relational = perturb(predicate, rows[table])
        if relational is not None:
            variants.append((", ".join(relational), relational))
        else:
            # Every column the predicate names, and every way each one can break it: a
            # conjunction over two columns is two cases, and a two-sided bound is two more.
            for candidate, (_, kind) in rows[table].items():
                if not re.search(rf"\b{re.escape(candidate)}\b", predicate):
                    continue
                for label, bad in violations(predicate, candidate, kind):
                    variants.append((f"{candidate} {label}", {candidate: bad}))
        if not variants:
            skipped.append(f"{name}: predicate shape not mechanical ({predicate[:70]})")
            continue
        companions = COMPANIONS.get(name, {})
        if name in OVERRIDES:
            variants = [(", ".join(OVERRIDES[name]), OVERRIDES[name])]
        for label, changes in variants:
            # The companions go in first, so a variant that moves one of the same columns
            # wins -- the variant is the thing under test.
            changes = {**companions, **changes}
            nth += 1
            values = []
            for col, (raw, kind) in rows[table].items():
                if col in changes:
                    values.append(changes[col])
                    continue
                replacement = fresh_value(table, col, kind, nth)
                values.append(replacement if replacement is not None else lit(raw, kind))
            emitted.append((table, name, label, list(rows[table]), values))

    # **Delimiters, because a splice by eye deleted nineteen hand-written cases once.** The
    # previous version of this generator printed no end marker, so re-splicing its output into
    # `isolation.sql` meant choosing a line to stop at -- and the line chosen was below the
    # hand-written section rather than above it. Everything between the two markers is
    # generated and may be replaced; nothing outside them is.
    print("    -- >>> GENERATED CHECK CASES BEGIN -- do not edit between the markers")
    print("    -- GENERATED by tests/sql/generate_access_cases.py and validated by")
    print("    -- tests/sql/sweep_access.sh. Each case takes a row the seed proved valid and")
    print("    -- changes exactly one column, so the rule it names is the only one it breaks.")
    for table, name, column, cols, values in emitted:
        print(f"""    -- {name}
    BEGIN
        INSERT INTO plt01.{table} ({', '.join(cols)})
        VALUES ({', '.join(values)});
        RAISE EXCEPTION
            'CHECK 110 FAILED: {name} admitted a row with a bad {column}';
    EXCEPTION
        WHEN check_violation THEN
            -- **Which constraint refused it, not merely that one did.** `check_violation`
            -- is the same exception for every CHECK on the table, so counting it proves
            -- whichever fires first -- the trap `.claude/rules/backend/mod004-rls.md`
            -- records three modules in a row for, and which fourteen of these cases were
            -- in until the sweep showed their drops going uncaught.
            GET STACKED DIAGNOSTICS offender = CONSTRAINT_NAME;
            IF offender = '{name}' THEN
                probe := probe + 1;
            ELSE
                confused := array_append(
                    confused, '{name} (answered by ' || offender || ')');
            END IF;
        WHEN raise_exception THEN
            IF SQLERRM LIKE 'CHECK 110 FAILED%' THEN RAISE; END IF;
            confused := array_append(confused, '{name} (answered by a trigger)');
    END;""")
    print("    -- <<< GENERATED CHECK CASES END")

    # ---- the unique rules -----------------------------------------------------------
    #
    # **Every one had no case at all**, which a reviewer found by dropping all twenty-five
    # indexes and watching the suite catch none -- including `acc_replay_tokens_pkey`, which
    # the migration calls "the deduplication *is* the constraint" and which is paragraph
    # 4183's whole anti-replay mechanism. MOD-010's review found the same shape for a
    # delivery key.
    #
    # A unique rule's case is a duplicate, and isolating it means freshening the columns of
    # *every other* unique rule on the table: re-inserting a row verbatim violates all of
    # them at once and proves whichever the planner reached first.
    print("    -- >>> GENERATED UNIQUE CASES BEGIN -- do not edit between the markers")
    uniques = q(
        "SELECT DISTINCT c.relname, i.relname,"
        "       (SELECT string_agg(a.attname, ',' ORDER BY k.ord)"
        "          FROM unnest(x.indkey) WITH ORDINALITY AS k(attnum, ord)"
        "          JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = k.attnum)"
        " FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid"
        " JOIN pg_class c ON c.oid = x.indrelid"
        " WHERE c.relnamespace='plt01'::regnamespace AND c.relname LIKE 'acc\\_%'"
        "   AND x.indisunique ORDER BY 2")
    by_table: dict[str, list[tuple[str, list[str]]]] = {}
    for table, index, cols in uniques:
        if table in rows and cols:
            by_table.setdefault(table, []).append((index, cols.split(",")))

    # **A partial unique index needs a row inside its own predicate.** The policy template is
    # the seeded *draft* -- deliberately, because the "a published policy's terms are frozen"
    # trigger would answer for half the generated cases otherwise -- and a draft falls outside
    # `WHERE status = 'published'`, so the duplicate case inserted happily and the index was
    # proved by nothing. The overrides put the row where the index can see it, with the
    # publication attribution its siblings require and a publisher who is not the author.
    PARTIAL = {
        "acc_policies_one_live_per_zone": {
            "zone_id": "'88888888-1000-4000-8000-000000000001'::uuid",
            "status": "'published'",
            "published_at": "now()",
            "published_by": "'44444444-4444-4444-8444-444444444444'::uuid",
            "publish_correlation_id": "'33333333-3333-4333-8333-333333333333'::uuid",
        },
    }

    unique_cases = 0
    for table, indexes in sorted(by_table.items()):
        for index, cols in indexes:
            nth += 1
            keep = set(cols)
            others = {c for other, ocols in indexes if other != index for c in ocols}
            override = PARTIAL.get(index, {})
            values = []
            for col, (raw, kind) in rows[table].items():
                if col in override:
                    values.append(override[col])
                    continue
                if col in keep:
                    values.append(lit(raw, kind))
                    continue
                if col in others:
                    fresh = fresh_value(table, col, kind, nth) or lit(raw, kind)
                    values.append(fresh)
                    continue
                values.append(lit(raw, kind))
            unique_cases += 1
            print(f"""    -- {index} on ({', '.join(cols)})
    BEGIN
        INSERT INTO plt01.{table} ({', '.join(rows[table])})
        VALUES ({', '.join(values)});
        RAISE EXCEPTION
            'CHECK 110 FAILED: {index} admitted a duplicate';
    EXCEPTION
        WHEN unique_violation THEN
            GET STACKED DIAGNOSTICS offender = CONSTRAINT_NAME;
            IF offender = '{index}' THEN
                probe := probe + 1;
            ELSE
                confused := array_append(
                    confused, '{index} (answered by ' || offender || ')');
            END IF;
        WHEN check_violation OR raise_exception THEN
            IF SQLERRM LIKE 'CHECK 110 FAILED%' THEN RAISE; END IF;
            confused := array_append(confused, '{index} (answered by another rule)');
    END;""")

    print("    -- <<< GENERATED UNIQUE CASES END")
    print(f"\n-- {len(emitted)} generated, {unique_cases} unique, "
          f"{len(skipped)} left for hand-written cases", file=sys.stderr)
    for s in skipped:
        print(f"--   {s}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env bash
# Break every MOD-022 schema rule, one at a time, and record which ones the suite notices.
#
# **This module shipped without one, and that was the largest finding against it.** An
# independent reviewer dropped all 73 `acc_` CHECK constraints individually and watched check
# 109 catch seven; dropped all 25 indexes and keys and watched it catch none; and replaced
# five of the ten trigger functions with `BEGIN RETURN NEW; END` while the suite reported
# 109/109. MOD-019 ran 770 mutations against its schema, MOD-020 580 and MOD-021 810. The
# "20/20 mutations caught" this module shipped with is a Python sweep over the decision
# modules, which is a different thing and does not touch the half where the rules live.
#
#   tests/sql/sweep_access.sh                 # every mutation
#   tests/sql/sweep_access.sh acc_decisions   # only rules on tables matching a pattern
#
# Four classes of mutation, because each needs a different statement:
#   * a CHECK is dropped with ALTER TABLE ... DROP CONSTRAINT;
#   * an index created by CREATE UNIQUE INDEX is dropped with DROP INDEX, and a constraint
#     index needs DROP CONSTRAINT -- the rules file records a sweep that reported the first
#     form as "caught" when the statement had simply errored;
#   * a CHECK is also *weakened* rather than dropped -- one conjunct removed, one side of a
#     biconditional, a widened bound -- because a case proves a constraint only in the
#     direction it exercises, and a reviewer weakened eight of MOD-013's to one-way
#     implications with the suite reporting 60/60 every time;
#   * a plpgsql branch is invisible to all of those, so a trigger function is re-created with
#     one branch deleted. That is the mutation MOD-018's review used to delete a balance rule
#     with the suite green.
#
# A mutation that the database refuses (a dependent key, an ill-formed predicate) is reported
# as NOT RUN rather than as a catch: "the statement did not apply" recorded as evidence is the
# false green this whole discipline exists to prevent.
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
PSQL=${PSQL:-"docker exec -i veyro-verify psql -U postgres"}
FILTER=${1:-}
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

ask() { $PSQL -d veyro -tAq -c "$1"; }

# **The judge is the behavioural block alone, not the whole file.**
#
# The first version of this harness ran `verify_db.sh` per mutation and reported almost
# everything as caught -- by check 107, the *definition pin*, which notices any change to a
# constraint's text. That is the pin doing its job and it is not evidence that a case bites:
# "a pin says the rule is still written down and only a case says it still bites, and one
# without the other is how vacuous evidence happens" is check 107's own preamble, and a sweep
# that cannot tell the two apart reports the vacuity as success. So the mutation is applied to
# a built database and only checks 108 and 109 are re-run against it.
extract() {
    "$ROOT/.venv/bin/python3" - "$ROOT/backend/tests/sql/isolation.sql" "$1" <<'PYX'
import pathlib, sys
text = pathlib.Path(sys.argv[1]).read_text()
start = text.index(sys.argv[2])
end = text.index("\\echo 'tenant isolation", start)
print("SET ROLE veyro_cp_migrator;")
print("BEGIN;")
print(text[start:end].replace("\\echo", "-- echo"))
print("ROLLBACK;")
PYX
}

echo "building the baseline..."
if ! PSQL="$PSQL" "$ROOT/backend/scripts/verify_db.sh" >"$WORK/base.log" 2>&1; then
    echo "BASELINE IS RED -- fix that before sweeping:"; tail -5 "$WORK/base.log"; exit 2
fi
grep -o 'tenant isolation: .*' "$WORK/base.log"
extract "-- ------------------------------------------- 108. MOD-022 is invisible" \
    >"$WORK/judge.sql"
if ! $PSQL -d veyro -v ON_ERROR_STOP=1 -q < "$WORK/judge.sql" >"$WORK/judge.log" 2>&1; then
    echo "THE JUDGE IS RED ON A CLEAN DATABASE:"; tail -5 "$WORK/judge.log"; exit 2
fi
echo "judge: checks 108-111 green on the baseline"

# ---- the mutation list ---------------------------------------------------------------------
: >"$WORK/mutations"

ask "SELECT con.conname, c.relname FROM pg_constraint con
     JOIN pg_class c ON c.oid = con.conrelid
     WHERE c.relnamespace = 'plt01'::regnamespace AND c.relname LIKE 'acc\\_%'
       AND con.contype = 'c' ORDER BY 1" |
while IFS='|' read -r name table; do
    [ -n "$name" ] || continue
    printf 'check\t%s\t%s\tALTER TABLE plt01.%s DROP CONSTRAINT %s;\n' \
        "$name" "$table" "$table" "$name" >>"$WORK/mutations"
done

# An index backed by a constraint has to go through the constraint, with CASCADE where a
# foreign key depends on it; a bare unique index goes through DROP INDEX.
# **Unique rules only.** A non-unique index decides how fast a query runs, never which rows
# are admitted, so no behavioural case can exist for one and sweeping it reports a gap nobody
# can close. Check 107 pins their text, which is the right evidence for a rule whose effect is
# not observable from a row -- the same judgement the rules file reaches for a constraint that
# has no isolating case.
ask "SELECT DISTINCT i.relname, c.relname, coalesce(con.conname, '')
     FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid
     JOIN pg_class c ON c.oid = x.indrelid
     -- The contype filter is load-bearing: a foreign key also names the index it reads, so
     -- without it a primary-key index produced one row per dependent key, each telling the
     -- harness to drop that foreign key from the index own table -- which does not exist
     -- there, so thirteen mutations were refused and recorded as not-run. The rules file
     -- records exactly this: a harness that misclassifies hides the real gap among the
     -- noise, and the primary keys it hid are the ones MOD-016 found unproven. No backticks
     -- or parentheses in this comment: it lives inside a double-quoted bash string.
     LEFT JOIN pg_constraint con
            ON con.conindid = i.oid AND con.contype IN ('p', 'u')
     WHERE c.relnamespace = 'plt01'::regnamespace AND c.relname LIKE 'acc\\_%'
       AND x.indisunique ORDER BY 1" |
while IFS='|' read -r index table con; do
    [ -n "$index" ] || continue
    if [ -n "$con" ]; then
        printf 'index\t%s\t%s\tALTER TABLE plt01.%s DROP CONSTRAINT %s CASCADE;\n' \
            "$index" "$table" "$table" "$con" >>"$WORK/mutations"
    else
        printf 'index\t%s\t%s\tDROP INDEX plt01.%s;\n' \
            "$index" "$table" "$index" >>"$WORK/mutations"
    fi
done

# One mutation per weakening of a CHECK: a dropped conjunct, each side of a biconditional on
# its own, and a widened numeric bound. A drop is not the only mutation a constraint has, and a
# case proves a constraint only in the direction it exercises.
"$ROOT/.venv/bin/python3" "$ROOT/backend/tests/sql/weaken_access_checks.py" >>"$WORK/mutations"

# One mutation per plpgsql branch: the function re-created with that RAISE removed. A branch
# whose RAISE never fires cannot refuse anything, which is exactly what a deleted branch is.
"$ROOT/.venv/bin/python3" - "$WORK" <<'PY' >>"$WORK/mutations"
import os, re, subprocess, sys
work = sys.argv[1]
psql = os.environ.get("PSQL", "docker exec -i veyro-verify psql -U postgres").split()
out = subprocess.run(
    psql + ["-d", "veyro", "-tAq", "-c",
            "SELECT proname FROM pg_proc WHERE pronamespace='plt01'::regnamespace"
            " AND proname LIKE 'acc\\_%' ORDER BY 1"],
    capture_output=True, text=True).stdout.split()
for fn in out:
    body = subprocess.run(
        psql + ["-d", "veyro", "-tAq", "-c",
                f"SELECT pg_get_functiondef('plt01.{fn}'::regproc)"],
        capture_output=True, text=True).stdout
    # Each `RAISE EXCEPTION` is one refusal. Neutralising it leaves the branch's condition
    # intact and its consequence gone, which is the smallest honest break.
    for n, match in enumerate(re.finditer(r"RAISE EXCEPTION", body), start=1):
        mutated = body[:match.start()] + "RAISE DEBUG" + body[match.end():]
        # Inlined, not written to a file: `psql` runs inside the container and resolves a
        # path there, so `\i /host/path` was refused for all forty branch mutations and the
        # sweep recorded them as not-run.
        # **Newlines encoded, not collapsed.** The mutation list is tab-separated, so the
        # first version replaced every newline with a space -- which turns each `--` comment
        # in the function body into one that swallows the rest of the definition. All forty
        # branch mutations were refused with "syntax error at end of input" and recorded as
        # not-run, which is the harness reporting a gap it had created.
        one_line = (mutated + ";").replace("\t", "    ").replace("\n", "\x01")
        print(f"branch\t{fn}#{n}\t{fn}\t{one_line}")
PY

total=$(wc -l <"$WORK/mutations" | tr -d ' ')
echo "$total mutations"

caught=0; gaps=(); notrun=()
# **Read on fd 3, not stdin.** `verify_db.sh` pipes SQL into psql on stdin, so a loop
# reading its mutation list from stdin has it swallowed after the first iteration --
# which looked like a sweep that ran one mutation and reported success.
while IFS=$'\t' read -r kind name table sql <&3; do
    [ -n "$name" ] || continue
    if [ -n "$FILTER" ] && [[ "$name$table" != *"$FILTER"* ]]; then continue; fi
    log="$WORK/run.log"
    # Apply the mutation to the standing database, run the judge, then undo it by rebuilding
    # only when something actually changed the schema irreversibly. A transaction around the
    # judge keeps its rows out of the way; the mutation itself is rolled back by restoring
    # from the migrations at the end of each iteration.
    : >"$log"
    if ! printf '%s\n' "SET ROLE veyro_cp_migrator;" "$sql" \
         | tr '\001' '\n' \
         | $PSQL -d veyro -v ON_ERROR_STOP=1 -q >>"$log" 2>&1; then
        notrun+=("$kind $name: mutation refused: $(grep -m1 '^ERROR' "$log" | cut -c1-90)")
        printf 'SKIP  %-12s %s (mutation refused)\n' "$kind" "$name"
        continue
    fi
    if $PSQL -d veyro -v ON_ERROR_STOP=1 -q < "$WORK/judge.sql" >>"$log" 2>&1; then
        gaps+=("$kind $name ($table)")
        printf 'GAP   %-12s %s\n' "$kind" "$name"
    else
        # The judge's own refusals all say "CHECK nn FAILED". Anything else is the mutated
        # schema breaking a *case's own insert*, which proves nothing about the rule.
        if grep -qE 'CHECK 1[01][0-9] FAILED' "$log"; then
            caught=$((caught + 1))
            printf 'ok    %-12s %s\n' "$kind" "$name"
        else
            notrun+=("$kind $name: $(grep -m1 '^ERROR' "$log" | cut -c1-110)")
            printf 'SKIP  %-12s %s\n' "$kind" "$name"
        fi
    fi
    PSQL="$PSQL" "$ROOT/backend/scripts/verify_db.sh" >/dev/null 2>&1
done 3<"$WORK/mutations"

echo
echo "$caught caught, ${#gaps[@]} uncaught, ${#notrun[@]} not run"
if [ ${#gaps[@]} -gt 0 ]; then printf 'UNCAUGHT:\n'; printf '  %s\n' "${gaps[@]}"; fi
if [ ${#notrun[@]} -gt 0 ]; then printf 'NOT RUN:\n'; printf '  %s\n' "${notrun[@]}"; fi
[ ${#gaps[@]} -eq 0 ] && [ ${#notrun[@]} -eq 0 ]

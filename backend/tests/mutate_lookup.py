"""Mutations against FD-02's lookup, one protection at a time. ADR-0012.

What these prove is that the prefix is matched on the start of a folded name and not loosely,
that a wildcard somebody typed is a character rather than a pattern, that a one-letter query is
refused rather than answered with the tenant in alphabetical order, that a merged-away record is
not offered, that the page is bounded, and that the index the cost argument rests on is the
operator class it has to be.

Each removes one protection and nothing else; the harness compares the file's bytes before and
after, so a mutation that did not apply is reported NOT RUN rather than counted as a gap.

    VEYRO_DATABASE_URL=... python3 -m tests.mutate_lookup
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import signal
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
PPL = "app/people/service.py"
SQL = "migrations/tenant/0032_a_name_can_be_looked_up_by_its_start.sql"
TESTS = ["tests.test_people_api.LookupTests",
         "tests.test_people_api.LookupIndexTests"]

MUTATIONS = [
    # **A caller-supplied value interpolated into a `LIKE` is a pattern.** MOD-018 shipped
    # exactly this in a wallet idempotency key and a till handed over 90.00 of goods for 1.00.
    ("a wildcard somebody typed stays a wildcard",
     PPL,
     '        pattern = (folded.replace("\\\\", "\\\\\\\\")\n'
     '                   .replace("%", "\\\\%").replace("_", "\\\\_")) + "%"',
     '        pattern = folded + "%"'),
    # The start of the name, which is what makes this a lookup rather than the `LIKE` scan
    # presented as search that MOD-014's own gap list refuses.
    ("the match is loosened to anywhere in the name",
     PPL,
     '        pattern = (folded.replace("\\\\", "\\\\\\\\")\n'
     '                   .replace("%", "\\\\%").replace("_", "\\\\_")) + "%"',
     '        pattern = "%" + (folded.replace("\\\\", "\\\\\\\\")\n'
     '                   .replace("%", "\\\\%").replace("_", "\\\\_")) + "%"'),
    # One letter is every member whose name starts with it, which is not an ambiguous match a
    # desk resolves by photo.
    ("a one-character query is answered rather than refused",
     PPL,
     "    if len(folded) < LOOKUP_MIN_PREFIX:",
     "    if False:"),
    ("the query is not folded, so a typed capital finds nobody",
     PPL,
     '    folded = " ".join(query.split()).lower()',
     '    folded = " ".join(query.split())'),
    # A merge leaves the losing person's rows where they are, so offering the merged-away one
    # points a desk at a record whose own readers are told to follow a pointer.
    ("a merged-away record is offered beside the survivor",
     PPL,
     '            " WHERE lower(p.legal_name) LIKE %s AND p.merge_status = \'active\'"',
     '            " WHERE lower(p.legal_name) LIKE %s"'),
    ("the page bound stops being enforced",
     PPL,
     "    if limit < 1 or limit > LOOKUP_PAGE:",
     "    if False:"),
    # **The index, which is the whole of ADR-0012's cost argument.** The default operator class
    # on this expression cannot serve a prefix in this collation at all.
    ("the prefix index loses its operator class",
     SQL,
     "    ON plt01.ppl_persons (tenant_id, lower(legal_name) text_pattern_ops);",
     "    ON plt01.ppl_persons (tenant_id, lower(legal_name));"),
    ("the prefix index is on the unfolded name",
     SQL,
     "    ON plt01.ppl_persons (tenant_id, lower(legal_name) text_pattern_ops);",
     "    ON plt01.ppl_persons (tenant_id, legal_name text_pattern_ops);"),
]


def digest(path: pathlib.Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def main() -> int:
    caught: list[str] = []
    uncaught: list[str] = []
    notrun: list[str] = []
    psql = os.environ.get("PSQL", "docker exec -i veyro-pg psql -U postgres")
    for name, rel, old, new in MUTATIONS:
        path = BACKEND / rel
        original = path.read_text()
        before = digest(path)

        def restore(
            *_: object, path: pathlib.Path = path, original: str = original,
        ) -> None:
            path.write_text(original)
            sys.exit(130)

        handlers = {
            sig: signal.signal(sig, restore)
            for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
        try:
            if original.count(old) != 1:
                notrun.append(f"{name}: anchor appears {original.count(old)} times")
                continue
            path.write_text(original.replace(old, new, 1))
            if digest(path) == before:
                notrun.append(f"{name}: file unchanged")
                continue
            # **A migration mutation needs the database rebuilt to take effect**, and a
            # Python one does not -- so the schema ones pay for a rebuild and the rest do not.
            if rel.startswith("migrations/"):
                built = subprocess.run(
                    [str(BACKEND / "scripts" / "verify_db.sh")],
                    capture_output=True, text=True,
                    env={**os.environ, "PSQL": psql})
                if built.returncode != 0:
                    notrun.append(f"{name}: the rebuild failed, so nothing was judged")
                    continue
            run = subprocess.run(
                ["../.venv/bin/python3", "-B", "-m", "unittest", *TESTS],
                cwd=BACKEND, capture_output=True, text=True, env=os.environ.copy())
            (caught if run.returncode != 0 else uncaught).append(name)
        finally:
            path.write_text(original)
            assert digest(path) == before, f"{rel} not restored"
            for sig, previous in handlers.items():
                signal.signal(sig, previous)

    # **The database is left as the migrations describe it**, because `verify_db.sh` applies a
    # mutation after the build with nothing putting it back -- which cost a whole backend suite
    # once, reported green against a schema nobody wrote.
    if any(rel.startswith("migrations/") for _, rel, _, _ in MUTATIONS):
        print("\nrestoring the database to the migrations ...", flush=True)
        restored = subprocess.run(
            [str(BACKEND / "scripts" / "verify_db.sh")], capture_output=True, text=True,
            env={**{k: v for k, v in os.environ.items() if k != "MUTATE"}, "PSQL": psql})
        if restored.returncode != 0:
            print("COULD NOT RESTORE -- run verify_db.sh before trusting any suite")
            notrun.append("the restore failed")
        else:
            print("restored")

    for name in caught:
        print(f"CAUGHT    {name}")
    for name in uncaught:
        print(f"UNCAUGHT  {name}")
    for name in notrun:
        print(f"NOT RUN   {name}")
    print(f"\n{len(caught)}/{len(MUTATIONS)} caught, {len(notrun)} not run")
    return 0 if not uncaught and not notrun else 1


if __name__ == "__main__":
    sys.exit(main())

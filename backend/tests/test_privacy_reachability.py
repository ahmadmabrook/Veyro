"""MOD-009 SEC-01-R07/R08: the deletion-reachability registry checked against the live database.

TSD paragraph 4393 makes deletion reachability a Foundation control, and paragraph 4394 gives the
mechanisms for PostgreSQL domain rows. A registry of those mechanisms is only worth having if it
cannot drift from the database it describes, so this suite checks it in both directions:

  * every column in `plt01` or `iam` that names a natural person is declared in
    `app.privacy.classification.SUBJECT_COLUMNS`, so a new table carrying a subject id cannot be
    added without somebody deciding how erasure reaches it; and
  * every declaration agrees with the grants the runtime roles actually hold, so a mechanism
    cannot be claimed that the database would refuse.

The second direction is the one that bites hardest. `anonymize` is a lie unless some runtime role
holds UPDATE on that table, and `unreachable` is a lie if one does -- which means a future
migration that grants UPDATE on an insert-only evidence table fails here, with the registry entry
that said it could not happen printed next to it.

These are integration tests. The property is a property of the catalogue, so a mocked connection
would assert nothing.
"""

from __future__ import annotations

import os
import unittest

import psycopg

from app.privacy.classification import (
    MECHANISMS,
    SUBJECT_COLUMNS,
    unreachable_columns,
    write_once_columns,
)

# A column names a natural person if it is one of these, or if it ends in `_by`. The suffix rule
# is deliberately broad: it will one day catch something like `ordered_by` that is not a person,
# and the cost of that is one registry line saying so, which is much cheaper than the cost of
# missing a real one.
SUBJECT_NAMES = frozenset({
    "identity_id", "person_id", "subject_id", "guardian_subject_id",
    "actor_identity_id", "actor_id",
    # MOD-013's name for the same thing. Added with that module: the sweep matches column
    # names, so a person held under a name nobody listed is invisible to it -- which is how
    # `evt_outbox.payload` came to need a hand-written declaration.
    "recipient_id",
})

#: **Any column whose name ends in `_person_id` as well**, matched by pattern rather than by
#: enumeration. MOD-014 names a person in nine columns the set above misses --
#: `from_person_id`, `to_person_id`, `source_person_id`, `target_person_id`,
#: `lower_person_id`, `higher_person_id`, `merged_into_person_id` -- and each one is a subject
#: identifier an erasure has to account for. Enumerating them would mean the next module's
#: tenth name is invisible again, which is the recurring shape this whole file exists to catch:
#: a per-item list has to be edited when a module adds an item, and that edit is the moment one
#: slips through.
SUBJECT_SUFFIX = r"%\_person\_id"
RUNTIME_ROLES = ("veyro_cp_app", "veyro_cp_worker", "veyro_iam_app")


def _dsn() -> str:
    return os.environ.get(
        "VEYRO_DATABASE_URL", "postgresql://postgres:veyro_dev@127.0.0.1:55432/veyro"
    )


class ReachabilityRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._conn = psycopg.connect(_dsn(), autocommit=True)
        cls.live = {
            (s, t, c)
            for s, t, c in cls._conn.execute(
                """
                SELECT c.table_schema, c.table_name, c.column_name
                FROM information_schema.columns c
                JOIN information_schema.tables t
                  ON t.table_schema = c.table_schema AND t.table_name = c.table_name
                WHERE c.table_schema IN ('plt01', 'iam')
                  AND t.table_type = 'BASE TABLE'
                  AND (c.column_name = ANY(%s) OR c.column_name LIKE %s
                       OR c.column_name LIKE %s)
                """,
                (list(SUBJECT_NAMES), r"%\_by", SUBJECT_SUFFIX),
            ).fetchall()
        }
        # UPDATE and DELETE held by any runtime role, per table. The table owner is excluded on
        # purpose: the migrator holds everything, and checking its grants would make every
        # assertion here pass vacuously.
        cls.grants: dict[tuple[str, str], set[str]] = {}
        for schema, table, privilege in cls._conn.execute(
            """
            SELECT table_schema, table_name, privilege_type
            FROM information_schema.role_table_grants
            WHERE table_schema IN ('plt01', 'iam')
              AND grantee = ANY(%s)
              AND privilege_type IN ('UPDATE', 'DELETE')
            """,
            (list(RUNTIME_ROLES),),
        ).fetchall():
            cls.grants.setdefault((schema, table), set()).add(privilege)

        # **Column-scoped UPDATE, per column.** `role_table_grants` reports table-level grants
        # only, so for every table whose UPDATE is column-scoped -- which is most of them in
        # this repository -- the table-level sweep above returns nothing and
        # `test_an_unreachable_declaration_is_actually_unreachable` passed vacuously. An
        # independent reviewer used that to land two `unreachable` declarations over columns in
        # a column-scoped grant, and then rewrote both as `veyro_cp_app`. `has_column_privilege`
        # over `pg_attribute` rather than the information_schema views, because those are
        # filtered to what the connecting user can see and would hide the worker role's grants.
        cls.column_updates: set[tuple[str, str, str]] = {
            (s, t, c) for s, t, c in cls._conn.execute(
                """
                SELECT n.nspname, c.relname, a.attname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_attribute a ON a.attrelid = c.oid
                CROSS JOIN unnest(%s::text[]) AS r(role)
                WHERE n.nspname IN ('plt01', 'iam') AND c.relkind = 'r'
                  AND a.attnum > 0 AND NOT a.attisdropped
                  AND has_column_privilege(r.role, c.oid, a.attname, 'UPDATE')
                """,
                (list(RUNTIME_ROLES),),
            ).fetchall()
        }

        # Tables with a row-level BEFORE UPDATE trigger. A trigger can refuse what a grant
        # permits, which is the only sanctioned way an `unreachable` declaration may stand over
        # a writable column.
        cls.update_triggers: set[tuple[str, str]] = {
            (s, t) for s, t in cls._conn.execute(
                """
                SELECT n.nspname, c.relname
                FROM pg_trigger tg
                JOIN pg_class c ON c.oid = tg.tgrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE NOT tg.tgisinternal
                  AND (tg.tgtype & 16) <> 0   -- UPDATE
                  AND (tg.tgtype & 2) <> 0    -- BEFORE
                  AND (tg.tgtype & 1) <> 0    -- FOR EACH ROW
                """
            ).fetchall()
        }

    @classmethod
    def tearDownClass(cls) -> None:
        cls._conn.close()

    # ------------------------------------------------------------------ the registry is complete

    def test_every_subject_column_in_the_database_is_declared(self):
        """A new table carrying a subject id cannot be added without declaring how erasure
        reaches it. This is the check that makes the registry a control rather than a comment."""
        declared = {(r.schema, r.table, r.column) for r in SUBJECT_COLUMNS}
        undeclared = sorted(self.live - declared)
        self.assertEqual(
            undeclared, [],
            "these columns name a person and no deletion mechanism is declared for them; add "
            "them to app.privacy.classification.SUBJECT_COLUMNS with the mechanism and the "
            "reason, and if the answer is 'none', say `unreachable` and say why",
        )

    def test_the_registry_names_no_column_that_does_not_exist(self):
        """The other direction: a stale entry would claim coverage of a table that is gone.

        Asked of the catalogue, not of `self.live`. `self.live` is the subject-name heuristic,
        and an entry declared by hand because the heuristic cannot see it -- a subject id inside
        a `jsonb` payload -- is not stale merely because the heuristic missed it.
        """
        columns = {
            (s, t, c) for s, t, c in self._conn.execute(
                "SELECT table_schema, table_name, column_name FROM information_schema.columns"
                " WHERE table_schema IN ('plt01','iam')"
            ).fetchall()
        }
        declared = {(r.schema, r.table, r.column) for r in SUBJECT_COLUMNS}
        self.assertEqual(sorted(declared - columns), [],
                         "these entries name columns the database does not have")

    def test_every_declaration_is_well_formed(self):
        seen = set()
        for r in SUBJECT_COLUMNS:
            self.assertIn(r.mechanism, MECHANISMS, f"{r.table}.{r.column}")
            self.assertTrue(r.reason.strip(), f"{r.table}.{r.column} declares no reason")
            key = (r.schema, r.table, r.column)
            self.assertNotIn(key, seen, f"{key} is declared twice")
            seen.add(key)

    # ------------------------------------------------------------------ the registry cannot lie

    def test_an_anonymize_declaration_has_the_update_grant_behind_it(self):
        """Claiming a row can be emptied is a claim some role can write **each column it names**.

        **Per column, not per table.** This asserted `information_schema.role_table_grants`,
        which reports table-level grants only -- so for a module whose UPDATE is column-scoped,
        which is most of them here, it passed on the strength of the *table* being writable and
        said nothing about the columns the erasure actually overwrites. MOD-007's grants are
        table-level and passed; MOD-014's are column-scoped and the first entry exposed it. That
        is the same blind spot the `column_updates` sweep above was built for, left in place one
        test further along.
        """
        for r in SUBJECT_COLUMNS:
            if r.mechanism != "anonymize":
                continue
            table_level = "UPDATE" in self.grants.get((r.schema, r.table), set())
            for column in r.clears:
                writable = table_level or (r.schema, r.table, column) in self.column_updates
                self.assertTrue(
                    writable,
                    f"{r.schema}.{r.table}.{r.column} is declared anonymize and clears "
                    f"{column!r}, but no runtime role holds UPDATE on that column, so the "
                    f"erasure this promises would fail at run time",
                )

    def test_an_anonymize_declaration_names_columns_that_exist_and_can_be_cleared(self):
        """`clears` is the operative half of the declaration: it says what is destroyed.

        An `anonymize` that clears nothing is a routine that reports success having touched
        nothing, which is the failure mode this whole registry exists to make impossible.
        """
        columns = {
            (s, t, c) for s, t, c in self._conn.execute(
                "SELECT table_schema, table_name, column_name FROM information_schema.columns"
                " WHERE table_schema IN ('plt01','iam')"
            ).fetchall()
        }
        from app.privacy.service import _CLEAR_SQL

        for r in SUBJECT_COLUMNS:
            if r.mechanism != "anonymize":
                continue
            self.assertTrue(r.clears, f"{r.table}.{r.column} is anonymize and clears nothing")
            for column in r.clears:
                self.assertIn((r.schema, r.table, column), columns,
                              f"{r.table}.{column} is declared cleared and does not exist")
                self.assertIn((r.table, column), _CLEAR_SQL,
                              f"{r.table}.{column} is declared cleared and the executor has no "
                              f"rule for how to clear it")

    def test_every_locator_is_a_real_column_of_its_own_table(self):
        """The locator is what the erasure filters on, and a wrong one matches nothing.

        That failure is silent by nature: the UPDATE succeeds, affects zero rows, and the action
        is recorded as done. It happened once -- the `person_id` entry filtered on `person_id`
        using an identity id -- so it is checked statically here rather than left to be noticed
        by a test that happens to read the row back.
        """
        columns = {
            (s, t, c) for s, t, c in self._conn.execute(
                "SELECT table_schema, table_name, column_name FROM information_schema.columns"
                " WHERE table_schema IN ('plt01','iam')"
            ).fetchall()
        }
        for r in SUBJECT_COLUMNS:
            if r.mechanism not in ("anonymize", "delete"):
                continue
            self.assertIn((r.schema, r.table, r.locator()), columns,
                          f"{r.table} is located by {r.locator()}, which it does not have")

    def test_only_an_anonymize_declares_columns_to_clear(self):
        for r in SUBJECT_COLUMNS:
            if r.mechanism == "anonymize":
                continue
            self.assertEqual(r.clears, (),
                             f"{r.table}.{r.column} is {r.mechanism} and cannot clear anything")

    def test_a_covered_declaration_rests_on_an_identity_row_that_is_really_anonymized(self):
        """`covered` means "the subject is anonymous here once iam.identities is emptied". That
        is only true while iam.identities is itself declared anonymize and clears its contact
        columns; if that ever changes, every covered entry silently becomes a lie."""
        covered = [r for r in SUBJECT_COLUMNS if r.mechanism == "covered"]
        self.assertTrue(covered)
        anchors = [r for r in SUBJECT_COLUMNS
                   if (r.schema, r.table) == ("iam", "identities") and r.mechanism == "anonymize"]
        self.assertTrue(anchors, "covered entries depend on iam.identities being anonymized")
        cleared = {c for a in anchors for c in a.clears}
        self.assertIn("display_name", cleared)
        for r in covered:
            self.assertEqual(r.schema, "iam",
                             f"{r.schema}.{r.table} is covered but does not reference iam")

    def test_a_delete_declaration_has_the_delete_grant_behind_it(self):
        for r in SUBJECT_COLUMNS:
            if r.mechanism != "delete":
                continue
            held = self.grants.get((r.schema, r.table), set())
            self.assertIn(
                "DELETE", held,
                f"{r.schema}.{r.table}.{r.column} is declared delete and no runtime role holds "
                f"DELETE on it",
            )

    def test_an_unreachable_declaration_is_actually_unreachable(self):
        """The strongest of the six, and the one most likely to fire years from now.

        `unreachable` is a statement that the database refuses to change this column. If a later
        migration grants UPDATE or DELETE over it, two things are true at once: erasure became
        possible, and the immutability something else depends on was lost. Either way the
        registry entry is wrong and somebody has to look at it.

        Checked at **table and column** level. The table-level half is what this test always
        did, and on its own it passed vacuously for every column-scoped grant in the repository
        -- which is most of them. `write_once` is the mechanism for a column a service really
        does write; a declaration that claims more than that fails here.
        """
        for r in SUBJECT_COLUMNS:
            if r.mechanism != "unreachable":
                continue
            held = self.grants.get((r.schema, r.table), set())
            self.assertEqual(
                held, set(),
                f"{r.schema}.{r.table}.{r.column} is declared unreachable but a runtime role now "
                f"holds {sorted(held)} on the table. Either the grant is a mistake and the "
                f"insert-only property has been lost, or erasure is now possible and this entry "
                f"should say so. Reason on file: {r.reason}",
            )
            if (r.schema, r.table, r.column) in self.column_updates:
                # One sanctioned exception: a BEFORE UPDATE trigger can refuse what a grant
                # permits, which is how `sec_legal_holds` makes a release final. The reason has
                # to say so, because otherwise this branch is a hole somebody can park a false
                # declaration in.
                self.assertIn(
                    "trigger", r.reason,
                    f"{r.schema}.{r.table}.{r.column} is declared unreachable and a runtime "
                    f"role holds a column-scoped UPDATE on exactly it. The database does not "
                    f"refuse to change it -- only a predicate in the service does, which is "
                    f"what this registry exists not to rely on. `write_once` is the mechanism "
                    f"for that. Reason on file: {r.reason}",
                )
                self.assertIn(
                    (r.schema, r.table), self.update_triggers,
                    f"{r.schema}.{r.table}.{r.column}'s reason claims a trigger and the table "
                    f"has no BEFORE UPDATE trigger",
                )

    def test_a_write_once_declaration_really_has_a_grant_behind_it(self):
        """The other direction, so `write_once` cannot become a place to park anything.

        It is the weaker claim -- a service writes the column once and no erasure path clears it
        -- and it is only the right answer when the column genuinely is writable. A column with
        no grant at all is `unreachable`, and saying `write_once` of it understates what the
        database guarantees.
        """
        written = write_once_columns()
        self.assertTrue(written, "if nothing is write_once, delete the mechanism")
        for r in written:
            self.assertIn(
                (r.schema, r.table, r.column), self.column_updates,
                f"{r.schema}.{r.table}.{r.column} is declared write_once and no runtime role "
                f"can write it; it is unreachable, which is a stronger and truer statement",
            )
            self.assertEqual(r.clears, (), f"{r.table}.{r.column} clears nothing")

    def test_the_subject_identifiers_inside_jsonb_are_declared_by_hand(self):
        """The completeness sweep matches column *names*, so a subject id inside a `jsonb`
        payload is invisible to it. `evt_outbox.payload` holds one for five of MOD-010's eight
        wired producers, and a residue report that omitted the newest and largest store of
        subject identifiers in the build would report something untrue. Found by review; named
        here because no sweep can find the next one either.
        """
        declared = {(r.schema, r.table, r.column) for r in SUBJECT_COLUMNS}
        self.assertIn(("plt01", "evt_outbox", "payload"), declared)
        residue = {(r.schema, r.table, r.column) for r in unreachable_columns()}
        self.assertIn(("plt01", "evt_outbox", "payload"), residue,
                      "it has to appear in what a completion report discloses")

    def test_the_pseudonymous_contact_digests_are_declared_by_hand(self):
        """MOD-013 holds a SHA-256 of `channel:address` and never an address, which is what
        keeps a second copy of everyone's email out of this build. It is **pseudonymous and not
        anonymous**: somebody holding a candidate address can test it against the digest. The
        sweep matches names and would never find it, and a residue report that omitted it would
        understate what survives an erasure.
        """
        declared = {(r.schema, r.table, r.column) for r in SUBJECT_COLUMNS}
        residue = {(r.schema, r.table, r.column) for r in unreachable_columns()}
        for table in ("ntf_notifications", "ntf_suppressions"):
            self.assertIn(("plt01", table, "address_digest"), declared)
            self.assertIn(("plt01", table, "address_digest"), residue,
                          "it has to appear in what a completion report discloses")

    def test_the_free_text_a_subject_can_appear_in_is_declared_by_hand(self):
        """The largest hand-declared group in the build, and until a reviewer deleted one of
        these declarations and watched every test pass, it had no pin at all.

        None of these column *names* says "subject", so the completeness sweep cannot find
        them -- they are prose an operator, a provider or a dispatcher writes, and a reviewer
        put an address and a date of birth into one of them and read it back out. MOD-010 and
        MOD-013 each have a named test for their own hand-declared group; this is MOD-018's,
        and it is a pin rather than a heuristic because no sweep will find the next one either.
        """
        declared = {(r.schema, r.table, r.column) for r in SUBJECT_COLUMNS}
        residue = {(r.schema, r.table, r.column) for r in unreachable_columns()}
        prose = {
            ("led_journals", "description"), ("led_journals", "source_ref"),
            ("led_journals", "correction_reason"), ("led_postings", "memo"),
            ("led_wallet_entries", "reason"), ("led_wallet_entries", "source_ref"),
            ("led_settlement_lines", "provider_ref"),
            ("led_settlement_lines", "outcome_reason"),
            ("led_reconciliation_cases", "detail"),
            ("led_reconciliation_cases", "subject_ref"),
            ("led_settlements", "provider_batch_ref"),
            ("led_settlements", "document_ref"),
            ("led_recognition_schedules", "source_ref"),
            ("led_exports", "target_ref"),
        }
        for table, column in sorted(prose):
            self.assertIn(("plt01", table, column), declared,
                          f"{table}.{column} is free text nobody declared")
            self.assertIn(("plt01", table, column), residue,
                          f"{table}.{column} has to appear in a completion report")
        # And the ones a service writes once under a predicate, which is the weaker, truer
        # statement: an erasure does not clear them either.
        write_once = {
            ("led_periods", "reopen_reason"),
            ("led_recognition_schedules", "close_reason"),
            ("led_cash_sessions", "variance_reason"),
            ("led_reconciliation_cases", "resolution"),
            ("led_deposits", "bank_reference"),
        }
        for table, column in sorted(write_once):
            self.assertIn(("plt01", table, column), declared,
                          f"{table}.{column} is free text nobody declared")

    def test_this_build_cannot_fully_erase_a_subject_and_says_so(self):
        """Stated as its own test so the disclosure cannot lapse quietly.

        If the unreachable set ever empties, this fails -- which is the right failure: somebody
        should then delete this test, and the gap note in CLAUDE.md with it.
        """
        from app.privacy.classification import deletion_is_complete

        self.assertFalse(deletion_is_complete())
        self.assertTrue(unreachable_columns())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

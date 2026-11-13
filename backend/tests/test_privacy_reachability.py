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

from app.privacy.classification import MECHANISMS, SUBJECT_COLUMNS

# A column names a natural person if it is one of these, or if it ends in `_by`. The suffix rule
# is deliberately broad: it will one day catch something like `ordered_by` that is not a person,
# and the cost of that is one registry line saying so, which is much cheaper than the cost of
# missing a real one.
SUBJECT_NAMES = frozenset({
    "identity_id", "person_id", "subject_id", "guardian_subject_id",
    "actor_identity_id", "actor_id",
})
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
                  AND (c.column_name = ANY(%s) OR c.column_name LIKE %s)
                """,
                (list(SUBJECT_NAMES), r"%\_by"),
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
        """The other direction: a stale entry would claim coverage of a table that is gone."""
        declared = {(r.schema, r.table, r.column) for r in SUBJECT_COLUMNS}
        stale = sorted(declared - self.live)
        self.assertEqual(stale, [],
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
        """Claiming a row can be emptied is a claim some role can write to it."""
        for r in SUBJECT_COLUMNS:
            if r.mechanism != "anonymize":
                continue
            held = self.grants.get((r.schema, r.table), set())
            self.assertIn(
                "UPDATE", held,
                f"{r.schema}.{r.table}.{r.column} is declared anonymize, but no runtime role "
                f"holds UPDATE on it, so the erasure this promises would fail at run time",
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

        `unreachable` is a statement that the database refuses to change these rows. If a later
        migration grants UPDATE or DELETE on one of them, two things are true at once: erasure
        became possible, and the insert-only guarantee that something else depends on was lost.
        Either way the registry entry is now wrong and somebody has to look at it.
        """
        for r in SUBJECT_COLUMNS:
            if r.mechanism != "unreachable":
                continue
            held = self.grants.get((r.schema, r.table), set())
            self.assertEqual(
                held, set(),
                f"{r.schema}.{r.table}.{r.column} is declared unreachable but a runtime role now "
                f"holds {sorted(held)} on it. Either the grant is a mistake and the insert-only "
                f"property has been lost, or erasure is now possible and this entry should say "
                f"so. Reason on file: {r.reason}",
            )

    def test_this_build_cannot_fully_erase_a_subject_and_says_so(self):
        """Stated as its own test so the disclosure cannot lapse quietly.

        If the unreachable set ever empties, this fails -- which is the right failure: somebody
        should then delete this test, and the gap note in CLAUDE.md with it.
        """
        from app.privacy.classification import deletion_is_complete, unreachable_columns

        self.assertFalse(deletion_is_complete())
        self.assertTrue(unreachable_columns())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

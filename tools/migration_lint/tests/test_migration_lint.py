"""Deterministic tests for the MOD-004 static migration lint.
Run: python3 -m unittest discover -s tools/migration_lint/tests -t tools/migration_lint

Every test writes its SQL to a temporary directory or uses the in-repo corpus read-only; nothing
is written inside the repository. The corpus tests include negative controls: a lint that reports
nothing, a lint that reports everything, and a repaired mutation must each make `corpus` BLOCK.
Without those, a corpus PASS would only show that the corpus runner ran.
"""
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import migration_lint as ml  # noqa: E402

CORPUS = HERE.parent / "corpus"
ALLOWLIST = HERE.parent / ml.DEFAULT_ALLOWLIST

COMPLETE_TENANT_TABLE = """
CREATE TABLE plt01.brand_appearance (
    tenant_id uuid NOT NULL,
    brand_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, brand_id),
    FOREIGN KEY (tenant_id) REFERENCES plt01_platform.tenants (tenant_id)
);
ALTER TABLE plt01.brand_appearance ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.brand_appearance FORCE ROW LEVEL SECURITY;
CREATE POLICY p ON plt01.brand_appearance
    FOR ALL TO veyro_cp_app USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
"""

NEGATIVE_TEST_FIXTURE = (
    "-- veyro_cp_app must read no plt01.brand_appearance row of another tenant\n"
)


class LintCase(unittest.TestCase):
    """Base: lint an SQL string and return the set of rules it produced."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.allowlist, self.views = ml.load_allowlist(ALLOWLIST)

    def rules(self, sql, track="tenant", tests=NEGATIVE_TEST_FIXTURE, allowlist=None, views=None):
        sql_path = self.tmp / "0001.sql"
        sql_path.write_text(sql, encoding="utf-8")
        tests_root = None
        if tests is not None:
            tests_root = self.tmp / "tests"
            tests_root.mkdir(exist_ok=True)
            (tests_root / "negatives.sql").write_text(tests, encoding="utf-8")
        found = ml.lint_file(
            sql_path, track,
            self.allowlist if allowlist is None else allowlist,
            self.views if views is None else views,
            tests_root,
        )
        return {f.rule for f in found}


class TestRuleCatalogue(LintCase):
    def test_every_rule_has_a_reason(self):
        for rule, why in ml.RULES.items():
            self.assertTrue(why.strip(), rule)
            self.assertRegex(rule, r"^[A-Z][A-Z0-9_]*$")

    def test_complete_tenant_table_is_clean(self):
        self.assertEqual(self.rules(COMPLETE_TENANT_TABLE), set())


class TestTenantTableCompleteness(LintCase):
    def test_missing_tenant_id_column(self):
        sql = COMPLETE_TENANT_TABLE.replace("tenant_id uuid NOT NULL,\n", "")
        self.assertIn("TENANT_ID_COLUMN", self.rules(sql))

    def test_missing_rls_enable(self):
        sql = COMPLETE_TENANT_TABLE.replace(
            "ALTER TABLE plt01.brand_appearance ENABLE ROW LEVEL SECURITY;\n", "")
        self.assertEqual(self.rules(sql), {"RLS_ENABLE"})

    def test_missing_rls_force(self):
        sql = COMPLETE_TENANT_TABLE.replace(
            "ALTER TABLE plt01.brand_appearance FORCE ROW LEVEL SECURITY;\n", "")
        self.assertEqual(self.rules(sql), {"RLS_FORCE"})

    def test_missing_policy(self):
        sql = COMPLETE_TENANT_TABLE.split("CREATE POLICY")[0]
        self.assertEqual(self.rules(sql), {"RLS_POLICY"})

    def test_primary_key_must_lead_with_tenant_id(self):
        sql = COMPLETE_TENANT_TABLE.replace("PRIMARY KEY (tenant_id, brand_id)",
                                           "PRIMARY KEY (brand_id, tenant_id)")
        self.assertEqual(self.rules(sql), {"TENANT_LEADING_INDEX"})

    def test_separate_tenant_leading_index_satisfies_the_rule(self):
        sql = COMPLETE_TENANT_TABLE.replace(
            "PRIMARY KEY (tenant_id, brand_id)", "UNIQUE (brand_id)")
        sql += "CREATE INDEX bi ON plt01.brand_appearance (tenant_id, brand_id);\n"
        self.assertEqual(self.rules(sql), set())

    def test_platform_table_needs_no_rls(self):
        sql = ("CREATE TABLE plt01_platform.tenants (tenant_id uuid NOT NULL PRIMARY KEY);\n")
        self.assertEqual(self.rules(sql, track="platform"), set())


class TestNegativeTests(LintCase):
    def test_absent_tests_tree_is_a_finding_not_a_skip(self):
        self.assertEqual(self.rules(COMPLETE_TENANT_TABLE, tests=None), {"NEGATIVE_TESTS"})

    def test_test_naming_the_table_but_no_runtime_role_is_not_enough(self):
        self.assertEqual(
            self.rules(COMPLETE_TENANT_TABLE, tests="-- touches plt01.brand_appearance\n"),
            {"NEGATIVE_TESTS"})

    def test_test_naming_a_runtime_role_but_not_the_table_is_not_enough(self):
        self.assertEqual(self.rules(COMPLETE_TENANT_TABLE, tests="-- veyro_cp_app denied\n"),
                         {"NEGATIVE_TESTS"})


class TestGrants(LintCase):
    def test_truncate_to_runtime_role(self):
        self.assertEqual(self.rules("GRANT TRUNCATE ON plt01.brand_appearance TO veyro_cp_app;"),
                         {"RUNTIME_TRUNCATE_OR_REFERENCES"})

    def test_references_to_runtime_role(self):
        self.assertEqual(
            self.rules("GRANT REFERENCES ON plt01.brand_appearance TO veyro_cp_worker;"),
            {"RUNTIME_TRUNCATE_OR_REFERENCES"})

    def test_all_privileges_to_runtime_role_includes_truncate(self):
        self.assertIn("RUNTIME_TRUNCATE_OR_REFERENCES",
                      self.rules("GRANT ALL ON plt01.brand_appearance TO veyro_cp_app;"))

    def test_references_to_the_migrator_is_the_permitted_exception(self):
        self.assertEqual(
            self.rules("GRANT REFERENCES (tenant_id) ON plt01_platform.tenants "
                       "TO veyro_cp_migrator;", track="platform"),
            set())

    def test_public_table_grant(self):
        self.assertEqual(self.rules("GRANT SELECT ON plt01.brand_appearance TO PUBLIC;"),
                         {"PUBLIC_GRANT"})

    def test_public_connect_on_database(self):
        self.assertEqual(self.rules("GRANT CONNECT ON DATABASE veyro_cp TO PUBLIC;",
                                    track="platform"),
                         {"PUBLIC_DATABASE_PRIVILEGE"})

    def test_public_non_connect_database_grant_is_still_a_public_grant(self):
        self.assertEqual(self.rules("GRANT CREATE ON DATABASE veyro_cp TO PUBLIC;",
                                    track="platform"),
                         {"PUBLIC_GRANT"})

    def test_revoke_from_public_is_the_safe_pattern(self):
        self.assertEqual(
            self.rules("REVOKE CONNECT, TEMPORARY ON DATABASE veyro_cp FROM PUBLIC;",
                       track="platform"),
            set())

    def test_default_privileges_grant_to_public(self):
        self.assertEqual(
            self.rules("ALTER DEFAULT PRIVILEGES IN SCHEMA plt01 "
                       "GRANT EXECUTE ON FUNCTIONS TO PUBLIC;"),
            {"DEFAULT_PRIVILEGES_GRANT"})

    def test_default_privileges_revoke_is_allowed(self):
        self.assertEqual(
            self.rules("ALTER DEFAULT PRIVILEGES IN SCHEMA plt01 "
                       "REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;"),
            set())

    def test_delete_on_append_only_history(self):
        # Two rules, both correct: the table is append-only, and D6.2 bars DELETE to this role on
        # any table ("no DELETE, TRUNCATE, REFERENCES or TRIGGER").
        self.assertEqual(
            self.rules("GRANT SELECT, DELETE ON plt01.brand_appearance_history "
                       "TO veyro_cp_app;"),
            {"APPEND_ONLY_WRITE_GRANT", "RUNTIME_TRUNCATE_OR_REFERENCES"})

    def test_update_on_append_only_history_is_the_append_only_rule_alone(self):
        self.assertEqual(
            self.rules("GRANT SELECT, UPDATE ON plt01.brand_appearance_history "
                       "TO veyro_cp_app;"),
            {"APPEND_ONLY_WRITE_GRANT"})

    def test_delete_to_the_app_role_is_barred_by_d62(self):
        self.assertEqual(self.rules("GRANT DELETE ON plt01.brand_appearance TO veyro_cp_app;"),
                         {"RUNTIME_TRUNCATE_OR_REFERENCES"})

    def test_trigger_to_the_app_role_is_barred_by_d62(self):
        self.assertEqual(self.rules("GRANT TRIGGER ON plt01.brand_appearance TO veyro_cp_app;"),
                         {"RUNTIME_TRUNCATE_OR_REFERENCES"})

    def test_insert_only_on_append_only_history_is_allowed(self):
        self.assertEqual(
            self.rules("GRANT SELECT, INSERT ON plt01.brand_appearance_history "
                       "TO veyro_cp_app;"),
            set())

    def test_delete_on_the_idempotency_table(self):
        self.assertEqual(
            self.rules("GRANT DELETE ON plt01.command_idempotency TO veyro_cp_app;"),
            {"APPEND_ONLY_WRITE_GRANT", "RUNTIME_TRUNCATE_OR_REFERENCES"})


class TestViews(LintCase):
    def test_view_without_security_invoker(self):
        self.assertEqual(self.rules("CREATE VIEW plt01.v AS SELECT 1 AS n;"),
                         {"VIEW_NOT_SECURITY_INVOKER"})

    def test_view_over_a_tenant_table_is_banned_by_default(self):
        self.assertEqual(
            self.rules("CREATE VIEW plt01.v WITH (security_invoker = true) AS "
                       "SELECT tenant_id FROM plt01.brand_appearance;"),
            {"VIEW_OVER_TENANT_TABLE"})

    def test_allowlisted_view_over_a_tenant_table_passes(self):
        self.assertEqual(
            self.rules("CREATE VIEW plt01.v WITH (security_invoker = true) AS "
                       "SELECT tenant_id FROM plt01.brand_appearance;",
                       views={"plt01.v"}),
            set())


class TestSecurityDefiner(LintCase):
    DEFINER = (
        "CREATE FUNCTION plt01_api.provision_tenant(p_key text) RETURNS uuid "
        "LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, plt01_platform, pg_temp "
        "AS $fn$ BEGIN RETURN gen_random_uuid(); END; $fn$;"
    )

    def test_unlisted_definer(self):
        self.assertEqual(self.rules(self.DEFINER, track="platform"),
                         {"SECURITY_DEFINER_UNLISTED"})

    def test_allowlisted_definer_passes(self):
        entry = {"function": "plt01_api.provision_tenant(text)", "owner": "veyro_cp_platform",
                 "search_path": "pg_catalog, plt01_platform, pg_temp",
                 "execute_grantees": ["veyro_cp_app"], "review_id": "VR-TEST-001"}
        self.assertEqual(
            self.rules(self.DEFINER, track="platform",
                       allowlist={"plt01_api.provision_tenant": entry}),
            set())

    def test_definer_without_pinned_search_path(self):
        sql = self.DEFINER.replace("SET search_path = pg_catalog, plt01_platform, pg_temp ", "")
        self.assertEqual(self.rules(sql, track="platform"),
                         {"SECURITY_DEFINER_UNLISTED", "SECURITY_DEFINER_SEARCH_PATH"})

    def test_definer_with_pg_temp_before_pg_catalog(self):
        sql = self.DEFINER.replace("pg_catalog, plt01_platform, pg_temp",
                                   "pg_temp, pg_catalog, plt01_platform")
        self.assertEqual(self.rules(sql, track="platform"),
                         {"SECURITY_DEFINER_UNLISTED", "SECURITY_DEFINER_SEARCH_PATH"})

    def test_security_invoker_function_needs_no_allowlist_entry(self):
        sql = self.DEFINER.replace("SECURITY DEFINER ", "")
        self.assertEqual(self.rules(sql, track="platform"), set())

    def test_forbidden_function_class(self):
        sql = ("CREATE FUNCTION plt01_api.archive_tenant(p uuid) RETURNS void "
               "LANGUAGE sql AS $fn$ SELECT 1 $fn$;")
        self.assertEqual(self.rules(sql, track="platform"), {"FORBIDDEN_FUNCTION_CLASS"})


class TestSessionContext(LintCase):
    def test_session_set(self):
        self.assertEqual(self.rules("SET app.tenant_id = 'x';"), {"SESSION_CONTEXT_SET"})

    def test_set_session(self):
        self.assertEqual(self.rules("SET SESSION app.tenant_id = 'x';"), {"SESSION_CONTEXT_SET"})

    def test_set_local_is_the_approved_form(self):
        self.assertEqual(self.rules("SET LOCAL app.tenant_id = 'x';"), set())

    def test_set_config_false(self):
        self.assertEqual(self.rules("SELECT set_config('app.tenant_id', 'x', false);"),
                         {"SESSION_CONTEXT_SET"})

    def test_set_config_true_is_the_approved_form(self):
        self.assertEqual(self.rules("SELECT set_config('app.tenant_id', 'x', true);"), set())

    def test_set_config_false_with_a_cast_does_not_evade(self):
        # Regression: a `, false)` regex missed `false::boolean`, which is the same session-level
        # set. The rule now requires the third argument to be the literal `true`.
        self.assertEqual(self.rules("SELECT set_config('app.tenant_id','x', false::boolean);"),
                         {"SESSION_CONTEXT_SET"})

    def test_set_config_with_an_expression_does_not_evade(self):
        self.assertEqual(self.rules("SELECT set_config('app.tenant_id','x', (1=0));"),
                         {"SESSION_CONTEXT_SET"})

    def test_set_config_with_a_non_literal_setting_name_is_a_finding(self):
        self.assertEqual(self.rules("SELECT set_config(v_name, 'x', true);"),
                         {"SESSION_CONTEXT_SET"})

    def test_set_config_with_wrong_arity_is_a_finding(self):
        self.assertEqual(self.rules("SELECT set_config('app.tenant_id', 'x');"),
                         {"SESSION_CONTEXT_SET"})

    def test_set_config_on_a_non_app_setting_is_not_this_rule(self):
        self.assertEqual(self.rules("SELECT set_config('statement_timeout', '5s', false);"), set())

    def test_current_setting_is_not_a_set(self):
        self.assertEqual(self.rules("SELECT current_setting('app.tenant_id', false);"), set())

    def test_alter_role_set_app_default(self):
        self.assertEqual(self.rules("ALTER ROLE veyro_cp_app SET app.tenant_id = 'x';",
                                    track="platform"),
                         {"SESSION_CONTEXT_SET"})

    def test_alter_database_set_app_default(self):
        self.assertEqual(self.rules("ALTER DATABASE veyro_cp SET app.tenant_id = 'x';",
                                    track="platform"),
                         {"SESSION_CONTEXT_SET"})

    def test_ban_inside_a_dollar_quoted_function_body_is_caught(self):
        sql = ("CREATE FUNCTION plt01_api.f() RETURNS void LANGUAGE plpgsql AS $fn$ BEGIN "
               "PERFORM set_config('app.tenant_id', 'x', false); END; $fn$;")
        self.assertEqual(self.rules(sql, track="platform"), {"SESSION_CONTEXT_SET"})

    def test_commented_out_ban_is_not_a_finding(self):
        self.assertEqual(self.rules("-- SET app.tenant_id = 'x';\nSELECT 1;"), set())

    def test_ban_inside_a_block_comment_is_not_a_finding(self):
        self.assertEqual(self.rules("/* SET app.tenant_id = 'x'; */ SELECT 1;"), set())

    def test_nested_block_comment_is_consumed_whole(self):
        sql = "/* outer /* inner */ SET app.tenant_id = 'x'; */ SELECT 1;"
        self.assertEqual(self.rules(sql), set())

    def test_ban_inside_a_string_literal_is_a_finding(self):
        # Deliberate and fail-closed: a literal holding `SET app.` is the dynamic-SQL evasion
        # route (`EXECUTE 'SET app...'`), and D6.3 admits no dynamic SQL. D5 bans the session-level
        # set "with no exception", so the lint does not try to decide whether a literal is inert.
        self.assertEqual(self.rules("SELECT 'SET app.tenant_id = 1';"), {"SESSION_CONTEXT_SET"})

    def test_execute_of_a_session_set_is_a_finding(self):
        sql = ("CREATE FUNCTION plt01_api.f() RETURNS void LANGUAGE plpgsql AS $fn$ BEGIN "
               "EXECUTE 'SET app.tenant_id = ''x'''; END; $fn$;")
        # Two findings, and both are wanted: the quoted ban is caught by the session rule, and the
        # EXECUTE itself is caught by DYNAMIC_SQL, which is what closes the whole dynamic route.
        self.assertEqual(self.rules(sql, track="platform"),
                         {"SESSION_CONTEXT_SET", "DYNAMIC_SQL"})

    def test_an_unrelated_string_literal_is_clean(self):
        self.assertEqual(self.rules("SELECT 'tenant settings changed';"), set())


class TestRoleMembership(LintCase):
    def test_role_membership_grant(self):
        self.assertEqual(self.rules("GRANT veyro_cp_platform TO veyro_cp_app;", track="platform"),
                         {"ROLE_MEMBERSHIP_GRANT"})

    def test_privilege_grant_is_not_a_membership_grant(self):
        self.assertNotIn("ROLE_MEMBERSHIP_GRANT",
                         self.rules("GRANT USAGE ON SCHEMA plt01_platform TO veyro_cp_migrator;",
                                    track="platform"))


class TestTracks(LintCase):
    def test_tenant_track_may_not_alter_a_platform_table(self):
        self.assertEqual(self.rules("ALTER TABLE plt01_platform.tenants ADD COLUMN plan text;"),
                         {"TENANT_TRACK_PLATFORM_OBJECT"})

    def test_tenant_track_may_declare_the_permitted_foreign_key(self):
        self.assertEqual(self.rules(COMPLETE_TENANT_TABLE), set())

    def test_tenant_track_may_not_reach_another_platform_object(self):
        self.assertIn("TENANT_TRACK_PLATFORM_OBJECT",
                      self.rules("SELECT * FROM plt01_platform.tenant_placement;"))

    def test_platform_track_may_not_create_a_tenant_table(self):
        self.assertEqual(self.rules(COMPLETE_TENANT_TABLE, track="platform"),
                         {"PLATFORM_TRACK_TENANT_TABLE"})

    def test_platform_track_may_create_its_own_table(self):
        self.assertEqual(
            self.rules("CREATE TABLE plt01_platform.tenant_placement (tenant_id uuid NOT NULL);",
                       track="platform"),
            set())


class TestBrandTheme(LintCase):
    def test_brandtheme_column_on_a_plt01_object(self):
        self.assertEqual(self.rules("ALTER TABLE plt01.brand_appearance ADD COLUMN "
                                    "brand_theme_id uuid;"),
                         {"BRANDTHEME_OBJECT"})

    def test_brand_appearance_is_the_permitted_name(self):
        self.assertEqual(self.rules("ALTER TABLE plt01.brand_appearance ADD COLUMN accent text;"),
                         set())


class TestEvasionRegressions(LintCase):
    """One test per evasion an independent review demonstrated against the first version.

    Every case here passed the lint clean before the fix. They are kept as a block, named after
    what each one slipped past, because the defect was not sixteen unrelated bugs: every rule was
    written against one canonical spelling, and the corpus only ever required one spelling to
    fire.
    """

    def test_do_block_hides_every_other_rule(self):
        # Was CLEAN while granting TRUNCATE, creating a membership edge, creating an unprotected
        # tenant table and granting to PUBLIC. _scan blanks dollar-quoted bodies out of the text
        # the statement rules read, so the construct is refused rather than parsed.
        sql = ("DO $mig$ BEGIN "
               "EXECUTE 'GRANT TRUNCATE ON plt01.brand_appearance TO veyro_cp_app'; "
               "EXECUTE 'CREATE TABLE plt01.naked (id uuid)'; END $mig$;")
        self.assertEqual(self.rules(sql), {"DYNAMIC_SQL"})

    def test_execute_in_a_function_body_is_dynamic_sql(self):
        sql = ("CREATE FUNCTION plt01_api.f() RETURNS void LANGUAGE plpgsql AS $fn$ BEGIN "
               "EXECUTE 'GRANT SELECT ON plt01.brand_appearance TO PUBLIC'; END; $fn$;")
        self.assertEqual(self.rules(sql, track="platform"), {"DYNAMIC_SQL"})

    def test_execute_as_a_privilege_name_is_not_dynamic_sql(self):
        self.assertEqual(
            self.rules("GRANT EXECUTE ON FUNCTION plt01_api.provision_tenant(text) "
                       "TO veyro_cp_app;", track="platform"),
            set())

    def test_revoke_execute_on_functions_is_not_dynamic_sql(self):
        # The platform baseline uses this line; the first DYNAMIC_SQL rule flagged it.
        self.assertEqual(
            self.rules("ALTER DEFAULT PRIVILEGES IN SCHEMA plt01_api "
                       "REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;", track="platform"),
            set())

    def test_permissive_policy_using_true(self):
        self.assertEqual(
            self.rules(COMPLETE_TENANT_TABLE.replace(
                "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)",
                "USING (true) WITH CHECK (true)")),
            {"PERMISSIVE_POLICY"})

    def test_permissive_policy_or_true(self):
        self.assertEqual(
            self.rules(COMPLETE_TENANT_TABLE.replace(
                "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)",
                "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid OR true)")),
            {"PERMISSIVE_POLICY"})

    def test_permissive_policy_without_a_tenant_predicate(self):
        self.assertEqual(
            self.rules(COMPLETE_TENANT_TABLE.replace(
                "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)",
                "USING (brand_id IS NOT NULL)")),
            {"PERMISSIVE_POLICY"})

    def test_permissive_policy_to_public(self):
        self.assertEqual(
            self.rules(COMPLETE_TENANT_TABLE.replace("TO veyro_cp_app", "TO PUBLIC")),
            {"PERMISSIVE_POLICY"})

    def test_alter_policy_can_make_a_policy_permissive(self):
        self.assertEqual(
            self.rules("ALTER POLICY p ON plt01.brand_appearance USING (true);"),
            {"PERMISSIVE_POLICY"})

    def test_good_policy_predicate_is_clean(self):
        # Guards the inverse of the above: the check reads the uncommented text, because _scan
        # blanks the 'app.tenant_id' literal out of the masked text and every policy then reads as
        # unrestricted. The clean baseline caught that.
        self.assertEqual(self.rules(COMPLETE_TENANT_TABLE), set())

    def test_protection_removed_disable_rls(self):
        self.assertEqual(self.rules("ALTER TABLE plt01.brand_appearance "
                                    "DISABLE ROW LEVEL SECURITY;"),
                         {"PROTECTION_REMOVED"})

    def test_protection_removed_no_force(self):
        self.assertEqual(self.rules("ALTER TABLE plt01.brand_appearance "
                                    "NO FORCE ROW LEVEL SECURITY;"),
                         {"PROTECTION_REMOVED"})

    def test_protection_removed_drop_policy(self):
        self.assertEqual(self.rules("DROP POLICY p ON plt01.brand_appearance;"),
                         {"PROTECTION_REMOVED"})

    def test_protection_removed_drop_tenant_id(self):
        self.assertEqual(self.rules("ALTER TABLE plt01.brand_appearance DROP COLUMN tenant_id;"),
                         {"PROTECTION_REMOVED"})

    def test_enable_then_disable_in_one_file_is_a_finding(self):
        sql = COMPLETE_TENANT_TABLE + \
            "ALTER TABLE plt01.brand_appearance DISABLE ROW LEVEL SECURITY;\n"
        self.assertIn("PROTECTION_REMOVED", self.rules(sql))

    def test_role_membership_comma_list(self):
        self.assertEqual(
            self.rules("GRANT veyro_cp_platform, veyro_cp_migrator TO veyro_cp_app;",
                       track="platform"),
            {"ROLE_MEMBERSHIP_GRANT"})

    def test_role_membership_granted_by(self):
        self.assertEqual(
            self.rules("GRANT veyro_cp_platform TO veyro_cp_app "
                       "GRANTED BY veyro_cp_bootstrap;", track="platform"),
            {"ROLE_MEMBERSHIP_GRANT"})

    def test_column_level_references_to_a_runtime_role(self):
        self.assertEqual(
            self.rules("GRANT REFERENCES (tenant_id) ON plt01.brand_appearance "
                       "TO veyro_cp_app;"),
            {"RUNTIME_TRUNCATE_OR_REFERENCES"})

    def test_column_level_update_on_append_only(self):
        self.assertEqual(
            self.rules("GRANT UPDATE (accent_color) ON plt01.brand_appearance_history "
                       "TO veyro_cp_app;"),
            {"APPEND_ONLY_WRITE_GRANT"})

    def test_column_level_references_to_the_migrator_stays_clean(self):
        # This is the exact spelling the platform baseline uses for D6.1 item 4's exception.
        self.assertEqual(
            self.rules("GRANT REFERENCES (tenant_id) ON plt01_platform.tenants "
                       "TO veyro_cp_migrator;", track="platform"),
            set())

    def test_schema_wide_write_grant_reaches_append_only_tables(self):
        self.assertEqual(
            self.rules("GRANT UPDATE ON ALL TABLES IN SCHEMA plt01 TO veyro_cp_app;"),
            {"APPEND_ONLY_WRITE_GRANT"})

    def test_quoted_dotted_guc_name(self):
        self.assertEqual(self.rules('SET "app"."tenant_id" = \'x\';'),
                         {"SESSION_CONTEXT_SET"})

    def test_quoted_whole_guc_name(self):
        self.assertEqual(self.rules('SET "app.tenant_id" = \'x\';'),
                         {"SESSION_CONTEXT_SET"})

    def test_quoted_guc_in_alter_role(self):
        self.assertEqual(self.rules('ALTER ROLE veyro_cp_app SET "app"."tenant_id" = \'x\';',
                                    track="platform"),
                         {"SESSION_CONTEXT_SET"})

    def test_alter_function_can_make_a_function_security_definer(self):
        self.assertEqual(
            self.rules("ALTER FUNCTION plt01_api.resolve_placement(uuid) SECURITY DEFINER;",
                       track="platform"),
            {"SECURITY_DEFINER_UNLISTED", "SECURITY_DEFINER_SEARCH_PATH"})

    def test_alter_function_can_reset_a_pinned_search_path(self):
        self.assertEqual(
            self.rules("ALTER FUNCTION plt01_api.resolve_placement(uuid) RESET search_path;",
                       track="platform"),
            {"SECURITY_DEFINER_SEARCH_PATH"})

    def test_allowlisted_search_path_must_match_the_sql(self):
        entry = {"function": "plt01_api.provision_tenant(text)", "owner": "veyro_cp_platform",
                 "search_path": "pg_catalog, plt01_platform, pg_temp",
                 "execute_grantees": ["veyro_cp_app"], "review_id": "VR-TEST-001"}
        sql = TestSecurityDefiner.DEFINER.replace("pg_catalog, plt01_platform, pg_temp",
                                                  "pg_catalog, public")
        self.assertEqual(
            self.rules(sql, track="platform",
                       allowlist={"plt01_api.provision_tenant": entry}),
            {"SECURITY_DEFINER_SEARCH_PATH"})

    def test_view_over_a_tenant_table_via_comma_join(self):
        self.assertEqual(
            self.rules("CREATE VIEW plt01.v WITH (security_invoker = true) AS "
                       "SELECT b.tenant_id FROM pg_catalog.pg_class c, plt01.brand_appearance b;"),
            {"VIEW_OVER_TENANT_TABLE"})

    def test_view_over_an_unqualified_tenant_table_via_comma_join(self):
        self.assertEqual(
            self.rules("CREATE VIEW plt01.v WITH (security_invoker = true) AS "
                       "SELECT x.tenant_id FROM pg_class c, brand_appearance x;"),
            {"VIEW_OVER_TENANT_TABLE"})

    def test_view_over_a_tenant_table_via_as_table(self):
        self.assertEqual(
            self.rules("CREATE VIEW plt01.v WITH (security_invoker = true) AS "
                       "TABLE plt01.brand_appearance;"),
            {"VIEW_OVER_TENANT_TABLE"})

    def test_view_over_a_tenant_table_via_cte(self):
        self.assertEqual(
            self.rules("CREATE VIEW plt01.v WITH (security_invoker = true) AS "
                       "WITH c AS (SELECT * FROM plt01.brand_appearance) SELECT * FROM c;"),
            {"VIEW_OVER_TENANT_TABLE"})

    def test_view_over_nothing_does_not_trip_the_tenant_table_rule(self):
        # The inverse guard: an earlier version captured every identifier, so the bare alias in
        # `SELECT 1 AS n` was read as an unqualified tenant table.
        self.assertEqual(self.rules("CREATE VIEW plt01.v AS SELECT 1 AS n;"),
                         {"VIEW_NOT_SECURITY_INVOKER"})

    def test_alter_view_can_turn_security_invoker_off(self):
        self.assertEqual(
            self.rules("ALTER VIEW plt01.v SET (security_invoker = false);"),
            {"VIEW_NOT_SECURITY_INVOKER"})

    def test_tenant_id_must_be_uuid(self):
        sql = COMPLETE_TENANT_TABLE.replace("tenant_id uuid NOT NULL", "tenant_id text NOT NULL")
        self.assertEqual(self.rules(sql), {"TENANT_ID_COLUMN"})

    def test_tenant_id_must_be_not_null(self):
        sql = COMPLETE_TENANT_TABLE.replace("tenant_id uuid NOT NULL,", "tenant_id uuid,")
        sql = sql.replace("PRIMARY KEY (tenant_id, brand_id)", "UNIQUE (tenant_id, brand_id)")
        self.assertEqual(self.rules(sql), {"TENANT_ID_COLUMN"})

    def test_tenant_id_in_a_tenant_leading_primary_key_is_implicitly_not_null(self):
        sql = COMPLETE_TENANT_TABLE.replace("tenant_id uuid NOT NULL,", "tenant_id uuid,")
        self.assertEqual(self.rules(sql), set())

    def test_migration_may_not_set_search_path(self):
        self.assertEqual(self.rules("SET search_path = plt01_platform;"),
                         {"MIGRATION_SEARCH_PATH"})

    def test_set_local_search_path_is_also_a_finding(self):
        self.assertEqual(self.rules("SET LOCAL search_path = plt01_platform, plt01;"),
                         {"MIGRATION_SEARCH_PATH"})

    def test_platform_track_may_not_create_a_table_in_another_schema(self):
        self.assertEqual(
            self.rules("CREATE TABLE plt01x.leaky (tenant_id uuid NOT NULL, data text);",
                       track="platform"),
            {"PLATFORM_TRACK_TENANT_TABLE"})

    def test_foreign_table_is_still_a_table(self):
        self.assertIn("TENANT_ID_COLUMN",
                      self.rules("CREATE FOREIGN TABLE plt01.remote (data text) SERVER s;"))

    def test_bare_brand_theme_table_name(self):
        self.assertEqual(
            self.rules("CREATE TABLE brand_theme (tenant_id uuid NOT NULL, "
                       "PRIMARY KEY (tenant_id));\n"
                       "ALTER TABLE brand_theme ENABLE ROW LEVEL SECURITY;\n"
                       "ALTER TABLE brand_theme FORCE ROW LEVEL SECURITY;\n"
                       "CREATE POLICY p ON brand_theme FOR ALL TO veyro_cp_app "
                       "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);",
                       tests="-- veyro_cp_app denied on brand_theme\n"),
            {"BRANDTHEME_OBJECT"})

    def test_create_brand_theme_function_name(self):
        self.assertEqual(
            self.rules("CREATE FUNCTION plt01_api.create_brand_theme() RETURNS void "
                       "LANGUAGE sql AS $fn$ SELECT 1 $fn$;", track="platform"),
            {"BRANDTHEME_OBJECT"})

    def test_brandtheme_in_a_data_literal_is_not_an_object(self):
        # The inverse guard: the rule used to match two independent substrings anywhere in the
        # statement, so an INSERT of a feature-flag name tripped it.
        self.assertEqual(
            self.rules("INSERT INTO plt01.config (k, v) VALUES ('brandtheme_enabled', 'false');"),
            set())

    def test_remove_tenant_is_a_forbidden_function_name(self):
        self.assertEqual(
            self.rules("CREATE FUNCTION plt01_api.remove_tenant(p uuid) RETURNS void "
                       "LANGUAGE sql AS $fn$ SELECT 1 $fn$;", track="platform"),
            {"FORBIDDEN_FUNCTION_CLASS"})

    def test_unique_constraint_counts_as_a_tenant_leading_index(self):
        sql = COMPLETE_TENANT_TABLE.replace("PRIMARY KEY (tenant_id, brand_id)",
                                            "UNIQUE (tenant_id, brand_id)")
        self.assertEqual(self.rules(sql), set())

    def test_added_unique_constraint_counts_too(self):
        self.assertEqual(
            self.rules("ALTER TABLE plt01.brand_appearance "
                       "ADD CONSTRAINT u UNIQUE (tenant_id, brand_id);"),
            set())

    def test_added_primary_key_beside_another_clause(self):
        # _paren_body used to take the FIRST paren group, so this read the column type (10,2).
        sql = COMPLETE_TENANT_TABLE.replace("    PRIMARY KEY (tenant_id, brand_id),\n", "")
        sql += ("ALTER TABLE plt01.brand_appearance ADD COLUMN fee numeric(10,2), "
                "ADD PRIMARY KEY (tenant_id, brand_id);\n")
        self.assertEqual(self.rules(sql), set())


class TestRoundTwoRegressions(LintCase):
    """One test per evasion a second independent review demonstrated.

    The first review found sixteen single-spelling holes. These are what the remediation for those
    sixteen left open, or introduced. The pair `test_adr_prescribed_policy_predicate_is_clean` and
    `test_or_arithmetic_true_is_a_bypass` is the important one: the rule was simultaneously
    over-inclusive on the predicate ADR-0002 D3 actually prescribes and under-inclusive on the
    bypass D3 names, which is why it was rewritten to read the body as a conjunction.
    """

    def test_adr_prescribed_policy_predicate_is_clean(self):
        # ADR-0002 D3 line 63 prescribes exactly this. The previous rule rejected it, because the
        # `true` is current_setting's missing_ok argument -- the thing that produces D3's
        # fail-closed contract -- and the whole corpus had quietly adopted a different predicate.
        self.assertEqual(self.rules(COMPLETE_TENANT_TABLE), set())

    def test_or_arithmetic_true_is_a_bypass(self):
        sql = COMPLETE_TENANT_TABLE.replace(
            "NULLIF(current_setting('app.tenant_id', true), '')::uuid)",
            "NULLIF(current_setting('app.tenant_id', true), '')::uuid OR 1=1)")
        self.assertEqual(self.rules(sql), {"PERMISSIVE_POLICY"})

    def test_or_any_disjunct_is_a_bypass(self):
        sql = COMPLETE_TENANT_TABLE.replace(
            "NULLIF(current_setting('app.tenant_id', true), '')::uuid)",
            "NULLIF(current_setting('app.tenant_id', true), '')::uuid "
            "OR current_setting('app.is_admin', true)::boolean)")
        self.assertEqual(self.rules(sql), {"PERMISSIVE_POLICY"})

    def test_tenant_id_compared_to_itself_is_not_a_tenant_predicate(self):
        sql = COMPLETE_TENANT_TABLE.replace(
            "NULLIF(current_setting('app.tenant_id', true), '')::uuid)", "tenant_id)")
        self.assertEqual(self.rules(sql), {"PERMISSIVE_POLICY"})

    def test_narrowing_conjuncts_are_clean(self):
        # AND can only narrow, and an OR inside a conjunct's own parentheses cannot widen the
        # whole predicate, so neither is a finding.
        sql = COMPLETE_TENANT_TABLE.replace(
            "NULLIF(current_setting('app.tenant_id', true), '')::uuid)",
            "NULLIF(current_setting('app.tenant_id', true), '')::uuid "
            "AND is_active = true AND (kind = 'a' OR kind = 'b'))")
        self.assertEqual(self.rules(sql), set())

    def test_redundant_outer_parentheses_are_clean(self):
        sql = COMPLETE_TENANT_TABLE.replace(
            "USING (NULLIF", "USING ((NULLIF").replace("::uuid);", "::uuid));")
        self.assertEqual(self.rules(sql), set())

    def test_with_grant_option_does_not_hide_the_grantee(self):
        # One suffix used to defeat four rules at once, because the grantee parsed as the single
        # token "veyro_cp_app with grant option".
        self.assertEqual(
            self.rules("GRANT TRUNCATE ON plt01.brand_appearance TO veyro_cp_app "
                       "WITH GRANT OPTION;"),
            {"RUNTIME_TRUNCATE_OR_REFERENCES"})

    def test_with_grant_option_does_not_hide_public(self):
        self.assertEqual(
            self.rules("GRANT SELECT ON plt01.brand_appearance TO PUBLIC WITH GRANT OPTION;"),
            {"PUBLIC_GRANT"})

    def test_unprotected_tenant_table_in_a_third_schema(self):
        # Was CLEAN: a table in neither plt01 nor a platform schema was not a tenant table at all,
        # so no rule in the file objected to it having no RLS, no policy and a text tenant_id.
        found = self.rules("CREATE TABLE plt01_v2.brand_appearance "
                           "(id uuid PRIMARY KEY, tenant_id text);")
        for rule in ("TENANT_ID_COLUMN", "RLS_ENABLE", "RLS_FORCE", "RLS_POLICY",
                     "TENANT_LEADING_INDEX"):
            self.assertIn(rule, found)

    def test_protected_tenant_table_in_a_third_schema_is_clean(self):
        sql = COMPLETE_TENANT_TABLE.replace("plt01.brand_appearance", "plt01_v2.brand_appearance")
        self.assertEqual(self.rules(sql), set())

    def test_ownership_transfer_to_a_runtime_role(self):
        # D1.1 [SRC]: runtime roles do not own tenant tables. An owner can disable RLS on its own
        # table, so this is protection removal in effect.
        self.assertEqual(self.rules("ALTER TABLE plt01.brand_appearance OWNER TO veyro_cp_app;"),
                         {"PROTECTION_REMOVED"})

    def test_ownership_transfer_to_the_migrator_is_clean(self):
        self.assertEqual(
            self.rules("ALTER TABLE plt01.brand_appearance OWNER TO veyro_cp_migrator;"),
            set())

    def test_drop_column_keyword_is_optional(self):
        self.assertEqual(self.rules("ALTER TABLE plt01.brand_appearance DROP tenant_id;"),
                         {"PROTECTION_REMOVED"})

    def test_dropping_not_null_from_tenant_id(self):
        self.assertEqual(
            self.rules("ALTER TABLE plt01.brand_appearance "
                       "ALTER COLUMN tenant_id DROP NOT NULL;"),
            {"PROTECTION_REMOVED"})

    def test_alter_view_reset_turns_security_invoker_off(self):
        # RESET restores the default, which is false. ALTER FUNCTION ... RESET search_path was
        # already handled, so this was the same omission one rule over.
        self.assertEqual(self.rules("ALTER VIEW plt01.v RESET (security_invoker);"),
                         {"VIEW_NOT_SECURITY_INVOKER"})

    def test_single_quoted_function_body_is_scanned(self):
        sql = ("CREATE FUNCTION plt01_api.touch() RETURNS void LANGUAGE plpgsql "
               "AS 'BEGIN EXECUTE ''ALTER TABLE plt01.brand_appearance "
               "DISABLE ROW LEVEL SECURITY''; END';")
        self.assertEqual(self.rules(sql, track="platform"), {"DYNAMIC_SQL"})

    def test_static_ddl_inside_a_function_body_is_refused(self):
        sql = ("CREATE FUNCTION plt01_api.f() RETURNS void LANGUAGE plpgsql AS $fn$ BEGIN "
               "ALTER TABLE plt01.brand_appearance DISABLE ROW LEVEL SECURITY; END $fn$;")
        self.assertEqual(self.rules(sql, track="platform"), {"DYNAMIC_SQL"})

    def test_a_quoted_body_without_ddl_or_execute_is_clean(self):
        self.assertEqual(
            self.rules("CREATE FUNCTION plt01_api.pure() RETURNS integer LANGUAGE sql "
                       "AS 'SELECT 1';", track="platform"),
            set())

    def test_quoted_identifier_is_a_different_table(self):
        # PostgreSQL folds an unquoted name to lower case and preserves a quoted one, so
        # plt01."T" and plt01.t are two tables. Lower-casing both merged them, and a file could
        # create an unprotected "T" while protecting t.
        sql = ('CREATE TABLE plt01."T" (tenant_id uuid NOT NULL, PRIMARY KEY (tenant_id));\n'
               "ALTER TABLE plt01.t ENABLE ROW LEVEL SECURITY;\n"
               "ALTER TABLE plt01.t FORCE ROW LEVEL SECURITY;\n"
               "CREATE POLICY p ON plt01.t FOR ALL TO veyro_cp_app "
               "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);")
        for rule in ("RLS_ENABLE", "RLS_FORCE", "RLS_POLICY"):
            self.assertIn(rule, self.rules(sql, tests="-- veyro_cp_app denied on T\n"))

    def test_search_path_via_set_config(self):
        self.assertEqual(self.rules("SELECT set_config('search_path', 'plt01', false);"),
                         {"MIGRATION_SEARCH_PATH"})

    def test_search_path_via_alter_role(self):
        self.assertEqual(
            self.rules("ALTER ROLE veyro_cp_app SET search_path = plt01;", track="platform"),
            {"MIGRATION_SEARCH_PATH"})

    def test_view_over_a_set_returning_function_is_clean(self):
        # Introduced by the round-one fix that broadened reference capture: the FROM item's first
        # word was a function call, which read as an unqualified tenant-track table.
        self.assertEqual(
            self.rules("CREATE VIEW plt01.probe WITH (security_invoker = true) AS "
                       "SELECT g AS n FROM generate_series(1, 3) g;"),
            set())

    def test_set_config_arity_counts_past_a_comma_in_a_literal(self):
        self.assertEqual(self.rules("SELECT set_config('app.correlation_id', 'a,b', true);"),
                         set())

    def test_alter_policy_alone_does_not_satisfy_the_policy_rule(self):
        sql = COMPLETE_TENANT_TABLE.split("CREATE POLICY")[0]
        sql += ("ALTER POLICY p ON plt01.brand_appearance USING "
                "(tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);\n")
        self.assertEqual(self.rules(sql), {"RLS_POLICY"})


class TestKnownOverReports(LintCase):
    """Two over-reports kept deliberately. Both are disclosed in the module docstring."""

    def test_comment_quoting_the_ban_trips_the_session_rule(self):
        self.assertEqual(
            self.rules("COMMENT ON TABLE plt01.brand_appearance IS "
                       "'Never SET app.tenant_id at session level.';"),
            {"SESSION_CONTEXT_SET"})

    def test_create_table_like_has_no_column_list_to_read(self):
        self.assertIn("TENANT_ID_COLUMN",
                      self.rules("CREATE TABLE plt01.copy "
                                 "(LIKE plt01.brand_appearance INCLUDING ALL);"))


class TestAllowlistFailsClosed(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def write(self, payload):
        path = self.tmp / "allowlist.json"
        path.write_text(json.dumps(payload) if not isinstance(payload, str) else payload,
                        encoding="utf-8")
        return path

    def test_missing_file(self):
        with self.assertRaises(ml.Malformed):
            ml.load_allowlist(self.tmp / "absent.json")

    def test_unparseable(self):
        with self.assertRaises(ml.Malformed):
            ml.load_allowlist(self.write("{not json"))

    def test_wrong_schema(self):
        with self.assertRaises(ml.Malformed):
            ml.load_allowlist(self.write({"schema": 99, "functions": []}))

    def test_entry_missing_a_required_d5_field(self):
        for omit in ml.ALLOWLIST_FIELDS:
            entry = {"function": "plt01_api.f", "owner": "veyro_cp_platform",
                     "search_path": "pg_catalog", "execute_grantees": ["veyro_cp_app"],
                     "review_id": "VR-1"}
            entry.pop(omit)
            with self.assertRaises(ml.Malformed, msg=omit):
                ml.load_allowlist(self.write({"schema": 1, "functions": [entry]}))

    def test_unqualified_function_name_is_rejected(self):
        entry = {"function": "f", "owner": "veyro_cp_platform", "search_path": "pg_catalog",
                 "execute_grantees": ["veyro_cp_app"], "review_id": "VR-1"}
        with self.assertRaises(ml.Malformed):
            ml.load_allowlist(self.write({"schema": 1, "functions": [entry]}))

    def test_shipped_allowlist_is_empty_and_valid(self):
        allowlist, views = ml.load_allowlist(ALLOWLIST)
        self.assertEqual(allowlist, {})
        self.assertEqual(views, set())


class TestCorpus(unittest.TestCase):
    """The corpus qualifies the lint. These tests qualify the corpus."""

    def setUp(self):
        self.allowlist, self.views = ml.load_allowlist(ALLOWLIST)

    def test_corpus_passes(self):
        self.assertEqual(ml.run_corpus(CORPUS, self.allowlist, self.views), [])

    def test_every_rule_is_targeted_by_a_mutation(self):
        targeted = {p.name.split("+")[0] for p in (CORPUS / "mutations").iterdir() if p.is_dir()}
        self.assertEqual(targeted, set(ml.RULES))

    def test_a_lint_that_reports_nothing_fails_the_corpus(self):
        with mock.patch.object(ml, "lint_file", return_value=[]):
            failures = ml.run_corpus(CORPUS, self.allowlist, self.views)
        self.assertTrue(failures)
        reported = " ".join(f["corpus_item"] for f in failures)
        for rule in ml.RULES:
            self.assertIn(rule, reported)

    def test_a_lint_that_reports_everything_fails_the_corpus(self):
        everything = [ml.Finding(rule, "x", 1, "x") for rule in ml.RULES]
        with mock.patch.object(ml, "lint_file", return_value=everything):
            failures = ml.run_corpus(CORPUS, self.allowlist, self.views)
        items = [f["corpus_item"] for f in failures]
        self.assertTrue(any(i.startswith("baseline/") for i in items))

    def test_a_repaired_mutation_fails_the_corpus(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        root = tmp / "corpus"
        shutil.copytree(CORPUS, root)
        target = root / "mutations" / "RLS_FORCE" / "tenant" / "0001_mutation.sql"
        target.write_text(COMPLETE_TENANT_TABLE, encoding="utf-8")
        shutil.copy(CORPUS / "baseline" / "tests" / "negative_runtime_role.sql",
                    root / "baseline" / "tests" / "negative_runtime_role.sql")
        failures = ml.run_corpus(root, self.allowlist, self.views)
        self.assertTrue(any("RLS_FORCE" in f["corpus_item"] for f in failures))

    def test_mutation_naming_an_unknown_rule_is_malformed(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        root = tmp / "corpus"
        shutil.copytree(CORPUS, root)
        (root / "mutations" / "NOT_A_RULE" / "tenant").mkdir(parents=True)
        (root / "mutations" / "NOT_A_RULE" / "tenant" / "0001.sql").write_text("SELECT 1;")
        with self.assertRaises(ml.Malformed):
            ml.run_corpus(root, self.allowlist, self.views)

    def test_empty_mutation_directory_is_malformed(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        root = tmp / "corpus"
        shutil.copytree(CORPUS, root)
        (root / "mutations" / "RLS_ENABLE" / "tenant" / "0001_mutation.sql").unlink()
        with self.assertRaises(ml.Malformed):
            ml.run_corpus(root, self.allowlist, self.views)


class TestScanner(unittest.TestCase):
    def test_masked_and_uncommented_keep_the_source_length(self):
        sql = "-- c\n/* b */ SELECT 'lit', $t$body$t$;\n"
        masked, uncommented, quoted = ml._scan(sql)
        self.assertEqual(len(masked), len(sql))
        self.assertEqual(len(uncommented), len(sql))
        # Both quoting forms are collected: a function body may be written either way, and
        # collecting only the dollar form left the single-quoted spelling unlinted and unrefused.
        self.assertEqual(quoted, ["lit", "body"])

    def test_semicolon_in_a_string_does_not_split(self):
        masked, uncommented, _ = ml._scan("SELECT 'a;b';")
        self.assertEqual(len(ml._statements(masked, uncommented)), 1)

    def test_semicolon_in_a_quoted_identifier_does_not_split(self):
        masked, uncommented, _ = ml._scan('CREATE TABLE "a;b" (x int);')
        self.assertEqual(len(ml._statements(masked, uncommented)), 1)

    def test_semicolon_in_a_dollar_body_does_not_split(self):
        masked, uncommented, _ = ml._scan("CREATE FUNCTION f() AS $$ SELECT 1; SELECT 2; $$;")
        self.assertEqual(len(ml._statements(masked, uncommented)), 1)

    def test_unterminated_dollar_quote_is_malformed(self):
        with self.assertRaises(ml.Malformed):
            ml._scan("CREATE FUNCTION f() AS $$ SELECT 1;")

    def test_e_string_backslash_escape(self):
        masked, _, _ = ml._scan(r"SELECT E'a\'b;c', 1;")
        self.assertEqual(len(ml._statements(masked, masked)), 1)


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def run_main(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = ml.main(argv)
        return code, json.loads(buf.getvalue())

    def test_clean_file_exits_zero(self):
        track = self.tmp / "tenant"
        track.mkdir()
        (track / "0001.sql").write_text(COMPLETE_TENANT_TABLE, encoding="utf-8")
        tests = self.tmp / "tests"
        tests.mkdir()
        (tests / "n.sql").write_text(NEGATIVE_TEST_FIXTURE, encoding="utf-8")
        code, out = self.run_main(["lint", "--tests-root", str(tests), str(track)])
        self.assertEqual((code, out["result"], out["track"]), (0, "PASS", "tenant"))

    def test_findings_exit_one(self):
        path = self.tmp / "0001.sql"
        path.write_text("GRANT SELECT ON plt01.brand_appearance TO PUBLIC;", encoding="utf-8")
        code, out = self.run_main(["lint", "--track", "tenant", str(path)])
        self.assertEqual((code, out["result"]), (1, "BLOCKED"))
        self.assertEqual(out["findings"][0]["rule"], "PUBLIC_GRANT")
        self.assertIn("why", out["findings"][0])

    def test_untrackable_path_exits_two(self):
        path = self.tmp / "0001.sql"
        path.write_text("SELECT 1;", encoding="utf-8")
        code, out = self.run_main(["lint", str(path)])
        self.assertEqual((code, out["result"]), (2, "MALFORMED"))

    def test_missing_path_exits_two(self):
        code, out = self.run_main(["lint", "--track", "tenant", str(self.tmp / "absent.sql")])
        self.assertEqual((code, out["result"]), (2, "MALFORMED"))

    def test_track_is_inferred_from_the_path(self):
        track = self.tmp / "platform"
        track.mkdir()
        (track / "0001.sql").write_text("SELECT 1;", encoding="utf-8")
        code, out = self.run_main(["lint", str(track)])
        self.assertEqual((code, out["track"]), (0, "platform"))

    def test_corpus_subcommand_exits_zero(self):
        code, out = self.run_main(["corpus", "--root", str(CORPUS)])
        self.assertEqual((code, out["result"]), (0, "PASS"))
        self.assertEqual(out["rules"], len(ml.RULES))

    def test_every_result_states_the_static_only_limit(self):
        code, out = self.run_main(["corpus", "--root", str(CORPUS)])
        self.assertIn("catalog assertions are NOT performed", out["static_only"])


if __name__ == "__main__":
    unittest.main()

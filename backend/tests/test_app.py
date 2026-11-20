import unittest

from fastapi.testclient import TestClient

from app.config import ConfigError, Settings, load_settings
from app.main import create_app

DSN = "postgresql://postgres:unused@127.0.0.1:5432/veyro"


class HealthzTests(unittest.TestCase):
    def client(self, environment: str = "local", release: str = "r1") -> TestClient:
        return TestClient(
            create_app(Settings(environment, release, "postgresql://unused/veyro"))
        )

    def test_healthz_is_deterministic_and_reports_environment_and_release(self):
        c = self.client("staging", "abc123")
        first = c.get("/healthz")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(
            first.json(),
            {
                "status": "ok",
                "service": "veyro-api",
                "environment": "staging",
                "release": "abc123",
            },
        )
        self.assertEqual(c.get("/healthz").json(), first.json())

    def test_no_root_or_docs_exposed(self):
        """The schema and the interactive docs are not served, and neither is a root page.

        `/memberships` used to stand in here for "a domain route that does not exist", and
        MOD-017 made it exist -- a `GET` on a `POST`-only path is then 405 rather than 404, and
        the test failed for a reason that had nothing to do with what it was checking. A
        placeholder that names a route somebody will one day write is a test with an expiry
        date on it, so the path below is one nothing will ever claim.
        """
        c = self.client()
        for path in ("/", "/docs", "/openapi.json", "/redoc",
                     "/not-a-surface-this-build-serves"):
            self.assertEqual(c.get(path).status_code, 404, path)

    def test_healthz_rejects_writes(self):
        self.assertEqual(self.client().post("/healthz").status_code, 405)


class ConfigTests(unittest.TestCase):
    def test_each_supported_environment_loads(self):
        for name in ("local", "development", "staging"):
            s = load_settings({"VEYRO_ENV": name, "VEYRO_DATABASE_URL": DSN})
            self.assertEqual((s.environment, s.release), (name, "unversioned"))
            self.assertEqual(s.database_url, DSN)

    def test_missing_or_unknown_environment_fails_closed(self):
        for env in ({}, {"VEYRO_ENV": "production"}, {"VEYRO_ENV": ""}):
            with self.assertRaises(ConfigError):
                load_settings({**env, "VEYRO_DATABASE_URL": DSN})

    def test_blank_release_rejected(self):
        with self.assertRaises(ConfigError):
            load_settings(
                {"VEYRO_ENV": "local", "VEYRO_RELEASE": "  ", "VEYRO_DATABASE_URL": DSN}
            )

    def test_missing_database_url_fails_closed(self):
        """The service has no in-memory fallback, so a missing DSN must not start it."""
        for env in ({"VEYRO_ENV": "local"}, {"VEYRO_ENV": "local", "VEYRO_DATABASE_URL": " "}):
            with self.assertRaises(ConfigError):
                load_settings(env)


if __name__ == "__main__":
    unittest.main()


class ApiRequestBudgetTests(unittest.TestCase):
    """The one knob in `config.py`, and why it is a knob rather than a smaller number.

    MOD-011's `api.request` budget is 600 a minute per identity, and its own comment says why
    it is generous: "a limit that trips during ordinary use is a limit somebody will raise to
    infinity rather than investigate". **A browser suite is not ordinary use** -- 300 tests in
    three minutes makes more requests per minute than any operator will. It tripped the
    limiter in CI, where six tests failed with "Something went wrong" and passed on every
    developer's laptop, because a laptop runs the dev server and CI drives the production
    build, which is faster.

    Raising the table's number to suit a test would be exactly the mistake that comment
    names. So the override is per process, bounded, and refused anywhere but `local`.
    """

    BASE = {"VEYRO_ENV": "local", "VEYRO_RELEASE": "dev",
            "VEYRO_DATABASE_URL": "postgresql://x/y"}

    def test_the_default_is_the_tables_own_number(self):
        self.assertIsNone(load_settings(dict(self.BASE)).api_request_budget)

    def test_local_may_raise_it(self):
        self.assertEqual(
            load_settings({**self.BASE, "VEYRO_API_REQUEST_BUDGET": "5000"})
            .api_request_budget, 5000)

    def test_development_and_staging_refuse_it_rather_than_widening_a_control(self):
        """**Fail closed**: an environment that is not local refuses to start rather than
        quietly admitting a wider budget, which is the whole point of putting it here."""
        for environment in ("development", "staging"):
            with self.subTest(environment=environment):
                with self.assertRaises(ConfigError) as refused:
                    load_settings({**self.BASE, "VEYRO_ENV": environment,
                                   "VEYRO_API_REQUEST_BUDGET": "5000"})
                self.assertIn("local-only", str(refused.exception))

    def test_a_non_integer_and_an_out_of_range_value_are_both_refused(self):
        for value in ("lots", "0", "-1", "100001", "6e2"):
            with self.subTest(value=value):
                with self.assertRaises(ConfigError):
                    load_settings({**self.BASE, "VEYRO_API_REQUEST_BUDGET": value})

    def test_a_blank_setting_is_the_same_as_an_absent_one(self):
        self.assertIsNone(
            load_settings({**self.BASE, "VEYRO_API_REQUEST_BUDGET": "  "})
            .api_request_budget)

    def test_the_limiter_honours_the_override_and_the_table_otherwise(self):
        """The whole point: the number the limiter uses, not the number the config carries."""
        from app.observability.ratelimit import BUDGETS, Limiter

        default = Limiter()
        raised = Limiter(budgets={**BUDGETS, "api.request": 2})
        for _ in range(1, BUDGETS["api.request"] + 1):
            verdict = default.check(tenant_id="t", limit_key="api.request",
                                    subject="s", now_epoch=1000.0)
        self.assertTrue(verdict.allowed, "the table's budget admits its own last request")
        self.assertTrue(raised.check(tenant_id="t", limit_key="api.request",
                                     subject="s", now_epoch=1000.0).allowed)
        self.assertTrue(raised.check(tenant_id="t", limit_key="api.request",
                                     subject="s", now_epoch=1000.0).allowed)
        self.assertFalse(
            raised.check(tenant_id="t", limit_key="api.request",
                         subject="s", now_epoch=1000.0).allowed,
            "an overridden budget of two refuses the third request")

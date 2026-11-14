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

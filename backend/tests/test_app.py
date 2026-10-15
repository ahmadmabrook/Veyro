import unittest

from fastapi.testclient import TestClient

from app.config import ConfigError, Settings, load_settings
from app.main import create_app


class HealthzTests(unittest.TestCase):
    def client(self, environment: str = "local", release: str = "r1") -> TestClient:
        return TestClient(create_app(Settings(environment, release)))

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

    def test_no_domain_routes_or_docs_exposed(self):
        c = self.client()
        for path in ("/", "/memberships", "/docs", "/openapi.json"):
            self.assertEqual(c.get(path).status_code, 404, path)

    def test_healthz_rejects_writes(self):
        self.assertEqual(self.client().post("/healthz").status_code, 405)


class ConfigTests(unittest.TestCase):
    def test_intentional_protected_ci_negative(self):
        self.fail("intentional protected-PR CI negative drill")

    def test_each_supported_environment_loads(self):
        for name in ("local", "development", "staging"):
            s = load_settings({"VEYRO_ENV": name})
            self.assertEqual((s.environment, s.release), (name, "unversioned"))

    def test_missing_or_unknown_environment_fails_closed(self):
        for env in ({}, {"VEYRO_ENV": "production"}, {"VEYRO_ENV": ""}):
            with self.assertRaises(ConfigError):
                load_settings(env)

    def test_blank_release_rejected(self):
        with self.assertRaises(ConfigError):
            load_settings({"VEYRO_ENV": "local", "VEYRO_RELEASE": "  "})


if __name__ == "__main__":
    unittest.main()

"""MOD-005 PLT-02 configuration API against a real PostgreSQL with row-level security in force.

The evaluation decisions themselves are covered by `test_configuration_evaluation.py`, which
needs no database. What is checked here is everything that only a real database can answer:
that the service feeds the evaluator the right rows, that history is append-only because the
privileges say so, that a scope cannot reach across tenants, and that two tenants with the same
configuration keys do not see each other at all.
"""

from __future__ import annotations

import os
import unittest
import uuid

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import make_platform_pool, make_tenant_pool
from app.main import create_app

DSN = os.environ.get("VEYRO_DATABASE_URL", "")


@unittest.skipUnless(DSN, "VEYRO_DATABASE_URL is not set")
class ConfigurationApiTests(unittest.TestCase):
    client: TestClient

    @classmethod
    def setUpClass(cls) -> None:
        cls._tenant_pool = make_tenant_pool(DSN)
        cls._platform_pool = make_platform_pool(DSN)
        app = create_app(
            Settings(environment="local", release="test", database_url=DSN),
            tenant_pool=cls._tenant_pool,
            platform_pool=cls._platform_pool,
        )
        cls._client_cm = TestClient(app)
        cls.client = cls._client_cm.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._client_cm.__exit__(None, None, None)
        cls._tenant_pool.close()
        cls._platform_pool.close()

    # ------------------------------------------------------------------ helpers

    def tenant(self) -> str:
        response = self.client.post("/platform/tenants", json={
            "external_key": f"cfg-{uuid.uuid4()}", "display_name": "Config Gym",
            "region": "eu-west", "actor_id": str(uuid.uuid4()),
            "correlation_id": str(uuid.uuid4()), "idempotency_key": str(uuid.uuid4()),
        })
        self.assertEqual(response.status_code, 201, response.text)
        return str(response.json()["tenant_id"])

    def headers(self, tenant_id: str) -> dict[str, str]:
        return {"X-Veyro-Tenant": tenant_id}

    def define(self, tenant_id: str, key: str = "checkin.grace_minutes", **overrides):
        body = {"config_key": key, "value_type": "integer", "default_value": 15,
                "owner_module": "MOD-005"}
        body.update(overrides)
        return self.client.post("/config/definitions", json=body,
                                headers=self.headers(tenant_id))

    def publish(self, tenant_id: str, value, key: str = "checkin.grace_minutes", **overrides):
        body = {"config_key": key, "value": value, "scope_type": "tenant",
                "published_by": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())}
        body.update(overrides)
        return self.client.post("/config/values", json=body, headers=self.headers(tenant_id))

    def brand_and_location(self, tenant_id: str) -> tuple[str, str]:
        head = self.headers(tenant_id)
        org = self.client.post("/organizations",
                               json={"legal_name": "Cfg ehf", "country_code": "IS"}, headers=head)
        self.assertEqual(org.status_code, 201, org.text)
        brand = self.client.post(
            "/brands", json={"organization_id": org.json()["organization_id"],
                             "brand_name": "Cfg City"}, headers=head)
        self.assertEqual(brand.status_code, 201, brand.text)
        location = self.client.post(
            "/locations", json={"brand_id": brand.json()["brand_id"],
                                "location_name": "Cfg Laugavegur",
                                "timezone": "Atlantic/Reykjavik"}, headers=head)
        self.assertEqual(location.status_code, 201, location.text)
        return brand.json()["brand_id"], location.json()["location_id"]

    # ------------------------------------------------------------------ definitions

    def test_definition_round_trips_and_its_key_is_unique_per_tenant(self):
        tenant_id = self.tenant()
        created = self.define(tenant_id)
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["value_type"], "integer")

        again = self.define(tenant_id)
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()["error"], "config_key_exists")

        other = self.tenant()
        self.assertEqual(self.define(other).status_code, 201,
                         "the same key must be free in another tenant")

    def test_a_default_that_fails_its_own_validation_is_refused(self):
        tenant_id = self.tenant()
        response = self.define(tenant_id, key="limits.cap", default_value=50,
                               validation={"maximum": 10})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "above_maximum")

    def test_a_malformed_key_is_refused(self):
        self.assertEqual(self.define(self.tenant(), key="NotDotted").status_code, 422)

    # ------------------------------------------------------------------ values and history

    def test_publishing_appends_versions_and_history_reads_forward(self):
        tenant_id = self.tenant()
        self.define(tenant_id)
        for expected, value in enumerate([20, 25, 30], start=1):
            response = self.publish(tenant_id, value)
            self.assertEqual(response.status_code, 201, response.text)
            self.assertEqual(response.json()["version"], expected)

        history = self.client.get("/config/values/checkin.grace_minutes/history",
                                  headers=self.headers(tenant_id))
        self.assertEqual([row["value"] for row in history.json()], [20, 25, 30])

    def test_a_value_that_breaks_its_definition_is_refused(self):
        tenant_id = self.tenant()
        self.define(tenant_id, validation={"minimum": 5, "maximum": 60})
        self.assertEqual(self.publish(tenant_id, 120).status_code, 422)
        self.assertEqual(self.publish(tenant_id, "twenty").status_code, 422)
        self.assertEqual(self.publish(tenant_id, 30).status_code, 201)

    def test_expected_version_refuses_a_stale_publish(self):
        tenant_id = self.tenant()
        self.define(tenant_id)
        self.publish(tenant_id, 20)
        stale = self.publish(tenant_id, 25, expected_version=0)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["error"], "version_mismatch")
        self.assertEqual(self.publish(tenant_id, 25, expected_version=1).status_code, 201)

    def test_publishing_to_an_unknown_key_is_a_404(self):
        response = self.publish(self.tenant(), 1, key="never.defined")
        self.assertEqual(response.status_code, 404)

    def test_scope_shape_is_enforced_before_the_database_sees_it(self):
        tenant_id = self.tenant()
        self.define(tenant_id)
        response = self.publish(tenant_id, 20, scope_type="brand")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "brand_scope_needs_brand_id")

    def test_another_tenants_brand_cannot_be_used_as_a_scope(self):
        """The composite foreign key carries tenant_id, so the database refuses this."""
        owner, intruder = self.tenant(), self.tenant()
        brand_id, _ = self.brand_and_location(owner)
        self.define(intruder)
        response = self.publish(intruder, 20, scope_type="brand", brand_id=brand_id)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "scope_not_found")

    # ------------------------------------------------------------------ inheritance

    def test_resolution_prefers_the_most_specific_scope(self):
        tenant_id = self.tenant()
        brand_id, location_id = self.brand_and_location(tenant_id)
        self.define(tenant_id)
        head = self.headers(tenant_id)

        def resolved(**params):
            response = self.client.get("/config/resolved", params=params, headers=head)
            self.assertEqual(response.status_code, 200, response.text)
            return response.json()["checkin.grace_minutes"]

        self.assertEqual(resolved(), {"value": 15, "scope_type": "default", "version": None})
        self.publish(tenant_id, 20)
        self.assertEqual(resolved()["value"], 20)
        self.publish(tenant_id, 25, scope_type="brand", brand_id=brand_id)
        self.assertEqual(resolved(brand_id=brand_id)["value"], 25)
        self.assertEqual(resolved()["value"], 20, "the tenant scope must be unaffected")
        self.publish(tenant_id, 30, scope_type="location", location_id=location_id)
        self.assertEqual(
            resolved(brand_id=brand_id, location_id=location_id)["value"], 30
        )

    # ------------------------------------------------------------------ preview and rollback

    def test_preview_reports_the_change_without_writing(self):
        tenant_id = self.tenant()
        self.define(tenant_id)
        self.publish(tenant_id, 20)
        response = self.client.post(
            "/config/preview", json={"config_key": "checkin.grace_minutes", "value": 45},
            headers=self.headers(tenant_id))
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["current"]["value"], 20)
        self.assertEqual(body["resolves_to"]["value"], 45)
        self.assertTrue(body["changes"])
        self.assertFalse(body["shadowed"])

        history = self.client.get("/config/values/checkin.grace_minutes/history",
                                  headers=self.headers(tenant_id))
        self.assertEqual(len(history.json()), 1, "preview must not publish")

    def test_preview_reports_a_value_that_a_narrower_scope_would_shadow(self):
        tenant_id = self.tenant()
        brand_id, _ = self.brand_and_location(tenant_id)
        self.define(tenant_id)
        self.publish(tenant_id, 20)
        self.publish(tenant_id, 25, scope_type="brand", brand_id=brand_id)
        response = self.client.post(
            "/config/preview",
            json={"config_key": "checkin.grace_minutes", "value": 99,
                  "scope_type": "tenant", "brand_id": None},
            headers=self.headers(tenant_id))
        self.assertEqual(response.json()["shadowed"], False,
                         "resolving at the tenant scope, nothing shadows it")

    def test_rollback_appends_rather_than_rewriting(self):
        tenant_id = self.tenant()
        self.define(tenant_id)
        self.publish(tenant_id, 20)
        self.publish(tenant_id, 999)
        response = self.client.post(
            "/config/values/checkin.grace_minutes/rollback",
            json={"scope_type": "tenant", "to_version": 1,
                  "published_by": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())},
            headers=self.headers(tenant_id))
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual((response.json()["value"], response.json()["version"]), (20, 3))
        self.assertEqual(response.json()["rolled_back_from"], 1)

        history = self.client.get("/config/values/checkin.grace_minutes/history",
                                  headers=self.headers(tenant_id)).json()
        self.assertEqual([row["value"] for row in history], [20, 999, 20],
                         "the bad version stays in history; nothing is rewritten")

    def test_rolling_back_to_a_version_that_never_existed_is_a_404(self):
        tenant_id = self.tenant()
        self.define(tenant_id)
        self.publish(tenant_id, 20)
        response = self.client.post(
            "/config/values/checkin.grace_minutes/rollback",
            json={"scope_type": "tenant", "to_version": 7,
                  "published_by": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())},
            headers=self.headers(tenant_id))
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------------ flags

    def set_flag(self, tenant_id: str, key: str = "pay.new_provider", **overrides):
        body = {"enabled": True, "default_variant": "off", "rules": []}
        body.update(overrides)
        return self.client.put(f"/flags/{key}", json=body, headers=self.headers(tenant_id))

    def evaluate(self, tenant_id: str, subject_id: str = "member-1", **params):
        response = self.client.get("/flags", params={"subject_id": subject_id, **params},
                                   headers=self.headers(tenant_id))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_a_flag_with_a_full_rollout_rule_is_on_for_everyone(self):
        tenant_id = self.tenant()
        self.assertEqual(self.set_flag(tenant_id, rules=[{"variant": "on"}]).status_code, 200)
        for subject in ("a", "b", "c"):
            self.assertEqual(
                self.evaluate(tenant_id, subject)["pay.new_provider"]["variant"], "on"
            )

    def test_targeting_selects_only_the_matching_context(self):
        tenant_id = self.tenant()
        self.set_flag(tenant_id, rules=[{"match": {"plan": "pro"}, "variant": "on"}])
        self.assertEqual(self.evaluate(tenant_id, plan="pro")["pay.new_provider"]["variant"], "on")
        self.assertEqual(
            self.evaluate(tenant_id, plan="free")["pay.new_provider"]["variant"], "off"
        )
        self.assertEqual(self.evaluate(tenant_id)["pay.new_provider"]["variant"], "off")

    def test_a_partial_rollout_is_stable_across_calls(self):
        tenant_id = self.tenant()
        self.set_flag(tenant_id, rules=[{"variant": "on", "rollout_bp": 5000}])
        first = {s: self.evaluate(tenant_id, s)["pay.new_provider"]["variant"]
                 for s in (f"member-{i}" for i in range(12))}
        again = {s: self.evaluate(tenant_id, s)["pay.new_provider"]["variant"] for s in first}
        self.assertEqual(first, again)
        self.assertEqual(set(first.values()) - {"on", "off"}, set())

    def test_replacing_a_policy_retires_the_old_rules(self):
        tenant_id = self.tenant()
        self.set_flag(tenant_id, rules=[{"variant": "on"}])
        self.assertEqual(self.evaluate(tenant_id)["pay.new_provider"]["variant"], "on")
        updated = self.set_flag(tenant_id, rules=[{"variant": "legacy"}])
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(self.evaluate(tenant_id)["pay.new_provider"]["variant"], "legacy")

    def test_kill_switch_overrides_an_enabled_flag_and_needs_a_reason(self):
        tenant_id = self.tenant()
        self.set_flag(tenant_id, rules=[{"variant": "on"}])
        head = self.headers(tenant_id)

        bare = self.client.post("/flags/pay.new_provider/kill-switch",
                                json={"engaged": True}, headers=head)
        self.assertEqual(bare.status_code, 422)
        self.assertEqual(bare.json()["error"], "kill_switch_needs_reason")

        engaged = self.client.post(
            "/flags/pay.new_provider/kill-switch",
            json={"engaged": True, "reason": "provider outage"}, headers=head)
        self.assertEqual(engaged.status_code, 200, engaged.text)
        decision = self.evaluate(tenant_id)["pay.new_provider"]
        self.assertEqual((decision["variant"], decision["reason"]), ("off", "kill_switch"))

        self.client.post("/flags/pay.new_provider/kill-switch",
                         json={"engaged": False}, headers=head)
        self.assertEqual(self.evaluate(tenant_id)["pay.new_provider"]["variant"], "on")

    def test_a_policy_edit_does_not_clear_an_engaged_kill_switch(self):
        """Switches are released deliberately, never as a side effect of an unrelated edit."""
        tenant_id = self.tenant()
        self.set_flag(tenant_id, rules=[{"variant": "on"}])
        self.client.post("/flags/pay.new_provider/kill-switch",
                         json={"engaged": True, "reason": "provider outage"},
                         headers=self.headers(tenant_id))
        self.set_flag(tenant_id, rules=[{"variant": "on"}], description="unrelated edit")
        self.assertEqual(self.evaluate(tenant_id)["pay.new_provider"]["reason"], "kill_switch")

    def test_a_kill_switch_on_an_unknown_flag_is_a_404(self):
        response = self.client.post("/flags/never.defined/kill-switch",
                                    json={"engaged": True, "reason": "x"},
                                    headers=self.headers(self.tenant()))
        self.assertEqual(response.status_code, 404)

    def test_expected_version_refuses_a_stale_policy_edit(self):
        tenant_id = self.tenant()
        self.set_flag(tenant_id)
        stale = self.set_flag(tenant_id, expected_version=99)
        self.assertEqual(stale.status_code, 409)

    # ------------------------------------------------------------------ experiments

    def create_experiment(self, tenant_id: str, key: str = "checkout.copy", **overrides):
        body = {"experiment_key": key,
                "variants": [{"variant_key": "control", "weight": 1},
                             {"variant_key": "treatment", "weight": 1}]}
        body.update(overrides)
        return self.client.post("/experiments", json=body, headers=self.headers(tenant_id))

    def test_a_draft_experiment_assigns_nobody(self):
        tenant_id = self.tenant()
        self.assertEqual(self.create_experiment(tenant_id).status_code, 201)
        response = self.client.post("/experiments/checkout.copy/allocate",
                                    json={"subject_id": "member-1"},
                                    headers=self.headers(tenant_id))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"experiment_key": "checkout.copy",
                                           "subject_id": "member-1", "variant": None,
                                           "exposed": False, "newly_exposed": False})

    def test_allocation_is_idempotent_and_records_one_exposure(self):
        tenant_id = self.tenant()
        self.create_experiment(tenant_id)
        head = self.headers(tenant_id)
        self.client.post("/experiments/checkout.copy/status", json={"status": "running"},
                         headers=head)

        first = self.client.post("/experiments/checkout.copy/allocate",
                                 json={"subject_id": "member-1"}, headers=head).json()
        self.assertIn(first["variant"], ("control", "treatment"))
        self.assertTrue(first["newly_exposed"])

        second = self.client.post("/experiments/checkout.copy/allocate",
                                  json={"subject_id": "member-1"}, headers=head).json()
        self.assertEqual(second["variant"], first["variant"])
        self.assertFalse(second["newly_exposed"])

        exposures = self.client.get("/experiments/checkout.copy/exposures", headers=head).json()
        self.assertEqual(len(exposures), 1)
        self.assertEqual(exposures[0]["subject_id"], "member-1")

    def test_experiment_status_only_moves_forward(self):
        tenant_id = self.tenant()
        self.create_experiment(tenant_id)
        head = self.headers(tenant_id)
        self.assertEqual(
            self.client.post("/experiments/checkout.copy/status", json={"status": "completed"},
                             headers=head).status_code, 409,
            "draft cannot jump straight to completed")
        self.client.post("/experiments/checkout.copy/status", json={"status": "running"},
                         headers=head)
        self.assertEqual(
            self.client.post("/experiments/checkout.copy/status", json={"status": "running"},
                             headers=head).status_code, 409)
        self.assertEqual(
            self.client.post("/experiments/checkout.copy/status", json={"status": "completed"},
                             headers=head).status_code, 200)

    def test_a_completed_experiment_stops_assigning(self):
        tenant_id = self.tenant()
        self.create_experiment(tenant_id)
        head = self.headers(tenant_id)
        for status in ("running", "completed"):
            self.client.post("/experiments/checkout.copy/status", json={"status": status},
                             headers=head)
        response = self.client.post("/experiments/checkout.copy/allocate",
                                    json={"subject_id": "fresh"}, headers=head).json()
        self.assertIsNone(response["variant"])

    def test_an_experiment_needs_at_least_two_variants(self):
        response = self.create_experiment(
            self.tenant(), variants=[{"variant_key": "only", "weight": 1}])
        self.assertEqual(response.status_code, 422)

    # ------------------------------------------------------------------ bundle and isolation

    def test_bundle_carries_configuration_and_flags_together(self):
        tenant_id = self.tenant()
        self.define(tenant_id)
        self.publish(tenant_id, 20)
        self.set_flag(tenant_id, rules=[{"variant": "on"}])
        response = self.client.get("/config/bundle", params={"subject_id": "kiosk-1"},
                                   headers=self.headers(tenant_id))
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["configuration"]["checkin.grace_minutes"]["value"], 20)
        self.assertEqual(body["flags"]["pay.new_provider"]["variant"], "on")
        self.assertGreater(body["version"], 0)

    def test_the_bundle_version_moves_when_anything_in_it_moves(self):
        tenant_id = self.tenant()
        self.define(tenant_id)
        self.publish(tenant_id, 20)
        head = self.headers(tenant_id)

        def version():
            return self.client.get("/config/bundle", params={"subject_id": "kiosk-1"},
                                   headers=head).json()["version"]

        before = version()
        self.publish(tenant_id, 25)
        self.assertNotEqual(version(), before)

    def test_two_tenants_with_the_same_keys_do_not_see_each_other(self):
        first, second = self.tenant(), self.tenant()
        self.define(first)
        self.publish(first, 20)
        self.set_flag(first, rules=[{"variant": "on"}])

        self.define(second)
        self.publish(second, 90)
        self.set_flag(second, enabled=False)

        first_bundle = self.client.get("/config/bundle", params={"subject_id": "s"},
                                       headers=self.headers(first)).json()
        second_bundle = self.client.get("/config/bundle", params={"subject_id": "s"},
                                        headers=self.headers(second)).json()
        self.assertEqual(first_bundle["configuration"]["checkin.grace_minutes"]["value"], 20)
        self.assertEqual(second_bundle["configuration"]["checkin.grace_minutes"]["value"], 90)
        self.assertEqual(first_bundle["flags"]["pay.new_provider"]["variant"], "on")
        self.assertEqual(second_bundle["flags"]["pay.new_provider"]["variant"], "off")

    def test_one_tenants_definitions_are_invisible_to_another(self):
        owner, other = self.tenant(), self.tenant()
        self.define(owner, key="secret.budget_cap")
        listed = self.client.get("/config/definitions", headers=self.headers(other)).json()
        self.assertEqual([row["config_key"] for row in listed], [])

    def test_a_history_read_for_another_tenants_key_finds_nothing(self):
        owner, other = self.tenant(), self.tenant()
        self.define(owner)
        self.publish(owner, 20)
        response = self.client.get("/config/values/checkin.grace_minutes/history",
                                   headers=self.headers(other))
        self.assertEqual(response.status_code, 404,
                         "the key is not merely empty for the other tenant, it does not exist")

    def test_an_experiment_is_not_allocatable_from_another_tenant(self):
        owner, other = self.tenant(), self.tenant()
        self.create_experiment(owner)
        self.client.post("/experiments/checkout.copy/status", json={"status": "running"},
                         headers=self.headers(owner))
        response = self.client.post("/experiments/checkout.copy/allocate",
                                    json={"subject_id": "member-1"},
                                    headers=self.headers(other))
        self.assertEqual(response.status_code, 404)

    def test_a_request_with_no_tenant_header_is_refused(self):
        for path, params in (("/config/definitions", {}),
                             ("/flags", {"subject_id": "s"}),
                             ("/config/bundle", {"subject_id": "s"})):
            self.assertEqual(self.client.get(path, params=params).status_code, 422, path)


if __name__ == "__main__":
    unittest.main()

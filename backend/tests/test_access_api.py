"""MOD-022 (OPS-03) over HTTP, with the credentials a real caller would hold.

**Driven through the routes, not the service.** This repository's record on that is explicit:
MOD-014's reviewers found four defects in its request path that a green suite could not see,
MOD-016 had no test that had ever called a `/catalog` route successfully, and MOD-020's review
named "no HTTP test ever recorded a no-show" as the gap that let four blocking findings ship.

The tests that matter most here are the two Critical Controls. Paragraph 1944: a denial never
reveals sensitive financial or health information publicly -- so most of the decision tests
assert what a *turnstile* may show, not what the server knows. Paragraph 4177: egress is never
conditioned on software authorization -- so the exit tests assert an absence of a code path.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from tests.support import GatedApiTestCase


def correlation_only() -> dict[str, str]:
    return {"correlation_id": str(uuid.uuid4())}


class AccessApiTestCase(GatedApiTestCase):
    """A tenant with a location, a live turnstile, a zone, a published policy and a member."""

    def location(self, tenant_id: str, *, timezone: str = "Asia/Amman") -> str:
        owner = self.headers(tenant_id)
        org = self.client.post("/organizations", json={
            "legal_name": "Veyro Sites Ltd", "country_code": "JO",
            **self.correlation()}, headers=owner)
        self.assertEqual(org.status_code, 201, org.text)
        brand = self.client.post("/brands", json={
            "organization_id": org.json()["organization_id"], "brand_name": "City"},
            headers=owner)
        created = self.client.post("/locations", json={
            "brand_id": brand.json()["brand_id"], "location_name": "Downtown",
            "timezone": timezone}, headers=owner)
        self.assertEqual(created.status_code, 201, created.text)
        return str(created.json()["location_id"])

    def publisher(self, tenant_id: str) -> str:
        """A stepped-up session that may publish, and did not author.

        Cached per tenant because each one costs two scrypt hashes, which is most of this
        suite's wall-clock -- the same reason `support.py` builds an owner through the
        service layer rather than over HTTP.
        """
        cached = getattr(self, "_publishers", None)
        if cached is None:
            cached = self._publishers = {}
        if tenant_id not in cached:
            cached[tenant_id] = self.stepped_grant(
                tenant_id, ["devices.type.publish", "access.policy.publish",
                            "access.zone.read"])
        return str(cached[tenant_id])

    def live_device(self, tenant_id: str, location_id: str, *,
                    kind: str = "turnstile") -> str:
        """A MOD-021 device in service, which is what an access point stands on."""
        owner = self.headers(tenant_id)
        declared = self.client.post("/fleet/types", json={
            "type_code": f"T{uuid.uuid4().hex[:8].upper()}", "vendor": "Acme",
            "model": "Gate 3000", "kind": kind, "display_name": "Acme Gate 3000",
            "capabilities": ["access.actuate", "credential.read", "telemetry"],
            **self.correlation()}, headers=owner)
        self.assertEqual(declared.status_code, 201, declared.text)
        type_id = declared.json()["type_id"]
        published = self.client.post(
            f"/fleet/types/{type_id}/publish", json=self.correlation(),
            headers=self.headers(tenant_id, self.publisher(tenant_id)))
        self.assertEqual(published.status_code, 200, published.text)

        registered = self.client.post("/fleet", json={
            "type_id": type_id, "location_id": location_id,
            "serial_number": f"SN-{uuid.uuid4().hex[:10].upper()}",
            "display_name": "North turnstile", **self.correlation()}, headers=owner)
        self.assertEqual(registered.status_code, 201, registered.text)
        device_id = str(registered.json()["device_id"])

        start = datetime.now(UTC) - timedelta(minutes=1)
        provisioned = self.client.post(f"/fleet/{device_id}/provision", json={
            "fingerprint": uuid.uuid4().hex + uuid.uuid4().hex,
            "vault_ref": "vault:acme/gate/1",
            "not_before": start.isoformat(),
            "not_after": (start + timedelta(days=90)).isoformat(),
            **self.correlation()}, headers=owner)
        self.assertEqual(provisioned.status_code, 201, provisioned.text)

        commissioned = self.client.post(f"/fleet/{device_id}/commission", json={
            "profile": "fail_safe", "on_egress_path": True,
            "fire_release_is_independent": True, "local_emergency_input": True,
            "evidence_ref": "uri:certs/fire-officer-2026-11",
            "door_description": "north entrance, single leaf",
            **self.correlation()}, headers=owner)
        self.assertEqual(commissioned.status_code, 201, commissioned.text)
        for name in ("power_loss", "edge_agent_crash", "controller_disconnect",
                     "fire_alarm_input", "emergency_unlock", "recovery", "manual_override"):
            passed = self.client.post(
                f"/fleet/{device_id}/commissioning-tests",
                json={"test_name": name, "passed": True, **self.correlation()},
                headers=owner)
            self.assertEqual(passed.status_code, 201, passed.text)
        activated = self.client.post(
            f"/fleet/{device_id}/activate", json=self.correlation(), headers=owner)
        self.assertEqual(activated.status_code, 200, activated.text)
        return device_id

    def zone(self, tenant_id: str, location_id: str, *,
             risk_class: str = "standard") -> str:
        created = self.client.post("/access/zones", json={
            "location_id": location_id, "zone_key": f"z-{uuid.uuid4().hex[:8]}",
            "display_name": "Main floor", "risk_class": risk_class,
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(created.status_code, 201, created.text)
        return str(created.json()["zone_id"])

    def point(self, tenant_id: str, zone_id: str, device_id: str, *,
              direction: str = "entry") -> str:
        created = self.client.post("/access/points", json={
            "zone_id": zone_id, "device_id": device_id, "direction": direction,
            "display_name": "North turnstile", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(created.status_code, 201, created.text)
        return str(created.json()["point_id"])

    def policy(self, tenant_id: str, zone_id: str, **terms: Any) -> str:
        """Drafted by the owner and published by somebody else, which the schema requires."""
        drafted = self.client.post("/access/policies", json={
            "zone_id": zone_id, "requires_entitlement": False,
            **terms, **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(drafted.status_code, 201, drafted.text)
        policy_id = str(drafted.json()["policy_id"])
        published = self.client.post(
            f"/access/policies/{policy_id}/publish", json=self.correlation(),
            headers=self.headers(tenant_id, self.publisher(tenant_id)))
        self.assertEqual(published.status_code, 200, published.text)
        return policy_id

    def person(self, tenant_id: str, **fields: Any) -> str:
        created = self.client.post("/people", json={
            "legal_name": "Jane Member", **fields, **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(created.status_code, 201, created.text)
        return str(created.json()["person_id"])

    def credential(self, tenant_id: str, person_id: str, *, value: str | None = None,
                   kind: str = "nfc_card") -> tuple[str, str]:
        value = value or f"CARD-{uuid.uuid4().hex[:12].upper()}"
        created = self.client.post("/access/credentials", json={
            "person_id": person_id, "kind": kind, "credential_value": value,
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(created.status_code, 201, created.text)
        return str(created.json()["credential_id"]), value

    def floor(self, tenant_id: str | None = None, **policy_terms: Any) -> dict[str, Any]:
        """The whole fixture, since most tests need all of it."""
        tenant_id = tenant_id or self.tenant()
        location_id = self.location(tenant_id)
        device_id = self.live_device(tenant_id, location_id)
        zone_id = self.zone(tenant_id, location_id)
        point_id = self.point(tenant_id, zone_id, device_id)
        policy_id = self.policy(tenant_id, zone_id, **policy_terms)
        person_id = self.person(tenant_id)
        credential_id, value = self.credential(tenant_id, person_id)
        return {"tenant_id": tenant_id, "location_id": location_id,
                "device_id": device_id, "zone_id": zone_id, "point_id": point_id,
                "policy_id": policy_id, "person_id": person_id,
                "credential_id": credential_id, "credential_value": value}

    def present(self, floor: dict[str, Any], *, value: str | None = None,
                headers: dict[str, str] | None = None) -> Any:
        return self.client.post("/access/decisions", json={
            "point_id": floor["point_id"],
            "credential_value": value or floor["credential_value"],
            "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=headers or self.headers(floor["tenant_id"]))


class ZoneAndPointTests(AccessApiTestCase):
    def test_a_zone_carries_the_risk_class_that_bounds_its_offline_authority(self):
        tenant_id = self.tenant()
        location_id = self.location(tenant_id)
        zone_id = self.zone(tenant_id, location_id, risk_class="high_risk")
        detail = self.client.get(f"/access/zones/{zone_id}",
                                 headers=self.headers(tenant_id))
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["risk_class"], "high_risk")

    def test_an_unknown_risk_class_is_refused_rather_than_defaulted(self):
        tenant_id = self.tenant()
        refused = self.client.post("/access/zones", json={
            "location_id": self.location(tenant_id), "zone_key": "z1",
            "display_name": "Main", "risk_class": "medium", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertIn(refused.status_code, (409, 422), refused.text)

    def test_a_malformed_id_answers_422_rather_than_500(self):
        """MOD-009's finding: eight of eight id-bearing routes answered 500 with a database
        exception because no id was shape-checked at the boundary."""
        tenant_id = self.tenant()
        headers = self.headers(tenant_id)
        for method, path, body in (
            ("get", "/access/zones/not-a-uuid", None),
            ("get", "/access/zones/not-a-uuid/occupancy", None),
            ("get", "/access/credentials/not-a-uuid", None),
            ("post", "/access/zones/not-a-uuid/retire",
             {"reason": "closed", **correlation_only()}),
            ("post", "/access/points/not-a-uuid/retire",
             {"reason": "closed", **correlation_only()}),
            ("post", "/access/policies/not-a-uuid/publish", correlation_only()),
            ("post", "/access/emergency/not-a-uuid/review",
             {"note": "reviewed", **correlation_only()}),
        ):
            call = getattr(self.client, method)
            response = (call(path, headers=headers) if body is None
                        else call(path, json=body, headers=headers))
            self.assertEqual(response.status_code, 422, f"{method} {path}: {response.text}")

    def test_a_zones_risk_class_can_be_tightened_and_not_loosened(self):
        """Loosening retroactively extends an authorization somebody has already been given:
        a snapshot issued under the old ceiling keeps running at the new, looser zone."""
        tenant_id = self.tenant()
        zone_id = self.zone(tenant_id, self.location(tenant_id), risk_class="standard")
        headers = self.headers(tenant_id)
        tightened = self.client.post(f"/access/zones/{zone_id}/reclassify", json={
            "risk_class": "high_risk", **self.correlation()}, headers=headers)
        self.assertEqual(tightened.status_code, 200, tightened.text)
        loosened = self.client.post(f"/access/zones/{zone_id}/reclassify", json={
            "risk_class": "standard", **self.correlation()}, headers=headers)
        self.assertEqual(loosened.status_code, 409, loosened.text)

    def test_an_access_point_needs_a_device_that_is_in_service(self):
        """A door standing on a unit nobody commissioned is a door with no safety record.

        **Found by this test on its first run.** The point was created over a device that had
        been registered and nothing else: no safety profile, no commissioning tests, never
        activated. MOD-021 still refused the unlock, so no door opened -- what existed was a
        point that read as commissioned and could never work, with decisions taken at it
        returning `granted` while nothing moved. Paragraph 4175 blocks opening an access point
        in production on a failed or missing commissioning, and declaring the point is putting
        it into production. The refusal is a trigger rather than a service check, for the
        reason the rules file gives: a control the service does is a control the writer that
        is not the service walks past.
        """
        tenant_id = self.tenant()
        location_id = self.location(tenant_id)
        zone_id = self.zone(tenant_id, location_id)
        owner = self.headers(tenant_id)
        declared = self.client.post("/fleet/types", json={
            "type_code": f"T{uuid.uuid4().hex[:8].upper()}", "vendor": "Acme",
            "model": "Gate", "kind": "turnstile", "display_name": "Gate",
            "capabilities": ["access.actuate", "telemetry"], **self.correlation()},
            headers=owner)
        type_id = declared.json()["type_id"]
        self.client.post(f"/fleet/types/{type_id}/publish", json=self.correlation(),
                         headers=self.headers(tenant_id, self.publisher(tenant_id)))
        registered = self.client.post("/fleet", json={
            "type_id": type_id, "location_id": location_id, "serial_number": "SN-X",
            "display_name": "Gate", **self.correlation()}, headers=owner)
        refused = self.client.post("/access/points", json={
            "zone_id": zone_id, "device_id": registered.json()["device_id"],
            "direction": "entry", "display_name": "Gate", **self.correlation()},
            headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)


class PolicyTests(AccessApiTestCase):
    def test_the_author_of_a_policy_cannot_publish_it(self):
        """MOD-017's contract-version argument in a building: these terms decide who gets
        through a door, so the author and the publisher are two people."""
        tenant_id = self.tenant()
        zone_id = self.zone(tenant_id, self.location(tenant_id))
        drafted = self.client.post("/access/policies", json={
            "zone_id": zone_id, "requires_entitlement": False, **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(drafted.status_code, 201, drafted.text)
        refused = self.client.post(
            f"/access/policies/{drafted.json()['policy_id']}/publish",
            json=self.correlation(), headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)

    def test_publishing_retires_whatever_was_live_for_that_zone(self):
        tenant_id = self.tenant()
        zone_id = self.zone(tenant_id, self.location(tenant_id))
        first = self.policy(tenant_id, zone_id)
        second = self.policy(tenant_id, zone_id, anti_passback_seconds=30)
        self.assertNotEqual(first, second)
        detail = self.client.get(f"/access/zones/{zone_id}",
                                 headers=self.headers(tenant_id))
        self.assertEqual(detail.json()["policy"]["policy_id"], second)

    def test_a_draft_decides_nothing(self):
        """Nothing is live until a second person settles it, so a door with only a draft
        refuses rather than falling back to a permissive default."""
        tenant_id = self.tenant()
        location_id = self.location(tenant_id)
        device_id = self.live_device(tenant_id, location_id)
        zone_id = self.zone(tenant_id, location_id)
        point_id = self.point(tenant_id, zone_id, device_id)
        self.client.post("/access/policies", json={
            "zone_id": zone_id, "requires_entitlement": False, **self.correlation()},
            headers=self.headers(tenant_id))
        person_id = self.person(tenant_id)
        _, value = self.credential(tenant_id, person_id)
        presented = self.client.post("/access/decisions", json={
            "point_id": point_id, "credential_value": value,
            "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertIn(presented.status_code, (201, 409), presented.text)
        if presented.status_code == 201:
            self.assertFalse(presented.json()["granted"], presented.text)

    def test_an_unbounded_policy_number_answers_422_rather_than_500(self):
        """MOD-011's, MOD-012's and MOD-013's finding, three times over: psycopg raises
        `NumericValueOutOfRange`, which is a `DataError` rather than the `CheckViolation`
        the handlers catch."""
        tenant_id = self.tenant()
        zone_id = self.zone(tenant_id, self.location(tenant_id))
        for field, value in (("anti_passback_seconds", 10**12),
                             ("capacity", 10**12),
                             ("max_balance_minor", 10**15),
                             ("min_age_years", 10**6),
                             ("opens_minute", 10**9)):
            refused = self.client.post("/access/policies", json={
                "zone_id": zone_id, field: value, **self.correlation()},
                headers=self.headers(tenant_id))
            self.assertEqual(refused.status_code, 422, f"{field}: {refused.text}")


class DecisionTests(AccessApiTestCase):
    def test_a_member_in_good_standing_is_admitted_and_the_decision_is_recorded(self):
        floor = self.floor()
        presented = self.present(floor)
        self.assertEqual(presented.status_code, 201, presented.text)
        body = presented.json()
        self.assertTrue(body["granted"])
        self.assertEqual(body["code"], "granted")

        history = self.client.get(
            f"/access/decisions?zone_id={floor['zone_id']}",
            headers=self.headers(floor["tenant_id"]))
        self.assertEqual(history.status_code, 200, history.text)
        self.assertTrue(history.json()["decisions"])

    def test_an_unknown_credential_is_refused_without_naming_anybody(self):
        floor = self.floor()
        presented = self.present(floor, value="CARD-NOBODY-HAS-THIS")
        self.assertEqual(presented.status_code, 201, presented.text)
        body = presented.json()
        self.assertFalse(body["granted"])
        self.assertEqual(body["code"], "credential_unknown")
        self.assertNotIn(floor["person_id"], presented.text)

    def test_a_revoked_credential_stops_opening_the_door(self):
        floor = self.floor()
        revoked = self.client.post(
            f"/access/credentials/{floor['credential_id']}/revoke",
            json={"reason": "reported lost", **self.correlation()},
            headers=self.headers(floor["tenant_id"]))
        self.assertEqual(revoked.status_code, 200, revoked.text)
        presented = self.present(floor)
        self.assertEqual(presented.json()["code"], "credential_revoked", presented.text)

    def test_the_same_presentation_twice_is_one_decision(self):
        """A reader that times out and retries must not create a second decision, and must
        not be told a different answer the second time."""
        floor = self.floor()
        key = str(uuid.uuid4())
        body = {"point_id": floor["point_id"],
                "credential_value": floor["credential_value"],
                "idempotency_key": key, **self.correlation()}
        first = self.client.post("/access/decisions", json=body,
                                 headers=self.headers(floor["tenant_id"]))
        second = self.client.post("/access/decisions", json={**body, **self.correlation()},
                                  headers=self.headers(floor["tenant_id"]))
        self.assertEqual(first.status_code, 201, first.text)
        self.assertIn(second.status_code, (200, 201), second.text)
        self.assertEqual(first.json()["decision_id"], second.json()["decision_id"])

    def test_an_exit_reader_decides_nothing(self):
        """Paragraph 4177, as a refusal rather than a policy that happens to allow it."""
        tenant_id = self.tenant()
        location_id = self.location(tenant_id)
        device_id = self.live_device(tenant_id, location_id)
        zone_id = self.zone(tenant_id, location_id)
        exit_point = self.point(tenant_id, zone_id, device_id, direction="exit")
        self.policy(tenant_id, zone_id)
        person_id = self.person(tenant_id)
        _, value = self.credential(tenant_id, person_id)
        presented = self.client.post("/access/decisions", json={
            "point_id": exit_point, "credential_value": value,
            "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=self.headers(tenant_id))
        if presented.status_code == 201:
            self.assertEqual(presented.json()["code"], "point_not_an_entry", presented.text)
        else:
            self.assertEqual(presented.status_code, 409, presented.text)

    def test_leaving_is_recorded_without_being_decided(self):
        """An exit event is written with no decision to cite, which is what makes egress
        software-independent rather than software-permitted."""
        tenant_id = self.tenant()
        location_id = self.location(tenant_id)
        device_id = self.live_device(tenant_id, location_id)
        zone_id = self.zone(tenant_id, location_id)
        exit_point = self.point(tenant_id, zone_id, device_id, direction="exit")
        person_id = self.person(tenant_id)
        _, value = self.credential(tenant_id, person_id)
        recorded = self.client.post("/access/events", json={
            "point_id": exit_point, "direction": "exit", "credential_value": value,
            "occurred_at": datetime.now(UTC).isoformat(), "source": "online",
            "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(recorded.status_code, 201, recorded.text)


class PublicReasonTests(AccessApiTestCase):
    """Paragraph 1944, the Critical Control: a denial never reveals sensitive financial or
    health information publicly."""

    def test_a_restricted_refusal_shows_the_member_one_discreet_line(self):
        floor = self.floor(requires_entitlement=True)
        presented = self.present(floor)
        self.assertEqual(presented.status_code, 201, presented.text)
        body = presented.json()
        self.assertFalse(body["granted"])
        self.assertEqual(body["code"], "no_entitlement")
        self.assertEqual(body["public_reason"], "please see the front desk")
        # And the response a reader gets carries no private half at all: this payload goes to
        # the device above the turnstile.
        self.assertNotIn("private_reason", body)
        self.assertTrue(body["reason_withheld"])

    def test_the_private_half_needs_its_own_permission(self):
        """`access.decision.read` returns the public code a turnstile may display; only
        `access.decision.read_reason`, which is financial class, returns the rest."""
        floor = self.floor(requires_entitlement=True)
        self.present(floor)
        reader = self.grant(floor["tenant_id"], ["access.decision.read"])
        narrow = self.client.get(
            f"/access/decisions?zone_id={floor['zone_id']}",
            headers=self.headers(floor["tenant_id"], reader))
        self.assertEqual(narrow.status_code, 200, narrow.text)
        decisions = narrow.json()["decisions"]
        self.assertTrue(decisions)
        for decision in decisions:
            self.assertIsNone(decision.get("private_reason"), narrow.text)

        full = self.client.get(
            f"/access/decisions?zone_id={floor['zone_id']}",
            headers=self.headers(floor["tenant_id"]))
        self.assertEqual(full.status_code, 200, full.text)
        self.assertTrue(
            any(d.get("private_reason") for d in full.json()["decisions"]), full.text)

    def test_a_credential_read_never_says_which_doors_it_opens(self):
        """A route answering that turns one found card into a map of a building."""
        floor = self.floor()
        status = self.client.get(
            f"/access/credentials/{floor['credential_id']}",
            headers=self.headers(floor["tenant_id"]))
        self.assertEqual(status.status_code, 200, status.text)
        self.assertNotIn(floor["zone_id"], status.text)
        self.assertNotIn(floor["point_id"], status.text)
        self.assertNotIn(floor["credential_value"], status.text)


class OverrideTests(AccessApiTestCase):
    def test_an_override_is_its_own_decision_and_the_refusal_stays_beside_it(self):
        floor = self.floor(requires_entitlement=True)
        refused = self.present(floor)
        self.assertFalse(refused.json()["granted"])

        overridden = self.client.post("/access/decisions/override", json={
            "point_id": floor["point_id"], "person_id": floor["person_id"],
            "reason": "her card is in the car, I know her",
            "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=self.headers(floor["tenant_id"]))
        self.assertEqual(overridden.status_code, 201, overridden.text)
        self.assertEqual(overridden.json()["code"], "granted_by_override")

        history = self.client.get(
            f"/access/decisions?zone_id={floor['zone_id']}",
            headers=self.headers(floor["tenant_id"]))
        codes = [d["code"] for d in history.json()["decisions"]]
        self.assertIn("granted_by_override", codes)
        self.assertIn("no_entitlement", codes)

    def test_an_override_states_why(self):
        floor = self.floor()
        for blank in ("", "   ", "\t"):
            refused = self.client.post("/access/decisions/override", json={
                "point_id": floor["point_id"], "person_id": floor["person_id"],
                "reason": blank, "idempotency_key": str(uuid.uuid4()),
                **self.correlation()}, headers=self.headers(floor["tenant_id"]))
            self.assertIn(refused.status_code, (409, 422), f"{blank!r}: {refused.text}")

    def test_an_override_needs_more_than_the_permission_to_present_a_card(self):
        """The routine permission a turnstile holds must not buy the one that admits
        somebody against the policy."""
        floor = self.floor(requires_entitlement=True)
        reader = self.grant(
            floor["tenant_id"], ["access.decision.evaluate", "access.event.record"])
        refused = self.client.post("/access/decisions/override", json={
            "point_id": floor["point_id"], "person_id": floor["person_id"],
            "reason": "I know her", "idempotency_key": str(uuid.uuid4()),
            **self.correlation()}, headers=self.headers(floor["tenant_id"], reader))
        self.assertEqual(refused.status_code, 403, refused.text)


class EmergencyTests(AccessApiTestCase):
    def test_an_unlock_can_be_ordered_on_a_password_only_session(self):
        """Paragraph 4178 says dual approval "where time permits", and a fire is the case
        where it does not. A step-up that fails during an evacuation is a door that stays
        shut, so the second person moves to the review."""
        floor = self.floor()
        responder = self.grant(
            floor["tenant_id"], ["access.emergency.unlock", "access.zone.read"])
        ordered = self.client.post("/access/emergency", json={
            "zone_id": floor["zone_id"], "reason": "fire alarm, north stair",
            "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=self.headers(floor["tenant_id"], responder))
        self.assertEqual(ordered.status_code, 201, ordered.text)
        self.assertGreaterEqual(ordered.json()["points_released"], 1)

    def test_the_reviewer_is_not_whoever_ordered_it(self):
        floor = self.floor()
        ordered = self.client.post("/access/emergency", json={
            "zone_id": floor["zone_id"], "reason": "fire alarm, north stair",
            "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=self.headers(floor["tenant_id"]))
        self.assertEqual(ordered.status_code, 201, ordered.text)
        unlock_id = ordered.json()["unlock_id"]

        same_person = self.client.post(
            f"/access/emergency/{unlock_id}/review",
            json={"note": "all clear", **self.correlation()},
            headers=self.headers(floor["tenant_id"]))
        self.assertEqual(same_person.status_code, 409, same_person.text)

        other = self.grant(floor["tenant_id"], ["access.emergency.unlock"])
        reviewed = self.client.post(
            f"/access/emergency/{unlock_id}/review",
            json={"note": "all clear, fire service attended", **self.correlation()},
            headers=self.headers(floor["tenant_id"], other))
        self.assertEqual(reviewed.status_code, 200, reviewed.text)

    def test_an_unlock_states_why(self):
        floor = self.floor()
        refused = self.client.post("/access/emergency", json={
            "zone_id": floor["zone_id"], "reason": "  ",
            "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=self.headers(floor["tenant_id"]))
        self.assertIn(refused.status_code, (409, 422), refused.text)


class OccupancyTests(AccessApiTestCase):
    def test_every_occupancy_read_says_it_is_never_a_muster_source(self):
        """Paragraph 4180. A number without the disclaimer is the one somebody counts heads
        against during an evacuation."""
        floor = self.floor()
        read = self.client.get(f"/access/zones/{floor['zone_id']}/occupancy",
                               headers=self.headers(floor["tenant_id"]))
        self.assertEqual(read.status_code, 200, read.text)
        body = read.json()
        self.assertIn("muster", body["detail"])
        self.assertIn(body["confidence"], ("measured", "advisory"))

    def test_a_zone_with_only_an_entry_reader_is_advisory(self):
        floor = self.floor()
        read = self.client.get(f"/access/zones/{floor['zone_id']}/occupancy",
                               headers=self.headers(floor["tenant_id"]))
        self.assertEqual(read.json()["confidence"], "advisory", read.text)

    def test_no_occupancy_count_is_stored_anywhere_a_writer_could_drift_it(self):
        """MOD-018's argument for computing every balance, applied to a number somebody might
        use to decide whether a room has been evacuated.

        **The ban is on a count that can be rewritten**, which is the one that drifts from the
        events it was derived from. `acc_decisions.occupancy_seen` is what a single decision
        observed, on a table with no UPDATE grant for any runtime role -- evidence of what the
        door was told, not a running total, and re-deriving it would answer a different
        question. So the sweep asks which occupancy-shaped columns are *writable*, which is
        the property, rather than which ones exist, which was a name list that caught its own
        module's evidence.
        """
        from app.db import tenant_scope

        floor = self.floor()
        with tenant_scope(self._tenant_pool, floor["tenant_id"]) as conn:
            writable = conn.execute(
                "select c.table_name, c.column_name from information_schema.columns c"
                " where c.table_schema = 'plt01'"
                "   and (c.column_name like '%occupan%' or c.column_name like '%head_count%'"
                "        or c.column_name like '%inside%' or c.column_name like '%people_count%')"
                "   and (has_column_privilege('veyro_cp_app',"
                "          'plt01.' || c.table_name, c.column_name, 'UPDATE')"
                "     or has_column_privilege('veyro_cp_worker',"
                "          'plt01.' || c.table_name, c.column_name, 'UPDATE'))"
                " order by 1, 2").fetchall()
        self.assertEqual(list(writable), [])


class GateTests(AccessApiTestCase):
    """Every route is gated, and the classes are not decorative."""

    def test_a_session_holding_nothing_is_refused_every_write(self):
        floor = self.floor()
        nobody = self.grant(floor["tenant_id"], [])
        headers = self.headers(floor["tenant_id"], nobody)
        for path, body in (
            ("/access/zones", {"location_id": floor["location_id"], "zone_key": "z",
                               "display_name": "Z", "risk_class": "standard",
                               **correlation_only()}),
            ("/access/points", {"zone_id": floor["zone_id"],
                                "device_id": floor["device_id"], "direction": "entry",
                                "display_name": "P", **correlation_only()}),
            ("/access/policies", {"zone_id": floor["zone_id"], **correlation_only()}),
            ("/access/credentials", {"person_id": floor["person_id"], "kind": "nfc_card",
                                     "credential_value": "X", **correlation_only()}),
            ("/access/decisions", {"point_id": floor["point_id"],
                                   "credential_value": "X",
                                   "idempotency_key": str(uuid.uuid4()),
                                   **correlation_only()}),
            ("/access/emergency", {"zone_id": floor["zone_id"], "reason": "fire",
                                   "idempotency_key": str(uuid.uuid4()),
                                   **correlation_only()}),
        ):
            refused = self.client.post(path, json=body, headers=headers)
            self.assertEqual(refused.status_code, 403, f"{path}: {refused.text}")

    def test_a_read_permission_does_not_buy_a_write(self):
        floor = self.floor()
        reader = self.grant(floor["tenant_id"], ["access.zone.read",
                                                 "access.decision.read"])
        refused = self.client.post("/access/zones", json={
            "location_id": floor["location_id"], "zone_key": "z2",
            "display_name": "Z2", "risk_class": "standard", **correlation_only()},
            headers=self.headers(floor["tenant_id"], reader))
        self.assertEqual(refused.status_code, 403, refused.text)

    def test_issuing_a_credential_needs_a_stepped_up_session_and_revoking_does_not(self):
        """The asymmetry is the module's: a card reported stolen at seven in the morning has
        to be killable by whoever is on the desk, and handing one out is how somebody gets
        into the building at all."""
        floor = self.floor()
        weak = self.grant(floor["tenant_id"],
                          ["access.credential.issue", "access.credential.revoke"])
        headers = self.headers(floor["tenant_id"], weak)
        refused = self.client.post("/access/credentials", json={
            "person_id": floor["person_id"], "kind": "nfc_card",
            "credential_value": f"CARD-{uuid.uuid4().hex[:8]}", **correlation_only()},
            headers=headers)
        self.assertEqual(refused.status_code, 403, refused.text)

        revoked = self.client.post(
            f"/access/credentials/{floor['credential_id']}/revoke",
            json={"reason": "reported lost", **correlation_only()}, headers=headers)
        self.assertEqual(revoked.status_code, 200, revoked.text)

    def test_no_access_route_is_reachable_without_a_session(self):
        floor = self.floor()
        bare = {"X-Veyro-Tenant": floor["tenant_id"]}
        for path in (f"/access/zones/{floor['zone_id']}",
                     f"/access/zones/{floor['zone_id']}/occupancy",
                     f"/access/credentials/{floor['credential_id']}",
                     "/access/decisions"):
            refused = self.client.get(path, headers=bare)
            self.assertIn(refused.status_code, (401, 422), f"{path}: {refused.text}")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

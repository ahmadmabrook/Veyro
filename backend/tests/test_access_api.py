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


class ZoneListTests(AccessApiTestCase):
    """The door board, which is the read a front desk actually enters this module through."""

    def test_a_zone_with_no_live_policy_says_so_rather_than_reading_as_unrestricted(self):
        tenant_id = self.tenant()
        location_id = self.location(tenant_id)
        device_id = self.live_device(tenant_id, location_id)
        zone_id = self.zone(tenant_id, location_id)
        self.point(tenant_id, zone_id, device_id)
        listed = self.client.get("/access/zones", headers=self.headers(tenant_id))
        self.assertEqual(listed.status_code, 200, listed.text)
        rows = {z["zone_id"]: z for z in listed.json()["zones"]}
        self.assertIsNone(rows[zone_id]["live_policy_version"], listed.text)
        self.assertEqual(rows[zone_id]["entry_points"], 1)
        self.assertEqual(rows[zone_id]["exit_points"], 0)

        self.policy(tenant_id, zone_id)
        again = self.client.get("/access/zones", headers=self.headers(tenant_id))
        self.assertEqual(
            {z["zone_id"]: z for z in again.json()["zones"]}[zone_id]["live_policy_version"],
            1, again.text)

    def test_a_retired_zone_is_out_of_the_board_unless_asked_for(self):
        tenant_id = self.tenant()
        zone_id = self.zone(tenant_id, self.location(tenant_id))
        retired = self.client.post(f"/access/zones/{zone_id}/retire", json={
            "reason": "the room was knocked through", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(retired.status_code, 200, retired.text)
        board = self.client.get("/access/zones", headers=self.headers(tenant_id))
        self.assertNotIn(zone_id, [z["zone_id"] for z in board.json()["zones"]])
        everything = self.client.get(
            "/access/zones?include_retired=true", headers=self.headers(tenant_id))
        self.assertIn(zone_id, [z["zone_id"] for z in everything.json()["zones"]])

    def test_the_board_carries_the_risk_class_ceiling_it_is_read_against(self):
        tenant_id = self.tenant()
        location_id = self.location(tenant_id)
        self.zone(tenant_id, location_id, risk_class="high_risk")
        board = self.client.get("/access/zones", headers=self.headers(tenant_id))
        high = [z for z in board.json()["zones"] if z["risk_class"] == "high_risk"]
        self.assertTrue(high, board.text)
        self.assertEqual(high[0]["snapshot_ceiling_seconds"], 2 * 3600)

    def test_the_board_needs_the_read_permission(self):
        tenant_id = self.tenant()
        self.zone(tenant_id, self.location(tenant_id))
        nobody = self.grant(tenant_id, [])
        refused = self.client.get(
            "/access/zones", headers=self.headers(tenant_id, nobody))
        self.assertEqual(refused.status_code, 403, refused.text)

    def test_another_tenants_zones_are_not_on_this_board(self):
        first = self.tenant()
        self.zone(first, self.location(first))
        second = self.tenant()
        board = self.client.get("/access/zones", headers=self.headers(second))
        self.assertEqual(board.status_code, 200, board.text)
        self.assertEqual(board.json()["zones"], [], board.text)


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
        # **The public code, not the real one.** Both reviewers found that the split gated
        # the sentence and not the fact: `no_entitlement` beside "please see the front desk"
        # tells whoever reads the screen above the turnstile that this named person has no
        # membership that admits them.
        self.assertEqual(body["code"], "see_front_desk")
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


class ReviewRegressionTests(AccessApiTestCase):
    """One test per blocking finding from the three independent reviews of MOD-022.

    Named for the attacks rather than the fixes, because the fix is what changes and the
    attack is what has to keep failing. Every one of these passed before the fix and fails
    without it; the four absences the reviewers named -- no rotating credential, no
    `both`-facing point, no reused idempotency key, no capacity behaviour -- are the reason
    the defects shipped inside a green 31-test suite.
    """

    def rotating(self, floor: dict[str, Any], **overrides: Any) -> dict[str, Any]:
        """A presentation of a rotating token, with a live window by default."""
        now = datetime.now(UTC)
        body = {
            "point_id": floor["point_id"], "credential_value": floor["credential_value"],
            "idempotency_key": str(uuid.uuid4()),
            "rotation_counter": 1, "nonce": uuid.uuid4().hex,
            "token_issued_at": now.isoformat(),
            "token_expires_at": (now + timedelta(seconds=30)).isoformat(),
            **self.correlation(),
        }
        body.update(overrides)
        return body

    def qr_floor(self) -> dict[str, Any]:
        floor = self.floor()
        person_id = self.person(floor["tenant_id"])
        credential_id, value = self.credential(
            floor["tenant_id"], person_id, kind="qr_rotating")
        return {**floor, "person_id": person_id, "credential_id": credential_id,
                "credential_value": value}

    # ------------------------------------------------------------------ the credential kind

    def test_a_reader_cannot_name_the_credential_kind_and_turn_off_its_controls(self):
        """**A photographed QR replayed for ever.**

        `kind` was a free-text body field and it decided which controls ran: the token
        window, the clock refusal and the replay cache are each guarded on the credential
        being a rotating one. A reviewer sent `{"kind": "nfc_card"}` with a month-old token
        and was admitted, repeatedly, each time issuing MOD-021's unlock.
        """
        floor = self.qr_floor()
        stale = datetime.now(UTC) - timedelta(days=30)
        refused = self.client.post("/access/decisions", json=self.rotating(
            floor, token_issued_at=stale.isoformat(),
            token_expires_at=(stale + timedelta(seconds=30)).isoformat(),
            kind="nfc_card"), headers=self.headers(floor["tenant_id"]))
        # The body no longer declares `kind` at all, so an extra key is either ignored or
        # refused -- what must not happen is a grant.
        self.assertIn(refused.status_code, (201, 422), refused.text)
        if refused.status_code == 201:
            self.assertFalse(refused.json()["granted"], refused.text)
            self.assertEqual(refused.json()["code"], "credential_window", refused.text)

    def test_a_token_outside_its_window_is_refused(self):
        floor = self.qr_floor()
        stale = datetime.now(UTC) - timedelta(hours=1)
        refused = self.client.post("/access/decisions", json=self.rotating(
            floor, token_issued_at=stale.isoformat(),
            token_expires_at=(stale + timedelta(seconds=30)).isoformat()),
            headers=self.headers(floor["tenant_id"]))
        self.assertEqual(refused.status_code, 201, refused.text)
        self.assertEqual(refused.json()["code"], "credential_window", refused.text)

    def test_a_replayed_token_is_refused_and_recorded_rather_than_answering_500(self):
        """**The refusal paragraph 4183 calls the core of the design was unreachable.**

        The replay insert caught its unique violation and carried on in a transaction
        PostgreSQL had already aborted, so the next statement raised and the caller got a
        500 -- and `credential_replayed` was a declared reason code no path could write.
        """
        floor = self.qr_floor()
        body = self.rotating(floor)
        first = self.client.post("/access/decisions", json=body,
                                 headers=self.headers(floor["tenant_id"]))
        self.assertEqual(first.status_code, 201, first.text)
        self.assertTrue(first.json()["granted"], first.text)

        again = self.client.post("/access/decisions", json={
            **body, "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=self.headers(floor["tenant_id"]))
        self.assertEqual(again.status_code, 201, again.text)
        self.assertFalse(again.json()["granted"], again.text)
        self.assertEqual(again.json()["code"], "credential_replayed", again.text)

        history = self.client.get(
            f"/access/decisions?zone_id={floor['zone_id']}",
            headers=self.headers(floor["tenant_id"]))
        self.assertIn("credential_replayed",
                      [d["code"] for d in history.json()["decisions"]], history.text)

    # ------------------------------------------------------------------ idempotency

    def test_a_reused_key_with_a_different_card_is_refused_not_answered(self):
        """**A revoked card was answered `granted`** from the previous member's row."""
        floor = self.floor()
        other_person = self.person(floor["tenant_id"])
        other_id, other_value = self.credential(floor["tenant_id"], other_person)
        key = "till-shift-7"

        first = self.client.post("/access/decisions", json={
            "point_id": floor["point_id"], "credential_value": floor["credential_value"],
            "idempotency_key": key, **self.correlation()},
            headers=self.headers(floor["tenant_id"]))
        self.assertEqual(first.status_code, 201, first.text)

        self.client.post(f"/access/credentials/{other_id}/revoke", json={
            "reason": "reported stolen", **self.correlation()},
            headers=self.headers(floor["tenant_id"]))
        reused = self.client.post("/access/decisions", json={
            "point_id": floor["point_id"], "credential_value": other_value,
            "idempotency_key": key, **self.correlation()},
            headers=self.headers(floor["tenant_id"]))
        self.assertEqual(reused.status_code, 409, reused.text)
        self.assertNotIn("granted_by", reused.text)

    def test_an_override_cannot_be_answered_from_an_ordinary_decisions_key(self):
        """**The cheapest permission read the authority of the most expensive one.**

        `acc_decisions.idempotency_key` is one column, so a presentation and an override
        shared a namespace: an override made under a key, then a revoked card presented
        under the same key on the routine permission, was answered `granted_by_override`.
        """
        floor = self.floor()
        key = "shift-counter-12"
        overridden = self.client.post("/access/decisions/override", json={
            "point_id": floor["point_id"], "person_id": floor["person_id"],
            "reason": "I know her", "idempotency_key": key, **self.correlation()},
            headers=self.headers(floor["tenant_id"]))
        self.assertEqual(overridden.status_code, 201, overridden.text)

        self.client.post(f"/access/credentials/{floor['credential_id']}/revoke", json={
            "reason": "reported stolen", **self.correlation()},
            headers=self.headers(floor["tenant_id"]))
        presented = self.client.post("/access/decisions", json={
            "point_id": floor["point_id"], "credential_value": floor["credential_value"],
            "idempotency_key": key, **self.correlation()},
            headers=self.headers(floor["tenant_id"]))
        self.assertEqual(presented.status_code, 201, presented.text)
        self.assertFalse(presented.json()["granted"], presented.text)
        self.assertEqual(presented.json()["code"], "credential_revoked", presented.text)

    def test_an_override_retry_is_answered_from_what_was_recorded(self):
        """It returned a fabricated success without reading the row, so a staff member was
        told an override had happened while the member was still refused."""
        floor = self.floor(requires_entitlement=True)
        key = str(uuid.uuid4())
        refused = self.client.post("/access/decisions", json={
            "point_id": floor["point_id"], "credential_value": floor["credential_value"],
            "idempotency_key": key, **self.correlation()},
            headers=self.headers(floor["tenant_id"]))
        self.assertFalse(refused.json()["granted"], refused.text)
        # The same key, now on the override: different namespace, so this is a fresh act.
        overridden = self.client.post("/access/decisions/override", json={
            "point_id": floor["point_id"], "person_id": floor["person_id"],
            "reason": "card left at home", "idempotency_key": key, **self.correlation()},
            headers=self.headers(floor["tenant_id"]))
        self.assertEqual(overridden.status_code, 201, overridden.text)
        self.assertFalse(overridden.json().get("repeated"), overridden.text)
        codes = [d["code"] for d in self.client.get(
            f"/access/decisions?zone_id={floor['zone_id']}",
            headers=self.headers(floor["tenant_id"])).json()["decisions"]]
        self.assertIn("granted_by_override", codes)

    def test_an_emergency_key_reused_for_another_zone_is_refused(self):
        """**It reported the second zone released when nothing had been.** During a fire,
        with the response omitting the zone so the caller could not tell."""
        floor = self.floor()
        second_zone = self.zone(floor["tenant_id"], floor["location_id"])
        key = "incident-2026-11-18"
        first = self.client.post("/access/emergency", json={
            "zone_id": floor["zone_id"], "reason": "fire alarm, north stair",
            "idempotency_key": key, **self.correlation()},
            headers=self.headers(floor["tenant_id"]))
        self.assertEqual(first.status_code, 201, first.text)

        second = self.client.post("/access/emergency", json={
            "zone_id": second_zone, "reason": "fire alarm, south stair",
            "idempotency_key": key, **self.correlation()},
            headers=self.headers(floor["tenant_id"]))
        self.assertEqual(second.status_code, 409, second.text)

    def test_an_emergency_repeat_names_the_zone_it_released(self):
        floor = self.floor()
        key = str(uuid.uuid4())
        body = {"zone_id": floor["zone_id"], "reason": "fire alarm",
                "idempotency_key": key, **self.correlation()}
        self.client.post("/access/emergency", json=body,
                         headers=self.headers(floor["tenant_id"]))
        again = self.client.post("/access/emergency", json={**body, **self.correlation()},
                                 headers=self.headers(floor["tenant_id"]))
        self.assertEqual(again.status_code, 201, again.text)
        self.assertTrue(again.json()["repeated"])
        self.assertEqual(again.json()["zone_id"], floor["zone_id"], again.text)

    # ------------------------------------------------------------------ egress and capacity

    def test_a_both_facing_lane_decides_nothing_on_the_way_out(self):
        """**Paragraph 4177, reached by wiring the ordinary hardware.**

        A `both` lane is one turnstile that reads each way -- the arrangement that makes a
        zone's occupancy `measured`. Every presentation at one was evaluated as an entry, so
        a reviewer walked a member in and then refused them on the way out.
        """
        tenant_id = self.tenant()
        location_id = self.location(tenant_id)
        device_id = self.live_device(tenant_id, location_id)
        zone_id = self.zone(tenant_id, location_id)
        point_id = self.point(tenant_id, zone_id, device_id, direction="both")
        self.policy(tenant_id, zone_id, anti_passback_seconds=600)
        person_id = self.person(tenant_id)
        _, value = self.credential(tenant_id, person_id)

        entering = self.client.post("/access/decisions", json={
            "point_id": point_id, "credential_value": value,
            "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(entering.status_code, 201, entering.text)
        self.assertTrue(entering.json()["granted"], entering.text)

        leaving = self.client.post("/access/decisions", json={
            "point_id": point_id, "credential_value": value,
            "reported_direction": "exit", "idempotency_key": str(uuid.uuid4()),
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(leaving.status_code, 201, leaving.text)
        self.assertEqual(leaving.json()["code"], "point_not_an_entry", leaving.text)
        # And no anti-passback refusal, which is what the member was given before.
        self.assertNotEqual(leaving.json()["code"], "anti_passback")

    def test_a_capacity_zone_with_one_reader_does_not_refuse_on_a_number_it_calls_advisory(self):
        """**A studio with a capacity stopped working after that many lifetime entries.**

        `_inside` counted every event the zone had ever seen and `decide` refused on it, with
        no DELETE grant to bring it down -- so the only remedy was a new policy, which is two
        acts by two people. Weaponisable from the weakest write permission in the module.
        """
        floor = self.floor(capacity=1)
        headers = self.headers(floor["tenant_id"])
        for _ in range(3):
            recorded = self.client.post("/access/events", json={
                "point_id": floor["point_id"], "direction": "entry",
                "occurred_at": datetime.now(UTC).isoformat(), "source": "online",
                "idempotency_key": str(uuid.uuid4()), **self.correlation()},
                headers=headers)
            self.assertEqual(recorded.status_code, 201, recorded.text)

        presented = self.present(floor)
        self.assertEqual(presented.status_code, 201, presented.text)
        self.assertNotEqual(presented.json()["code"], "zone_at_capacity", presented.text)
        self.assertTrue(presented.json()["granted"], presented.text)

    # ------------------------------------------------------------------ the rest

    def test_a_naive_timestamp_answers_422_rather_than_500(self):
        """The commonest thing an embedded reader emits, 500ing both high-volume routes."""
        floor = self.floor()
        headers = self.headers(floor["tenant_id"])
        naive = "2026-11-19T00:00:00"
        refused = self.client.post("/access/events", json={
            "point_id": floor["point_id"], "direction": "entry", "occurred_at": naive,
            "source": "online", "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=headers)
        self.assertEqual(refused.status_code, 422, refused.text)

        ancient = self.client.post("/access/decisions", json={
            "point_id": floor["point_id"], "credential_value": floor["credential_value"],
            "token_issued_at": "0001-01-01T00:00:00Z",
            "idempotency_key": str(uuid.uuid4()), **self.correlation()}, headers=headers)
        self.assertEqual(ancient.status_code, 422, ancient.text)

    def test_an_override_at_a_retired_point_is_a_refusal_not_a_500(self):
        floor = self.floor()
        headers = self.headers(floor["tenant_id"])
        retired = self.client.post(f"/access/points/{floor['point_id']}/retire", json={
            "reason": "lane removed", **self.correlation()}, headers=headers)
        self.assertEqual(retired.status_code, 200, retired.text)
        refused = self.client.post("/access/decisions/override", json={
            "point_id": floor["point_id"], "person_id": floor["person_id"],
            "reason": "I know her", "idempotency_key": str(uuid.uuid4()),
            **self.correlation()}, headers=headers)
        self.assertEqual(refused.status_code, 409, refused.text)

    def test_a_credential_read_needs_its_own_permission_and_withholds_the_reason(self):
        """`access.zone.read` is a claim about zones, and the revocation reason is prose a
        desk typed -- "she left it at the oncology clinic" is the module's own example."""
        floor = self.floor()
        self.client.post(f"/access/credentials/{floor['credential_id']}/revoke", json={
            "reason": "left at the oncology clinic on Tuesday", **self.correlation()},
            headers=self.headers(floor["tenant_id"]))

        zones_only = self.grant(floor["tenant_id"], ["access.zone.read"])
        refused = self.client.get(
            f"/access/credentials/{floor['credential_id']}",
            headers=self.headers(floor["tenant_id"], zones_only))
        self.assertEqual(refused.status_code, 403, refused.text)

        reader = self.grant(floor["tenant_id"], ["access.credential.read"])
        allowed = self.client.get(
            f"/access/credentials/{floor['credential_id']}",
            headers=self.headers(floor["tenant_id"], reader))
        self.assertEqual(allowed.status_code, 200, allowed.text)
        self.assertIsNone(allowed.json()["revoke_reason"], allowed.text)
        self.assertTrue(allowed.json()["reason_withheld"], allowed.text)
        self.assertNotIn("oncology", allowed.text)

    def test_the_restricted_code_does_not_reach_a_routine_decision_read(self):
        floor = self.floor(requires_entitlement=True)
        self.present(floor)
        reader = self.grant(floor["tenant_id"], ["access.decision.read"])
        narrow = self.client.get(
            f"/access/decisions?zone_id={floor['zone_id']}",
            headers=self.headers(floor["tenant_id"], reader))
        self.assertEqual(narrow.status_code, 200, narrow.text)
        self.assertNotIn("no_entitlement", narrow.text)
        self.assertIn("see_front_desk", narrow.text)


class VisitTests(AccessApiTestCase):
    """ADM-CC-01's third metric: "VISITS TODAY · 218 · usual for a Wednesday"."""

    def entry(self, floor: dict[str, Any], *, when: datetime | None = None) -> None:
        recorded = self.client.post("/access/events", json={
            "point_id": floor["point_id"], "direction": "entry",
            "credential_value": floor["credential_value"],
            "occurred_at": (when or datetime.now(UTC)).isoformat(), "source": "online",
            "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=self.headers(floor["tenant_id"]))
        self.assertEqual(recorded.status_code, 201, recorded.text)

    def test_an_entry_today_is_counted_against_its_own_location(self):
        floor = self.floor()
        self.entry(floor)
        read = self.client.get("/access/visits",
                               headers=self.headers(floor["tenant_id"]))
        self.assertEqual(read.status_code, 200, read.text)
        body = read.json()
        self.assertEqual(body["entries"], 1)
        row = next(r for r in body["locations"] if r["location_id"] == floor["location_id"])
        self.assertEqual(row["entries"], 1)
        self.assertEqual(row["timezone"], "Asia/Amman")

    def test_an_exit_is_not_a_visit(self):
        """MOD-022 keeps decisions and events apart, and directions apart with them. A count
        that added exits would roughly double on a zone that reads both ways."""
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
        read = self.client.get("/access/visits", headers=self.headers(tenant_id))
        self.assertEqual(read.json()["entries"], 0, read.text)

    def test_no_prior_same_weekday_reports_null_rather_than_zero(self):
        """"Usual for a Wednesday" is a claim, and a tenant four days old cannot make it.

        Zero would read as "nobody normally comes", which is the confident wrong answer on a
        metric whose whole job is to say whether today is unusual.
        """
        floor = self.floor()
        self.entry(floor)
        read = self.client.get("/access/visits",
                               headers=self.headers(floor["tenant_id"]))
        body = read.json()
        row = next(r for r in body["locations"] if r["location_id"] == floor["location_id"])
        self.assertIsNone(row["usual_for_this_weekday"])
        self.assertEqual(row["weekdays_compared"], 0)
        self.assertIn("null", body["no_baseline_is_not_zero"])

    def test_the_same_weekday_a_week_ago_becomes_the_baseline(self):
        floor = self.floor()
        self.entry(floor)
        for _ in range(4):
            self.entry(floor, when=datetime.now(UTC) - timedelta(days=7))
        read = self.client.get("/access/visits",
                               headers=self.headers(floor["tenant_id"]))
        row = next(r for r in read.json()["locations"]
                   if r["location_id"] == floor["location_id"])
        self.assertEqual(row["entries"], 1)
        self.assertEqual(row["usual_for_this_weekday"], 4)
        self.assertEqual(row["weekdays_compared"], 1)

    def test_a_day_six_days_back_is_not_the_same_weekday(self):
        """The comparison is weekly because gyms are. Six days back is a different day of the
        week and must not enter the baseline."""
        floor = self.floor()
        self.entry(floor, when=datetime.now(UTC) - timedelta(days=6))
        read = self.client.get("/access/visits",
                               headers=self.headers(floor["tenant_id"]))
        rows = [r for r in read.json()["locations"]
                if r["location_id"] == floor["location_id"]]
        # Either no row for this location at all, or one with nothing in either figure.
        for row in rows:
            self.assertEqual(row["entries"], 0)
            self.assertIsNone(row["usual_for_this_weekday"])

    def test_the_day_is_each_locations_own_and_the_response_says_so(self):
        floor = self.floor()
        read = self.client.get("/access/visits",
                               headers=self.headers(floor["tenant_id"]))
        body = read.json()
        self.assertIn("own timezone", body["a_day_is_local_to_each_location"])
        self.assertIn("not a visit", body["entries_are_events_not_decisions"])

    def test_the_comparison_window_is_bounded_and_the_date_is_validated(self):
        tenant_id = self.tenant()
        head = self.headers(tenant_id)
        for query in ("compare_weeks=0", "compare_weeks=100", "on=not-a-date"):
            answer = self.client.get(f"/access/visits?{query}", headers=head)
            self.assertEqual(answer.status_code, 422, f"{query}: {answer.text}")

    def test_a_session_holding_nothing_is_refused_the_count(self):
        tenant_id = self.tenant()
        nobody = self.grant(tenant_id, [])
        refused = self.client.get("/access/visits",
                                  headers=self.headers(tenant_id, nobody))
        self.assertEqual(refused.status_code, 403, refused.text)

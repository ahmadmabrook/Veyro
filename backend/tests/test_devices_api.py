"""MOD-021 ECO-03 over HTTP, with the credentials a real caller would hold.

**Driven through the routes, not the service.** MOD-014's reviewers found four defects in its
request path that a green suite could not see, MOD-016 had no test that had ever called a
`/catalog` route successfully, MOD-019's HTTP tests found five defects in a module whose domain
suite was green, and MOD-020's review named "no HTTP test ever recorded a no-show" as the gap
that let four blocking findings ship.

The tests that matter most here are TSD section 16.4's: that a failed or missing commissioning
test blocks opening an access point, that a fail-secure barrier on an egress path is refused,
and that no request can make a door stay shut. Those are fire-code rules implemented as
refusals, so most of these tests assert a refusal.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from tests.support import GatedApiTestCase

SHA = "a" * 64


def fingerprint() -> str:
    """A well-formed 64-character hex fingerprint, unique per call.

    Unique because `dev_certificates` is unique on (tenant, fingerprint) -- which is the half
    of "default credentials are forbidden" that catches ten thousand units sharing whatever
    their vendor actually printed.
    """
    return uuid.uuid4().hex + uuid.uuid4().hex


def window(days: int = 90) -> dict[str, str]:
    start = datetime.now(UTC) - timedelta(minutes=1)
    return {"not_before": start.isoformat(),
            "not_after": (start + timedelta(days=days)).isoformat()}


class DeviceApiTestCase(GatedApiTestCase):
    """Fixtures: a tenant with a location, a published device type and a device on it."""

    def location(self, tenant_id: str, *, timezone: str = "Asia/Amman") -> str:
        owner = self.headers(tenant_id)
        org = self.client.post("/organizations", json={
            "legal_name": "Veyro Sites Ltd", "country_code": "JO",
            **self.correlation()}, headers=owner)
        brand = self.client.post("/brands", json={
            "organization_id": org.json()["organization_id"], "brand_name": "City"},
            headers=owner)
        created = self.client.post("/locations", json={
            "brand_id": brand.json()["brand_id"], "location_name": "Downtown",
            "timezone": timezone}, headers=owner)
        self.assertEqual(created.status_code, 201, created.text)
        return str(created.json()["location_id"])

    def device_type(
        self, tenant_id: str, *, kind: str = "turnstile",
        capabilities: list[str] | None = None, publish: bool = True,
    ) -> str:
        owner = self.headers(tenant_id)
        created = self.client.post("/fleet/types", json={
            "type_code": f"T{uuid.uuid4().hex[:8].upper()}",
            "vendor": "Acme", "model": "Gate 3000", "kind": kind,
            "display_name": "Acme Gate 3000",
            "capabilities": capabilities or ["access.actuate", "credential.read",
                                             "telemetry"],
            **self.correlation()}, headers=owner)
        self.assertEqual(created.status_code, 201, created.text)
        type_id = str(created.json()["type_id"])
        if publish:
            # **A second person settles it.** `dev_device_types_publisher_is_not_author`
            # refuses the author publishing their own declaration, because declaring
            # `access.actuate` is what makes a model commandable as a barrier. The publisher
            # is cached per tenant: each one costs two scrypt hashes to step up.
            published = self.client.post(
                f"/fleet/types/{type_id}/publish", json=self.correlation(),
                headers=self.headers(tenant_id, self.publisher(tenant_id)))
            self.assertEqual(published.status_code, 200, published.text)
        return type_id

    def publisher(self, tenant_id: str) -> str:
        """A stepped-up session that may publish a device type, and did not author one."""
        cached = getattr(self, "_publishers", None)
        if cached is None:
            cached = self._publishers = {}
        if tenant_id not in cached:
            cached[tenant_id] = self.stepped_grant(
                tenant_id, ["devices.type.publish", "devices.type.write",
                            "devices.device.read"])
        return str(cached[tenant_id])

    def device(
        self, tenant_id: str, *, type_id: str | None = None,
        location_id: str | None = None, kind: str = "turnstile",
        capabilities: list[str] | None = None,
    ) -> dict[str, Any]:
        owner = self.headers(tenant_id)
        type_id = type_id or self.device_type(
            tenant_id, kind=kind, capabilities=capabilities)
        location_id = location_id or self.location(tenant_id)
        created = self.client.post("/fleet", json={
            "type_id": type_id, "location_id": location_id,
            "serial_number": f"SN-{uuid.uuid4().hex[:10].upper()}",
            "display_name": "North turnstile", **self.correlation()}, headers=owner)
        self.assertEqual(created.status_code, 201, created.text)
        return {"device_id": str(created.json()["device_id"]), "type_id": type_id,
                "location_id": location_id,
                "capabilities": created.json()["capabilities"]}

    def provisioned(self, tenant_id: str, **kw: Any) -> dict[str, Any]:
        device = self.device(tenant_id, **kw)
        response = self.client.post(
            f"/fleet/{device['device_id']}/provision",
            json={"fingerprint": fingerprint(), "vault_ref": "vault:acme/gate/1",
                  **window(), **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(response.status_code, 201, response.text)
        device["certificate_id"] = str(response.json()["certificate_id"])
        return device

    def commissioned(self, tenant_id: str, device_id: str, *,
                     profile: str = "fail_safe", on_egress_path: bool = True,
                     tests: bool = True) -> None:
        owner = self.headers(tenant_id)
        response = self.client.post(f"/fleet/{device_id}/commission", json={
            "profile": profile, "on_egress_path": on_egress_path,
            "fire_release_is_independent": True, "local_emergency_input": True,
            "evidence_ref": "uri:certs/fire-officer-2026-11",
            "door_description": "north entrance, single leaf",
            **self.correlation()}, headers=owner)
        self.assertEqual(response.status_code, 201, response.text)
        if tests:
            for name in ("power_loss", "edge_agent_crash", "controller_disconnect",
                         "fire_alarm_input", "emergency_unlock", "recovery",
                         "manual_override"):
                passed = self.client.post(
                    f"/fleet/{device_id}/commissioning-tests",
                    json={"test_name": name, "passed": True, **self.correlation()},
                    headers=owner)
                self.assertEqual(passed.status_code, 201, passed.text)

    def live(self, tenant_id: str, **kw: Any) -> dict[str, Any]:
        """A device in service: enrolled, provisioned, commissioned and activated."""
        device = self.provisioned(tenant_id, **kw)
        if "access.actuate" in device["capabilities"]:
            self.commissioned(tenant_id, device["device_id"])
        activated = self.client.post(
            f"/fleet/{device['device_id']}/activate", json=self.correlation(),
            headers=self.headers(tenant_id))
        self.assertEqual(activated.status_code, 200, activated.text)
        return device


class DeviceTypeTests(DeviceApiTestCase):
    def test_a_type_declares_what_its_units_may_be_asked_to_do(self):
        tenant_id = self.tenant()
        type_id = self.device_type(tenant_id)
        detail = self.client.post("/fleet", json={
            "type_id": type_id, "location_id": self.location(tenant_id),
            "serial_number": "SN-1", "display_name": "Gate",
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(detail.status_code, 201, detail.text)
        self.assertEqual(sorted(detail.json()["capabilities"]),
                         ["access.actuate", "credential.read", "telemetry"])
        self.assertTrue(detail.json()["needs_safety_profile"])

    def test_a_gateway_cannot_declare_that_it_moves_a_barrier(self):
        """The edge agent runs on it and drives the devices beside it; a gateway declaring
        `access.actuate` would be a door with no door, and the safety profile -- commissioned
        per access point -- would have nothing physical to describe."""
        tenant_id = self.tenant()
        refused = self.client.post("/fleet/types", json={
            "type_code": "GW1", "vendor": "Acme", "model": "Edge", "kind": "gateway",
            "display_name": "Edge box", "capabilities": ["access.actuate"],
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_a_draft_type_takes_no_devices(self):
        """A draft is a declaration somebody is still writing, and the trigger that freezes a
        published type's capabilities is what makes a device's snapshot meaningful."""
        tenant_id = self.tenant()
        type_id = self.device_type(tenant_id, publish=False)
        refused = self.client.post("/fleet", json={
            "type_id": type_id, "location_id": self.location(tenant_id),
            "serial_number": "SN-2", "display_name": "Gate",
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("draft", refused.text)

    def test_retiring_a_type_stops_the_next_enrolment_and_not_the_last(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.device(tenant_id)
        retired = self.client.post(
            f"/fleet/types/{device['type_id']}/retire",
            json={"reason": "superseded by the Gate 4000", **self.correlation()},
            headers=owner)
        self.assertEqual(retired.status_code, 200, retired.text)
        self.assertEqual(retired.json()["devices_still_enrolled"], 1)
        refused = self.client.post("/fleet", json={
            "type_id": device["type_id"], "location_id": device["location_id"],
            "serial_number": "SN-3", "display_name": "Gate",
            **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        still_there = self.client.get(f"/fleet/{device['device_id']}", headers=owner)
        self.assertEqual(still_there.status_code, 200, still_there.text)


class SafetyGateTests(DeviceApiTestCase):
    """TSD section 16.4. **The tests that matter most in this module.**"""

    def test_a_door_with_no_passing_commissioning_record_does_not_open(self):
        """Paragraph 4175: "A failed safety test blocks opening the access point in
        production." The gate is on the activation, where somebody is doing it deliberately."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.provisioned(tenant_id)
        self.commissioned(tenant_id, device["device_id"], tests=False)
        refused = self.client.post(
            f"/fleet/{device['device_id']}/activate", json=self.correlation(),
            headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("commissioning", refused.text)

    def test_one_outstanding_test_is_enough_to_keep_the_door_shut(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.provisioned(tenant_id)
        self.commissioned(tenant_id, device["device_id"], tests=False)
        for name in ("power_loss", "edge_agent_crash", "controller_disconnect",
                     "emergency_unlock", "recovery", "manual_override"):
            self.client.post(
                f"/fleet/{device['device_id']}/commissioning-tests",
                json={"test_name": name, "passed": True, **self.correlation()},
                headers=owner)
        refused = self.client.post(
            f"/fleet/{device['device_id']}/activate", json=self.correlation(),
            headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("fire_alarm_input", refused.text)

    def test_a_failed_retest_shuts_a_door_that_had_passed(self):
        """`_passing_tests` reads the *latest* answer per name. A door that passed its
        fire-alarm test in March, failed a re-test in June and was never repaired has a
        passing row -- and reading "has it ever passed" would let it open."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        failed = self.client.post(
            f"/fleet/{device['device_id']}/commissioning-tests",
            json={"test_name": "fire_alarm_input", "passed": False,
                  "detail": "the release did not fire on the alarm input",
                  **self.correlation()}, headers=owner)
        self.assertEqual(failed.status_code, 201, failed.text)
        self.assertFalse(failed.json()["may_go_live"])
        self.assertIn("fire_alarm_input", failed.json()["outstanding_tests"])
        # Out of service and back: the gate runs again and refuses.
        self.client.post(f"/fleet/{device['device_id']}/state",
                         json={"target": "maintenance", **self.correlation()},
                         headers=owner)
        refused = self.client.post(
            f"/fleet/{device['device_id']}/activate", json=self.correlation(),
            headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("fire_alarm_input", refused.text)

    def test_a_fail_secure_barrier_on_an_egress_path_is_refused(self):
        """Paragraph 4173. A fail-secure maglock holds the door shut when the power fails --
        refused rather than stored with a warning, because a building whose records pass an
        audit it would fail is worse than one with no records."""
        tenant_id = self.tenant()
        device = self.provisioned(tenant_id)
        refused = self.client.post(
            f"/fleet/{device['device_id']}/commission", json={
                "profile": "fail_secure", "on_egress_path": True,
                "fire_release_is_independent": True, "local_emergency_input": True,
                "evidence_ref": "uri:certs/x", "door_description": "north entrance",
                **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("egress", refused.text)

    def test_a_fail_secure_barrier_off_an_egress_path_is_ordinary(self):
        """A delivery door or a plant room. That is why the profile exists at all rather than
        being deleted."""
        tenant_id = self.tenant()
        device = self.provisioned(tenant_id)
        ok = self.client.post(
            f"/fleet/{device['device_id']}/commission", json={
                "profile": "fail_secure", "on_egress_path": False,
                "fire_release_is_independent": False, "local_emergency_input": False,
                "evidence_ref": "uri:certs/plant-room",
                "door_description": "plant room, no public access",
                **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(ok.status_code, 201, ok.text)

    def test_an_egress_path_without_an_independent_fire_release_is_refused(self):
        tenant_id = self.tenant()
        device = self.provisioned(tenant_id)
        for field in ("fire_release_is_independent", "local_emergency_input"):
            body = {"profile": "fail_safe", "on_egress_path": True,
                    "fire_release_is_independent": True,
                    "local_emergency_input": True,
                    "evidence_ref": "uri:certs/x",
                    "door_description": "north entrance", **self.correlation()}
            body[field] = False
            refused = self.client.post(
                f"/fleet/{device['device_id']}/commission", json=body,
                headers=self.headers(tenant_id))
            self.assertEqual(refused.status_code, 409, f"{field}: {refused.text}")

    def test_a_printer_needs_no_fire_alarm_test(self):
        """Only a device that actuates needs one. Demanding a fire-alarm test of a receipt
        printer is how a safety gate gets routed around."""
        tenant_id = self.tenant()
        device = self.provisioned(
            tenant_id, kind="pos", capabilities=["payment", "print", "telemetry"])
        activated = self.client.post(
            f"/fleet/{device['device_id']}/activate", json=self.correlation(),
            headers=self.headers(tenant_id))
        self.assertEqual(activated.status_code, 200, activated.text)

    def test_a_device_that_moves_no_barrier_has_no_safety_profile(self):
        tenant_id = self.tenant()
        device = self.provisioned(
            tenant_id, kind="scanner", capabilities=["scan", "telemetry"])
        refused = self.client.post(
            f"/fleet/{device['device_id']}/commission", json={
                "profile": "fail_safe", "on_egress_path": False,
                "fire_release_is_independent": True, "local_emergency_input": True,
                "evidence_ref": "uri:certs/x", "door_description": "none",
                **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("no barrier", refused.text)

    def test_a_re_commissioning_supersedes_rather_than_edits(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        again = self.client.post(f"/fleet/{device['device_id']}/commission", json={
            "profile": "mechanical_free_egress", "on_egress_path": True,
            "fire_release_is_independent": True, "local_emergency_input": True,
            "evidence_ref": "uri:certs/fire-officer-2027-02",
            "door_description": "north entrance, rebuilt as a free-egress turnstile",
            **self.correlation()}, headers=owner)
        self.assertEqual(again.status_code, 201, again.text)
        self.assertIsNotNone(again.json()["superseded"])
        detail = self.client.get(f"/fleet/{device['device_id']}", headers=owner).json()
        self.assertEqual(detail["safety"]["profile"], "mechanical_free_egress")


class CommandTests(DeviceApiTestCase):
    """Paragraph 3084: scoped, signed, audited and bounded by device safety."""

    def test_no_request_can_tell_a_barrier_to_stay_shut(self):
        """**There is no permission that buys this and no state in which it is allowed.**
        Paragraph 4173 is a fire code, and a fire code is not delegable -- so the action is
        not in the vocabulary and a request naming one is refused at validation."""
        tenant_id = self.tenant()
        device = self.live(tenant_id)
        for action in ("lock_down", "hold", "hold_closed", "maglock_engage",
                       "disable_egress"):
            refused = self.client.post(
                f"/fleet/{device['device_id']}/commands",
                json={"action": action, "idempotency_key": str(uuid.uuid4()),
                      **self.correlation()}, headers=self.headers(tenant_id))
            self.assertIn(refused.status_code, (409, 422), f"{action}: {refused.text}")

    def test_an_unlock_is_issued_with_a_digest_and_a_minute_to_live(self):
        tenant_id = self.tenant()
        device = self.live(tenant_id)
        issued = self.client.post(
            f"/fleet/{device['device_id']}/commands",
            json={"action": "unlock_momentary", "idempotency_key": str(uuid.uuid4()),
                  **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(issued.status_code, 201, issued.text)
        self.assertEqual(len(issued.json()["payload_digest"]), 64)
        issued_at = datetime.fromisoformat(issued.json()["expires_at"])
        self.assertLess(issued_at - datetime.now(UTC), timedelta(seconds=61))

    def test_an_unlock_cannot_be_given_a_long_deadline(self):
        """A door opened a minute after somebody asked is a door opened for whoever is
        standing there now."""
        tenant_id = self.tenant()
        device = self.live(tenant_id)
        refused = self.client.post(
            f"/fleet/{device['device_id']}/commands",
            json={"action": "unlock_momentary", "idempotency_key": str(uuid.uuid4()),
                  "expires_in_seconds": 3600, **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        # The message names the action and its own window now that there is more than one
        # door-touching command: `unlock_momentary` is a minute and `emergency_unlock` is
        # five, and a message that said "a minute" for both would be wrong half the time.
        self.assertIn("unlock_momentary is deliverable for at most 60 seconds", refused.text)

    def test_a_command_a_device_cannot_perform_is_refused(self):
        tenant_id = self.tenant()
        device = self.live(
            tenant_id, kind="scanner", capabilities=["scan", "telemetry"])
        refused = self.client.post(
            f"/fleet/{device['device_id']}/commands",
            json={"action": "unlock_momentary", "idempotency_key": str(uuid.uuid4()),
                  **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("access.actuate", refused.text)

    def test_a_command_to_a_device_out_of_service_is_refused(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        self.client.post(f"/fleet/{device['device_id']}/state",
                         json={"target": "quarantined",
                               "reason": "reader reporting errors",
                               **self.correlation()}, headers=owner)
        refused = self.client.post(
            f"/fleet/{device['device_id']}/commands",
            json={"action": "reboot", "idempotency_key": str(uuid.uuid4()),
                  **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("quarantined", refused.text)

    def test_a_key_reused_for_another_device_is_refused(self):
        """MOD-019 shipped a key checked on one field and handed one member another's hold;
        MOD-020 shipped three compared against nothing."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        first = self.live(tenant_id)
        second = self.live(tenant_id)
        key = "shift-counter-4"
        one = self.client.post(
            f"/fleet/{first['device_id']}/commands",
            json={"action": "reboot", "idempotency_key": key, **self.correlation()},
            headers=owner)
        self.assertEqual(one.status_code, 201, one.text)
        two = self.client.post(
            f"/fleet/{second['device_id']}/commands",
            json={"action": "reboot", "idempotency_key": key, **self.correlation()},
            headers=owner)
        self.assertEqual(two.status_code, 409, two.text)
        self.assertIn("different_request", two.text)

    def test_a_retried_command_is_answered_from_what_was_recorded(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        key = str(uuid.uuid4())
        one = self.client.post(
            f"/fleet/{device['device_id']}/commands",
            json={"action": "reboot", "idempotency_key": key, **self.correlation()},
            headers=owner)
        two = self.client.post(
            f"/fleet/{device['device_id']}/commands",
            json={"action": "reboot", "idempotency_key": key, **self.correlation()},
            headers=owner)
        self.assertEqual(two.status_code, 201, two.text)
        self.assertTrue(two.json()["repeated"])
        self.assertEqual(two.json()["command_id"], one.json()["command_id"])

    def test_a_command_is_delivered_once_and_settled_by_the_device(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        issued = self.client.post(
            f"/fleet/{device['device_id']}/commands",
            json={"action": "diagnostics", "idempotency_key": str(uuid.uuid4()),
                  **self.correlation()}, headers=owner).json()
        delivered = self.client.post(
            f"/fleet/commands/{issued['command_id']}/deliver",
            json={"signature_ref": "vault:sig/1", **self.correlation()}, headers=owner)
        self.assertEqual(delivered.status_code, 200, delivered.text)
        self.assertEqual(delivered.json()["state"], "delivered")
        again = self.client.post(
            f"/fleet/commands/{issued['command_id']}/deliver",
            json=self.correlation(), headers=owner)
        self.assertEqual(again.status_code, 409, again.text)
        for outcome in ("acknowledged", "completed"):
            settled = self.client.post(
                f"/fleet/commands/{issued['command_id']}/settle",
                json={"outcome": outcome, **self.correlation()}, headers=owner)
            self.assertEqual(settled.status_code, 200, settled.text)

    def test_a_failed_command_says_what_happened(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        issued = self.client.post(
            f"/fleet/{device['device_id']}/commands",
            json={"action": "reboot", "idempotency_key": str(uuid.uuid4()),
                  **self.correlation()}, headers=owner).json()
        refused = self.client.post(
            f"/fleet/commands/{issued['command_id']}/settle",
            json={"outcome": "failed", **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_an_expired_command_is_settled_expired_rather_than_delivered(self):
        """A device offline when an unlock was issued must not receive it a minute later and
        open a door for whoever is standing there now."""
        from app.devices import service as device_service
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        issued = self.client.post(
            f"/fleet/{device['device_id']}/commands",
            json={"action": "unlock_momentary", "idempotency_key": str(uuid.uuid4()),
                  **self.correlation()}, headers=owner).json()
        # The deadline is re-read under a lock on the row, so a stale command settles rather
        # than being handed over. No route takes an instant, for MOD-011's reason.
        late = device_service.deliver_command(
            self._tenant_pool, tenant_id, issued["command_id"], signature_ref=None,
            actor_id="33333333-3333-4333-8333-333333333333",
            correlation_id=str(uuid.uuid4()),
            at=datetime.now(UTC) + timedelta(minutes=5))
        self.assertEqual(late["state"], "expired", late)
        queue = self.client.get(f"/fleet/{device['device_id']}/commands",
                                headers=owner).json()
        self.assertEqual(queue["commands"][0]["state"], "expired")


class CertificateTests(DeviceApiTestCase):
    """Paragraph 3083, a Critical Control."""

    def test_a_vendor_default_fingerprint_is_refused(self):
        tenant_id = self.tenant()
        device = self.device(tenant_id)
        refused = self.client.post(
            f"/fleet/{device['device_id']}/provision",
            json={"fingerprint": "DE:AD:BE:EF:" * 8, "vault_ref": "vault:x",
                  **window(), **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("default credential", refused.text)

    def test_two_devices_cannot_share_one_fingerprint(self):
        """The other half of "default credentials are forbidden": ten thousand turnstiles
        sharing whatever their vendor actually printed."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        shared = fingerprint()
        first = self.device(tenant_id)
        second = self.device(tenant_id)
        one = self.client.post(
            f"/fleet/{first['device_id']}/provision",
            json={"fingerprint": shared, "vault_ref": "vault:a", **window(),
                  **self.correlation()}, headers=owner)
        self.assertEqual(one.status_code, 201, one.text)
        two = self.client.post(
            f"/fleet/{second['device_id']}/provision",
            json={"fingerprint": shared, "vault_ref": "vault:b", **window(),
                  **self.correlation()}, headers=owner)
        self.assertEqual(two.status_code, 409, two.text)

    def test_a_vault_reference_has_to_look_like_a_locator(self):
        """MOD-012 shipped a `vault_ref` that was merely non-blank, which made a live API key
        a valid "vault reference" and the absence of a key column a naming convention."""
        tenant_id = self.tenant()
        device = self.device(tenant_id)
        refused = self.client.post(
            f"/fleet/{device['device_id']}/provision",
            json={"fingerprint": fingerprint(),
                  "vault_ref": "4111111111111111 exp 12/29", **window(),
                  **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_a_device_with_no_usable_certificate_does_not_go_live(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.device(tenant_id)
        self.commissioned(tenant_id, device["device_id"])
        refused = self.client.post(
            f"/fleet/{device['device_id']}/activate", json=self.correlation(),
            headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)

    def test_rotation_keeps_the_outgoing_certificate_until_it_expires(self):
        """A device whose certificate was replaced the instant the new one was issued is
        locked out for as long as it takes to receive it."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        rotated = self.client.post(
            f"/fleet/{device['device_id']}/certificates",
            json={"fingerprint": fingerprint(), "vault_ref": "vault:acme/gate/2",
                  **window(), **self.correlation()}, headers=owner)
        self.assertEqual(rotated.status_code, 201, rotated.text)
        self.assertEqual(rotated.json()["superseded"], device["certificate_id"])
        detail = self.client.get(f"/fleet/{device['device_id']}", headers=owner).json()
        states = {c["state"]: c["usable"] for c in detail["certificates"]}
        self.assertTrue(states["superseded"], detail["certificates"])
        self.assertTrue(states["active"])

    def test_revoking_a_certificate_bumps_the_revocation_epoch(self):
        """A gateway compares its snapshot's epoch numerically, so the two committing
        separately is a window in which a revoked certificate still authenticates."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        before = self.client.get(f"/fleet/{device['device_id']}",
                                 headers=owner).json()["revocation_epoch"]
        revoked = self.client.post(
            f"/fleet/certificates/{device['certificate_id']}/revoke",
            json={"reason": "the unit was stolen from the lobby", **self.correlation()},
            headers=owner)
        self.assertEqual(revoked.status_code, 200, revoked.text)
        self.assertEqual(revoked.json()["revocation_epoch"], before + 1)
        self.assertFalse(revoked.json()["device_can_still_authenticate"])

    def test_retiring_a_device_revokes_what_authenticates_it(self):
        """A retired unit whose certificate still works is a box somebody took off a wall
        that can still talk to the registry."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        retired = self.client.post(
            f"/fleet/{device['device_id']}/state",
            json={"target": "retired", "reason": "replaced by a Gate 4000",
                  **self.correlation()}, headers=owner)
        self.assertEqual(retired.status_code, 200, retired.text)
        self.assertEqual(retired.json()["certificates_revoked"], 1)
        detail = self.client.get(f"/fleet/{device['device_id']}", headers=owner).json()
        self.assertFalse(any(c["usable"] for c in detail["certificates"]))


class SnapshotTests(DeviceApiTestCase):
    def test_a_snapshot_carries_the_devices_current_epoch(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        published = self.client.post(
            f"/fleet/{device['device_id']}/snapshots",
            json={"content_digest": SHA, "ttl_minutes": 60, **self.correlation()},
            headers=owner)
        self.assertEqual(published.status_code, 201, published.text)
        self.assertEqual(published.json()["revocation_epoch"], 0)
        detail = self.client.get(f"/fleet/{device['device_id']}", headers=owner).json()
        self.assertFalse(detail["snapshot"]["stale"])
        self.assertFalse(detail["snapshot"]["behind_revocation"])

    def test_a_revocation_leaves_every_live_snapshot_behind(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        self.client.post(
            f"/fleet/{device['device_id']}/snapshots",
            json={"content_digest": SHA, "ttl_minutes": 60, **self.correlation()},
            headers=owner)
        self.client.post(
            f"/fleet/certificates/{device['certificate_id']}/revoke",
            json={"reason": "stolen", **self.correlation()}, headers=owner)
        detail = self.client.get(f"/fleet/{device['device_id']}", headers=owner).json()
        self.assertTrue(detail["snapshot"]["behind_revocation"])

    def test_a_snapshot_outside_the_bound_is_refused(self):
        tenant_id = self.tenant()
        device = self.live(tenant_id)
        for ttl in (1, 2000):
            refused = self.client.post(
                f"/fleet/{device['device_id']}/snapshots",
                json={"content_digest": SHA, "ttl_minutes": ttl,
                      **self.correlation()}, headers=self.headers(tenant_id))
            self.assertEqual(refused.status_code, 422, f"{ttl}: {refused.text}")

    def test_a_device_out_of_service_takes_no_policy(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.provisioned(tenant_id)
        refused = self.client.post(
            f"/fleet/{device['device_id']}/snapshots",
            json={"content_digest": SHA, "ttl_minutes": 60, **self.correlation()},
            headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)


class FleetTests(DeviceApiTestCase):
    def test_reachability_is_derived_from_the_last_report(self):
        """There is no `online` column: a stored flag is a second authority that disagrees
        with the last report and sends somebody to a working device."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        before = self.client.get(f"/fleet/{device['device_id']}", headers=owner).json()
        self.assertEqual(before["reachability"], "never_seen")
        reported = self.client.post(
            f"/fleet/{device['device_id']}/health",
            json={"latency_ms": 12, "error_count": 0,
                  "storage_free_bytes": 4_000_000_000, "agent_version": "1.4.2",
                  "peripherals": {"reader": "ok"}, **self.correlation()},
            headers=owner)
        self.assertEqual(reported.status_code, 201, reported.text)
        after = self.client.get(f"/fleet/{device['device_id']}", headers=owner).json()
        self.assertEqual(after["reachability"], "online")
        self.assertEqual(after["health"]["agent_version"], "1.4.2")

    def test_the_fleet_view_names_what_blocks_a_club(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        view = self.client.get("/fleet", headers=owner)
        self.assertEqual(view.status_code, 200, view.text)
        ids = [d["device_id"] for d in view.json()["devices"]]
        self.assertIn(device["device_id"], ids)
        # Never seen is not a failure: nobody has finished installing it.
        self.assertEqual(view.json()["needs_attention"], [])

    def test_a_health_report_for_a_retired_device_is_refused(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        self.client.post(f"/fleet/{device['device_id']}/state",
                         json={"target": "retired", "reason": "scrapped",
                               **self.correlation()}, headers=owner)
        refused = self.client.post(
            f"/fleet/{device['device_id']}/health",
            json={"latency_ms": 1, "error_count": 0, "storage_free_bytes": 1,
                  "agent_version": "1.0", **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)

    def test_a_sync_conflict_is_recorded_and_not_resolved(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        reported = self.client.post(
            f"/fleet/{device['device_id']}/sync-conflicts",
            json={"detail": "the local policy cache names a credential the registry revoked",
                  "local_digest": SHA, "remote_digest": "b" * 64,
                  **self.correlation()}, headers=owner)
        self.assertEqual(reported.status_code, 201, reported.text)
        self.assertIn("not resolved", reported.json()["detail"])


class LifecycleTests(DeviceApiTestCase):
    def test_a_device_does_not_go_live_without_being_provisioned(self):
        tenant_id = self.tenant()
        device = self.device(tenant_id)
        self.commissioned(tenant_id, device["device_id"])
        refused = self.client.post(
            f"/fleet/{device['device_id']}/activate", json=self.correlation(),
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)

    def test_maintenance_is_reversible_and_retirement_is_not(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        for target in ("maintenance",):
            moved = self.client.post(
                f"/fleet/{device['device_id']}/state",
                json={"target": target, **self.correlation()}, headers=owner)
            self.assertEqual(moved.status_code, 200, moved.text)
        back = self.client.post(
            f"/fleet/{device['device_id']}/activate", json=self.correlation(),
            headers=owner)
        self.assertEqual(back.status_code, 200, back.text)
        self.assertFalse(back.json()["first_activation"])
        self.client.post(f"/fleet/{device['device_id']}/state",
                         json={"target": "retired", "reason": "scrapped",
                               **self.correlation()}, headers=owner)
        refused = self.client.post(
            f"/fleet/{device['device_id']}/activate", json=self.correlation(),
            headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)

    def test_quarantine_and_retirement_state_why(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        refused = self.client.post(
            f"/fleet/{device['device_id']}/state",
            json={"target": "quarantined", **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_configuring_a_device_takes_the_version_the_caller_read(self):
        """Two operators editing one device is ordinary; last-write-wins discards whichever
        finished first and leaves no trace."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        detail = self.client.get(f"/fleet/{device['device_id']}", headers=owner).json()
        first = self.client.post(
            f"/fleet/{device['device_id']}/configure",
            json={"display_name": "North gate", "expected_version": detail["version"],
                  **self.correlation()}, headers=owner)
        self.assertEqual(first.status_code, 200, first.text)
        stale = self.client.post(
            f"/fleet/{device['device_id']}/configure",
            json={"display_name": "South gate", "expected_version": detail["version"],
                  **self.correlation()}, headers=owner)
        self.assertEqual(stale.status_code, 409, stale.text)

    def test_a_serial_number_is_enrolled_once(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.device(tenant_id)
        detail = self.client.get(f"/fleet/{device['device_id']}", headers=owner).json()
        again = self.client.post("/fleet", json={
            "type_id": device["type_id"], "location_id": device["location_id"],
            "serial_number": detail["serial_number"], "display_name": "Clone",
            **self.correlation()}, headers=owner)
        self.assertEqual(again.status_code, 409, again.text)


class FirmwareTests(DeviceApiTestCase):
    def test_a_release_is_staged_and_a_withdrawal_is_final(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        type_id = self.device_type(tenant_id)
        released = self.client.post("/fleet/firmware", json={
            "type_id": type_id, "version": "2.1.0", "image_ref": "oci:acme/gate:2.1.0",
            "image_digest": SHA, "release_notes": "fixes the reader timeout",
            **self.correlation()}, headers=owner)
        self.assertEqual(released.status_code, 201, released.text)
        firmware_id = released.json()["firmware_id"]
        staged = self.client.post(
            f"/fleet/firmware/{firmware_id}/status",
            json={"target": "staged", **self.correlation()}, headers=owner)
        self.assertEqual(staged.status_code, 200, staged.text)
        withdrawn = self.client.post(
            f"/fleet/firmware/{firmware_id}/status",
            json={"target": "withdrawn", "reason": "bricks units on 1.9",
                  **self.correlation()}, headers=owner)
        self.assertEqual(withdrawn.status_code, 200, withdrawn.text)
        back = self.client.post(
            f"/fleet/firmware/{firmware_id}/status",
            json={"target": "available", **self.correlation()}, headers=owner)
        self.assertEqual(back.status_code, 409, back.text)
        self.assertIn("does not come back", back.text)

    def test_one_version_per_type(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        type_id = self.device_type(tenant_id)
        body = {"type_id": type_id, "version": "1.0.0",
                "image_ref": "oci:acme/gate:1.0.0", "image_digest": SHA,
                "release_notes": "first", **self.correlation()}
        self.assertEqual(
            self.client.post("/fleet/firmware", json=body, headers=owner).status_code,
            201)
        again = self.client.post("/fleet/firmware", json={
            **body, "release_notes": "again", **self.correlation()}, headers=owner)
        self.assertEqual(again.status_code, 409, again.text)


class IsolationTests(DeviceApiTestCase):
    def test_one_tenants_fleet_is_not_another_tenants(self):
        first = self.tenant()
        second = self.tenant()
        device = self.live(first)
        theirs = self.client.get(f"/fleet/{device['device_id']}",
                                 headers=self.headers(second))
        self.assertEqual(theirs.status_code, 404, theirs.text)
        view = self.client.get("/fleet", headers=self.headers(second)).json()
        self.assertEqual(view["devices"], [])


class EventTests(DeviceApiTestCase):
    def test_enrolling_and_reporting_reach_the_outbox(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        self.client.post(
            f"/fleet/{device['device_id']}/health",
            json={"latency_ms": 5, "error_count": 0, "storage_free_bytes": 1000,
                  "agent_version": "1.0", **self.correlation()}, headers=owner)
        with self._tenant_pool.connection() as conn:
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            rows = conn.execute(
                "SELECT event_type FROM plt01.evt_outbox"
                " WHERE event_type LIKE 'device.%' OR event_type LIKE 'edge.%'"
                " ORDER BY occurred_at").fetchall()
        kinds = [str(r[0]) for r in rows]
        self.assertIn("device.enrolled", kinds)
        self.assertIn("device.online", kinds)

    def test_no_payload_carries_a_credential_or_a_key(self):
        """A device event is about a box. The one thing that could identify somebody -- what
        a reader read -- is MOD-022's and is not in this module at all."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        secret = fingerprint()
        device = self.device(tenant_id)
        self.client.post(
            f"/fleet/{device['device_id']}/provision",
            json={"fingerprint": secret, "vault_ref": "vault:secret/path",
                  **window(), **self.correlation()}, headers=owner)
        with self._tenant_pool.connection() as conn:
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            rows = conn.execute(
                "SELECT payload::text FROM plt01.evt_outbox"
                " WHERE event_type LIKE 'device.%'").fetchall()
        blob = " ".join(str(r[0]) for r in rows)
        self.assertNotIn(secret, blob)
        self.assertNotIn("vault:secret/path", blob)


if __name__ == "__main__":
    unittest.main()

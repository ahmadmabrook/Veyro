"""The MOD-021 review's findings, each as a test named for the attack rather than the fix.

Three reviewers worked this module in parallel -- the schema, the decision modules and the
request path -- and all three returned CHANGES_REQUESTED. Twenty-three blocking defects, every
one inside a suite of 116 green tests. The tests below are the attacks, so a regression reads
as the attack succeeding again.

**The dominant shape is this repository's own "a control consulted once is a control with a
window"**, applied to the two gates a door's safety rests on: `safety.may_go_live` and
`certificates.check_may_activate` were read at activation and never again, so a fire-alarm
re-test that failed and a certificate that was revoked each changed nothing about a door
already in service. The gates were correct; nothing re-entered them.
"""

from __future__ import annotations

import threading
import unittest
import uuid

import psycopg

from tests.support import DSN
from tests.test_devices_api import DeviceApiTestCase


class CommissioningIsNotOnlyAGateTests(DeviceApiTestCase):
    """Paragraph 4175 holds for a door already in production, not only at its activation."""

    def test_a_failed_re_test_takes_a_live_door_out_of_service(self) -> None:
        """A reviewer recorded a failed fire-alarm re-test on a live turnstile and the door
        went on unlocking on request, with the failure visible only on one read."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        failed = self.client.post(
            f"/fleet/{device['device_id']}/commissioning-tests",
            json={"test_name": "fire_alarm_input", "passed": False,
                  "detail": "the maglock stayed engaged", **self.correlation()},
            headers=owner)
        self.assertEqual(failed.status_code, 201, failed.text)
        self.assertTrue(failed.json()["withdrawn_from_service"], failed.text)
        detail = self.client.get(f"/fleet/{device['device_id']}", headers=owner).json()
        self.assertEqual(detail["state"], "quarantined", detail)
        unlock = self.client.post(
            f"/fleet/{device['device_id']}/commands",
            json={"action": "unlock_momentary", "idempotency_key": str(uuid.uuid4()),
                  **self.correlation()}, headers=owner)
        self.assertEqual(unlock.status_code, 409, unlock.text)

    def test_the_commissioning_gate_is_in_the_database_and_not_only_in_the_service(
            self) -> None:
        """The trigger's own message claimed to be paragraph 4175's gate and asked only
        whether a safety-profile row existed, so a door that reached `active` by any writer
        other than `activate_device` opened with six of seven tests never run."""
        tenant_id = self.tenant()
        device = self.provisioned(tenant_id)
        self.commissioned(tenant_id, device["device_id"], tests=False)
        with psycopg.connect(DSN) as conn, conn.cursor() as cur:
            cur.execute("SET LOCAL ROLE veyro_cp_app")
            cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            cur.execute(
                "UPDATE plt01.dev_devices SET state = 'active', activated_at = now(),"
                " activated_by = %s, activate_correlation_id = %s WHERE device_id = %s",
                (str(uuid.uuid4()), str(uuid.uuid4()), device["device_id"]))
            with self.assertRaises(psycopg.errors.RaiseException) as caught:
                cur.execute(
                    "INSERT INTO plt01.dev_commands (tenant_id, device_id, action,"
                    " payload_digest, expires_at, idempotency_key, issued_by,"
                    " correlation_id) VALUES (%s, %s, 'unlock_momentary', %s,"
                    " now() + interval '30 seconds', %s, %s, %s)",
                    (tenant_id, device["device_id"], "b" * 64, str(uuid.uuid4()),
                     str(uuid.uuid4()), str(uuid.uuid4())))
        self.assertIn("commissioning tests", str(caught.exception))


class RevocationTakesTheDeviceWithItTests(DeviceApiTestCase):
    def test_revoking_the_last_certificate_withdraws_the_device(self) -> None:
        """`device_can_still_authenticate` was computed, returned to the caller and acted on
        by nothing: the access point stayed live and went on taking unlock commands."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        revoked = self.client.post(
            f"/fleet/certificates/{device['certificate_id']}/revoke",
            json={"reason": "the gateway was stolen", **self.correlation()}, headers=owner)
        self.assertEqual(revoked.status_code, 200, revoked.text)
        self.assertFalse(revoked.json()["device_can_still_authenticate"])
        self.assertTrue(revoked.json()["withdrawn_from_service"], revoked.text)
        detail = self.client.get(f"/fleet/{device['device_id']}", headers=owner).json()
        self.assertEqual(detail["state"], "quarantined", detail)
        unlock = self.client.post(
            f"/fleet/{device['device_id']}/commands",
            json={"action": "unlock_momentary", "idempotency_key": str(uuid.uuid4()),
                  **self.correlation()}, headers=owner)
        self.assertEqual(unlock.status_code, 409, unlock.text)


class TheCommandIsWhatItSaysTests(DeviceApiTestCase):
    def test_an_unlock_takes_no_arguments_at_all(self) -> None:
        """`HOLD_COMMANDS` refuses a word, and `arguments` was an unvalidated passthrough --
        so hold-the-door semantics reached the row a gateway parameterises its relay from."""
        tenant_id = self.tenant()
        device = self.live(tenant_id)
        held = self.client.post(
            f"/fleet/{device['device_id']}/commands",
            json={"action": "unlock_momentary",
                  "arguments": {"mode": "hold_open", "hold_seconds": "86400"},
                  "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(held.status_code, 409, held.text)
        self.assertIn("no arguments", held.text)

    def test_a_command_carries_no_free_text_about_a_person(self) -> None:
        tenant_id = self.tenant()
        device = self.live(tenant_id)
        leaked = self.client.post(
            f"/fleet/{device['device_id']}/commands",
            json={"action": "set_maintenance",
                  "arguments": {"note": "jane.doe@example.com dob 1984-02-03"},
                  "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(leaked.status_code, 409, leaked.text)

    def test_a_retried_key_naming_a_different_request_is_refused(self) -> None:
        """One key, two different doors' arguments: the first version answered 201
        `repeated` with the other request's command id."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        key = str(uuid.uuid4())
        first = self.client.post(
            f"/fleet/{device['device_id']}/commands",
            json={"action": "set_maintenance", "arguments": {"reason": "north leaf"},
                  "idempotency_key": key, **self.correlation()}, headers=owner)
        self.assertEqual(first.status_code, 201, first.text)
        second = self.client.post(
            f"/fleet/{device['device_id']}/commands",
            json={"action": "set_maintenance", "arguments": {"reason": "south fire exit"},
                  "idempotency_key": key, **self.correlation()}, headers=owner)
        self.assertEqual(second.status_code, 409, second.text)

    def test_a_quarantined_device_collects_nothing(self) -> None:
        """Taking a suspect door out of service did not stop the unlock issued a minute
        earlier from being collected by it."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        issued = self.client.post(
            f"/fleet/{device['device_id']}/commands",
            json={"action": "unlock_momentary", "idempotency_key": str(uuid.uuid4()),
                  **self.correlation()}, headers=owner)
        self.assertEqual(issued.status_code, 201, issued.text)
        quarantined = self.client.post(
            f"/fleet/{device['device_id']}/state",
            json={"target": "quarantined", "reason": "tailgating reported",
                  **self.correlation()}, headers=owner)
        self.assertEqual(quarantined.status_code, 200, quarantined.text)
        collected = self.client.post(
            f"/fleet/commands/{issued.json()['command_id']}/deliver",
            json=self.correlation(), headers=owner)
        self.assertEqual(collected.status_code, 409, collected.text)

    def test_a_command_cannot_be_dated_three_days_from_now(self) -> None:
        """The minute an unlock is deliverable for was a minute starting whenever the writer
        said, because both ends of the window were caller-supplied."""
        tenant_id = self.tenant()
        device = self.live(tenant_id)
        with psycopg.connect(DSN) as conn, conn.cursor() as cur:
            cur.execute("SET LOCAL ROLE veyro_cp_app")
            cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            with self.assertRaises(psycopg.errors.CheckViolation):
                cur.execute(
                    "INSERT INTO plt01.dev_commands (tenant_id, device_id, action,"
                    " payload_digest, issued_at, expires_at, idempotency_key, issued_by,"
                    " correlation_id) VALUES (%s, %s, 'unlock_momentary', %s,"
                    " now() + interval '3 days',"
                    " now() + interval '3 days' + interval '45 seconds', %s, %s, %s)",
                    (tenant_id, device["device_id"], "c" * 64, str(uuid.uuid4()),
                     str(uuid.uuid4()), str(uuid.uuid4())))


class EvidenceNamesSomebodyTests(DeviceApiTestCase):
    def test_a_delivery_and_a_settlement_each_name_who_made_them(self) -> None:
        """The only name on a row saying a door opened was the party that did not make the
        claim, and `devices.agent.report` is routine, AAL 1 and tenant-wide."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        issued = self.client.post(
            f"/fleet/{device['device_id']}/commands",
            json={"action": "reboot", "idempotency_key": str(uuid.uuid4()),
                  **self.correlation()}, headers=owner)
        command_id = issued.json()["command_id"]
        agent = self.headers(tenant_id, self.grant(tenant_id, ["devices.agent.report"]))
        self.assertEqual(self.client.post(
            f"/fleet/commands/{command_id}/deliver", json=self.correlation(),
            headers=agent).status_code, 200)
        self.assertEqual(self.client.post(
            f"/fleet/commands/{command_id}/settle",
            json={"outcome": "failed", "detail": "the relay did not fire",
                  **self.correlation()}, headers=agent).status_code, 200)
        with psycopg.connect(DSN) as conn, conn.cursor() as cur:
            cur.execute("SET LOCAL ROLE veyro_cp_app")
            cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            cur.execute(
                "SELECT issued_by, delivered_by, settled_by FROM plt01.dev_commands"
                " WHERE command_id = %s", (command_id,))
            row = cur.fetchone()
        assert row is not None
        self.assertIsNotNone(row[1])
        self.assertIsNotNone(row[2])
        self.assertNotEqual(str(row[0]), str(row[1]))

    def test_a_return_to_service_names_whoever_made_it(self) -> None:
        """`activated_by` is final by trigger and correctly so, and a re-activation re-runs
        the commissioning gate -- so the first version left a live door's fire-code
        attribution naming somebody who did not make that decision."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        device = self.live(tenant_id)
        self.client.post(f"/fleet/{device['device_id']}/state",
                         json={"target": "quarantined", "reason": "failed re-test",
                               **self.correlation()}, headers=owner)
        second = self.headers(tenant_id, self.stepped_grant(
            tenant_id, ["devices.device.activate", "devices.device.read"]))
        again = self.client.post(f"/fleet/{device['device_id']}/activate",
                                 json=self.correlation(), headers=second)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertFalse(again.json()["first_activation"])
        with psycopg.connect(DSN) as conn, conn.cursor() as cur:
            cur.execute("SET LOCAL ROLE veyro_cp_app")
            cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            cur.execute(
                "SELECT activated_by, reactivated_by FROM plt01.dev_devices"
                " WHERE device_id = %s", (device["device_id"],))
            row = cur.fetchone()
        assert row is not None
        self.assertIsNotNone(row[1])
        self.assertNotEqual(str(row[0]), str(row[1]))

    def test_a_sync_conflict_records_what_diverged(self) -> None:
        """The route demanded a statement, validated it, answered "recorded" and threw it
        away -- MOD-012's `release_run` shape."""
        tenant_id = self.tenant()
        device = self.live(tenant_id)
        reported = self.client.post(
            f"/fleet/{device['device_id']}/sync-conflicts",
            json={"detail": "the member table diverged", "local_digest": "a" * 64,
                  "remote_digest": "b" * 64, **self.correlation()},
            headers=self.headers(tenant_id, self.grant(
                tenant_id, ["devices.agent.report"])))
        self.assertEqual(reported.status_code, 201, reported.text)
        with psycopg.connect(DSN) as conn, conn.cursor() as cur:
            cur.execute("SET LOCAL ROLE veyro_cp_app")
            cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            cur.execute(
                "SELECT detail, reported_by FROM plt01.dev_sync_conflicts"
                " WHERE conflict_id = %s", (reported.json()["conflict_id"],))
            row = cur.fetchone()
        assert row is not None
        self.assertEqual(row[0], "the member table diverged")
        self.assertIsNotNone(row[1])


class ThePermissionIsAClaimTests(DeviceApiTestCase):
    def test_releasing_firmware_does_not_own_the_device_type_catalogue(self) -> None:
        """All three type routes were gated on `devices.firmware.write` and there was no
        `devices.type.*` permission at all."""
        tenant_id = self.tenant()
        firmware_only = self.headers(tenant_id, self.stepped_grant(
            tenant_id, ["devices.firmware.write", "devices.device.read"]))
        refused = self.client.post("/fleet/types", json={
            "type_code": f"T{uuid.uuid4().hex[:8].upper()}", "vendor": "Acme",
            "model": "Gate", "kind": "turnstile", "display_name": "Acme Gate",
            "capabilities": ["access.actuate"], **self.correlation()},
            headers=firmware_only)
        self.assertEqual(refused.status_code, 403, refused.text)

    def test_a_device_type_is_published_by_somebody_other_than_its_author(self) -> None:
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        created = self.client.post("/fleet/types", json={
            "type_code": f"T{uuid.uuid4().hex[:8].upper()}", "vendor": "Acme",
            "model": "Gate", "kind": "turnstile", "display_name": "Acme Gate",
            "capabilities": ["access.actuate"], **self.correlation()}, headers=owner)
        self.assertEqual(created.status_code, 201, created.text)
        selfpub = self.client.post(
            f"/fleet/types/{created.json()['type_id']}/publish",
            json=self.correlation(), headers=owner)
        self.assertEqual(selfpub.status_code, 409, selfpub.text)
        self.assertIn("other_than_its_author", selfpub.text)

    def test_maintenance_costs_what_quarantine_costs(self) -> None:
        """`OPERABLE` is `{"active"}`, so maintenance stops commands exactly as quarantine
        does -- and the way back is a permission the routine holder does not have."""
        tenant_id = self.tenant()
        device = self.live(tenant_id)
        routine = self.headers(tenant_id, self.grant(
            tenant_id, ["devices.device.write", "devices.device.read"]))
        refused = self.client.post(
            f"/fleet/{device['device_id']}/state",
            json={"target": "maintenance", **self.correlation()}, headers=routine)
        self.assertEqual(refused.status_code, 403, refused.text)


class NothingFreeTextReachesTheOutboxTests(DeviceApiTestCase):
    def test_an_agent_version_is_a_version(self) -> None:
        tenant_id = self.tenant()
        device = self.live(tenant_id)
        agent = self.headers(tenant_id, self.grant(tenant_id, ["devices.agent.report"]))
        leaked = self.client.post(
            f"/fleet/{device['device_id']}/health",
            json={"latency_ms": 12, "error_count": 0, "storage_free_bytes": 400,
                  "agent_version": "jane@example.test dob 1984-02-03",
                  **self.correlation()}, headers=agent)
        self.assertEqual(leaked.status_code, 422, leaked.text)

    def test_a_sync_conflict_digest_is_a_digest(self) -> None:
        tenant_id = self.tenant()
        device = self.live(tenant_id)
        agent = self.headers(tenant_id, self.grant(tenant_id, ["devices.agent.report"]))
        leaked = self.client.post(
            f"/fleet/{device['device_id']}/sync-conflicts",
            json={"detail": "diverged",
                  "local_digest": "jane.doe@example.com 1984-02-03 member 9912 padxxx0",
                  "remote_digest": "b" * 64, **self.correlation()}, headers=agent)
        self.assertEqual(leaked.status_code, 422, leaked.text)

    def test_a_firmware_version_is_a_version(self) -> None:
        tenant_id = self.tenant()
        type_id = self.device_type(tenant_id)
        leaked = self.client.post("/fleet/firmware", json={
            "type_id": type_id, "version": "1.0 built for jane.doe@example.com",
            "image_ref": "oci:acme/gate:1.0", "image_digest": "d" * 64,
            "release_notes": "notes", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(leaked.status_code, 422, leaked.text)

    def test_a_peripheral_inventory_is_bounded(self) -> None:
        tenant_id = self.tenant()
        device = self.live(tenant_id)
        agent = self.headers(tenant_id, self.grant(tenant_id, ["devices.agent.report"]))
        huge = self.client.post(
            f"/fleet/{device['device_id']}/health",
            json={"latency_ms": 12, "error_count": 0, "storage_free_bytes": 400,
                  "agent_version": "1.4.2",
                  "peripherals": {"reader": "x" * 2000}, **self.correlation()},
            headers=agent)
        self.assertEqual(huge.status_code, 422, huge.text)


class TheSweepDoesNotAbortTests(DeviceApiTestCase):
    def test_a_device_still_offline_does_not_stop_the_sweep(self) -> None:
        """`append_event` raises on a duplicate key, so the second sweep of a device that
        was still offline rolled the whole batch back -- and every device that had gone
        quiet behind it was never reported."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        first = self.live(tenant_id)
        agent = self.headers(tenant_id, self.grant(tenant_id, ["devices.agent.report"]))
        self.client.post(f"/fleet/{first['device_id']}/health",
                         json={"latency_ms": 12, "error_count": 0,
                               "storage_free_bytes": 400, "agent_version": "1.4.2",
                               **self.correlation()}, headers=agent)
        with psycopg.connect(DSN) as conn, conn.cursor() as cur:
            cur.execute("SET LOCAL ROLE veyro_cp_app")
            cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            cur.execute(
                "UPDATE plt01.dev_devices SET last_seen_at = now() - interval '2 hours'"
                " WHERE device_id = %s", (first["device_id"],))
        one = self.client.post("/fleet/offline-sweep", json=self.correlation(),
                               headers=owner)
        self.assertEqual(one.status_code, 200, one.text)
        self.assertEqual(one.json()["offline"], 1, one.text)
        second = self.live(tenant_id, type_id=first["type_id"])
        self.client.post(f"/fleet/{second['device_id']}/health",
                         json={"latency_ms": 12, "error_count": 0,
                               "storage_free_bytes": 400, "agent_version": "1.4.2",
                               **self.correlation()}, headers=agent)
        with psycopg.connect(DSN) as conn, conn.cursor() as cur:
            cur.execute("SET LOCAL ROLE veyro_cp_app")
            cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            cur.execute(
                "UPDATE plt01.dev_devices SET last_seen_at = now() - interval '1 hour'"
                " WHERE device_id = %s", (second["device_id"],))
        two = self.client.post("/fleet/offline-sweep", json=self.correlation(),
                               headers=owner)
        self.assertEqual(two.status_code, 200, two.text)
        self.assertEqual(two.json()["offline"], 1, two.text)
        self.assertEqual(two.json()["devices"], [second["device_id"]], two.text)


class TheTriggerHoldsForTheWriterThatIsNotTheServiceTests(DeviceApiTestCase):
    """Two connections, because a single session cannot race itself.

    The service happens to be safe -- `publish_snapshot` locks the device row and revocation
    updates it -- so the half that failed is the one the trigger exists for. MOD-019's
    `FOR SHARE` finding, one notch weaker: this took no lock at all.
    """

    def test_a_snapshot_cannot_be_written_below_an_epoch_being_bumped(self) -> None:
        tenant_id = self.tenant()
        device = self.live(tenant_id)
        device_id = device["device_id"]
        results: list[str] = []
        lock = threading.Lock()

        def revoke() -> None:
            outcome = "ok"
            try:
                with psycopg.connect(DSN) as conn, conn.cursor() as cur:
                    cur.execute("SET LOCAL ROLE veyro_cp_app")
                    cur.execute("SELECT set_config('app.tenant_id', %s, true)",
                                (tenant_id,))
                    cur.execute(
                        "UPDATE plt01.dev_devices"
                        " SET revocation_epoch = revocation_epoch + 1"
                        " WHERE device_id = %s", (device_id,))
                    cur.execute("SELECT pg_sleep(1.5)")
            except Exception as e:  # noqa: BLE001
                outcome = f"unexpected {type(e).__name__}: {e}"
            with lock:
                results.append(outcome)

        def snapshot() -> None:
            outcome = "ok"
            try:
                with psycopg.connect(DSN) as conn, conn.cursor() as cur:
                    cur.execute("SET LOCAL ROLE veyro_cp_app")
                    cur.execute("SELECT set_config('app.tenant_id', %s, true)",
                                (tenant_id,))
                    cur.execute("SELECT pg_sleep(0.4)")
                    cur.execute(
                        "INSERT INTO plt01.dev_policy_snapshots (tenant_id, device_id,"
                        " revocation_epoch, content_digest, expires_at, issued_by,"
                        " correlation_id) VALUES (%s, %s, (SELECT revocation_epoch FROM"
                        " plt01.dev_devices WHERE device_id = %s), %s,"
                        " now() + interval '12 hours', %s, %s)",
                        (tenant_id, device_id, device_id, "e" * 64, str(uuid.uuid4()),
                         str(uuid.uuid4())))
            except psycopg.errors.RaiseException as e:
                outcome = str(e).splitlines()[0]
            except Exception as e:  # noqa: BLE001
                outcome = f"unexpected {type(e).__name__}: {e}"
            with lock:
                results.append(outcome)

        threads = [threading.Thread(target=revoke), threading.Thread(target=snapshot)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(results), 2, results)
        self.assertNotIn(True, ["unexpected" in r for r in results], results)
        with psycopg.connect(DSN) as conn, conn.cursor() as cur:
            cur.execute("SET LOCAL ROLE veyro_cp_app")
            cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            cur.execute(
                "SELECT s.revocation_epoch, d.revocation_epoch"
                " FROM plt01.dev_policy_snapshots s JOIN plt01.dev_devices d"
                "   ON d.device_id = s.device_id"
                " WHERE s.device_id = %s ORDER BY s.issued_at DESC LIMIT 1",
                (device_id,))
            row = cur.fetchone()
        if row is not None:
            self.assertGreaterEqual(
                row[0], row[1],
                "a snapshot was written below the device's revocation epoch")


class ASupersessionStaysWithinItsDeviceTests(DeviceApiTestCase):
    def test_one_doors_commissioning_cannot_supersede_anothers(self) -> None:
        """A fire door's chain read "re-commissioned as fail_secure, no independent fire
        release" through a pointer that crossed doors."""
        tenant_id = self.tenant()
        first = self.live(tenant_id)
        second = self.live(tenant_id, type_id=first["type_id"])
        with psycopg.connect(DSN) as conn, conn.cursor() as cur:
            cur.execute("SET LOCAL ROLE veyro_cp_app")
            cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cur.execute(
                "SELECT profile_id, device_id FROM plt01.dev_safety_profiles"
                " WHERE device_id IN (%s, %s) ORDER BY device_id = %s DESC",
                (first["device_id"], second["device_id"], first["device_id"]))
            rows = cur.fetchall()
            mine = [r for r in rows if str(r[1]) == first["device_id"]][0]
            theirs = [r for r in rows if str(r[1]) == second["device_id"]][0]
            with self.assertRaises(psycopg.errors.RaiseException) as caught:
                cur.execute(
                    "UPDATE plt01.dev_safety_profiles SET superseded_at = now(),"
                    " superseded_by = %s, supersede_correlation_id = %s"
                    " WHERE profile_id = %s",
                    (theirs[0], str(uuid.uuid4()), mine[0]))
        self.assertIn("different door", str(caught.exception))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
